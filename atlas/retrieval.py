"""Versioned Chroma RAG, with offline lexical embeddings or opt-in semantic embeddings."""
import hashlib
import math
import re
import json
import threading
import time
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings

SYNONYMS = {'remboursement':'refund', 'retour':'return', 'retours':'return', 'livraison':'shipping',
            'commande':'order', 'tenue':'outfit', 'chemise':'shirt', 'pantalon':'trousers'}

# Factual catalog taxonomy enriches otherwise repetitive synthetic descriptions.
# This describes garment construction/use, without inventing materials, fit or stock.
CATEGORY_CONTEXT = {
    'shirt':'An upper-body garment with a collar, worn with separate bottoms.',
    'top':'An upper-body garment worn with separate bottoms.',
    'knitwear':'An upper-body knitted garment worn with separate bottoms.',
    'trousers':'Pants: separate lower-body clothing with two legs.',
    'skirt':'Separate lower-body clothing worn with a top.',
    'dress':'A single garment combining upper and lower body clothing in one piece.',
    'shoes':'Footwear worn on the feet.',
    'jacket':'An outer layer worn over other garments.',
}


def embed(text, dimensions=512):
    # Stable positive hashing (no Python hash randomization), normalized for cosine distance.
    v = [0.0] * dimensions
    for token in re.findall(r'\w+', text.lower()):
        token = SYNONYMS.get(token, token)
        if token.endswith('s') and len(token) > 4:
            token = token[:-1]
        index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], 'big') % dimensions
        v[index] += 1
    norm = math.sqrt(sum(x*x for x in v)) or 1
    return [x / norm for x in v]


class Knowledge:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.events = []
        self.client = chromadb.PersistentClient(path=config.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False))
        model_id = (config.openai_base_url+':'+config.embedding_model
                    if config.embedding_model else 'lexical-hash-512-v1')
        suffix = hashlib.sha256(model_id.encode()).hexdigest()[:12]
        self.collection = self.client.get_or_create_collection(f'atlas-policies-{suffix}',
            metadata={'hnsw:space':'cosine'}, embedding_function=None)
        self.product_collection = self.client.get_or_create_collection(f'atlas-products-{suffix}',
            metadata={'hnsw:space':'cosine'}, embedding_function=None)
        self.ingest()
        self.ingest_products()

    def embeddings(self, texts):
        if not self.config.embedding_model:
            return [embed(t) for t in texts]
        from openai import OpenAI
        client = OpenAI(api_key=self.config.openai_api_key, base_url=self.config.openai_base_url,
                        timeout=20, max_retries=1)
        from atlas.model import RUN_ID
        start = time.perf_counter()
        event = {'run_id':RUN_ID.get(), 'ok':False, 'texts':len(texts), 'tokens':None}
        try:
            response = client.embeddings.create(model=self.config.embedding_model, input=texts)
            event.update(ok=True, tokens=response.usage.total_tokens if response.usage else None)
            return [r.embedding for r in sorted(response.data, key=lambda r:r.index)]
        finally:
            event['duration_ms'] = round((time.perf_counter()-start)*1000)
            with self.lock:
                # Indexing usage is excluded from per-contact inference usage.
                if event['run_id']:
                    self.events.append(event)

    def usage(self, run_id):
        with self.lock:
            events = [e for e in self.events if e['run_id'] == run_id]
            self.events = [e for e in self.events if e['run_id'] != run_id]
        return {'model':self.config.embedding_model or 'lexical-hash-512-v1',
                'calls':len(events), 'failed_calls':sum(not e['ok'] for e in events),
                'reported_tokens':sum(e['tokens'] or 0 for e in events), 'events':events}

    def ingest_products(self):
        rows = json.loads((Path(self.config.data_dir)/'generated/products.json').read_text())
        docs = [(p['id'], p['name']+'. '+p['description']+' '+CATEGORY_CONTEXT.get(p['category'],'')+
                 ' Style: '+p['style']+
                 '. Color: '+p['color']+'. Category: '+p['category']) for p in rows]
        existing = self.product_collection.get(include=['metadatas'])
        digests = dict(zip(existing['ids'], [m['sha256'] for m in existing['metadatas']]))
        fresh = [(pid, text, hashlib.sha256(text.encode()).hexdigest()) for pid, text in docs
                 if digests.get(pid) != hashlib.sha256(text.encode()).hexdigest()]
        if fresh:
            self.product_collection.upsert(ids=[x[0] for x in fresh],
                documents=[x[1] for x in fresh], embeddings=self.embeddings([x[1] for x in fresh]),
                metadatas=[{'product_id':pid, 'sha256':digest} for pid, _, digest in fresh])
        stale = set(existing['ids']) - {p['id'] for p in rows}
        if stale:
            self.product_collection.delete(ids=list(stale))

    def products(self, query, candidates, k=24):
        """Semantic ranking on SQL-eligible IDs; SQL remains authoritative for commerce facts."""
        if not candidates:
            return []
        by_id = {p['id']:p for p in candidates}
        result = self.product_collection.query(query_embeddings=self.embeddings([query]),
            where={'product_id':{'$in':list(by_id)}}, n_results=len(by_id),
            include=['metadatas','distances'])
        ranked = [{**by_id[m['product_id']], 'retrieval_distance':round(d,4)}
                  for m,d in zip(result['metadatas'][0], result['distances'][0])]
        # Retain category diversity so the stylist can actually construct complete outfits.
        selected = ranked[:min(8,k)]
        for category in sorted({p['category'] for p in ranked}):
            for p in [p for p in ranked if p['category'] == category][:2]:
                if p not in selected and len(selected) < k:
                    selected.append(p)
        selected.extend(p for p in ranked if p not in selected)
        return selected[:k]

    def ingest(self):
        docs = []
        for path in sorted((Path(self.config.data_dir)/'policies').glob('*.md')):
            for index, chunk in enumerate(path.read_text().split('\n\n')):
                if chunk.strip():
                    source = f'{path.name}#{index}'
                    docs.append((source, chunk, hashlib.sha256(chunk.encode()).hexdigest()))
        if not docs:
            raise ValueError('Policy corpus is empty')
        # Include content digests in IDs; remove outdated chunks on version changes.
        ids = [f'{s}:{digest[:12]}' for s, _, digest in docs]
        existing = set(self.collection.get()['ids'])
        fresh = [(i, doc) for i, doc in zip(ids, docs) if i not in existing]
        if fresh:
            self.collection.upsert(ids=[i for i, _ in fresh],
                embeddings=self.embeddings([d[1] for _, d in fresh]),
                documents=[d[1] for _, d in fresh],
                metadatas=[{'source':d[0], 'sha256':d[2]} for _, d in fresh])
        stale = existing - set(ids)
        if stale:
            self.collection.delete(ids=list(stale))

    def search(self, query, k=3):
        result = self.collection.query(query_embeddings=self.embeddings([query]),
            n_results=min(k, self.collection.count()), include=['documents', 'metadatas', 'distances'])
        return [dict(source=m['source'], text=t, distance=round(d, 4), sha256=m['sha256'])
            for t, m, d in zip(result['documents'][0], result['metadatas'][0], result['distances'][0])]
