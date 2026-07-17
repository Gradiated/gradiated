#!/usr/bin/env python3
import copy,json,shutil,tempfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent; sys.path.insert(0,str(ROOT))
from validate_resealed_holdout import validate
from score_resealed_holdout import score,token_hash
from build_resealed_holdout import build
def rows(): return [json.loads(x) for x in (ROOT/'sealed_holdout_v3/holdout.jsonl').read_text().splitlines()]
def evidence(rs):
 d={m:{o:{} for o in range(3)} for m in ('bf16','awq')}
 for m in d:
  for o in d[m]:
   for r in rs:
    ids=r['token_pair'][f'{m}_token_ids']; x={'pass':True,'token_ids':ids,'token_sequence_sha256':token_hash(ids)}
    if r['category']=='teacher_forced_loss': x['prompt_logprobs']=[None]+[-1.0]*(len(ids)-1)
    d[m][o][r['case_id']]=x
 return d
def rejects(mut):
 x=evidence(rows()); mut(x)
 try: score(x,rows())
 except ValueError:return
 raise AssertionError('scorer mutation accepted')
def vreject(mut):
 with tempfile.TemporaryDirectory() as t:
  p=Path(t)/'p'; shutil.copytree(ROOT,p); mut(p)
  try: validate(p)
  except ValueError:return
  raise AssertionError('validator mutation accepted')
def main():
 before=[(ROOT/'sealed_holdout_v3'/x).read_bytes() for x in ('holdout.jsonl','MANIFEST.json')]; build(); assert before==[(ROOT/'sealed_holdout_v3'/x).read_bytes() for x in ('holdout.jsonl','MANIFEST.json')]
 rs=rows(); assert validate()['pass']; assert score(evidence(rs),rs)['pass']
 rejects(lambda x: [x['bf16'][o].__setitem__(f'holdout_tool_call_{i:02d}',{**x['bf16'][o][f'holdout_tool_call_{i:02d}'],'pass':False}) for o in range(3) for i in (1,2)])
 rejects(lambda x: [x['awq'][o].__setitem__('holdout_tool_call_01',{**x['awq'][o]['holdout_tool_call_01'],'pass':False}) for o in range(3)])
 rejects(lambda x: x['awq'][0]['holdout_teacher_forced_loss_01'].update(prompt_logprobs=[None]+[-2.0]*(len(x['awq'][0]['holdout_teacher_forced_loss_01']['token_ids'])-1)))
 rejects(lambda x: x['awq'][1]['holdout_tool_call_01'].update(token_ids=[9]))
 rejects(lambda x: [x['awq'][o].__setitem__(f'holdout_{c}_01',{**x['awq'][o][f'holdout_{c}_01'],'pass':False}) for o in range(3) for c in ('tool_call','coding','long_context_retrieval','multi_turn_continuation','teacher_forced_loss','serving_correctness')])
 vreject(lambda p:(p/'POST_DEVELOPMENT_QUALITY_POLICY_V2.json').write_text('{}'))
 vreject(lambda p:(p/'sealed_holdout_v3'/'holdout.jsonl').write_text((p/'sealed_holdout_v3'/'holdout.jsonl').read_text().replace('aurora','overlap',1)))
 vreject(lambda p:(p/'sealed_holdout_v3'/'MANIFEST.json').write_text((p/'sealed_holdout_v3'/'MANIFEST.json').read_text().replace('/v1/chat/completions','/drift',1)))
 for needle in ('"builder_sha256":"','"adjudication_sha256":"','"canonical_tokenizer_sha256_truncation_disabled":"','"sha256":"'):
  def drift(p, needle=needle):
   f=p/'sealed_holdout_v3'/'MANIFEST.json'; f.write_text(f.read_text().replace(needle,needle+'0',1))
  vreject(drift)
 print(json.dumps({'pass':True,'mutations_rejected':11},sort_keys=True))
if __name__=='__main__':main()
