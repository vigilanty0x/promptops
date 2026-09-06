import contextlib,copy,hashlib,importlib.util,io,json,math,random,shutil,tempfile,unittest
from pathlib import Path
from unittest import mock
from fixtures import suite_data
from promptbench import bundles
from promptbench.bundle_primitives import _redact,record_benchmark
from promptbench.bundle_verification import verify_release_bundle
from promptbench.judgment import read_input
from promptbench.models import BenchmarkSuite
from promptbench.ops import OpsValidationError
from promptbench.ops_cli import main
from promptbench.routing import RoutingPolicy
from promptbench.workflow import run_workflow,verify_workflow,_encode

ROOT=Path(__file__).resolve().parents[1]

def original(package,module):
    path=ROOT/'packages'/package/'src'/module/'core.py'
    spec=importlib.util.spec_from_file_location('_oracle_'+module,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

def request(data):
    packages=[]
    for c in data['candidates']:
        packages.append({'candidate_id':c['id'],'record':{
            'name':'package-'+c['id'],'version':'1.0.0','prompt':c['prompt_template'],'variables':['input'],
            'output_schema':{'type':'string'},'tests':[{'variables':{'input':'fixture'},
            'expected_prompt':c['prompt_template'].replace('{input}','fixture'),'output':'sample'}]}})
    return {'schema':'promptops-bundle-input/1','suite_sha':BenchmarkSuite.from_dict(data).suite_sha,
            'release_version':'1.0.0','split':{'algorithm':bundles.ALGORITHM,'test_percent':20},
            'packages':packages,'provenance':{'source_id':'synthetic-replay','declared_at':None,'duration_ms':None}}

class PrimitiveParityTests(unittest.TestCase):
    def test_split_matches_real_source_105_cases(self):
        source=original('eval-dataset-builder','eval_dataset_builder');rng=random.Random(501)
        for n in range(105):
            items=[{'input':rng.choice(['a','b','é\r\n界']), 'expected':rng.choice(['ok',{'a':[1,True]},None])} for _ in range(n%13+1)]
            pct=n%99+1
            with self.subTest(n=n):
                actual=bundles.split_rows(items,test_percent=pct)
                self.assertEqual(actual,source.build(items,test_percent=pct))
                self.assertEqual(actual,bundles.split_rows(list(reversed(items)),test_percent=pct))
                self.assertEqual(len({x['id'] for x in actual['items']}),actual['count'])

    def test_package_success_and_refusal_match_real_runner(self):
        source=original('prompt-package-manager','prompt_package_manager')
        record=request(suite_data())['packages'][0]['record']
        cases=[record,{**record,'version':'1.2.3-rc.1+build.5'}]
        for schema,output in [({'type':'integer'},3),({'type':'boolean'},True),({'type':'number'},3.5),
             ({'type':'array'},[1]),({'type':'object','required':['ok'],'properties':{'ok':{'type':'boolean'}}},{'ok':True})]:
            r=copy.deepcopy(record);r['output_schema']=schema;r['tests'][0]['output']=output;cases.append(r)
        for case in cases:self.assertEqual(bundles.test_package(case),source.build_prompt_package(case))
        bad=[]
        for field,value in [('version','01.2.3'),('name','Upper'),('prompt','{input.__class__}'),('prompt','{input!r}'),('variables',['other']),('prompt','{input')]:
            bad.append({**record,field:value})
        r=copy.deepcopy(record);r['tests'][0]['expected_prompt']='wrong';bad.append(r)
        r=copy.deepcopy(record);r['tests'][0]['output']=False;bad.append(r)
        for case in bad:
            with self.subTest(case=len(case)):
                with self.assertRaises((ValueError,KeyError)):source.build_prompt_package(case)
                with self.assertRaises(OpsValidationError):bundles.test_package(case)

    def test_recorder_exact_source_parity_declared_metrics(self):
        source=original('benchmark-run-recorder','benchmark_run_recorder')
        for duration in [1,13.5,86400000]:
            data={'benchmark':'sample','configuration':{'suite':'a'},'duration_ms':duration,
                  'result':{'accuracy':0.5},'artifacts':[{'path':'report.json','sha256':'a'*64}]}
            self.assertEqual(record_benchmark(data),source.record_benchmark(data))
            self.assertEqual(record_benchmark(data)['verification'],'not-performed')

    def test_redaction_exact_source_and_limits_not_anonymity(self):
        source=original('multi-agent-failure-corpus','multi_agent_failure_corpus')
        values=['plain fixture','password='+'not-a-real-password','Bearer '+'abcde1234567890',
                'AKIA'+'A'*16,'xoxb-'+'a'*20,'sk_live_'+'a'*20,'ghp_'+'a'*25,
                'someone@example.test','127.0.0.1','short password=abc',
                'eyJ'+'a'*8+'.eyJ'+'b'*8+'.'+'c'*12]
        for value in values:
            with self.subTest(length=len(value)):self.assertEqual(_redact(value),source._redact(value))
        self.assertEqual(_redact('short password=abc')[1],0)

    def test_stricter_types_budgets_and_schema_refusals(self):
        for items,pct in [([],20),([{'input':'a','expected':'b'}],True),([{'input':'a','expected':math.nan}],20),([{'input':'a'}],20)]:
            with self.assertRaises(OpsValidationError):bundles.split_rows(items,test_percent=pct)
        item=request(suite_data())['packages'][0]['record']
        for schema in [{'type':[]},{'type':'object','additionalProperties':False},{'type':'array','items':{}}, {'type':'object','required':['x','x']}]:
            with self.assertRaises(OpsValidationError):bundles.test_package({**item,'output_schema':schema})
        nested={};v=nested
        for _ in range(22):v['x']={};v=v['x']
        with self.assertRaises(OpsValidationError):bundles._finite_tree(nested)
        with mock.patch.object(bundles,'MAX_NODES',2):
            with self.assertRaises(OpsValidationError):bundles._finite_tree([1,2,3])

class BundleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data=suite_data()
        self.suite=self.root/'suite.json';self.bundle=self.root/'bundle-input.json';self.req=request(self.data)
        self.save()
    def put(self,p,v):p.write_bytes(_encode(v))
    def save(self):self.put(self.suite,self.data);self.put(self.bundle,self.req)
    def execute(self,name='run',**kwargs):return run_workflow(self.suite,self.root/name,bundle_path=self.bundle,**kwargs)
    def test_release_split_and_replay_use_existing_engine(self):
        before=run_workflow(self.suite,self.root/'plain')
        with mock.patch('promptbench.bundles.build_prompt_package',wraps=bundles.build_prompt_package) as runner:
            result=self.execute()
        self.assertEqual(runner.call_count,len(self.data['candidates']))
        for name in before['artifacts']:self.assertEqual((self.root/'plain'/name).read_bytes(),(self.root/'run'/name).read_bytes())
        self.assertEqual(result['decision'],before['decision']);self.assertEqual(result['gate_passed'],before['gate_passed'])
        self.assertFalse(result['provider_called']);self.assertEqual(result['provenance'],'not-verified')
        split=read_input(self.root/'run/split.json');self.assertFalse(split['holdout_evaluation_executed'])
        self.assertEqual(split['evaluation_scope'],'complete_replay_suite')
        release=read_input(self.root/'run/release.json')
        self.assertTrue(verify_release_bundle(release,[read_input(self.root/'run/dataset.json'),read_input(self.root/'run/scorecard.json')])['valid'])
        self.assertTrue(verify_workflow(self.root/'run',self.suite,bundle_path=self.bundle)['valid'])
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'run',self.suite)
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'plain',self.suite,bundle_path=self.bundle)
    def test_omission_exact_before_bytes_six_contexts(self):
        before=Path(__file__).resolve().parent/'fixtures/workflow_before_bundles.py'
        self.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest(),'1b7d33aa012e1f9c81164d8e4b63ecbed1c9fc9eac8cc2d47f51eb883f86cc6b')
        spec=importlib.util.spec_from_file_location('promptbench._bundle_before',before)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        for n in range(6):
            policy=RoutingPolicy(min_pass_rate=n/5)
            old.run_workflow(self.suite,self.root/f'old{n}',policy=policy)
            run_workflow(self.suite,self.root/f'new{n}',policy=policy)
            a={p.name:p.read_bytes() for p in (self.root/f'old{n}').iterdir()}
            b={p.name:p.read_bytes() for p in (self.root/f'new{n}').iterdir()}
            self.assertEqual(a,b)
    def test_train_test_no_duplicates_and_conflicting_labels_refused(self):
        same=copy.deepcopy(self.data['scenarios'][0]);same['id']='duplicate';self.data['scenarios'].append(same)
        for replay in self.data['replay'].values():replay['duplicate']=copy.deepcopy(replay['exact'])
        self.req=request(self.data);self.save();self.execute()
        split=read_input(self.root/'run/split.json');self.assertEqual(split['duplicates_removed'],1)
        self.assertEqual(split['unique_rows'],2)
        self.data['scenarios'][-1]['expected']='conflicting';self.req=request(self.data);self.save()
        with self.assertRaisesRegex(OpsValidationError,'conflicting'):self.execute('conflict')
        self.assertFalse((self.root/'conflict').exists())
    def test_provenance_missing_and_declared_never_becomes_observation(self):
        self.execute('missing');origin=read_input(self.root/'missing/metrics-origin.json')
        self.assertEqual(origin['duration_status'],'not_supplied');self.assertIsNone(origin['benchmark_record'])
        self.req['provenance'].update(duration_ms=12.5,declared_at='2099-01-01T00:00:00Z');self.save();self.execute('declared')
        origin=read_input(self.root/'declared/metrics-origin.json')
        self.assertEqual(origin['declared_at_status'],'declared_not_observed')
        self.assertFalse(origin['independent_measurement']);self.assertFalse(origin['provenance_verified'])
        self.assertEqual(origin['benchmark_record']['verification'],'not-performed')
        for artifact in origin['benchmark_record']['artifacts']:
            self.assertEqual(hashlib.sha256((self.root/'declared'/artifact['path']).read_bytes()).hexdigest(),artifact['sha256'])
    def test_tamper_each_artifact_inventory_and_export_replay(self):
        result=self.execute();copy_path=self.root/'copied';shutil.copytree(self.root/'run',copy_path)
        self.assertTrue(verify_workflow(copy_path,self.suite,bundle_path=self.bundle)['valid'])
        for name in result['artifacts']:
            p=copy_path/name;raw=p.read_bytes();p.write_bytes(raw+b' ')
            with self.subTest(name=name):
                with self.assertRaises(OpsValidationError):verify_workflow(copy_path,self.suite,bundle_path=self.bundle)
            p.write_bytes(raw)
        (copy_path/'unexpected.json').write_text('{}')
        with self.assertRaises(OpsValidationError):verify_workflow(copy_path,self.suite,bundle_path=self.bundle)
    def test_changed_bundle_suite_and_result_cannot_replay(self):
        self.execute()
        result_file=self.root/'run/result.json';raw=result_file.read_bytes();data=read_input(result_file)
        data['gate_passed']=not data['gate_passed'];self.put(result_file,data)
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'run',self.suite,bundle_path=self.bundle)
        result_file.write_bytes(raw)
        self.req['release_version']='1.0.1';self.save()
        with self.assertRaises(OpsValidationError):verify_workflow(self.root/'run',self.suite,bundle_path=self.bundle)
        self.req=request(self.data);self.data['scenarios'][0]['input']='changed';self.save()
        with self.assertRaises(OpsValidationError):self.execute('different')
    def test_refuse_malformed_contract_before_any_output(self):
        bad=[]
        for field,value in [('schema','unknown'),('suite_sha','a'*64),('release_version','01.2.3'),('packages',[])]:bad.append({**self.req,field:value})
        bad.append({**self.req,'seed':1})
        for change in [{'algorithm':'seed-v1','test_percent':20},{'algorithm':bundles.ALGORITHM,'test_percent':True}]:bad.append({**self.req,'split':change})
        for index,item in enumerate(bad):
            self.put(self.bundle,item)
            with self.assertRaises(OpsValidationError):self.execute(f'bad{index}')
            self.assertFalse((self.root/f'bad{index}').exists())
    def test_package_template_identity_duplicates_and_failure(self):
        for index,kind in enumerate(['template','duplicate','candidate','expected','output','unknown-field']):
            req=copy.deepcopy(self.req);p=req['packages'][0]
            if kind=='template':p['record']['prompt']='Unrelated {input}'
            if kind=='duplicate':req['packages'][1]=p
            if kind=='candidate':p['candidate_id']='unknown'
            if kind=='expected':p['record']['tests'][0]['expected_prompt']='wrong'
            if kind=='output':p['record']['tests'][0]['output']=3
            if kind=='unknown-field':p['record']['installed']=True
            self.put(self.bundle,req)
            with self.assertRaises(OpsValidationError):self.execute(f'bad{index}')
            self.assertFalse((self.root/f'bad{index}').exists())
    def test_formatter_and_native_renderer_disagreement_is_refused(self):
        self.data['candidates'][0]['prompt_template']='Literal {{text}} {input}'
        self.req=request(self.data)
        self.req['packages'][0]['record']['tests'][0]['expected_prompt']='Literal {text} fixture'
        self.save()
        with self.assertRaisesRegex(OpsValidationError,'native replay template'):self.execute()
        self.assertFalse((self.root/'run').exists())
    def test_supplied_provenance_and_input_limits_fail_closed(self):
        for index,provenance in enumerate([
            {'source_id':'x','declared_at':'2026-09-06','duration_ms':None},
            {'source_id':'x','declared_at':None,'duration_ms':True},
            {'source_id':'x','declared_at':None,'duration_ms':math.inf},
            {'source_id':'x','declared_at':None,'duration_ms':-1},
            {'source_id':'x','declared_at':None,'duration_ms':1,'verified':True}]):
            item={**self.req,'provenance':provenance}
            # json.dumps permits the intentionally invalid Infinity fixture.
            self.bundle.write_text(json.dumps(item))
            with self.assertRaises(OpsValidationError):self.execute(str(index))
            self.assertFalse((self.root/str(index)).exists())
        self.save()
        with mock.patch.object(bundles,'MAX_BUNDLE_INPUT',100):
            with self.assertRaises(OpsValidationError):self.execute('bounded')
        self.assertFalse((self.root/'bounded').exists())
    def test_sensitive_failure_refused_before_output_legacy_unchanged(self):
        token='ghp_'+'a'*25
        self.data['replay']['bad']['exact'][0]['output']=token;self.req=request(self.data);self.save()
        with self.assertRaisesRegex(OpsValidationError,'sensitive-looking'):self.execute()
        self.assertFalse((self.root/'run').exists())
        run_workflow(self.suite,self.root/'legacy')
        self.assertIn(token,(self.root/'legacy/failures.json').read_text())
    def test_sensitive_other_inputs_fail_without_exposing_value(self):
        value='password='+'synthetic-password-only'
        for index,target in enumerate(['prompt','package','provenance']):
            self.data=suite_data();self.req=request(self.data)
            if target=='prompt':self.data['candidates'][0]['prompt_template']=value+' {input}';self.req=request(self.data)
            if target=='package':self.req['packages'][0]['record']['tests'][0]['output']=value
            if target=='provenance':self.req['provenance']['source_id']=value
            self.save()
            with self.assertRaises(OpsValidationError) as error:self.execute(str(index))
            self.assertNotIn(value,str(error.exception));self.assertFalse((self.root/str(index)).exists())
    def test_user_renaming_to_digest_or_schema_key_cannot_bypass_policy(self):
        token=hashlib.sha256(b'synthetic-user-value-not-an-integrity-field').hexdigest()
        self.assertGreater(_redact(token)[1],0)
        for index,key in enumerate(['suite_sha','report_sha','output_sha','prompt_sha','schema']):
            self.data=suite_data();self.data['scenarios'][1]['expected']={key:token}
            self.req=request(self.data);self.save()
            with self.assertRaisesRegex(OpsValidationError,'sensitive-looking'):self.execute(str(index))
            self.assertFalse((self.root/str(index)).exists())
        self.data=suite_data();self.req=request(self.data)
        self.req['packages'][0]['record']['output_schema']={'type':'object'}
        self.req['packages'][0]['record']['tests'][0]['output']={'suite_sha':token};self.save()
        with self.assertRaisesRegex(OpsValidationError,'sensitive-looking'):self.execute('nested-package')
        self.assertFalse((self.root/'nested-package').exists())
    def test_jury_and_abstention_remain_monotone(self):
        jury=self.root/'jury.json';self.put(jury,{'schema':'promptops-jury-input/1','suite_sha':self.req['suite_sha'],
                                               'votes':[{'choice':'bad'},{'choice':'bad'}]})
        result=self.execute(jury_path=jury);self.assertEqual(result['decision'],'route');self.assertFalse(result['gate_passed'])
        bundle=read_input(self.root/'run/bundle.json');self.assertIn('jury.json',bundle['artifacts'])
        self.assertFalse(bundle['gate_passed']);self.assertTrue(verify_workflow(self.root/'run',self.suite,bundle_path=self.bundle,jury_path=jury)['valid'])
        result=self.execute('abstain',policy=RoutingPolicy(max_mean_latency_ms=0))
        self.assertEqual(result['decision'],'abstain');self.assertFalse(result['gate_passed'])
    def test_baseline_linked_release_and_replay(self):
        run_workflow(self.suite,self.root/'previous')
        baseline=self.root/'previous/report.json';self.execute(baseline=baseline)
        bundle=read_input(self.root/'run/bundle.json');self.assertIn('regression.json',bundle['artifacts'])
        self.assertTrue(verify_workflow(self.root/'run',self.suite,bundle_path=self.bundle,baseline=baseline)['valid'])
    def test_exported_baseline_metadata_cannot_use_digest_exemption(self):
        from promptbench.ops import _digest
        run_workflow(self.suite,self.root/'previous');baseline=self.root/'previous/report.json'
        data=read_input(baseline);data['suite_version']=hashlib.sha256(b'synthetic-secret-shaped-version').hexdigest()
        data.pop('report_sha');data['report_sha']=_digest(data);self.put(baseline,data)
        with self.assertRaisesRegex(OpsValidationError,'sensitive-looking'):self.execute(baseline=baseline)
        self.assertFalse((self.root/'run').exists())
    def test_documented_example_runs_and_verifies(self):
        suite=ROOT/'examples/suite.json';bundle=ROOT/'examples/bundle-input.json'
        result=run_workflow(suite,self.root/'example',bundle_path=bundle,policy=RoutingPolicy(min_pass_rate=.7))
        self.assertTrue(result['gate_passed'])
        self.assertTrue(verify_workflow(self.root/'example',suite,bundle_path=bundle)['valid'])
    def test_output_budget_existing_directory_and_input_file_guards(self):
        with mock.patch.object(bundles,'MAX_EXPORT',200):
            with self.assertRaises(OpsValidationError):self.execute('large')
        self.assertFalse((self.root/'large').exists())
        self.execute()
        with self.assertRaises(OpsValidationError):self.execute()
        self.bundle.write_text('{"schema":1,"schema":2}')
        with self.assertRaises(OpsValidationError):self.execute('duplicate')
        self.assertFalse((self.root/'duplicate').exists())
    def test_real_bundle_input_symlink_is_refused(self):
        link=self.root/'link.json'
        try:link.symlink_to(self.bundle)
        except OSError:self.skipTest('fixture symlink unavailable on this platform')
        with self.assertRaises(OpsValidationError):run_workflow(self.suite,self.root/'linked',bundle_path=link)
        self.assertFalse((self.root/'linked').exists())
    def test_cli_run_verify_and_misplaced_flag(self):
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=main(['run',str(self.suite),'--bundle',str(self.bundle),'--output',str(self.root/'cli')])
        self.assertEqual(code,0);self.assertIn('bundle.json',json.loads(out.getvalue())['artifacts'])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['verify','--run',str(self.root/'cli'),'--suite',str(self.suite),'--bundle',str(self.bundle)]),0)
        with contextlib.redirect_stderr(err):self.assertEqual(main(['verify',str(self.suite),'--bundle',str(self.bundle)]),2)

if __name__=='__main__':unittest.main()
