"""Source-exact passages with local embeddings and permission-scoped hybrid retrieval."""

import logging
import math
import re

from ..errors import APIError

logger = logging.getLogger(__name__)
CHUNK_SIZE = 1600
CHUNK_OVERLAP = 240
INDEX_VERSION = 2


def chunk_text(text):
    # Offsets are zero-based internally; stored citations are one-based inclusive.
    text = text or ""
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            boundaries = [m.end() for m in re.finditer(r"(?:[.!?।]\s+|\n\s*\n)", text[start:end])]
            useful = [boundary for boundary in boundaries if boundary >= CHUNK_SIZE // 2]
            if useful:
                end = start + useful[-1]
        left, right = start, end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if right > left:
            chunks.append((left, text[left:right]))
        if end == len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


async def embed_texts(client, settings, texts):
    if not texts:
        return []
    try:
        response = await client.post(
            settings.ollama_base_url.rstrip('/') + '/api/embed',
            json={'model': settings.rag_embedding_model, 'input': texts, 'truncate': False, 'keep_alive': '5m'},
            timeout=60,
        )
        if not response.is_success:
            raise ValueError
        vectors = response.json()['embeddings']
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError
        normalized = []
        dimensions = None
        for vector in vectors:
            if not isinstance(vector, list) or not vector:
                raise ValueError
            if any(type(v) not in (float, int) or not math.isfinite(v) for v in vector):
                raise ValueError
            dimensions = dimensions or len(vector)
            norm = math.sqrt(sum(v * v for v in vector))
            if dimensions != len(vector) or not norm:
                raise ValueError
            normalized.append([v / norm for v in vector])
        return normalized
    except Exception:
        raise APIError('Document embeddings are unavailable. Check Ollama and the RAG_EMBEDDING_MODEL setting.', 503) from None


async def index_document(db, document_id, text, *, settings=None, client=None):
    chunks = chunk_text(text)
    vectors = []
    if settings and client and settings.rag_embedding_model:
        try:
            for offset in range(0, len(chunks), 16):
                vectors.extend(await embed_texts(client, settings, [value for _, value in chunks[offset:offset + 16]]))
        except APIError:
            vectors = []
            logger.warning('Document %s indexed for keyword search; embeddings need a retry', document_id)
    # Replace the complete index atomically. A cancelled reindex preserves its predecessor.
    async with db.transaction() as tx:
        await tx.query('SELECT document_id FROM officer_documents WHERE document_id=%s FOR UPDATE', (document_id,))
        await tx.query('DELETE FROM document_chunks WHERE document_id=%s', (document_id,))
        for index, (offset, chunk) in enumerate(chunks):
            await tx.query(
                """INSERT INTO document_chunks
                   (document_id,chunk_text,source_start,source_end,search_vector,embedding,embedding_model,index_version)
                   VALUES (%s,%s,%s,%s,to_tsvector('simple',%s),%s,%s,%s)""",
                (document_id, chunk, offset + 1, offset + len(chunk), chunk,
                 vectors[index] if vectors else None, settings.rag_embedding_model if vectors else None, INDEX_VERSION),
            )
    return {'chunks': len(chunks), 'embedded': len(vectors), 'mode': 'hybrid' if vectors else 'keyword'}


async def retrieve_context(db, officer_id, question, limit=5, *, person_id=None, case_id=None,
                           settings=None, client=None):
    if not question or not question.strip():
        return []
    limit = min(max(limit, 1), 30)
    # One scope clause serves every root record; the kind decides which entity links a document in.
    kind, canonical_id = ('Case', case_id) if case_id is not None else ('Person', person_id)
    scope = f"""d.officer_id=%s AND d.confirmed_at IS NOT NULL
        AND (%s::text IS NULL OR EXISTS (
          SELECT 1 FROM extracted_entities e WHERE e.document_id=d.document_id
            AND e.kind='{kind}' AND e.canonical_id=%s))"""
    # OR terms avoids requiring every word in a natural-language question to occur.
    terms = ' | '.join(dict.fromkeys(re.findall(r'[^\W_]+', question, re.UNICODE)))
    if not terms:
        return []
    lexical = await db.query(
        f"""SELECT c.chunk_id,c.document_id,d.original_name,c.chunk_text,c.source_start,c.source_end,
             ts_rank(c.search_vector,to_tsquery('simple',%s)) AS score
           FROM document_chunks c JOIN officer_documents d ON d.document_id=c.document_id
           WHERE {scope} AND c.search_vector @@ to_tsquery('simple',%s)
           ORDER BY score DESC,c.chunk_id LIMIT %s""",
        (terms, officer_id, canonical_id, canonical_id, terms, max(30, limit * 3)),
    )
    semantic = []
    if settings and client and settings.rag_embedding_model:
        try:
            vector = (await embed_texts(client, settings, [question]))[0]
            semantic = await db.query(
                f"""SELECT c.chunk_id,c.document_id,d.original_name,c.chunk_text,c.source_start,c.source_end,
                     (SELECT sum(v*q) FROM unnest(c.embedding,%s::double precision[]) pair(v,q)) AS score
                   FROM document_chunks c JOIN officer_documents d ON d.document_id=c.document_id
                   WHERE {scope} AND c.embedding_model=%s AND cardinality(c.embedding)=%s
                   ORDER BY score DESC NULLS LAST,c.chunk_id LIMIT %s""",
                (vector, officer_id, canonical_id, canonical_id, settings.rag_embedding_model, len(vector), max(30, limit * 3)),
            )
        except APIError:
            logger.warning('Semantic retrieval unavailable; using source-scoped keyword search')
    ranked, rows = {}, {}
    for results in (lexical, semantic):
        for rank, row in enumerate(results):
            key = row['chunk_id']
            rows[key] = row
            ranked[key] = ranked.get(key, 0) + 1 / (60 + rank + 1)
    selected = []
    for key in sorted(ranked, key=lambda key: (-ranked[key], key)):
        row = rows[key]
        # Suppress near-identical overlapping hits without losing other source documents.
        if any(old['document_id'] == row['document_id'] and
               max(0, min(old['source_end'], row['source_end']) - max(old['source_start'], row['source_start']) + 1)
               > .7 * min(old['source_end'] - old['source_start'] + 1, row['source_end'] - row['source_start'] + 1)
               for old in selected):
            continue
        selected.append({**row, 'retrieval_mode': 'hybrid' if semantic else 'keyword'})
        if len(selected) == limit:
            break
    return selected
