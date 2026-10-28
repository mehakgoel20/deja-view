"""Step 6: baseline category/severity prediction from retrieved neighbours.

A similarity-weighted vote. Category votes are divided by prior**alpha so the
402 configuration_deployment incidents do not drown out the 10 memory_leak
ones; alpha is tuned by leave-one-out on the training split (rag.evaluate).
"""
from .config import CATEGORIES, SEVERITIES

DEFAULT_ALPHA = 0.5


def neighbour_weight(c):
    if "relevance" in c:
        return c["relevance"] / 10
    return max(c.get("cosine", 0.0), 0.0)


def vote(kb, neighbours, alpha=DEFAULT_ALPHA):
    category, severity = {}, {}
    for c in neighbours:
        d, w = kb.docs[c["row"]], neighbour_weight(c)
        category[d["category"]] = category.get(d["category"], 0) + w
        severity[d["severity"]] = severity.get(d["severity"], 0) + w
    category = {k: v / (kb.category_prior[k] ** alpha) for k, v in category.items()}

    def normalise(scores, labels):
        total = sum(scores.values()) or 1.0
        dist = {k: round(scores.get(k, 0) / total, 3) for k in labels if scores.get(k)}
        best = max(dist, key=dist.get) if dist else None
        return best, dist

    cat, cat_dist = normalise(category, CATEGORIES)
    sev, sev_dist = normalise(severity, SEVERITIES)
    return {"category": cat, "category_distribution": cat_dist,
            "severity": sev, "severity_distribution": sev_dist}
