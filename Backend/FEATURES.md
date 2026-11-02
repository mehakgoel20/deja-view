# Investigation features

Seven capabilities layered on the retrieval engine. Each is independent: with
nothing configured the system behaves exactly as it did before, and every
feature reports what evidence it was missing rather than guessing.

| # | Feature | Module | Needs |
|---|---|---|---|
| 1 | Live observability | `observability/` | Prometheus / Loki / Grafana / Tempo (all optional) |
| 2 | Multi-agent RCA | `agents/` | nothing (LLM optional) |
| 3 | Service dependency graph | `graph/` | a topology file (sample included) |
| 4 | Causal analysis | `causal/` | nothing |
| 5 | Timeline reconstruction | `timeline/` | timestamped signals |
| 6 | AI remediation | `remediation/` | nothing (LLM optional) |
| 7 | Evaluation & benchmarking | `benchmark/` | the built index |

Run the offline tests for all of it:

```bash
python -m unittest tests.test_features -v      # 43 tests, no network
```

---

## 1. Live observability

Pulls real operational evidence for the window around an incident, so the
analysis rests on what the system did rather than only on the description.

```bash
RCA_PROMETHEUS_URL=http://localhost:9090
RCA_LOKI_URL=http://localhost:3100
RCA_GRAFANA_URL=http://localhost:3000
RCA_GRAFANA_TOKEN=glsa_...
RCA_TEMPO_URL=http://localhost:3200       # or RCA_JAEGER_URL
```

```python
from observability import TimeWindow, collect_signals, correlate
window = TimeWindow.last(minutes=90)
signals, status = collect_signals(window, {"service": "checkout"})
correlate(signals, window)["summary"]
```

Each backend becomes a list of `Signal` objects, so everything downstream is
source-agnostic. Design notes:

- **Metrics** are not dumped raw. A series is reported only when its peak
  exceeds its own median by `RCA_PROM_SPIKE_RATIO` (default 3x) — median, not
  mean, so one large spike cannot hide itself.
- **Logs** are normalised and clustered before they go anywhere near a model.
  A thousand near-identical stack traces is one fact, not a thousand; numbers,
  UUIDs, IPs, paths and quoted values collapse to placeholders.
- **Grafana annotations** are where most teams already record deploys, which
  makes them the cheapest reliable answer to "what changed at 13:42".
- **Traces** are the only source that gives *direction* — which service called
  which when it failed — and that feeds the dependency and causal layers.

Nothing configured is not an error: `GET /observability/status` tells you which
backends are live and what to set.

## 2. Multi-agent RCA

Specialists gather evidence concurrently, then an investigator judges it.

```python
from agents import investigate, render
report = investigate("Checkout 500s since the 13:00 release", use_llm=False)
print(render(report))
```

| Stage | Agents | Job |
|---|---|---|
| 1 (parallel) | `log_analysis`, `metrics_analysis`, `historical_incident`, `dependency_analysis` | gather evidence in one narrow domain each |
| 2 | `root_cause_investigator` | weigh everything and commit to ranked hypotheses |
| 3 | remediation | propose fixes once a cause exists |

Every agent does as much as it can deterministically before using the LLM, so
`use_llm=False` gives a complete investigation with no API calls — which is how
the tests run. An agent that fails or has no data returns a `gap` finding; the
investigation continues and reports the gap instead of silently proceeding as
if the evidence existed.

## 3. Service dependency graph

```python
from graph import ServiceGraph
g = ServiceGraph.from_file("data/topology.yaml")
g.blast_radius("redis")          # who breaks if redis does
g.rank_suspects(["checkout", "catalog"])   # what explains both at once
```

Edge direction is `A -> B` meaning *A depends on B*, so failure propagates
backwards along edges. That matters: when Redis fails the question is who calls
Redis, not what Redis calls.

- Impact decays along the path and by dependency type — a synchronous caller is
  hit hard, an optional async hop three levels away barely notices.
- `rank_suspects` is the useful query when several services fail together: a
  shared dependency explaining all of them beats a coincidence in each.

NetworkX by default (no infrastructure). `graph/neo4j_store.py` mirrors the same
API into Neo4j for teams already running it. A sample topology ships in
`data/topology.yaml`; point `RCA_TOPOLOGY_PATH` at your own.

## 4. Causal analysis

Goes past "these happened together" to "this caused that".

```python
from causal import analyse_causally
res = analyse_causally(text=issue, signals=signals, service_graph=g,
                       neighbours=[(incident_id, root_cause_text)])
res["hypotheses"][0]["contradictions"]
```

The graph is built **deterministically**, from three link types ordered by
strength: stated mechanism > known precedent > dependency path > temporal order
> co-occurrence. The LLM is then handed a structure it did not invent and asked
to judge it — asking a model to both produce and grade its own causal chain is
how confident nonsense gets made.

Two things this gives that similarity search cannot:

