"""Failure contracts and model-driven choices, tested without provider credentials."""
import json
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import httpx
import pytest
from openai import OpenAI
from openai.types.chat import ChatCompletion
from sqlalchemy import update
from atlas import db
from atlas.config import Settings
from atlas.model import Model, RUN_ID
from atlas.schemas import ResolutionDecision, OutfitDecision, Plan
from atlas.specialists import NoArguments, SearchArguments, baseline_outfit, registry, valid_outfit
from conftest import login
from test_pipeline import chat


def completion(calls):
    return ChatCompletion.model_validate({'id':'test','model':'test','object':'chat.completion','created':0,
        'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
        'tool_calls':[{'id':str(i),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}
                      for i,(name,args) in enumerate(calls)]}}]})


def test_native_tool_feedback_repairs_arguments():
    model = Model(Settings(_env_file=None))
    replies = iter([completion([('investigate',{'customer_id':'C0002'})]),
                    completion([('investigate',{}),('policy_search',{'query':'return policy'})])])
    messages = []
    def request(history, *args, **kwargs):
        messages.append(list(history))
        return next(replies)
    model.request = request
    observations, calls = model.tool_loop('returns_investigation',{}, {
        'investigate':{'schema':NoArguments,'description':'Owned order','call':lambda:{'owned':True}},
        'policy_search':{'schema':SearchArguments,'description':'Policy','call':lambda query:[]}},
        {'investigate','policy_search'})
    assert observations['investigate']['owned']
    assert calls[0]['status']=='invalid_arguments'
    assert any(m['role']=='tool' and 'error' in m['content'] for m in messages[1])


def test_native_tool_registry_rejects_cross_role_execution():
    model = Model(Settings(_env_file=None))
    model.request = lambda *a,**kw:completion([('refund_payment',{})])
    with pytest.raises(ValueError,match='not allowed'):
        model.tool_loop('order_tracking',{}, {}, {'shipment'})


def test_specialist_cannot_end_without_evidence():
    model = Model(Settings(_env_file=None))
    model.request = lambda *a,**kw:SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(tool_calls=[]))])
    with pytest.raises(ValueError,match='without required evidence'):
        model.tool_loop('order_tracking',{}, {}, {'shipment'})


def test_provider_usage_is_attributed_to_concurrent_runs():
    model = Model(Settings(_env_file=None,atlas_mode='llm',openai_api_key='test',openai_model='test',
                           input_cost_per_million=1,output_cost_per_million=2))
    def respond(request):
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':'test',
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{}'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
    model.client = OpenAI(api_key='test',http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    def run(run_id):
        token=RUN_ID.set(run_id)
        try:
            model.request([{'role':'user','content':'test'}],'probe')
        finally:
            RUN_ID.reset(token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,['one','two']))
    for run_id in ['one','two']:
        usage=model.usage(run_id)
        assert usage['calls']==1 and usage['prompt_tokens']==10 and usage['completion_tokens']==5
        assert usage['estimated_cost_usd']==.00002
        assert usage['events'][0]['run_id']==run_id
    assert model.tokens==30
    assert not model.events


def test_failed_provider_call_is_counted_with_unknown_cost():
    model = Model(Settings(_env_file=None,atlas_mode='llm',openai_api_key='test',openai_model='test'))
    def fail(request):
        raise httpx.ReadTimeout('test timeout')
    model.client = OpenAI(api_key='test',max_retries=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(fail)))
    token=RUN_ID.set('failure')
    try:
        with pytest.raises(Exception):
            model.request([{'role':'user','content':'test'}],'probe')
    finally:
        RUN_ID.reset(token)
    usage=model.usage('failure')
    assert usage['failed_calls']==1 and usage['estimated_cost_usd'] is None
    assert not usage['usage_complete']


def test_schema_does_not_allow_silent_empty_route():
    model=Model(Settings(_env_file=None))
    seen={}
    def request(messages,stage,**options):
        seen.update(options)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"intents":[]}'))])
    model.request=request
    model.structured(Plan,'Route request',{})
    schema=seen['response_format']['json_schema']['schema']
    assert 'intents' in schema['required']


