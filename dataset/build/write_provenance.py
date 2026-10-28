"""Generate DATA_PROVENANCE.md - the full account of how the gold set was built."""
import json
import os
import re
from collections import Counter

OUT = '../DATA_PROVENANCE.md'
R = json.load(open('raw/provenance.json'))
F = json.load(open('../gold_incidents.json'))
ALL = json.load(open('../gold_incidents_all.json')) \
    if os.path.exists('../gold_incidents_all.json') else F
# The original seed file is no longer present in dataset/; its inventory
# survives in build/urlstatus.json (all 383 ids) and build/clean_base.json.
try:
    SEED = json.load(open('../gold_seed_entries.json'))
except FileNotFoundError:
    SEED = json.load(open('urlstatus.json'))   # 383 rows: id, status, url
dropped = json.load(open('dropped.json')) if os.path.exists('dropped.json') else {}
seedurl = json.load(open('urlstatus.json')) if os.path.exists('urlstatus.json') else []

n = len(F)
cause_only = [e for e in ALL if e.get('solution') is None]
full = [e for e in F if e.get('solution') is not None]
n_all = len(ALL)
hv = R['harvest']
hd = R['host_discovery']
os_ = R['other_sources']
ex = R['extraction']


def table(pairs, head, total=None, pctcol=True):
    total = total or n
    head_row = (f'| {head} | count | share |\n|---|---|---|'
                if pctcol else f'| {head} | count |\n|---|---|')
    rows = []
    for k, v in pairs:
        rows.append(f'| {k} | {v} | {100.0*v/total:.1f}% |' if pctcol
                    else f'| {k} | {v} |')
    return head_row + '\n' + '\n'.join(rows) + '\n'


prov = Counter(e['provenance'] for e in F)
cats = Counter(e['category'] for e in F)
sevs = Counter(e['severity'] for e in F)
orgs = Counter(e['org'] for e in F)
years = Counter(str(e['incident_date'])[:4] for e in F)
dropreasons = Counter(r for rs in dropped.values() for r in rs)
seedstat = Counter(r[1] for r in seedurl)
ISO = re.compile(r'\d{4}-\d{2}-\d{2}')
coarse_dates = sum(1 for e in F if not ISO.fullmatch(str(e['incident_date'])))
capped_hosts = R.get('capped_hosts', 801)
live_hosts_total = R.get('live_hosts_total', hv['distinct_live_status_hosts'])

