#!/usr/bin/env python3
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,subprocess,sys,tarfile,time
from pathlib import Path
P=Path(__file__).resolve().parent;N=Path('/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius');sys.path.insert(0,str(N))
from placement_control import VerifiedRetainedOwner,build_create_command,extract_instance_id,extract_public_ipv4,get_instance,list_items,make_cloud_init,wait_ssh
from session_staging import transfer_checkpoint,transfer_timeout_seconds
from stock_control import run_ssh,scp_from,scp_to
from vllm_smoke_control import start_independent_watchdog,write_create_diagnostic
import mla_microbench_control as controller
IMAGE='docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79';KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519');PUB=KEY.with_suffix('.pub');CK=P/'artifacts/w4-checkpoint-owner-20260717T223754Z/checkpoint-repair-2';TERM=P/'W4_CHECKPOINT_TERMINAL.json';RATE=2.15;DISK=.01215275
def put(p:Path,v:object)->None:
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.part');t.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');t.replace(p)
def transfer_contract()->tuple[object,...]:
 rows=[]
 for path in sorted(CK.iterdir()):
  if path.is_file() and path.name not in {'model-files.sha256','.campaign-integrity-v1','.campaign-staging-contract-v1'}:
   digest=hashlib.sha256()
   with path.open('rb') as handle:
    for block in iter(lambda:handle.read(16*1024*1024),b''):digest.update(block)
   rows.append(f'{digest.hexdigest()}  {path.name}')
 manifest=CK/'model-files.sha256';temp=manifest.with_suffix('.sha256.part');temp.write_text('\n'.join(rows)+'\n');temp.replace(manifest)
 from session_staging import checkpoint_files
 files=checkpoint_files(CK)
 return files
def remote(d:int)->str:
 return '\n'.join(['set -Eeuo pipefail','w=/home/glmrunner/w4-endpoint; m=$w/checkpoint; mkdir -p "$w"',f'sudo docker pull {IMAGE}','sudo docker rm -f w4-endpoint >/dev/null 2>&1 || true',f'''sudo docker run -d --rm --name w4-endpoint --gpus all --ipc=host --shm-size=16g -p 8000:8000 -v "$w:$w" {IMAGE} vllm serve "$m" --quantization awq --dtype bfloat16 --kv-cache-dtype fp8_e4m3fn --enable-prefix-caching --max-model-len 5000 --max-num-seqs 128 --max-num-batched-tokens 524288 --limit-mm-per-prompt '{{"image":0,"audio":0}}' > "$w/container-id.txt"''',f'ready=0; while test "$(date +%s)" -lt {d}; do if curl --fail --silent http://127.0.0.1:8000/v1/models > "$w/models.json"; then ready=1; break; fi; sleep 5; done; test "$ready" = 1','sudo docker logs w4-endpoint > "$w/vllm-load.log" 2>&1 || true',"sudo docker exec w4-endpoint python3 -c 'from vllm.model_executor.layers.quantization.machete import MacheteLinearKernel; print(MacheteLinearKernel.apply_weights)' > \"$w/machete-consumer.txt\"",'python3 "$w/endpoint_runner.py" --tokenizer "$m" --output "$w/fp8-kv" --concurrencies 96,128','nvidia-smi --query-gpu=name,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits > "$w/nvml-final.csv"','sudo docker logs w4-endpoint > "$w/vllm-final.log" 2>&1 || true',"tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf \"$w/result.tar.gz\" -C \"$w\" fp8-kv models.json machete-consumer.txt nvml-final.csv vllm-load.log vllm-final.log",'sha256sum "$w/result.tar.gz" > "$w/result.tar.gz.sha256"'])
