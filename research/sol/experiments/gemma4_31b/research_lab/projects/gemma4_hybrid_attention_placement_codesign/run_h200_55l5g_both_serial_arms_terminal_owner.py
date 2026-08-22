#!/usr/bin/env python3
"""Persist the two consumed serial arms without a comparator delta, then release."""
import hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parent; L=R.parents[1]; P='gemma4_hybrid_attention_placement_codesign'; B=R/'DIRECTOR_H200_55L5G_ENDPOINT_BOTH_SERIAL_ARMS_TERMINAL_RELEASE_20260729T0254Z.json'; A=R/'artifacts/h200-55l5g-both-serial-arms-terminal-20260729t0254z'; T='HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def atom(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f:json.dump(x,f,sort_keys=True,indent=2);f.write('\n');q=Path(f.name)
 json.loads(q.read_text());q.replace(p)
def pool(*a):return subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(L),*a],text=True,capture_output=True,env={**os.environ,'PYTHONPATH':str(R.parents[5]/'factory'/'src')})
def main():
 b=load(B)
 if sha(B)!='d57d5afa4d982d8e05b9813b6c1805983b5abce543d0dc15767e23c1f2f6c671':raise RuntimeError('binding_hash')
 arms=b['consumed_arms']; paths={'stock':R/arms['stock']['path'],'candidate_submission':R/arms['candidate_submission']['path'],'candidate':R/arms['candidate']['path'],'conflict':R/b['cause']['candidate_consumption_conflict_path']}
 wants={'stock':arms['stock']['sha256'],'candidate_submission':arms['candidate_submission']['sha256'],'candidate':arms['candidate']['sha256'],'conflict':b['cause']['candidate_consumption_conflict_sha256']}
 if any(sha(paths[k])!=wants[k] for k in wants):raise RuntimeError('evidence_hash')
 stock,csub,cand=load(paths['stock']),load(paths['candidate_submission']),load(paths['candidate'])
 if not(stock.get('complete_requests')==cand.get('complete_requests')==32 and stock.get('failures')==cand.get('failures')==0 and csub.get('science_started') is True):raise RuntimeError('ledger')
 shown=pool('show','--bench',b['live_claim']['bench_id']);bench=json.loads(shown.stdout);claim=bench.get('claim') or {};expected=b['live_claim']['expected_claimed_at_utc']
 if shown.returncode or claim.get('project')!=P or claim.get('claimed_at')!=expected or not bench.get('drain_after_release'):raise RuntimeError('claim')
 if pool('heartbeat','--project',P,'--bench',bench['id']).returncode:raise RuntimeError('heartbeat')
 r=bench['resource'];ssh=['/usr/bin/ssh','-i',r['identity_file'],'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={r['known_hosts_namespace']}",f"{r['ssh_user']}@{r['public_ipv4']}"]
 census=subprocess.run([*ssh,'sudo -n docker ps --format "{{.Names}} {{.Image}} {{.Status}}"; nvidia-smi --query-gpu=name,memory.used --format=csv,noheader'],text=True,capture_output=True,timeout=60);atom(A/'REMOTE_CENSUS.json',{'returncode':census.returncode,'stdout':census.stdout[-12000:],'stderr':census.stderr[-12000:]})
 for k,p in paths.items(): atom(A/f'{k.upper()}.json',load(p)) if k!='conflict' else atom(A/'CONFLICT.json',load(p))
 terminal={'schema_version':1,'classification':'invalid_scope_serial_stock_and_candidate_consumed','science_consumed':True,'stock_science_consumed':True,'candidate_science_consumed':True,'quality_preservation_claimed':False,'comparator_delta':None,'comparator_delta_allowed':False,'scope_disposition':b['scope_disposition'],'stock':stock,'candidate_submission':csub,'candidate':cand,'binding_sha256':sha(B),'claim_started_at_utc':expected};atom(A/T,terminal);atom(R/T,terminal)
 contents={'project':P,'state':terminal['classification'],'stock_sha256':wants['stock'],'candidate_submission_sha256':wants['candidate_submission'],'candidate_sha256':wants['candidate'],'drain_after_release':True,'remote_census':str(A/'REMOTE_CENSUS.json'),'terminal':str(A/T)};atom(A/'BENCH_CONTENTS.json',contents)
 rel=pool('release','--project',P,'--bench',bench['id'],'--expected-claimed-at',expected,'--condition','maintenance','--contents',str(A/'BENCH_CONTENTS.json'));atom(A/'RELEASE.json',{'returncode':rel.returncode,'stdout':rel.stdout,'stderr':rel.stderr,'expected_claimed_at_utc':expected,'condition':'maintenance','drain_after_release_preserved':True})
 if rel.returncode:raise RuntimeError('release')
 s=load(R/'STATUS.json');s['active_session']=None;s['status']='terminal';s['terminal_path']=str(R/T);atom(R/'STATUS.json',s)
if __name__=='__main__':main()
