"""The specialist agents: logs, metrics, history, dependencies.

These are the evidence gatherers (stage 1). They run concurrently and each
returns findings in its own narrow domain. None of them decides the root
cause - that is the investigator's job in stage 2, working from what these
produce.
"""
from __future__ import annotations

import re

from observability.base import (KIND_LOG_BURST, KIND_METRIC_SPIKE,
                                KIND_SERVICE_RESTART, KIND_TRACE_ERROR)

from .base import (FINDING_GAP, FINDING_HYPOTHESIS, FINDING_OBSERVATION,
                   Agent, Context, Finding)

# ---------------------------------------------------------------- logs

_LOG_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["themes"],
    "properties": {"themes": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["theme", "meaning", "signal_ids"],
        "properties": {"theme": {"type": "string"}, "meaning": {"type": "string"},
                       "signal_ids": {"type": "array", "items": {"type": "string"}}}}}},
}
_LOG_SYSTEM = (
    "You are a log analysis specialist. You get clustered error-log templates from an "
    "incident window, already grouped and counted. For each distinct theme, say what it "
    "means operationally in one sentence - what component is failing and how. Do not "
    "speculate about the root cause of the whole incident; describe only what the logs show. "
    "Cite the signal ids you used."
)


class LogAnalysisAgent(Agent):
    name = "log_analysis"
    role = "Reads clustered error logs and says what is failing"
    stage = 1

    def run(self, ctx: Context) -> list[Finding]:
        bursts = ctx.signals_of_kind(KIND_LOG_BURST)
        if not bursts:
            return [self.finding(FINDING_GAP,
                                 "No error logs available for this window "
                                 "(Loki not configured or nothing matched).", 0.9)]
        out: list[Finding] = []
        total = sum(s.detail.get("count", 1) for s in bursts)
        dominant = max(bursts, key=lambda s: s.detail.get("count", 0))
        share = dominant.detail.get("count", 0) / total if total else 0
        out.append(self.finding(
            FINDING_OBSERVATION,
            f"{total} error log lines in {len(bursts)} distinct template(s); "
            f"the dominant one is {share:.0%} of them: "
            f"{dominant.detail.get('template', dominant.summary)[:140]}",
            0.8 if share > 0.5 else 0.6,
            [s.id for s in bursts],
            templates=len(bursts), lines=total, dominant_share=round(share, 3)))
        # A single template dominating usually means one failure, not many.
        if share > 0.7:
            out.append(self.finding(
                FINDING_HYPOTHESIS,
                "One log template dominates, so this is likely a single failure mode "
                "repeating rather than several unrelated problems.",
                0.6, [dominant.id]))
        if ctx.use_llm:
            lines = "\n".join(
                f"[{s.id}] {s.detail.get('count', '?')}x on {s.service or 'unknown'}: "
                f"{s.detail.get('template', s.summary)[:200]}" for s in bursts[:10])
            got = self.ask_llm(_LOG_SYSTEM, f"LOG CLUSTERS:\n{lines}",
                               _LOG_SCHEMA, "log_analysis")
            for t in (got or {}).get("themes", [])[:5]:
                out.append(self.finding(FINDING_OBSERVATION,
                                        f"{t['theme']}: {t['meaning']}", 0.65,
                                        t.get("signal_ids", [])))
        return out


# ------------------------------------------------------------- metrics

class MetricsAnalysisAgent(Agent):
    name = "metrics_analysis"
    role = "Reads metric spikes and restarts, and orders them in time"
    stage = 1

    def run(self, ctx: Context) -> list[Finding]:
        spikes = ctx.signals_of_kind(KIND_METRIC_SPIKE)
        restarts = ctx.signals_of_kind(KIND_SERVICE_RESTART)
        traces = ctx.signals_of_kind(KIND_TRACE_ERROR)
        if not (spikes or restarts or traces):
            return [self.finding(FINDING_GAP,
                                 "No metrics available for this window "
                                 "(Prometheus not configured or nothing spiked).", 0.9)]
        out: list[Finding] = []
        for s in sorted(spikes, key=lambda s: s.at)[:6]:
            d = s.detail or {}
            mult = d.get("multiple")
            out.append(self.finding(
                FINDING_OBSERVATION,
                f"{d.get('metric', 'metric')} on {s.service or 'unknown'} reached "
                f"{d.get('peak', '?'):.4g} "
                f"({f'{mult}x' if mult else 'far above'} its median)",
                0.85 if s.severity == "critical" else 0.65, [s.id],
                metric=d.get("metric"), service=s.service))
        if restarts:
            svcs = sorted({s.service for s in restarts if s.service})
            out.append(self.finding(
                FINDING_HYPOTHESIS,
                f"Restarts observed on {', '.join(svcs) or 'unknown service(s)'}; "
                "a crash loop points at resource exhaustion or a failing dependency "
                "rather than a slow query.",
                0.6, [s.id for s in restarts]))
        if traces:
            top = max(traces, key=lambda s: s.detail.get("count", 0))
            out.append(self.finding(
                FINDING_OBSERVATION,
                f"Failing traces concentrate on {top.service or 'unknown'}"
                f"{' (' + str(top.detail.get('operation')) + ')' if top.detail.get('operation') else ''}, "
                f"{top.detail.get('count', '?')} traces",
                0.75, [top.id]))
        # Ordering is the most useful thing metrics give us.
        ordered = sorted(spikes + restarts + traces, key=lambda s: s.at)
        if len(ordered) >= 2:
            first, last = ordered[0], ordered[-1]
            span = (last.at - first.at).total_seconds() / 60
            out.append(self.finding(
                FINDING_OBSERVATION,
                f"First anomaly was on {first.service or 'unknown'} "
                f"({first.detail.get('metric', first.kind)}); the sequence spans "
                f"{span:.0f} min, so {first.service or 'that service'} is upstream "
                "of the rest in time.",
                0.7, [first.id, last.id], span_minutes=round(span, 1)))
        return out


