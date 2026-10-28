"""Step 7: grounded LLM analysis with strict JSON output and validation."""
from .config import CATEGORIES, SEVERITIES
from .llm import chat_json

MAX_HYPOTHESES = 3

ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "category", "category_confidence", "severity",
                 "severity_confidence", "hypotheses", "first_checks", "fix_steps", "novel"],
    "properties": {
        "summary": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
        "category_confidence": {"type": "number"},
        "severity": {"type": "string", "enum": SEVERITIES},
        "severity_confidence": {"type": "number"},
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["cause", "likelihood", "evidence_ids", "reasoning"],
                "properties": {
                    "cause": {"type": "string"},
                    "likelihood": {"type": "number"},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "reasoning": {"type": "string"},
                },
            },
        },
        "first_checks": {"type": "array", "items": {"type": "string"}},
        "fix_steps": {"type": "array", "items": {"type": "string"}},
        "novel": {"type": "boolean"},
    },
}

_SYSTEM = f"""You are a senior Site Reliability Engineer doing first-response root-cause analysis.
You get a new incident report and, when available, similar past production incidents from a
curated postmortem database, plus a statistical vote over those incidents.

Return:
- summary: one sentence restating the incident.
- category: exactly one of {", ".join(CATEGORIES)}.
  Use "other" only when none of the specific categories fits.
- severity: Low / Medium / High / Critical, judged by customer impact described in the report.
- hypotheses: up to {MAX_HYPOTHESES} root-cause hypotheses, most likely first. Each names a concrete
  mechanism (what broke and how), a likelihood between 0 and 1 (all likelihoods sum to at
  most 1), the ids of the past incidents that support it, and short reasoning.
  Cite only ids that appear in PAST INCIDENTS. A hypothesis with no supporting incident gets
  an empty evidence_ids list.
- first_checks: 3-5 concrete diagnostics an on-call engineer should run first, in order.
- fix_steps: 3-5 mitigation and remediation steps.
- novel: true when no past incident shares the failure mode.
- category_confidence and severity_confidence: between 0 and 1.

Past incidents marked [vague cause] have a published cause that is not specific; rely on
their symptom and fix rather than their cause. Do not invent details absent from the report."""


def _format_context(kb, neighbours, baseline):
    if not neighbours:
        return "PAST INCIDENTS: none retrieved. Reason from first principles; set novel to true."
    blocks = []
    for c in neighbours:
        d = kb.docs[c["row"]]
        score = f"relevance {c['relevance']}/10" if "relevance" in c else f"cosine {c.get('cosine', 0):.2f}"
        flag = " [vague cause]" if d.get("cause_is_vague") else ""
        blocks.append(
            f"[{d['id']}] {d['org']} | {d['category']} | {d['severity']} | {score}{flag}\n"
            f"  symptom: {d['issue']}\n  cause: {d['root_cause']}\n  fix: {d['solution']}"
        )
    vote = (f"VOTE OVER PAST INCIDENTS: category {baseline['category_distribution']}, "
            f"severity {baseline['severity_distribution']}")
    return "PAST INCIDENTS:\n" + "\n".join(blocks) + "\n\n" + vote


def validate(result, allowed_ids):
    """Clamp numbers, cap list lengths and drop citations to incidents not retrieved."""
    report = {"dropped_citations": [], "hypotheses_truncated": 0}
    clamp = lambda x: max(0.0, min(1.0, float(x)))
    result["category_confidence"] = clamp(result["category_confidence"])
    result["severity_confidence"] = clamp(result["severity_confidence"])
    hypotheses = sorted(result["hypotheses"], key=lambda h: -h["likelihood"])
    report["hypotheses_truncated"] = max(0, len(hypotheses) - MAX_HYPOTHESES)
    hypotheses = hypotheses[:MAX_HYPOTHESES]
    for h in hypotheses:
        h["likelihood"] = clamp(h["likelihood"])
        kept = [i for i in h["evidence_ids"] if i in allowed_ids]
        report["dropped_citations"] += [i for i in h["evidence_ids"] if i not in allowed_ids]
        h["evidence_ids"] = list(dict.fromkeys(kept))
    total = sum(h["likelihood"] for h in hypotheses)
    if total > 1:
        for h in hypotheses:
            h["likelihood"] = round(h["likelihood"] / total, 3)
    result["hypotheses"] = hypotheses
    result["first_checks"] = result["first_checks"][:5]
    result["fix_steps"] = result["fix_steps"][:5]
    return result, report


def analyze(kb, incident_text, neighbours, baseline):
    user = f"NEW INCIDENT:\n{incident_text}\n\n{_format_context(kb, neighbours, baseline)}"
    result = chat_json(_SYSTEM, user, ANALYSIS_SCHEMA, "rca_analysis")
    allowed = {kb.docs[c["row"]]["id"] for c in neighbours}
    return validate(result, allowed)