def test_semantic_candidates_revalidated_against_live_sql(client):
    pipeline=client.app.state.pipeline
    state={'plan':{'size':'M','intents':['product_discovery'],'category':'shirt','budget_cents':6000},
           'customer_id':'C0001'}
    allowed,_=registry(pipeline,state,'product_discovery')
    with pipeline.tools.engine.begin() as c:
        c.execute(update(db.variants).where(db.variants.c.product_id=='P0009').values(stock=0))
    result=allowed['product_search']['call'](query='elegant clothes for office')
    assert result['products']
    assert all(p['stock']>0 and p['size']=='M' and p['price_cents']<=6000 and
               p['category']=='shirt' and p['id']!='P0009' for p in result['products'])


def test_complete_outfit_search_avoids_greedy_dead_end():
    def garment(vid,category,price):
        return {'variant_id':vid,'category':category,'price_cents':price,'stock':2,'size':'M'}
    evidence={'size':'M','products':[garment('expensive','shirt',9000),garment('cheap','shirt',2000),
                garment('bottom','trousers',4000),garment('shoe','shoes',3000)]}
    outfit=baseline_outfit(evidence,10000)
    assert {p['variant_id'] for p in outfit}=={'cheap','bottom','shoe'}
    assert valid_outfit(outfit,evidence,10000)
    assert not valid_outfit(outfit+[outfit[0]],evidence,10000)
    assert not baseline_outfit(evidence,100)


def test_stylist_uses_valid_model_selection_and_rejects_unknown_variants(client):
    p=client.app.state.pipeline
    result=chat(client,login(client),'Build an outfit under EUR 150 size M')
    state={**result,'message':'Build an outfit under EUR 150 size M',
           'session_id':client.post('/api/sessions',json={'customer_id':'C0001'}).json()['session_id']}
    evidence=p.finding(state,'product_discovery')
    # Select a valid alternative by searching within a reversed discovery ranking.
    alternate=baseline_outfit({**evidence,'products':list(reversed(evidence['products']))},15000)
    p.model.client=object()
    p.model.structured=lambda *a:OutfitDecision(variant_ids=[x['variant_id'] for x in alternate],reason='Compatible colors')
    chosen=p.style(state)
    assert chosen['outfit']==alternate and chosen['trace'][0]['execution']=='llm_decision'
    p.model.structured=lambda *a:OutfitDecision(variant_ids=['invented'],reason='Test')
    blocked=p.style(state)
    assert blocked['trace'][0]['execution']=='fallback' and blocked['warnings']
    assert all(x['variant_id']!='invented' for x in blocked['outfit'])


def test_resolution_cannot_bypass_mandatory_review(client):
    p=client.app.state.pipeline
    r=chat(client,login(client),'Return O1002')
    state={**r,'customer_id':'C0001','message':'Return O1002',
           'session_id':client.post('/api/sessions',json={'customer_id':'C0001'}).json()['session_id']}
    p.model.client=object()
    p.model.structured=lambda *a:ResolutionDecision(recommendation='standard_refund',reason='Bypass',next_steps=['Pay'])
    result=p.resolve(state)
    assert result['resolution']['requires_human']
    assert result['resolution']['recommendation']=='review_exception'
    assert result['trace'][0]['execution']=='fallback'


def test_parallel_workers_really_overlap(client,monkeypatch):
    p=client.app.state.pipeline
    barrier=threading.Barrier(2)
    original_shipment=p.tools.shipment
    original_catalog=p.tools.catalog
    def shipment(*a,**kw):
        barrier.wait(timeout=5)
        time.sleep(.025)
        return original_shipment(*a,**kw)
    def catalog(*a,**kw):
        barrier.wait(timeout=5)
        return original_catalog(*a,**kw)
    monkeypatch.setattr(p.tools,'shipment',shipment)
    monkeypatch.setattr(p.tools,'catalog',catalog)
    result=chat(client,login(client),'Track O1001 and build an outfit under EUR 150 size M')
    from scripts.evaluate import overlap
    assert overlap(result['trace'])
    assert result['quality']['passed'] and result['outfit']


def test_tool_outage_blocks_action_and_records_fallback(client,monkeypatch):
    p=client.app.state.pipeline
    def fail(*a,**kw):
        raise RuntimeError('SQL unavailable')
    monkeypatch.setattr(p.tools,'investigate',fail)
    result=chat(client,login(client),'Return O1001')
    assert not result['quality']['passed'] and result['action'] is None
    assert result['degraded'] and result['trace'][1]['execution']=='failed'


