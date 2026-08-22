#!/usr/bin/env python3
"""R2 retained-claim controller for the unchanged exact H200 component ledger."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, shlex, subprocess, sys, tempfile, threading, time

P=pathlib.Path(__file__).resolve().parent; LAB=P.parents[1]; FACTORY='/root/workspace/research/factory/src'; NAME='gemma4_h200_fixed_floor_crossop_executor'; BENCH='h200-dflash-r3-computeinstance-e00t5s028ts52zp215'; REPAIR='/root/workspace/research/factory/tools/repair-handshake'; RATE=2.45
def now(): return dt.datetime.now(dt.UTC)
def iso(v=None): return (v or now()).isoformat().replace('+00:00','Z')
def parse(v): return dt.datetime.fromisoformat(v.replace('Z','+00:00'))
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for x in iter(lambda:f.read(1<<20),b''): h.update(x)
 return h.hexdigest()
def atomic(p,v):
 p=pathlib.Path(p); p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False,prefix='.'+p.name) as f: json.dump(v,f,indent=2,sort_keys=True); f.write('\n'); q=f.name
 json.loads(pathlib.Path(q).read_text()); os.replace(q,p)
def call(x,timeout=60,env=None): return subprocess.run(x,text=True,capture_output=True,timeout=timeout,check=False,env=env)
def pool(*x): return call([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*x],env={**os.environ,'PYTHONPATH':FACTORY})
class HB:
 def __init__(s,root,claimed): s.root,s.claimed,s.stop=root,claimed,threading.Event()
 def __enter__(s):
  def f():
   while not s.stop.wait(30):
    r=pool('heartbeat','--project',NAME,'--bench',BENCH,'--expected-claimed-at',s.claimed)
    with (s.root/'heartbeat.log').open('a') as h:h.write(json.dumps({'at_utc':iso(),'rc':r.returncode,'stderr':r.stderr[-500:]})+'\n')
  s.t=threading.Thread(target=f,daemon=True);s.t.start();return s
 def __exit__(s,*_):s.stop.set();s.t.join(5)
def fail(x): raise RuntimeError(x)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execution-binding',type=pathlib.Path,required=True);ap.add_argument('--artifact-root',type=pathlib.Path,required=True);a=ap.parse_args();root=a.artifact_root.resolve();root.mkdir(parents=True,exist_ok=True)
 b=json.loads(a.execution_binding.read_text()); deadline=parse(b['absolute_release_deadline_utc']); repair_deadline=deadline-dt.timedelta(seconds=90)
 for row in b['bound_files']:
  if sha(P/row['path'])!=row['sha256']: fail('bound_file:'+row['path'])
 if sha(P/'DIRECTOR_FIXED_FLOOR_CROSSOP_H200_OWNER_REPAIR_20260730T0402Z.json')!=b['director_repair_sha256']: fail('director_repair_hash')
 if sha(P/'run_fixed_floor_crossop_h200_owner_r2.py')!=b['owner_sha256']: fail('owner_hash')
 if now()>=parse(b['claim_start_by_utc']): fail('claim_fence_expired')
 show=pool('show','--bench',BENCH); bench=json.loads(show.stdout) if show.returncode==0 else {}; r=bench.get('resource',{})
 if not(show.returncode==0 and bench.get('status')=='available' and bench.get('claim') is None and r.get('gpu_uuid')==b['gpu_uuid'] and r.get('ssh_ed25519_fingerprint')==b['ssh_fingerprint'] and bench.get('lifecycle',{}).get('watchdog',{}).get('main_pid')==506236): fail('bench_identity_or_availability')
 claim=pool('claim','--project',NAME,'--bench',BENCH,'--lease-seconds','1200');
 if claim.returncode: fail('claim:'+claim.stderr[-500:])
 bench=json.loads(claim.stdout); claimed=bench['claim']['claimed_at']; atomic(root/'CLAIM.json',bench); atomic(root/'PROGRESS.json',{'phase':'claimed','claimed_at':claimed,'at_utc':iso()})
 rr=bench['resource']; target=f"{rr['ssh_user']}@{rr['public_ipv4']}"; ssh_cmd=['ssh','-i',rr['ssh_identity_path'],'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={rr['known_hosts_namespace']}",'-o','ConnectTimeout=20',target]; scp_cmd=['scp','-i',rr['ssh_identity_path'],'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={rr['known_hosts_namespace']}"]
 remote='/home/glmrunner/fixed-floor-crossop-executor-r2'; remote_out=remote+'/artifacts/h200_exact_consumer'; released=False
 def ssh_exec(command,label,cap=300):
  t=max(1,min(cap,int((deadline-now()).total_seconds()-30))); z=call([*ssh_cmd,command],t);(root/(label+'.stdout')).write_text(z.stdout);(root/(label+'.stderr')).write_text(z.stderr);return z
 def retained(error,generation):
  diagnostic=root/f'REPAIR_DIAGNOSTIC_{generation}.json'; atomic(diagnostic,{'at_utc':iso(),'classification':'recoverable_pre_science_or_unknown','error':str(error),'science_consumed':False})
  rid=f'r2-{generation}-{int(time.time())}'; ready=call([REPAIR,'ready','--root',str(root),'--repair-id',rid,'--deadline',iso(repair_deadline),'--failure-kind','integration','--diagnostic',str(diagnostic),'--retry-scope','operation'])
  atomic(root/'PROGRESS.json',{'phase':'repair_wait','repair_id':rid,'at_utc':iso(),'ready_rc':ready.returncode})
  if ready.returncode: return None
  wait=call([REPAIR,'wait','--root',str(root),'--repair-id',rid,'--deadline',iso(repair_deadline),'--poll-seconds','5'],max(1,int((repair_deadline-now()).total_seconds()+5)))
  if wait.returncode:return None
  status=json.loads(wait.stdout);
  if status.get('state')!='requested': return None
  request=pathlib.Path(status['request_path']); req=json.loads(request.read_text()); dg=sha(request); os.replace(request,request.with_name(f'REPAIR_REQUEST.{dg}.consumed.json'))
  if req.get('retry_scope')!='operation': return None
  return req
 with HB(root,claimed):
  terminal=None; final=''; condition='maintenance'; gen=0
  while now()<deadline and terminal is None:
   try:
    if ssh_exec('mkdir -p '+shlex.quote(remote),'mkdir',60).returncode: fail('remote_mkdir')
    for row in b['bound_files']:
     src=P/row['path']; tmp=remote+'/'+row['path']+'.part'; dst=remote+'/'+row['path']; z=call([*scp_cmd,str(src),target+':'+tmp],120);(root/(f"stage-{row['path']}.stderr")).write_text(z.stderr)
     if z.returncode:fail('stage:'+row['path'])
     if ssh_exec(f"test \"$(sha256sum {shlex.quote(tmp)} | cut -d' ' -f1)\" = {row['sha256']} && mv -f {shlex.quote(tmp)} {shlex.quote(dst)}",'finalize-'+row['path'],60).returncode:fail('verify:'+row['path'])
    if now()>=parse(b['scientific_launch_by_utc']):fail('launch_fence_expired')
    cmd=f"mkdir -p {shlex.quote(remote_out)} && sudo -n docker run --rm --gpus all -v {shlex.quote(remote)}:{shlex.quote(str(P))} {shlex.quote(b['image'])} bash -lc {shlex.quote(b['remote_command'])}"
    atomic(root/'PROGRESS.json',{'phase':'scientific_launch','at_utc':iso(),'claimed_at':claimed})
    z=ssh_exec(cmd,'scientific',max(60,int((deadline-now()).total_seconds()-40)))
    for n in ('TERMINAL.json','INVOCATION_STATE.json'):
     q=call([*scp_cmd,target+':'+remote_out+'/'+n,str(root/n)],90);(root/(f'get-{n}.stderr')).write_text(q.stderr)
    inv=json.loads((root/'INVOCATION_STATE.json').read_text()) if (root/'INVOCATION_STATE.json').exists() else {}
    terminal=json.loads((root/'TERMINAL.json').read_text()) if (root/'TERMINAL.json').exists() else None
    atomic(root/'EXECUTION_CAPTURE.json',{'rc':z.returncode,'invocation':inv,'terminal_sha256':sha(root/'TERMINAL.json') if terminal else None})
    if not(isinstance(terminal,dict) and len(terminal.get('cases',[]))==10): fail('terminal_incomplete_after_submission')
    final='complete_ten_case_terminal:'+str(terminal.get('passed'));condition='ready'
   except Exception as e:
    if terminal is not None: final='terminal_adoption_boundary:'+str(e);break
    gen+=1; request=retained(e,gen)
    if request is None: final='retained_repair_deadline_or_request_boundary:'+str(e);break
    atomic(root/'PROGRESS.json',{'phase':'repair_consumed','at_utc':iso(),'generation':gen}); continue
  secs=max(0,(now()-parse(claimed)).total_seconds()); spent=b['prior_actual_spend_usd']+secs*RATE/3600
  contents={'schema_version':1,'project':NAME,'role':'exact_h200_component_r2','state':'released','scientific_terminal':final,'artifacts':str(root),'claim_seconds':secs,'actual_spend_usd':spent,'server_state':'No retained container; pinned image/source/cache preserved.'};atomic(root/'RELEASE_CONTENTS.json',contents)
  rel=pool('release','--project',NAME,'--bench',BENCH,'--expected-claimed-at',claimed,'--condition',condition,'--contents',str(root/'RELEASE_CONTENTS.json'));atomic(root/'RELEASE_EVIDENCE.json',{'rc':rel.returncode,'stdout':rel.stdout,'stderr':rel.stderr,'condition':condition})
  st=json.loads((P/'STATUS.json').read_text());st.update({'status':'complete' if terminal else 'blocked','actual_spend_usd':spent,'active_session':None,'claim_allowed':False,'summary':final,'terminal_artifact':str(root/'TERMINAL.json') if terminal else None});atomic(P/'STATUS.json',st);atomic(root/'PROGRESS.json',{'phase':'released','at_utc':iso(),'terminal':terminal is not None});return 0 if terminal else 76
if __name__=='__main__':raise SystemExit(main())
