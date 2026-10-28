"""User-visible reliability regressions found in the repository review."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from atlas import db
from atlas.config import Settings
from atlas.model import Model
from atlas.schemas import Plan
from conftest import login
from test_pipeline import ADMIN, chat


def test_empty_model_response_is_not_a_valid_routing_plan():
    model = Model(Settings(_env_file=None))
    model.request = lambda *a, **kw:SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content='{}'))])
    with pytest.raises(ValidationError, match='intents'):
        model.structured(Plan, 'Route a customer request', {'message':'Refund O1002'})
    assert Plan(intents=[]).intents == []  # An explicit no-task plan remains valid.


def test_operator_reason_cannot_be_only_whitespace(client):
    h = login(client)
    r = chat(client, h, 'Refund O1002')
    aid = r['action']['id']
    client.post(f'/api/actions/{aid}/confirm', headers=h)
    response = client.post(f'/admin/actions/{aid}/decision', headers=ADMIN,
                           json={'approve':True, 'reason':'   \n  '})
    assert response.status_code == 422
    assert client.post('/admin/outbox/drain', headers=ADMIN).json()['processed'] == 0
    assert client.get('/admin/reviews', headers=ADMIN).json()[0]['id'] == aid


def test_cannot_delete_session_while_its_chat_is_running(client, monkeypatch):
    h = login(client)
    started, release = Event(), Event()
    original = client.app.state.pipeline.run
    def slow(*args, **kwargs):
        started.set()
        assert release.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(client.app.state.pipeline, 'run', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/chat', headers=h, json={'message':'Track O1001'})
        try:
            assert started.wait(timeout=5)
            assert client.delete('/api/session', headers=h).status_code == 409
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 200
    assert client.delete('/api/session', headers=h).status_code == 204
    assert client.get('/api/history', headers=h).status_code == 401
    with client.app.state.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.messages)) == 0
        assert c.scalar(select(func.count()).select_from(db.runs)) == 0


@pytest.mark.parametrize(('status','phrase'), [
    ('pending_review','awaiting human review'),
    ('queued_simulation','queued for simulated processing'),
    ('completed_simulation','completed as a simulation'),
    ('rejected','rejected by the operator'),
])
def test_repeated_refund_reports_existing_lifecycle(client, status, phrase):
    h = login(client)
    original = chat(client, h, 'Refund O1002')
    aid = original['action']['id']
    client.post(f'/api/actions/{aid}/confirm', headers=h)
    if status != 'pending_review':
        client.post(f'/admin/actions/{aid}/decision', headers=ADMIN,
                    json={'approve':status != 'rejected', 'reason':'Reviewed the fictional receipt'})
    if status == 'completed_simulation':
        client.post('/admin/outbox/drain', headers=ADMIN)
    repeated = chat(client, h, 'Refund O1002')
    assert repeated['action']['id'] == aid and repeated['action']['status'] == status
    assert phrase in repeated['answer'].lower()
    assert 'Confirm the proposal' not in repeated['answer']
    with client.app.state.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.actions)) == 1
        assert c.scalar(select(func.count()).select_from(db.outbox)) <= 1
