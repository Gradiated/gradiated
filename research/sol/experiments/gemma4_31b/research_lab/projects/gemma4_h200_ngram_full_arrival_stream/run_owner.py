#!/usr/bin/env python3
import datetime as dt, hashlib, json, os, shlex, subprocess, sys, threading, time
from pathlib import Path

P=Path(__file__).resolve().parent; L=P.parents[1]; F=Path('/root/workspace/research/factory/src'); N=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius'); K=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); H=Path('/root/.config/nebius/glm-campaign/known_hosts'); D=Path('/root/workspace/research/factory/tools/detached-owner'); NAME='gemma4_h200_ngram_full_arrival_stream'; BENCH='h200-ngram-verifier-e00kcm9nfhwt7e7gbc'; REMOTE='/home/glmrunner/gemma4-ngram-full-arrival-stream'; RATE=2.46; DEADLINE=dt.datetime(2026,7,25,3,20,tzinfo=dt.timezone.utc)
def now(): return dt.datetime.now(dt.timezone.utc)
def atomic(p,x):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n'); q.replace(p)
def run(a,timeout=None,**kw): return subprocess.run(a,text=True,capture_output=True,check=False,timeout=timeout,**kw)
def pool(*a): return run(['python3','-m','grad_research.gpu_pool','--lab',str(L),*a],env={**os.environ,'PYTHONPATH':str(F)})
def ssh(ip,c,t=120): return run(['ssh','-i',str(K),'-o','BatchMode=yes','-o','ServerAliveInterval=20','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={H}',f'glmrunner@{ip}',c],t)
def scp(ip,s,t): return run(['scp','-p','-i',str(K),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={H}',str(s),f'glmrunner@{ip}:{t}'],900)
def get_ip():
 sys.path.insert(0,str(N)); from placement_control import extract_public_ipv4,get_instance
 return extract_public_ipv4(get_instance('computeinstance-e00kcm9nfhwt7e7gbc'))
def digest(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def remote_workload_present(inspection):
 if inspection.returncode: return True
 lines=[line.strip() for line in inspection.stdout.splitlines() if line.strip()]
 if not lines: return False
 try: state=json.loads(lines[0])
 except json.JSONDecodeError: return True
 return bool(state.get('Running')) or len(lines)>1
def inspect_remote_workload(ip):
 return ssh(ip,"sudo docker inspect gemma4-ngram-tail-overlap --format '{{json .State}}' 2>/dev/null || true; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null || true",60)
def status(session,summary,spend=0.0,terminal=None):
 x=json.loads((P/'STATUS.json').read_text()); x.update({'active_session':session,'summary':summary,'actual_spend_usd':spend})
 if terminal is not None: x['terminal']=terminal
 atomic(P/'STATUS.json',x)
def main():
 a=P/'artifacts'/now().strftime('full-arrival-%Y%m%dt%H%M%Sz'); a.mkdir(parents=True); prior=float(json.loads((P/'STATUS.json').read_text()).get('actual_spend_usd',0.0)); started=time.monotonic(); c=pool('claim','--project',NAME,'--bench',BENCH,'--lease-seconds','300'); (a/'claim.stdout').write_text(c.stdout); (a/'claim.stderr').write_text(c.stderr)
 if c.returncode: raise RuntimeError('typed_pool_boundary:claim:'+c.stderr[-500:])
 hb=pool('heartbeat','--project',NAME); atomic(P/'OWNER_HEARTBEAT.json',{'at_utc':now().isoformat(),'returncode':hb.returncode,'stderr':hb.stderr})
 if hb.returncode: raise RuntimeError('typed_pool_boundary:initial_heartbeat:'+hb.stderr[-500:])
 stop=threading.Event()
 def beat():
  while not stop.wait(45):
   r=pool('heartbeat','--project',NAME); atomic(P/'OWNER_HEARTBEAT.json',{'at_utc':now().isoformat(),'returncode':r.returncode,'stderr':r.stderr})
 t=threading.Thread(target=beat,daemon=True); t.start(); disposition='maintenance'
 try:
  ip=get_ip()
  if not ip: raise RuntimeError('typed_provider_boundary:no_public_ip')
  packet=a/'PACKET.tar'; r=run(['tar','-cf',str(packet),'-C',str(P),'inputs','remote_full_arrival.py','DIRECTOR_BINDING.json','BINDING_VERIFIED.json']);
  if r.returncode: raise RuntimeError('typed_packet_boundary')
  for source,target in ((packet,REMOTE+'/PACKET.tar'),(D,REMOTE+'/detached-owner')):
   want=digest(source); ssh(ip,f'mkdir -p {shlex.quote(REMOTE)}'); ok=ssh(ip,f'test -f {shlex.quote(target)} && test "$(sha256sum {shlex.quote(target)} | cut -d\" \" -f1)" = {want}')
   if ok.returncode:
    part=target+'.'+want+'.part'; x=scp(ip,source,part)
    if x.returncode: raise RuntimeError('typed_staging_boundary:scp:'+x.stderr[-500:])
    x=ssh(ip,f'test "$(sha256sum {shlex.quote(part)} | cut -d\" \" -f1)" = {want} && mv -f {shlex.quote(part)} {shlex.quote(target)}')
    if x.returncode: raise RuntimeError('typed_staging_boundary:verify')
  packet_hash=digest(packet)
  x=ssh(ip,f"cd {shlex.quote(REMOTE)} && test \"$(sha256sum PACKET.tar | cut -d' ' -f1)\" = {packet_hash} && tar -xf PACKET.tar && python3 -c 'import json; assert json.load(open(\"BINDING_VERIFIED.json\"))[\"result\"] == \"all_bound_identities_and_hashes_match\"' && chmod 0555 detached-owner remote_full_arrival.py")
  atomic(a/'REMOTE_PACKET_PREFLIGHT.json',{'packet_sha256':packet_hash,'returncode':x.returncode,'stdout':x.stdout,'stderr':x.stderr,'remote_root':REMOTE})
  if x.returncode: raise RuntimeError('typed_staging_boundary:extract:'+x.stderr[-500:])
  x=ssh(ip,f'cd {shlex.quote(REMOTE)} && ./detached-owner start --state OWNER.json --log OWNER.log --cwd {shlex.quote(REMOTE)} --unit-manager remote-shell -- env FULL_ARRIVAL_ROOT={shlex.quote(REMOTE)} python3 remote_full_arrival.py')
  (a/'launch.stdout').write_text(x.stdout); (a/'launch.stderr').write_text(x.stderr)
  if x.returncode: raise RuntimeError('typed_remote_owner_boundary:launch')
  while now()<DEADLINE:
   time.sleep(30); x=ssh(ip,f'cd {shlex.quote(REMOTE)} && ./detached-owner status --state OWNER.json 2>/dev/null; test -f out/FINAL_TERMINAL.json && echo FINAL || true; test -f out/ATTEMPT_TERMINAL.json && echo ATTEMPT || true',60); (a/'remote-state.json').write_text(json.dumps({'stdout':x.stdout,'stderr':x.stderr,'at_utc':now().isoformat()},indent=2))
   if 'FINAL' in x.stdout or ('ATTEMPT' in x.stdout and '"live": true' not in x.stdout) or '"live": false' in x.stdout: break
  x=ssh(ip,f'cd {shlex.quote(REMOTE)} && tar -czf compact.tar.gz OWNER.json OWNER.log out && sha256sum compact.tar.gz > compact.tar.gz.sha256',300)
  if x.returncode: raise RuntimeError('recoverable_retrieval_defect:archive')
  for n in ('compact.tar.gz','compact.tar.gz.sha256'):
   x=run(['scp','-p','-i',str(K),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={H}',f'glmrunner@{ip}:{REMOTE}/{n}',str(a/n)],timeout=900)
   if x.returncode: raise RuntimeError('recoverable_retrieval_defect:scp')
  if digest(a/'compact.tar.gz') != (a/'compact.tar.gz.sha256').read_text().split()[0]: raise RuntimeError('recoverable_retrieval_defect:hash')
  x=run(['tar','-xzf',str(a/'compact.tar.gz'),'-C',str(a)]); 
  if x.returncode: raise RuntimeError('recoverable_retrieval_defect:extract')
  final_path=a/'out/FINAL_TERMINAL.json'; attempt_path=a/'out/ATTEMPT_TERMINAL.json'
  final=final_path.exists()
  if final or attempt_path.exists(): term=json.loads((final_path if final else attempt_path).read_text())
  else: term={'classification':'recoverable_worker_exit_without_terminal','error':(a/'OWNER.log').read_text()[-4000:] if (a/'OWNER.log').exists() else 'remote owner exited without a typed terminal','candidate_science_consumed':False}
  spend=prior+(time.monotonic()-started)/3600*RATE
  if not final and not term.get('candidate_science_consumed',False):
   inspection=inspect_remote_workload(ip)
   contents={'project':NAME,'result':term.get('classification','recoverable_attempt'),'artifacts':str(a.relative_to(P)),'candidate_sample_consumed':False,'checkpoint':'/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.','runtime':'Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, native depth-12 NGRAM.','server_state':'Recoverable attempt retained for in-place director/researcher inspection; do not cold-restart.','remote_inspection':inspection.stdout[-4000:],'gpu_processes':'present or inspection uncertain' if remote_workload_present(inspection) else 'none observed'}; atomic(P/'BENCH_CONTENTS.json',contents); atomic(P/'REPAIR_READY.json',{'at_utc':now().isoformat(),'deadline_utc':DEADLINE.isoformat().replace('+00:00','Z'),'artifact_root':str(a.relative_to(P)),'bench_id':BENCH,'diagnostic':term}); rel=pool('release','--project',NAME,'--condition','maintenance','--contents',str(P/'BENCH_CONTENTS.json')); (a/'release.stdout').write_text(rel.stdout); (a/'release.stderr').write_text(rel.stderr)
   status(None,'Recoverable attempt retrieved; resident state retained in maintenance for in-place repair.',spend,{'classification':'recoverable_attempt','artifact_root':str(a.relative_to(P)),'candidate_science_consumed':False}); disposition='recoverable_attempt_retained_maintenance'; return
  inspection=inspect_remote_workload(ip); workload_present=remote_workload_present(inspection); condition='maintenance' if workload_present else 'ready'
  contents={'project':NAME,'result':term.get('result'),'artifacts':str(a.relative_to(P)),'candidate_sample_consumed':term.get('candidate_science_consumed',False),'checkpoint':'/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.','runtime':'Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, native depth-12 NGRAM.','server_state':'Healthy resident SGLang container retained without removal; director disposition required before incompatible reuse.' if workload_present else 'Accelerator unoccupied.','remote_inspection':inspection.stdout[-4000:],'gpu_processes':'present or inspection uncertain' if workload_present else 'none observed'}; atomic(P/'BENCH_CONTENTS.json',contents); rel=pool('release','--project',NAME,'--condition',condition,'--contents',str(P/'BENCH_CONTENTS.json')); (a/'release.stdout').write_text(rel.stdout); (a/'release.stderr').write_text(rel.stderr)
  status(None,'Candidate terminal retrieved; retained H200 released '+condition+'.',spend,{'classification':term.get('result'),'artifact_root':str(a.relative_to(P)),'candidate_science_consumed':term.get('candidate_science_consumed',False)}); disposition='terminal_retrieved_released_'+condition; return
 except Exception as e:
  atomic(a/'OWNER_EXCEPTION.json',{'error':repr(e),'at_utc':now().isoformat()}); status(None,'Typed owner boundary; bench claim retained only if repair handoff is required.',prior+(time.monotonic()-started)/3600*RATE,{'classification':'typed_owner_boundary','artifact_root':str(a.relative_to(P))}); raise
 finally:
  stop.set(); t.join(2); atomic(P/'OWNER_TERMINAL.json',{'at_utc':now().isoformat(),'disposition':disposition,'conservative_provider_spend_usd':prior+(time.monotonic()-started)/3600*RATE,'artifact_root':str(a)})
if __name__=='__main__': main()