- **Symptom vs root cause.** Only nodes typed as symptoms are effects to be
  explained. A mechanism with a trigger upstream of it is still the thing you
  report as the cause.
- **Contradictions subtract.** A change that happened *after* the symptom it
  supposedly caused is marked wrong-order and demoted to zero. So is a cause
  that explains none of the observed symptoms, or one that merely restates a
  symptom. Similar incidents routinely have different causes, so penalising
  unsupportable claims matters more than rewarding plausible ones.

## 5. Timeline reconstruction

```python
from timeline import reconstruct, render
tl = reconstruct(signals, window, reported_at=when, reported_text=issue)
tl["ordering"]["verdict"]
```

Merges deploys, spikes, log bursts, restarts and recovery into one ordered
narrative and labels the phases: `pre-incident`, `trigger`, `onset`, `impact`,
`recovery`.

`what_happened_first` is deliberately conservative — it nominates a trigger only
when a change precedes the first symptom inside a plausible window, and says so
plainly when no change precedes it. It also reports **detection delay**: the gap
between first symptom and first human report, often the most actionable number
in a postmortem.

## 6. AI remediation

```python
from remediation import build_plan, approve
plan = build_plan(issue, cause=cause, neighbours=nb)
approve(plan, 0, approver="you", decision="approved")
```

Four horizons: `immediate` (stop the bleeding), `corrective` (fix the defect),
`preventive` (stop the class recurring), `configuration` (a specific setting and
value). Each action carries a `risk` rating and its `source`.

Fixes that actually resolved similar incidents come first, cited by incident id
— stronger evidence than a model's suggestion. Code locations are only named
when they appear in the evidence; model-suggested ones are labelled as such so a
reviewer can tell them apart.

**Nothing executes.** Every action carries `requires_approval: true`, the module
exposes no apply path, and `approve()` only records a human decision for audit.
An RCA tool that can restart production on its own inference is a worse outage
waiting to happen.

## 7. Evaluation & benchmarking

```bash
python -m benchmark.run --limit 50
python -m benchmark.run --report
```

| pipeline | retrieval | rerank | agents |
|---|---|---|---|
| `basic` | dense only | no | no |
| `hybrid` | dense + BM25 (RRF) | yes | no |
| `agentic` | dense + BM25 (RRF) | yes | yes |

Adds the IR metrics the project lacked — **Recall@K, Precision@K, MRR, NDCG**
with graded relevance — alongside root-cause accuracy, citation correctness,
hallucination rate, recommendation usefulness and p50/p95 latency.

Measurement choices worth knowing:

- **Relevance** = the retrieved incident shares the held-out incident's
  category, the same proxy the project already used. Swap in a stricter
  definition via `relevance_fn` without touching the metrics.
- **Root-cause accuracy** is token-F1 ≥ 0.30 against the published cause, not
  exact match: "the pool hit its ceiling" and "connection pool exhaustion" are
  the same answer.
- **Hallucination** is split in two, because they need different fixes:
  *invented citations* are a grounding failure, *uncited claims* a discipline
  failure.
- Each incident is **excluded from its own retrieval**, or the answer is in the
  context and every number is meaningless.

`benchmark.metrics` is pure and importable without faiss or an API key.

---

## API

| Method | Path | Feature |
|---|---|---|
| GET | `/observability/status` | 1 |
| GET | `/observability/signals` | 1 |
| POST | `/investigate` | 2 |
| GET | `/graph`, `/graph/blast-radius`, `/graph/suspects` | 3 |
| POST | `/causal` | 4 |
| POST | `/timeline` | 5 |
| POST | `/remediation`, `/remediation/approve` | 6 |
| GET | `/benchmark` | 7 |

`POST /analyze` is unchanged, so the existing frontend keeps working.

```bash
curl -s localhost:8000/investigate -H 'content-type: application/json' -d '{
  "issue": "Checkout 500s and the postgres pool is exhausted since the 13:00 deploy",
  "use_llm": false, "collect_live": false
}' | jq '.top_cause, .evidence_gaps[].statement'
```

## Configuration

| Variable | Purpose |
|---|---|
| `RCA_PROMETHEUS_URL` | enable metrics |
| `RCA_PROM_QUERIES` | JSON `{label: promql}` to override the default queries |
| `RCA_PROM_SPIKE_RATIO` | spike threshold vs median (default 3.0) |
| `RCA_LOKI_URL`, `RCA_LOKI_SELECTOR` | enable logs, narrow the stream |
| `RCA_GRAFANA_URL`, `RCA_GRAFANA_TOKEN` | enable annotations / deploy markers |
| `RCA_TEMPO_URL` or `RCA_JAEGER_URL` | enable traces |
| `RCA_TOPOLOGY_PATH` | service topology (YAML or JSON) |
| `RCA_NEO4J_URI`, `RCA_NEO4J_USER`, `RCA_NEO4J_PASSWORD` | optional Neo4j backend |
