"""Command-line interface for deterministic PromptOps evidence operations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .bundle_verification import verify_release_bundle
from .ops import (
    OpsValidationError,
    RegressionThresholds,
    build_failure_corpus,
    build_scorecard,
    compare_reports,
    dataset_manifest,
    jury_consensus,
    release_manifest,
)
from .routing import RoutingPolicy, route_scorecard
from .verification import verify_artifact
from .judgment import assess_cases, assess_jury, read_input

ARTIFACT_KINDS = (
    "scorecard",
    "regression",
    "failure_corpus",
    "jury_consensus",
    "jury_assessment",
    "case_regression",
    "dataset_manifest",
    "route_decision",
    "release_manifest",
)


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

    run = sub.add_parser("run", help="evaluate a replay suite and produce one evidence-bound decision")
    run.add_argument("suite")
    run.add_argument("--output", required=True, help="new evidence directory")
    run.add_argument("--baseline-report")
    run.add_argument("--jury", help="explicit suite-bound supplied jury input; may veto the route")
    run.add_argument("--bundle", help="explicit suite-bound local bundle input; no holdout execution or publication")
    run.add_argument("--min-pass-rate", type=float, default=.9)
    run.add_argument("--max-latency-ms", type=float)
    run.add_argument("--max-cost-microunits", type=float)

    score = sub.add_parser("scorecard", help="build a scorecard from one PromptBench report")
    score.add_argument("report")
    score.add_argument("-o", "--output")

    failures = sub.add_parser("failures", help="extract a bounded failure corpus")
    failures.add_argument("report")
    failures.add_argument("--limit", type=int, default=10_000)
    failures.add_argument("-o", "--output")

    regress = sub.add_parser("regress", help="compare a current report with a baseline")
    regress.add_argument("baseline", nargs="?")
    regress.add_argument("current", nargs="?")
    regress.add_argument("--cases", help="explicit exact/contains/JSON case-regression input")
    regress.add_argument("--pass-rate-drop", type=float, default=0.0)
    regress.add_argument("--latency-increase", type=float, default=0.25)
    regress.add_argument("--cost-increase", type=float, default=0.25)
    regress.add_argument("-o", "--output")

    jury = sub.add_parser("jury", help="aggregate one or more report rankings")
    jury.add_argument("reports", nargs="*")
    jury.add_argument("--votes", help="explicit weighted-vote input with optional median/spread jury")
    jury.add_argument("-o", "--output")

    datasets = sub.add_parser("datasets", help="build a content-addressed suite manifest")
    datasets.add_argument("suites", nargs="+")
    datasets.add_argument("-o", "--output")

    verify = sub.add_parser("verify", help="verify one stored PromptOps artifact")
    verify.add_argument("artifact", nargs="?")
    verify.add_argument("--run", help="verify an exported workflow directory by replay")
    verify.add_argument("--suite", help="original replay suite for --run")
    verify.add_argument("--baseline-report", help="original baseline when the workflow used one")
    verify.add_argument("--jury", help="original jury input when the workflow used one")
    verify.add_argument("--bundle", help="original bundle input when the workflow used one")
    verify.add_argument("--kind", choices=ARTIFACT_KINDS)
    verify.add_argument("-o", "--output")

    bundle = sub.add_parser(
        "verify-bundle",
        help="verify a release manifest against explicit local evidence artifacts",
    )
    bundle.add_argument("release")
    bundle.add_argument("--artifact", action="append", required=True)
    bundle.add_argument("-o", "--output")

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
        if args.command == "run":
            from .workflow import run_workflow
            result = run_workflow(args.suite,args.output,baseline=args.baseline_report,
                                  jury_path=args.jury,bundle_path=args.bundle,
                                  policy=RoutingPolicy(min_pass_rate=args.min_pass_rate,
                                      max_mean_latency_ms=args.max_latency_ms,
                                      max_total_cost_microunits=args.max_cost_microunits))
            _write(result,None)
            return 0 if result['gate_passed'] else 3
        if args.command == "scorecard":
            value = build_scorecard(_load(args.report))
        elif args.command == "failures":
            value = build_failure_corpus(_load(args.report), limit=args.limit)
        elif args.command == "regress":
            if args.cases:
                if args.baseline is not None or args.current is not None:
                    raise OpsValidationError("--cases cannot be combined with report inputs")
                if (args.pass_rate_drop,args.latency_increase,args.cost_increase)!=(0.0,0.25,0.25):
                    raise OpsValidationError("report thresholds do not apply to case regressions")
                value=assess_cases(read_input(args.cases))
                _write(value,args.output)
                return 0 if value['gate_passed'] else 3
            if args.baseline is None or args.current is None:
                raise OpsValidationError("baseline and current reports are required")
            thresholds = RegressionThresholds(
                pass_rate_drop=args.pass_rate_drop,
                latency_increase=args.latency_increase,
                cost_increase=args.cost_increase,
            )
            value = compare_reports(_load(args.baseline), _load(args.current), thresholds=thresholds)
        elif args.command == "jury":
            if args.votes:
                if args.reports:raise OpsValidationError("--votes cannot be combined with Borda reports")
                value=assess_jury(read_input(args.votes))
            else:
                if not args.reports:raise OpsValidationError("jury requires reports or --votes")
                value = jury_consensus([_load(path) for path in args.reports])
        elif args.command == "datasets":
            value = dataset_manifest([_load(path) for path in args.suites])
        elif args.command == "verify":
            if args.run:
                if args.artifact is not None or args.kind is not None or not args.suite:
                    raise OpsValidationError("--run requires --suite and cannot be combined with artifact/--kind")
                from .workflow import verify_workflow
                value=verify_workflow(args.run,args.suite,baseline=args.baseline_report,jury_path=args.jury,bundle_path=args.bundle)
            else:
                if args.artifact is None or args.suite or args.baseline_report or args.jury or args.bundle:
                    raise OpsValidationError("verify requires an artifact or explicit --run inputs")
                value = verify_artifact(_load(args.artifact), expected_kind=args.kind)
        elif args.command == "verify-bundle":
            value = verify_release_bundle(
                _load(args.release),
                [_load(path) for path in args.artifact],
            )
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
        if args.command == "jury" and args.votes and value['gate_passed'] is False:
            return 3
        if args.command == "release" and value.get("regression_gate_passed") is False:
            return 3
        return 0
    except (OpsValidationError, OSError, ValueError) as exc:
        sys.stderr.write(f"promptops: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
