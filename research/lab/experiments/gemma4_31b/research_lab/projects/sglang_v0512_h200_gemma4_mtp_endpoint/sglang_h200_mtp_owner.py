#!/usr/bin/env python3
"""Durable retained H200 stock-then-NEXTN SGLang development owner."""
import argparse, datetime as dt, hashlib, json, os, subprocess, sys, tarfile, time
from pathlib import Path
P = Path(__file__).resolve().parent
N = Path('/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius'); sys.path.insert(0, str(N))
from placement_control import VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, list_items, make_cloud_init, wait_ssh
from stock_control import run_ssh, scp_from, scp_to
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic
from mla_microbench_control import retained_development_window, run_repairable_operation
KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); PUB=KEY.with_suffix('.pub'); WORK='/home/glmrunner/sglang-v0512-gemma4'; IMAGE='docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a'; MODEL='google/gemma-4-31B-it'; REV='b9ea41a2887d8607f594846523f94c6cc75ac8a4'; ASSIST_REV='627c5ec1458b9086b841a91e0512fd31fd2fbbf1'
CK=(P/'../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint').resolve(); ASSIST=P/'artifacts/assistant'; TRACE=(P/'../gemma_exact_cache_trace_contract/TRACE_PACKET.json').resolve()
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def put(path,x): path.parent.mkdir(parents=True,exist_ok=True); t=path.with_suffix(path.suffix+'.part');t.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n');t.replace(path)
def event(path,phase,**x): path.open('a').write(json.dumps({'timestamp':now(),'phase':phase,**x},sort_keys=True)+'\n')
def stage(ip,out,events,label,command,timeout):
 event(events,label,state='start',timeout_seconds=timeout); r=run_ssh(ip,KEY,command,timeout=timeout); (out/f'{label}.stdout.log').write_text(r.stdout);(out/f'{label}.stderr.log').write_text(r.stderr);put(out/f'{label}.json',{'returncode':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest()});event(events,label,state='complete',returncode=r.returncode)
 if r.returncode: raise RuntimeError(f'{label}_failed:{r.returncode}')
 return r
def bindings(deadline):
 b=json.loads((P/'BINDINGS.json').read_text()); a=json.loads((P/'artifacts/ASSISTANT_TERMINAL.json').read_text()); c=json.loads((CK.parent/'CHECKPOINT_TERMINAL.json').read_text()); checks={'assistant_pass':a.get('pass') is True and a.get('revision')==ASSIST_REV,'assistant_files':all((ASSIST/x).is_file() for x in ('config.json','model.safetensors','tokenizer.json')),'checkpoint_terminal':c.get('pass') is True,'checkpoint_files':len(list(CK.iterdir()))==8,'trace_sha':sha((P/b['workload']['trace']).resolve())==b['workload']['trace_sha256'],'empty_inventory':not list_items('instance') and not list_items('disk'),'keypair':KEY.is_file() and PUB.is_file(),'time_budget':3600<deadline-time.time()<=5100,'image':b['runtime']['image']==IMAGE,'placement':b['placement']=={'platform':'gpu-h200-sxm','preset':'1gpu-16vcpu-200gb','disk_gib':250},'runner':(P/'sglang_mtp_runner.py').is_file()}; return {'classification':'sglang_v0512_h200_mtp_precreate','pass':all(checks.values()),'checks':checks,'deadline_epoch':deadline}
def upload(ip,out,events,local,remote,label,timeout):
 event(events,label,state='start'); r=subprocess.run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts',*map(str,sorted(local.iterdir())),f'glmrunner@{ip}:{remote}/'],capture_output=True,text=True,timeout=timeout);put(out/f'{label}.json',{'returncode':r.returncode,'stderr_tail':r.stderr[-1000:],'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest()});event(events,label,state='complete',returncode=r.returncode)
 if r.returncode: raise RuntimeError(f'{label}_failed:{r.returncode}')
def launch(ip,out,events,mode,deadline):
 stage(ip,out,events,'stop_'+mode,"sudo docker rm -f sglang-endpoint >/dev/null 2>&1 || true",60)
 spec='' if mode=='stock' else f' --speculative-algorithm NEXTN --speculative-draft-model-path {WORK}/assistant --speculative-draft-model-revision {ASSIST_REV} --speculative-num-steps 1 --speculative-num-draft-tokens 1 --speculative-eagle-topk 1'
 cmd=f"sudo docker run -d --name sglang-endpoint --gpus all --ipc=host --shm-size=16g --network host -v {WORK}:{WORK} {IMAGE} python3 -m sglang.launch_server --model-path {WORK}/checkpoint --tokenizer-path {WORK}/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 --served-model-name {MODEL} --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics{spec}"
 stage(ip,out,events,'start_'+mode,cmd,180)
 until=min(deadline-900,time.time()+1500)
 while time.time()<until:
  r=run_ssh(ip,KEY,"curl --fail --silent http://127.0.0.1:30000/v1/models || true; sudo docker inspect -f '{{{{.State.Running}}}}' sglang-endpoint 2>/dev/null || true",timeout=45)
  if MODEL in r.stdout and 'true' in r.stdout: event(events,'ready_'+mode);return
  time.sleep(10)
 stage(ip,out,events,'logs_'+mode,'sudo docker logs sglang-endpoint || true',120);raise RuntimeError(f'{mode}_readiness_timeout')