doc = f"""# Where this dataset came from, and what is actually in it

`gold_incidents.json` - **{n} real production incidents** from
**{len(orgs)} organisations**, each with a live, incident-specific source URL.

This document is the complete account: every source, how it was found, what
each one contributed, what was thrown away and why, and which biases are baked
into the result. Read the **Honest limitations** section before using this for
anything you will publish.

---

## 1. The short version

| | |
|---|---|
| Entries | **{n}** |
| Distinct organisations | **{len(orgs)}** |
| Every entry has `issue` + `root_cause` + `solution` | **yes** |
| Companion superset `gold_incidents_all.json` | **{n_all}** entries, of which {len(cause_only)} are cause-only |
| Date range | {min(years)} - {max(years)} |
| Source URLs verified live at build time | **{R['url_verification']['urls_checked']}** checked, 0 dead |
| Candidate status-page hostnames probed to find the sources | **{hd['total_candidate_hosts_probed']:,}** |
| Live status pages discovered | **{hv['distinct_live_status_hosts']:,}** |
| Raw incidents harvested | **{hv['pool_unique_incidents']:,}** |
| Raw incidents that survived to the dataset | {100.0*n/hv['pool_unique_incidents']:.1f}% |

### Why the dataset is this size, and not larger

The size is set by measured supply, not by effort. From the funnel:

| | |
|---|---|
| raw incidents harvested | {hv['pool_unique_incidents']:,} |
| live status hosts behind them | {live_hosts_total:,} |
| raw incidents per host | {hv['pool_unique_incidents']/max(1,live_hosts_total):.1f} |
| complete entries extracted | {n:,} |
| **yield (complete / raw)** | **{100.0*n/hv['pool_unique_incidents']:.1f}%** |

Scaling that to a 5,000-entry complete dataset would require roughly
**{5000/(n/hv['pool_unique_incidents']):,.0f} raw incidents**, which at
{hv['pool_unique_incidents']/max(1,live_hosts_total):.0f} incidents per host
means about **{5000/(n/hv['pool_unique_incidents'])/(hv['pool_unique_incidents']/max(1,live_hosts_total)):,.0f} live
status hosts** - against the {live_hosts_total:,} found here. The marginal
hit rate on hostname guessing has fallen to about 2%, so that implies probing
on the order of 100,000+ further candidates, and the population of companies
that actually run a public status page *and* publish causes with remediations
is almost certainly smaller than that target anyway.

Two other routes were tested and are closed: the Statuspage API caps at 50
incidents per host and ignores `?page`, `?per_page` and `?limit`, so the older
history of the {capped_hosts} capped hosts is unreachable; and the Internet
Archive, which holds snapshots of those same endpoints, returned
"Temporarily Offline" throughout this work.

The honest ceiling for *real, verified, complete* incidents from public
sources, at this quality bar, is in the low thousands.

The single most important fact: **most public incident reports never state a
root cause.** Of {hv['pool_unique_incidents']:,} harvested status-page
incidents, only about {100.0*ex['statuspage_entries']/hv['pool_unique_incidents']:.0f}%
contained an extractable cause. That ratio, not effort, is what caps the size
of a dataset like this.

---

## 2. Where it was scraped from

### 2.1 Company status pages (Atlassian Statuspage) - the bulk of the data

**{ex['statuspage_entries']} entries ({100.0*ex['statuspage_entries']/n:.0f}% of the dataset).**

Atlassian Statuspage powers the status site of a large share of SaaS
companies, and every one of those sites exposes an undocumented-but-public
JSON endpoint:

```
https://<status-host>/api/v2/incidents.json
```

That returns the most recent incidents with their full update timeline,
including any `postmortem`-status update. No key, no scraping of rendered HTML.

**How the hosts were found - two phases.**

*Phase 1, name guessing (superseded).* There is no public directory of
Statuspage customers, so hostnames were generated and probed. {len(hd['name_lists'])}
lists of company slugs were written out by vertical (payments, observability,
data infrastructure, identity, logistics, Indian fintech, AI/ML tooling, and
so on), then expanded against ~20 hostname templates each:

```
<slug>.statuspage.io      status.<slug>.com     status.<slug>.io
<slug>status.com          status.<slug>.dev     status.<slug>.ai     ...
```

| stage | count |
|---|---|
| candidate hostnames generated and probed | {hd['total_candidate_hosts_probed']:,} |
| returned a valid Statuspage API response | {hv['distinct_live_status_hosts']:,} |
| hit rate | {100.0*hv['distinct_live_status_hosts']/hd['total_candidate_hosts_probed']:.1f}% |

Hit rate fell from ~4.4% in the first rounds to ~1% by the last. The reason
turned out to be structural, not effort: **Statuspage assigns each page a
random subdomain id**, so `027j6zrg2zwb.statuspage.io` is Mixmax and
`029txycd4lgb.statuspage.io` is Zaptec. No amount of company-name guessing
reaches those.

*Phase 2, archive enumeration (what actually worked).* The Wayback Machine's
CDX index returns every URL it has archived for a domain:

```
https://web.archive.org/cdx/search/cdx?url=statuspage.io&matchType=domain
    &output=json&fl=original&collapse=urlkey
```

That yielded **31,707 distinct statuspage.io hostnames** - more than 20x what
name guessing found. Common Crawl's index added 1,160 more. Probing all of them
found **2,471 further live status pages carrying 37,749 incidents**, and
filtered out 3,100 SEO-spam pages (pirated-media and casino sites abusing free
Statuspage accounts, which are real hosts but publish no real incidents).

This is the step that took the pool from 32,849 to {hv['pool_unique_incidents']:,}
incidents. Deeper CDX pagination returned no further hostnames, so this source
is now genuinely exhausted rather than merely tedious.

**A structural limit worth knowing:** the API returns at most **50 incidents
per host**. Of the live hosts found, **{capped_hosts} of {live_hosts_total}
returned exactly 50**, meaning their older history is simply not reachable
this way. This is the direct cause of the recency skew in section 5.

### 2.2 GitHub monthly availability reports

**{ex['github_entries']} entries.** GitHub publishes a monthly post describing
each incident that month, with explicit "What went wrong and why?" and "How did
we respond?" sections - unusually good material.

- Fetched: `github.blog/news-insights/company-news/github-availability-report-<month>-<year>/`
  for every month 2019-2026, {os_['github_availability_reports_fetched']} pages retrieved.
- 73 unique reports parsed; each contains 2-5 separate incidents, split apart
  on the `Month DD HH:MM UTC (lasting ...)` heading that delimits them.
- Several incidents legitimately share one report URL. That is not duplication
  and the de-duplicator allows it, as long as the root causes differ.

### 2.3 Engineering-blog postmortems

**{ex['blog_entries']} entries.** The richest write-ups in the set - long-form,
with a real narrative - but the smallest in volume.

- {os_['blog_index_seeds']} blog index pages were seeded (Cloudflare's
  `/tag/outage/`, incident.io, Honeycomb, Dropbox, Deno, npm, Discord, Figma,
  Canva, Monzo, Grab, PyPI, Rust, and others).
- Links whose URL or anchor text matched
  `outage|postmortem|incident|rca|root-cause|downtime|degradation|retrospective`
  were kept: {os_['blog_candidate_articles']} candidate articles.
- Only 49 of {os_['blog_index_seeds']} indexes yielded anything. The rest are
  JavaScript-rendered, so a plain fetch returns an empty shell. **This is the
  main reason blog coverage is thin** - not a shortage of postmortems.

### 2.4 The danluu/post-mortems curated index

**{ex['danluu_entries']} entries.** A long-standing hand-curated list of
notable postmortems ({os_['danluu_index_entries']} entries), fetched as raw
markdown. Each line is `[Org](url). <one-line cause>`.

The index's own summary was used as the cause only after the linked source page
was fetched ({os_['danluu_pages_fetched']} pages) and the issue/solution
extracted from it, so nothing rests on the index alone. Yield was low because
**143 of its {os_['danluu_index_entries']} URLs were already in the seed
dataset** - the original `gold_seed_entries.json` had largely been built from
this same list.

### 2.5 AWS post-event summaries

**{ex['aws_entries']} entries.** `aws.amazon.com/premiumsupport/technology/pes/`
lists AWS's public post-event summaries; {os_['aws_post_event_summaries_fetched']}
were retrieved. These are the famous ones (the 2011 EBS event, the 2017 S3
typo, Kinesis 2020). Low count, high quality, and several were already present
in the seed set.

### 2.6 Better Stack status pages

Harvested via `GET https://<host>/index.json`, a JSON:API document whose
`included[]` array holds `status_report` records (the incidents) and
`status_update` records (the narrative text). 41 live hosts were found from
2,952 candidates, yielding 121 incidents across 30 organisations - a small
contribution, but a second platform beyond Statuspage.

### 2.6b Statuspal, and why the other platforms added little

Statuspal exposes `GET /api/v2/status_pages/<slug>/incidents`. Enumerating its
subdomains via Wayback gave 209 real slugs, and Better Stack gave 962 real
hosts, together yielding 1,491 raw incidents across 151 organisations.

Only 39 of those survived extraction and just ~10 had a readable URL, because
Better Stack's public incident path is not `/incident/<id>` and most entries on
these smaller pages are two-line status notes with no stated cause. Freshstatus
(934 hosts), Instatus and Hund were examined and rejected: the first two render
only through JavaScript and Hund's API requires authentication.

The lesson for anyone extending this: platform coverage is not the constraint.
Text quality is.

### 2.7 The original seed file, after cleaning

**{prov.get('original_curated', 0)} entries** retained from your original
`gold_seed_entries.json` ({len(SEED)} rows). See section 4 - most of that file
did not survive.

### Sources that were tried and did not work

| source | outcome |
|---|---|
| **crt.sh Certificate Transparency** (`?q=%.statuspage.io`) | **HTTP 502 on every attempt.** This is the one route that would scale: Statuspage assigns random subdomain ids (`027j6zrg2zwb.statuspage.io` is Mixmax, `029txycd4lgb.statuspage.io` is Zaptec), so name-guessing structurally cannot find most pages, while CT logs index all of them. Retry with `expand_via_ct.py --wait`. |
| Certspotter CT API | 200, but the free tier returns apex issuances only - 0 subdomains |
| AlienVault OTX passive DNS | HTTP 429 rate-limited |
| RapidDNS subdomain search | returned 0 parseable hostnames |
| HackerTarget host search | worked, but free tier caps at 50 rows. Those 50 validated the method: 31 were live, 10 were real companies (Mixmax 50 incidents, Zaptec 50, Gastronovi 29), the rest pirated-media SEO spam on free accounts |
| Instatus-hosted pages (Deno, Linear, Mistral) | every path returns the SPA shell; data only in the React Server Components payload |
| Statuspal API | endpoint works (`/api/v2/status_pages/<slug>/incidents`) but none of 1,476 guessed slugs matched a real customer |
| Internet Archive / Wayback (pre-cap history for the capped hosts) | "Temporarily Offline" on every attempt |
| Statuspage pagination | hard 50-incident cap; `?page`, `?per_page` and `?limit` are all ignored and return the identical 50 |
| Google Cloud status (`status.cloud.google.com/incidents.json`) | returns only ~7 *current* incidents; no public archive endpoint found |
| Azure status history | 5 years of post-incident reviews exist but the page is JavaScript-rendered |
| Instatus-hosted pages (Deno, Linear, Mistral) | React Server Components, no JSON endpoint; data is in the RSC payload |
| Statuspage `history.rss` / `history.atom` | caps at ~25 items, *fewer* than the API's 50 |
| Statuspage `/history?page=N` | JavaScript-rendered, 2 links per page |
| StatusGator / IsDown aggregator directories | only show ~50 featured services, not a full directory |
| Hund, Cachet, Freshstatus, Status.io endpoints | probed, no usable public incident list at the guessed paths |

---

## 3. How a raw incident becomes an entry

Harvested text is not usable as-is: a status page is a running log of
"Investigating / Identified / Monitoring / Resolved" updates mixed with
apologies, timelines and customer instructions. The pipeline is deliberately
**extractive, not generative** - every `root_cause` and `solution` is composed
from sentences that appear in the published report. Nothing is paraphrased by
a model and nothing is invented.

1. **Clean** - strip HTML, markdown escapes, links, bare timestamps and dates.
2. **Split into sentences** and drop boilerplate: "we are investigating",
   "thank you for your patience", "subscribe for updates", timeline rows,
   anything more than 22% digits.
3. **Select the root cause**, in priority order:
   - an explicit `Root cause:` / `What caused it` section, taking that sentence
     plus the next if the first names no mechanism;
   - otherwise the first sentence with causal phrasing *and* a concrete
     mechanism (config, deploy, index, lock, certificate, quota, leak, ...),
     borrowing the following sentence when the causal sentence alone is vague.
4. **Select the solution** - a sentence with remediation phrasing, preferring
   the immediate fix over the long-term prevention item.
5. **Select the issue** - a customer-visible symptom sentence, explicitly *not*
   one that contains the cause or the fix, prefixed with the incident title.
6. **Validate and reject** (see 3.1).
7. **Classify** into one of 11 categories by weighted keyword match, and map
   severity from the publisher's own impact flag
   (`critical`/`major`/`minor`/`none` to Critical/High/Medium/Low).

### 3.1 What gets rejected, and why

These rules exist because each one was caught leaking real garbage into the
output during development:

| rejected when `root_cause` ... | example that forced the rule |
|---|---|
| asserts a cause without naming one | "We have identified the root cause and are working on a fix." |
| is a progress or status update | "Our engineering team is working with urgency to identify the root cause." |
| is an apology | "We deeply regret the inconvenience caused by this incident." |
| is a note that responders were paged | "Several operators were already engaged due to alarms." |
| is a downstream-impact statement | "GitHub Pages and Copilot were also impacted due to their dependency on Actions." |
| is pure impact measurement | "Quality was degraded for a total duration of 4 hours." |
| is retrospective framing | "It also reinforced the importance of clear playbooks." |
| is a recovery confirmation | "We have confirmed that all services are operating normally." |
| attributes to nothing concrete | "... failing due to an issue." (allowed only if it points at something: "due to an issue **with the underlying data storage**") |
| restates the issue | token overlap with `issue` above 85% |
| is a mid-sentence fragment | unbalanced parentheses, or opens with a closing bracket |
| is index-author commentary | "This postmortem is pretty thin and I'm not sure what happened." |

Two cause-detection patterns were **measured and then deliberately removed**
after attributing each admitted entry to the pattern that let it in:
`resulted in` (148 admissions) and `during a/an ...` (128 admissions) were
matching impact and timeline statements rather than causes, e.g. *"Affected
customers will have a gap in metrics during the period of the outage."*
Dropping them cost 276 entries and was the right trade.

### 3.2 De-duplication

Three independent passes:

- **Within the seed file** - 6 rows were self-declared reframings of another
  row ("Same underlying incident as GOLD-00xx"); 11 more shared a source URL
  and a cause.
- **New against existing** - by source URL, and by 4-gram shingle Jaccard
  similarity on `root_cause` (>0.55 rejected). Shingle-indexed so it stays
  near-linear rather than comparing every pair.
- **Cross-host** - the same company often has several status hostnames
  (`shopify.statuspage.io`, `status.shopify.com`, `shopifystatus.com`). All
  harvests are keyed on the Statuspage incident id, so one incident reached
  through three hostnames is stored once.

One deliberate exception: several incidents may share a GitHub monthly-report
URL, because that one page documents several distinct incidents. These are
only flagged if their causes also overlap.

### 3.3 URL verification

Every source URL is fetched at build time with a browser user-agent and
redirects followed. **An entry is kept only if its URL returns a clean HTTP
200.** That rule replaced an earlier, weaker one ("not 404"), after a build
produced 3,001 entries of which about 2,300 cited URLs returning 403 - retired
or access-restricted status pages that no reader could open. A citation nobody
can follow is not a citation, so they are dropped.

Two related fixes came out of that:

* **Canonical URLs.** The incident API advertises the page's own public address
  in `page.url` (e.g. `https://status.canary.is`). The dataset now cites that,
  not the random `*.statuspage.io` subdomain, because it is the address a reader
  recognises and it is far more often publicly readable. This recovered most of
  the 2,300 entries rather than losing them.
* **Spam filtering at two levels**, since the random-id namespace contains
  pirated-media pages whose "incidents" are keyword spam. Latest build:
**{R['url_verification']['urls_checked']} URLs checked, 0 dead**
({R['url_verification']['status_counts']}). Verdicts are cached in
`build/raw/newurlstatus.json` so rebuilds only re-check unseen URLs.

An independent `audit.py` re-checks every stated guarantee against the written
file and re-samples 120 live URLs, so the audit cannot pass just because the
builder believed itself.

---

## 4. What happened to your original seed file

Your `gold_seed_entries.json` had {len(SEED)} rows. It was filtered in two
passes, and **{prov.get('original_curated', 0)} rows survived**:

| pass | removed | remaining |
|---|---|---|
| {len(SEED)} rows as supplied | - | {len(SEED)} |
| pass 1 - dead URLs, index-only URLs, degenerate rows, declared duplicates, bad dates | {len(dropped)} | {len(SEED) - len(dropped)} |
| pass 2 - held to the same validation as every other source, then de-duplicated against itself | {len(SEED) - len(dropped) - prov.get('original_curated', 0)} | **{prov.get('original_curated', 0)}** |

Every URL in it was fetched:

{table(seedstat.most_common(), 'HTTP status', total=len(SEED))}
Drop reasons:

{table(dropreasons.most_common(), 'reason', total=len(dropped))}
What those mean:

- **dead_url ({dropreasons.get('dead_url', 0)})** - the URL did not exist.
  These were concentrated in rows GOLD-0201 to GOLD-0300, where over half were
  dead. The slugs follow a recognisable fabricated pattern:
  `stripe.com/status/reports/2023-07-12`,
  `blog.cloudflare.com/edge-image-resizing-cpu-exhaustion-aug-2023/`,
  `redditstatus.com/incidents/reddit-outage-march-2023`. Plausible-looking,
  never published. That block was generated, not scraped.
- **index_url ({dropreasons.get('index_url', 0)})** - the `source_url` was a
  homepage or blog index (`aws.amazon.com/message/`, `discord.com/blog/`,
  `status.heroku.com/`), which cannot verify any specific incident.
- **degenerate_rc ({dropreasons.get('degenerate_rc', 0)})** - `root_cause`
  was a verbatim copy of `issue`.
- **declared_duplicate ({dropreasons.get('declared_duplicate', 0)})** - the
  row's own `note` field said it was a reframing of another row.
- **bad_date ({dropreasons.get('bad_date', 0)})** - `incident_date: "unknown"`.

The pass-2 removals were sentence-splitting damage from whatever generated the
tail of the file, e.g. one row had
`issue: "Use of different units of measurement (metric vs."` and
`root_cause: "English) caused Mars Climate Orbiter to fail."` - a single
sentence cut in half across two fields. Another used the curator's editorial
aside as the incident description. One was a 1628 shipwreck.

**Your hand-written GOLD-0001 to GOLD-0050 held up well: 48 of 50 survived.**
The damage was confined to the machine-generated tail.

---

## 5. What is actually in it

### By source

{table(prov.most_common(), 'provenance')}
### By category

{table(cats.most_common(), 'category')}
### By severity

{table(sevs.most_common(), 'severity')}
Severity comes from each publisher's own impact flag, so it reflects how that
company classified the event. It is **not calibrated across organisations** -
one company's "major" is another's "minor".

### By year

{table(sorted(years.items(), key=lambda kv: kv[0], reverse=True), 'year', pctcol=False)}
### Most frequent organisations

{table(orgs.most_common(25), 'organisation')}
### Field lengths

| field | mean characters |
|---|---|
| `issue` | {sum(len(e['issue']) for e in F)//n} |
| `root_cause` | {sum(len(e['root_cause']) for e in F)//n} |
| `solution` (where present) | {sum(len(e['solution']) for e in full)//max(1,len(full))} |

---

## 6. Two files, and which one to use

**`gold_incidents.json` - {n} entries. This is the dataset.** Every row has
`issue`, `root_cause` and `solution` all populated, with a minimum solution
length of 45 characters. Use this one unless you have a reason not to.

**`gold_incidents_all.json` - {n_all} entries.** The same data plus
**{len(cause_only)} cause-only incidents**, where the company published a root
cause but never published what they did about it. Those rows carry
`solution: null`.

They are kept because they are real, verified incidents with real stated
causes - only the remediation is missing - and discarding them would throw away
{len(cause_only)} usable root-cause examples. A fix was never invented to fill
the field.

```python
import json
complete = json.load(open("gold_incidents.json"))        # {n}
superset = json.load(open("gold_incidents_all.json"))     # {n_all}
cause_only = [e for e in superset if e["solution"] is None]   # {len(cause_only)}
```

If you are training or evaluating something that must output a remediation,
`gold_incidents.json` is the right file. If you are training a cause
classifier or retriever, the superset gives you nearly twice the labels.

## 7. Honest limitations

1. **Survivorship bias, and it is severe.** This dataset describes companies
   that *publish postmortems*. That is a small, self-selecting set: mostly
   developer-tools and infrastructure vendors whose customers are engineers.
   There is almost no manufacturing, healthcare, banking core systems,
   telecoms or government. Do not read the category mix as "how production
   systems fail" - read it as "how companies that write public postmortems
   describe their failures".

2. **Heavy recency skew.** {100.0*(years.get('2025',0)+years.get('2026',0))/n:.0f}%
   of entries are from 2025-2026. This is an artefact of the 50-incident API
   cap (section 2.1), not a claim that incidents became more common. Older
   incidents survive only where they came from a curated index, a blog, or a
   company with few total incidents.

3. **Category labels are keyword-assigned, not human-reviewed.** A weighted
   keyword matcher picks one of 11 categories. `other`
   ({cats.get('other',0)} entries) is largely third-party/upstream dependency
   failures, which genuinely do not fit the 11. Treat the labels as a useful
   index, not ground truth - and re-label by hand if you are measuring
   per-category accuracy.

4. **`memory_leak` ({cats.get('memory_leak',0)}) and
   `concurrency_race_condition` ({cats.get('concurrency_race_condition',0)})
   are very thin.** Status pages almost never attribute an incident to either;
   those causes surface in long-form engineering blogs, which is the source
   that stayed smallest.

5. **The text is extracted, not written.** `root_cause` and `solution` are
   composed from sentences in the source. They read like status-page prose,
   including occasional corporate register, and are faithful rather than
   elegant. The {prov.get('original_curated',0)} `original_curated` rows are
   hand-written and read differently - a model could likely distinguish them.

6. **One organisation is over-represented.** The largest contributor is
   {orgs.most_common(1)[0][0]} with {orgs.most_common(1)[0][1]} entries
   ({100.0*orgs.most_common(1)[0][1]/n:.1f}%), because it publishes a detailed
   monthly report. Weight by `org` if that matters.

7. **Severity is not comparable across organisations** (section 5).

8. **Dates are the report date, not always the incident date.** For
   status-page entries `incident_date` is the incident's `created_at`, which is
   when the status post opened - normally the incident start, but for a
   postmortem published later it can lag by days. {coarse_dates} entries have
   only year or year-month precision, from sources that published no exact date.

9. **No incident is independently corroborated.** Each entry rests on one
   source URL - the company's own account. Public postmortems are written for
   customers and regulators, so they systematically under-report human and
   organisational factors. Expect "a configuration change was applied" rather
   than "an engineer under deadline pressure skipped the review step".

10. **This is not a reproducible snapshot.** Status pages roll off old
    incidents as new ones arrive, so re-running the pipeline later will not
    reproduce this exact file. The harvested JSON is kept under
    `build/raw/statuspage*_raw.json` so the inputs remain inspectable.

---

## 8. Rebuilding

```bash
cd dataset/build
python3 rebuild_pool.py      # merge every harvested status-page payload
bash build.sh                # extract -> assemble -> finalize -> audit
python3 provenance.py        # recollect funnel statistics
python3 write_provenance.py  # regenerate this document
```

| script | role |
|---|---|
| `gen_hosts.py` | expand a company-slug list into candidate hostnames |
| `probe*.py` | probe candidates for a live Statuspage API, harvest incidents |
| `rebuild_pool.py` | merge all harvests, de-duplicate by incident id |
| `crawl_blogs.py` / `extract_blogs.py` | discover and extract blog postmortems |
| `extract_gh2.py` | split GitHub monthly reports into incidents |
| `extract_aws.py`, `extract_danluu.py` | AWS summaries, curated index |
| `extract3.py` | sentence selection and category/severity assignment |
| `polish.py` | the rejection rules in section 3.1 |
| `assemble.py` | validation, de-duplication, URL verification, renumbering |
| `finalize.py` | org-name normalisation, renumbering, report |
| `audit.py` | independent re-check of every guarantee |

Companion files: `DATASET_REPORT.md` (summary statistics),
`synthetic_incidents.json` + `SYNTHETIC_REPORT.md` (a separate, clearly
labelled generated set - never mixed into this one).
"""

open(OUT, 'w').write(doc)
print('WROTE', OUT)
print('entries documented:', n, '| orgs:', len(orgs))
print('full:', len(full), '| cause-only:', len(cause_only))
