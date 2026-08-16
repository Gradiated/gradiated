#!/usr/bin/env python3
"""User-systemd retained owner for the admitted exact Gemma vLLM run."""
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path

HERE=Path(__file__).resolve().parent
NEBIUS=Path('/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius'); sys.path.insert(0,str(NEBIUS))
from placement_control import VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, make_cloud_init, wait_ssh
from session_staging import transfer_checkpoint, transfer_timeout_seconds
from stock_control import run_ssh, scp_from, scp_to
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic

KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); PUB=KEY.with_suffix('.pub')
MODEL='google/gemma-4-31B-it'; REV='b9ea41a2887d8607f594846523f94c6cc75ac8a4'
IMAGE='vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
CHECKPOINT=HERE.parent/'sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint'
TRACE=HERE.parent/'gemma_exact_cache_trace_contract/TRACE_PACKET.json'; ASSERTION=HERE/'artifacts/DIRECTOR_IDENTITY_ASSERTION.json'
RUNNER=HERE/'trace_endpoint_runner.py'; WORK='/home/glmrunner/gemma-fixed-session'

def write(path, value):
 path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.part'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); tmp.replace(path)
def emit(path,event,**kw):
 with path.open('a') as f:f.write(json.dumps({'epoch':time.time(),'event':event,**kw},sort_keys=True)+'\n')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identity():
 a=json.loads(ASSERTION.read_text()); t=json.loads(TRACE.read_text()); terminal=CHECKPOINT.parent/'CHECKPOINT_TERMINAL.json'
 checks={'assertion_pass':a.get('pass') is True,'trace_hash':digest(TRACE)==a['authoritative_inputs']['trace_packet']['sha256'],'checkpoint_terminal_hash':digest(terminal)==a['authoritative_inputs']['checkpoint_terminal']['sha256'],'checkpoint_pass':json.loads(terminal.read_text()).get('pass') is True,'checkpoint_index':digest(CHECKPOINT/'model.safetensors.index.json')==a['bound']['checkpoint_index_sha256'],'model':t['identity']['model']==MODEL,'revision':t['identity']['revision']==REV,'groups':[g['concurrency'] for g in t['primary_groups']]==[1,4,8,16],'separate_10k':t['separate_10k_stream']['concurrency']==1}
 if not all(checks.values()):raise RuntimeError('immutable_identity_gate_failed')
 return checks
def remote(deadline): return f'''#!/usr/bin/env bash
set -Eeuo pipefail
w={WORK}; deadline={deadline}; mkdir -p "$w/artifacts" "$w/runtime"
sudo docker rm -f gemma-vllm >/dev/null 2>&1 || true
sudo docker pull '{IMAGE}'
sudo docker image inspect '{IMAGE}' > "$w/runtime/image-inspect.json"
sudo docker run --rm --gpus all --entrypoint nvidia-smi '{IMAGE}' > "$w/runtime/nvidia-smi-image.txt"
(while test $(date +%s) -lt "$deadline"; do nvidia-smi --query-gpu=timestamp,name,uuid,memory.total,memory.used,utilization.gpu,utilization.memory,power.draw --format=csv,noheader,nounits; sleep 1; done) > "$w/runtime/gpu-telemetry.csv" 2> "$w/runtime/gpu-telemetry.stderr" & echo $! > "$w/runtime/gpu-telemetry.pid"
sudo docker run -d --rm --name gemma-vllm --gpus all --ipc=host --shm-size=32g -p 30000:30000 -v "$w:$w" '{IMAGE}' vllm serve "$w/model" --served-model-name '{MODEL}' --dtype bfloat16 --max-model-len 12000 --max-num-seqs 32 --max-num-batched-tokens 65536 --enable-prefix-caching --enable-metrics --host 0.0.0.0 --port 30000 > "$w/runtime/container-id"
until curl -fsS http://127.0.0.1:30000/v1/models > "$w/runtime/models.json"; do test $(date +%s) -lt "$deadline" || exit 70; sleep 5; done
sudo docker exec gemma-vllm python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/semantic" --mode semantic
sudo docker exec gemma-vllm python3 "$w/input/trace_endpoint_runner.py" --trace "$w/input/TRACE_PACKET.json" --output "$w/artifacts/vllm" --mode baseline
curl -fsS http://127.0.0.1:30000/metrics > "$w/artifacts/metrics-final.prom" || true
cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/gpu-telemetry.csv" || true
sudo docker logs gemma-vllm > "$w/artifacts/server.log" 2>&1 || true
python3 - "$w/artifacts" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); semantic=json.load(open(p/'semantic/TERMINAL.json')); vllm=json.load(open(p/'vllm/TERMINAL.json'))
market=any(a['concurrency'] in (8,16) and a['completed_requests_per_second']>=2.094181 for a in vllm.get('arms',[]))
trigger={'pass':semantic.get('pass') is True and vllm.get('pass') is True and vllm.get('failure_count')==0 and vllm.get('reload_count')==0 and market,'market_rps_pass':market,'run_sglang':False,'classification':'vllm_market_trigger_false_cleanup' if not market else 'sglang_not_started_deadline_reserve_unproven'}
json.dump(trigger,open(p/'VLLM_MARKET_TRIGGER.json','w'),sort_keys=True)
json.dump({'schema_version':1,'semantic':semantic,'vllm':vllm,'trigger':trigger},open(p/'SUMMARY.json','w'),sort_keys=True)
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w" -czf "$w/results.tar.gz" artifacts runtime
sha256sum "$w/results.tar.gz" > "$w/results.tar.gz.sha256"
'''
def audit(path,name,deadline):
 c=identity(); src=Path(__file__).read_text(); c.update({'durable_user_owner':'INVOCATION_ID' in src and 'SYSTEMD_EXEC_PID' in src,'shared_retained_owner':'VerifiedRetainedOwner' in src,'user_watchdog':'unit_manager="user"' in src,'rfc1123':name==name.lower() and all(x.islower() or x.isdigit() or x=='-' for x in name),'shared_staging':'transfer_checkpoint' in src,'session_owner_fix':'sudo install -d -o glmrunner -g glmrunner' in src,'entrypoint_override':'--entrypoint nvidia-smi' in src,'exact_image':IMAGE in src,'trace_arrays':'TRACE_PACKET.json' in src,'simultaneous':'threading.Barrier' in RUNNER.read_text(),'semantic_first':'--mode semantic' in src,'telemetry':'gpu-telemetry.csv' in src and '/metrics' in src,'atomic_terminal':'VLLM_MARKET_TRIGGER.json' in src,'conditional_trigger':'market_rps_pass' in src})
 write(path,{'classification':'final_program_audit','pass':all(c.values()),'checks':c,'name':name,'deadline_seconds':deadline}); return 0 if all(c.values()) else 2
