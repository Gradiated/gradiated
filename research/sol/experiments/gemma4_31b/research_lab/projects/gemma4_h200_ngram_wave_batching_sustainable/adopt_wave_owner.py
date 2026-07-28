#!/usr/bin/env python3
"""PID-managed recovery owner: retrieve, settle, clean, and release one live arm."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, shutil, subprocess, sys, tarfile, time
from pathlib import Path

P=Path(__file__).resolve().parent; LAB=P.parents[1]; FACTORY=Path('/root/workspace/research/factory/src'); NEBIUS=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius'); KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); KNOWN=Path('/root/.config/nebius/glm-campaign/known_hosts')
NAME='gemma4_h200_ngram_wave_batching_sustainable'; BENCH='h200-ngram-verifier-e00kcm9nfhwt7e7gbc'; REMOTE='/home/glmrunner/gemma4-ngram-wave-admission'; RATE=2.46; INITIAL=dt.datetime(2026,7,24,15,28,41,321043,tzinfo=dt.timezone.utc)
def now(): return dt.datetime.now(dt.timezone.utc)
def atomic(path,value):
 path=Path(path); q=path.with_suffix(path.suffix+'.part'); q.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); q.replace(path)
def run(a,**kw): return subprocess.run(a,text=True,capture_output=True,check=False,**kw)
def pool(*a): return run(['python3','-m','grad_research.gpu_pool','--lab',str(LAB),*a],env={**os.environ,'PYTHONPATH':str(FACTORY)})
def ssh(host,command,timeout=180): return run(['ssh','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{host}',command],timeout=timeout)
def scp(host,remote,local): return run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={KNOWN}',f'glmrunner@{host}:{remote}',str(local)],timeout=900)
def host():
 inv=json.loads((LAB/'runtime/gpus.json').read_text()); b=inv['benches'][BENCH]; sys.path.insert(0,str(NEBIUS)); from placement_control import extract_public_ipv4,get_instance
 value=extract_public_ipv4(get_instance(b['resource']['instance_id']))
 if not value: raise RuntimeError('typed_provider_boundary:no_public_ip')
 return value
def status(summary,spend,terminal=None,session=None):
 x=json.loads((P/'STATUS.json').read_text()); x['summary']=summary; x['actual_spend_usd']=spend; x['active_session']=session
 if terminal is not None: x['terminal']=terminal
 atomic(P/'STATUS.json',x)
def main():
 artifact=P/'artifacts'/now().strftime('wave-adoption-%Y%m%dt%H%M%Sz'); artifact.mkdir(parents=True)
 owner_state=Path(os.environ['WAVE_ADOPTION_OWNER_STATE'])
 for _ in range(20):
  if owner_state.exists(): break
  time.sleep(.05)
 owner=json.loads(owner_state.read_text())
 x=json.loads((P/'STATUS.json').read_text()); x['active_session']={'unit':str(owner_state.resolve()),'unit_manager':'pid','pid':owner['pid'],'start_ticks':owner['start_ticks'],'deadline_utc':'2026-07-24T16:45:00Z','artifact_root':str(artifact),'bench_id':BENCH,'remote_root':REMOTE,'expected_terminal':'FINAL_TERMINAL.json'}; x['summary']='PID-managed adoption owner claimed solely to retrieve, settle, clean, and release the existing wave terminal; no science launch is authorized.'; atomic(P/'STATUS.json',x)
 claim=pool('claim','--project',NAME,'--bench',BENCH,'--lease-seconds','300'); (artifact/'claim.stdout').write_text(claim.stdout); (artifact/'claim.stderr').write_text(claim.stderr)
 if claim.returncode: raise RuntimeError('typed_pool_boundary:claim')
 h=host(); terminal_check=ssh(h,f'test -f {REMOTE}/out/FINAL_TERMINAL.json && cat {REMOTE}/out/FINAL_TERMINAL.json || true',45); (artifact/'terminal-check.stdout').write_text(terminal_check.stdout); (artifact/'terminal-check.stderr').write_text(terminal_check.stderr)
 if not terminal_check.stdout.strip(): raise RuntimeError('typed_adoption_boundary:terminal_missing_no_replay_authorized')
 remote_archive=f'{REMOTE}/adoption-compact.tar.gz'; pack=ssh(h,f'cd {REMOTE} && tar -czf {remote_archive} OWNER.json OWNER.log out && sha256sum {remote_archive} > {remote_archive}.sha256',180); (artifact/'archive.stdout').write_text(pack.stdout); (artifact/'archive.stderr').write_text(pack.stderr)
 if pack.returncode: raise RuntimeError('recoverable_retrieval_defect:archive')
 for name in ('adoption-compact.tar.gz','adoption-compact.tar.gz.sha256'):
  copied=scp(h,f'{REMOTE}/{name}',artifact/name)
  if copied.returncode: (artifact/(name+'.scp.stderr')).write_text(copied.stderr); raise RuntimeError('recoverable_retrieval_defect:scp')
 expected=(artifact/'adoption-compact.tar.gz.sha256').read_text().split()[0]; got=hashlib.sha256((artifact/'adoption-compact.tar.gz').read_bytes()).hexdigest()
 if got!=expected: raise RuntimeError('recoverable_retrieval_defect:hash')
 with tarfile.open(artifact/'adoption-compact.tar.gz') as tar: tar.extractall(artifact/'retrieved',filter='data')
 terminal=json.loads((artifact/'retrieved/out/FINAL_TERMINAL.json').read_text())
 if not terminal.get('candidate_science_consumed'): raise RuntimeError('typed_terminal_boundary:unconsumed')
 cleanup=ssh(h,'sudo docker rm -f gemma4-ngram-wave-admission; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits',90); (artifact/'cleanup.stdout').write_text(cleanup.stdout); (artifact/'cleanup.stderr').write_text(cleanup.stderr)
 if cleanup.returncode: raise RuntimeError('typed_cleanup_boundary:stock_container')
 elapsed=max(0,(now()-INITIAL).total_seconds()); spend=elapsed/3600*RATE
 contents={'project':NAME,'result':terminal['result'],'artifacts':str(artifact.relative_to(P)),'server_state':'Stock wave-admission container removed after terminal retrieval; accelerator is unoccupied.','checkpoint':'/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.','caches':'Image, checkpoint, CUDA graph, JIT, tokenizer, and runtime caches retained.','gpu_processes':cleanup.stdout.strip()}
 atomic(P/'BENCH_CONTENTS.json',contents); release=pool('release','--project',NAME,'--condition','ready','--contents',str(P/'BENCH_CONTENTS.json')); (artifact/'release.stdout').write_text(release.stdout); (artifact/'release.stderr').write_text(release.stderr)
 if release.returncode: raise RuntimeError('typed_pool_boundary:release')
 terminal_record={'classification':'measured_wave_admission','path':str((artifact/'retrieved/out/FINAL_TERMINAL.json').relative_to(P)),'retain_wave_admission':terminal['retain_wave_admission'],'requests':terminal['primary']['requests'],'planning_cost_usd_per_million_total_tokens':terminal['primary']['planning_cost_usd_per_million_total_tokens']}
 status('Retrieved the sole wave terminal, removed the stock container, settled full retained-H200 exposure, and released the bench ready.',spend,terminal_record)
 with (P/'RESEARCH_LOG.md').open('a') as log: log.write(f'\n## {now().isoformat()} — terminal recovered\n\nRetrieved the one consumed terminal through PID-managed adoption; no replay. All 1,036 requests completed, but wave policy did not meet the preregistered acceptance decision. Conservative retained-H200 exposure: ${spend:.6f}. Artifacts: `{artifact.relative_to(P)}`.\n')
if __name__=='__main__': main()
