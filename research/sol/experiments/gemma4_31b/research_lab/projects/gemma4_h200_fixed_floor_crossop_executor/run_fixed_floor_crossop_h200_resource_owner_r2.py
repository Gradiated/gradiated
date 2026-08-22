#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as D,hashlib,json,os,pathlib,subprocess,sys,tempfile,threading,time
P=pathlib.Path(__file__).resolve().parent;LAB=P.parents[1];N='gemma4_h200_fixed_floor_crossop_executor';B='h200-dflash-r3-computeinstance-e00t5s028ts52zp215';F='/root/workspace/research/factory/src';R='/root/workspace/research/factory/tools/repair-handshake';RATE=2.45
def now():return D.datetime.now(D.UTC)
def iso(x=None):return (x or now()).isoformat().replace('+00:00','Z')
def pt(x):return D.datetime.fromisoformat(x.replace('Z','+00:00'))
def sh(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def put(p,x):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',dir=p.parent,delete=False) as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n');q=f.name
 json.loads(pathlib.Path(q).read_text());os.replace(q,p)
def run(x,t=60,e=None):return subprocess.run(x,text=True,capture_output=True,timeout=t,check=False,env=e)
def pool(*x):return run([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),*x],e={**os.environ,'PYTHONPATH':F})
class HB:
 def __init__(s,c):s.c,s.stop=c,threading.Event()
 def __enter__(s):
  s.t=threading.Thread(target=lambda:[pool('heartbeat','--project',N,'--bench',B,'--expected-claimed-at',s.c) for _ in iter(lambda:not s.stop.wait(30),False)],daemon=True);s.t.start();return s
 def __exit__(s,*_):s.stop.set();s.t.join(5)
def main():
 a=argparse.ArgumentParser();a.add_argument('--execution-binding',type=pathlib.Path,required=True);a.add_argument('--artifact-root',type=pathlib.Path,required=True);z=a.parse_args();root=z.artifact_root.resolve();root.mkdir(parents=True,exist_ok=True);b=json.loads(z.execution_binding.read_text());dl=pt(b['deadline'])
 if sh(P/'DIRECTOR_FIXED_FLOOR_CROSSOP_H200_RESOURCE_METADATA_REPAIR_20260730T0421Z.json')!=b['director_sha'] or sh(P/'run_fixed_floor_crossop_h200_resource_owner_r2.py')!=b['owner_sha']:raise RuntimeError('binding')
 for f in b['files']:
  if sh(P/f['path'])!=f['sha256']:raise RuntimeError('file:'+f['path'])
 q=pool('show','--bench',B);bench=json.loads(q.stdout);r=bench['resource']
 if now()>=pt(b['claim_by']) or bench['status']!='available' or bench['claim'] or r['gpu_uuid']!=b['gpu'] or r['ssh_ed25519_fingerprint']!=b['fp'] or bench['lifecycle']['watchdog']['main_pid']!=506236:raise RuntimeError('preclaim')
 q=pool('claim','--project',N,'--bench',B,'--lease-seconds','780');bench=json.loads(q.stdout);claimed=bench['claim']['claimed_at'];put(root/'CLAIM.json',bench);target=f"{r['ssh_user']}@{r['public_ipv4']}";o=['-i',r['ssh_identity_path'],'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={r['known_hosts_namespace']}"];ssh=['ssh',*o,target];scp=['scp',*o];remote='/home/glmrunner/fixed-floor-resources-r2'
 def ex(c,l,t=180):
  x=run([*ssh,c],min(t,max(1,int((dl-now()).total_seconds()-20))));(root/(l+'.out')).write_text(x.stdout);(root/(l+'.err')).write_text(x.stderr);return x
 term=None;attempt=0
 with HB(claimed):
  while now()<dl and term is None:
   try:
    if ex('mkdir -p '+remote,'mkdir',30).returncode:raise RuntimeError('mkdir')
    for f in b['files']:
     x=run([*scp,str(P/f['path']),target+':'+remote+'/'+f['path']+'.part'],90)
     if x.returncode:raise RuntimeError('stage')
     if ex(f"test \"$(sha256sum {remote}/{f['path']}.part|cut -d' ' -f1)\" = {f['sha256']} && mv {remote}/{f['path']}.part {remote}/{f['path']}",'verify',30).returncode:raise RuntimeError('verify')
    put(root/'PROGRESS.json',{'phase':'compile_only','no_candidate_launch':True,'at_utc':iso()});cmd=f"mkdir -p {remote}/out && sudo -n docker run --rm --gpus all -v {remote}:{P} -e RESOURCE_OUTPUT={P}/out/TERMINAL.json {b['image']} bash -lc 'PYTHONPATH={P} python3 {P}/collect_fixed_floor_crossop_h200_resources_r2.py'";x=ex(cmd,'compile',max(60,int((dl-now()).total_seconds()-45)));g=run([*scp,target+':'+remote+'/out/TERMINAL.json',str(root/'TERMINAL.json')],90)
    if x.returncode or g.returncode:raise RuntimeError('collector')
    term=json.loads((root/'TERMINAL.json').read_text())
    if len(term.get('rows',[]))!=2:raise RuntimeError('rows')
   except Exception as e:
    attempt+=1;diag=root/f'DIAGNOSTIC_{attempt}.json';put(diag,{'error':str(e),'no_candidate_launch':True});rid=f'metadata-r2-{attempt}';ready=run([R,'ready','--root',str(root),'--repair-id',rid,'--deadline',iso(dl-D.timedelta(seconds=60)),'--failure-kind','integration','--diagnostic',str(diag),'--retry-scope','extract'])
    put(root/'PROGRESS.json',{'phase':'repair_wait','repair_id':rid,'at_utc':iso()})
    if ready.returncode:break
    w=run([R,'wait','--root',str(root),'--repair-id',rid,'--deadline',iso(dl-D.timedelta(seconds=60)),'--poll-seconds','5'],max(1,int((dl-now()).total_seconds()-50)))
    if w.returncode or json.loads(w.stdout).get('state')!='requested':break
    req=pathlib.Path(json.loads(w.stdout)['request_path']);dg=sh(req);os.replace(req,req.with_name('REPAIR_REQUEST.'+dg+'.consumed.json'));continue
  sec=(now()-pt(claimed)).total_seconds();spent=b['prior']+sec*RATE/3600;ok=isinstance(term,dict);put(root/'RELEASE_CONTENTS.json',{'project':N,'actual_spend_usd':spent,'claim_seconds':sec,'scientific_terminal':'metadata_r2:'+str(term.get('passed') if ok else None),'artifacts':str(root)});rel=pool('release','--project',N,'--bench',B,'--expected-claimed-at',claimed,'--condition','ready' if ok else 'maintenance','--contents',str(root/'RELEASE_CONTENTS.json'));put(root/'RELEASE.json',{'rc':rel.returncode,'stdout':rel.stdout,'stderr':rel.stderr});st=json.loads((P/'STATUS.json').read_text());st.update({'active_session':None,'actual_spend_usd':spent,'claim_allowed':False,'status':'complete' if ok else 'blocked','summary':'metadata_r2:'+str(term.get('passed') if ok else None),'resource_terminal':str(root/'TERMINAL.json') if ok else None,'terminal_acceptance_complete':bool(term and term.get('passed'))});put(P/'STATUS.json',st)
if __name__=='__main__':main()
