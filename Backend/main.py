from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from api_extra import router as extra_router
from rag.engine import Engine

app = FastAPI(title="Root Cause Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Loads the prebuilt index from index/full; run `python -m rag.build_index` first.
engine = Engine("full")


class Query(BaseModel):
    issue: str
    rerank: Optional[bool] = None  # None = RCA_RERANK default (off for local models)
    debug: bool = False


# Features 1-7: observability, multi-agent investigation, dependency graph,
# causal analysis, timeline, remediation and benchmarking.
app.include_router(extra_router)


@app.get("/")
def home():
    from observability import default_providers
    return {
        "message": "RCA API is running 🚀",
        "incidents_indexed": len(engine.kb.docs),
        "capabilities": {
            "analyze": "/analyze - single-shot RAG analysis (unchanged)",
            "investigate": "/investigate - multi-agent investigation",
            "causal": "/causal - causal graph and ranked hypotheses",
            "timeline": "/timeline - chronological reconstruction",
            "graph": "/graph, /graph/blast-radius, /graph/suspects",
            "remediation": "/remediation, /remediation/approve",
            "observability": "/observability/status, /observability/signals",
            "benchmark": "/benchmark",
        },
        "observability_configured": sum(
            1 for p in default_providers() if p.configured()),
    }


def add_legacy_fields(result):
    """Also fill the fields the React frontend (Frontend/src/parse.js) reads:
    analysis.{root_causes, solutions, confidence, explanation} and
    similar_issues[{content, similarity_score}]. The new fields stay alongside."""
    a = result["analysis"]
    a["root_causes"] = [h["cause"] for h in a["hypotheses"]]
    a["solutions"] = a["fix_steps"]
    a["confidence"] = a["hypotheses"][0]["likelihood"] if a["hypotheses"] else a["category_confidence"]
    a["explanation"] = " ".join(
        [a["summary"], f"Category: {a['category']}, severity: {a['severity']}."]
        + [h["reasoning"] for h in a["hypotheses"][:1]]
    )
    result["similar_issues"] = [
        {
            "content": f"Issue: {s['issue']}\nCauses: {s['root_cause']}\nSolutions: {s['solution']}",
            "similarity_score": s["scores"].get("relevance", 0) / 10 if "relevance" in s["scores"]
            else s["scores"].get("cosine", 0),
            "id": s["id"],
            "org": s["org"],
            "source_url": s["source_url"],
        }
        for s in result["similar_incidents"]
    ] if result["mode"] == "RAG" else []
    if result["mode"] == "NOVEL":
        result["mode"] = "LLM_ONLY"
    return result


@app.post("/analyze")
def analyze(query: Query):
    result = engine.run(query.issue, rerank=query.rerank)
    if not query.debug:
        result.pop("trace")
    return add_legacy_fields(result)
