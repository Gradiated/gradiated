#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,pathlib,subprocess,sys,tempfile,threading,time
P=pathlib.Path(__file__).resolve().parent;LAB=P.parents[1];NAME='gemma4_h200_fixed_floor_crossop_executor';BENCH='h200-dflash-r3-computeinstance-e00t5s028ts52zp215';RATE=2.45;FACTORY='/root/workspace/research/factory/src';REPAIR='/root/workspace/research/factory/tools/repair-handshake'
def now():return dt.datetime.now(dt.UTC)
def iso(x=None):return (x or now()).isoformat().replace('+00:00','Z')
def tm(x):return dt.datetime.fromisoformat(x.replace('Z','+00:00'))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def atom(p,x):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n');q=f.name
 json.loads(pathlib.Path(q).read_text());os.replace(q,p)
def call(x,t=60,e=None):return subprocess.run(x,text=True,capture_output=True,timeout=t,check=False,env=e)
def pool(*x):return call([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*x],e={**os.environ,'PYTHONPATH':FACTORY})
class HB:
 def __init__(s,r,c):s.r,s.c,s.stop=r,c,threading.Event()
 def __enter__(s):
  def f():
   while not s.stop.wait(30):pool('heartbeat','--project',NAME,'--bench',BENCH,'--expected-claimed-at',s.c)
  s.t=threading.Thread(target=f,daemon=True);s.t.start();return s
 def __exit__(s,*_):s.stop.set();s.t.join(5)
def main():
 a=argparse.ArgumentParser();a.add_argument('--execution-binding',type=pathlib.Path,required=True);a.add_argument('--artifact-root',type=pathlib.Path,required=True);z=a.parse_args();root=z.artifact_root.resolve();root.mkdir(parents=True,exist_ok=True);b=json.loads(z.execution_binding.read_text());deadline=tm(b['deadline'])
 if sha(P/'DIRECTOR_FIXED_FLOOR_CROSSOP_H200_RESOURCE_RECOVERY_20260730T0414Z.json')!=b['director_sha256'] or sha(P/'run_fixed_floor_crossop_h200_resource_owner.py')!=b['owner_sha256']:raise RuntimeError('binding_hash')
 for r in b['files']:
  if sha(P/r['path'])!=r['sha256']:raise RuntimeError('file_hash:'+r['path'])
 show=pool('show','--bench',BENCH);bench=json.loads(show.stdout);res=bench['resource']
 if now()>=tm(b['claim_by']) or bench['status']!='available' or bench['claim'] is not None or res['gpu_uuid']!=b['gpu_uuid'] or res['ssh_ed25519_fingerprint']!=b['ssh_fingerprint'] or bench['lifecycle']['watchdog']['main_pid']!=506236:raise RuntimeError('claim_precondition')
 c=pool('claim','--project',NAME,'--bench',BENCH,'--lease-seconds','840');bench=json.loads(c.stdout);claimed=bench['claim']['claimed_at'];atom(root/'CLAIM.json',bench)
 target=f"{res['ssh_user']}@{res['public_ipv4']}";opts=['-i',res['ssh_identity_path'],'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={res['known_hosts_namespace']}"];ssh=['ssh',*opts,target];scp=['scp',*opts];remote='/home/glmrunner/fixed-floor-resources';term=None
 def ex(cmd,label,t=180):
  q=call([*ssh,cmd],min(t,max(1,int((deadline-now()).total_seconds()-20))));(root/(label+'.stdout')).write_text(q.stdout);(root/(label+'.stderr')).write_text(q.stderr);return q
 with HB(root,claimed):
  try:
   if ex('mkdir -p '+remote,'mkdir',30).returncode:raise RuntimeError('mkdir')
   for r in b['files']:
    q=call([*scp,str(P/r['path']),target+':'+remote+'/'+r['path']+'.part'],90);
    if q.returncode:raise RuntimeError('stage:'+r['path'])
    if ex(f"test \"$(sha256sum {remote}/{r['path']}.part | cut -d' ' -f1)\" = {r['sha256']} && mv {remote}/{r['path']}.part {remote}/{r['path']}",'verify-'+r['path'],30).returncode:raise RuntimeError('verify:'+r['path'])
   atom(root/'PROGRESS.json',{'phase':'compile_only','at_utc':iso(),'no_launch':True})
   cmd=f"mkdir -p {remote}/out && sudo -n docker run --rm --gpus all -v {remote}:{P} -e RESOURCE_OUTPUT={P}/out/TERMINAL.json {b['image']} bash -lc 'PYTHONPATH={P} python3 {P}/collect_fixed_floor_crossop_h200_resources.py'"
   q=ex(cmd,'compile',max(60,int((deadline-now()).total_seconds()-40)))
   g=call([*scp,target+':'+remote+'/out/TERMINAL.json',str(root/'TERMINAL.json')],90);term=json.loads((root/'TERMINAL.json').read_text()) if g.returncode==0 else None
   if not isinstance(term,dict) or len(term.get('rows',[]))!=2:raise RuntimeError('resource_terminal')
  except Exception as e:
   atom(root/'RECOVERABLE_DIAGNOSTIC.json',{'error':str(e),'no_candidate_launch':True}); rid='resource-1';call([REPAIR,'ready','--root',str(root),'--repair-id',rid,'--deadline',iso(deadline-dt.timedelta(seconds=60)),'--failure-kind','integration','--diagnostic',str(root/'RECOVERABLE_DIAGNOSTIC.json'),'--retry-scope','compile_only']);term={'passed':False,'error':str(e),'no_candidate_kernel_launch':True}
  sec=(now()-tm(claimed)).total_seconds();spent=b['prior_spend']+sec*RATE/3600;atom(root/'RELEASE_CONTENTS.json',{'project':NAME,'actual_spend_usd':spent,'claim_seconds':sec,'scientific_terminal':'resource_recovery:'+str(term.get('passed')),'artifacts':str(root)});rel=pool('release','--project',NAME,'--bench',BENCH,'--expected-claimed-at',claimed,'--condition','ready','--contents',str(root/'RELEASE_CONTENTS.json'));atom(root/'RELEASE.json',{'rc':rel.returncode,'stdout':rel.stdout,'stderr':rel.stderr});st=json.loads((P/'STATUS.json').read_text());st.update({'active_session':None,'actual_spend_usd':spent,'claim_allowed':False,'status':'complete','summary':'resource_recovery:'+str(term.get('passed')),'resource_terminal':str(root/'TERMINAL.json')});atom(P/'STATUS.json',st)
if __name__=='__main__':main()
