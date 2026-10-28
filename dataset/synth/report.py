"""Write SYNTHETIC_REPORT.md, comparing the synthetic set against gold."""
import json
import re
import statistics
from collections import Counter

G = json.load(open('../gold_incidents.json'))
S = json.load(open('../synthetic_incidents.json'))
OUT = '../SYNTHETIC_REPORT.md'
n = len(S)


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p / 100 * len(xs)))]


def tbl(c, head, total=None):
    total = total or n
    rows = '\n'.join(f'| {k} | {v} | {100.0*v/total:.1f}% |' for k, v in c.most_common())
    return f'| {head} | count | share |\n|---|---|---|\n{rows}\n'


gc = Counter(e['category'] for e in G)
sc = Counter(e['category'] for e in S)
cat_rows = '\n'.join(
    f'| {k} | {sc[k]} | {gc[k]} |' for k, _ in gc.most_common())

len_rows = []
for f in ('issue', 'root_cause', 'solution'):
    gl = [len(e[f]) for e in G]
    sl = [len(e[f]) for e in S]
    len_rows.append(
        f'| `{f}` | {pct(sl,10)} / {pct(gl,10)} | {pct(sl,25)} / {pct(gl,25)} | '
        f'{pct(sl,50)} / {pct(gl,50)} | {pct(sl,75)} / {pct(gl,75)} | '
        f'{pct(sl,90)} / {pct(gl,90)} | {int(statistics.mean(sl))} / {int(statistics.mean(gl))} |')

with open(OUT, 'w') as f:
    f.write(f"""# Synthetic RCA incident dataset

**{n} synthetic incidents** in `synthetic_incidents.json`, using the exact
schema and key order of `gold_incidents.json`.

This file contains **no real incidents**. It is generated, and it is kept in a
separate file from the gold set — nothing is merged.

## How a synthetic row is marked

Three fields make a synthetic row unmistakable, so it can never be confused
with a real one or silently mixed into a gold evaluation:

| field | value | why |
|---|---|---|
| `data_type` | `"synthetic"` | gold rows are always `"real"` |
| `id` | `SYN-0001` .. `SYN-{n:04d}` | gold uses `GOLD-####`, so ids cannot collide |
| `source_url` | `null` | there is no source, and inventing a plausible-looking URL is exactly the defect that had to be cleaned out of the gold set |
| `provenance` | `"synthetic_generated"` | gold uses `original_curated`, `statuspage_postmortem`, etc. |
| `org` | invented names | a fabricated incident is never filed under a real company's name |

The {len(set(e['org'] for e in S))} organisation names are built from invented
morphemes (`Wynelle Health`, `Glimix Analytics`, ...). None collides with any
organisation in the gold set.

## How entries are built

Each entry is anchored on one of 56 **failure patterns** that bundles a
symptom, the mechanism that explains it, and a fix that addresses that
mechanism. Within a pattern, cause and fix are authored as matched pairs and
are selected with the same index, so the solution always addresses the cause
that was actually stated. Surrounding sentences come from category-scoped
pools — a consequence clause (how the mechanism reached customers) and a
preventive clause (follow-up work) — which supply variety without breaking
coherence. Slot values (`the checkout service`, `the Cassandra ring`, ...) stay
consistent within a single entry.

Every entry therefore satisfies, by construction:

* the `root_cause` explains the `issue` rather than restating it;
* the `solution` addresses the stated `root_cause`;
* all {n} `root_cause` values are distinct.

## Category mix

Mirrors the gold set exactly, so the synthetic set is a drop-in distributional
twin.

| category | synthetic | gold |
|---|---|---|
{cat_rows}

## Severity

{tbl(Counter(e['severity'] for e in S), 'severity')}
Severity is sampled from per-pattern weights rather than forced to match gold's
marginal distribution, because the weights keep it coherent with the content —
a data-loss pattern should not be labelled `Low` just to hit a target.

## Dates

All dates are full `YYYY-MM-DD`, spread over 2019-2026 with a mild recency
bias. The gold set's year-only dates are an artefact of incomplete sourcing, so
that imprecision is not reproduced here.

{tbl(Counter(e['incident_date'][:4] for e in S), 'year')}
## Field length, synthetic / gold

| field | p10 | p25 | p50 | p75 | p90 | mean |
|---|---|---|---|---|---|---|
{chr(10).join(len_rows)}

`issue` tracks gold closely. **`root_cause` and `solution` run roughly 30-40%
longer than gold at the median.** Gold's distribution is shaped by sentence
extraction from status pages, which often yields a single short sentence; the
generated text is a deliberate two-clause construction. The distributions
overlap but are not identical, so a classifier could separate the two sets on
length alone. If you need them statistically indistinguishable, say so and the
templates can be rewritten at mixed lengths.

## Known limitations

- Text variety comes from recombination, not from independent authorship. All
  {n} `root_cause` values are distinct, but there are
  {len(set(e['solution'] for e in S))} distinct `solution` texts, so a fix
  phrasing recurs about {n/len(set(e['solution'] for e in S)):.1f} times on
  average across different incidents.
- The 56 patterns are modelled on common production failure modes, so the set
  covers those well and contains nothing genuinely novel or surprising. It will
  not test a model against an unusual mechanism.
- `memory_leak` ({sc['memory_leak']}) and `concurrency_race_condition`
  ({sc['concurrency_race_condition']}) are as thin as in gold, because the mix
  is mirrored. If you want these categories filled out instead, the generator
  takes any target mix — ask and it can be rebalanced.
- Severity is coherent with content but is not calibrated against gold's
  marginal distribution (see above).

## Rebuilding

```bash
cd dataset/synth
python3 generate.py        # writes ../synthetic_incidents.json
python3 validate_synth.py  # schema parity against gold + content sanity
python3 report.py          # rewrites this file
```

| file | contents |
|---|---|
| `patterns.py` | the 56 failure patterns (symptom / mechanism / fix) |
| `clauses.py` | consequence, preventive, scope and terse-title pools |
| `vocab.py` | slot vocabularies and the invented organisation pool |
| `generate.py` | composition, length shaping, deduplication |
| `validate_synth.py` | checks schema parity with gold and content sanity |

`generate.py` is seeded (`SEED = 20261006`), so a rebuild reproduces this file
byte for byte. Change `TARGET` for a different size or `GOLD_MIX` for a
different category balance.
""")

print('WROTE', OUT)
print('synthetic entries:', n)
