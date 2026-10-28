# Root Cause Analysis assistant

Describe a production issue in plain words and get likely root causes, recommended fixes, and the similar known issues the answer was based on.

## How it works

1. **Search.** The description is rewritten into a clean symptom, then matched against 2,856 past production incidents using both embeddings and keyword search. A model reranks the candidates and the top five are kept, at most two per organisation.
2. **Ground.** If the best match is relevant enough (4 out of 10 or more), those incidents are passed to the model as evidence. The response is tagged `RAG` and each hypothesis cites the incidents that support it.
3. **Fall back.** Otherwise the model reasons without past incidents and the response is tagged `LLM_ONLY`.

## Project layout

| Path | What it is |
|---|---|
| `Backend/` | FastAPI service. `main.py` is the API; `rag/` holds retrieval, reranking and analysis. |
| `Backend/index/` | The prebuilt search index. Rebuild it with `python -m rag.build_index`. |
| `Backend/data/` | The cleaned incident set, embeddings and evaluation results. |
| `Backend/tests/` | Offline unit tests: `python -m unittest tests.test_rag`. |
| `Frontend/` | React + Vite analysis app. |
| `Landing/` | Public site (Next.js, Clerk sign-in): landing page, dashboard, privacy and terms. See its own README. |
| `dataset/` | The incident datasets and the scripts that built them. |

`Backend/rca_engine.py` and `Backend/dataset/production_issues_75.json` are the earlier, smaller engine. The API no longer uses them.

## Running it

You need Python 3.9+, Node 20+, and an OpenAI API key.

**Backend**

```bash
cd Backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
echo "OPENAI_API_KEY=your-key" > .env
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

The search index ships with the repository, so startup makes no API calls. By default the model is `gpt-4.1-mini`; set `RCA_LLM_MODEL`, or `RCA_LLM_BASE_URL` for a local OpenAI-compatible server, in `Backend/.env` to change that. Embeddings always use OpenAI.

**Frontend**

```bash
cd Frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. The app expects the API at `http://127.0.0.1:8000`; to point it elsewhere, set `VITE_API_URL` in `Frontend/.env.local`.

## API

`POST /analyze` with `{"issue": "Redis out of memory errors"}` returns, among other fields:

```json
{
  "mode": "RAG",
  "analysis": {
    "summary": "...",
    "category": "database_issue",
    "severity": "High",
    "hypotheses": [{ "cause": "...", "likelihood": 0.6, "evidence_ids": ["GOLD-0621"], "reasoning": "..." }],
    "first_checks": ["..."],
    "fix_steps": ["..."],
    "root_causes": ["..."],
    "solutions": ["..."],
    "confidence": 0.6,
    "explanation": "..."
  },
  "similar_incidents": [{ "id": "GOLD-0621", "org": "...", "issue": "...", "root_cause": "...", "solution": "...", "source_url": "..." }],
  "similar_issues": [{ "content": "...", "similarity_score": 1.0 }]
}
```

`root_causes`, `solutions`, `confidence`, `explanation` and `similar_issues` are the simpler fields the analysis app reads. An answer takes roughly 6 to 9 seconds. `GET /` reports how many incidents are indexed. Interactive docs are at http://127.0.0.1:8000/docs.

## Datasets

- `gold_incidents.json`: 2,856 real production incidents, each with a source URL. See `DATASET_REPORT.md`.
- `synthetic_incidents.json`: 1,383 generated incidents in the same schema, marked `data_type: "synthetic"`. See `SYNTHETIC_REPORT.md`.

The raw scraped pages the gold set was extracted from are not included in this repository because of their size.
