"""AI remediation engine (feature 6).

Produces a plan in four horizons - immediate mitigation, corrective fix,
preventive work, and concrete configuration changes - plus code locations
where the evidence actually supports naming one.

**Nothing here executes anything.** Every action carries
`requires_approval: True` and a `risk` rating, and the module exposes no
apply/exec path at all. That is a deliberate boundary: an RCA tool that can
restart production on its own inference is a worse outage waiting to happen.
The output is a reviewed proposal, and `approve()` only records a human's
decision for audit.

Remediations observed in precedent are preferred over invented ones: if three
past incidents with this mechanism were fixed by reverting, that is stronger
than a model's suggestion.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

HORIZON_IMMEDIATE = "immediate"      # stop the bleeding now
HORIZON_CORRECTIVE = "corrective"    # fix the actual defect
HORIZON_PREVENTIVE = "preventive"    # stop the class of failure recurring
HORIZON_CONFIG = "configuration"     # a specific setting to change

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

# Mechanism -> playbook. Derived from what actually fixed incidents in the
# gold set, which is why these read as concrete operations.
PLAYBOOKS = [
    (r"config(uration)?|misconfigur|feature flag|wrong (value|default)", {
        HORIZON_IMMEDIATE: [
            ("Roll the configuration back to the last known-good revision", RISK_LOW),
            ("If the change was scoped to a flag, set it to its previous value", RISK_LOW)],
        HORIZON_CORRECTIVE: [
            ("Correct the value and re-apply through the normal pipeline", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Add schema validation that rejects a config the consumer cannot parse", RISK_LOW),
            ("Stage config rollouts with a health gate between stages", RISK_LOW)],
        HORIZON_CONFIG: [
            ("Require an exact environment match before a config apply", RISK_LOW)],
    }),
    (r"deploy|release|rollout|regression|new version|bad build", {
        HORIZON_IMMEDIATE: [
            ("Roll back to the previous release", RISK_LOW),
            ("Freeze further deploys to this service until the cause is confirmed", RISK_LOW)],
        HORIZON_CORRECTIVE: [
            ("Fix the defect and roll forward; do not re-deploy the same artifact", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Add the failing path to pre-production checks", RISK_LOW),
            ("Make the rollout canary-first with automatic revert on error-rate rise", RISK_MEDIUM)],
        HORIZON_CONFIG: [
            ("Set a canary percentage and an automatic rollback threshold", RISK_LOW)],
    }),
    (r"connection|pool|too many connections|max_connections", {
        HORIZON_IMMEDIATE: [
            ("Raise the pool ceiling temporarily and recycle idle connections", RISK_MEDIUM),
            ("Shed non-critical traffic to let the pool drain", RISK_MEDIUM)],
        HORIZON_CORRECTIVE: [
            ("Return connection acquisition to request scope so connections are released", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Alert on pool saturation before exhaustion, not after", RISK_LOW),
            ("Tie per-instance pool size to instance count so the fleet total stays under the server limit", RISK_LOW)],
        HORIZON_CONFIG: [
            ("Set pool_size * replicas < server max_connections", RISK_LOW)],
    }),
    (r"index|full scan|query plan|slow quer|schema (change|migration)", {
        HORIZON_IMMEDIATE: [
            ("Recreate or re-point the missing index", RISK_MEDIUM),
            ("Kill the long-running queries holding resources", RISK_MEDIUM)],
        HORIZON_CORRECTIVE: [
            ("Add the index backing the query's filter columns", RISK_MEDIUM),
            ("Refresh planner statistics on the affected relation", RISK_LOW)],
        HORIZON_PREVENTIVE: [
            ("Reject a new query path in review when no index backs its filter", RISK_LOW),
            ("Treat an index modification as one atomic operation, never drop-then-create", RISK_LOW)],
        HORIZON_CONFIG: [("Schedule regular ANALYZE / statistics refresh", RISK_LOW)],
    }),
    (r"memory|oom|heap|leak", {
        HORIZON_IMMEDIATE: [
            ("Restart the affected instances to reclaim memory", RISK_LOW),
            ("Raise the memory limit to buy time while the leak is found", RISK_MEDIUM)],
        HORIZON_CORRECTIVE: [
            ("Bound the growing structure and release it when the request completes", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Alert on memory growth over a rolling window, not only on restarts", RISK_LOW),
            ("Add an eviction policy to any in-process cache", RISK_LOW)],
        HORIZON_CONFIG: [("Set a memory limit plus a restart budget so a leak is visible", RISK_LOW)],
    }),
    (r"certificat|\btls\b|\bssl\b|expir|credential|token", {
        HORIZON_IMMEDIATE: [
            ("Issue and deploy a replacement certificate or credential", RISK_MEDIUM)],
        HORIZON_CORRECTIVE: [
            ("Repair the renewal automation and verify it end to end", RISK_LOW)],
        HORIZON_PREVENTIVE: [
            ("Alert on expiry well before the deadline instead of reporting silently", RISK_LOW),
            ("Rotate with an overlap window: publish the new credential and accept both", RISK_LOW)],
        HORIZON_CONFIG: [("Set the expiry alert threshold to at least 30 days", RISK_LOW)],
    }),
    (r"\bdns\b|resolv|service discovery|nxdomain", {
        HORIZON_IMMEDIATE: [
            ("Restore the previous records and restart the resolvers", RISK_MEDIUM)],
        HORIZON_CORRECTIVE: [
            ("Repair the record set and verify resolution from a consumer, not the resolver", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Never repair a resolution outage with tooling that itself depends on resolution", RISK_LOW),
            ("Shorten negative-response caching so a fix propagates promptly", RISK_LOW)],
        HORIZON_CONFIG: [("Block a zone change that would empty a record set in use", RISK_LOW)],
    }),
    (r"upstream|third[- ]party|vendor|provider (outage|incident)", {
        HORIZON_IMMEDIATE: [
            ("Fail over to the secondary provider or serve a degraded response", RISK_MEDIUM),
            ("Throttle retries so recovery is not amplified", RISK_LOW)],
        HORIZON_CORRECTIVE: [
            ("Add a circuit breaker and a cached fallback around the dependency", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Give every synchronous external call a timeout and a fallback", RISK_LOW),
            ("Use exponential backoff with jitter on retries", RISK_LOW)],
        HORIZON_CONFIG: [("Set a per-dependency timeout below your own request deadline", RISK_LOW)],
    }),
    (r"capacity|saturat|overload|traffic (spike|surge)|autoscal|queue", {
        HORIZON_IMMEDIATE: [
            ("Scale out the saturated tier", RISK_LOW),
            ("Shed or queue low-priority work to protect the critical path", RISK_MEDIUM)],
        HORIZON_CORRECTIVE: [
            ("Add admission control so work is rejected rather than accepted and failed", RISK_MEDIUM)],
        HORIZON_PREVENTIVE: [
            ("Key autoscaling on queue depth, not CPU, for queue-driven work", RISK_LOW),
            ("Add per-tenant concurrency limits so one caller cannot consume the pool", RISK_LOW)],
        HORIZON_CONFIG: [("Set max in-flight requests per instance", RISK_LOW)],
    }),
]

CODE_HINT = re.compile(
    r"\b([\w/\-]+\.(?:py|js|ts|tsx|go|java|rb|rs|php|cs|yaml|yml|tf|json))\b"
    r"|\b(?:in|at|from)\s+([\w.]+\.[\w]+\(\))")


@dataclass
class Action:
    horizon: str
    action: str
    risk: str = RISK_MEDIUM
    rationale: str = ""
    source: str = "playbook"            # playbook | precedent | llm
    evidence_ids: list[str] = field(default_factory=list)
    requires_approval: bool = True      # always; kept explicit in the payload

    def to_dict(self) -> dict:
        return asdict(self)


_LLM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["actions", "code_locations"],
    "properties": {
        "actions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["horizon", "action", "risk", "rationale"],
            "properties": {
                "horizon": {"type": "string",
                            "enum": [HORIZON_IMMEDIATE, HORIZON_CORRECTIVE,
                                     HORIZON_PREVENTIVE, HORIZON_CONFIG]},
                "action": {"type": "string"},
                "risk": {"type": "string", "enum": [RISK_LOW, RISK_MEDIUM, RISK_HIGH]},
                "rationale": {"type": "string"}}}},
        "code_locations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["location", "why"],
            "properties": {"location": {"type": "string"}, "why": {"type": "string"}}}},
    },
}

_LLM_SYSTEM = """You propose remediation for a diagnosed production incident. A human will review
everything you write before anything is run; never phrase an action as already done.

