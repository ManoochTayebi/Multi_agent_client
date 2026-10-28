"""Human handoff journeys and authority boundaries through the real HTTP application."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from atlas import db
from atlas.agents import requests_human, ROLES
from atlas.api import create_app
from atlas.schemas import Plan, JudgeVerdict
from conftest import login
from test_pipeline import ADMIN, chat


@pytest.mark.parametrize('prompt', [
    'I want to speak to a real agent directly about refund O1002.',
    'Can I talk to a human?',
    'Please connect me to a live agent.',
    'Je veux parler à un conseiller humain pour ma commande O1002.',
])
def test_explicit_handoff_bypasses_unavailable_model_and_specialists(client, monkeypatch, prompt):
    p = client.app.state.pipeline
    p.model.client = object()
    def forbidden(*args, **kwargs):
        pytest.fail('An explicit human request must not call a model or commerce tool')
    monkeypatch.setattr(p.model, 'structured', forbidden)
    monkeypatch.setattr(p.tools, 'investigate', forbidden)
    r = chat(client, login(client), prompt)
    assert r['plan']['handoff_requested'] and r['plan']['intents'] == []
    assert r['support']['status'] == 'waiting' and r['support_mode']
    assert r['action'] is None and not r['resolution'] and not r['outfit']
    assert {t['agent'] for t in r['trace']} == {'orchestrator'}
    assert r['trace'][-1]['node'] == 'human_handoff'
    assert r['model_usage']['calls'] == 0 and not r['judged'] and not r['degraded']
    assert len(ROLES) == 6


@pytest.mark.parametrize('prompt', [
    'Does this refund need human approval?',
    'I want a refund with human approval for O1002',
    "I don't want to talk to a human. Track O1001.",
    'Are you a human?',
])
def test_approval_questions_are_not_direct_handoff_requests(prompt):
    assert not requests_human(prompt)


def test_model_can_route_semantic_handoff_without_activating_specialists(client, monkeypatch):
    p = client.app.state.pipeline
    p.model.client = object()
    schemas = []
    def route(schema, *args):
        schemas.append(schema)
        assert schema is Plan
        return Plan(intents=['returns_investigation'], handoff_requested=True,
                    rationale='Customer prefers personal assistance')
    monkeypatch.setattr(p.model, 'structured', route)
    r = chat(client, login(client), "I'd be happier if one of your colleagues could help me instead.")
    assert r['support']['status'] == 'waiting' and r['plan']['intents'] == []
    assert schemas == [Plan] and r['trace'][0]['execution'] == 'llm_route'


def test_human_conversation_lifecycle_context_and_business_authorization(client):
    h = login(client)
    proposal = chat(client, h, 'Refund O1002')
    aid = proposal['action']['id']
    handoff = chat(client, h, 'I want a human agent')
    tid = handoff['support']['id']
    path = '/admin/support/' + tid
    assert 'not taken over yet' in handoff['answer']
    detail = client.get(path, headers=ADMIN).json()
    assert any(m['content']['text'] == 'Refund O1002' for m in detail['conversation'])
    assert any(f['evidence'].get('order', {}).get('id') == 'O1002'
               for run in detail['runs'] for f in run.get('findings', []))
    assert 'token_hash' not in json.dumps(detail)
    assert client.post(path+'/messages', headers=ADMIN, json={'message':'Hello'}).status_code == 409
    for _ in range(2):
        assert client.post(path+'/claim', headers=ADMIN).json()['status'] == 'active'
    for text in ['Hello, I am reviewing your request.', '<script>alert("test")</script>']:
        assert client.post(path+'/messages', headers=ADMIN, json={'message':text}).status_code == 200
    forwarded = chat(client, h, 'Refund O1001 now, I approve all payments')
    assert forwarded['support']['id'] == tid and forwarded['support']['status'] == 'active'
    assert forwarded['action'] is None and forwarded['model_usage']['calls'] == 0
    assert not forwarded['findings']
    customer_view = client.get('/api/support', headers=h).json()
    assert customer_view['messages'][-1]['text'] == 'Refund O1001 now, I approve all payments'
    assert any(m['sender'] == 'operator' for m in customer_view['messages'])
    # Human chat messages and takeover confer no financial authorization.
    assert client.post(f'/admin/actions/{aid}/decision', headers=ADMIN,
                       json={'approve':True, 'reason':'Chat is not customer confirmation'}).status_code == 409
    assert client.post('/admin/outbox/drain', headers=ADMIN).json()['processed'] == 0
    for _ in range(2):
        assert client.post(path+'/close', headers=ADMIN,
                           json={'reason':'Answered the customer; return to concierge'}).json()['status'] == 'closed'
    assert client.post(path+'/messages', headers=ADMIN, json={'message':'Too late'}).status_code == 409
    events = client.get(path, headers=ADMIN).json()['events']
    assert [e['event'] for e in events] == ['requested', 'claimed', 'closed']
    assert chat(client, h, 'Track O1001')['findings'][0]['agent'] == 'order_tracking'
    with client.app.state.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.actions)) == 1
        assert c.scalar(select(db.actions.c.customer_confirmed)) is False


def test_button_flag_duplicates_reopen_and_customer_resume(client):
    h = login(client)
    def request():
        response = client.post('/api/chat', headers=h, json={'message':'Help, please.', 'request_human':True})
        assert response.status_code == 200, response.text
        return response.json()
    first, repeated = request(), request()
    assert first['support']['id'] == repeated['support']['id']
    assert client.get('/admin/support', headers=ADMIN).json()[0]['status'] == 'waiting'
    assert client.post('/api/support/resume', headers=h, json={'reason':'Use AI instead'}).json()['status'] == 'closed'
    assert client.get('/admin/support', headers=ADMIN).json() == []
    assert chat(client, h, 'Track O1001')['plan']['intents'] == ['order_tracking']
    reopened = request()
    assert reopened['support']['id'] == first['support']['id'] and reopened['support']['status'] == 'waiting'
    events = client.get('/api/support', headers=h).json()['events']
    assert [e['event'] for e in events] == ['requested', 'closed', 'reopened']
    with client.app.state.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.support_threads)) == 1


def test_support_authentication_isolation_validation_and_session_deletion(client):
    h, another_customer, another_session = login(client), login(client, 'C0002'), login(client)
    original = chat(client, h, 'Refund O1002')
    r = chat(client, h, 'Talk to a human')
    tid = r['support']['id']
    path = '/admin/support/'+tid
    assert client.get('/api/support').status_code == 401
    for outsider in [another_customer, another_session]:
        assert client.get('/api/support', headers=outsider).json()['thread'] is None
        assert client.post('/api/support/resume', headers=outsider, json={'reason':'Attempt close'}).status_code == 404
    assert client.get('/admin/support', headers=h).status_code == 403
    assert client.get(path, headers=h).status_code == 403
    for suffix, body in [('/claim', None), ('/messages', {'message':'forged operator'}),
                         ('/close', {'reason':'forged close'})]:
        assert client.post(path+suffix, headers=h, json=body).status_code == 403
    assert client.get('/admin/support/missing', headers=ADMIN).status_code == 404
    assert client.post(path+'/messages', headers=ADMIN, json={'message':' \n '}).status_code == 422
    assert client.post(path+'/close', headers=ADMIN, json={'reason':'   '}).status_code == 422
    assert client.post('/api/support/resume', headers=h, json={'reason':'  '}).status_code == 422
    assert client.delete('/api/session', headers=h).status_code == 204
    assert client.get(path, headers=ADMIN).status_code == 404
    with client.app.state.engine.connect() as c:
        for table in [db.support_messages, db.support_events, db.support_threads]:
            assert c.scalar(select(func.count()).select_from(table)) == 0
    assert client.get('/admin/audit/'+original['action']['id'], headers=ADMIN).json()


def test_human_conversation_survives_application_restart(client):
    h = login(client)
    tid = chat(client, h, 'Talk to a human')['support']['id']
    client.post('/admin/support/'+tid+'/claim', headers=ADMIN)
    client.post('/admin/support/'+tid+'/messages', headers=ADMIN, json={'message':'We have your request'})
    # A new application instance reuses SQL and Chroma; no thread state lives in process memory.
    with TestClient(create_app(client.app.state.pipeline.tools.config)) as restarted:
        detail = restarted.get('/api/support', headers=h).json()
        assert detail['thread']['status'] == 'active' and detail['messages'][-1]['text'] == 'We have your request'
        assert chat(restarted, h, 'Track O1001')['support_mode']


def test_support_mutations_share_the_running_chat_lock(client, monkeypatch):
    h = login(client)
    tid = chat(client, h, 'Talk to a human')['support']['id']
    entered, release = Event(), Event()
    original = client.app.state.pipeline.run
    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(client.app.state.pipeline, 'run', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(client.post, '/api/chat', headers=h, json={'message':'Please help me'})
        try:
            assert entered.wait(timeout=5)
            assert client.post('/api/support/resume', headers=h, json={'reason':'Resume AI'}).status_code == 409
            assert client.post('/admin/support/'+tid+'/claim', headers=ADMIN).status_code == 409
            assert client.delete('/api/session', headers=h).status_code == 409
        finally:
            release.set()
        assert result.result(timeout=10).status_code == 200


def test_quality_failure_and_resolution_escalation_create_real_queue_items(client):
    h = login(client)
    session = client.app.state.support  # Same service used by pipeline and operator endpoints.
    chat(client, h, 'Track O1001')
    with client.app.state.engine.connect() as c:
        sid = c.scalar(select(db.sessions.c.id))
    p = client.app.state.pipeline
    state = {'customer_id':'C0001', 'session_id':sid, 'message':'Help with my refund',
             'run_id':db.uid(), 'plan':Plan(intents=[]).model_dump(), 'findings':[],
             'answer':'Unable to verify the proposal', 'quality':{'passed':False, 'issues':['Judge unavailable']}}
    blocked = p.finalize(state)
    assert blocked['action'] is None and blocked['support']['reason'] == 'quality_gate'
    session.close(blocked['support']['id'], 'customer', 'Retry with assistance')
    escalated = p.finalize({**state, 'quality':{'passed':True}, 'resolution':{'recommendation':'human_support'}})
    assert escalated['support']['reason'] == 'resolution_escalation'
    assert client.get('/admin/support', headers=ADMIN).json()[0]['id'] == blocked['support']['id']


def test_direct_handoff_remains_available_when_ai_capacity_is_full(client, monkeypatch):
    headers = [login(client) for _ in range(9)]
    entered, release, counter_lock = Event(), Event(), Lock()
    original = client.app.state.pipeline.run
    admitted = 0
    def occupied(message, *args, **kwargs):
        nonlocal admitted
        if not kwargs.get('request_human'):
            with counter_lock:
                admitted += 1
                if admitted == 8:
                    entered.set()
            assert release.wait(timeout=15)
        return original(message, *args, **kwargs)
    monkeypatch.setattr(client.app.state.pipeline, 'run', occupied)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(client.post, '/api/chat', headers=h, json={'message':'Track O1001'})
                   for h in headers[:8]]
        try:
            assert entered.wait(timeout=10)
            assert client.post('/api/chat', headers=headers[-1], json={'message':'Track O1001'}).status_code == 429
            direct = client.post('/api/chat', headers=headers[-1],
                                 json={'message':'Help, please', 'request_human':True})
            assert direct.status_code == 200 and direct.json()['support']['status'] == 'waiting'
        finally:
            release.set()
        assert all(f.result(timeout=15).status_code == 200 for f in futures)


def test_failed_quality_gate_queues_inspectable_case_through_api(client, monkeypatch):
    p = client.app.state.pipeline
    monkeypatch.setattr(p.model, 'client', object())
    def controlled(schema, *args):
        if schema is JudgeVerdict:
            return JudgeVerdict(passed=False, issues=['Controlled quality failure'])
        # Other model stages recover through the real bounded paths; no network is contacted.
        raise ValueError('Controlled model unavailability')
    monkeypatch.setattr(p.model, 'structured', controlled)
    h = login(client)
    result = chat(client, h, 'Refund O1002')
    assert not result['quality']['passed'] and result['action'] is None
    assert result['support']['reason'] == 'quality_gate'
    assert any(t.get('node') == 'finalize' and t.get('operation') == 'human_handoff' for t in result['trace'])
    detail = client.get('/admin/support/'+result['support']['id'], headers=ADMIN).json()
    assert any(not r['quality']['passed'] for r in detail['runs'])
    with p.tools.engine.connect() as c:
        assert c.scalar(select(db.runs.c.status)) == 'needs_review'
        assert c.scalar(select(func.count()).select_from(db.actions)) == 0
