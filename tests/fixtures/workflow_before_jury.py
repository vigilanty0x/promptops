"""Integrated replay assessment using the existing verified PromptOps engines."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .cli import _read_json
from .harness import BenchmarkHarness
from .models import BenchmarkSuite
from .ops import (OpsValidationError,build_scorecard,build_failure_corpus,
                  compare_reports,dataset_manifest)
from .routing import RoutingPolicy,route_scorecard
from .verification import verify_artifact


def _save(root: Path,name: str,value: Any) -> str:
    encoded=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    with (root/name).open('xb') as stream:
        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
    return hashlib.sha256(encoded).hexdigest()


def run_workflow(suite_path: str | Path,output: str | Path,*,baseline: str | Path | None=None,
                 policy: RoutingPolicy | None=None) -> dict[str,Any]:
    """Evaluate recorded samples, retain failures and return an evidence-bound choice.

    No provider is called. Latency and cost belong to supplied replay records,
    not to an independently measured model inference in this process.
    """
    target=Path(output)
    if target.exists() or target.is_symlink():
        raise OpsValidationError('workflow output already exists')
    parent=target.absolute().parent.resolve(strict=True)
    target=parent/target.name
    data=_read_json(str(suite_path))
    suite=BenchmarkSuite.from_dict(data)
    previous=_read_json(str(baseline)) if baseline is not None else None
    active_policy=policy or RoutingPolicy(min_pass_rate=.9)
    report=BenchmarkHarness(suite).run().to_dict()
    scorecard=build_scorecard(report)
    failures=build_failure_corpus(report)
    dataset=dataset_manifest([data])
    route=route_scorecard(scorecard,policy=active_policy)
    values={'report.json':report,'dataset.json':dataset,'scorecard.json':scorecard,
            'failures.json':failures,'route.json':route}
    regression=None
    if previous is not None:
        regression=compare_reports(previous,report)
        values['regression.json']=regression
    # Validation precedes creation of the output and uses the existing engines.
    for name,value in values.items():
        if name!='report.json': verify_artifact(value)
    target.mkdir(exist_ok=False)
    artifacts={name:_save(target,name,value) for name,value in values.items()}
    result={
        'schema':'promptops-workflow/1','state':'DONE','mode':'recorded_replay',
        'provider_called':False,'provenance':'not-verified',
        'suite_sha':suite.suite_sha,'report_sha':report['report_sha'],
        'decision':route['decision'],
        'gate_passed':route['decision']!='abstain' and (regression is None or regression['passed']),
        'regression_checked':regression is not None,'artifacts':artifacts,
    }
    _save(target,'result.json',result)
    return result
