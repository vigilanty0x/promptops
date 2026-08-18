from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr

from promptbench.ops import OpsValidationError, _digest, build_scorecard
from promptbench.ops_cli import main
from promptbench.routing import RoutingPolicy, route_scorecard, validate_scorecard


def make_report():
    payload = {
        "schema_version": "1.0",
        "tool_version": "0.2.0",
        "suite_id": "routing-suite",
        "suite_version": "1.0.0",
        "suite_sha": "0" * 64,
        "records": [],
        "candidates": [
            {
                "candidate_id": "alpha",
                "model": "replay/a",
                "pass_rate": 0.95,
                "pass_at_1": 0.95,
                "score_variance": 0.0,
                "mean_latency_ms": 100.0,
                "p95_latency_ms": 120.0,
                "total_cost_microunits": 100,
                "recovery_rate": 0.0,
            },
            {
                "candidate_id": "beta",
                "model": "replay/b",
                "pass_rate": 0.90,
                "pass_at_1": 0.90,
                "score_variance": 0.0,
                "mean_latency_ms": 50.0,
                "p95_latency_ms": 60.0,
                "total_cost_microunits": 50,
                "recovery_rate": 0.0,
            },
            {
                "candidate_id": "gamma",
                "model": "replay/c",
                "pass_rate": 0.85,
                "pass_at_1": 0.85,
                "score_variance": 0.0,
                "mean_latency_ms": 30.0,
                "p95_latency_ms": 40.0,
                "total_cost_microunits": 20,
                "recovery_rate": 0.0,
            },
        ],
        "ranking": ["alpha", "beta", "gamma"],
        "methodology": ["offline"],
        "limitations": ["replay"],
    }
    payload["report_sha"] = _digest(payload)
    return payload


def make_scorecard():
    return build_scorecard(make_report())


class RoutingTests(unittest.TestCase):
    def test_default_route_selects_verified_scorecard_winner_deterministically(self):
        card = make_scorecard()
        first = route_scorecard(card)
        second = route_scorecard(copy.deepcopy(card))
        self.assertEqual(first, second)
        self.assertEqual(first["decision"], "route")
        self.assertEqual(first["selected_candidate"], "alpha")
        self.assertEqual(first["source_scorecard_sha"], card["artifact_sha"])
        self.assertEqual(len(first["artifact_sha"]), 64)

    def test_constraints_skip_higher_ranked_candidate(self):
        result = route_scorecard(
            make_scorecard(),
            policy=RoutingPolicy(
                min_pass_rate=0.90,
                max_mean_latency_ms=60,
                max_total_cost_microunits=60,
            ),
        )
        self.assertEqual(result["selected_candidate"], "beta")
        alpha = result["candidates"][0]
        self.assertFalse(alpha["eligible"])
        self.assertEqual(set(alpha["reasons"]), {"latency", "cost"})
        self.assertTrue(result["candidates"][1]["eligible"])
        self.assertEqual(result["candidates"][2]["reasons"], ["pass_rate"])

    def test_allowlist_and_fallbacks_preserve_scorecard_rank_order(self):
        result = route_scorecard(
            make_scorecard(),
            policy=RoutingPolicy(allowed_candidates=("beta", "gamma"), fallback_count=1),
        )
        self.assertEqual(result["selected_candidate"], "beta")
        self.assertEqual(result["fallback_candidates"], ["gamma"])
        self.assertEqual(result["candidates"][0]["reasons"], ["not_allowed"])

    def test_no_eligible_candidate_abstains_instead_of_fabricating_route(self):
        result = route_scorecard(make_scorecard(), policy=RoutingPolicy(min_pass_rate=1.0))
        self.assertEqual(result["decision"], "abstain")
        self.assertIsNone(result["selected_candidate"])
        self.assertEqual(result["fallback_candidates"], [])
        self.assertEqual(result["eligible_count"], 0)

    def test_tampered_scorecard_is_rejected_before_routing(self):
        card = make_scorecard()
        validate_scorecard(card)
        card["rows"][0]["pass_rate"] = 0.1
        with self.assertRaisesRegex(OpsValidationError, "does not match"):
            route_scorecard(card)

    def test_invalid_policies_fail_closed(self):
        with self.assertRaises(OpsValidationError):
            RoutingPolicy(min_pass_rate=float("nan"))
        with self.assertRaises(OpsValidationError):
            RoutingPolicy(allowed_candidates=("alpha", "alpha"))
        with self.assertRaises(OpsValidationError):
            RoutingPolicy(fallback_count=65)


class RoutingCliTests(unittest.TestCase):
    def test_route_command_writes_content_addressed_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card_path = root / "card.json"
            out = root / "route.json"
            card_path.write_text(json.dumps(make_scorecard()), encoding="utf-8")
            rc = main(["route", str(card_path), "--fallbacks", "1", "-o", str(out)])
            self.assertEqual(rc, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["kind"], "route_decision")
            self.assertEqual(result["selected_candidate"], "alpha")
            self.assertEqual(result["fallback_candidates"], ["beta"])

    def test_route_command_returns_three_on_abstention(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card_path = root / "card.json"
            out = root / "route.json"
            card_path.write_text(json.dumps(make_scorecard()), encoding="utf-8")
            rc = main(["route", str(card_path), "--min-pass-rate", "1", "-o", str(out)])
            self.assertEqual(rc, 3)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["decision"], "abstain")

    def test_route_command_returns_two_for_tampered_scorecard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            card = make_scorecard()
            card["winner"] = "gamma"
            path = root / "card.json"
            path.write_text(json.dumps(card), encoding="utf-8")
            errors = io.StringIO()
            with redirect_stderr(errors):
                rc = main(["route", str(path)])
            self.assertEqual(rc, 2)
            self.assertIn("artifact_sha does not match", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
