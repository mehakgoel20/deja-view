"""Offline unit tests for features 1-7 (no API calls, no monitoring backends).

    python -m unittest tests.test_features -v
"""
import unittest
from datetime import datetime, timedelta, timezone

from agents import Context, investigate
from agents.investigator import _same_claim
from agents.specialists import (DependencyAgent, HistoricalIncidentAgent,
                                LogAnalysisAgent, MetricsAnalysisAgent,
                                _services_in_text)
from benchmark.metrics import (citation_metrics, graded_gain,
                               hallucination_rate, latency_report, ndcg_at_k,
                               precision_at_k, recall_at_k, reciprocal_rank,
                               recommendation_usefulness, retrieval_report,
                               root_cause_accuracy, token_f1)
from causal import analyse_causally, build_graph
from causal.model import (BASIS_MECHANISM, NODE_MECHANISM, NODE_SYMPTOM,
                          CausalGraph, CausalNode)
from graph import ServiceGraph
from observability import (KIND_DEPLOY, KIND_LOG_BURST, KIND_METRIC_SPIKE,
                           KIND_RECOVERY, Signal, TimeWindow, cluster_lines,
                           collect_signals, correlate, detect_spike,
                           normalise_line)
from remediation import approve, build_plan
from timeline import reconstruct, what_happened_first

T0 = datetime(2026, 11, 2, 13, 0, tzinfo=timezone.utc)


def sig(sid, kind, minutes, service=None, summary="x", severity="warn", **detail):
    return Signal(id=sid, source=sid.split("-")[0].lower(), kind=kind,
                  at=T0 + timedelta(minutes=minutes), summary=summary,
                  severity=severity, service=service, detail=detail)


# ------------------------------------------------------------- feature 1

class ObservabilityTests(unittest.TestCase):
    def test_unconfigured_providers_yield_nothing_and_say_why(self):
        signals, status = collect_signals(TimeWindow.last(60))
        self.assertEqual(signals, [])
        self.assertTrue(all(not s["configured"] for s in status))
        self.assertTrue(all(s["detail"] for s in status))

    def test_detect_spike_needs_a_real_deviation(self):
        flat = [(i * 60.0, 2.0) for i in range(10)]
        self.assertIsNone(detect_spike(flat))
        spiky = flat + [(600.0, 30.0)]
        found = detect_spike(spiky)
        self.assertIsNotNone(found)
        self.assertEqual(found[1], 30.0)

    def test_detect_spike_ignores_too_few_samples(self):
        self.assertIsNone(detect_spike([(0.0, 1.0), (60.0, 99.0)]))

    def test_log_lines_normalise_and_cluster(self):
        self.assertEqual(normalise_line("timeout after 2.5s on /api/v1/orders/8891"),
                         normalise_line("timeout after 9s on /api/v1/orders/42"))
        entries = [(T0, "timeout after 2.5s on /api/v1/x/1", {}),
                   (T0, "timeout after 9s on /api/v1/x/2", {}),
                   (T0, "disk full on node-7", {})]
        clusters = cluster_lines(entries)
        self.assertEqual(clusters[0][1]["count"], 2)

    def test_correlate_finds_trigger_before_symptom(self):
        signals = [sig("GRAF-DEP-001", KIND_DEPLOY, 0, "auth"),
                   sig("PROM-MET-001", KIND_METRIC_SPIKE, 5, "auth",
                       severity="critical")]
        out = correlate(signals, TimeWindow(T0 - timedelta(minutes=10),
                                            T0 + timedelta(minutes=30)))
        self.assertIsNotNone(out["likely_trigger"])
        self.assertEqual(out["likely_trigger"]["id"], "GRAF-DEP-001")
        self.assertGreater(out["confidence"], 0.5)

    def test_correlate_rejects_change_after_symptom_as_trigger(self):
        signals = [sig("PROM-MET-001", KIND_METRIC_SPIKE, 0, "auth"),
                   sig("GRAF-DEP-001", KIND_DEPLOY, 12, "auth")]
        out = correlate(signals, TimeWindow(T0, T0 + timedelta(minutes=30)))
        self.assertIsNone(out["likely_trigger"])


# ------------------------------------------------------------- feature 3

