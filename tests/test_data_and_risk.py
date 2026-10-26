import json
from datetime import timedelta
from pathlib import Path
from sqlalchemy import update
from fastapi.testclient import TestClient
from atlas.dataset import generate
from atlas.config import Settings
from atlas.api import create_app
from atlas import db
from conftest import login
from test_pipeline import chat, ADMIN


def test_data_generation_is_reproducible(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    assert generate(a) == generate(b)
    assert json.loads((a/'generated/manifest.json').read_text())['files']['orders.json']['rows'] == 600


def test_eligibility_boundaries(client):
    tools = client.app.state.pipeline.tools
    today = tools.config.as_of_date
    for age, eligible in [(30,True),(31,False),(-1,False)]:
        with tools.engine.begin() as c:
            c.execute(update(db.orders).where(db.orders.c.id == 'O1001').values(
                delivered_at=(today-timedelta(days=age)).isoformat()))
        assert tools.investigate('C0001','O1001')['eligible'] == eligible


def test_confirmation_revalidates_changed_condition(client):
    h = login(client)
    r = chat(client,h,'Return O1001')
    with client.app.state.engine.begin() as c:
        c.execute(update(db.orders).where(db.orders.c.id == 'O1001').values(condition='worn'))
    response = client.post('/api/actions/'+r['action']['id']+'/confirm',headers=h)
    assert response.json()['status'] == 'pending_review'
    assert client.post('/admin/outbox/drain',headers=ADMIN).json()['processed'] == 0


def test_carrier_timeout_falls_back(client, monkeypatch):
    import httpx
    tools = client.app.state.pipeline.tools
    tools.config.carrier_base_url = 'https://carrier.invalid'
    def fail(*args,**kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr(httpx,'get',fail)
    response = tools.shipment('C0002','O1004')
    assert response['status'] == 'delayed'
    assert 'unavailable' in response['warning']


def test_judge_failure_blocks_action(client):
    from atlas.schemas import Plan, AgentPlan, JudgeVerdict
    model = client.app.state.pipeline.model
    model.client = object()
    def structured(schema,system,payload):
        if schema is Plan:
            return Plan(intents=['returns_investigation'],order_id='O1002')
        if schema is AgentPlan:
            return AgentPlan(steps=['Verify evidence'])
        if schema is JudgeVerdict:
            raise TimeoutError()
    model.structured = structured
    model.compose = lambda *args:'Refund proposal, pending review.'
    r = chat(client,login(client),'Refund O1002')
    assert r['judged']
    assert not r['quality']['passed']
    assert r['action'] is None


def test_protected_customer_session_bootstrap(tmp_path):
    config = Settings(database_url='sqlite:///'+str(tmp_path/'secure.db'),
        chroma_path=str(tmp_path/'chroma'),data_dir=str(Path('data').resolve()),
        demo_access=False,customer_tokens={'customer-secret':'C0001'})
    with TestClient(create_app(config)) as c:
        assert c.post('/api/sessions',json={'customer_id':'C0001'}).status_code == 401
        assert c.post('/api/sessions',headers={'Authorization':'Bearer customer-secret'},
                      json={'customer_id':'C0002'}).status_code == 401
        assert c.post('/api/sessions',headers={'Authorization':'Bearer customer-secret'},
                      json={'customer_id':'C0001'}).status_code == 200
