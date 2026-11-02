"""HTTP surface for features 1-7, as a router mounted by main.py.

Kept separate so the original `/analyze` contract - which the React frontend
depends on - is untouched. Every endpoint here degrades rather than fails:
with no observability backend and no topology file the investigation still
returns, saying what evidence it lacked.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


# ------------------------------------------------------------- models

class InvestigateRequest(BaseModel):
    issue: str = Field(..., description="The incident description")
    service: Optional[str] = Field(None, description="Narrow live queries to one service")
    window_minutes: int = Field(90, ge=5, le=1440)
    reported_at: Optional[datetime] = None
    use_llm: bool = True
    collect_live: bool = Field(True, description="Query the observability backends")
    retrieve: bool = Field(True, description="Also retrieve similar past incidents")
    remediate: bool = True


class CausalRequest(BaseModel):
    issue: str
    service: Optional[str] = None
    window_minutes: int = Field(90, ge=5, le=1440)
    collect_live: bool = True


class RemediationRequest(BaseModel):
    issue: str
    cause: str = ""
    use_llm: bool = True
    retrieve: bool = True


class ApprovalRequest(BaseModel):
    plan: dict
    index: int
    approver: str
    decision: str = "approved"
    note: str = ""


# ------------------------------------------------------------- helpers

def _window(minutes: int):
    from observability import TimeWindow
    return TimeWindow.last(minutes=minutes)


def _retrieve_neighbours(issue: str, k: int = 5):
    """Reuse the existing engine so retrieval behaviour stays identical."""
    try:
        from main import engine
        neighbours, _ = __import__("rag.retrieve", fromlist=["retrieve"]).retrieve(
            engine.kb, issue, k=k)
        return [engine._describe(c) for c in neighbours]
    except Exception:
        return []


# ------------------------------------------------------------ feature 1

@router.get("/observability/status", tags=["observability"])
def observability_status():
    """Which monitoring backends are configured and reachable."""
    from observability import default_providers
    providers = [p.status().to_dict() for p in default_providers()]
    return {"providers": providers,
            "configured": sum(1 for p in providers if p["configured"]),
            "hint": "set RCA_PROMETHEUS_URL, RCA_LOKI_URL, RCA_GRAFANA_URL "
                    "(+RCA_GRAFANA_TOKEN) or RCA_TEMPO_URL to enable"}


@router.get("/observability/signals", tags=["observability"])
def observability_signals(service: Optional[str] = None,
                          window_minutes: int = Query(90, ge=5, le=1440)):
    """Raw correlated signals for a window, without running an investigation."""
    from observability import collect_signals, correlate
    window = _window(window_minutes)
    signals, status = collect_signals(window, {"service": service} if service else {})
    return {"window": window.to_dict(),
            "signals": [s.to_dict() for s in signals],
            "correlation": correlate(signals, window),
            "providers": status}


# ------------------------------------------------------------ feature 2

@router.post("/investigate", tags=["investigation"])
def investigate_endpoint(req: InvestigateRequest):
    """Full multi-agent investigation: evidence, causality, timeline, remediation."""
    from agents import investigate
    neighbours = _retrieve_neighbours(req.issue) if req.retrieve else []
    return investigate(
        req.issue,
        window=_window(req.window_minutes),
        neighbours=neighbours,
        reported_at=req.reported_at,
        use_llm=req.use_llm,
        collect_live=req.collect_live,
        remediate=req.remediate,
        hints={"service": req.service} if req.service else None,
    )


# ------------------------------------------------------------ feature 3

@router.get("/graph", tags=["graph"])
def graph_stats():
    """The loaded service topology, or how to provide one."""
    from graph import default_topology_path, load_default_graph
    g = load_default_graph()
    if g is None:
        return {"loaded": False,
                "hint": "set RCA_TOPOLOGY_PATH or add Backend/data/topology.yaml"}
    return {"loaded": True, "source": str(default_topology_path()),
            "stats": g.stats(), "topology": g.to_dict()}


@router.get("/graph/blast-radius", tags=["graph"])
def blast_radius(service: str):
    """Which services break if `service` does."""
    from graph import load_default_graph
    g = load_default_graph()
    if g is None:
        raise HTTPException(503, "no service topology configured")
    return g.blast_radius(service)


@router.get("/graph/suspects", tags=["graph"])
def graph_suspects(services: str = Query(..., description="comma-separated failing services")):
    """Rank shared dependencies that would explain several failures at once."""
    from graph import load_default_graph
    g = load_default_graph()
    if g is None:
        raise HTTPException(503, "no service topology configured")
    failing = [s.strip() for s in services.split(",") if s.strip()]
    return {"failing": failing, "suspects": g.rank_suspects(failing),
            "shared_dependencies": g.shared_dependencies(failing)}


# ------------------------------------------------------- features 4 and 5

@router.post("/causal", tags=["causal"])
def causal_endpoint(req: CausalRequest):
    """Causal graph and ranked hypotheses, with contradictions."""
    from causal import analyse_causally, separate_symptoms
    from graph import load_default_graph
    from observability import collect_signals
    window = _window(req.window_minutes)
    signals = []
    if req.collect_live:
        signals, _ = collect_signals(window,
                                     {"service": req.service} if req.service else {})
    neighbours = _retrieve_neighbours(req.issue)
    pairs = [(n["id"], n.get("root_cause", "")) for n in neighbours]
    result = analyse_causally(text=req.issue, signals=signals,
                              service_graph=load_default_graph(), neighbours=pairs)
    result["separated"] = separate_symptoms(result)
    return result


@router.post("/timeline", tags=["timeline"])
def timeline_endpoint(req: CausalRequest):
    """Chronological reconstruction with phases and an ordering verdict."""
    from observability import collect_signals
    from timeline import reconstruct, render
    window = _window(req.window_minutes)
    signals, status = collect_signals(
        window, {"service": req.service} if req.service else {})
    tl = reconstruct(signals, window, reported_text=req.issue)
    tl["rendered"] = render(tl)
    tl["providers"] = status
    return tl


# ------------------------------------------------------------ feature 6

@router.post("/remediation", tags=["remediation"])
def remediation_endpoint(req: RemediationRequest):
    """Propose remediation. Returns a plan; executes nothing."""
    from remediation import build_plan
    neighbours = _retrieve_neighbours(req.issue) if req.retrieve else []
    return build_plan(req.issue, cause=req.cause, neighbours=neighbours,
                      use_llm=req.use_llm)


@router.post("/remediation/approve", tags=["remediation"])
def remediation_approve(req: ApprovalRequest):
    """Record a human decision on one proposed action. Runs nothing."""
    from remediation import approve
    try:
        return approve(req.plan, req.index, req.approver, req.decision, req.note)
    except (IndexError, ValueError) as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------ feature 7

@router.get("/benchmark", tags=["benchmark"])
def benchmark_results():
    """The saved pipeline comparison, if the benchmark has been run."""
    import json
    from pathlib import Path
    from rag.config import EVAL_DIR
    path = Path(EVAL_DIR) / "benchmark" / "results.json"
    if not path.exists():
        return {"available": False,
                "hint": "run: python -m benchmark.run --limit 50"}
    payload = json.loads(path.read_text())
    from benchmark.run import render
    return {"available": True, "comparison": payload.get("comparison"),
            "aggregate": payload.get("aggregate"),
            "table": render(payload.get("aggregate", {}))}
