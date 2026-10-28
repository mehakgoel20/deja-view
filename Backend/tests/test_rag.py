"""Offline unit tests (no API calls).

    python -m unittest tests.test_rag -v
"""
import json
import unittest
from collections import Counter

from rag.analyze import validate
from rag.clean import clean_text, is_vague_cause
from rag.config import CATEGORIES, CLEAN_PATH, SPLIT_PATH
from rag.evaluate import macro_f1, within_one
from rag.kb import BM25, KnowledgeBase
from rag.predict import vote
from rag.retrieve import diversify


class CleanTests(unittest.TestCase):
    def test_strips_leading_label(self):
        self.assertEqual(clean_text("Root cause We determined it was DNS."), "We determined it was DNS.")

    def test_strips_colon_label(self):
        self.assertEqual(clean_text("Why it happened: We shipped a bug"), "We shipped a bug.")

    def test_strips_stacked_labels(self):
        self.assertEqual(clean_text("Root Cause Primary Root Cause: An invalid config."), "An invalid config.")

    def test_strips_root_cause_heading_before_lowercase(self):
        self.assertEqual(clean_text("Root Causes Race condition on the endpoint."), "Race condition on the endpoint.")
        self.assertEqual(clean_text("Root cause npm's spam check flagged it."), "npm's spam check flagged it.")
        text = "Root cause was a misconfiguration of login parameters."
        self.assertEqual(clean_text(text), text)

    def test_keeps_prose_that_starts_like_a_label(self):
        text = "Summary of AWS Direct Connect Event in Tokyo."
        self.assertEqual(clean_text(text), text)
        text = "Remediation involved restarting the SQL service."
        self.assertEqual(clean_text(text), text)

    def test_keeps_label_word_mid_sentence(self):
        text = "Intermittent DNS Resolution Errors for some customers."
        self.assertEqual(clean_text(text), text)

    def test_removes_components_boilerplate(self):
        self.assertEqual(
            clean_text("Controller downtime. Components impacted Controller Relays Summary The controller was down."),
            "Controller downtime. The controller was down.")

    def test_vague_cause(self):
        self.assertTrue(is_vague_cause("We identified an issue affecting the loading of Dashboards."))
        self.assertFalse(is_vague_cause("A Terraform change removed the triggers."))


class SplitTests(unittest.TestCase):
    def test_split_is_disjoint_complete_and_stratified(self):
        entries = json.loads(CLEAN_PATH.read_text())
        split = json.loads(SPLIT_PATH.read_text())
        train, test = set(split["train"]), set(split["test"])
        self.assertFalse(train & test)
        self.assertEqual(train | test, {e["id"] for e in entries})
        category = {e["id"]: e["category"] for e in entries}
        test_counts = Counter(category[i] for i in test)
        for name in CATEGORIES:
            self.assertGreaterEqual(test_counts[name], 1, name)

    def test_train_index_excludes_test(self):
        split = json.loads(SPLIT_PATH.read_text())
        kb = KnowledgeBase("train")
        self.assertFalse({d["id"] for d in kb.docs} & set(split["test"]))
        self.assertEqual(kb.index.ntotal, len(kb.docs))


class RetrievalTests(unittest.TestCase):
    def test_bm25_ranks_matching_doc_first(self):
        bm25 = BM25(["database replica lag", "dns resolution failure", "certificate expired on load balancer"])
        self.assertEqual(int(bm25.scores("expired TLS certificate").argmax()), 2)

    def test_dense_search_finds_itself(self):
        kb = KnowledgeBase("train")
        vector = kb.index.reconstruct(10)
        self.assertEqual(kb.dense_search(vector, 1)[0][0], 10)

    def test_diversify_caps_per_org(self):
        kb = KnowledgeBase("train")
        github = [i for i, d in enumerate(kb.docs) if d["org"] == "GitHub"][:4]
        others = [i for i, d in enumerate(kb.docs) if d["org"] != "GitHub"][:3]
        picked = diversify(kb, [{"row": r} for r in github + others], 5)
        self.assertEqual(sum(kb.docs[c["row"]]["org"] == "GitHub" for c in picked), 2)
        self.assertEqual(len(picked), 5)


class VoteTests(unittest.TestCase):
    def test_prior_correction_lifts_rare_class(self):
        kb = KnowledgeBase("train")
        rare = next(i for i, d in enumerate(kb.docs) if d["category"] == "memory_leak")
        common = next(i for i, d in enumerate(kb.docs) if d["category"] == "configuration_deployment")
        neighbours = [{"row": common, "cosine": 0.6}, {"row": rare, "cosine": 0.5}]
        self.assertEqual(vote(kb, neighbours, alpha=0.0)["category"], "configuration_deployment")
        self.assertEqual(vote(kb, neighbours, alpha=0.5)["category"], "memory_leak")

    def test_empty_neighbours(self):
        kb = KnowledgeBase("train")
        self.assertIsNone(vote(kb, [])["category"])


class ValidateTests(unittest.TestCase):
    def test_drops_unknown_citations_and_clamps(self):
        result = {
            "category_confidence": 1.4, "severity_confidence": -0.2,
            "hypotheses": [
                {"cause": "a", "likelihood": 0.9, "evidence_ids": ["GOLD-1", "GOLD-999"], "reasoning": ""},
                {"cause": "b", "likelihood": 0.6, "evidence_ids": ["GOLD-2", "GOLD-2"], "reasoning": ""},
                {"cause": "c", "likelihood": 0.1, "evidence_ids": [], "reasoning": ""},
                {"cause": "d", "likelihood": 0.05, "evidence_ids": [], "reasoning": ""},
            ],
            "first_checks": list("abcdefg"), "fix_steps": list("ab"),
        }
        out, report = validate(result, {"GOLD-1", "GOLD-2"})
        self.assertEqual(out["category_confidence"], 1.0)
        self.assertEqual(out["severity_confidence"], 0.0)
        self.assertEqual(report["dropped_citations"], ["GOLD-999"])
        self.assertEqual(report["hypotheses_truncated"], 1)
        self.assertEqual([h["cause"] for h in out["hypotheses"]], ["a", "b", "c"])
        self.assertEqual(out["hypotheses"][1]["evidence_ids"], ["GOLD-2"])
        self.assertLessEqual(sum(h["likelihood"] for h in out["hypotheses"]), 1.0001)
        self.assertEqual(len(out["first_checks"]), 5)


class MetricTests(unittest.TestCase):
    def test_macro_f1(self):
        self.assertAlmostEqual(macro_f1(["a", "a", "b"], ["a", "a", "b"], ["a", "b"]), 1.0)
        self.assertAlmostEqual(macro_f1(["a", "b"], ["b", "a"], ["a", "b"]), 0.0)

    def test_within_one(self):
        self.assertEqual(within_one(["Low", "Critical"], ["Medium", "Low"]), 0.5)


if __name__ == "__main__":
    unittest.main()
