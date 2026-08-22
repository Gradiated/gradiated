#!/usr/bin/env python3
"""Durable controller-host owner for the single bound H200 component run."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,'/root/workspace/research/factory/src')
from grad_research.gpu_pool import GpuPool
from grad_research.gpu_claim_session import GpuClaimSession
P=Path('/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_fp8_downproj_residual_norm_fusion')
LAB=P.parent.parent
BENCH='h200-downproj-computeinstance-e00qft1sf416qp6knw'; PROJECT=P.name
ART=P/'artifacts'/'h200-downproj-compile-repair-20260730t0929z'; ART.mkdir(parents=True,exist_ok=True)
DEADLINE='2026-07-30T10:05:00Z'
def atomic(p,o):
 t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n'); json.loads(t.read_text()); t.replace(p)
def run(cmd,**kw): return subprocess.run(cmd,text=True,capture_output=True,**kw)
def retain(session, diagnostic):
 atomic(ART/'REPAIR_DIAGNOSTIC.json',diagnostic)
 command=['/root/workspace/research/factory/tools/repair-handshake','hold','--root',str(ART),'--repair-id','compile-repair-r2','--deadline',DEADLINE,'--failure-kind','integration','--diagnostic',str(ART/'REPAIR_DIAGNOSTIC.json'),'--retry-scope','runner_stream_api_or_retrieval_only']
 held=run(command,timeout=max(1,int(__import__('datetime').datetime.fromisoformat(DEADLINE.replace('Z','+00:00')).timestamp()-time.time()+10)))
 atomic(ART/'REPAIR_HOLD_RESULT.json',{'returncode':held.returncode,'stdout':held.stdout,'stderr':held.stderr})
 # The hard fence is the only release path after a recoverable failure.
 session.release(condition='maintenance',contents={'state':'repair_deadline_maintenance','project':PROJECT,'summary':'Recoverable compile-repair owner held its claim through the director hard fence.'})
def main():
 pool=GpuPool(LAB)
 release={'state':'component_owner_terminal','project':PROJECT,'summary':'H200 exact component attempt terminal is in project artifacts; image/cache may remain resident.'}
 session=GpuClaimSession(pool,PROJECT,BENCH,lease_seconds=1800,heartbeat_seconds=30,release_condition='maintenance')
 session.__enter__()
 try:
  atomic(ART/'OWNER_STATE.json',{'phase':'claimed','claimed_at':session.claimed_at,'bench':BENCH,'deadline_utc':DEADLINE})
  (ART/'OWNER_READY').write_text(session.claimed_at+'\n')
  show=pool.show(bench_id=BENCH); ci=show['contents']['connection_identity']; host=ci['public_ipv4']; user=ci['ssh_user']; key=ci['ssh_identity_path']; known=ci['known_hosts_namespace']
  ssh=['ssh','-i',key,'-o','UserKnownHostsFile='+known,'-o','StrictHostKeyChecking=yes',user+'@'+host]
  remote='/home/glmrunner/downproj_20260730t0913z'; output=remote+'/out-r2'
  mkdir=run(ssh+['mkdir -p '+remote],timeout=30)
  if mkdir.returncode:
   retain(session,{'classification':'recoverable_integration_defect','stage':'remote_mkdir','stdout':mkdir.stdout,'stderr':mkdir.stderr,'candidate_cuda_started':False}); return
  cp=run(['scp','-i',key,'-o','UserKnownHostsFile='+known,'-o','StrictHostKeyChecking=yes',str(P/'h200_component_runner.py'),user+'@'+host+':'+remote+'/'],timeout=60)
  (ART/'scp.stdout').write_text(cp.stdout);(ART/'scp.stderr').write_text(cp.stderr)
  if cp.returncode: retain(session,{'classification':'recoverable_integration_defect','stage':'scp','stderr':cp.stderr,'candidate_cuda_started':False});return
  command=f"mkdir {output} && cd {remote} && sudo -n docker run --rm --gpus all -v {remote}:/work -e OUT=/work/out-r2 docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 python3 /work/h200_component_runner.py --output /work/out-r2/H200_COMPONENT_TERMINAL.json"
  atomic(ART/'OWNER_STATE.json',{'phase':'remote_science','claimed_at':session.claimed_at,'remote':remote})
  r=run(ssh+[command],timeout=2500); (ART/'remote.stdout').write_text(r.stdout);(ART/'remote.stderr').write_text(r.stderr)
  get=run(['scp','-i',key,'-o','UserKnownHostsFile='+known,'-o','StrictHostKeyChecking=yes',user+'@'+host+':'+output+'/H200_COMPONENT_TERMINAL.json',str(ART/'remote_terminal.json')],timeout=60)
  if get.returncode: retain(session,{'classification':'retrieval_defect','remote_exit':r.returncode,'stdout_path':str(ART/'remote.stdout'),'stderr_path':str(ART/'remote.stderr'),'candidate_cuda_started':'unknown'});return
  term=json.loads((ART/'remote_terminal.json').read_text()); atomic(P/'H200_COMPONENT_TERMINAL.json',term)
  atomic(ART/'OWNER_STATE.json',{'phase':'terminal_retrieved','claimed_at':session.claimed_at,'classification':term['classification'],'terminal':str(P/'H200_COMPONENT_TERMINAL.json')})
  if term.get('classification') != 'interpretable_component_measurement':
   retain(session,{'classification':term.get('classification','unknown'),'stage':'remote_runner','terminal':str(ART/'remote_terminal.json'),'candidate_cuda_started':term.get('candidate_cuda_started'),'science_started':term.get('science_started')}); return
  session.check(); session.release(condition='maintenance',contents=release)
 except BaseException as error:
  if not session.released: retain(session,{'classification':'owner_exception','error':repr(error),'candidate_cuda_started':'unknown'})
if __name__=='__main__': main()
