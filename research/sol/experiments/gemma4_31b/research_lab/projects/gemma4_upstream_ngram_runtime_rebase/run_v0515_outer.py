#!/usr/bin/env python3
"""Durable local owner for the single v0.5.15 discriminator."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, pathlib, shlex, subprocess, sys, threading, time

P=pathlib.Path(__file__).resolve().parent; LAB=P.parents[1]; FACTORY=pathlib.Path('/root/workspace/research/factory/src'); NEBIUS=pathlib.Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius')
KEY=pathlib.Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); KNOWN=pathlib.Path('/root/.config/nebius/glm-campaign/known_hosts'); DETACHED=pathlib.Path('/root/workspace/research/factory/tools/detached-owner')
PROJECT='gemma4_upstream_ngram_runtime_rebase'; BENCH='h200-ngram-verifier-e00kcm9nfhwt7e7gbc'; REMOTE='/home/glmrunner/gemma4-upstream-ngram-v0515'; DEADLINE=dt.datetime(2026,7,25,7,0,tzinfo=dt.timezone.utc); RATE=2.46
STATE=pathlib.Path(os.environ.get('UPSTREAM_REBASE_OWNER_STATE',str(P/'OWNER_STATE.json')))
BASE_SPEND=float(json.loads((P/'STATUS.json').read_text()).get('actual_spend_usd',0.0))
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def atomic(p,x):
 p=pathlib.Path(p); p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n'); q.replace(p)
def run(a,timeout=90,**kw): return subprocess.run(a,text=True,capture_output=True,check=False,timeout=timeout,**kw)
def pool(*a): return run(['python3','-m','grad_research.gpu_pool','--lab',str(LAB),*a],env={**os.environ,'PYTHONPATH':str(FACTORY)})
def ssh(host,cmd,timeout=90): return run(['ssh','-i',str(KEY),'-o','BatchMode=yes','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{host}',cmd],timeout)
def scp_to(host,src,dst): return run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',str(src),f'glmrunner@{host}:{dst}'],900)
def scp_from(host,src,dst): return run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{host}:{src}',str(dst)],900)
def digest(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def host():
 inv=json.loads((LAB/'runtime/gpus.json').read_text()); b=inv['benches'][BENCH]; sys.path.insert(0,str(NEBIUS)); from placement_control import extract_public_ipv4,get_instance
 value=extract_public_ipv4(get_instance(b['resource']['instance_id']))
 if not value: raise RuntimeError('typed_provider_boundary:no_public_ip')
 return value
def status(session,summary,spend=None,terminal=None):
 x=json.loads((P/'STATUS.json').read_text()); x['active_session']=session; x['summary']=summary
 if spend is not None: x['actual_spend_usd']=round(BASE_SPEND+spend,6)
 if terminal is not None: x['terminal']=terminal
 atomic(P/'STATUS.json',x)
def stage(h,a):
 packet=a/'PACKET.tar'; r=run(['tar','-cf',str(packet),'-C',str(P),'remote_runtime_discriminator.py','remote_v0515_worker.sh','-C',str(P/'artifacts/candidate-v0.5.15'),'CANDIDATE_RUNTIME.json','inputs']);
 if r.returncode: raise RuntimeError('typed_staging_boundary:tar')
 want=digest(packet); dsha=digest(DETACHED); ssh(h,f'install -d {shlex.quote(REMOTE)} {shlex.quote(REMOTE+"/out")}')
 for src,dst,expected in ((packet,REMOTE+'/PACKET.tar',want),(DETACHED,REMOTE+'/detached-owner',dsha)):
  check=ssh(h,f'test -f {shlex.quote(dst)} && test "$(sha256sum {shlex.quote(dst)} | cut -d\" \" -f1)" = {expected}')
  if check.returncode:
   cp=scp_to(h,src,dst+'.part')
   if cp.returncode: (a/(src.name+'.scp.stderr')).write_text(cp.stderr); raise RuntimeError('typed_staging_boundary:scp')
   if ssh(h,f'test "$(sha256sum {shlex.quote(dst+".part")} | cut -d\" \" -f1)" = {expected} && mv -f {shlex.quote(dst+".part")} {shlex.quote(dst)}').returncode: raise RuntimeError('typed_staging_boundary:verify')
 ex=ssh(h,f'cd {shlex.quote(REMOTE)} && tar -xf PACKET.tar && chmod 0555 detached-owner remote_v0515_worker.sh remote_runtime_discriminator.py')
 if ex.returncode: raise RuntimeError('typed_staging_boundary:extract')
 atomic(a/'STAGING_MANIFEST.json',{'packet_sha256':want,'detached_owner_sha256':dsha,'remote_root':REMOTE})
def launch(h,a):
 r=ssh(h,f'cd {shlex.quote(REMOTE)} && ./detached-owner start --state GUEST_OWNER.json --log GUEST_OWNER.log --cwd {shlex.quote(REMOTE)} --unit-manager remote-shell -- env UPSTREAM_REBASE_ROOT={shlex.quote(REMOTE)} ./remote_v0515_worker.sh',60); (a/'guest-launch.stdout').write_text(r.stdout); (a/'guest-launch.stderr').write_text(r.stderr)
 if r.returncode: raise RuntimeError('typed_remote_owner_boundary:launch')
def state(h):
 r=ssh(h,f'cd {shlex.quote(REMOTE)} && ./detached-owner status --state GUEST_OWNER.json 2>/dev/null; test -f out/FINAL_TERMINAL.json && echo FINAL || true; test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT || true; cat out/INVOCATION_STATE.json 2>/dev/null || true',45)
 return {'at_utc':now(),'stdout':r.stdout,'stderr':r.stderr,'returncode':r.returncode,'final':'FINAL' in r.stdout,'attempt':'ATTEMPT' in r.stdout,'live':'"live": true' in r.stdout}
def retrieve(h,a):
 r=ssh(h,f'cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz GUEST_OWNER.json GUEST_OWNER.log out PRE_REPLACEMENT_CONTAINERS.json 2>/dev/null && sha256sum compact.tar.gz > compact.tar.gz.sha256',180); (a/'retrieval.stdout').write_text(r.stdout); (a/'retrieval.stderr').write_text(r.stderr)
 if r.returncode: raise RuntimeError('recoverable_retrieval_defect:archive')
 for remote,local in [('compact.tar.gz','compact.tar.gz'),('compact.tar.gz.sha256','compact.tar.gz.sha256')]:
  r=scp_from(h,REMOTE+'/'+remote,a/local)
  if r.returncode: (a/(local+'.scp.stderr')).write_text(r.stderr); raise RuntimeError('recoverable_retrieval_defect:scp')
 if digest(a/'compact.tar.gz') != (a/'compact.tar.gz.sha256').read_text().split()[0]: raise RuntimeError('recoverable_retrieval_defect:hash')
 (a/'retrieved').mkdir(exist_ok=True); run(['tar','-xzf',str(a/'compact.tar.gz'),'-C',str(a/'retrieved')])
def release(condition,contents):
 path=P/'BENCH_CONTENTS.json'; atomic(path,contents)
 return pool('release','--project',PROJECT,'--condition',condition,'--contents',str(path))
def main():
 a=P/'artifacts'/('v0515-discriminator-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dt%H%M%Sz')); a.mkdir(parents=True,exist_ok=False); started=time.time(); h=host(); stop=threading.Event()
 def beat():
  while not stop.wait(45):
   r=pool('heartbeat','--project',PROJECT); atomic(P/'OWNER_HEARTBEAT.json',{'at_utc':now(),'returncode':r.returncode,'stderr':r.stderr[-2000:]})
 th=threading.Thread(target=beat,daemon=True); th.start()
 status({'unit':str(STATE),'unit_manager':'pid','deadline_utc':'2026-07-25T07:00:00Z','artifact_root':str(a),'bench_id':BENCH,'remote_root':REMOTE,'expected_terminal':'FINAL_TERMINAL.json'},'Claimed H200 is owned by durable v0.5.15 discriminator controller.')
 try:
  identity=ssh(h,'hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker ps --format "{{.Names}} {{.Image}}"',45); (a/'remote-identity.stdout').write_text(identity.stdout); (a/'remote-identity.stderr').write_text(identity.stderr)
  if identity.returncode: raise RuntimeError('typed_remote_boundary:ssh')
  stage(h,a); launch(h,a)
  while dt.datetime.now(dt.timezone.utc)<DEADLINE:
   time.sleep(20); s=state(h); atomic(a/'REMOTE_STATE.json',s)
   if s['final']:
    retrieve(h,a); t=json.loads((a/'retrieved/out/FINAL_TERMINAL.json').read_text()); spend=(time.time()-started)/3600*RATE
    contents={'project':PROJECT,'result':t['result'],'artifacts':str(a.relative_to(P)),'image':'docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd','checkpoint':'/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.','server_state':'Official v0.5.15 native-NGRAM server gemma4-ngram-upstream-v0515 remains loaded on port 30000; requires compatible successor or director disposition.'}
    rel=release('maintenance',contents); (a/'release.stdout').write_text(rel.stdout); (a/'release.stderr').write_text(rel.stderr)
    status(None,'v0.5.15 discriminator terminal retrieved; H200 released to maintenance with server resident.',spend,{'classification':'measured_upstream_runtime_discriminator','artifact_root':str(a.relative_to(P)),'candidate_sample_consumed':True,'endpoint_admitted':t['endpoint_admitted']}); return
   if s['attempt'] and not s['live']:
    retrieve(h,a)
    repair=run(['/root/workspace/research/factory/tools/repair-handshake','ready','--root',str(a),'--deadline','2026-07-25T06:55:00Z','--failure-kind','recoverable_remote_consumer_or_setup_defect','--diagnostic','compact remote terminal retrieved','--retry-scope','only invalidated operation against existing server'])
    (a/'repair-ready.stdout').write_text(repair.stdout); (a/'repair-ready.stderr').write_text(repair.stderr)
    status({'unit':str(STATE),'unit_manager':'pid','deadline_utc':'2026-07-25T07:00:00Z','artifact_root':str(a),'bench_id':BENCH},'Recoverable remote defect; claim retained while repair-handshake waits.')
    wait=run(['/root/workspace/research/factory/tools/repair-handshake','wait','--root',str(a)],timeout=max(1,int((DEADLINE-dt.datetime.now(dt.timezone.utc)).total_seconds())))
    (a/'repair-wait.stdout').write_text(wait.stdout); (a/'repair-wait.stderr').write_text(wait.stderr)
    if wait.returncode: raise RuntimeError('typed_repair_boundary:deadline_or_binding')
    stamp=str(int(time.time())); archive=ssh(h,f'cd {shlex.quote(REMOTE)} && test -d out && mv out out.pre_repair_{stamp} && mkdir out && rm -f ATTEMPT_TERMINAL.json',45)
    if archive.returncode: raise RuntimeError('recoverable_repair_archive_defect')
    stage(h,a); launch(h,a)
  raise RuntimeError('typed_deadline_boundary:absolute')
 except Exception as e:
  atomic(a/'OWNER_EXCEPTION.json',{'at_utc':now(),'error':repr(e)})
  try: retrieve(h,a)
  except Exception as retrieval: atomic(a/'RETRIEVAL_EXCEPTION.json',{'at_utc':now(),'error':repr(retrieval)})
  spend=(time.time()-started)/3600*RATE; rel=release('maintenance',{'project':PROJECT,'result':'typed_owner_or_remote_boundary','error':repr(e),'artifacts':str(a.relative_to(P)),'server_state':'Requires director inspection; retrieval diagnostics retained.'}); (a/'release.stdout').write_text(rel.stdout); (a/'release.stderr').write_text(rel.stderr)
  status(None,'Owner reached typed boundary and released H200 to maintenance after retrieval attempt.',spend,{'classification':'typed_boundary','artifact_root':str(a.relative_to(P)),'candidate_sample_consumed':False})
 finally:
  stop.set(); th.join(5); atomic(P/'OWNER_TERMINAL.json',{'at_utc':now(),'artifact_root':str(a),'claimed_seconds':max(0,time.time()-started),'conservative_provider_spend_usd':max(0,time.time()-started)/3600*RATE})
if __name__=='__main__': main()