def test_unrelated_greeting_does_not_reuse_previous_order(client):
    headers=login(client)
    chat(client,headers,'Track O1001')
    r=chat(client,headers,'Hello')
    assert not r['plan']['intents'] and r['plan']['order_id'] is None


def test_agent_memory_survives_application_restart(client):
    from fastapi.testclient import TestClient
    from atlas.api import create_app
    headers=login(client)
    chat(client,headers,'Track O1001')
    config=client.app.state.pipeline.tools.config
    with TestClient(create_app(config)) as restarted:
        result=chat(restarted,headers,'Can I return it?')
        assert result['plan']['order_id']=='O1001'
        assert result['resolution']['eligible']


def test_stylist_can_repair_invalid_choice_without_fallback(client):
    p=client.app.state.pipeline
    result=chat(client,login(client),'Build an outfit under EUR 150 size M')
    state={**result,'message':'Build an outfit under EUR 150 size M',
           'session_id':client.post('/api/sessions',json={'customer_id':'C0001'}).json()['session_id']}
    chosen=baseline_outfit(p.finding(state,'product_discovery'),15000)
    decisions=iter([OutfitDecision(variant_ids=['invented'],reason='Invalid first attempt'),
                    OutfitDecision(variant_ids=[x['variant_id'] for x in chosen],reason='Corrected compatible outfit')])
    payloads=[]
    def structured(schema,system,payload):
        payloads.append(dict(payload))
        return next(decisions)
    p.model.client=object()
    p.model.structured=structured
    result=p.style(state)
    assert result['trace'][0]['execution']=='llm_decision' and not result['warnings']
    assert len(result['trace'][0]['model_choices'])==2
    assert 'validation_error' in payloads[1]


def test_carrier_without_key_does_not_send_empty_bearer(client,monkeypatch):
    tools=client.app.state.pipeline.tools
    tools.config.carrier_base_url='http://carrier.test'
    def get(url,headers,timeout):
        assert headers=={} and timeout==5
        return httpx.Response(200,request=httpx.Request('GET',url),
                              json={'status':'delivered','provider':'simulation'})
    monkeypatch.setattr(httpx,'get',get)
    result=tools.shipment('C0001','O1001')
    assert result['source']=='live mock carrier API'


def test_explicit_budget_size_and_order_are_bound_independently_of_model(client):
    p=client.app.state.pipeline
    sid=client.post('/api/sessions',json={'customer_id':'C0001'}).json()['session_id']
    p.model.client=object()
    p.model.structured=lambda *a:Plan(intents=['order_tracking','product_discovery','personal_stylist'],
                                    order_id='O1002',budget_cents=15000,size='L')
    result=p.route({'message':'Track O1001 and build an outfit under EUR 1 size M',
                    'session_id':sid,'customer_id':'C0001'})
    assert result['plan']['order_id']=='O1001'
    assert result['plan']['budget_cents']==100 and result['plan']['size']=='M'
    assert {c['field'] for c in result['trace'][0]['constraint_corrections']}=={'order_id','budget_cents','size'}


def test_single_product_literal_category_is_not_changed_by_model(client):
    p=client.app.state.pipeline
    sid=client.post('/api/sessions',json={'customer_id':'C0001'}).json()['session_id']
    p.model.client=object()
    p.model.structured=lambda *a:Plan(intents=['product_discovery'],category='dress',budget_cents=60,size='L')
    result=p.route({'message':'Find a shirt under EUR 60 size L','session_id':sid,'customer_id':'C0001'})
    assert result['plan']['category']=='shirt' and result['plan']['budget_cents']==6000


def test_specialist_is_prompted_for_missing_evidence_before_fallback():
    model=Model(Settings(_env_file=None))
    responses=iter([completion([('policy_search',{'query':'shipping'})]),completion([]),
                    completion([('shipment',{})])])
    prompts=[]
    def request(messages,*a,**kw):
        prompts.append(list(messages))
        return next(responses)
    model.request=request
    observations,calls=model.tool_loop('order_tracking',{}, {
        'policy_search':{'schema':SearchArguments,'description':'Policy','call':lambda query:[]},
        'shipment':{'schema':NoArguments,'description':'Owned shipment','call':lambda:{'status':'delayed'}}},
        {'policy_search','shipment'})
    assert observations['shipment']['status']=='delayed' and len(calls)==2
    assert 'shipment' in prompts[-1][-1]['content']
