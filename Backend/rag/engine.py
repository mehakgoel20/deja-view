"""Orchestrates steps 4-7 for one incident."""
import time

from .analyze import analyze
from .config import EMBED_MODEL, LLM_MODEL, RERANK
from .kb import KnowledgeBase
from .predict import DEFAULT_ALPHA, vote
from .retrieve import retrieve

# Below these, the best match is not a real precedent and the LLM is told to
# reason without context instead of being anchored on unrelated incidents.
GATE_RELEVANCE = 4   # LLM rerank score, 0-10
GATE_COSINE = 0.40   # used when rerank is off


def is_relevant(neighbours):
    if not neighbours:
        return False
    top = neighbours[0]
    if "relevance" in top:
        return top["relevance"] >= GATE_RELEVANCE
    return top.get("cosine", 0) >= GATE_COSINE


class Engine:
    def __init__(self, index_name="full", alpha=DEFAULT_ALPHA):
        self.kb = KnowledgeBase(index_name)
        self.alpha = alpha

    def run(self, text, k=5, rewrite=True, rerank=None, use_context=True, query_vector=None):
        """`rerank=None` uses the RCA_RERANK default (off for local models)."""
        rerank = RERANK if rerank is None else rerank
        t0 = time.time()
        neighbours, trace = retrieve(self.kb, text, k=k, rewrite=rewrite, rerank=rerank,
                                     query_vector=query_vector)
        t_retrieve = time.time() - t0
        baseline = vote(self.kb, neighbours, self.alpha)
        relevant = use_context and is_relevant(neighbours)
        analysis, validation = analyze(self.kb, text, neighbours if relevant else [], baseline)
        return {
            "mode": "RAG" if relevant else "NOVEL",
            "analysis": analysis,
            "baseline": baseline,
            "similar_incidents": [self._describe(c) for c in neighbours],
            "validation": validation,
            "trace": trace,
            "timing_s": {"retrieve": round(t_retrieve, 2), "total": round(time.time() - t0, 2)},
            "models": {"llm": LLM_MODEL, "embed": EMBED_MODEL, "index": self.kb.name,
                       "rerank": rerank},
        }

    def _describe(self, c):
        d = self.kb.docs[c["row"]]
        out = {k: d[k] for k in ("id", "org", "category", "severity", "issue", "root_cause",
                                 "solution", "source_url", "incident_date")}
        out["scores"] = {k: round(c[k], 4) if isinstance(c[k], float) else c[k]
                         for k in ("relevance", "cosine", "rrf", "dense_rank", "bm25_rank") if k in c}
        return out