class ServiceGraphTests(unittest.TestCase):
    def setUp(self):
        self.g = ServiceGraph.from_dict({
            "api-gateway": ["auth-service", "catalog"],
            "auth-service": [{"to": "postgres", "type": "storage"},
                             {"to": "redis", "type": "cache"}],
            "catalog": [{"to": "postgres", "type": "storage"}],
        })
        self.g.add_service("postgres", kind="datastore", tier="critical")

    def test_dependency_direction(self):
        self.assertIn("postgres", self.g.dependencies_of("api-gateway"))
        self.assertIn("api-gateway", self.g.dependents_of("postgres"))
        self.assertNotIn("api-gateway", self.g.dependencies_of("postgres"))

    def test_blast_radius_decays_with_distance(self):
        br = self.g.blast_radius("postgres")
        self.assertTrue(br["known"])
        direct = next(a for a in br["affected"] if a["service"] == "auth-service")
        indirect = next(a for a in br["affected"] if a["service"] == "api-gateway")
        self.assertEqual(direct["hops"], 1)
        self.assertEqual(indirect["hops"], 2)
        self.assertGreaterEqual(direct["impact"], indirect["impact"])

    def test_unknown_service_is_reported_not_raised(self):
        self.assertFalse(self.g.blast_radius("nope")["known"])

    def test_depth_limit_is_respected(self):
        self.assertEqual(set(self.g.dependents_of("postgres", depth=1)),
                         {"auth-service", "catalog"})

    def test_shared_dependency_explains_joint_failure(self):
        self.assertEqual(self.g.shared_dependencies(["auth-service", "catalog"]),
                         ["postgres"])

    def test_rank_suspects_prefers_what_explains_most(self):
        suspects = self.g.rank_suspects(["auth-service", "catalog"])
        self.assertEqual(suspects[0]["service"], "postgres")
        self.assertEqual(suspects[0]["explains"], 2)

    def test_round_trip_through_dict(self):
        again = ServiceGraph.from_dict(self.g.to_dict())
        self.assertEqual(again.stats()["services"], self.g.stats()["services"])
        self.assertEqual(again.stats()["dependencies"], self.g.stats()["dependencies"])


# ------------------------------------------------------------- feature 4

class CausalTests(unittest.TestCase):
    def test_cycles_are_refused(self):
        g = CausalGraph()
        g.add_node(CausalNode("a", NODE_MECHANISM, "a"))
        g.add_node(CausalNode("b", NODE_SYMPTOM, "b"))
        self.assertTrue(g.add_edge("a", "b", BASIS_MECHANISM))
        self.assertFalse(g.add_edge("b", "a", BASIS_MECHANISM))

    def test_mechanism_is_a_cause_even_with_a_trigger_upstream(self):
        g = build_graph(text="a bad configuration change broke the token validator")
        mech = [n for n in g.nodes.values() if n.kind == NODE_MECHANISM]
        self.assertTrue(mech)
        # a mechanism has a trigger upstream but is still not a symptom
        self.assertFalse(g.is_symptom(mech[0].id))

    def test_symptoms_are_only_symptom_nodes(self):
        g = build_graph(text="memory leak caused out of memory restarts")
        self.assertTrue(all(n.kind == NODE_SYMPTOM for n in g.symptoms()))

    def test_change_after_symptom_gets_no_causal_edge(self):
        signals = [sig("PROM-MET-001", KIND_METRIC_SPIKE, 0, "checkout"),
                   sig("GRAF-DEP-001", KIND_DEPLOY, 20, "checkout")]
        res = analyse_causally(text="checkout errors spiked", signals=signals)
        deploy = next((h for h in res["hypotheses"]
                       if h["node_id"] == "sig::GRAF-DEP-001"), None)
        if deploy is not None:
            self.assertEqual(deploy["likelihood"], 0.0)
            self.assertTrue(deploy["contradictions"])

    def test_precedent_raises_mechanism_confidence(self):
        without = build_graph(text="a configuration change broke it")
        with_prec = build_graph(
            text="a configuration change broke it",
            neighbours=[("GOLD-1", "a configuration change set an invalid default"),
                        ("GOLD-2", "misconfiguration of the feature flag")])
        key = "mech::config_rollout"
        self.assertGreater(with_prec.nodes[key].confidence,
                           without.nodes[key].confidence)
        self.assertIn("GOLD-1", with_prec.nodes[key].evidence)

    def test_hypotheses_carry_contradictions(self):
        res = analyse_causally(text="latency rose", signals=[])
        self.assertIn("hypotheses", res)
        self.assertIsInstance(res["summary"], str)


# ------------------------------------------------------------- feature 5