# ------------------------------------------------------------- history

class HistoricalIncidentAgent(Agent):
    name = "historical_incident"
    role = "Finds precedent in the curated incident set"
    stage = 1

    def run(self, ctx: Context) -> list[Finding]:
        if not ctx.neighbours:
            return [self.finding(FINDING_GAP,
                                 "No comparable past incident was retrieved.", 0.8)]
        out: list[Finding] = []
        top = ctx.neighbours[0]
        score = top.get("scores", {})
        strength = score.get("relevance", score.get("cosine", 0))
        out.append(self.finding(
            FINDING_OBSERVATION,
            f"Closest precedent is {top['id']} ({top['org']}, {top['category']}): "
            f"{top['root_cause'][:180]}",
            min(0.9, 0.4 + 0.05 * strength if "relevance" in score else strength),
            [top["id"]], category=top["category"], org=top["org"]))
        # Agreement across precedents is a stronger signal than any single one.
        cats: dict[str, int] = {}
        for n in ctx.neighbours:
            cats[n["category"]] = cats.get(n["category"], 0) + 1
        best, count = max(cats.items(), key=lambda kv: kv[1])
        if count >= 3:
            out.append(self.finding(
                FINDING_HYPOTHESIS,
                f"{count} of {len(ctx.neighbours)} precedents are {best}, so the "
                f"failure class is probably {best}.",
                min(0.85, count / len(ctx.neighbours)),
                [n["id"] for n in ctx.neighbours if n["category"] == best]))
        fixes = [n for n in ctx.neighbours if n.get("solution")]
        if fixes:
            out.append(self.finding(
                FINDING_OBSERVATION,
                f"{len(fixes)} precedent(s) record what actually fixed them, "
                "which constrains the remediation options.",
                0.6, [n["id"] for n in fixes]))
        return out


# -------------------------------------------------------- dependencies

class DependencyAgent(Agent):
    """Reads the service graph: who could be the shared cause of these failures."""

    name = "dependency_analysis"
    role = "Uses the dependency graph to find a shared cause and blast radius"
    stage = 1

    def run(self, ctx: Context) -> list[Finding]:
        if ctx.service_graph is None:
            return [self.finding(FINDING_GAP,
                                 "No service dependency graph is configured "
                                 "(set RCA_TOPOLOGY_PATH).", 0.9)]
        failing = ctx.failing_services()
        source = "telemetry"
        if not failing:
            # With no live signals, the reporter usually still names the
            # services. Match the incident text against the known topology
            # rather than giving up - this is the common case in practice.
            failing = _services_in_text(ctx.text, ctx.service_graph)
            source = "incident text"
        if not failing:
            return [self.finding(FINDING_GAP,
                                 "No service names in the evidence or the incident "
                                 "text matched the dependency graph.", 0.8)]
        out: list[Finding] = []
        if source == "incident text":
            out.append(self.finding(
                FINDING_OBSERVATION,
                f"Services named in the report and present in the topology: "
                f"{', '.join(failing)}.", 0.5, [], services=failing))
        suspects = ctx.service_graph.rank_suspects(failing)
        if suspects:
            top = suspects[0]
            if top["explains"] > 1:
                out.append(self.finding(
                    FINDING_HYPOTHESIS,
                    f"{top['service']} is a shared dependency of "
                    f"{top['explains']} of the {top['of_failing']} failing services, "
                    "so a fault there explains them all at once.",
                    min(0.85, 0.4 + 0.15 * top["explains"]), [],
                    suspect=top["service"], suspect_kind=top["kind"]))
            else:
                out.append(self.finding(
                    FINDING_OBSERVATION,
                    f"No single dependency explains more than one failing service; "
                    f"the strongest candidate is {top['service']}.",
                    0.4, [], suspect=top["service"]))
        shared = ctx.service_graph.shared_dependencies(failing)
        if len(failing) > 1 and shared:
            out.append(self.finding(
                FINDING_OBSERVATION,
                f"All failing services share: {', '.join(shared[:6])}.",
                0.7, [], shared=shared))
        for svc in failing[:3]:
            br = ctx.service_graph.blast_radius(svc)
            if br.get("known") and br.get("critical_affected"):
                out.append(self.finding(
                    FINDING_OBSERVATION,
                    f"If {svc} is the cause, critical services affected: "
                    f"{', '.join(br['critical_affected'][:5])}.",
                    0.6, [], service=svc,
                    affected=len(br.get("affected", []))))
        return out


def _services_in_text(text: str, service_graph) -> list[str]:
    """Services from the topology whose name appears in the incident text.

    Matches on word boundaries so "auth" does not match "author", and tries
    the hyphen/underscore/space variants teams actually write.
    """
    if not text or service_graph is None:
        return []
    low = text.lower()
    found = []
    for name in service_graph.g.nodes:
        variants = {name.lower(), name.lower().replace("-", " "),
                    name.lower().replace("-", "_"), name.lower().replace("_", "-")}
        if any(re.search(rf"(?<![\w-]){re.escape(v)}(?![\w-])", low) for v in variants):
            found.append(name)
    return sorted(found)
