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
from sqlalchemy import select, func
from atlas import db
from atlas.config import settings
from atlas.dataset import seed
from atlas.tools import Tools
from atlas.actions import Actions, Conflict
from atlas.retrieval import Knowledge
from atlas.model import Model
from atlas.agents import Pipeline, ROLES
from atlas.schemas import SessionRequest, ChatRequest, Decision

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
        yield
        engine.dispose()

    app = FastAPI(title='Atlas CustomerAI', version='1.0.0', lifespan=lifespan)

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

    @app.post('/api/chat')
    def chat(body: ChatRequest, identity=Depends(bearer)):
        with lock_guard:
            if len(session_locks) > 10000:
                # Idle locks are safe to discard; active ones remain to preserve serialization.
                for key in list(session_locks):
                    if not session_locks[key].locked():
                        session_locks.pop(key)
            session_lock = session_locks.setdefault(identity['id'], threading.Lock())
        if not session_lock.acquire(blocking=False):
            raise HTTPException(409, 'Another message is running in this session')
        if not gate.acquire(blocking=False):
            session_lock.release()
            raise HTTPException(429, 'Capacity reached; retry shortly', headers={'Retry-After':'3'})
        start, run_id = time.perf_counter(), db.uid()
        try:
            result = app.state.pipeline.run(body.message, identity['customer_id'], identity['id'], run_id)
            result = {k:v for k,v in result.items() if k not in {'customer_id','session_id','message'}}
            result['mode'] = config.atlas_mode
            result['run_id'] = run_id
            result['latency_ms'] = int((time.perf_counter()-start)*1000)
            result = jsonable_encoder(result)
            with app.state.engine.begin() as c:
                c.execute(db.runs.insert().values(id=run_id, session_id=identity['id'],
                    status='completed' if result['quality']['passed'] else 'needs_review', result=result,
                    latency_ms=result['latency_ms'], created_at=db.now()))
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
            gate.release()
            session_lock.release()

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
        # Financial audit records remain; they do not contain session message text.
        with app.state.engine.begin() as c:
            c.execute(db.messages.delete().where(db.messages.c.session_id == identity['id']))
            c.execute(db.runs.delete().where(db.runs.c.session_id == identity['id']))
            c.execute(db.sessions.delete().where(db.sessions.c.id == identity['id']))
        return Response(status_code=204)

    return app


app = create_app()
