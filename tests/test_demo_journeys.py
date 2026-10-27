"""Complete business journeys, plus provider-protocol contracts (not live LLM validation)."""
import json
import subprocess
import sys
from pathlib import Path
import httpx
from openai import OpenAI
from sqlalchemy import select, update, func
from atlas import db
from atlas.schemas import Plan
from scripts.evaluate import overlap, resolution_journey
from conftest import login
from test_pipeline import chat, ADMIN


def test_installed_evaluation_import_outside_checkout(tmp_path):
    # -I removes cwd and PYTHONPATH. This fails when the wheel excludes scripts.
    result = subprocess.run([sys.executable, '-I', '-c',
        'from scripts.evaluate import overlap; from atlas.api import create_app; '
        'assert callable(overlap) and callable(create_app)'], cwd=tmp_path,
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_demo_a_complete_approval_audit_and_authorization(client):
    client.app.state.pipeline.tools.config.admin_api_key = 'evaluation-operator'
    h = login(client)
    r = chat(client, h, 'I would like a refund for order O1002.')
    assert all(resolution_journey(client, h, r).values())
    investigation = next(f for f in r['findings'] if f['agent'] == 'returns_investigation')
    assert investigation['evidence']['order']['total_cents'] == 24900
    assert any('150' in source['text'] and source['source'].startswith('returns.md')
               for source in investigation['sources'])
    with client.app.state.engine.connect() as c:
        assert c.scalar(select(func.count()).select_from(db.outbox)) == 1
        assert c.scalar(select(db.outbox.c.status)) == 'completed_simulation'


def test_rejection_never_creates_payment(client):
    h = login(client)
    r = chat(client, h, 'Refund O1002')
    aid = r['action']['id']
    client.post(f'/api/actions/{aid}/confirm', headers=h)
    response = client.post(f'/admin/actions/{aid}/decision', headers=ADMIN,
                           json={'approve':False, 'reason':'Inspection did not verify the condition'})
    assert response.json()['status'] == 'rejected'
    assert client.post('/admin/outbox/drain', headers=ADMIN).json()['processed'] == 0
    again = client.post(f'/api/actions/{aid}/confirm', headers=h).json()
    assert again['status'] == 'rejected'
    audit = client.get(f'/admin/audit/{aid}', headers=ADMIN).json()
    assert any(e['event'].startswith('rejected:') for e in audit)


def test_demo_b_exact_prompt_sql_and_dependency_evidence(client):
    r = chat(client, login(client),
             'Track my order O1001 and build a smart casual outfit under €150, size M.')
    assert r['quality']['passed'] and overlap(r['trace'])
    assert {t['agent'] for t in r['trace']} == {'orchestrator', 'order_tracking',
                                               'product_discovery', 'personal_stylist'}
    trace = {t['agent']:t for t in r['trace']}
    assert trace['personal_stylist']['started_ms'] >= trace['product_discovery']['ended_ms']
    assert 'Shipment status:' in r['answer'] and 'Suggested outfit:' in r['answer']
    assert sum(p['price_cents'] for p in r['outfit']) <= 15000
    assert not client.app.state.pipeline.tools.validate_variants(r['outfit'], 'M')
    assert r['execution_summary']['parallel_pairs']
    assert r['guardrails']['passed'] and not r['judge_evaluation']['invoked']


def test_live_stock_change_blocks_stale_recommendation(client):
    p = client.app.state.pipeline
    r = chat(client, login(client), 'Build an outfit under EUR 150 size M')
    state = {**r, 'customer_id':'C0001'}
    with p.tools.engine.begin() as c:
        c.execute(update(db.variants).where(db.variants.c.id == r['outfit'][0]['variant_id']).values(stock=0))
    result = p.validate(state)
    assert not result['guardrails']['passed']
    finalized = p.finalize({**state, **result})
    assert 'could not be verified' in finalized['answer']
    assert r['outfit'][0]['name'] not in finalized['answer']


def test_both_llm_journeys_use_native_protocol_and_judge(client):
    """Controlled model HTTP responses exercise actual agents/tools; not inference evidence."""
    p = client.app.state.pipeline
    requests = []
    def provider(request):
        payload = json.loads(request.content)
        requests.append(payload)
        data = json.loads(payload['messages'][1]['content'])
        tool_names = [x['function']['name'] for x in payload.get('tools', [])]
        message = {}
        if tool_names:
            message['tool_calls'] = [
                {'id':f'call-{i}', 'type':'function', 'function':{'name':name,
                    'arguments':json.dumps({'query':'smart casual outfit size M return shipping policy'}
                        if name in {'product_search','policy_search'} else {})}}
                for i, name in enumerate(tool_names)]
            finish = 'tool_calls'
        else:
            schema = payload['response_format']['json_schema']['name']
            if schema == 'Plan':
                is_return = 'refund' in data['message'].lower()
                content = Plan(intents=['returns_investigation'] if is_return else
                    ['order_tracking','product_discovery','personal_stylist'],
                    order_id='O1002' if is_return else 'O1001',
                    budget_cents=None if is_return else 15000, size=None if is_return else 'M',
                    rationale='Independent evidence first').model_dump()
            elif schema == 'ResolutionDecision':
                content = {'recommendation':'review_exception','reason':'High value requires review',
                           'next_steps':['Customer confirmation','Human approval','Simulated processing']}
            elif schema == 'OutfitDecision':
                content = {'variant_ids':data['feasible_baseline'],'reason':'Compatible smart casual garments'}
            elif schema == 'AnswerSchema':
                content = {'answer':data['safe_baseline']}
            else:
                assert schema == 'JudgeVerdict'
                content = {'passed':True,'issues':[]}
            message['content'] = json.dumps(content)
            finish = 'stop'
        return httpx.Response(200, json={'id':'contract-test', 'object':'chat.completion', 'created':0,
            'model':'controlled-test', 'choices':[{'index':0, 'finish_reason':finish,
                'message':{'role':'assistant', **message}}],
            'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}})
    p.model.client = OpenAI(api_key='test', max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(provider)))
    for prompt in ['Refund O1002', 'Track my order O1001 and build a smart casual outfit under €150, size M.']:
        r = chat(client, login(client), prompt)
        assert r['judged'] and r['judge_evaluation']['passed'] and r['guardrails']['passed']
        assert not r['degraded']
        assert any(t.get('execution') == 'llm_tools' for t in r['trace'])
        assert r['model_usage']['calls'] > 0
    assert any('tools' in request for request in requests)
    assert Path('models/Modelfile').is_file()


def test_provider_retry_is_bounded_and_usage_recorded():
    from atlas.config import Settings
    from atlas.model import Model, RUN_ID
    attempts = []
    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503, json={'error':{'message':'temporary outage','type':'server_error'}})
        return httpx.Response(200, json={'id':'retry-test','model':'test','object':'chat.completion','created':0,
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}],
            'usage':{'prompt_tokens':5,'completion_tokens':2,'total_tokens':7}})
    model = Model(Settings(_env_file=None))
    model.client = OpenAI(api_key='test', max_retries=1,
        http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    token = RUN_ID.set('bounded-retry')
    try:
        model.request([{'role':'user','content':'test'}], 'retry-contract')
    finally:
        RUN_ID.reset(token)
    usage = model.usage('bounded-retry')
    assert len(attempts) == 2 and usage['calls'] == 1
    assert usage['prompt_tokens'] == 5 and usage['completion_tokens'] == 2
