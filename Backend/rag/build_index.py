"""Step 3: embed incidents and write the indexes to disk.

Only the `issue` text is embedded, because at query time the user only knows
the symptom. Root cause, solution and labels travel as payload. Embeddings are
cached in data/embeddings.npy and only recomputed when the texts change, so
rebuilding is free.

Two indexes are written:
  index/full   every incident, used by the API
  index/train  training split only, used by evaluation

    python -m rag.build_index
"""
import hashlib
import json

import faiss
import numpy as np

from .config import (CLEAN_PATH, EMB_META_PATH, EMB_PATH, EMBED_MODEL, INDEX_DIR,
                     SPLIT_PATH)
from .llm import embed

PAYLOAD_FIELDS = ["id", "issue", "root_cause", "solution", "severity", "category", "org",
                  "source_url", "incident_date", "provenance", "cause_is_vague"]


def _fingerprint(texts):
    return hashlib.sha256("\x00".join(texts).encode()).hexdigest()


def load_embeddings(entries):
    """Return (ids, vectors) for every entry, using the on-disk cache when valid."""
    ids = [e["id"] for e in entries]
    texts = [e["issue"] for e in entries]
    fingerprint = _fingerprint(texts)
    if EMB_PATH.exists() and EMB_META_PATH.exists():
        meta = json.loads(EMB_META_PATH.read_text())
        if meta["fingerprint"] == fingerprint and meta["model"] == EMBED_MODEL:
            print(f"embeddings: cache hit ({len(ids)} vectors, {EMBED_MODEL})")
            return ids, np.load(EMB_PATH)
    print(f"embeddings: computing {len(texts)} vectors with {EMBED_MODEL}")
    vectors = embed(texts)
    np.save(EMB_PATH, vectors)
    EMB_META_PATH.write_text(json.dumps(
        {"model": EMBED_MODEL, "fingerprint": fingerprint, "ids": ids, "dim": vectors.shape[1]}
    ))
    return ids, vectors


def write_index(name, entries, vectors):
    out = INDEX_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    index = faiss.IndexFlatIP(vectors.shape[1])  # inner product on unit vectors = cosine
    index.add(vectors)
    faiss.write_index(index, str(out / "dense.faiss"))
    docs = [{field: e.get(field) for field in PAYLOAD_FIELDS} for e in entries]
    (out / "docs.json").write_text(json.dumps(docs, ensure_ascii=False))
    (out / "manifest.json").write_text(json.dumps(
        {"name": name, "count": len(docs), "dim": vectors.shape[1], "embed_model": EMBED_MODEL},
        indent=1,
    ))
    print(f"index/{name}: {len(docs)} docs, dim {vectors.shape[1]}")


def main():
    entries = json.loads(CLEAN_PATH.read_text())
    split = json.loads(SPLIT_PATH.read_text())
    ids, vectors = load_embeddings(entries)
    row = {incident_id: i for i, incident_id in enumerate(ids)}

    write_index("full", entries, vectors)
    train_ids = set(split["train"])
    train_rows = [row[e["id"]] for e in entries if e["id"] in train_ids]
    write_index("train", [entries[i] for i in train_rows], vectors[train_rows])


if __name__ == "__main__":
    main()
