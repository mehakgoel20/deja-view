"""Step 1: clean the gold incidents.

Strips section labels left over from status-page scraping ("Root cause ...",
"Summary ...", "Why it happened: ...") and page boilerplate, and flags root
causes that only assert a cause without describing it. The gold file itself
is never modified; output goes to data/gold_clean.json.

    python -m rag.clean
"""
import json
import re
from collections import Counter

from .config import CATEGORIES, CLEAN_PATH, DATA_DIR, GOLD_PATH, SEVERITIES

_HEAD = (
    r"(?i:Primary Root Cause|Root Cause and Resolution|Root Cause|Background|Incident Summary|Summary|Resolution|Impact"
    r"|Remediation|Mitigation|Next Steps|Action Items|Timeline|Problem Description,?"
    r"|What happened|Why it happened|How we fixed it"
    r"|What caused (?:it|this|the (?:issue|incident))|Contributing Factors?)"
)
# A label at the start of the text or of a sentence, directly followed by a
# capitalised word: "Root cause We determined ..." -> "We determined ...".
# A lower-case continuation ("Summary of ...", "Remediation involved ...")
# is prose, not a label, and is kept.
_LABEL = re.compile(r"(?:^|(?<=[.!?:)]\s))" + _HEAD + r"\s*:?\s+(?=[A-Z0-9\"“(])")
# "Root cause(s)" at the start is a heading even before a lower-case word
# ("Root cause npm's spam analysis ..."), unless the sentence continues it
# ("Root cause was ...", "Root cause analysis of ...").
_ROOT_CAUSE_HEAD = re.compile(
    r"^(?i:root causes?)\s*:?\s+(?!(?:was|were|is|are|of|analysis|for|and|has|have|remains?"
    r"|appears?|lies|isolated|identified|determined|found)\b)"
)
# A label followed by a colon is a label wherever it appears.
_COLON_LABEL = re.compile(r"\b" + _HEAD + r"\s*:\s*")
_COMPONENTS = re.compile(r"Components impacted\b.*?\bSummary\s+", re.I)
_JUNK = [
    re.compile(r"\b\d+ min read\s*", re.I),
    re.compile(r"By The [\w ]+? Team, view all posts by this author\s*", re.I),
    re.compile(r"Share Link copied to clipboard!\s*", re.I),
]
_VAGUE = re.compile(
    r"\b(we (?:have )?identified (?:a|an|the)\b(?! root)|discrepancy|under investigation"
    r"|still investigating|identified the (?:root )?cause)\b",
    re.I,
)
_MECHANISM = re.compile(
    r"\b(caus|due to|because|result|introduc|trigger|misconfigur|bug|fail|expired"
    r"|exhaust|overload|deploy|change|outage|error|crash|leak|race|corrupt)",
    re.I,
)


def clean_text(text):
    text = " ".join((text or "").split())
    for junk in _JUNK:
        text = junk.sub("", text)
    text = _COMPONENTS.sub("", text)
    # Labels can be stacked ("Summary Root cause ..."), so repeat until stable.
    for _ in range(3):
        stripped = _COLON_LABEL.sub("", _LABEL.sub("", _ROOT_CAUSE_HEAD.sub("", text)))
        if stripped == text:
            break
        text = stripped
    text = text.strip()
    if text and text[-1] not in ".!?\"”)":
        text += "."
    return text


def is_vague_cause(cause):
    """True when a root cause asserts that a cause exists without stating it."""
    return bool(_VAGUE.search(cause)) and not _MECHANISM.search(_VAGUE.sub("", cause))


def clean_entries(raw):
    cleaned, stats = [], Counter()
    for entry in raw:
        row = dict(entry)
        for field in ("issue", "root_cause", "solution"):
            row[field] = clean_text(entry.get(field))
            if row[field] != " ".join((entry.get(field) or "").split()):
                stats["changed_" + field] += 1
        if len(row["issue"]) < 20 or len(row["root_cause"]) < 20:
            stats["dropped_too_short"] += 1
            continue
        if row["category"] not in CATEGORIES or row["severity"] not in SEVERITIES:
            stats["dropped_bad_label"] += 1
            continue
        row["cause_is_vague"] = is_vague_cause(row["root_cause"])
        stats["vague_cause"] += row["cause_is_vague"]
        cleaned.append(row)
    return cleaned, stats


def main():
    raw = json.loads(GOLD_PATH.read_text())
    cleaned, stats = clean_entries(raw)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_PATH.write_text(json.dumps(cleaned, indent=1, ensure_ascii=False))
    print(f"read {len(raw)} entries from {GOLD_PATH}")
    print(f"kept {len(cleaned)}  -> {CLEAN_PATH}")
    for key, value in sorted(stats.items()):
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
