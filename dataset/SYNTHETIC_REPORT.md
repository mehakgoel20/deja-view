# Synthetic RCA incident dataset

**1383 synthetic incidents** in `synthetic_incidents.json`, using the exact
schema and key order of `gold_incidents.json`.

This file contains **no real incidents**. It is generated, and it is kept in a
separate file from the gold set — nothing is merged.

## How a synthetic row is marked

Three fields make a synthetic row unmistakable, so it can never be confused
with a real one or silently mixed into a gold evaluation:

| field | value | why |
|---|---|---|
| `data_type` | `"synthetic"` | gold rows are always `"real"` |
| `id` | `SYN-0001` .. `SYN-1383` | gold uses `GOLD-####`, so ids cannot collide |
| `source_url` | `null` | there is no source, and inventing a plausible-looking URL is exactly the defect that had to be cleaned out of the gold set |
| `provenance` | `"synthetic_generated"` | gold uses `original_curated`, `statuspage_postmortem`, etc. |
| `org` | invented names | a fabricated incident is never filed under a real company's name |

The 260 organisation names are built from invented
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
* all 1383 `root_cause` values are distinct.

## Category mix

Mirrors the gold set exactly, so the synthetic set is a drop-in distributional
twin.

| category | synthetic | gold |
|---|---|---|
| configuration_deployment | 402 | 402 |
| database_issue | 223 | 223 |
| api_latency | 184 | 184 |
| other | 157 | 157 |
| hardware_infra | 123 | 123 |
| networking_dns | 109 | 109 |
| authentication | 88 | 88 |
| payment_processing | 53 | 53 |
| security_incident | 22 | 22 |
| concurrency_race_condition | 12 | 12 |
| memory_leak | 10 | 10 |

## Severity

| severity | count | share |
|---|---|---|
| Medium | 522 | 37.7% |
| High | 437 | 31.6% |
| Low | 246 | 17.8% |
| Critical | 178 | 12.9% |

Severity is sampled from per-pattern weights rather than forced to match gold's
marginal distribution, because the weights keep it coherent with the content —
a data-loss pattern should not be labelled `Low` just to hit a target.

## Dates

All dates are full `YYYY-MM-DD`, spread over 2019-2026 with a mild recency
bias. The gold set's year-only dates are an artefact of incomplete sourcing, so
that imprecision is not reproduced here.

| year | count | share |
|---|---|---|
| 2025 | 293 | 21.2% |
| 2026 | 276 | 20.0% |
| 2023 | 206 | 14.9% |
| 2024 | 195 | 14.1% |
| 2022 | 168 | 12.1% |
| 2021 | 113 | 8.2% |
| 2020 | 82 | 5.9% |
| 2019 | 50 | 3.6% |

## Field length, synthetic / gold

| field | p10 | p25 | p50 | p75 | p90 | mean |
|---|---|---|---|---|---|---|
| `issue` | 52 / 39 | 62 / 62 | 108 / 121 | 130 / 173 | 155 / 224 | 104 / 126 |
| `root_cause` | 124 / 100 | 186 / 123 | 240 / 156 | 318 / 201 | 352 / 263 | 246 / 171 |
| `solution` | 151 / 68 | 170 / 92 | 194 / 135 | 262 / 207 | 289 / 278 | 213 / 158 |

`issue` tracks gold closely. **`root_cause` and `solution` run roughly 30-40%
longer than gold at the median.** Gold's distribution is shaped by sentence
extraction from status pages, which often yields a single short sentence; the
generated text is a deliberate two-clause construction. The distributions
overlap but are not identical, so a classifier could separate the two sets on
length alone. If you need them statistically indistinguishable, say so and the
templates can be rewritten at mixed lengths.

## Known limitations

- Text variety comes from recombination, not from independent authorship. All
  1383 `root_cause` values are distinct, but there are
  767 distinct `solution` texts, so a fix
  phrasing recurs about 1.8 times on
  average across different incidents.
- The 56 patterns are modelled on common production failure modes, so the set
  covers those well and contains nothing genuinely novel or surprising. It will
  not test a model against an unusual mechanism.
- `memory_leak` (10) and `concurrency_race_condition`
  (12) are as thin as in gold, because the mix
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
