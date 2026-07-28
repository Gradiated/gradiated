#!/usr/bin/env python3
"""One retained-H200 owner for the admitted wave policy measurement."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, shlex, subprocess, sys, threading, time
from pathlib import Path
P=Path(__file__).resolve().parent; LAB=P.parents[1]; FACTORY=Path('/root/workspace/research/factory/src'); NEBIUS=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius'); KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); KNOWN=Path('/root/.config/nebius/glm-campaign/known_hosts'); DETACHED=Path('/root/workspace/research/factory/tools/detached-owner')
NAME='gemma4_h200_ngram_wave_batching_sustainable'; BENCH='h200-ngram-verifier-e00kcm9nfhwt7e7gbc'; REMOTE='/home/glmrunner/gemma4-ngram-wave-admission'; DEADLINE=dt.datetime(2026,7,24,16,45,tzinfo=dt.timezone.utc); RATE=2.46
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def atomic(p,x):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); q.replace(p)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(a, timeout=None, **kwargs): return subprocess.run(a,text=True,capture_output=True,check=False,timeout=timeout,**kwargs)
def pool(*a): return run(['python3','-m','grad_research.gpu_pool','--lab',str(LAB),*a],env={**os.environ,'PYTHONPATH':str(FACTORY)})
def ssh(ip,command,timeout=90): return run(['ssh','-i',str(KEY),'-o','BatchMode=yes','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{ip}',command],timeout)
def scp_to(ip,src,target): return run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',str(src),f'glmrunner@{ip}:{target}'],900)
def scp_from(ip,src,dst): return run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{ip}:{src}',str(dst)],900)
def ip():
 inv=json.loads((LAB/'runtime/gpus.json').read_text()); benches=inv['benches']; b=benches[BENCH] if isinstance(benches,dict) else next(x for x in benches if x['id']==BENCH); sys.path.insert(0,str(NEBIUS)); from placement_control import extract_public_ipv4,get_instance
 value=extract_public_ipv4(get_instance(b['resource']['instance_id']));
 if not value: raise RuntimeError('typed_provider_boundary:no_public_ip')
 return value
def status(session,summary,spend=None,terminal=None):
 x=json.loads((P/'STATUS.json').read_text()); x['active_session']=session; x['summary']=summary
 if spend is not None: x['actual_spend_usd']=spend
 if terminal is not None: x['terminal']=terminal
 atomic(P/'STATUS.json',x)
def stage(host,artifact):
 packet=artifact/'FROZEN_PACKET.tar'; run(['tar','-cf',str(packet),'-C',str(P),'inputs','remote_wave_admission.py']); expected=sha(packet); dsha=sha(DETACHED)
 prep=ssh(host,f'install -d {shlex.quote(REMOTE)} {shlex.quote(REMOTE+"/out")}');
 if prep.returncode: raise RuntimeError('typed_staging_boundary:prepare')
 for src,target,want in [(packet,REMOTE+'/FROZEN_PACKET.tar',expected),(DETACHED,REMOTE+'/detached-owner',dsha)]:
  test=ssh(host,f'test -f {shlex.quote(target)} && test "$(sha256sum {shlex.quote(target)} | cut -d" " -f1)" = {want}')
  if test.returncode:
   part=target+'.part'; c=scp_to(host,src,part)
   if c.returncode: (artifact/(src.name+'.scp.stderr')).write_text(c.stderr); raise RuntimeError('typed_staging_boundary:scp')
   v=ssh(host,f'test "$(sha256sum {shlex.quote(part)} | cut -d" " -f1)" = {want} && mv -f {shlex.quote(part)} {shlex.quote(target)}')
   if v.returncode: raise RuntimeError('typed_staging_boundary:verify')
 ex=ssh(host,f'cd {shlex.quote(REMOTE)} && tar -xf FROZEN_PACKET.tar && chmod +x detached-owner remote_wave_admission.py')
 if ex.returncode: raise RuntimeError('typed_staging_boundary:extract')
 atomic(artifact/'STAGING_MANIFEST.json',{'packet_sha256':expected,'detached_owner_sha256':dsha,'remote':REMOTE})
def launch(host,artifact):
 r=ssh(host,f'cd {shlex.quote(REMOTE)} && ./detached-owner start --state OWNER.json --log OWNER.log --cwd {shlex.quote(REMOTE)} -- python3 remote_wave_admission.py',60); (artifact/'remote-owner-launch.stdout').write_text(r.stdout); (artifact/'remote-owner-launch.stderr').write_text(r.stderr)
 if r.returncode: raise RuntimeError('typed_remote_owner_boundary:launch')
def state(host):
 r=ssh(host,f'cd {shlex.quote(REMOTE)} && ./detached-owner status --state OWNER.json 2>/dev/null; test -f out/FINAL_TERMINAL.json && echo FINAL || true; test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT || true; cat out/INVOCATION_STATE.json 2>/dev/null || true',45); return {'stdout':r.stdout,'stderr':r.stderr,'returncode':r.returncode,'final':'FINAL' in r.stdout,'attempt':'ATTEMPT' in r.stdout,'live':'"live": true' in r.stdout}
def retrieve(host,a):
 r=ssh(host,f'cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz OWNER.json OWNER.log out && sha256sum compact.tar.gz > compact.tar.gz.sha256',180); (a/'retrieval.stdout').write_text(r.stdout); (a/'retrieval.stderr').write_text(r.stderr)
 if r.returncode: raise RuntimeError('recoverable_retrieval_defect:archive')
 for remote,local in [('compact.tar.gz','compact.tar.gz'),('compact.tar.gz.sha256','compact.tar.gz.sha256')]:
  c=scp_from(host,REMOTE+'/'+remote,a/local)
  if c.returncode: (a/(local+'.scp.stderr')).write_text(c.stderr); raise RuntimeError('recoverable_retrieval_defect:scp')
 if sha(a/'compact.tar.gz') != (a/'compact.tar.gz.sha256').read_text().split()[0]: raise RuntimeError('recoverable_retrieval_defect:hash')
 (a/'retrieved').mkdir(exist_ok=True); r=run(['tar','-xzf',str(a/'compact.tar.gz'),'-C',str(a/'retrieved')]);
 if r.returncode: raise RuntimeError('recoverable_retrieval_defect:extract')
def release(condition,contents): atomic(P/'BENCH_CONTENTS.json',contents); r=pool('release','--project',NAME,'--condition',condition,'--contents',str(P/'BENCH_CONTENTS.json')); 
def main():
 a=P/'artifacts'/dt.datetime.now(dt.timezone.utc).strftime('wave-admission-%Y%m%dt%H%M%Sz'); a.mkdir(parents=True); claimed=time.time(); c=pool('claim','--project',NAME,'--bench',BENCH,'--lease-seconds','300'); (a/'claim.stdout').write_text(c.stdout); (a/'claim.stderr').write_text(c.stderr)
 if c.returncode: raise RuntimeError('typed_pool_boundary:claim')
 host=ip(); stop=threading.Event()
 def beat():
  while not stop.wait(45):
   r=pool('heartbeat','--project',NAME); atomic(P/'OWNER_HEARTBEAT.json',{'at_utc':now(),'returncode':r.returncode,'stderr':r.stderr})
 th=threading.Thread(target=beat,daemon=True); th.start(); status({'unit':str(P/'run_bench_owner.py'),'unit_manager':'foreground-controller','pid':os.getpid(),'deadline_utc':'2026-07-24T16:45:00Z','artifact_root':str(a),'bench_id':BENCH,'remote_root':REMOTE,'expected_terminal':'FINAL_TERMINAL.json'},'Claimed once; project-local immutable packet and one full wave-admission trajectory are owned by this controller.')
 disposition=None
 try:
  identity=ssh(host,'hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version',45); (a/'remote-identity.stdout').write_text(identity.stdout); (a/'remote-identity.stderr').write_text(identity.stderr)
  if identity.returncode: raise RuntimeError('typed_remote_boundary:ssh')
  stage(host,a); launch(host,a)
  while dt.datetime.now(dt.timezone.utc)<DEADLINE:
   time.sleep(20); s=state(host); atomic(a/'REMOTE_STATE.json',s)
   if s['final']:
    retrieve(host,a); t=json.loads((a/'retrieved/out/FINAL_TERMINAL.json').read_text())
    if not t.get('candidate_science_consumed'): raise RuntimeError('recoverable_consumer_defect:unconsumed')
    release('maintenance',{'project':NAME,'result':t['result'],'artifacts':str(a.relative_to(P)),'server_state':'Healthy clean stock NGRAM container gemma4-ngram-wave-admission remains loaded on port 30000; requires explicit compatible successor or director disposition.','checkpoint':'/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.','runtime':'Pinned stock SGLang FP8, FP8-E5M2 KV, NGRAM.'}); disposition='scientific_terminal_released_maintenance'; status(None,'Wave-admission terminal retrieved and bench released to maintenance with clean stock server resident.',max(0,time.time()-claimed)/3600*RATE,{'classification':'measured_wave_admission','path':str((a/'retrieved/out/FINAL_TERMINAL.json').relative_to(P)),'retain_wave_admission':t['retain_wave_admission']}); return
   if s['attempt'] and not s['live']:
    retrieve(host,a); atomic(P/'REPAIR_READY.json',{'at_utc':now(),'artifact_root':str(a),'diagnostic':'Remote worker exited before a scientific terminal; compact terminal retrieved.','repair_deadline_utc':'2026-07-24T16:40:00Z','claim_retained':True});
    while dt.datetime.now(dt.timezone.utc)<dt.datetime(2026,7,24,16,40,tzinfo=dt.timezone.utc):
     q=P/'REPAIR_REQUEST.json'
     if q.exists(): q.rename(P/f'REPAIR_REQUEST.consumed.{int(time.time())}.json'); launch(host,a); break
     time.sleep(10)
    else: raise RuntimeError('typed_repair_boundary:deadline')
  raise RuntimeError('typed_deadline_boundary:absolute')
 except Exception as exc:
  atomic(a/'OWNER_EXCEPTION.json',{'at_utc':now(),'error':repr(exc)})
  try: retrieve(host,a)
  except Exception as e: atomic(a/'RETRIEVAL_EXCEPTION.json',{'at_utc':now(),'error':repr(e)})
  release('maintenance',{'project':NAME,'result':'typed_owner_or_remote_boundary','error':repr(exc),'artifacts':str(a.relative_to(P)),'server_state':'Requires director inspection; retrieval artifacts retained.'}); disposition='typed_boundary_released_maintenance'; status(None,'Owner reached a typed boundary; compact remote diagnostics were requested before maintenance release.',max(0,time.time()-claimed)/3600*RATE,{'classification':'typed_boundary','artifact_root':str(a.relative_to(P))})
 finally:
  stop.set(); th.join(5); atomic(P/'OWNER_TERMINAL.json',{'at_utc':now(),'disposition':disposition,'artifact_root':str(a),'claimed_seconds':max(0,time.time()-claimed),'conservative_provider_spend_usd':max(0,time.time()-claimed)/3600*RATE})
if __name__=='__main__': main()