class TimelineTests(unittest.TestCase):
    def test_phases_and_ordering(self):
        signals = [sig("GRAF-DEP-001", KIND_DEPLOY, 0, "auth", summary="release v4"),
                   sig("PROM-MET-001", KIND_METRIC_SPIKE, 4, "auth",
                       severity="critical"),
                   sig("LOKI-LOG-001", KIND_LOG_BURST, 5, "auth"),
                   sig("PROM-REC-001", KIND_RECOVERY, 40, "auth")]
        tl = reconstruct(signals, TimeWindow(T0 - timedelta(minutes=10),
                                             T0 + timedelta(minutes=60)),
                         reported_at=T0 + timedelta(minutes=12),
                         reported_text="cannot log in")
        self.assertEqual(tl["by_phase"].get("trigger"), 1)
        self.assertEqual(tl["ordering"]["lead_time_minutes"], 4.0)
        self.assertEqual(tl["detection_delay_minutes"], 8.0)
        self.assertEqual(tl["event_count"], 5)

    def test_no_trigger_when_change_follows_symptom(self):
        events = reconstruct([sig("PROM-MET-001", KIND_METRIC_SPIKE, 0, "a"),
                              sig("GRAF-DEP-001", KIND_DEPLOY, 10, "a")])
        self.assertIsNone(events["ordering"]["trigger"])

    def test_what_happened_first_says_so_when_nothing_preceded(self):
        from timeline import from_signals
        ordering = what_happened_first(from_signals(
            [sig("PROM-MET-001", KIND_METRIC_SPIKE, 0, "a")]))
        self.assertIsNone(ordering["trigger"])
        self.assertIn("not a deploy", ordering["verdict"])

    def test_what_happened_first_handles_no_symptoms(self):
        ordering = what_happened_first([])
        self.assertIsNone(ordering["first_symptom"])

    def test_empty_signals_are_handled(self):
        tl = reconstruct([])
        self.assertEqual(tl["event_count"], 0)
        self.assertIsNone(tl["ordering"]["first_symptom"])


# ------------------------------------------------------------- feature 2

class AgentTests(unittest.TestCase):
    def test_agents_report_gaps_when_evidence_is_missing(self):
        ctx = Context(text="checkout is down", use_llm=False)
        for agent in (LogAnalysisAgent(), MetricsAnalysisAgent(),
                      HistoricalIncidentAgent(), DependencyAgent()):
            findings = agent.run(ctx)
            self.assertTrue(findings, f"{agent.name} returned nothing")
            self.assertTrue(any(f.kind == "gap" for f in findings))

    def test_metrics_agent_orders_anomalies(self):
        ctx = Context(text="x", use_llm=False, signals=[
            sig("PROM-MET-001", KIND_METRIC_SPIKE, 0, "auth", peak=9.0, metric="error_rate"),
            sig("PROM-MET-002", KIND_METRIC_SPIKE, 10, "api", peak=3.0, metric="latency_p99"),
        ])
        statements = " ".join(f.statement for f in MetricsAnalysisAgent().run(ctx))
        self.assertIn("auth", statements)

    def test_dependency_agent_names_shared_cause(self):
        g = ServiceGraph.from_dict({"checkout": ["redis"], "catalog": ["redis"]})
        ctx = Context(text="x", use_llm=False, service_graph=g, signals=[
            sig("PROM-MET-001", KIND_METRIC_SPIKE, 0, "checkout"),
            sig("PROM-MET-002", KIND_METRIC_SPIKE, 1, "catalog")])
        statements = " ".join(f.statement for f in DependencyAgent().run(ctx))
        self.assertIn("redis", statements)

    def test_investigation_runs_without_llm_or_backends(self):
        report = investigate(
            "Checkout 500s and the postgres connection pool is exhausted",
            use_llm=False, collect_live=False)
        self.assertEqual(report["mode"], "MULTI_AGENT")
        self.assertTrue(report["hypotheses"])
        self.assertTrue(report["evidence_gaps"])
        self.assertIn("total", report["timing_s"])

    def test_one_failing_agent_does_not_break_the_investigation(self):
        class Boom(LogAnalysisAgent):
            name = "boom"

            def run(self, ctx):
                raise RuntimeError("deliberate")

        report = investigate("x", agents=[Boom(), MetricsAnalysisAgent()],
                             use_llm=False, collect_live=False, remediate=False)
        self.assertTrue(any("boom" in f["statement"] or f["agent"] == "boom"
                            for f in report["findings"]))


