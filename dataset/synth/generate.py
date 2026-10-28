"""Generate a synthetic RCA dataset matching the gold schema exactly.

Design decisions worth knowing:

* `data_type` is "synthetic" and ids are `SYN-####`, so a synthetic row can
  never be mistaken for, or collide with, a gold row.
* `org` values are invented (see vocab.py). Putting a fabricated incident under
  a real company's name would be inventing a record about that company.
* `source_url` is null. Inventing a plausible-looking URL is exactly the defect
  that had to be cleaned out of the gold set, so no URL is emitted at all.
* Each entry is anchored on one mechanism pattern, so the root_cause explains
  the issue and the solution addresses the root_cause. Surrounding clauses come
  from category-scoped pools that are compatible with any mechanism in that
  category, which supplies variety without breaking coherence.

Deduplication note: gold used 4-gram shingle similarity, which is the wrong
tool here. Two fills of one template share nearly all their 4-grams, so that
rule would permit only one entry per template. Instead this enforces (a) no two
entries identical after slot filling, (b) no two entries sharing the same
clause skeleton *and* the same filled slot values, and (c) a hard cap on how
often any one skeleton may be reused.
"""
import json
import random
import re
from collections import Counter

from clauses import CONSEQ, PREVENT, SCOPE, TERSE
from patterns import P
from vocab import SLOTS, org_pool

TARGET = 1383
OUT = '../synthetic_incidents.json'
SEED = 20261006
SKELETON_CAP = 6

# mirrors the gold set's category mix so the synthetic set is a drop-in twin
GOLD_MIX = {
    'configuration_deployment': 402,
    'database_issue': 223,
    'api_latency': 184,
    'other': 157,
    'hardware_infra': 123,
    'networking_dns': 109,
    'authentication': 88,
    'payment_processing': 53,
    'security_incident': 22,
    'concurrency_race_condition': 12,
    'memory_leak': 10,
}
FIELD_ORDER = ['id', 'issue', 'root_cause', 'solution', 'severity', 'category',
               'org', 'source_url', 'incident_date', 'data_type', 'provenance']
SLOT_RE = re.compile(r'\{(\w+)\}')


def render(template, rng, chosen):
    """Fill slots, reusing any value already chosen for this entry.

    Slot names are visited in order of first appearance, not set order: string
    hashing is randomised per process, so iterating a set here would consume
    rng values in a different order on every run and break reproducibility.
    """
    for name in dict.fromkeys(SLOT_RE.findall(template)):
        if name not in chosen:
            chosen[name] = rng.choice(SLOTS[name])
    return SLOT_RE.sub(lambda m: chosen[m.group(1)], template)


def pick_severity(weights, rng):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def make_date(rng):
    """Full ISO dates over 2019-2026 with a mild recency bias.

    The gold set's year-only dates are an artefact of incomplete sourcing, so
    that imprecision is not reproduced here.
    """
    year = rng.choices(range(2019, 2027),
                       weights=[4, 5, 7, 9, 11, 14, 18, 16])[0]
    return f'{year:04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}'


def tidy(t):
    t = re.sub(r'\s+', ' ', t).strip()
    t = re.sub(r'\s+([.,;:])', r'\1', t)
    # Fields are built by joining sentences, and a slot value such as
    # "the catalogue API" can land at the start of any of them - so capitalise
    # every sentence, not just the first.
    t = re.sub(r'(^|(?<=[.!?])\s)([a-z])',
               lambda m: m.group(1) + m.group(2).upper(), t)
    return t


def _overlap(a, b):
    """Content-word overlap, used to suppress a restated preventive clause."""
    def toks(x):
        return {w for w in re.sub(r'[^a-z0-9 ]', '', x.lower()).split()
                if len(w) > 3}
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / float(min(len(ta), len(tb)))


def sentences(t):
    return [s for s in re.split(r'(?<=[.!?])\s+', t.strip()) if s]


def clip(t, keep):
    """Keep the first `keep` sentences, but never drop below 90 characters -
    a one-sentence cause still has to name a mechanism."""
    ss = sentences(t)
    if len(ss) <= keep:
        return t
    head = ' '.join(ss[:keep])
    return head if len(head) >= 90 else t


