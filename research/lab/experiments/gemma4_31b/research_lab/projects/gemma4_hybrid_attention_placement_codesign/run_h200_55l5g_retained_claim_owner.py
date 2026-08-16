#!/usr/bin/env python3
"""Durable no-claim adoption controller for the original hybrid lease."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,subprocess,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent; LAB=ROOT.parents[1]; PROJECT='gemma4_hybrid_attention_placement_codesign'; TERM='HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json'
def load(p): return json.loads(Path(p).read_text())
def atomic(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f: json.dump(v,f,indent=2,sort_keys=True);f.write('\n');q=Path(f.name)
 q.replace(p)
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pool(*x): return subprocess.run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*x],text=True,capture_output=True,env={**os.environ,'PYTHONPATH':str(ROOT.parents[5]/'factory'/'src')})
def main():
 a=argparse.ArgumentParser();a.add_argument('--authority',type=Path,required=True);a.add_argument('--artifact-root',type=Path,required=True);n=a.parse_args(); b=load(n.authority); art=n.artifact_root.resolve();art.mkdir(parents=True,exist_ok=False); c=b['claim']; inv=load(LAB/'runtime/gpus.json'); rows=inv['benches'].values() if isinstance(inv['benches'],dict) else inv['benches']; row=next(x for x in rows if x['id']==c['bench_id'])
 if not(c['adoption_allowed'] and not c['new_claim_allowed'] and row['claim']['project']==PROJECT and row['claim']['claimed_at']==c['expected_claimed_at_utc']): raise RuntimeError('original_claim_adoption_verification_failed')
 deadline=dt.datetime.fromisoformat(b['lifecycle']['release_by_utc'].replace('Z','+00:00'))
 files=[ROOT/'run_h200_55l5g_endpoint_runtime.py',ROOT/b['resident_inputs']['pair_source'],ROOT/b['resident_inputs']['candidate_source'],Path(b['resident_inputs']['workload']),ROOT/b['resident_inputs']['staging_artifact'],ROOT/b['resident_inputs']['candidate_install_artifact'],n.authority]
 atomic(art/'ADOPTION.json',{'claimed_at':c['expected_claimed_at_utc'],'hashes':{str(x.relative_to(ROOT)) if ROOT in x.parents else str(x):digest(x) for x in files}})
 initial=pool('heartbeat','--project',PROJECT,'--bench',c['bench_id'])
 atomic(art/'OWNER_HEARTBEAT.json',{'at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'returncode':initial.returncode,'stderr':initial.stderr[-1000:],'initial_before_runtime':True})
 if initial.returncode: raise RuntimeError('adoption_heartbeat_failed_before_runtime')
 stop=threading.Event()
 def beat():
  while not stop.wait(30): atomic(art/'OWNER_HEARTBEAT.json',{'at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'returncode':pool('heartbeat','--project',PROJECT,'--bench',c['bench_id']).returncode})
 threading.Thread(target=beat,daemon=True).start(); atomic(ROOT/'STATUS.json',{**load(ROOT/'STATUS.json'),'active_session':{'artifact_root':str(art),'bench_id':c['bench_id'],'expected_claimed_at_utc':c['expected_claimed_at_utc'],'deadline_utc':b['lifecycle']['release_by_utc'],'expected_terminal':TERM,'unit':os.environ['DETACHED_OWNER_STATE'],'pid':os.getpid(),'unit_manager':'pid','forward_progress':'original claim adopted; heartbeat restored; pair runtime started'}})
 try:
  remaining=(deadline-dt.datetime.now(dt.timezone.utc)).total_seconds()-30
  if remaining<=0: raise RuntimeError('release_deadline_before_runtime')
  r=subprocess.run([sys.executable,'run_h200_55l5g_endpoint_runtime.py','--authority',str(n.authority),'--phase','run-pair-and-retrieve','--artifact-root',str(art)],cwd=ROOT,text=True,capture_output=True,timeout=min(600,remaining));(art/'runtime.stdout.log').write_text(r.stdout);(art/'runtime.stderr.log').write_text(r.stderr);t=load(art/'retrieved'/TERM)
  if t.get('classification')!='scientific_terminal': raise RuntimeError('pair_not_interpretable')
  atomic(ROOT/TERM,t);contents=art/'BENCH_CONTENTS.json';atomic(contents,{'project':PROJECT,'checkpoint':'resident exact checkpoint','image':'resident pinned image','server_state':'no server remains','terminal':str(ROOT/TERM)});rel=pool('release','--project',PROJECT,'--bench',c['bench_id'],'--expected-claimed-at',c['expected_claimed_at_utc'],'--condition','ready','--contents',str(contents));(art/'release.stdout.log').write_text(rel.stdout);(art/'release.stderr.log').write_text(rel.stderr);return 0 if rel.returncode==0 else 72
 finally: stop.set()
if __name__=='__main__': raise SystemExit(main())