class AgentFixTests(unittest.TestCase):
    """Regressions for defects found by running the pipeline end to end."""

    def test_same_claim_merges_paraphrase_but_not_different_causes(self):
        self.assertTrue(_same_claim(
            "The connection pool reached its ceiling and refused new work",
            "the connection pool reached its ceiling, refusing new work"))
        self.assertFalse(_same_claim(
            "The connection pool reached its ceiling",
            "A certificate expired and peers rejected it"))

    def test_hypotheses_are_not_duplicated_between_rankings(self):
        report = investigate("postgres connection pool exhausted", use_llm=False,
                             collect_live=False)
        statements = [h["statement"] for h in report["hypotheses"]]
        self.assertEqual(len(statements), len(set(statements)))

    def test_services_are_read_from_the_report_when_telemetry_is_empty(self):
        g = ServiceGraph.from_dict({"checkout": ["postgres"],
                                    "auth-service": ["postgres"]})
        found = _services_in_text(
            "checkout and auth-service fail; postgres looks saturated", g)
        self.assertEqual(found, ["auth-service", "checkout", "postgres"])

    def test_service_matching_respects_word_boundaries(self):
        g = ServiceGraph.from_dict({"auth": ["catalog"]})
        self.assertEqual(_services_in_text("the author read a catalogue", g), [])

    def test_dependency_agent_works_without_live_signals(self):
        g = ServiceGraph.from_dict({"checkout": ["redis"], "catalog": ["redis"]})
        ctx = Context(text="checkout and catalog are both failing",
                      use_llm=False, service_graph=g)
        findings = DependencyAgent().run(ctx)
        self.assertFalse(any(f.kind == "gap" for f in findings))
        self.assertIn("redis", " ".join(f.statement for f in findings))


# ------------------------------------------------------------- feature 6

class RemediationTests(unittest.TestCase):
    def test_plan_always_requires_approval_and_never_executes(self):
        plan = build_plan("pool exhausted", cause="connection pool exhaustion",
                          use_llm=False)
        self.assertTrue(plan["requires_human_approval"])
        self.assertIn("none", plan["execution"])
        self.assertTrue(all(a["requires_approval"] for a in plan["actions"]))

    def test_horizons_are_ordered_immediate_first(self):
        plan = build_plan("bad deploy", cause="a deploy introduced a regression",
                          use_llm=False)
        self.assertEqual(plan["actions"][0]["horizon"], "immediate")

    def test_precedent_fixes_are_preferred_and_cited(self):
        plan = build_plan("db slow", cause="missing index", use_llm=False,
                          neighbours=[{"id": "GOLD-7", "org": "Acme",
                                       "category": "database_issue",
                                       "solution": "Recreated the dropped index"}])
        precedent = [a for a in plan["actions"] if a["source"] == "precedent"]
        self.assertTrue(precedent)
        self.assertIn("GOLD-7", precedent[0]["evidence_ids"])

    def test_code_locations_only_from_evidence(self):
        plan = build_plan("error in services/auth/token.py on startup",
                          cause="bad config", use_llm=False)
        locs = [c["location"] for c in plan["code_locations"]]
        self.assertIn("services/auth/token.py", locs)

    def test_actions_are_capped_so_the_plan_stays_actionable(self):
        from remediation.engine import PER_HORIZON_CAP
        plan = build_plan(
            "deploy broke config, pool exhausted, memory leak, certificate expired, "
            "dns broken, upstream provider down, capacity short, disk failed",
            cause="everything at once", use_llm=False)
        for horizon, cap in PER_HORIZON_CAP.items():
            got = plan["by_horizon"].get(horizon, 0)
            self.assertLessEqual(got, cap, f"{horizon} exceeded its cap")

    def test_precedent_actions_survive_the_cap(self):
        plan = build_plan("db slow", cause="missing index", use_llm=False,
                          neighbours=[{"id": f"GOLD-{i}", "org": "Acme",
                                       "category": "database_issue",
                                       "solution": f"Distinct fix number {i} applied"}
                                      for i in range(8)])
        sources = [a["source"] for a in plan["actions"]
                   if a["horizon"] == "corrective"]
        self.assertIn("precedent", sources)

    def test_approval_is_recorded_not_executed(self):
        plan = build_plan("x", cause="memory leak", use_llm=False)
        approve(plan, 0, approver="mehak", decision="approved", note="ok")
        self.assertEqual(len(plan["approvals"]), 1)
        self.assertEqual(plan["actions"][0]["approval"]["approver"], "mehak")
        with self.assertRaises(IndexError):
            approve(plan, 9999, approver="x")
        with self.assertRaises(ValueError):
            approve(plan, 0, approver="x", decision="maybe")