def main():
 q=argparse.ArgumentParser();q.add_argument('--output-dir',type=Path,required=True);q.add_argument('--name',required=True);q.add_argument('--deadline-epoch',type=float,required=True);a=q.parse_args()
 if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()):raise RuntimeError('durable_user_systemd_owner_required')
 out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);events=out/'events.jsonl';pre=bindings(a.deadline_epoch);put(out/'PRECREATE_TERMINAL.json',pre)
 if not pre['pass']:return 2
 status=json.loads((P/'STATUS.json').read_text());status.update({'provider_mutation':'exclusive_durable_owner_only','active_session':{'mode':'development','unit':os.getenv('SYSTEMD_UNIT') or a.name+'.service','unit_manager':'user','pid':os.getpid(),'name':a.name,'artifact_root':str(out),'deadline_epoch':a.deadline_epoch,'expected_terminal':'typed stock c32 and matched native NEXTN MTP c32 rows or typed development failure','forward_progress':'precreate_passed_pending_provider_create'},'next_action':'Attach to retained H200 development owner and repair ordinary defects in place.'});put(P/'STATUS.json',status)
 iid=watchdog=ip=None; code=1; classification='sglang_v0512_h200_mtp_typed_failure'
 try:
  with VerifiedRetainedOwner(a.name,out/'cleanup.json') as owner,retained_development_window(out,events,a.deadline_epoch,600):
   create=subprocess.run(build_create_command(name=a.name,disk_name=a.name+'-boot',cloud_init=make_cloud_init(PUB.read_text()),disk_gib=250,platform='gpu-h200-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180);write_create_diagnostic(out,create)
   if create.returncode:raise RuntimeError(f'provider_create_{create.returncode}')
   iid=extract_instance_id(json.loads(create.stdout));owner.bind_instance(iid);watchdog=start_independent_watchdog(iid,a.name+'-boot',a.deadline_epoch,a.name+'-watchdog',unit_manager='user');event(events,'provider_create',instance_id=iid,watchdog=watchdog)
   for _ in range(120):
    ip=extract_public_ipv4(get_instance(iid) or {});
    if ip:break
    time.sleep(5)
   if not ip:raise RuntimeError('public_ip_timeout')
   wait_ssh(ip,KEY,min(a.deadline_epoch-900,time.time()+600));stage(ip,out,events,'workspace',f'mkdir -p {WORK}/checkpoint {WORK}/assistant {WORK}/run',60);scp_to(ip,KEY,[P/'sglang_mtp_runner.py',TRACE],WORK+'/')
   upload(ip,out,events,ASSIST,WORK+'/assistant','assistant_transfer',min(900,int(a.deadline_epoch-time.time()-1800)))
   upload(ip,out,events,CK,WORK+'/checkpoint','checkpoint_transfer',min(3300,int(a.deadline_epoch-time.time()-1200)))
   stage(ip,out,events,'remote_hashes',f"sha256sum {WORK}/assistant/model.safetensors {WORK}/checkpoint/model.safetensors.index.json",180);stage(ip,out,events,'image_pull',f'sudo docker pull {IMAGE}',min(1200,int(a.deadline_epoch-time.time()-900)))
   stage(ip,out,events,'telemetry_start',f"nohup bash -c 'while true; do date -u +%FT%TZ; nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits; sleep 5; done' >{WORK}/telemetry.csv 2>&1 &",30)
   launch(ip,out,events,'stock',a.deadline_epoch);stage(ip,out,events,'stock_run',f'python3 {WORK}/sglang_mtp_runner.py --trace {WORK}/TRACE_PACKET.json --output {WORK}/run/stock --arm stock',min(1800,int(a.deadline_epoch-time.time()-600)))
   scp_from(ip,KEY,f'{WORK}/run/stock/TERMINAL.json',out/'STOCK_TERMINAL.json');stock=json.loads((out/'STOCK_TERMINAL.json').read_text())
   if not stock.get('pass') or time.time()+1200>a.deadline_epoch: put(out/'MTP_DISPOSITION.json',{'attempted':False,'reason':'stock_invalid_or_insufficient_time'});owner.complete('stock_terminal_mtp_not_admitted');classification='stock_terminal_mtp_not_admitted';code=0
   else:
    launch(ip,out,events,'mtp',a.deadline_epoch);stage(ip,out,events,'mtp_run',f'python3 {WORK}/sglang_mtp_runner.py --trace {WORK}/TRACE_PACKET.json --output {WORK}/run/mtp --arm mtp',min(1800,int(a.deadline_epoch-time.time()-300)))
    scp_from(ip,KEY,f'{WORK}/run/mtp/TERMINAL.json',out/'MTP_TERMINAL.json');mtp=json.loads((out/'MTP_TERMINAL.json').read_text());same=[x['output_id'] for x in stock['rows']]==[x['output_id'] for x in mtp['rows']];gain=1-mtp['service_seconds_per_request']/stock['service_seconds_per_request'];put(out/'MTP_COMPARISON.json',{'output_ids_equal':same,'all_in_service_reduction':gain,'promotion_pass':mtp.get('pass') and same and gain>=.05,'accepted_tokens_metric':'retrieve from metrics artifacts; endpoint terminal does not synthesize it'});owner.complete('stock_and_mtp_complete');classification='stock_and_mtp_complete';code=0
 except Exception as e:put(out/'failure.json',{'classification':'typed_retained_development_failure','type':type(e).__name__,'message':str(e)[:4000],'instance_id':iid,'watchdog':watchdog,'timestamp':now()});event(events,'failure',error_type=type(e).__name__,message=str(e)[:1000])
 put(out/'SUMMARY.json',{'classification':classification,'controller_returncode':code,'instance_id':iid,'watchdog':watchdog,'completed_at_utc':now()});status=json.loads((P/'STATUS.json').read_text());status.update({'active_session':None,'reconciliation_pending':True,'terminal_artifact':str(out/'SUMMARY.json'),'provider_mutation':'forbidden_pending_reconciliation','next_action':'Reconcile typed retained owner terminal and authenticated cleanup.'});put(P/'STATUS.json',status);return code
if __name__=='__main__':raise SystemExit(main())
