#!/usr/bin/env python3
"""Candidate-only continuation after the bound stock arm was consumed."""
from __future__ import annotations
import hashlib, json, os, shlex, subprocess, sys, tempfile, threading, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
LAB=ROOT.parents[1]
PROJECT='gemma4_hybrid_attention_placement_codesign'
BIND=ROOT/'DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_STOCK_RECOVERY_CANDIDATE_TRANSITION_20260729T0235Z.json'
EXEC=ROOT/'DIRECTOR_H200_55L5G_ENDPOINT_EXECUTION_20260729T0047Z.json'
ART=ROOT/'artifacts/h200-55l5g-endpoint-stock-recovery-candidate-transition-20260729t0235z'
TERM='HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json'

def load(p): return json.loads(Path(p).read_text())
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atom(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f:
  json.dump(x,f,sort_keys=True,indent=2);f.write('\n');t=Path(f.name)
 json.loads(t.read_text());t.replace(p)
def run(cmd,timeout,label):
 r=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
 atom(ART/'commands'/f'{label}.json',{'command':cmd,'returncode':r.returncode,'stdout':r.stdout[-16000:],'stderr':r.stderr[-16000:]})
 return r
def pool(*a):
 return subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*a],text=True,capture_output=True,env={**os.environ,'PYTHONPATH':str(ROOT.parents[5]/'factory'/'src')})
def fail(error,consumed=False):
 atom(ART/'REPAIR_READY.json',{'classification':'recoverable_candidate_transition_failure','science_consumed':consumed,'exception':repr(error),'repair_deadline_utc':'2026-07-29T03:25:00Z'})
 return 72