def run(parent,name,deadline_seconds):
 if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()):raise RuntimeError('durable user systemd owner required')
 checks=identity(); out=parent/(name+'-run'); out.mkdir(); events=out/'events.jsonl'; deadline=time.time()+deadline_seconds; iid=None; stage='provider_create'
 try:
  with VerifiedRetainedOwner(name,out/'cleanup.json') as owner:
   emit(events,'owner_started',deadline_epoch=deadline,unit_manager='user',checks=checks)
   inv=subprocess.run(['/root/.nebius/bin/nebius','compute','instance','list','--format','json'],capture_output=True,text=True,timeout=60); write(out/'inventory-before-create.json',{'returncode':inv.returncode,'stdout':inv.stdout,'stderr':inv.stderr[-4096:]})
   if inv.returncode or json.loads(inv.stdout):raise RuntimeError('authenticated_inventory_not_empty')
   q=subprocess.run(build_create_command(name=name,disk_name=name+'-boot',cloud_init=make_cloud_init(PUB.read_text()),disk_gib=250,platform='gpu-h200-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180); write_create_diagnostic(out,q)
   if q.returncode:raise RuntimeError('provider_create_failed')
   iid=extract_instance_id(json.loads(q.stdout)); owner.bind_instance(iid); watch=start_independent_watchdog(iid,name+'-boot',deadline,name+'-watchdog',unit_manager='user'); write(out/'watchdog.json',watch); emit(events,'created',instance_id=iid,watchdog=watch)
   ip=None
   while time.time()<min(deadline,time.time()+600):
    item=get_instance(iid); ip=extract_public_ipv4(item) if item else None
    if ip:break
    time.sleep(5)
   if not ip:raise RuntimeError('public_ip_timeout')
   wait_ssh(ip,KEY,min(deadline,time.time()+600)); stage='session_staging'; prep=run_ssh(ip,KEY,f'sudo install -d -o glmrunner -g glmrunner {WORK} {WORK}/model {WORK}/input {WORK}/artifacts && test -w {WORK}/model',timeout=60); write(out/'session-parent.json',{'returncode':prep.returncode,'stdout':prep.stdout,'stderr':prep.stderr})
   if prep.returncode:raise RuntimeError('glmrunner_session_parent_create_failed')
   transfer=transfer_checkpoint(ip,KEY,CHECKPOINT,WORK+'/model',timeout_seconds=min(transfer_timeout_seconds(sum(x.stat().st_size for x in CHECKPOINT.iterdir() if x.is_file())),max(900,int(deadline-time.time()-900)))); write(out/'checkpoint-transfer.json',{**transfer.__dict__}); emit(events,'checkpoint_transferred',**transfer.__dict__)
   stage='program_transfer'; scp_to(ip,KEY,[TRACE,RUNNER],WORK+'/input/')
   stage='science'; r=run_ssh(ip,KEY,['bash',WORK+'/input/run.sh'],timeout=max(60,int(deadline-time.time()-120)),input_text=None) if False else run_ssh(ip,KEY,'bash -s',timeout=max(60,int(deadline-time.time()-120)),input_text=remote(int(deadline))); write(out/'remote-diagnostic.json',{'returncode':r.returncode,'stdout':r.stdout[-16000:],'stderr':r.stderr[-16000:]})
   scp_from(ip,KEY,WORK+'/results.tar.gz',out/'results.tar.gz'); scp_from(ip,KEY,WORK+'/results.tar.gz.sha256',out/'results.tar.gz.sha256')
   if r.returncode:raise RuntimeError('typed_remote_science_failure')
   owner.complete('exact_vllm_h200_fixed_session_terminal')
 except Exception as e:
  write(out/'failure.json',{'classification':'typed_presemantic_failure' if stage!='science' else 'typed_scientific_failure','stage':stage,'error_type':type(e).__name__,'message':str(e),'instance_id':iid}); emit(events,'failure',stage=stage,error_type=type(e).__name__,message=str(e)); return 1
 return 0
def main():
 p=argparse.ArgumentParser(); s=p.add_subparsers(dest='cmd',required=True); a=s.add_parser('audit');a.add_argument('--output',type=Path,required=True);a.add_argument('--name',required=True);a.add_argument('--deadline-seconds',type=int,default=5400);r=s.add_parser('run');r.add_argument('--artifacts-parent',type=Path,required=True);r.add_argument('--name',required=True);r.add_argument('--deadline-seconds',type=int,default=5400);x=p.parse_args();return audit(x.output,x.name,x.deadline_seconds) if x.cmd=='audit' else run(x.artifacts_parent,x.name,x.deadline_seconds)
if __name__=='__main__':raise SystemExit(main())
