"""Steps 4-5: query rewrite, hybrid retrieval, rerank and org diversity."""
from .llm import chat_json, embed

RRF_K = 60
CANDIDATES = 30
RERANK_POOL = 20
PER_ORG_CAP = 2

_REWRITE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["symptom", "keywords"],
    "properties": {
        "symptom": {"type": "string"},
        "keywords": {"type": "array", "items": {"type": "string"}},
    },
}
_REWRITE_SYSTEM = (
    "You normalise incident reports for search. Rewrite the report as one or two plain "
    "sentences describing the customer-visible symptom and affected component, in the style "
    "of a status-page incident title and summary. Drop greetings, timestamps, ticket numbers "
    "and company names. Then list 3-8 technical keywords (components, error codes, "
    "technologies) that appear in or are directly implied by the report. Do not guess a cause."
)

_RERANK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scores"],
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "score"],
                "properties": {"id": {"type": "string"}, "score": {"type": "integer"}},
            },
        }
    },
}
_RERANK_SYSTEM = (
    "You are an SRE ranking past incidents by how useful they are for diagnosing a new one. "
    "Score every candidate from 0 to 10: 10 = same symptom in the same kind of component, "
    "very likely the same failure mode; 5 = related component or symptom, plausibly a similar "
    "cause; 0 = unrelated. Judge by technical similarity, not by company. Return a score for "
    "every candidate id."
)


def rewrite_query(text):
    return chat_json(_REWRITE_SYSTEM, text, _REWRITE_SCHEMA, "query_rewrite")


def hybrid_candidates(kb, dense_query_vector, lexical_query, n=CANDIDATES, mode="hybrid"):
    """Merge dense and BM25 rankings with reciprocal rank fusion."""
    merged = {}
    if mode in ("hybrid", "dense"):
        for rank, (row, cosine) in enumerate(kb.dense_search(dense_query_vector, n)):
            c = merged.setdefault(row, {"row": row, "rrf": 0.0})
            c.update(dense_rank=rank + 1, cosine=cosine)
            c["rrf"] += 1 / (RRF_K + rank + 1)
    if mode in ("hybrid", "bm25"):
        for rank, (row, score) in enumerate(kb.bm25_search(lexical_query, n)):
            c = merged.setdefault(row, {"row": row, "rrf": 0.0})
            c.update(bm25_rank=rank + 1, bm25=score)
            c["rrf"] += 1 / (RRF_K + rank + 1)
    if dense_query_vector is not None and merged:
        # Candidates found only lexically still need a cosine for voting and the gate.
        vectors = kb.index.reconstruct_batch([c["row"] for c in merged.values()])
        for c, v in zip(merged.values(), vectors):
            c.setdefault("cosine", float(v @ dense_query_vector))
    return sorted(merged.values(), key=lambda c: -c["rrf"])


def llm_rerank(kb, query, candidates, pool=RERANK_POOL):
    pool_cands = candidates[:pool]
    lines = []
    for c in pool_cands:
        d = kb.docs[c["row"]]
        lines.append(f"[{d['id']}] symptom: {d['issue'][:300]}\n    cause: {d['root_cause'][:300]}")
    user = f"NEW INCIDENT:\n{query}\n\nCANDIDATES:\n" + "\n".join(lines)
    result = chat_json(_RERANK_SYSTEM, user, _RERANK_SCHEMA, "rerank")
    scores = {s["id"]: max(0, min(10, s["score"])) for s in result["scores"]}
    for c in pool_cands:
        c["relevance"] = scores.get(kb.docs[c["row"]]["id"], 0)
    return sorted(pool_cands, key=lambda c: (-c["relevance"], -c["rrf"]))


def diversify(kb, candidates, k, per_org=PER_ORG_CAP):
    """Take the top k, allowing at most `per_org` incidents from one organisation."""
    picked, per = [], {}
    for c in candidates:
        org = kb.docs[c["row"]]["org"]
        if per.get(org, 0) >= per_org:
            continue
        per[org] = per.get(org, 0) + 1
        picked.append(c)
        if len(picked) == k:
            break
    return picked


def retrieve(kb, text, k=5, mode="hybrid", rewrite=True, rerank=True, query_vector=None):
    """Return the top-k diversified neighbours plus every intermediate stage.

    `query_vector` lets evaluation pass a precomputed embedding of `text`
    (only used when rewrite is off, since rewriting changes the text).
    """
    trace = {"input": text}
    if rewrite:
        rewritten = rewrite_query(text)
        trace["rewrite"] = rewritten
        dense_text = rewritten["symptom"]
        lexical = text + " " + rewritten["symptom"] + " " + " ".join(rewritten["keywords"])
    else:
        dense_text, lexical = text, text
    if mode in ("hybrid", "dense"):
        if query_vector is None or rewrite:
            query_vector = embed([dense_text])[0]
    candidates = hybrid_candidates(kb, query_vector, lexical, mode=mode)
    trace["fused"] = [c["row"] for c in candidates]
    if rerank and candidates:
        candidates = llm_rerank(kb, dense_text, candidates)
        trace["reranked"] = [c["row"] for c in candidates]
    neighbours = diversify(kb, candidates, k)
    return neighbours, trace
