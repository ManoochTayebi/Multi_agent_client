"""Authenticated API, chat UI, operator review queue and aggregate monitoring."""
import hashlib
import logging
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func
from atlas import db
from atlas.config import settings
from atlas.dataset import seed
from atlas.tools import Tools
from atlas.actions import Actions, Conflict
from atlas.retrieval import Knowledge
from atlas.model import Model
from atlas.agents import Pipeline, ROLES, requests_human
from atlas.schemas import SessionRequest, ChatRequest, Decision, SupportMessage, SupportClose

log = logging.getLogger('atlas')


def create_app(config=None):
    config = config or settings()
    gate = threading.BoundedSemaphore(8)
    session_locks = {}
    lock_guard = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        config.validate_runtime()
        engine = db.make_engine(config.database_url)
        seed(engine, config.data_dir)
        tools = Tools(engine, config)
        actions = Actions(engine, tools)
        app.state.engine = engine
        app.state.pipeline = Pipeline(tools, Knowledge(config), Model(config), actions)
        app.state.actions = actions
        app.state.support = app.state.pipeline.support
        yield
        engine.dispose()

    app = FastAPI(title='Atlas CustomerAI', version='1.0.0', lifespan=lifespan)
    app.mount('/static', StaticFiles(directory=Path(__file__).parent/'static'), name='static')

    def bearer(authorization: str = Header(default='')):
        if not authorization.startswith('Bearer '):
            raise HTTPException(401, 'Bearer session token required')
        token = authorization[7:]
        digest = hashlib.sha256(token.encode()).hexdigest()
        with app.state.engine.connect() as c:
            row = c.execute(select(db.sessions).where(db.sessions.c.token_hash == digest)).mappings().first()
        if not row or row['expires_at'].replace(tzinfo=timezone.utc) < db.now():
            raise HTTPException(401, 'Session is invalid or expired')
        return dict(row)

    def admin(x_admin_key: str = Header(default='')):
        if not config.admin_api_key or not secrets.compare_digest(x_admin_key, config.admin_api_key):
            raise HTTPException(403, 'Operator key required')

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).parent/'static'/'index.html')

    @app.get('/health')
    def health():
        with app.state.engine.connect() as c:
            c.execute(select(1))
        count = app.state.pipeline.knowledge.collection.count()
        return {'status':'ok', 'mode':config.atlas_mode, 'policy_chunks':count,
                'indexed_products':app.state.pipeline.knowledge.product_collection.count(),
                'retrieval':'semantic' if config.embedding_model else 'lexical',
                'chat_model':config.openai_model if config.atlas_mode == 'llm' else None,
                'synthetic_clock':str(config.as_of_date), 'demo_access':config.demo_access,
                'payments':'simulation'}

    @app.get('/api/agents')
    def agents():
        return ROLES

    @app.post('/api/sessions')
    def session(body: SessionRequest, authorization: str = Header(default='')):
        customer_id = body.customer_id
        if not config.demo_access:
            credential = authorization.removeprefix('Bearer ')
            authorized_customer = next((value for key, value in config.customer_tokens.items()
                if secrets.compare_digest(key, credential)), None)
            if authorized_customer != customer_id:
                raise HTTPException(401, 'Customer credential does not match account')
        try:
            app.state.pipeline.tools.profile(customer_id)
        except ValueError:
            raise HTTPException(404, 'Customer not found')
        token = secrets.token_urlsafe(32)
        sid = db.uid()
        with app.state.engine.begin() as c:
            c.execute(db.sessions.insert().values(id=sid, customer_id=customer_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(), created_at=db.now(),
                expires_at=db.now()+timedelta(hours=24)))
        return {'session_id':sid, 'token':token, 'customer_id':customer_id, 'expires_in':86400}

    @app.get('/api/me')
    def me(identity=Depends(bearer)):
        tools = app.state.pipeline.tools
        return {'profile':tools.profile(identity['customer_id']),
                'orders':tools.recent_orders(identity['customer_id'])}

    def acquire_session(identity):
        # Serialize deletion and chat; acquiring under the map guard also makes pruning safe.
        with lock_guard:
            if len(session_locks) > 10000:
                for key in list(session_locks):
                    if not session_locks[key].locked():
                        session_locks.pop(key)
            lock = session_locks.setdefault(identity['id'], threading.Lock())
            if not lock.acquire(blocking=False):
                raise HTTPException(409, 'Another request is running in this session; wait and retry')
        try:
            # Authentication may have completed just before another request deleted the session.
            with app.state.engine.connect() as c:
                exists = c.scalar(select(db.sessions.c.id).where(db.sessions.c.id == identity['id']))
            if not exists:
                raise HTTPException(401, 'Session is invalid or expired')
        except Exception:
            lock.release()
            raise
        return lock

    @app.post('/api/chat')
    def chat(body: ChatRequest, identity=Depends(bearer)):
        session_lock = acquire_session(identity)
        try:
            thread = app.state.support.for_session(identity['id'])
        except Exception:
            session_lock.release()
            raise
        human_conversation = (body.request_human or requests_human(body.message)
                              or bool(thread and thread['status'] != 'closed'))
        admitted = not human_conversation and gate.acquire(blocking=False)
        if not human_conversation and not admitted:
            session_lock.release()
            raise HTTPException(429, 'Capacity reached; retry shortly', headers={'Retry-After':'3'})
        start, run_id = time.perf_counter(), db.uid()
        try:
            result = app.state.pipeline.run(body.message, identity['customer_id'], identity['id'], run_id,
                                            request_human=body.request_human)
            result = {k:v for k,v in result.items() if k not in {'customer_id','session_id','message','request_human'}}
            result['mode'] = config.atlas_mode
            result['run_id'] = run_id
            result['latency_ms'] = int((time.perf_counter()-start)*1000)
            result = jsonable_encoder(result)
            with app.state.engine.begin() as c:
                c.execute(db.runs.insert().values(id=run_id, session_id=identity['id'],
                    status='completed' if result['quality']['passed'] else 'needs_review', result=result,
                    latency_ms=result['latency_ms'], created_at=db.now()))
                for role, text in [('customer', body.message), ('assistant', result['answer'])]:
                    c.execute(db.messages.insert().values(id=db.uid(), session_id=identity['id'],
                        agent='conversation', role=role, content={'text':text, 'run_id':run_id}, created_at=db.now()))
            log.info('run_finished run_id=%s latency_ms=%s quality=%s', run_id,
                     result['latency_ms'], result['quality']['passed'])
            return result
        except Exception:
            log.exception('run_failed run_id=%s', run_id)
            with app.state.engine.begin() as c:
                c.execute(db.runs.insert().values(id=run_id, session_id=identity['id'], status='failed',
                    result={'error':'Internal failure'}, latency_ms=int((time.perf_counter()-start)*1000),
                    created_at=db.now()))
            raise HTTPException(503, 'Request could not complete; retry or contact support')
        finally:
            if admitted:
                gate.release()
            session_lock.release()

    @app.get('/api/support')
    def support_status(identity=Depends(bearer)):
        thread = app.state.support.for_session(identity['id'])
        return app.state.support.detail(thread['id']) if thread else {'thread':None, 'messages':[], 'events':[]}

    @app.post('/api/support/resume')
    def resume_ai(body: SupportClose, identity=Depends(bearer)):
        session_lock = acquire_session(identity)
        try:
            thread = app.state.support.for_session(identity['id'])
            if not thread:
                raise HTTPException(404, 'Support conversation not found')
            return app.state.support.close(thread['id'], 'customer', body.reason)
        finally:
            session_lock.release()

    @app.get('/admin/support', dependencies=[Depends(admin)])
    def support_queue():
        with app.state.engine.connect() as c:
            return [dict(x) for x in c.execute(select(db.support_threads).where(
                db.support_threads.c.status != 'closed').order_by(db.support_threads.c.updated_at)).mappings()]

    def support_mutation(thread_id, operation):
        try:
            thread = app.state.support.get(thread_id)
            session_lock = acquire_session({'id':thread['session_id']})
            try:
                return operation(app.state.support, thread_id)
            finally:
                session_lock.release()
        except KeyError:
            raise HTTPException(404, 'Support conversation not found')
        except Conflict as exc:
            raise HTTPException(409, str(exc))

    @app.get('/admin/support/{thread_id}', dependencies=[Depends(admin)])
    def support_detail(thread_id: str):
        try:
            detail = app.state.support.detail(thread_id)
        except KeyError:
            raise HTTPException(404, 'Support conversation not found')
        with app.state.engine.connect() as c:
            conversation = c.execute(select(db.messages.c.role, db.messages.c.content, db.messages.c.created_at)
                .where(db.messages.c.session_id == detail['thread']['session_id'], db.messages.c.agent == 'conversation')
                .order_by(db.messages.c.created_at.desc()).limit(40)).mappings().all()
            runs = list(c.execute(select(db.runs.c.result).where(
                db.runs.c.session_id == detail['thread']['session_id'])
                .order_by(db.runs.c.created_at.desc()).limit(10)).scalars())
        return {**detail, 'conversation':list(reversed([dict(x) for x in conversation])), 'runs':runs}

    @app.post('/admin/support/{thread_id}/claim', dependencies=[Depends(admin)])
    def claim_support(thread_id: str):
        return support_mutation(thread_id, lambda support, tid:support.claim(tid))

    @app.post('/admin/support/{thread_id}/messages', dependencies=[Depends(admin)])
    def reply_support(thread_id: str, body: SupportMessage):
        def reply(support, tid):
            support.post(tid, 'operator', body.message)
            return support.detail(tid)
        return support_mutation(thread_id, reply)

    @app.post('/admin/support/{thread_id}/close', dependencies=[Depends(admin)])
    def close_support(thread_id: str, body: SupportClose):
        return support_mutation(thread_id, lambda support, tid:support.close(tid, 'human_operator', body.reason))

    @app.get('/api/history')
    def history(identity=Depends(bearer)):
        with app.state.engine.connect() as c:
            return list(c.execute(select(db.runs.c.result).where(db.runs.c.session_id == identity['id'])
                .order_by(db.runs.c.created_at.desc()).limit(20)).scalars())

    @app.post('/api/actions/{action_id}/confirm')
    def confirm(action_id: str, identity=Depends(bearer)):
        try:
            return app.state.actions.confirm(action_id, identity['customer_id'])
        except KeyError:
            raise HTTPException(404, 'Action not found')

    @app.get('/admin/reviews', dependencies=[Depends(admin)])
    def reviews():
        with app.state.engine.connect() as c:
            return [dict(x) for x in c.execute(select(db.actions).where(
                db.actions.c.status == 'pending_review')).mappings()]

    @app.post('/admin/actions/{action_id}/decision', dependencies=[Depends(admin)])
    def decide(action_id: str, body: Decision):
        try:
            return app.state.actions.decide(action_id, body.approve, body.reason)
        except KeyError:
            raise HTTPException(404, 'Action not found')
        except Conflict as e:
            raise HTTPException(409, str(e))

    @app.get('/admin/audit/{action_id}', dependencies=[Depends(admin)])
    def audit(action_id: str):
        with app.state.engine.connect() as c:
            return [dict(x) for x in c.execute(select(db.audit).where(
                db.audit.c.action_id == action_id).order_by(db.audit.c.created_at)).mappings()]

    @app.post('/admin/outbox/drain', dependencies=[Depends(admin)])
    def drain():
        return {'processed':app.state.actions.drain(), 'provider':'simulation'}

    @app.get('/metrics', response_class=PlainTextResponse, dependencies=[Depends(admin)])
    def metrics():
        with app.state.engine.connect() as c:
            total = c.scalar(select(func.count()).select_from(db.runs))
            failed = c.scalar(select(func.count()).select_from(db.runs).where(db.runs.c.status == 'failed'))
            review = c.scalar(select(func.count()).select_from(db.runs).where(db.runs.c.status == 'needs_review'))
            latency = c.scalar(select(func.coalesce(func.sum(db.runs.c.latency_ms),0)))
        model = app.state.pipeline.model
        return (f'atlas_runs_total {total}\natlas_runs_failed_total {failed}\n'
                f'atlas_runs_review_total {review}\natlas_latency_milliseconds_sum {latency}\n'
                f'atlas_llm_calls_process_total {model.calls}\natlas_llm_tokens_process_total {model.tokens}\n')

    @app.delete('/api/session', status_code=204)
    def delete_session(identity=Depends(bearer)):
        session_lock = acquire_session(identity)
        try:
            # Financial audit records remain; they do not contain session message text.
            with app.state.engine.begin() as c:
                thread_ids = select(db.support_threads.c.id).where(db.support_threads.c.session_id == identity['id'])
                c.execute(db.support_messages.delete().where(db.support_messages.c.thread_id.in_(thread_ids)))
                c.execute(db.support_events.delete().where(db.support_events.c.thread_id.in_(thread_ids)))
                c.execute(db.support_threads.delete().where(db.support_threads.c.session_id == identity['id']))
                c.execute(db.messages.delete().where(db.messages.c.session_id == identity['id']))
                c.execute(db.runs.delete().where(db.runs.c.session_id == identity['id']))
                c.execute(db.sessions.delete().where(db.sessions.c.id == identity['id']))
            return Response(status_code=204)
        finally:
            session_lock.release()

    return app


app = create_app()
