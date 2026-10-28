# Gold RCA incident dataset

**1383 real production incidents.** Every entry has a live, incident-specific
source URL that returned a non-404 status at build time.

## Schema

| field | notes |
|---|---|
| `id` | `GOLD-0001` .. `GOLD-1383`, renumbered on every build |
| `issue` | the customer-visible symptom |
| `root_cause` | the mechanism that caused it |
| `solution` | what was done to resolve or mitigate it |
| `severity` | `Critical` / `High` / `Medium` / `Low` |
| `category` | one of 11 values, see below |
| `org` | the organisation that published the report |
| `source_url` | link to the specific incident report |
| `incident_date` | `YYYY`, `YYYY-MM` or `YYYY-MM-DD` |
| `data_type` | always `real` |
| `provenance` | how the entry was built, see below |
| `note` | optional caveat; present only on some curated entries |

## Provenance

| source | count | share |
|---|---|---|
| statuspage_postmortem | 1097 | 79.3% |
| original_curated | 198 | 14.3% |
| github_availability_report | 61 | 4.4% |
| curated_index+source_page | 26 | 1.9% |
| aws_post_event_summary | 1 | 0.1% |

- `original_curated` — hand-written entries retained from the previous
  `gold_seed_entries.json`, after cleaning.
- `statuspage_postmortem` — postmortem / resolution text published on company
  status pages, read through the Statuspage v2 API.
- `github_availability_report` — individual incidents inside GitHub's monthly
  availability reports.
- `aws_post_event_summary` — AWS post-event summaries.
- `curated_index+source_page` — the danluu/post-mortems index, with cause text
  cross-checked against the original write-up.

## Category

| category | count | share |
|---|---|---|
| configuration_deployment | 402 | 29.1% |
| database_issue | 223 | 16.1% |
| api_latency | 184 | 13.3% |
| other | 157 | 11.4% |
| hardware_infra | 123 | 8.9% |
| networking_dns | 109 | 7.9% |
| authentication | 88 | 6.4% |
| payment_processing | 53 | 3.8% |
| security_incident | 22 | 1.6% |
| concurrency_race_condition | 12 | 0.9% |
| memory_leak | 10 | 0.7% |

## Severity

| severity | count | share |
|---|---|---|
| Medium | 551 | 39.8% |
| High | 409 | 29.6% |
| Low | 214 | 15.5% |
| Critical | 209 | 15.1% |

## Date coverage

| date precision | count |
|---|---|
| YYYY-MM-DD | 1329 |
| YYYY | 42 |
| YYYY-MM | 12 |

| year | count |
|---|---|
| 2026 | 627 |
| 2025 | 324 |
| 2024 | 113 |
| 2023 | 72 |
| 2022 | 58 |
| 2021 | 49 |
| 2019 | 26 |
| 2020 | 18 |
| 2014 | 15 |
| 2016 | 15 |
| 2017 | 15 |
| 2012 | 13 |
| 2018 | 10 |
| 2015 | 9 |
| 2013 | 7 |
| 2003 | 2 |
| 2009 | 2 |
| 2011 | 2 |
| 1969 | 1 |
| 1980 | 1 |
| 1990 | 1 |
| 1994 | 1 |
| 2000 | 1 |
| 2007 | 1 |

## Organisations

394 distinct organisations. Most frequent:

| org | count | share |
|---|---|---|
| GitHub | 123 | 8.9% |
| Harness | 31 | 2.2% |
| Currencycloud | 28 | 2.0% |
| KnowBe4 | 27 | 2.0% |
| xMatters | 25 | 1.8% |
| Box | 25 | 1.8% |
| Cloudflare | 23 | 1.7% |
| Kustomer | 22 | 1.6% |
| MovableInk | 22 | 1.6% |
| Thycotic | 22 | 1.6% |
| Twingate | 18 | 1.3% |
| PubNub | 18 | 1.3% |
| Close | 15 | 1.1% |
| Neo4j | 15 | 1.1% |
| Smartsheet | 15 | 1.1% |
| Socure | 15 | 1.1% |
| LiveKit | 15 | 1.1% |
| CircleCI | 14 | 1.0% |
| Google Cloud | 12 | 0.9% |
| Trello | 12 | 0.9% |
| Lucidworks | 12 | 0.9% |
| Bitbucket | 12 | 0.9% |
| Tink | 12 | 0.9% |
| AWS | 11 | 0.8% |
| Dyte | 11 | 0.8% |

## What is guaranteed

Every entry:

1. has a `source_url` that resolved (non-404) at build time;
2. has an `incident_date` matching `YYYY`, `YYYY-MM` or `YYYY-MM-DD`;
3. has `root_cause` and `solution` of at least 45 characters, and an `issue` of
   at least 25, all three mutually distinct — no entry restates its symptom as
   its cause;
4. is deduplicated against every other entry by source URL and by root-cause
   shingle similarity (Jaccard > 0.55 rejected);
5. states an actual causal mechanism. Reports that only assert one
   ("we have identified the root cause and are working on a fix"), or that
   offer an apology, a responder-paging note or a downstream-impact note in
   place of a cause, were rejected rather than kept as filler.

## Rebuilding

```bash
cd dataset/build
python3 rebuild_pool.py   # merge every harvested status-page payload into one pool
bash build.sh             # extract -> assemble -> finalize -> audit
```

`build.sh` runs the four stages in order:

| stage | script | what it does |
|---|---|---|
| extract | `run_extract2.py`, `extract_gh2.py`, `extract_aws.py`, `extract_danluu.py` | pull `issue`/`root_cause`/`solution` out of each source |
| assemble | `assemble.py` | validate, dedupe, HTTP-verify every URL |
| finalize | `finalize.py` | normalise org names, renumber, write dataset + this report |
| audit | `audit.py` | re-check every guarantee independently and spot-check 120 live URLs |

Quality rules live in `polish.py`; the sentence-selection logic lives in
`extract3.py`. URL verdicts are cached in `build/raw/newurlstatus.json`, so a
rebuild only re-checks URLs it has not seen.

To widen coverage, add company slugs to a `names*.txt` file, then:

```bash
python3 gen_hosts.py names16.txt hosts16.txt
sed 's/hosts12.txt/hosts16.txt/; s/statuspage12_raw/statuspage16_raw/' probe12.py > probe16.py
python3 probe16.py        # discovers live Statuspage hosts and harvests them
python3 rebuild_pool.py && bash build.sh
```

## Known limitations

- For everything other than `original_curated`, `root_cause` and `solution` are
  composed from sentences in the published report rather than freely
  paraphrased. They read closer to the source text than the hand-written
  entries do.
- `memory_leak` (10) and `concurrency_race_condition`
  (12) stay under-represented. Status-page
  postmortems rarely attribute an incident to either; the examples that exist
  come mostly from long-form engineering blogs.
- GitHub is the largest single contributor (123 entries,
  8.9%) because it publishes a detailed monthly
  availability report. Weight by `org` if that concentration matters for your
  evaluation.
- Statuspage's public API exposes only each company's ~50 most recent
  incidents, so coverage skews to recent years.
- `severity` for status-page entries is derived from the publisher's own impact
  flag (`critical`/`major`/`minor`/`none`), not from a uniform rubric, so it is
  not strictly comparable across organisations.