Give actions in four horizons:
- immediate: stop customer impact now, lowest-risk option first.
- corrective: fix the actual defect, not the symptom.
- preventive: stop this class of failure recurring.
- configuration: a specific setting, limit or threshold to change, with the value.

Rate each action's risk honestly: an action that could worsen the outage is high risk.
Only name a code location when the evidence actually points at one - an invented file path
is worse than none. Do not repeat the actions already listed as known-good from precedent."""


def _playbook_actions(cause: str, text: str) -> list[Action]:
    blob = f"{cause} {text}".lower()
    actions: list[Action] = []
    for pattern, horizons in PLAYBOOKS:
        if not re.search(pattern, blob, re.I):
            continue
        for horizon, items in horizons.items():
            for action, risk in items:
                actions.append(Action(horizon=horizon, action=action, risk=risk,
                                      source="playbook",
                                      rationale="Matches a known failure mechanism"))
    return actions


def _precedent_actions(neighbours) -> list[Action]:
    """What actually fixed similar incidents, straight from the gold set."""
    out: list[Action] = []
    for n in (neighbours or [])[:5]:
        if not isinstance(n, dict):
            continue
        fix = (n.get("solution") or "").strip()
        if not fix:
            continue
        out.append(Action(
            horizon=HORIZON_CORRECTIVE,
            action=fix[:300],
            risk=RISK_MEDIUM,
            source="precedent",
            rationale=f"This resolved {n['id']} ({n.get('org', 'unknown')}), "
                      f"a {n.get('category', 'similar')} incident",
            evidence_ids=[n["id"]]))
    return out


def _code_locations(text: str, neighbours) -> list[dict]:
    """Only locations that literally appear in the evidence."""
    found: dict[str, str] = {}
    blobs = [text] + [f"{n.get('root_cause','')} {n.get('solution','')}"
                      for n in (neighbours or []) if isinstance(n, dict)]
    for blob in blobs:
        for m in CODE_HINT.finditer(blob or ""):
            loc = m.group(1) or m.group(2)
            if loc and loc not in found:
                found[loc] = "named in the incident evidence"
    return [{"location": k, "why": v, "source": "evidence"} for k, v in list(found.items())[:6]]


def _dedupe(actions: list[Action]) -> list[Action]:
    seen, out = set(), []
    for a in actions:
        key = re.sub(r"[^a-z0-9]", "", a.action.lower())[:70]
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def build_plan(text: str, cause: str = "", ctx=None, neighbours=None,
               use_llm: bool = True) -> dict:
    """Build a remediation plan. Never executes; always needs approval."""
    actions = _precedent_actions(neighbours) + _playbook_actions(cause, text)
    code_locations = _code_locations(text, neighbours)

    if use_llm:
        try:
            from rag.llm import chat_json
            known = "\n".join(f"- [{a.horizon}] {a.action}" for a in actions[:10])
            user = (f"INCIDENT:\n{text}\n\nDIAGNOSED CAUSE:\n{cause or 'not yet determined'}\n\n"
                    f"ALREADY PROPOSED FROM PRECEDENT AND PLAYBOOKS:\n{known or 'none'}")
            if ctx is not None and getattr(ctx, "causal", None):
                user += f"\n\nCAUSAL ANALYSIS:\n{ctx.causal.get('summary', '')}"
            got = chat_json(_LLM_SYSTEM, user, _LLM_SCHEMA, "remediation_plan")
        except Exception:
            got = None
        for a in (got or {}).get("actions", [])[:10]:
            actions.append(Action(horizon=a["horizon"], action=a["action"],
                                  risk=a.get("risk", RISK_MEDIUM),
                                  rationale=a.get("rationale", ""), source="llm"))
        for c in (got or {}).get("code_locations", [])[:5]:
            # Keep model-suggested locations, but label them so a reviewer
            # knows they were not read out of the evidence.
            code_locations.append({"location": c["location"], "why": c["why"],
                                   "source": "model-suggested"})

    actions = _dedupe(actions)
    order = {HORIZON_IMMEDIATE: 0, HORIZON_CORRECTIVE: 1,
             HORIZON_PREVENTIVE: 2, HORIZON_CONFIG: 3}
    risk_order = {RISK_LOW: 0, RISK_MEDIUM: 1, RISK_HIGH: 2}
    actions.sort(key=lambda a: (order.get(a.horizon, 9), risk_order.get(a.risk, 1)))

    by_horizon: dict[str, int] = {}
    for a in actions:
        by_horizon[a.horizon] = by_horizon.get(a.horizon, 0) + 1

    return {
        "cause": cause,
        "actions": [a.to_dict() for a in actions],
        "by_horizon": by_horizon,
        "code_locations": code_locations,
        "requires_human_approval": True,
        "execution": "none - this module proposes only and has no apply path",
        "approvals": [],
        "summary": _summary(actions, by_horizon),
    }


def _summary(actions: list[Action], by_horizon: dict) -> str:
    if not actions:
        return "No remediation could be proposed without a diagnosed cause."
    first = next((a for a in actions if a.horizon == HORIZON_IMMEDIATE), actions[0])
    precedent = sum(1 for a in actions if a.source == "precedent")
    bits = [f"{len(actions)} proposed action(s) across {len(by_horizon)} horizon(s)",
            f"start with: {first.action[:120]} (risk {first.risk})"]
    if precedent:
        bits.append(f"{precedent} drawn from what fixed similar incidents")
    bits.append("all actions require human approval before execution")
    return ". ".join(bits) + "."


def approve(plan: dict, index: int, approver: str, decision: str = "approved",
            note: str = "") -> dict:
    """Record a human decision on one action. Does not run anything.

    Kept so the approval trail lives with the plan; executing the action
    remains entirely outside this system.
    """
    if not 0 <= index < len(plan.get("actions", [])):
        raise IndexError("no such action")
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    entry = {"index": index, "action": plan["actions"][index]["action"],
             "decision": decision, "approver": approver, "note": note,
             "at": datetime.now(timezone.utc).isoformat()}
    plan.setdefault("approvals", []).append(entry)
    plan["actions"][index]["approval"] = entry
    return plan