def main()->int:
 a=argparse.ArgumentParser();a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--name',required=True);a.add_argument('--deadline-epoch',type=float,required=True);x=a.parse_args()
 if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()):raise RuntimeError('durable user systemd owner required')
 out=x.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);files=transfer_contract();total_bytes=sum(row.bytes for row in files);timeout=transfer_timeout_seconds(total_bytes);checks={'terminal':json.loads(TERM.read_text()).get('pass') is True,'checkpoint':CK.is_dir(),'transfer_manifest':any(row.path=='model-files.sha256' for row in files),'runner':(P/'endpoint_runner.py').is_file(),'keys':KEY.is_file() and PUB.is_file(),'inventory':not list_items('instance') and not list_items('disk'),'deadline':0<x.deadline_epoch-time.time()<=4500,'budget':(RATE+DISK)*4500/3600<=3.5};put(out/'PRECREATE_TERMINAL.json',{'type':'h100_w4_full_endpoint_precreate','checks':checks,'pass':all(checks.values()),'transfer_files_total':len(files),'transfer_bytes':total_bytes,'transfer_timeout_seconds':timeout,'runner_sha256':hashlib.sha256((P/'endpoint_runner.py').read_bytes()).hexdigest()})
 if not all(checks.values()):return 1
 status=json.loads((P/'STATUS.json').read_text());status.update({'provider_mutation':'exclusive_durable_owner_only','active_session':{'mode':'development','unit':os.getenv('SYSTEMD_UNIT'),'unit_manager':'systemd --user','owner_pid':os.getpid(),'name':x.name,'artifact_root':str(out),'deadline_epoch':x.deadline_epoch,'expected_terminal':'typed c96/c128 FP8-KV endpoint rows or typed provider/runtime failure with authenticated cleanup'},'summary':'Retained H100 development owner stages AWQ W4 and executes c96/c128 FP8-KV endpoint.','next_action':'Attach and repair first-call defects in place, or reconcile the owner terminal.'});put(P/'STATUS.json',status);iid=None;watch=None;code=1;classification='h100_w4_endpoint_typed_failure'
 try:
  with VerifiedRetainedOwner(x.name,out/'cleanup.json') as owner, controller.retained_development_window(out,out/'events.jsonl',x.deadline_epoch,600):
   create=subprocess.run(build_create_command(name=x.name,disk_name=x.name+'-boot',cloud_init=make_cloud_init(PUB.read_text()),disk_gib=250,platform='gpu-h100-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180);write_create_diagnostic(out,create)
   if create.returncode:raise RuntimeError(f'provider create returned {create.returncode}')
   iid=extract_instance_id(json.loads(create.stdout));owner.bind_instance(iid);watch=start_independent_watchdog(iid,x.name+'-boot',x.deadline_epoch,x.name+'-watchdog',unit_manager='user');ready=min(x.deadline_epoch,time.time()+600);ip=None
   while time.time()<ready:
    payload=get_instance(iid);ip=extract_public_ipv4(payload) if payload else None
    if ip:break
    time.sleep(5)
   if not ip:raise RuntimeError('public IP readiness deadline exceeded')
   wait_ssh(ip,KEY,ready);work='/home/glmrunner/w4-endpoint';run_ssh(ip,KEY,f'sudo install -d -o glmrunner -g glmrunner {work}',timeout=60);scp_to(ip,KEY,[P/'endpoint_runner.py'],work+'/');transfer_checkpoint(ip,KEY,CK,work+'/checkpoint',timeout_seconds=timeout);r=run_ssh(ip,KEY,'bash -s',timeout=max(60,int(x.deadline_epoch-time.time())),input_text=remote(int(x.deadline_epoch)));(out/'remote.stdout.log').write_text(r.stdout);(out/'remote.stderr.log').write_text(r.stderr)
   if r.returncode:raise RuntimeError(f'remote endpoint stage returned {r.returncode}')
   scp_from(ip,KEY,work+'/result.tar.gz',out/'result.tar.gz');scp_from(ip,KEY,work+'/result.tar.gz.sha256',out/'result.tar.gz.sha256')
   with tarfile.open(out/'result.tar.gz') as z:z.extractall(out/'retrieved',filter='data')
   if not json.loads((out/'retrieved/fp8-kv/TERMINAL.json').read_text()).get('pass'):raise RuntimeError('typed FP8-KV endpoint terminal failed')
   owner.complete('h100_w4_fp8_kv_endpoint_complete');code=0;classification='h100_w4_fp8_kv_endpoint_complete'
 except Exception as e:put(out/'failure.json',{'type':type(e).__name__,'message':str(e)[:4000],'instance_id':iid,'watchdog':watch})
 put(out/'SUMMARY.json',{'classification':classification,'controller_returncode':code,'instance_id':iid,'watchdog':watch,'completed_at_utc':dt.datetime.now(dt.UTC).isoformat()});status=json.loads((P/'STATUS.json').read_text());status.update({'active_session':None,'reconciliation_pending':True,'terminal_artifact':str(out/'SUMMARY.json'),'provider_mutation':'forbidden_pending_reconciliation','summary':'Retained H100 endpoint owner terminal requires typed reconciliation.','next_action':'Reconcile retrieved endpoint rows and authenticated cleanup.'});put(P/'STATUS.json',status);return code
if __name__=='__main__':raise SystemExit(main())
