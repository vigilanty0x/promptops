"""Differential checks against preserved source engines; no provider execution."""
import copy
import importlib.util
import json
from pathlib import Path
import random
import unittest

from fixtures import suite_data
from promptbench.harness import BenchmarkHarness
from promptbench.models import BenchmarkSuite
from promptbench.judgment import (weighted_vote,score_jury,compare_cases,assess_cases,
                                 assess_jury,verify_judgment)
from promptbench.ops import OpsValidationError,_digest,build_scorecard
from promptbench.routing import route_scorecard,RoutingPolicy
from promptbench.verification import verify_artifact

ROOT=Path(__file__).resolve().parents[1]
def source(project,package):
    path=ROOT/'packages'/project/'src'/package/'core.py'
    spec=importlib.util.spec_from_file_location('parity_'+package,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class JudgmentParityTests(unittest.TestCase):
    def test_weighted_source_positive_negative_and_boundary(self):
        old=source('consensus-engine','consensus_engine')
        cases=[([{'choice':'a'},{'choice':'abstain'}],2,.6),
               ([{'choice':'a'},{'choice':'b'}],2,.5),
               ([{'choice':'a','weight':3},{'choice':'b','weight':2}],2,.6),
               ([{'choice':'a','weight':3},{'choice':'b','weight':2}],2,.61),
               ([{'choice':'abstain'},{'choice':'abstain'}],2,0)]
        rng=random.Random(2048)
        for _ in range(200):
            cases.append(([{'choice':rng.choice(['a','b','c','abstain']),'weight':rng.choice([.25,1,2,100])}
                           for _ in range(rng.randint(1,20))],rng.randint(1,12),rng.choice([0,.5,.6,.9,1])))
        for votes,quorum,threshold in cases:
            with self.subTest(votes=votes,quorum=quorum,threshold=threshold):
                self.assertEqual(weighted_vote(votes,quorum=quorum,threshold=threshold),old.decide(votes,quorum=quorum,threshold=threshold))
        self.assertEqual(weighted_vote([{'choice':'a'},{'choice':'abstain'}])['decision'],'accepted')

    def test_score_jury_source_positive_negative_and_boundary(self):
        old=source('llm-jury','llm_jury');rng=random.Random(12)
        cases=[([.7,.7],.7,.35),([.5,.85],.7,.35),([.2,.9],.7,.35),([.6,.6],.7,.35)]
        cases += [([rng.randint(0,100)/100 for _ in range(rng.randint(2,20))],rng.choice([0,.7,1]),rng.choice([0,.35,1])) for _ in range(100)]
        for scores,minimum,spread in cases:
            with self.subTest(scores=scores):
                self.assertEqual(score_jury(scores,pass_score=minimum,max_spread=spread),old.judge(scores,pass_score=minimum,max_spread=spread))

    def test_native_rules_source_parity(self):
        old=source('prompt-regression','prompt_regression')
        cases=[{'id':'exact-regression','baseline':'yes','candidate':' yes ','expected':'yes'},
               {'id':'exact-improvement','baseline':'YES','candidate':'yes','expected':'yes'},
               {'id':'contains-regression','baseline':'xYESy','candidate':'yes','expected':'YES','mode':'contains'},
               {'id':'contains-unchanged','baseline':'xyz','candidate':'x','expected':'x','mode':'contains'},
               {'id':'json-improvement','baseline':'{"a":2}','candidate':'{"b":[true],"a":1}','expected':{'a':1,'b':[True]},'mode':'json'},
               {'id':'json-same','baseline':'{"b":2,"a":1}','candidate':'{ "a":1, "b":2 }','expected':{'a':1,'b':2},'mode':'json'}]
        self.assertEqual(compare_cases(cases),old.compare(cases))
        self.assertEqual(compare_cases(cases)['regressions'],2)
        artifact=assess_cases({'schema':'promptops-cases-input/1','cases':cases})
        self.assertFalse(artifact['gate_passed']);verify_artifact(artifact)

    def test_scorecard_source_parity_with_real_harness_and_units(self):
        old=source('model-scorecard','model_scorecard')
        report=BenchmarkHarness(BenchmarkSuite.from_dict(suite_data())).run()
        models=[{'model':candidate.candidate_id,'runs':[{'passed':r.passed,'latency_ms':r.latency_ms,'cost':r.cost_microunits}
                for r in report.records if r.candidate_id==candidate.candidate_id]} for candidate in report.candidates]
        card=build_scorecard(report.to_dict())
        for latency in [0,5,100,5000]:
            for cost in [0,1,1000,1000000]:
                with self.subTest(latency=latency,cost=cost):
                    expected=old.score(models,max_latency_ms=latency,max_cost=cost)
                    actual=route_scorecard(card,policy=RoutingPolicy(min_pass_rate=0,max_mean_latency_ms=latency,max_total_cost_microunits=cost))
                    self.assertEqual(actual['selected_candidate'],expected['winner'])
                    by_id={r['candidate_id']:r for r in card['rows']}
                    for row in expected['scorecards']:
                        native=by_id[row['model']]
                        self.assertEqual(native['pass_rate'],row['pass_rate'])
                        self.assertEqual(native['mean_latency_ms'],row['latency_ms'])
                        self.assertEqual(native['total_cost_microunits'],row['cost'])

    def test_stricter_typed_finite_contract(self):
        for value in [True,'1',0,-1,float('nan'),float('inf'),101,10**1000]:
            with self.subTest(weight=repr(value)[:20]),self.assertRaises(OpsValidationError):weighted_vote([{'choice':'a','weight':value}])
        for scores in [[True,.7],['.9',.9],[float('nan'),.9],[],[.9]]:
            with self.subTest(scores=scores),self.assertRaises(OpsValidationError):score_jury(scores)
        for quorum in [True,0,1.2,1001]:
            with self.assertRaises(OpsValidationError):weighted_vote([{'choice':'a'}],quorum=quorum)
        for bad in ['{','{"a":1,"a":2}','NaN']:
            with self.assertRaises(OpsValidationError):compare_cases([{'id':'x','baseline':bad,'candidate':'{}','expected':{},'mode':'json'}])
        case={'id':'x','baseline':'a','candidate':'a','expected':'a'}
        with self.assertRaises(OpsValidationError):compare_cases([case,case])

    def test_rehashed_lie_rejected_and_supplied_input_detached(self):
        request={'schema':'promptops-jury-input/1','suite_sha':'1'*64,'votes':[{'choice':'a'},{'choice':'abstain'}]}
        artifact=assess_jury(request);verify_artifact(artifact)
        request['votes'][0]['choice']='b'
        self.assertEqual(artifact['input']['votes'][0]['choice'],'a')
        for field,value in [('gate_passed',False),('provider_called',True),('input_sha','2'*64),('reasons',['injected'])]:
            changed=copy.deepcopy(artifact);changed[field]=value;changed.pop('artifact_sha');changed['artifact_sha']=_digest(changed)
            with self.subTest(field=field),self.assertRaises(OpsValidationError):verify_judgment(changed)
