"""Command-line interface for deterministic PromptOps evidence operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .ops import (
    OpsValidationError,
    RegressionThresholds,
    build_failure_corpus,
    build_scorecard,
    compare_reports,
    dataset_manifest,
    jury_consensus,
)
from .release_ops import release_manifest
from .routing import RoutingPolicy, route_scorecard


def _load(path: str) -> Any:
    target = Path(path)
    if not target.is_file():
        raise OpsValidationError(f"file not found: {target}")
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpsValidationError(f"invalid JSON: {target}") from exc


def _write(value: Any, output: str | None) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if output:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="promptops", description="Offline PromptOps evidence operations")
    sub = parser.add_subparsers(dest="command", required=True)

    score = sub.add_parser("scorecard", help="build a scorecard from one PromptBench report")
    score.add_argument("report")
    score.add_argument("-o", "--output")

    failures = sub.add_parser("failures", help="extract a bounded failure corpus")
    failures.add_argument("report")
    failures.add_argument("--limit", type=int, default=10_000)
    failures.add_argument("-o", "--output")

    regress = sub.add_parser("regress", help="compare a current report with a baseline")
    regress.add_argument("baseline")
    regress.add_argument("current")
    regress.add_argument("--pass-rate-drop", type=float, default=0.0)
    regress.add_argument("--latency-increase", type=float, default=0.25)
    regress.add_argument("--cost-increase", type=float, default=0.25)
    regress.add_argument("-o", "--output")

    jury = sub.add_parser("jury", help="aggregate one or more report rankings")
    jury.add_argument("reports", nargs="+")
    jury.add_argument("-o", "--output")

    datasets = sub.add_parser("datasets", help="build a content-addressed suite manifest")
    datasets.add_argument("suites", nargs="+")
    datasets.add_argument("-o", "--output")

    route = sub.add_parser("route", help="route from one verified PromptOps scorecard")
    route.add_argument("scorecard")
    route.add_argument("--min-pass-rate", type=float, default=0.0)
    route.add_argument("--max-latency-ms", type=float)
    route.add_argument("--max-cost-microunits", type=float)
    route.add_argument("--allow-candidate", action="append", default=None)
    route.add_argument("--fallbacks", type=int, default=0)
    route.add_argument("-o", "--output")

    release = sub.add_parser("release", help="bind verified PromptOps evidence into a release manifest")
    release.add_argument("--version", required=True)
    release.add_argument("--dataset", required=True)
    release.add_argument("--scorecard", action="append", required=True)
    release.add_argument("--regression", action="append", default=[])
    release.add_argument("-o", "--output")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scorecard":
            value = build_scorecard(_load(args.report))
        elif args.command == "failures":
            value = build_failure_corpus(_load(args.report), limit=args.limit)
        elif args.command == "regress":
            thresholds = RegressionThresholds(
                pass_rate_drop=args.pass_rate_drop,
                latency_increase=args.latency_increase,
                cost_increase=args.cost_increase,
            )
            value = compare_reports(_load(args.baseline), _load(args.current), thresholds=thresholds)
        elif args.command == "jury":
            value = jury_consensus([_load(path) for path in args.reports])
        elif args.command == "datasets":
            value = dataset_manifest([_load(path) for path in args.suites])
        elif args.command == "route":
            policy = RoutingPolicy(
                min_pass_rate=args.min_pass_rate,
                max_mean_latency_ms=args.max_latency_ms,
                max_total_cost_microunits=args.max_cost_microunits,
                allowed_candidates=None if args.allow_candidate is None else tuple(args.allow_candidate),
                fallback_count=args.fallbacks,
            )
            value = route_scorecard(_load(args.scorecard), policy=policy)
        else:
            value = release_manifest(
                release_version=args.version,
                dataset=_load(args.dataset),
                scorecards=[_load(path) for path in args.scorecard],
                regressions=[_load(path) for path in args.regression],
            )
        _write(value, getattr(args, "output", None))
        if args.command == "regress" and value.get("passed") is False:
            return 3
        if args.command == "route" and value.get("decision") == "abstain":
            return 3
        if args.command == "release" and value.get("regression_gate_passed") is False:
            return 3
        return 0
    except OpsValidationError as exc:
        sys.stderr.write(f"promptops: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
