"""Root cause investigator (stage 2).

Reads every stage-1 finding plus the deterministic causal graph and commits to
ranked hypotheses. Two deliberate choices:

* The causal graph is computed *before* the LLM sees it, so the model is asked
  to judge a structure it did not invent. Asking a model to both generate and
  grade its own causal chain is how confident nonsense gets produced.
* Hypotheses must cite evidence ids that actually exist. Anything else is
  dropped and counted, which is what the benchmark measures as hallucination.
"""
from __future__ import annotations

import re

from .base import (FINDING_GAP, FINDING_HYPOTHESIS, FINDING_OBSERVATION,
                   Agent, Context, Finding)


def _key(text: str) -> set:
    """Content words, for deciding whether two hypotheses say the same thing."""
    stop = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "was",
            "were", "is", "are", "its", "it", "that", "which", "had", "has",
            "causal", "engine"}
    return {w for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in stop and len(w) > 2}


def _same_claim(a: str, b: str, threshold: float = 0.6) -> bool:
    ka, kb = _key(a), _key(b)
    if not ka or not kb:
        return False
    return len(ka & kb) / len(ka | kb) >= threshold

INVESTIGATION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["hypotheses", "discriminating_checks", "verdict"],
    "properties": {
        "hypotheses": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["cause", "likelihood", "is_root_cause", "evidence_ids",
                         "supporting", "contradicting", "reasoning"],
            "properties": {
                "cause": {"type": "string"},
                "likelihood": {"type": "number"},
                "is_root_cause": {"type": "boolean"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "supporting": {"type": "array", "items": {"type": "string"}},
                "contradicting": {"type": "array", "items": {"type": "string"}},
                "reasoning": {"type": "string"},
            }}},
        "discriminating_checks": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string"},
    },
}

_SYSTEM = """You are the lead investigator in a root-cause analysis. Specialist agents have
already gathered evidence, and a causal graph has been built mechanically from the
timing, the service topology and known failure mechanisms.

Your job is to judge that evidence, not to invent more.

Rules:
- Every hypothesis must name a concrete mechanism: what broke and how. "Latency increased"
  is a symptom, not a cause. Set is_root_cause false for anything that is an effect of
  something else in the evidence.
- Cite only ids that appear in the EVIDENCE section (signal ids like PROM-MET-001 or
  incident ids like GOLD-0123). Never invent an id.
- For each hypothesis list what supports it and, importantly, what contradicts it. A
  hypothesis whose timing is wrong - a change that happened after the symptom it is
  supposed to have caused - must be marked contradicted and given a low likelihood.
- discriminating_checks: diagnostics that would tell the top hypotheses apart. A check
  that cannot change the ranking is useless.
- verdict: one paragraph an on-call engineer can act on, stating your confidence honestly.
- likelihoods sum to at most 1."""


