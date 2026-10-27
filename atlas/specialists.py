"""Role-specific, server-bound tool registries and validated styling decisions."""
from itertools import product
from pydantic import BaseModel, ConfigDict, Field


class NoArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchArguments(NoArguments):
    query: str = Field(min_length=3, max_length=300)


def registry(pipeline, state, role):
    tools, kb, plan = pipeline.tools, pipeline.knowledge, state['plan']
    customer = state['customer_id']
    policy = {'schema':SearchArguments, 'description':'Retrieve cited Atlas business policies.',
              'call':lambda query: kb.search(query,k=2)}
    if role == 'returns_investigation':
        return {'investigate':{'schema':NoArguments,
            'description':'Verify owned order, condition, return window and review signals. No arguments: use {}.',
            'call':lambda: tools.investigate(customer, plan['order_id'])}, 'policy_search':policy}, 'investigate'
    if role == 'order_tracking':
        return {'shipment':{'schema':NoArguments,
            'description':'Get owned shipment via carrier API with cached fallback. No arguments: use {}.',
            'call':lambda: tools.shipment(customer, plan['order_id'])}, 'policy_search':policy}, 'shipment'

    def search(query):
        profile = tools.profile(customer)
        size = plan['size'] or profile['size']
        candidates = tools.catalog(size,
            None if 'personal_stylist' in plan['intents'] else plan['category'],
            plan['budget_cents'], profile['style'], limit=None)
        ranked = kb.products(query, candidates, k=24)
        return {'products':ranked, 'size':size, 'style':profile['style'],
                'budget_cents':plan['budget_cents'], 'query':query,
                'retrieval_mode':'semantic' if kb.config.embedding_model else 'lexical',
                'candidate_count':len(candidates)}
    return {'product_search':{'schema':SearchArguments,
                'description':'Find products semantically, with authoritative size, stock and price filters.',
                'call':search}, 'policy_search':policy}, 'product_search'


def valid_outfit(selected, evidence, budget):
    available = {p['variant_id']:p for p in evidence.get('products', [])}
    if not selected or len({p['variant_id'] for p in selected}) != len(selected):
        return False
    if any(p['variant_id'] not in available or p != available[p['variant_id']]
           or p['stock'] <= 0 or p['size'] != evidence['size'] for p in selected):
        return False
    categories = [p['category'] for p in selected]
    upper = sum(c in {'shirt','top','knitwear'} for c in categories)
    lower = sum(c in {'trousers','skirt'} for c in categories)
    dress = categories.count('dress')
    compatible = (dress == 1 and upper == lower == 0) or (dress == 0 and upper == lower == 1)
    return (compatible and len(categories) == len(set(categories))
            and (budget is None or sum(p['price_cents'] for p in selected) <= budget))


def baseline_outfit(evidence, budget):
    """Search feasible complete combinations; never present one random garment as an outfit."""
    rows = evidence.get('products', [])
    uppers = [p for p in rows if p['category'] in {'shirt','top','knitwear'}]
    lowers = [p for p in rows if p['category'] in {'trousers','skirt'}]
    dresses = [p for p in rows if p['category'] == 'dress']
    shoes = [p for p in rows if p['category'] == 'shoes']
    options = [[a,b] for a,b in product(uppers, lowers)] + [[p] for p in dresses]
    options += [base+[shoe] for base in list(options) for shoe in shoes]
    options = [o for o in options if valid_outfit(o, evidence, budget)]
    if not options:
        return []
    ranks = {p['variant_id']:i for i,p in enumerate(rows)}
    return min(options, key=lambda o:(-len(o), sum(ranks[p['variant_id']] for p in o),
                                     sum(p['price_cents'] for p in o)))
