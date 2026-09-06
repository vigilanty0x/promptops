"""Native deterministic rules and juries over explicitly supplied records.

Semantics follow the preserved consensus-engine, llm-jury and prompt-regression
cores. Finite typed inputs are required; permissive NaN/bool coercions in those
historical cores are deliberately rejected. Nothing calls an AI provider.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
import os
from pathlib import Path
import re
import stat
import statistics
from typing import Any

from .judges import judge
from .models import JudgeSpec
from .ops import OPS_SCHEMA_VERSION, OpsValidationError, _digest

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_CASES = 1000
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _object(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise OpsValidationError("judgment object has missing or unknown fields")
    return value


def _number(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise OpsValidationError(f"{name} must be a finite number in [{low}, {high}]")
    return float(value)


def _text(value, name, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > maximum:
        raise OpsValidationError(f"{name} must be a nonempty bounded string")
    if any(ord(char) < 32 for char in value):
        raise OpsValidationError(f"{name} contains control characters")
    return value


def _array(value, name, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise OpsValidationError(f"{name} must contain {minimum} to {maximum} entries")
    return value


def _bounded(value, maximum=MAX_INPUT_BYTES):
    try:
        raw=json.dumps(value, ensure_ascii=True, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError, OverflowError) as error:
        raise OpsValidationError("judgment must be finite bounded JSON") from error
    if len(raw)>maximum:
        raise OpsValidationError("judgment exceeds its byte limit")


def _pairs(items):
    result={}
    for key,value in items:
        if key in result: raise OpsValidationError("duplicate JSON key")
        result[key]=value
    return result


def _reject_constant(value):
    raise OpsValidationError("nonfinite JSON number")


def read_input(path, *, maximum=MAX_INPUT_BYTES, with_bytes=False):
    """Read one explicit regular JSON file, with bounded bytes and stable identity."""
    target=Path(path).absolute()
    if type(maximum) is not int or not 1<=maximum<=64*1024*1024:
        raise OpsValidationError('invalid JSON file byte limit')
    for item in (target,*target.parents):
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():
            raise OpsValidationError("linked judgment input refused")
    before=target.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size>maximum:
        raise OpsValidationError("judgment input must be a bounded regular file")
    fd=os.open(target,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
    try:
        opened=os.fstat(fd)
        if (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino):
            raise OpsValidationError("judgment input changed before opening")
        with os.fdopen(fd,'rb',closefd=False) as stream:
            raw=stream.read(maximum+1)
        after=os.fstat(fd);visible=target.stat()
    finally:
        os.close(fd)
    identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    if len(raw)>maximum or identity(opened)!=identity(after) or identity(after)!=identity(visible):
        raise OpsValidationError("judgment input changed or exceeded its byte limit")
    try:
        result=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_reject_constant)
    except (UnicodeError,ValueError,RecursionError) as error:
        raise OpsValidationError("invalid bounded judgment JSON") from error
    _bounded(result,maximum)
    return (result,raw) if with_bytes else result


def weighted_vote(votes, *, quorum=2, threshold=0.6):
    """Preserve source quorum including abstentions and weighted participating share."""
    _array(votes,'votes',1,1000)
    if type(quorum) is not int or not 1<=quorum<=1000:
        raise OpsValidationError("quorum must be an integer within [1, 1000]")
    threshold=_number(threshold,'threshold',0,1)
    totals=defaultdict(float);participating=0.0
    for vote in votes:
        _object(vote,('choice',),('weight',))
        choice=_text(vote['choice'],'choice')
        weight=_number(vote.get('weight',1),'weight',0,100)
        if weight<=0:raise OpsValidationError("weight must be positive")
        if choice!='abstain':totals[choice]+=weight;participating+=weight
    if len(votes)<quorum or participating==0:return {'decision':'blocked','reason':'quorum'}
    ordered=sorted(totals.items(),key=lambda item:(-item[1],item[0]))
    if len(ordered)>1 and ordered[0][1]==ordered[1][1]:return {'decision':'blocked','reason':'split'}
    share=ordered[0][1]/participating
    return {'decision':'accepted' if share>=threshold else 'blocked','choice':ordered[0][0],'share':share}


def score_jury(scores, *, pass_score=0.7, max_spread=0.35):
    """Median/spread policy; separate from Borda rankings and weighted votes."""
    values=[_number(value,'score',0,1) for value in _array(scores,'scores',2,100)]
    pass_score=_number(pass_score,'pass_score',0,1)
    max_spread=_number(max_spread,'max_spread',0,1)
    median=statistics.median(values);spread=max(values)-min(values)
    decision='blocked' if spread>max_spread else ('pass' if median>=pass_score else 'fail')
    return {'decision':decision,'median':median,'spread':spread,'jurors':len(values)}


def _context(value):
    if value is None:return None
    _object(value,('suite_sha','report_sha','candidate_ids','selected_candidate'))
    for name in ('suite_sha','report_sha'):
        if not isinstance(value[name],str) or not _SHA.fullmatch(value[name]):
            raise OpsValidationError("jury context requires exact SHA-256 identities")
    ids=_array(value['candidate_ids'],'candidate_ids',1,1000)
    if any(_text(item,'candidate_id')=='abstain' for item in ids) or len(set(ids))!=len(ids):
        raise OpsValidationError("jury candidate ids must be unique and not abstain")
    selected=value['selected_candidate']
    if selected is not None and selected not in ids:
        raise OpsValidationError("jury selected candidate is outside context")
    return value


def assess_jury(request, *, context=None):
    """Return replayable, content-bound judgment; data provenance stays unverified."""
    _bounded(request)
    _object(request,('schema','suite_sha','votes'),('quorum','threshold','score_jury'))
    if request['schema']!='promptops-jury-input/1' or not isinstance(request['suite_sha'],str) or not _SHA.fullmatch(request['suite_sha']):
        raise OpsValidationError("jury schema and suite_sha are required")
    context=_context(context)
    vote=weighted_vote(request['votes'],quorum=request.get('quorum',2),threshold=request.get('threshold',.6))
    score=None
    if 'score_jury' in request:
        entry=_object(request['score_jury'],('candidate_id','scores'),('pass_score','max_spread'))
        _text(entry['candidate_id'],'score candidate')
        if entry['candidate_id']=='abstain':raise OpsValidationError('abstain cannot receive candidate scores')
        score=score_jury(entry['scores'],pass_score=entry.get('pass_score',.7),max_spread=entry.get('max_spread',.35))
        score={**score,'candidate_id':entry['candidate_id']}
    reasons=[]
    if vote['decision']!='accepted':reasons.append('vote_'+vote.get('reason','threshold'))
    if score is not None:
        if score['decision']!='pass':reasons.append('score_'+score['decision'])
        if score['candidate_id']!=vote.get('choice'):reasons.append('score_candidate_mismatch')
    if context is not None:
        if request['suite_sha']!=context['suite_sha']:raise OpsValidationError('jury belongs to another suite')
        choices={row['choice'] for row in request['votes'] if row['choice']!='abstain'}
        if not choices<=set(context['candidate_ids']):raise OpsValidationError('jury contains unknown candidates')
        if score and score['candidate_id'] not in context['candidate_ids']:raise OpsValidationError('score candidate is unknown')
        if context['selected_candidate'] is None or vote.get('choice')!=context['selected_candidate']:
            reasons.append('routing_candidate_mismatch')
    result={'schema_version':OPS_SCHEMA_VERSION,'kind':'jury_assessment','policy':'weighted_votes_with_optional_median',
        'input':request,'input_sha':_digest(request),'context':context,'weighted_vote':vote,'score_jury':score,
        'gate_passed':not reasons,'reasons':reasons,'provider_called':False,'juror_identity_verified':False,
        'provenance':'not-verified','mode':'supplied_judgments'}
    # Reparse the validated input to prevent subsequent caller mutations from
    # changing the returned artifact after its digest was calculated.
    result=json.loads(json.dumps(result,allow_nan=False))
    result['artifact_sha']=_digest(result)
    return result


def compare_cases(cases):
    """Source-compatible exact/contains/JSON transitions through native judges."""
    _bounded(cases);_array(cases,'cases',1,MAX_CASES)
    rows=[];seen=set()
    for case in cases:
        _object(case,('id','baseline','candidate','expected'),('mode',))
        identifier=_text(case['id'],'case id')
        if identifier in seen:raise OpsValidationError('case ids must be unique')
        seen.add(identifier)
        mode=case.get('mode','exact')
        if mode not in {'exact','contains','json'}:raise OpsValidationError('unknown case mode')
        for name in ('baseline','candidate'):
            if not isinstance(case[name],str) or len(case[name].encode())>8192:
                raise OpsValidationError('case responses must be bounded strings')
        if mode!='json' and not isinstance(case['expected'],str):
            raise OpsValidationError('text case expected must be a string')
        if mode=='json':
            # Source raises on invalid JSON. Reject duplicates/nonfinite values
            # as a documented stronger input rule, before the canonical judge.
            for name in ('baseline','candidate'):
                try:json.loads(case[name],object_pairs_hook=_pairs,parse_constant=_reject_constant)
                except (ValueError,RecursionError) as error:raise OpsValidationError('invalid case JSON') from error
        spec=JudgeSpec('json_equal' if mode=='json' else mode,case_sensitive=True,normalize_whitespace=False)
        before=judge(spec,case['expected'],case['baseline']).passed
        after=judge(spec,case['expected'],case['candidate']).passed
        status='regression' if before and not after else ('improvement' if after and not before else 'unchanged')
        rows.append({'id':identifier,'status':status})
    return {'results':rows,'regressions':sum(row['status']=='regression' for row in rows)}


def assess_cases(request):
    _bounded(request);_object(request,('schema','cases'))
    if request['schema']!='promptops-cases-input/1':raise OpsValidationError('case schema required')
    result={'schema_version':OPS_SCHEMA_VERSION,'kind':'case_regression',
        'input':json.loads(json.dumps(request,allow_nan=False)),'input_sha':_digest(request),
        'comparison':compare_cases(request['cases']),'provider_called':False,'provenance':'not-verified'}
    result['gate_passed']=result['comparison']['regressions']==0
    result['artifact_sha']=_digest(result)
    return result


def verify_judgment(artifact):
    """Replay rules from embedded bounded input, not just its content hash."""
    _bounded(artifact,2*MAX_INPUT_BYTES)
    if not isinstance(artifact,dict):raise OpsValidationError('judgment artifact must be an object')
    if artifact.get('kind')=='jury_assessment':
        expected=assess_jury(artifact.get('input'),context=artifact.get('context'))
    elif artifact.get('kind')=='case_regression':expected=assess_cases(artifact.get('input'))
    else:raise OpsValidationError('unknown judgment kind')
    if artifact!=expected:raise OpsValidationError('judgment replay differs from artifact')