def main():
    rng = random.Random(SEED)
    orgs = org_pool(rng)

    rows = []
    skeletons = Counter()
    seen_text = set()
    seen_key = set()
    seen_cause = set()
    sol_uses = Counter()
    attempts = 0

    for cat, want in GOLD_MIX.items():
        pats = P[cat]
        conseqs, prevents = CONSEQ[cat], PREVENT[cat]
        made = 0
        while made < want:
            attempts += 1
            if attempts > TARGET * 600:
                raise SystemExit(f'could not fill {cat}: {made}/{want}')

            pi = rng.randrange(len(pats))
            pat = pats[pi]
            ii = rng.randrange(len(pat['issue']))
            # cause[i] and fix[i] are authored as matched pairs: the fix must
            # address the cause that was actually selected, so they share an index
            ci = rng.randrange(len(pat['cause']))
            fi = ci
            qi = rng.randrange(len(conseqs))
            vi = rng.randrange(len(prevents))
            si = rng.randrange(len(SCOPE))
            # length shaping: how much of each field to keep, so the synthetic
            # length distribution overlaps gold's instead of running long
            kc = rng.choices([1, 2, 3], weights=[70, 22, 8])[0]    # cause sentences
            kf = rng.choices([1, 2], weights=[76, 24])[0]          # fix sentences
            terse = rng.random() < 0.34        # status-page style short title
            use_scope = rng.random() < 0.22    # extra scope sentence on issue
            ti = rng.randrange(len(TERSE[cat]))
            skel = (cat, pi, ii, ci, fi, qi, vi, si, kc, kf, terse, use_scope, ti)
            if skeletons[skel] >= SKELETON_CAP:
                continue

            chosen = {}
            if terse:
                issue = render(TERSE[cat][ti], rng, chosen)
            else:
                issue = render(pat['issue'][ii], rng, chosen)
            if use_scope and SCOPE[si]:
                issue = issue + ' ' + render(SCOPE[si], rng, chosen)
            cause = clip(render(pat['cause'][ci], rng, chosen) + ' '
                         + render(conseqs[qi], rng, chosen), kc)
            base_fix = render(pat['fix'][fi], rng, chosen)
            prevent = render(prevents[vi], rng, chosen)
            if _overlap(base_fix, prevent) > 0.55:
                prevent = ''        # would just restate the immediate fix
            sol = clip((base_fix + ' ' + prevent).strip(), kf)
            issue, cause, sol = tidy(issue), tidy(cause), tidy(sol)

            # (a) no two entries identical after slot filling
            text_key = (issue, cause, sol)
            if text_key in seen_text:
                continue
            # (b) no repeat of the same skeleton with the same slot values
            slot_key = skel + tuple(sorted(chosen.items()))
            if slot_key in seen_key:
                continue
            # (c) root_cause is the field an RCA model is judged on, so it must
            #     be unique across the whole set
            if cause in seen_cause:
                continue
            # (d) fixes legitimately repeat across incidents, but cap the reuse
            if sol_uses[sol] >= 4:
                continue

            seen_text.add(text_key)
            seen_key.add(slot_key)
            seen_cause.add(cause)
            sol_uses[sol] += 1
            skeletons[skel] += 1
            made += 1
            rows.append({
                'issue': issue,
                'root_cause': cause,
                'solution': sol,
                'severity': pick_severity(pat['sev'], rng),
                'category': cat,
                'org': rng.choice(orgs),
                'source_url': None,
                'incident_date': make_date(rng),
                'data_type': 'synthetic',
                'provenance': 'synthetic_generated',
            })

    rows.sort(key=lambda r: (r['incident_date'], r['org']))
    out = []
    for i, r in enumerate(rows, 1):
        e = {'id': f'SYN-{i:04d}'}
        for k in FIELD_ORDER[1:]:
            e[k] = r[k]
        out.append(e)

    json.dump(out, open(OUT, 'w'), indent=2)

    print('TOTAL:', len(out))
    print('categories:', Counter(e['category'] for e in out).most_common())
    print('severity:', Counter(e['severity'] for e in out).most_common())
    print('orgs:', len(set(e['org'] for e in out)))
    print('years:', sorted(Counter(e['incident_date'][:4] for e in out).items()))
    print('avg lens: issue %d rc %d sol %d' % (
        sum(len(e['issue']) for e in out) // len(out),
        sum(len(e['root_cause']) for e in out) // len(out),
        sum(len(e['solution']) for e in out) // len(out)))
    print('distinct skeletons:', len(skeletons), '| max reuse:', max(skeletons.values()),
          '| mean reuse: %.2f' % (len(out) / len(skeletons)))
    print('WROTE', OUT)


if __name__ == '__main__':
    main()
