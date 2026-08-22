#!/usr/bin/env python3
"""R2 claim adopter: standby first, then producer -> exact consumer only."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent; LAB=ROOT.parent.parent; PROJECT='gemma4_h200_m384_target_verify_attention_executor'; BENCH='h200-downproj-computeinstance-e00qft1sf416qp6knw'
sys.path.insert(0,str(ROOT.parents[6]/'factory'/'src'))
def atomic(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(f'.{p.name}.{os.getpid()}.tmp');t.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n');json.loads(t.read_text());os.replace(t,p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cmd(x,timeout=30):return subprocess.run(x,text=True,capture_output=True,timeout=timeout)
def main():
 a=argparse.ArgumentParser();a.add_argument('--binding',required=True);a.add_argument('--artifact-root',required=True);a.add_argument('--claimed-at',required=True);a.add_argument('--activate-file',required=True);x=a.parse_args();art=(ROOT/x.artifact_root).resolve();art.mkdir(parents=True,exist_ok=True); deadline='2026-07-30T10:49:00Z'; ident=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); kh='/root/.config/nebius/glm-campaign/known_hosts'
 binding=ROOT/x.binding; files=[ROOT/n for n in ('m384_attention_producer_capture.py','m384_grouped_attention_sm90a.cu','m384_attention_h200_runner.py',Path(__file__).name)]
 if not ident.is_file(): raise RuntimeError('strict SSH identity missing')
 remote=['ssh','-i',str(ident),'-o',f'UserKnownHostsFile={kh}','-o','StrictHostKeyChecking=yes','glmrunner@89.169.99.32']
 census=cmd(remote+['sudo -n docker ps --format "{{.ID}} {{.Names}}"; ps -eo pid,args | grep -E "m384_attention|producer_capture" | grep -v grep || true'])
 if census.returncode: raise RuntimeError(census.stderr[-1000:])
 atomic(art/'OWNER_R2_STANDBY_READY.json',{'at_utc':dt.datetime.now(dt.UTC).isoformat().replace('+00:00','Z'),'binding_sha256':sha(binding),'claimed_at':x.claimed_at,'files':{p.name:sha(p) for p in files},'strict_ssh_identity':str(ident),'remote_census':census.stdout,'state':'standby_no_generation1_worker'})
 activate=Path(x.activate_file)
 while not activate.exists(): time.sleep(1)
 atomic(art/'OWNER_R2_PROGRESS.json',{'phase':'adopted_original_claim','claimed_at':x.claimed_at,'deadline_utc':deadline})
 mkdir=cmd(remote+['mkdir -p /home/glmrunner/m384-attention-r2/out'],30)
 stage=cmd(['scp','-i',str(ident),'-o',f'UserKnownHostsFile={kh}',*map(str,files[:-1]),'glmrunner@89.169.99.32:/home/glmrunner/m384-attention-r2/'],120) if not mkdir.returncode else mkdir
 if stage.returncode:
  atomic(art/'REPAIR_READY_R2.json',{'classification':'recoverable_stage_failure','retry_scope':'stage_only','deadline_utc':deadline,'stderr':stage.stderr[-3000:]})
  while dt.datetime.now(dt.UTC)<dt.datetime(2026,7,30,10,49,tzinfo=dt.UTC):
   cmd([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),'heartbeat','--project',PROJECT,'--bench',BENCH,'--expected-claimed-at',x.claimed_at],20);time.sleep(20)
  return 20
 run_remote='mkdir -p /home/glmrunner/m384-attention-r2/out; sudo -n docker run --rm --gpus all -v /home/glmrunner/m384-attention-r2:/work -w /work docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 python3 m384_attention_producer_capture.py --model ${M384_MODEL_PATH:?M384_MODEL_PATH_required} --output /work/capture && python3 m384_attention_h200_runner.py --packet /work/capture/producer_packet.json --source /work/m384_grouped_attention_sm90a.cu --output /work/out/TERMINAL.json'
 work=cmd(remote+[run_remote],max(1,int((dt.datetime(2026,7,30,10,49,tzinfo=dt.UTC)-dt.datetime.now(dt.UTC)).total_seconds())))
 atomic(art/'R2_WORKER_CAPTURE.json',{'exit_code':work.returncode,'stdout':work.stdout[-8000:],'stderr':work.stderr[-8000:],'claimed_at':x.claimed_at})
 # Always retain the claim on a pre-decision failure and accept only an R2-scoped request.
 atomic(art/'OWNER_R2_PROGRESS.json',{'phase':'worker_finished','exit_code':work.returncode,'claimed_at':x.claimed_at,'terminal_expected':'/home/glmrunner/m384-attention-r2/out/TERMINAL.json'})
 if work.returncode:
  atomic(art/'REPAIR_READY_R2.json',{'classification':'recoverable_worker_failure','retry_scope':'producer_or_consumer_only','deadline_utc':deadline,'worker_capture_sha256':sha(art/'R2_WORKER_CAPTURE.json')})
  while dt.datetime.now(dt.UTC)<dt.datetime(2026,7,30,10,49,tzinfo=dt.UTC):
   cmd([sys.executable,'-m','grad_research.gpu_pool','--lab',str(LAB),'heartbeat','--project',PROJECT,'--bench',BENCH,'--expected-claimed-at',x.claimed_at],20);time.sleep(20)
 return work.returncode
if __name__=='__main__':raise SystemExit(main())
