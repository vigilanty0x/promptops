import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from promptbench.cli import _demo_suite_dict
from promptbench.ops import OpsValidationError
from promptbench.ops_cli import main
from promptbench.routing import RoutingPolicy
from promptbench.workflow import run_workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.suite=self.base/'suite.json'
        self.suite.write_text(json.dumps(_demo_suite_dict()),encoding='utf-8')

    def test_suite_to_verified_choice_and_failure_archive(self):
        result=run_workflow(self.suite,self.base/'result',policy=RoutingPolicy(min_pass_rate=.7))
        self.assertTrue(result['gate_passed']);self.assertFalse(result['provider_called'])
        self.assertEqual(result['mode'],'recorded_replay')
        self.assertEqual(result['provenance'],'not-verified')
        for name,digest in result['artifacts'].items():
            self.assertEqual(hashlib.sha256((self.base/'result'/name).read_bytes()).hexdigest(),digest)
        failures=json.loads((self.base/'result/failures.json').read_text(encoding='utf-8'))
        self.assertEqual(failures['failure_count'],4)
        self.assertEqual(len(failures['failures']),4)
        self.assertFalse(failures['truncated'])

    def test_no_qualifying_candidate_is_real_abstention(self):
        result=run_workflow(self.suite,self.base/'result',policy=RoutingPolicy(min_pass_rate=1))
        self.assertEqual(result['decision'],'abstain');self.assertFalse(result['gate_passed'])

    def test_tampered_baseline_does_not_create_output(self):
        run_workflow(self.suite,self.base/'previous',policy=RoutingPolicy(min_pass_rate=.7))
        baseline=self.base/'previous/report.json';data=json.loads(baseline.read_text());data['suite_id']='altered'
        baseline.write_text(json.dumps(data))
        with self.assertRaises(ValueError):run_workflow(self.suite,self.base/'new',baseline=baseline)
        self.assertFalse((self.base/'new').exists())

    def test_existing_output_is_never_replaced(self):
        output=self.base/'keep';output.mkdir();(output/'keep.txt').write_text('original')
        with self.assertRaises(OpsValidationError):run_workflow(self.suite,output)
        self.assertEqual((output/'keep.txt').read_text(),'original')

    def test_cli_and_baseline_use_the_same_pipeline(self):
        run_workflow(self.suite,self.base/'previous',policy=RoutingPolicy(min_pass_rate=.7))
        stream=io.StringIO()
        with contextlib.redirect_stdout(stream):
            code=main(['run',str(self.suite),'--output',str(self.base/'next'),
                       '--baseline-report',str(self.base/'previous/report.json'),'--min-pass-rate','.7'])
        self.assertEqual(code,0)
        result=json.loads(stream.getvalue());self.assertTrue(result['regression_checked'])
        self.assertIn('regression.json',result['artifacts'])
