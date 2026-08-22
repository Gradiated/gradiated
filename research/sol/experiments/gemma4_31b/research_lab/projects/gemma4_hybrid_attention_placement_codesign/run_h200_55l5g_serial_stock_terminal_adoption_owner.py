#!/usr/bin/env python3
"""Adopt a consumed serial stock terminal and release its drain-fenced claim."""
from __future__ import annotations
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parent; LAB=R.parents[1]; P='gemma4_hybrid_attention_placement_codesign'
B=R/'DIRECTOR_H200_55L5G_ENDPOINT_SERIAL_STOCK_TERMINAL_ADOPTION_RELEASE_20260729T0240Z.json'; X=R/'DIRECTOR_H200_55L5G_ENDPOINT_SERIAL_STOCK_TERMINAL_ADOPTION_RELEASE_START_EXTENSION_20260729T0248Z.json'; A=R/'artifacts/h200-55l5g-serial-stock-terminal-adoption-20260729t0240z'; T='HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text())
def atom(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f: json.dump(x,f,sort_keys=True,indent=2);f.write('\n');q=Path(f.name)
 json.loads(q.read_text());q.replace(p)
def pool(*a): return subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*a],text=True,capture_output=True,env={**os.environ,'PYTHONPATH':str(R.parents[5]/'factory'/'src')})
def call(cmd,timeout,label):
 z=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout);atom(A/'commands'/f'{label}.json',{'command':cmd,'returncode':z.returncode,'stdout':z.stdout[-12000:],'stderr':z.stderr[-12000:]});return z
def main():
 b,x=load(B),load(X)
 if sha(B)!='8c46dbb8857cf41f77f1f6a011f07d63c668f5bb4959f80e8017ab04ea269562' or sha(X)!='02ca059e1d321574e7559cbebd0b5c93217c50d25cbf2a588eca87cc884a4762': raise RuntimeError('binding_hash')
 stock=R/'artifacts/h200-55l5g-endpoint-stock-recovery-candidate-transition-20260729t0235z/STOCK_ARM.json'; census=R/'artifacts/h200-55l5g-endpoint-stock-recovery-candidate-transition-20260729t0235z/CANDIDATE_CENSUS_AFTER_CANCELLATION.txt'
 if sha(stock)!='1f2092ff8410cd42b90adbf404d7ceead729c1c0a75da6cacc668822a6f5d382' or sha(census)!='6e956fda779561bf76721a21fc7df7badb818ade4c94715cface4c7ed8c603db': raise RuntimeError('local_adoption_hash')
 s=load(stock)
 if not(s.get('arm')=='stock' and s.get('complete_requests')==32 and s.get('failures')==0): raise RuntimeError('stock_ledger')
 shown=pool('show','--bench',b['live_claim']['bench_id']); bench=json.loads(shown.stdout);cl=bench.get('claim') or {};expected=b['live_claim']['expected_claimed_at_utc']
 if shown.returncode or cl.get('project')!=P or cl.get('claimed_at')!=expected or not bench.get('drain_after_release'): raise RuntimeError('claim_or_drain')
 if pool('heartbeat','--project',P,'--bench',bench['id']).returncode: raise RuntimeError('heartbeat')
 rsrc=bench['resource'];host=f"{rsrc['ssh_user']}@{rsrc['public_ipv4']}";ssh=['/usr/bin/ssh','-i',rsrc['identity_file'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={rsrc['known_hosts_namespace']}",host]
 # Census only; it neither launches nor requests the candidate.
 z=call([*ssh,"sudo -n docker exec hybrid-55l5g sh -lc 'test ! -e /work/materialized-candidate-0235/CANDIDATE_SUBMISSION.json && test ! -e /work/materialized-candidate-0235/CANDIDATE_ARM.json'"],60,'candidate_census')
 if z.returncode: raise RuntimeError('candidate_evidence_present_or_unobservable')
 atom(A/'STOCK_ARM.json',s)
 terminal={'schema_version':1,'classification':'invalid_scope_serial_stock_consumed_candidate_unsubmitted','science_consumed':True,'stock_science_consumed':True,'candidate_science_consumed':False,'quality_preservation_claimed':False,'service_time_delta_seconds_per_request':None,'stock':s,'driver_scope_failure':b['driver_scope_failure'],'binding_sha256':sha(B),'extension_sha256':sha(X),'claim_started_at_utc':expected}
 atom(A/T,terminal);atom(R/T,terminal)
 contents={'project':P,'state':'invalid_scope_serial_stock_consumed_candidate_unsubmitted','stock_terminal_sha256':sha(A/'STOCK_ARM.json'),'candidate_submission':False,'candidate_arm':False,'drain_after_release':True,'checkpoint':b['scientific_identity']['packet_sha256'],'terminal':str(A/T)};atom(A/'BENCH_CONTENTS.json',contents)
 released=pool('release','--project',P,'--bench',bench['id'],'--expected-claimed-at',expected,'--condition','maintenance','--contents',str(A/'BENCH_CONTENTS.json'))
 atom(A/'RELEASE.json',{'returncode':released.returncode,'stdout':released.stdout,'stderr':released.stderr,'expected_claimed_at_utc':expected,'condition':'maintenance','drain_after_release_preserved':True})
 if released.returncode: raise RuntimeError('release_failed')
 status=load(R/'STATUS.json');status['active_session']=None;status['status']='terminal';status['terminal_path']=str(R/T);atom(R/'STATUS.json',status)
 return 0
if __name__=='__main__': raise SystemExit(main())
