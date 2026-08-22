#!/usr/bin/env python3
"""One bounded, durable owner for the director-bound H200 component call."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, shlex, subprocess, sys, tempfile, threading, time

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path('/root/workspace/research/factory/src')
NAME = 'gemma4_h200_fixed_floor_crossop_executor'
BENCH = 'h200-dflash-r3-computeinstance-e00t5s028ts52zp215'
RATE = 2.45

def now(): return dt.datetime.now(dt.UTC)
def iso(x=None): return (x or now()).isoformat().replace('+00:00','Z')
def stamp(x): return dt.datetime.fromisoformat(x.replace('Z','+00:00'))
def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def atomic(p,v):
    p=pathlib.Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False,prefix='.'+p.name) as f:
        json.dump(v,f,indent=2,sort_keys=True); f.write('\n'); t=f.name
    json.loads(pathlib.Path(t).read_text()); os.replace(t,p)
def run(cmd, *, timeout=30, env=None):
    return subprocess.run(cmd,text=True,capture_output=True,timeout=timeout,check=False,env=env)
def pool(*args, timeout=30):
    return run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*args],timeout=timeout,env={**os.environ,'PYTHONPATH':str(FACTORY)})
def need(ok, label):
    if not ok: raise RuntimeError(label)

class Heartbeat:
  def __init__(self, claimed_at, root): self.claimed_at,self.root,self.stop=claimed_at,root,threading.Event()
  def __enter__(self):
    def loop():
      while not self.stop.wait(30):
        r=pool('heartbeat','--project',NAME,'--bench',BENCH,'--expected-claimed-at',self.claimed_at)
        with (self.root/'heartbeat.log').open('a') as f: f.write(json.dumps({'at_utc':iso(),'rc':r.returncode,'stderr':r.stderr[-800:]})+'\n')
    self.t=threading.Thread(target=loop,daemon=True); self.t.start(); return self
  def __exit__(self,*_): self.stop.set(); self.t.join(5)

def main():
  ap=argparse.ArgumentParser(); ap.add_argument('--execution-binding',type=pathlib.Path,required=True); ap.add_argument('--artifact-root',type=pathlib.Path,required=True); a=ap.parse_args()
  root=a.artifact_root.resolve(); root.mkdir(parents=True,exist_ok=True)
  b=json.loads(a.execution_binding.read_text()); director=PROJECT/'DIRECTOR_FIXED_FLOOR_CROSSOP_H200_EXECUTION_20260730T0355Z.json'
  atomic(root/'OWNER_PROGRESS.json',{'phase':'preclaim','at_utc':iso()})
  need(digest(director)==b['director_binding_sha256'],'director_binding_hash')
  need(b['owner_sha256']==digest(PROJECT/'run_fixed_floor_crossop_h200_owner.py'),'owner_hash')
  for row in b['bound_files']:
    need(digest(PROJECT/row['path'])==row['sha256'],'bound_file:'+row['path'])
  deadline=stamp(b['absolute_release_deadline_utc']); need(now()<stamp(b['claim_start_by_utc']),'claim_fence_expired')
  show=pool('show','--bench',BENCH); need(show.returncode==0,'bench_show'); bench=json.loads(show.stdout)
  need(bench['status']=='available' and bench['claim'] is None,'bench_unavailable')
  r=bench['resource']; need(r['gpu_uuid']==b['gpu_uuid'],'gpu_uuid'); need(r['ssh_ed25519_fingerprint']==b['ssh_fingerprint'],'ssh_fingerprint'); need(bench['lifecycle']['watchdog']['main_pid']==506236,'watchdog')
  claim=pool('claim','--project',NAME,'--bench',BENCH,'--lease-seconds','1200'); need(claim.returncode==0,'claim:'+claim.stderr[-500:]); bench=json.loads(claim.stdout); claimed=bench['claim']['claimed_at']
  atomic(root/'CLAIM.json',bench); atomic(root/'OWNER_PROGRESS.json',{'phase':'claimed','at_utc':iso(),'claimed_at':claimed})
  resource=bench['resource']; key=resource['ssh_identity_path']; known=resource['known_hosts_namespace']; target=f"{resource['ssh_user']}@{resource['public_ipv4']}"
  ssh_cmd=['ssh','-i',key,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',f'UserKnownHostsFile={known}','-o','ConnectTimeout=20',target]
  scp=['scp','-i',key,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',f'UserKnownHostsFile={known}']
  remote='/home/glmrunner/fixed-floor-crossop-executor'; remote_art=remote+'/artifacts/h200_exact_consumer'
  def ssh(command,label,cap=300):
    rr=run([*ssh_cmd,command],timeout=max(1,min(cap,int((deadline-now()).total_seconds()-30))))
    (root/(label+'.stdout')).write_text(rr.stdout); (root/(label+'.stderr')).write_text(rr.stderr); return rr
  terminal=None; invocation=None; condition='maintenance'; summary='owner_failed_before_terminal'
  with Heartbeat(claimed,root):
    try:
      need(ssh('mkdir -p '+shlex.quote(remote), 'mkdir',60).returncode==0,'remote_mkdir')
      for row in b['bound_files']:
        src=PROJECT/row['path']; tmp=remote+'/'+row['path']+'.part'; dst=remote+'/'+row['path']
        rr=run([*scp,str(src),target+':'+tmp],timeout=120); (root/('stage-'+row['path']+'.stderr')).write_text(rr.stderr); need(rr.returncode==0,'stage:'+row['path'])
        need(ssh(f"test \"$(sha256sum {shlex.quote(tmp)} | cut -d' ' -f1)\" = {row['sha256']} && mv -f {shlex.quote(tmp)} {shlex.quote(dst)}",'finalize-'+row['path'],60).returncode==0,'verify:'+row['path'])
      need(now()<stamp(b['scientific_launch_by_utc']),'launch_fence_expired')
      cmd=(f"mkdir -p {shlex.quote(remote_art)} && sudo -n docker run --rm --gpus all -v {shlex.quote(remote)}:{shlex.quote(str(PROJECT))} {shlex.quote(b['image'])} bash -lc {shlex.quote(b['remote_command'])}")
      atomic(root/'OWNER_PROGRESS.json',{'phase':'scientific_launch','at_utc':iso(),'claimed_at':claimed})
      rr=ssh(cmd,'scientific',max(60,int((deadline-now()).total_seconds()-45)))
      for name in ('TERMINAL.json','INVOCATION_STATE.json'):
        local=root/name; get=run([*scp,target+':'+remote_art+'/'+name,str(local)],timeout=90); (root/('get-'+name+'.stderr')).write_text(get.stderr)
      terminal_path=root/'TERMINAL.json'; invocation_path=root/'INVOCATION_STATE.json'
      invocation=json.loads(invocation_path.read_text()) if invocation_path.exists() else None
      terminal=json.loads(terminal_path.read_text()) if terminal_path.exists() else None
      atomic(root/'EXECUTION_CAPTURE.json',{'scientific_rc':rr.returncode,'invocation':invocation,'terminal_sha256':digest(terminal_path) if terminal_path.exists() else None})
      need(isinstance(terminal,dict) and len(terminal.get('cases',[]))==10,'incomplete_terminal')
      need(all(c.get('correctness',{}).get('qkv_vs_accepted_producer',{}).get('normalized_rmse',99)<=1e-5 and c.get('correctness',{}).get('cache_vs_unfused_consumer',{}).get('key_bytewise_equal') and c.get('correctness',{}).get('cache_vs_unfused_consumer',{}).get('value_bytewise_equal') for c in terminal['cases']),'oracle')
      condition='ready'; summary='complete_exact_ten_case_terminal:'+str(terminal.get('passed'))
    except Exception as e:
      atomic(root/'OWNER_FAILURE.json',{'at_utc':iso(),'error':str(e),'invocation':invocation,'terminal_present':terminal is not None})
      summary='typed_owner_boundary:'+str(e)
    seconds=max(0,(now()-stamp(claimed)).total_seconds()); spend=seconds*RATE/3600
    contents={'schema_version':1,'project':NAME,'role':'exact_h200_qkv_norm_rope_e5m2_cache_component_execution','state':'terminal_released','scientific_terminal':summary,'artifacts':str(root),'claim_seconds':seconds,'actual_spend_usd':spend,'server_state':'No retained container; image, source, caches preserved.'}
    atomic(root/'RELEASE_CONTENTS.json',contents)
    rel=pool('release','--project',NAME,'--bench',BENCH,'--expected-claimed-at',claimed,'--condition',condition,'--contents',str(root/'RELEASE_CONTENTS.json'))
    atomic(root/'RELEASE_EVIDENCE.json',{'rc':rel.returncode,'stdout':rel.stdout,'stderr':rel.stderr,'condition':condition})
    status=json.loads((PROJECT/'STATUS.json').read_text()); status.update({'status':'complete' if terminal else 'blocked','actual_spend_usd':spend,'active_session':None,'claim_allowed':False,'summary':summary,'terminal_artifact':str(root/'TERMINAL.json') if terminal else None}); atomic(PROJECT/'STATUS.json',status)
    atomic(root/'OWNER_PROGRESS.json',{'phase':'released','at_utc':iso(),'claim_seconds':seconds,'terminal_present':terminal is not None})
    return 0 if terminal else 76
if __name__=='__main__': raise SystemExit(main())
