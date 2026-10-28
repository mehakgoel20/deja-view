"""Write the final dataset. Keeps every entry that passed quality checks."""
import json, re
from collections import Counter

OUT = '../gold_incidents.json'            # complete entries only
OUT_ALL = '../gold_incidents_all.json'    # superset, including cause-only
REPORT = '../DATASET_REPORT.md'

# host-derived org slugs that need their real casing
ORGFIX = {
    'Xmatters': 'xMatters', 'Currencycloud': 'Currencycloud', 'Imgix': 'imgix',
    'Npm': 'npm', 'Ngrok': 'ngrok', 'Jfrog': 'JFrog', 'Clickup': 'ClickUp',
    'Livekit': 'LiveKit', 'Assemblyai': 'AssemblyAI', 'Elevenlabs': 'ElevenLabs',
    'Openai': 'OpenAI', 'Hubspot': 'HubSpot', 'Planetscale': 'PlanetScale',
    'Clickhouse': 'ClickHouse', 'Influxdata': 'InfluxData', 'Newrelic': 'New Relic',
    'Pagerduty': 'PagerDuty', 'Launchdarkly': 'LaunchDarkly', 'Sendgrid': 'SendGrid',
    'Messagebird': 'MessageBird', 'Gocardless': 'GoCardless', 'Bigcommerce': 'BigCommerce',
    'Cockroachlabs': 'CockroachDB', 'Digitalocean': 'DigitalOcean', 'Mongodb': 'MongoDB',
    'Posthog': 'PostHog', 'Browserstack': 'BrowserStack', 'Lambdatest': 'LambdaTest',
    'Saucelabs': 'Sauce Labs', 'Stackblitz': 'StackBlitz', 'Codesandbox': 'CodeSandbox',
    'Crowdstrike': 'CrowdStrike', 'Sentinelone': 'SentinelOne', 'Rabbitmq': 'RabbitMQ',
    'Mariadb': 'MariaDB', 'Lemonsqueezy': 'Lemon Squeezy', 'Crunchydata': 'Crunchy Data',
    'Bamboohr': 'BambooHR', 'Dropboxsign': 'Dropbox Sign', 'Opentable': 'OpenTable',
    'Sevenrooms': 'SevenRooms', 'Seatgeek': 'SeatGeek', 'Stubhub': 'StubHub',
    'Soundcloud': 'SoundCloud', 'Hbomax': 'HBO Max', 'Riotgames': 'Riot Games',
    'Epicgames': 'Epic Games', 'Justeat': 'Just Eat', 'Gopuff': 'Gopuff',
    'Keeptruckin': 'KeepTruckin', 'Shipstation': 'ShipStation',
    'Shippingeasy': 'ShippingEasy', 'Easypost': 'EasyPost', 'Fourkites': 'FourKites',
    'Project44': 'project44', 'Goodrx': 'GoodRx', 'Zocdoc': 'Zocdoc',
    'Healthequity': 'HealthEquity', 'Changehealthcare': 'Change Healthcare',
    'Particlehealth': 'Particle Health', 'Truepill': 'Truepill',
    'Weightwatchers': 'WeightWatchers', 'Khanacademy': 'Khan Academy',
    'Coursehero': 'Course Hero', 'Linkedinlearning': 'LinkedIn Learning',
    'Datacamp': 'DataCamp', 'Pluralsight': 'Pluralsight', 'Oysterhr': 'Oyster HR',
    'Velocityglobal': 'Velocity Global', 'Culturamp': 'Culture Amp',
    'Goodhire': 'GoodHire', 'Mycase': 'MyCase', 'Smokeball': 'Smokeball',
    'Lexisnexis': 'LexisNexis', 'Wealthfront': 'Wealthfront', 'Tastytrade': 'tastytrade',
    'Iexcloud': 'IEX Cloud', 'Twelvedata': 'Twelve Data', 'Finnhub': 'Finnhub',
    'Drivewealth': 'DriveWealth', 'Vacasa': 'Vacasa', 'Britishairways': 'British Airways',
    'Airfrance': 'Air France', 'Qatarairways': 'Qatar Airways', 'Easyjet': 'easyJet',
    'Wizzair': 'Wizz Air', 'Doordash': 'DoorDash', 'Ubereats': 'Uber Eats',
    'Grubhub': 'Grubhub', 'Jellyfin': 'Jellyfin', 'Lucidchart': 'Lucidchart',
    'Excalidraw': 'Excalidraw', 'Whimsical': 'Whimsical', 'Thirtymadison': 'Thirty Madison',
    'Collectivehealth': 'Collective Health', 'Allscripts': 'Allscripts',
    'Athenahealth': 'athenahealth', 'Nextgen': 'NextGen', 'Doctorondemand': 'Doctor on Demand',
    'Knowbe4': 'KnowBe4', 'Movableink': 'MovableInk', 'Pubnub': 'PubNub',
    'Neo4j': 'Neo4j', 'Lucidworks': 'Lucidworks', 'Kustomer': 'Kustomer',
    'Smartsheet': 'Smartsheet', 'Socure': 'Socure', 'Twingate': 'Twingate',
    'Dnsmadeeasy': 'DNS Made Easy', 'Nsone': 'NS1', 'Nextdns': 'NextDNS',
    'Dnsimple': 'DNSimple', 'Dnsfilter': 'DNSFilter', 'Controld': 'ControlD',
    'Cloudns': 'ClouDNS', 'Luadns': 'LuaDNS', 'Noip': 'No-IP',
    'Openfga': 'OpenFGA', 'Fusionauth': 'FusionAuth', 'Zitadel': 'ZITADEL',
    'Authentik': 'authentik', 'Propelauth': 'PropelAuth', 'Scalekit': 'Scalekit',
    'Fleetdm': 'Fleet', 'Ninjaone': 'NinjaOne', 'Connectwise': 'ConnectWise',
    'Arcticwolf': 'Arctic Wolf', 'Abnormalsecurity': 'Abnormal Security',
    'Ironscales': 'IRONSCALES', 'Hetznercloud': 'Hetzner', 'Oracleoci': 'Oracle Cloud',
    'Nhncloud': 'NHN Cloud', 'Qingcloud': 'QingCloud', 'Ucloud': 'UCloud',
    'Tencentcloud': 'Tencent Cloud', 'Huaweicloud': 'Huawei Cloud',
    'Volcengine': 'Volcengine', 'Edgenext': 'EdgeNext', 'Gcore': 'Gcore',
    'Logzio': 'Logz.io', 'Coralogix': 'Coralogix', 'Mezmo': 'Mezmo',
    'Betterstack': 'Better Stack', 'Baselime': 'Baselime', 'Debugbear': 'DebugBear',
    'Speedcurve': 'SpeedCurve', 'Site24x7': 'Site24x7', 'Solarwinds': 'SolarWinds',
    'Thousandeyes': 'ThousandEyes', 'Catchpoint': 'Catchpoint',
    'Splitio': 'Split', 'Opsgenie': 'Opsgenie', 'Routific': 'Routific',
    'Syncplicity': 'Syncplicity', 'Jumpcloud': 'JumpCloud', 'Dyte': 'Dyte',
    'Harness': 'Harness', 'Hydrow': 'Hydrow', 'Alpaca': 'Alpaca',
    'Clickhousecloud': 'ClickHouse Cloud', 'Confluentcloud': 'Confluent Cloud',
    'Temporalcloud': 'Temporal Cloud', 'Upstashkafka': 'Upstash',
    'Dbtlabs': 'dbt Labs', 'Montecarlo': 'Monte Carlo', 'Openmetadata': 'OpenMetadata',
    'Rudderstack': 'RudderStack', 'Growthbook': 'GrowthBook', 'Devcycle': 'DevCycle',
    'Vertexinc': 'Vertex', 'Highradius': 'HighRadius', 'Treasuryprime': 'Treasury Prime',
}


