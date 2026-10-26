"""Versioned Chroma RAG, with offline lexical embeddings or opt-in semantic embeddings."""
import hashlib
import math
import re
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings

SYNONYMS = {'remboursement':'refund', 'retour':'return', 'retours':'return', 'livraison':'shipping',
            'commande':'order', 'tenue':'outfit', 'chemise':'shirt', 'pantalon':'trousers'}


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
        self.client = chromadb.PersistentClient(path=config.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False))
        model_id = config.embedding_model or 'lexical-hash-512-v1'
        suffix = hashlib.sha256(model_id.encode()).hexdigest()[:12]
        self.collection = self.client.get_or_create_collection(f'atlas-policies-{suffix}',
            metadata={'hnsw:space':'cosine'}, embedding_function=None)
        self.ingest()

    def embeddings(self, texts):
        if not self.config.embedding_model:
            return [embed(t) for t in texts]
        from openai import OpenAI
        client = OpenAI(api_key=self.config.openai_api_key, base_url=self.config.openai_base_url,
                        timeout=20, max_retries=1)
        return [r.embedding for r in client.embeddings.create(model=self.config.embedding_model,
                                                              input=texts).data]

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
