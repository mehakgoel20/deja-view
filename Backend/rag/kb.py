"""Loads a saved index and exposes dense and BM25 search over it."""
import json
import math
import re
from collections import Counter, defaultdict

import faiss
import numpy as np

from .config import INDEX_DIR

_STOPWORDS = set("""
a an the and or of to in on for with by at from as is are was were be been being this that
these those it its we our us you your they their there here which who what when where how
some any all can could would should will may might not no but if then than so such into
out over under up down after before during while about between also has have had do does
did more most other only own same very just because via per new
""".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9_\-\.]*[a-z0-9]|[a-z0-9]")


def tokenize(text):
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


class BM25:
    def __init__(self, documents, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        tokenized = [tokenize(d) for d in documents]
        self.doc_len = np.array([len(t) for t in tokenized], dtype="float32")
        self.avg_len = float(self.doc_len.mean())
        self.postings = defaultdict(list)
        for i, tokens in enumerate(tokenized):
            for term, tf in Counter(tokens).items():
                self.postings[term].append((i, tf))
        n = len(documents)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5))
                    for t, p in self.postings.items()}

    def scores(self, query):
        scores = np.zeros(len(self.doc_len), dtype="float32")
        for term in set(tokenize(query)):
            for i, tf in self.postings.get(term, ()):
                norm = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avg_len)
                scores[i] += self.idf[term] * tf * (self.k1 + 1) / norm
        return scores


class KnowledgeBase:
    def __init__(self, name="full"):
        path = INDEX_DIR / name
        self.name = name
        self.manifest = json.loads((path / "manifest.json").read_text())
        self.docs = json.loads((path / "docs.json").read_text())
        self.index = faiss.read_index(str(path / "dense.faiss"))
        self.by_id = {d["id"]: i for i, d in enumerate(self.docs)}
        # Lexical side indexes the cause too, so terms like "terraform" or
        # "certificate" in a user's description can match a past mechanism.
        self.bm25 = BM25([d["issue"] + " " + d["root_cause"] for d in self.docs])
        counts = Counter(d["category"] for d in self.docs)
        self.category_prior = {c: n / len(self.docs) for c, n in counts.items()}

    def dense_search(self, query_vector, k):
        scores, rows = self.index.search(query_vector.reshape(1, -1).astype("float32"), k)
        return [(int(r), float(s)) for r, s in zip(rows[0], scores[0]) if r >= 0]

    def bm25_search(self, query, k):
        scores = self.bm25.scores(query)
        top = np.argsort(-scores)[:k]
        return [(int(r), float(scores[r])) for r in top if scores[r] > 0]
