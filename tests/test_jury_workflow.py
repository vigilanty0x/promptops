import contextlib
import copy
import hashlib
import importlib.util
import io
import json

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from fixtures import suite_data
from promptbench.models import BenchmarkSuite
from promptbench.ops import OpsValidationError,_digest
from promptbench.ops_cli import main
from promptbench.routing import RoutingPolicy
from promptbench.workflow import run_workflow,verify_workflow,_encode
from promptbench.judgment import read_input


class JuryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.suite=self.root/'suite.json'
        self.data=suite_data();self.suite.write_text(json.dumps(self.data),encoding='utf-8')
        self.sha=BenchmarkSuite.from_dict(self.data).suite_sha
        self.jury=self.root/'jury-input.json'
        self.request={'schema':'promptops-jury-input/1','suite_sha':self.sha,
                      'votes':[{'choice':'good','weight':3},{'choice':'bad','weight':1}],
                      'score_jury':{'candidate_id':'good','scores':[.8,.9]}}
        self.put(self.jury,self.request)

    def put(self,path,value):path.write_bytes(_encode(value))
    def call(self,argv):
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):code=main(argv)
        return code,out.getvalue(),err.getvalue()

    def test_jury_binds_suite_report_and_selected_candidate(self):
        result=run_workflow(self.suite,self.root/'run',jury_path=self.jury)
        self.assertEqual(result['decision'],'route');self.assertTrue(result['gate_passed'])
        jury=read_input(self.root/'run/jury.json')
        self.assertEqual(jury['context']['suite_sha'],result['suite_sha'])
        self.assertEqual(jury['context']['report_sha'],result['report_sha'])
        self.assertEqual(jury['context']['selected_candidate'],'good')
        self.assertFalse(jury['provider_called']);self.assertFalse(jury['juror_identity_verified'])
        self.assertEqual(hashlib.sha256((self.root/'run/jury.json').read_bytes()).hexdigest(),result['artifacts']['jury.json'])
        self.assertTrue(verify_workflow(self.root/'run',self.suite,jury_path=self.jury)['valid'])

    def test_explicit_veto_keeps_route_and_cannot_rescue_abstention(self):
        cases=[('other',[{'choice':'bad'},{'choice':'bad'}],None),
               ('split',[{'choice':'good'},{'choice':'bad'}],None),
               ('quorum',[{'choice':'good'}],None),
               ('scores',[{'choice':'good'},{'choice':'good'}],{'candidate_id':'good','scores':[.1,.2]}),
               ('score-mismatch',[{'choice':'good'},{'choice':'good'}],{'candidate_id':'bad','scores':[.9,.9]})]
        for name,votes,scores in cases:
            request={**self.request,'votes':votes};request.pop('score_jury')
            if scores is not None:request['score_jury']=scores
            self.put(self.jury,request)
            result=run_workflow(self.suite,self.root/name,jury_path=self.jury)
            with self.subTest(name=name):
                self.assertEqual(result['decision'],'route');self.assertFalse(result['gate_passed'])
                self.assertEqual(read_input(self.root/name/'route.json')['selected_candidate'],'good')
                self.assertTrue(verify_workflow(self.root/name,self.suite,jury_path=self.jury)['valid'])
        self.put(self.jury,self.request)
        result=run_workflow(self.suite,self.root/'abstain',jury_path=self.jury,policy=RoutingPolicy(min_pass_rate=1,max_mean_latency_ms=0))
        self.assertEqual(result['decision'],'abstain');self.assertFalse(result['gate_passed'])

    def test_jury_cannot_rescue_failed_regression(self):
        run_workflow(self.suite,self.root/'baseline')
        current=copy.deepcopy(self.data)
        current['replay']['good']['exact'][0]['output']='wrong'
        self.put(self.suite,current)
        self.request['suite_sha']=BenchmarkSuite.from_dict(current).suite_sha;self.put(self.jury,self.request)
        result=run_workflow(self.suite,self.root/'current',baseline=self.root/'baseline/report.json',jury_path=self.jury,policy=RoutingPolicy(min_pass_rate=.5))
        self.assertTrue(read_input(self.root/'current/jury.json')['gate_passed'])
        self.assertFalse(read_input(self.root/'current/regression.json')['passed'])
        self.assertFalse(result['gate_passed'])
        self.assertTrue(verify_workflow(self.root/'current',self.suite,baseline=self.root/'baseline/report.json',jury_path=self.jury)['valid'])

    def test_invalid_context_fails_before_output_creation(self):
        for field,value in [('suite_sha','f'*64),('votes',[{'choice':'unknown'},{'choice':'good'}])]:
            request={**self.request,field:value};self.put(self.jury,request)
            with self.subTest(field=field),self.assertRaises(OpsValidationError):run_workflow(self.suite,self.root/'invalid',jury_path=self.jury)
            self.assertFalse((self.root/'invalid').exists())

    def test_export_replay_requires_original_inputs_and_exact_bytes(self):
        run_workflow(self.suite,self.root/'run',jury_path=self.jury)
        shutil.copytree(self.root/'run',self.root/'export')
        self.assertTrue(verify_workflow(self.root/'export',self.suite,jury_path=self.jury)['valid'])
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'export',self.suite)
        artifact=read_input(self.root/'export/jury.json')
        # A rehashed, internally consistent alternative report identity still
        # cannot pass replay against the original suite/report.
        artifact['context']['report_sha']='f'*64;artifact.pop('artifact_sha');artifact['artifact_sha']=_digest(artifact)
        self.put(self.root/'export/jury.json',artifact)
        receipt=read_input(self.root/'export/result.json')
        receipt['artifacts']['jury.json']=hashlib.sha256((self.root/'export/jury.json').read_bytes()).hexdigest()
        self.put(self.root/'export/result.json',receipt)
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'export',self.suite,jury_path=self.jury)
        (self.root/'run/jury.json').write_text(json.dumps(read_input(self.root/'run/jury.json')),encoding='utf-8')
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'run',self.suite,jury_path=self.jury)

    def test_export_cannot_swap_supplied_ballots_or_global_gate(self):
        run_workflow(self.suite,self.root/'run',jury_path=self.jury)
        alternative=copy.deepcopy(self.request);alternative['votes'][0]['weight']=2
        self.put(self.jury,alternative)
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'run',self.suite,jury_path=self.jury)
        self.put(self.jury,self.request)
        result=read_input(self.root/'run/result.json');result['gate_passed']=False
        self.put(self.root/'run/result.json',result)
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'run',self.suite,jury_path=self.jury)

    def test_output_failure_preserves_partial_artifacts_without_receipt(self):
        from promptbench import workflow
        original=workflow._save
        def fail(root,name,value):
            if name=='jury.json':raise OSError('synthetic write fault')
            return original(root,name,value)
        with mock.patch.object(workflow,'_save',side_effect=fail),self.assertRaises(OSError):
            run_workflow(self.suite,self.root/'partial',jury_path=self.jury)
        self.assertTrue((self.root/'partial/report.json').is_file())
        self.assertFalse((self.root/'partial/result.json').exists())
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'partial',self.suite,jury_path=self.jury)

    def test_cli_codes_and_replay(self):
        code,out,err=self.call(['run',str(self.suite),'--output',str(self.root/'run'),'--jury',str(self.jury)])
        self.assertEqual((code,err),(0,''));self.assertTrue(json.loads(out)['gate_passed'])
        code,out,err=self.call(['verify','--run',str(self.root/'run'),'--suite',str(self.suite),'--jury',str(self.jury)])
        self.assertEqual(code,0);self.assertTrue(json.loads(out)['jury_checked'])
        self.request['votes']=[{'choice':'good'},{'choice':'bad'}];self.put(self.jury,self.request)
        code,out,err=self.call(['jury','--votes',str(self.jury)])
        self.assertEqual(code,3);self.assertFalse(json.loads(out)['gate_passed'])
        for argv in [['jury','report.json','--votes',str(self.jury)],['jury'],['verify','--run',str(self.root/'run')],['regress','--cases',str(self.jury),'baseline','current']]:
            with self.subTest(argv=argv):
                code,out,err=self.call(argv);self.assertEqual(code,2);self.assertNotIn('Traceback',err)

    def test_cases_cli_real_regression_and_invalid_input(self):
        cases=self.root/'cases.json'
        self.put(cases,{'schema':'promptops-cases-input/1','cases':[{'id':'x','baseline':'yes','candidate':'no','expected':'yes'}]})
        code,out,err=self.call(['regress','--cases',str(cases)])
        self.assertEqual(code,3);self.assertEqual(json.loads(out)['comparison']['regressions'],1)
        for data in ['{"schema":"x","schema":"y"}','{"a":NaN}','['*2000,'x'*((2*1024*1024)+1)]:
            cases.write_text(data,encoding='utf-8')
            code,out,err=self.call(['regress','--cases',str(cases)])
            self.assertEqual(code,2);self.assertNotIn('Traceback',err)

    def test_input_symlink_refused(self):
        link=self.root/'linked.json'
        try:link.symlink_to(self.jury)
        except OSError as error:self.skipTest('OS does not permit fixture symlink: '+str(error.errno))
        with self.assertRaises(OpsValidationError):read_input(link)
        directory=self.root/'linked-dir';directory.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OpsValidationError):read_input(directory/'jury-input.json')

    def test_documented_examples_execute_the_real_pipeline(self):
        project=Path(__file__).resolve().parents[1]
        code,out,err=self.call(['run',str(project/'examples/suite.json'),'--output',str(self.root/'example'),
                               '--min-pass-rate','.7','--jury',str(project/'examples/jury-input.json')])
        self.assertEqual((code,err),(0,''));self.assertTrue(json.loads(out)['gate_passed'])
        code,out,err=self.call(['verify','--run',str(self.root/'example'),'--suite',str(project/'examples/suite.json'),
                               '--jury',str(project/'examples/jury-input.json')])
        self.assertEqual(code,0);self.assertTrue(json.loads(out)['valid'])
        code,out,err=self.call(['regress','--cases',str(project/'examples/cases-input.json')])
        self.assertEqual(code,3);self.assertEqual(json.loads(out)['comparison']['regressions'],1)

    def test_old_workflow_bytes_remain_identical_without_jury(self):
        # Exact retained public source: omission keeps the historical bytes.
        before=Path(__file__).resolve().parent/'fixtures/workflow_before_jury.py'
        self.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest(),'5e23ff73c7fabd07085ead9006d1a1caf9abb2356325d800b1844f6538e06123')
        spec=importlib.util.spec_from_file_location('promptbench._before_workflow',before)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        old.run_workflow(self.suite,self.root/'old')
        run_workflow(self.suite,self.root/'new')
        self.assertEqual({p.name:p.read_bytes() for p in (self.root/'old').iterdir()},
                         {p.name:p.read_bytes() for p in (self.root/'new').iterdir()})
