"""Orchestrator: runs the agents in stages and assembles one investigation.

Stage 1 (concurrent) - the evidence gatherers: logs, metrics, history,
dependencies. They are independent, so they run in parallel and a failure in
one leaves the others intact.

Stage 2 - the investigator, which judges everything stage 1 produced plus the
deterministic causal graph.

Stage 3 - remediation, which only runs once a cause has been proposed.

The context is assembled first: observability signals, timeline, dependency
graph and causal analysis are all computed before any agent runs, so every
agent sees the same evidence.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from .base import (FINDING_GAP, FINDING_HYPOTHESIS, FINDING_RECOMMENDATION,
                   Agent, Context, Finding)
from .investigator import RootCauseInvestigator
from .specialists import (DependencyAgent, HistoricalIncidentAgent,
                          LogAnalysisAgent, MetricsAnalysisAgent)


def default_agents() -> list[Agent]:
    return [LogAnalysisAgent(), MetricsAnalysisAgent(),
            HistoricalIncidentAgent(), DependencyAgent()]


def build_context(text: str, *, window=None, service_graph=None, kb=None,
                  neighbours=None, reported_at=None, use_llm=True,
                  collect_live=True, hints=None) -> Context:
    """Gather every source of evidence once, for all agents to share."""
    from observability import (TimeWindow, collect_signals, correlate,
                               utcnow)
    from causal import analyse_causally
    from timeline import reconstruct

    window = window or TimeWindow.last(minutes=90)
    signals, provider_status = ([], [])
    if collect_live:
        signals, provider_status = collect_signals(window, hints or {})

    if service_graph is None:
        try:
            from graph import load_default_graph
            service_graph = load_default_graph()
        except Exception:
            service_graph = None

    pairs = [(n["id"], n.get("root_cause", "")) for n in (neighbours or [])
             if isinstance(n, dict) and "id" in n]
    causal = analyse_causally(text=text, signals=signals,
                              service_graph=service_graph, neighbours=pairs)
    tl = reconstruct(signals, window,
                     reported_at=reported_at or (utcnow() if signals else None),
                     reported_text=text)

    ctx = Context(text=text, window=window, signals=signals,
                  correlation=correlate(signals, window),
                  service_graph=service_graph, kb=kb,
                  neighbours=list(neighbours or []), causal=causal,
                  timeline=tl, reported_at=reported_at, use_llm=use_llm)
    ctx.correlation["providers"] = provider_status
    return ctx


def investigate(text: str, *, agents: list[Agent] | None = None, ctx: Context | None = None,
                remediate: bool = True, **ctx_kwargs) -> dict:
    """Run a full multi-agent investigation and return a single report."""
    t0 = time.time()
    ctx = ctx or build_context(text, **ctx_kwargs)
    agents = agents if agents is not None else default_agents()

    # ---- stage 1: gather, concurrently ---------------------------------
    stage1 = [a for a in agents if a.stage == 1]
    findings: list[Finding] = []
    timings: dict[str, float] = {}

    def run_one(agent: Agent):
        started = time.time()
        try:
            got = agent.run(ctx)
        except Exception as e:
            got = [Finding(agent=agent.name, kind=FINDING_GAP,
                           statement=f"{agent.name} failed: {type(e).__name__}",
                           confidence=1.0)]
        return agent.name, got, round(time.time() - started, 2)

    if stage1:
        with ThreadPoolExecutor(max_workers=len(stage1)) as ex:
            for name, got, secs in ex.map(run_one, stage1):
                findings.extend(got)
                timings[name] = secs

    # ---- stage 2: investigate ------------------------------------------
    investigator = RootCauseInvestigator()
    started = time.time()
    try:
        verdict_findings = investigator.run(ctx, findings)
    except Exception as e:
        verdict_findings = [Finding(agent=investigator.name, kind=FINDING_GAP,
                                    statement=f"investigator failed: {type(e).__name__}",
                                    confidence=1.0)]
    timings[investigator.name] = round(time.time() - started, 2)
    findings.extend(verdict_findings)

    hypotheses = [f for f in verdict_findings if f.kind == FINDING_HYPOTHESIS]
    hypotheses.sort(key=lambda f: -f.confidence)

    # ---- stage 3: remediation ------------------------------------------
    remediation = None
    if remediate and hypotheses:
        started = time.time()
        try:
            from remediation import build_plan
            remediation = build_plan(
                text, cause=hypotheses[0].statement, ctx=ctx,
                neighbours=ctx.neighbours, use_llm=ctx.use_llm)
        except Exception as e:
            remediation = {"error": f"{type(e).__name__}", "actions": [],
                           "requires_human_approval": True}
        timings["remediation"] = round(time.time() - started, 2)

    gaps = [f.to_dict() for f in findings if f.kind == FINDING_GAP]
    return {
        "mode": "MULTI_AGENT",
        "incident": text,
        "agents": [{"name": a.name, "role": a.role, "stage": a.stage}
                   for a in stage1] + [{"name": investigator.name,
                                        "role": investigator.role, "stage": 2}],
        "findings": [f.to_dict() for f in findings],
        "hypotheses": [f.to_dict() for f in hypotheses],
        "top_cause": hypotheses[0].statement if hypotheses else None,
        "evidence_gaps": gaps,
        "correlation": ctx.correlation,
        "timeline": ctx.timeline,
        "causal": ctx.causal,
        "remediation": remediation,
        "dependency_graph": (ctx.service_graph.stats()
                             if ctx.service_graph is not None else None),
        "timing_s": {**timings, "total": round(time.time() - t0, 2)},
    }


def render(report: dict) -> str:
    """Readable summary of an investigation, for a terminal or a log."""
    lines = [f"INVESTIGATION: {report['incident'][:140]}",
             f"agents: {', '.join(a['name'] for a in report['agents'])}"]
    corr = report.get("correlation") or {}
    if corr.get("signal_count"):
        lines.append(f"live evidence: {corr['summary'][:200]}")
    else:
        lines.append("live evidence: none (no observability backend configured)")
    lines.append("")
    lines.append("HYPOTHESES:")
    for h in report.get("hypotheses", [])[:5]:
        tag = "" if h["detail"].get("is_root_cause", True) else "  (effect, not cause)"
        lines.append(f"  [{h['confidence']:.2f}] {h['statement'][:120]}{tag}")
        for s in h["detail"].get("contradicting", [])[:2]:
            lines.append(f"        - contradicted: {str(s)[:100]}")
    if report.get("evidence_gaps"):
        lines.append("")
        lines.append("EVIDENCE GAPS:")
        for g in report["evidence_gaps"][:5]:
            lines.append(f"  - {g['statement'][:140]}")
    rem = report.get("remediation")
    if rem and rem.get("actions"):
        lines.append("")
        lines.append(f"REMEDIATION ({len(rem['actions'])} actions, "
                     f"human approval {'required' if rem.get('requires_human_approval') else 'not required'}):")
        for a in rem["actions"][:5]:
            lines.append(f"  [{a.get('horizon', '?')}] {a.get('action', '')[:110]}")
    lines.append("")
    lines.append(f"total {report['timing_s']['total']}s")
    return "\n".join(lines)