def main():
    cand = json.load(open('final_candidate.json'))
    print('candidates:', len(cand))

    for e in cand:
        e['org'] = ORGFIX.get(e['org'], e['org'])
        if not e.get('note'):
            e.pop('note', None)

    cand.sort(key=lambda x: (0 if x['provenance'] == 'original_curated' else 1,
                             str(x['incident_date']), str(x['org'])))

    # The shipped dataset holds only complete entries: issue, root_cause and a
    # published solution. Entries where the publisher stated a cause but never a
    # remediation are real incidents, so they are preserved in the superset file
    # rather than discarded.
    allrows = [dict(e) for e in cand]
    for i, e in enumerate(allrows, 1):
        e['id'] = f'GOLD-{i:04d}'
    json.dump(allrows, open(OUT_ALL, 'w'), indent=2)

    cand = [e for e in cand if e.get('solution') is not None]
    for i, e in enumerate(cand, 1):
        e['id'] = f'GOLD-{i:04d}'

    json.dump(cand, open(OUT, 'w'), indent=2)
    print(f'superset (incl. cause-only): {len(allrows)} -> {OUT_ALL}')
    print(f'complete entries only      : {len(cand)} -> {OUT}')

    n_all = len(allrows)
    n_all_minus_n = n_all - len(cand)
    cats = Counter(e['category'] for e in cand)
    sevs = Counter(e['severity'] for e in cand)
    provs = Counter(e['provenance'] for e in cand)
    orgs = Counter(e['org'] for e in cand)
    yrs = Counter(str(e['incident_date'])[:4] for e in cand)
    dfmt = Counter('YYYY-MM-DD' if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(e['incident_date']))
                   else 'YYYY-MM' if re.fullmatch(r'\d{4}-\d{2}', str(e['incident_date']))
                   else 'YYYY' for e in cand)
    n = len(cand)

    def tbl(c, head, pct=False):
        rows = '\n'.join(
            f'| {k} | {v} |' if not pct else f'| {k} | {v} | {100.0*v/n:.1f}% |'
            for k, v in c.most_common())
        hdr = (f'| {head} | count |\n|---|---|' if not pct
               else f'| {head} | count | share |\n|---|---|---|')
        return f'{hdr}\n{rows}\n'

    with open(REPORT, 'w') as f:
        f.write(f"""# Gold RCA incident dataset

**{n} real production incidents.** Every entry has a live, incident-specific
source URL that returned a non-404 status at build time.

## Schema

| field | notes |
|---|---|
| `id` | `GOLD-0001` .. `GOLD-{n:04d}`, renumbered on every build |
| `issue` | the customer-visible symptom |
| `root_cause` | the mechanism that caused it |
| `solution` | what was done to resolve or mitigate it (always populated in this file) |
| `severity` | `Critical` / `High` / `Medium` / `Low` |
| `category` | one of 11 values, see below |
| `org` | the organisation that published the report |
| `source_url` | link to the specific incident report |
| `incident_date` | `YYYY`, `YYYY-MM` or `YYYY-MM-DD` |
| `data_type` | always `real` |
| `provenance` | how the entry was built, see below |
| `note` | optional caveat; present only on some curated entries |

## Provenance

{tbl(provs, 'source', pct=True)}
- `original_curated` — hand-written entries retained from the previous
  `gold_seed_entries.json`, after cleaning.
- `statuspage_postmortem` — postmortem / resolution text published on company
  status pages, read through the Statuspage v2 API.
- `github_availability_report` — individual incidents inside GitHub's monthly
  availability reports.
- `aws_post_event_summary` — AWS post-event summaries.
- `curated_index+source_page` — the danluu/post-mortems index, with cause text
  cross-checked against the original write-up.

## Completeness

Every entry in this file is complete: `issue`, `root_cause` and `solution` are
all populated. Entries where the publisher stated a cause but never published a
remediation are **not** in this file; they are kept in
`gold_incidents_all.json` ({n_all} rows total, {n_all} - {n} = {n_all_minus_n}
cause-only) so nothing real is discarded.

## Category

{tbl(cats, 'category', pct=True)}
## Severity

{tbl(sevs, 'severity', pct=True)}
## Date coverage

{tbl(dfmt, 'date precision')}
{tbl(yrs, 'year')}
## Organisations

{len(orgs)} distinct organisations. Most frequent:

{tbl(Counter(dict(orgs.most_common(25))), 'org', pct=True)}
## What is guaranteed

Every entry:

1. has a `source_url` that resolved (non-404) at build time;
2. has an `incident_date` matching `YYYY`, `YYYY-MM` or `YYYY-MM-DD`;
3. has a `root_cause` of at least 45 characters and an `issue` of at least 25,
   mutually distinct — no entry restates its symptom as its cause;
4. has a `solution` of at least 45 characters. A fix is never invented to fill
   the field, so incidents whose publisher never stated a remediation are held
   in `gold_incidents_all.json` instead of this file;
5. is deduplicated against every other entry by source URL and by root-cause
   shingle similarity (Jaccard > 0.55 rejected);
6. states an actual causal mechanism. Reports that only assert one
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
- `memory_leak` ({cats['memory_leak']}) and `concurrency_race_condition`
  ({cats['concurrency_race_condition']}) stay under-represented. Status-page
  postmortems rarely attribute an incident to either; the examples that exist
  come mostly from long-form engineering blogs.
- GitHub is the largest single contributor ({orgs['GitHub']} entries,
  {100.0*orgs['GitHub']/n:.1f}%) because it publishes a detailed monthly
  availability report. Weight by `org` if that concentration matters for your
  evaluation.
- Statuspage's public API exposes only each company's ~50 most recent
  incidents, so coverage skews to recent years.
- `severity` for status-page entries is derived from the publisher's own impact
  flag (`critical`/`major`/`minor`/`none`), not from a uniform rubric, so it is
  not strictly comparable across organisations.
""")

    print('WROTE', OUT, 'and', REPORT)
    print('TOTAL:', n)
    print('categories:', cats.most_common())
    print('provenance:', provs.most_common())
    print('orgs:', len(orgs), '| top:', orgs.most_common(6))
    print('date precision:', dfmt.most_common())


if __name__ == '__main__':
    main()
