#!/usr/bin/env python3
"""Fail closed validator; it recomputes every V3 identity rather than trusting a manifest."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRE=ROOT.parent/'stock_awq_holdout_contract_seal'; DEV=ROOT.parent/'quality_gate_calibration'/'executable_development_v2'; ADJ=ROOT.parent/'bf16_v2_capture_adjudication'; BRIDGE=ROOT.parent/'bf16_vllm_quality_bridge'; RUNNER=ROOT.parents[2]/'campaign_100'/'nebius'/'vllm_v2_quality_runner.py'
def sha(b): return hashlib.sha256(b).hexdigest()
def fsha(p): return sha(Path(p).read_bytes())
def canon(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def tokenizer_binding(path):
 raw=json.loads((path/'tokenizer.json').read_text()); raw['truncation']=None
 return {'root':str(path),'files':{x:fsha(path/x) for x in ('tokenizer.json','tokenizer_config.json','chat_template.jinja')},'canonical_tokenizer_sha256_truncation_disabled':sha(canon(raw))}
def fail(x): raise ValueError(x)
def payloads(row):
 keys=('case_id','prompt','history','synthetic_context','teacher_forced_text','expected','tests','scorer','transport')
 return {sha(canon({k:row[k] for k in keys if k in row}))}
def validate(root=ROOT):
 out=root/'sealed_holdout_v3'; m=json.loads((out/'MANIFEST.json').read_text()); rows=[json.loads(x) for x in (out/'holdout.jsonl').read_text().splitlines()]; policy=json.loads((root/'POST_DEVELOPMENT_QUALITY_POLICY_V2.json').read_text())
 if m.get('status')!='HOLDOUT_CONTRACT_RESEALED' or policy.get('status')!='HOLDOUT_CONTRACT_RESEALED': fail('status')
 pairs={'holdout_sha256':out/'holdout.jsonl','builder_sha256':root/'build_resealed_holdout.py','policy_sha256':root/'POST_DEVELOPMENT_QUALITY_POLICY_V2.json','scorer_sha256':root/'score_resealed_holdout.py','validator_sha256':root/'validate_resealed_holdout.py','executable_bridge_sha256':root/'executable_capture_bridge.py'}
 for k,p in pairs.items():
  if m.get(k)!=fsha(p): fail(k)
 for k,p in [('holdout_sha256',PRE/'sealed_holdout_v2'/'holdout.jsonl'),('manifest_sha256',PRE/'sealed_holdout_v2'/'MANIFEST.json'),('builder_sha256',PRE/'build_holdout.py'),('policy_sha256',PRE/'POST_DEVELOPMENT_QUALITY_POLICY.json')]:
  if m['predecessor'].get(k)!=fsha(p): fail('predecessor_'+k)
 for k,p in [('fixture_sha256',DEV/'development.jsonl'),('manifest_sha256',DEV/'MANIFEST.json')]:
  if m['development'].get(k)!=fsha(p): fail('development_'+k)
 if m['bf16_archive']['adjudication_sha256']!=fsha(ADJ/'BF16_V2_CONTROL_ADJUDICATION.json') or m['bf16_archive']['ceilings_sha256']!=fsha(ADJ/'BF16_V2_NLL_CEILINGS.json') or m['bf16_archive']['bridge_sha256']!=fsha(BRIDGE/'BF16_VLLM_BRIDGE_2026-07-15.json'): fail('adjudication_binding')
 if m['runner']['sha256']!=fsha(RUNNER): fail('runner_binding')
 if m['checkpoints'].get('bf16_manifest')!=tokenizer_binding(Path('/root/.cache/glm47flash-bf16-33faccf4')) or m['checkpoints'].get('awq_manifest')!=tokenizer_binding(Path('/root/.cache/glm47flash-awq-ab31d120')): fail('tokenizer_checkpoint_binding')
 runtime=Path(m['encoding_runtime'].get('runtime_root',''))
 if not runtime.is_dir(): fail('encoding_runtime')
 sys.path.insert(0,str(runtime)); import tokenizers
 if tokenizers.__version__ != m['encoding_runtime'].get('version'): fail('encoding_runtime_version')
 if len(rows)!=36 or len({r['case_id'] for r in rows})!=36 or {r['category'] for r in rows}!={'tool_call','coding','long_context_retrieval','multi_turn_continuation','teacher_forced_loss','serving_correctness'} or any(sum(r['category']==c for r in rows)!=6 for c in {r['category'] for r in rows}): fail('geometry')
 dev=[json.loads(x) for x in (DEV/'development.jsonl').read_text().splitlines()]
 if set().union(*(payloads(r) for r in rows)) & set().union(*(payloads(r) for r in dev)): fail('payload_overlap')
 for r in rows:
  if r['category']=='serving_correctness' and r.get('deterministic_repetitions') != 1: fail('repetition_geometry')
  if r.get('content_sha256')!=sha(canon({k:v for k,v in r.items() if k!='content_sha256'})): fail('row_integrity')
  p=r.get('token_pair',{}); ids=p.get('bf16_token_ids')
  if ids!=p.get('awq_token_ids') or not all(isinstance(x,int) for x in ids) or r.get('token_sequence_sha256')!=__import__('score_resealed_holdout').token_hash(ids): fail('token_ids_hash')
  if r['runtime_token_sequence'].get('first_token')!='unscored_for_prompt_logprobs_but_included_in_returned_id_list_and_hash': fail('first_token_rule')
 req=m['request_contract'];
 if req['chat'] != {'endpoint':'/v1/chat/completions','stream':False,'temperature':0,'top_p':1,'max_tokens':256,'seed':470200,'chat_template_kwargs':{'enable_thinking':False},'timeout_seconds':300,'finish_reason_forbidden':'length'} or req['loss'] != {'endpoint':'/v1/completions','stream':False,'temperature':0,'max_tokens':1,'prompt_logprobs':1,'return_token_ids':True,'timeout_seconds':300}: fail('request_contract')
 return {'pass':True,'cases':36}
def main(): print(json.dumps(validate(),sort_keys=True))
if __name__=='__main__': main()