def main():
 b=load(BIND); e=load(EXEC); c=b['scientific_contract']; stock=b['consumed_stock_evidence']
 if digest(BIND)!='aea1d6c24718a6490c015b2dc0d21b7dee56852bb0515f992f0b6bf2f8d215ff': raise RuntimeError('binding_hash')
 if digest(EXEC)!=c['execution_binding_sha256'] or digest(ROOT/'h200_55l5g_exact_workload_adapter.py')!=c['adapter_sha256'] or digest(ROOT/'qualified_c32_request_payloads.json')!=c['payloads_sha256']: raise RuntimeError('immutable_input_hash')
 shown=pool('show','--bench',b['live_claim']['bench_id'])
 if shown.returncode: raise RuntimeError('pool_show')
 bench=load_text= json.loads(shown.stdout); claim=bench.get('claim') or {}
 if claim.get('project')!=PROJECT or claim.get('claimed_at')!=b['live_claim']['expected_claimed_at_utc']: raise RuntimeError('claim_generation')
 if pool('heartbeat','--project',PROJECT,'--bench',bench['id']).returncode: raise RuntimeError('heartbeat')
 ART.mkdir(parents=True,exist_ok=True)
 rsrc=bench['resource'];host=f"{rsrc['ssh_user']}@{rsrc['public_ipv4']}";key=rsrc['identity_file'];known=rsrc['known_hosts_namespace']
 ssh=['/usr/bin/ssh','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',f'UserKnownHostsFile={known}',host]
 stop=threading.Event()
 def beats():
  while not stop.wait(35): pool('heartbeat','--project',PROJECT,'--bench',bench['id'])
 threading.Thread(target=beats,daemon=True).start()
 try:
  remote=e['runtime_destinations']['remote_root'];packet=remote+'/packet';stock_remote=stock['remote_stock_path']
  existing=run([*ssh,"sudo -n docker exec hybrid-55l5g test -e /work/materialized-candidate-0235/CANDIDATE_ARM.json || sudo -n docker exec hybrid-55l5g test -e /work/materialized-candidate-0235/CANDIDATE_SUBMISSION.json"],30,'candidate_census')
  if existing.returncode==0: raise RuntimeError('prior_candidate_evidence_exists')
  got=run([*ssh,f"sudo -n docker exec hybrid-55l5g cat {shlex.quote(stock_remote)}"],60,'stock_retrieve')
  if got.returncode: raise RuntimeError('stock_retrieve')
  if hashlib.sha256(got.stdout.encode()).hexdigest()!=stock['remote_stock_sha256']: raise RuntimeError('stock_hash')
  s=json.loads(got.stdout)
  if not (s.get('arm')=='stock' and s.get('complete_requests')==32 and s.get('failures')==0): raise RuntimeError('stock_ledger')
  atom(ART/'STOCK_ARM.json',s); atom(ART/'STOCK_TERMINAL_ADOPTED.json',{'sha256':stock['remote_stock_sha256'],'remote_path':stock_remote,'science_consumed':True})
  candidate=ROOT/c['candidate_source_path']; adapter=ROOT/'h200_55l5g_exact_workload_adapter.py'; payloads=ROOT/'qualified_c32_request_payloads.json'
  # Packet is already exact; copy only mutable adapter/payload bytes when missing, never overwrite a mismatch.
  for local in (adapter,payloads):
   target=f'{packet}/{local.name}'; want=digest(local)
   check=run([*ssh,f"if test -e {shlex.quote(target)}; then sha256sum {shlex.quote(target)}; else true; fi"],30,f'packet_check_{local.name}')
   if check.stdout.strip() and check.stdout.split()[0]!=want: raise RuntimeError(f'packet_mismatch:{local.name}')
   if not check.stdout.strip():
    copy=run(['/usr/bin/scp','-i',key,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',f'UserKnownHostsFile={known}',str(local),f'{host}:{target}.part'],180,f'packet_copy_{local.name}')
    if copy.returncode: raise RuntimeError(f'packet_copy:{local.name}')
    final=run([*ssh,f"echo {want} {shlex.quote(target)}.part | sha256sum -c - && mv {shlex.quote(target)}.part {shlex.quote(target)}"],60,f'packet_finalize_{local.name}')
    if final.returncode: raise RuntimeError(f'packet_finalize:{local.name}')
  if digest(candidate)!=c['candidate_source_sha256']: raise RuntimeError('candidate_local_hash')
  mount='/usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py'
  proof=run([*ssh,f'sudo -n docker exec hybrid-55l5g sha256sum {mount}'],60,'candidate_source_proof_before_launch')
  state=run([*ssh,"sudo -n docker inspect --format '{{json .State}}' hybrid-55l5g"],30,'candidate_state_before_launch')
  activated=c['candidate_source_sha256'] in proof.stdout and '"Running":true' in state.stdout.replace(' ','')
  if not activated:
   checkpoint=e['runtime_destinations']['checkpoint'];image=e['runtime_destinations']['image']
   stopped=run([*ssh,'sudo -n docker rm -f hybrid-55l5g'],90,'stock_stop')
   if stopped.returncode: raise RuntimeError('stock_stop')
   launch=f"sudo -n docker run -d --name hybrid-55l5g --gpus all -p 30000:30000 -v {checkpoint}:/models/target:ro -v {packet}:/work -v {packet}/{candidate.name}:{mount}:ro {image} python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --dtype bfloat16 --tp-size 1 --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32"
   if run([*ssh,launch],180,'candidate_launch').returncode: raise RuntimeError('candidate_launch')
  for attempt in range(30):
   health=run([*ssh,'curl -fsS http://127.0.0.1:30000/health'],30,f'candidate_health_{attempt}')
   state=run([*ssh,"sudo -n docker inspect --format '{{json .State}}' hybrid-55l5g"],30,f'candidate_state_{attempt}')
   proof=run([*ssh,f'sudo -n docker exec hybrid-55l5g sha256sum {mount}'],30,f'candidate_source_proof_{attempt}')
   if health.returncode==0 and c['candidate_source_sha256'] in proof.stdout and '"Running":true' in state.stdout.replace(' ',''): break
   if '"Running":false' in state.stdout.replace(' ',''): raise RuntimeError('candidate_container_died')
   time.sleep(5)
  else: raise RuntimeError('candidate_activation_timeout')
  out='/work/materialized-candidate-0235'
  cmd=f"sudo -n docker exec -w /work hybrid-55l5g python3 /work/{adapter.name} --pair /work/run_h200_55l5g_endpoint_pair.py --payloads /work/{payloads.name} --identity /work/qualified_c32_workload.json --out {out} --arm candidate --url http://127.0.0.1:30000"
  called=run([*ssh,cmd],1800,'candidate_driver')
  sub=run([*ssh,f'sudo -n docker exec hybrid-55l5g cat {out}/CANDIDATE_SUBMISSION.json'],60,'candidate_submission_retrieve')
  if sub.returncode: raise RuntimeError('candidate_submission_missing')
  atom(ART/'CANDIDATE_SUBMISSION.json',json.loads(sub.stdout))
  arm=run([*ssh,f'sudo -n docker exec hybrid-55l5g cat {out}/CANDIDATE_ARM.json'],120,'candidate_arm_retrieve')
  if called.returncode or arm.returncode: raise RuntimeError('candidate_driver_or_terminal')
  cr=json.loads(arm.stdout);atom(ART/'CANDIDATE_ARM.json',cr)
  valid=cr.get('complete_requests')==32 and cr.get('failures')==0
  terminal={'schema_version':1,'classification':'scientific_terminal' if valid else 'invalid_candidate_arm','science_consumed':True,'quality_preservation_claimed':False,'stock':s,'candidate':cr,'service_time_delta_seconds_per_request':cr.get('service_seconds_per_request',0)-s.get('service_seconds_per_request',0),'binding_sha256':digest(BIND),'claim_started_at_utc':claim['claimed_at'],'candidate_source_sha256':c['candidate_source_sha256']}
  atom(ART/TERM,terminal);atom(ROOT/TERM,terminal)
  return 0 if valid else fail(RuntimeError('candidate_ledger'),True)
 except Exception as x: return fail(x,True)
 finally: stop.set()
if __name__=='__main__': raise SystemExit(main())