class RootCauseInvestigator(Agent):
    name = "root_cause_investigator"
    role = "Weighs all findings and commits to ranked root-cause hypotheses"
    stage = 2

    def run(self, ctx: Context, findings: list[Finding] | None = None) -> list[Finding]:
        findings = findings or []
        causal = ctx.causal or {}
        out: list[Finding] = []

        # The causal engine's ranking stands on its own, so the investigation
        # is useful with no LLM at all.
        mechanical = (causal.get("hypotheses") or [])[:3]
        for h in mechanical:
            out.append(self.finding(
                FINDING_HYPOTHESIS, h["cause"],
                h.get("likelihood", 0.0), h.get("evidence_ids", []),
                source="causal_engine", is_root_cause=h.get("is_root_cause", True),
                contradictions=[c["basis"] for c in h.get("contradictions", [])]))

        if not ctx.use_llm:
            return out

        allowed = self._allowed_ids(ctx)
        got = self.ask_llm(_SYSTEM, self._prompt(ctx, findings),
                           INVESTIGATION_SCHEMA, "rca_investigation")
        if not got:
            out.append(self.finding(
                FINDING_GAP,
                "The reasoning model was unavailable; the ranking above comes from "
                "the deterministic causal engine only.", 0.9))
            return out

        dropped: list[str] = []
        hyps = sorted(got.get("hypotheses", []),
                      key=lambda h: -h.get("likelihood", 0))[:4]
        total = sum(max(0.0, h.get("likelihood", 0)) for h in hyps) or 1.0
        for h in hyps:
            cited = [i for i in h.get("evidence_ids", []) if i in allowed]
            dropped += [i for i in h.get("evidence_ids", []) if i not in allowed]
            like = max(0.0, min(1.0, h.get("likelihood", 0)))
            if total > 1:
                like = round(like / total, 3)

            # If the model reaches the same conclusion as the mechanical
            # ranking, merge them rather than listing the claim twice. Two
            # independent methods agreeing is itself evidence, so the merged
            # entry is scored up and marked corroborated.
            existing = next((f for f in out if f.kind == FINDING_HYPOTHESIS
                             and _same_claim(f.statement, h["cause"])), None)
            if existing is not None:
                existing.confidence = round(
                    min(1.0, max(existing.confidence, like) + 0.1), 3)
                existing.evidence_ids = list(dict.fromkeys(
                    existing.evidence_ids + cited))
                existing.detail.update(
                    source="causal_engine+llm", corroborated=True,
                    supporting=h.get("supporting", [])[:4],
                    contradicting=h.get("contradicting", [])[:4],
                    reasoning=h.get("reasoning", ""))
                continue

            out.append(self.finding(
                FINDING_HYPOTHESIS, h["cause"], like, list(dict.fromkeys(cited)),
                source="llm",
                is_root_cause=bool(h.get("is_root_cause", True)),
                supporting=h.get("supporting", [])[:4],
                contradicting=h.get("contradicting", [])[:4],
                reasoning=h.get("reasoning", "")))
        for c in got.get("discriminating_checks", [])[:5]:
            out.append(self.finding(FINDING_OBSERVATION, f"Discriminating check: {c}",
                                    0.6, [], source="llm"))
        if got.get("verdict"):
            out.append(self.finding(FINDING_OBSERVATION, got["verdict"], 0.7, [],
                                    source="llm", role="verdict"))
        if dropped:
            out.append(self.finding(
                FINDING_GAP,
                f"Dropped {len(dropped)} invented evidence id(s): "
                f"{', '.join(sorted(set(dropped))[:6])}",
                1.0, [], dropped_citations=sorted(set(dropped))))
        return out

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _allowed_ids(ctx: Context) -> set[str]:
        ids = {s.id for s in ctx.signals}
        ids |= {n["id"] for n in ctx.neighbours if isinstance(n, dict) and "id" in n}
        return ids

    @staticmethod
    def _prompt(ctx: Context, findings: list[Finding]) -> str:
        from observability.correlate import evidence_block
        parts = [f"NEW INCIDENT:\n{ctx.text}"]
        if ctx.signals:
            parts.append(evidence_block(ctx.signals))
        if ctx.neighbours:
            lines = []
            for n in ctx.neighbours[:5]:
                lines.append(f"[{n['id']}] {n['org']} | {n['category']}\n"
                             f"  symptom: {n['issue'][:200]}\n"
                             f"  cause: {n['root_cause'][:200]}\n"
                             f"  fix: {(n.get('solution') or 'not published')[:160]}")
            parts.append("PAST INCIDENTS:\n" + "\n".join(lines))
        if ctx.timeline:
            from timeline import render as render_timeline
            parts.append(render_timeline(ctx.timeline))
        if ctx.causal.get("graph_text"):
            parts.append(ctx.causal["graph_text"])
        if ctx.causal.get("hypotheses_text"):
            parts.append("MECHANICAL RANKING (for you to judge):\n"
                         + ctx.causal["hypotheses_text"])
        if findings:
            lines = [f"  [{f.agent}] ({f.confidence:.2f}) {f.statement[:220]}"
                     for f in findings if f.kind != FINDING_GAP]
            gaps = [f"  [{f.agent}] MISSING: {f.statement[:160]}"
                    for f in findings if f.kind == FINDING_GAP]
            parts.append("AGENT FINDINGS:\n" + "\n".join(lines + gaps))
        return "\n\n".join(parts)