class MechanismGroupTests(unittest.TestCase):
    def test_change_mechanisms_do_not_both_fire(self):
        from causal.model import CausalGraph
        from causal.rules import apply_mechanism_rules
        g = CausalGraph()
        matched = apply_mechanism_rules(
            g, "after the release, a bad configuration change broke it")
        change_group = {"config_rollout", "bad_deploy"}
        self.assertEqual(len(set(matched) & change_group), 1)

    def test_distinct_mechanisms_still_fire_together(self):
        from causal.model import CausalGraph
        from causal.rules import apply_mechanism_rules
        g = CausalGraph()
        matched = set(apply_mechanism_rules(
            g, "memory grew until OOM, the connection pool was exhausted, "
               "and the TLS certificate expired"))
        self.assertIn("memory_leak", matched)
        self.assertIn("connection_exhaustion", matched)
        self.assertIn("cert_expiry", matched)


# ------------------------------------------------------------- feature 7

class BenchmarkMetricTests(unittest.TestCase):
    def test_precision_and_recall_at_k(self):
        rel = [False, True, False, True, False]
        self.assertEqual(precision_at_k(rel, 2), 0.5)
        self.assertEqual(recall_at_k(rel, 2, total_relevant=2), 0.5)
        self.assertEqual(recall_at_k([False] * 5, 5), 0.0)

    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank([False, True]), 0.5)
        self.assertEqual(reciprocal_rank([True]), 1.0)
        self.assertEqual(reciprocal_rank([False, False]), 0.0)

    def test_ndcg_rewards_better_ordering(self):
        good = ndcg_at_k([2, 1, 0, 0], 4)
        bad = ndcg_at_k([0, 0, 1, 2], 4)
        self.assertGreater(good, bad)
        self.assertEqual(ndcg_at_k([2, 1], 2), 1.0)

    def test_graded_gain_levels(self):
        self.assertEqual(graded_gain("db", "dns"), 0.0)
        self.assertEqual(graded_gain("db", "db"), 1.0)
        self.assertEqual(graded_gain("db", "db", "connection pool exhausted",
                                     "the connection pool was exhausted"), 2.0)

    def test_root_cause_accuracy_tolerates_paraphrase(self):
        self.assertTrue(root_cause_accuracy(
            "the connection pool hit its ceiling and refused connections",
            "connection pool exhaustion meant new connections were refused"))
        self.assertFalse(root_cause_accuracy("dns resolution failed",
                                             "memory leak in the worker"))

    def test_citation_metrics_flag_invented_ids(self):
        out = citation_metrics(["GOLD-1", "GOLD-999"], {"GOLD-1"}, {"GOLD-1"})
        self.assertEqual(out["invented"], 1)
        self.assertTrue(out["has_invented"])
        self.assertEqual(out["precision"], 0.5)

    def test_hallucination_rate_separates_the_two_failures(self):
        out = hallucination_rate([
            {"citations": {"has_invented": True}, "claims_without_citation": 0},
            {"citations": {"has_invented": False}, "claims_without_citation": 1},
            {"citations": {"has_invented": False}, "claims_without_citation": 0}])
        self.assertAlmostEqual(out["invented_citation_rate"], 1 / 3, places=3)
        self.assertAlmostEqual(out["uncited_claim_rate"], 1 / 3, places=3)
        self.assertAlmostEqual(out["hallucination_rate"], 2 / 3, places=3)

    def test_recommendation_usefulness(self):
        out = recommendation_usefulness(
            ["roll back the release", "restart everything"],
            "the team rolled back the release")
        self.assertTrue(out["hit"])
        self.assertGreater(out["best_f1"], out["mean_f1"])

    def test_latency_report_percentiles(self):
        out = latency_report([1.0, 2.0, 3.0, 100.0])
        self.assertEqual(out["n"], 4)
        self.assertEqual(out["max_s"], 100.0)
        self.assertGreaterEqual(out["p95_s"], out["p50_s"])

    def test_retrieval_report_aggregates(self):
        out = retrieval_report([
            {"relevant": [True, False], "gains": [1, 0], "total_relevant": 1},
            {"relevant": [False, False], "gains": [0, 0], "total_relevant": 1}],
            ks=(1, 2))
        self.assertEqual(out["queries"], 2)
        self.assertEqual(out["queries_with_no_relevant_hit"], 1)
        self.assertEqual(out["mrr"], 0.5)

    def test_token_f1_is_symmetric_enough(self):
        self.assertEqual(token_f1("", "abc"), 0.0)
        self.assertGreater(token_f1("redis memory exhausted",
                                    "memory exhausted on redis"), 0.8)


if __name__ == "__main__":
    unittest.main()
