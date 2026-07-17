#!/usr/bin/env python3
"""Deterministic, fail-closed scorer for V3 synthetic or future captures."""
import json, math, random
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def token_hash(ids):
 import hashlib
 return hashlib.sha256(canon({"serialization":"json_utf8_canonical_array_of_int32_token_ids_v1","token_ids":ids})).hexdigest()
def q025(xs): return sorted(xs)[math.ceil(.025*len(xs))-1]
def score(evidence, rows):
 cats=sorted({r['category'] for r in rows}); byid={r['case_id']:r for r in rows}; expected=set(byid)
 if set(evidence)!= {'bf16','awq'}: raise ValueError('models')
 for model in evidence:
  if sorted(evidence[model]) != [0,1,2]: raise ValueError('capture_ordinals')
  for ordinal in range(3):
   if set(evidence[model][ordinal]) != expected: raise ValueError('case_coverage')
   for cid,x in evidence[model][ordinal].items():
    r=byid[cid]
    if x.get('token_ids') != r['token_pair'][f'{model}_token_ids'] or x.get('token_sequence_sha256') != token_hash(x.get('token_ids')) or x['token_sequence_sha256'] != r['token_sequence_sha256']: raise ValueError('token_ids_hash')
    if not isinstance(x.get('pass'),bool): raise ValueError('binary_score')
    if r['category']=='teacher_forced_loss':
     lp=x.get('prompt_logprobs')
     if not isinstance(lp,list) or len(lp)!=len(x['token_ids']) or lp[0] is not None or any(not isinstance(z,(int,float)) or not math.isfinite(z) for z in lp[1:]): raise ValueError('nll_alignment')
 for ordinal in range(3):
  for c in cats:
   if sum(evidence['bf16'][ordinal][r['case_id']]['pass'] for r in rows if r['category']==c)<5: raise ValueError('bf16_per_capture_floor')
 ceilings={}
 for r in rows:
  if r['category']=='teacher_forced_loss':
   ns=[sum(-x for x in evidence['bf16'][o][r['case_id']]['prompt_logprobs'][1:])/(len(evidence['bf16'][o][r['case_id']]['prompt_logprobs'])-1) for o in range(3)]
   ceilings[r['case_id']]=1.05*max(ns)
   for o in range(3):
    n=sum(-x for x in evidence['awq'][o][r['case_id']]['prompt_logprobs'][1:])/(len(evidence['awq'][o][r['case_id']]['prompt_logprobs'])-1)
    if n>ceilings[r['case_id']]: raise ValueError('nll_ceiling')
 deltas={r['case_id']:sum(int(evidence['awq'][o][r['case_id']]['pass'])-int(evidence['bf16'][o][r['case_id']]['pass']) for o in range(3))/3 for r in rows}
 for c in cats:
  if sum(deltas[r['case_id']] for r in rows if r['category']==c)/6 < -1/6: raise ValueError('critical_regression')
 rng=random.Random(470236); reps=[]
 for _ in range(10000): reps.append(sum(sum(deltas[[r['case_id'] for r in rows if r['category']==c][rng.randrange(6)]] for _ in range(6))/6 for c in cats)/6)
 lower=q025(reps)
 if lower < -.05: raise ValueError('bootstrap_lower_bound')
 return {'pass':True,'bootstrap_lower_bound':lower,'nll_ceilings':ceilings}
def main():
 rows=[json.loads(x) for x in (ROOT/'sealed_holdout_v3/holdout.jsonl').read_text().splitlines()]
 print(json.dumps(score(json.load(open(__import__('sys').argv[1])),rows),sort_keys=True))
if __name__=='__main__': main()
