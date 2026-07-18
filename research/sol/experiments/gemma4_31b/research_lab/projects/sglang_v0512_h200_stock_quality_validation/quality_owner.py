#!/usr/bin/env python3
import argparse, datetime as dt, hashlib, json, os, subprocess, sys, time
from pathlib import Path
P=Path(__file__).resolve().parent; N=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius');sys.path.insert(0,str(N))
from placement_control import VerifiedRetainedOwner,build_create_command,extract_instance_id,extract_public_ipv4,get_instance,list_items,make_cloud_init,wait_ssh
from stock_control import run_ssh,scp_from,scp_to
from vllm_smoke_control import start_independent_watchdog,write_create_diagnostic
from mla_microbench_control import run_repairable_operation,retained_development_window
KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519');PUB=KEY.with_suffix('.pub');WORK='/home/glmrunner/gemma-quality';IMAGE='docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a';MODEL='google/gemma-4-31B-it';CK=(P/'../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint').resolve()
def now():return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def put(p,x):p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.part');t.write_text(json.dumps(x,sort_keys=True,indent=2)+'\n');t.replace(p)
def ev(p,phase,**x):p.open('a').write(json.dumps({'timestamp':now(),'phase':phase,**x},sort_keys=True)+'\n')
def sh(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def call(ip,out,events,label,cmd,timeout,deadline):
 def op(attempt):
  ev(events,label,state='start',attempt=attempt);r=run_ssh(ip,KEY,cmd,timeout=timeout);(out/(label+'.stdout.log')).write_text(r.stdout);(out/(label+'.stderr.log')).write_text(r.stderr);put(out/(label+'.json'),{'returncode':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest()});ev(events,label,state='complete',returncode=r.returncode,attempt=attempt)
  if r.returncode:raise RuntimeError(label+'_failed_'+str(r.returncode))
  return r
 return run_repairable_operation(op,out,events,deadline,600)
def copy(ip,out,events,paths,remote,label,deadline):
 def op(attempt):
  ev(events,label,state='start',attempt=attempt);r=scp_to(ip,KEY,paths,remote);ev(events,label,state='complete',attempt=attempt);return r
 return run_repairable_operation(op,out,events,deadline,600)
def retrieve(ip,out,events,remote,local,label,deadline):
 def op(attempt):
  ev(events,label,state='start',attempt=attempt);r=scp_from(ip,KEY,remote,local);ev(events,label,state='complete',attempt=attempt);return r
 return run_repairable_operation(op,out,events,deadline,600)
def pre(deadline):
 b=json.loads((P/'BINDINGS.json').read_text());c=json.loads((CK.parent/'CHECKPOINT_TERMINAL.json').read_text()); checks={'suite':(P/'suite/MANIFEST.json').is_file(),'suite_valid':subprocess.run([sys.executable,str(P/'quality_suite.py'),'validate'],capture_output=True).returncode==0,'bindings':b['candidate']['image']==IMAGE and b['checkpoint']['files']==8,'checkpoint':c.get('pass') is True and len(list(CK.iterdir()))==8,'keys':KEY.is_file() and PUB.is_file(),'time':3600<deadline-time.time()<=4800,'inventory_empty':not list_items('instance') and not list_items('disk')};return {'classification':'gemma_paired_quality_precreate','pass':all(checks.values()),'checks':checks,'deadline_epoch':deadline}
def launch(ip,out,events,kv,deadline):
 call(ip,out,events,'stop_'+kv,'sudo docker rm -f gemma-quality >/dev/null 2>&1 || true',60,deadline)
 cmd=f'sudo docker run -d --name gemma-quality --gpus all --ipc=host --shm-size=16g --network host -v {WORK}:{WORK} {IMAGE} python3 -m sglang.launch_server --model-path {WORK}/checkpoint --tokenizer-path {WORK}/checkpoint --dtype bfloat16 --tp-size 1 --kv-cache-dtype {kv} --served-model-name {MODEL} --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --enable-metrics'
 call(ip,out,events,'start_'+kv,cmd,180,deadline)
 for _ in range(100):
  r=run_ssh(ip,KEY,"curl -fsS http://127.0.0.1:30000/v1/models || true",timeout=30)
  if MODEL in r.stdout:ev(events,'ready_'+kv);return
  time.sleep(10)
 call(ip,out,events,'logs_'+kv,'sudo docker logs gemma-quality || true',120,deadline);raise RuntimeError(kv+'_readiness_timeout')
def main():
 a=argparse.ArgumentParser();a.add_argument('--output-dir',type=Path,required=True);a.add_argument('--name',required=True);a.add_argument('--deadline-epoch',type=float,required=True);x=a.parse_args()
 if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()):raise RuntimeError('durable_user_systemd_owner_required')
 out=x.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);events=out/'events.jsonl';gate=pre(x.deadline_epoch);put(out/'PRECREATE_TERMINAL.json',gate)
 if not gate['pass']:return 2
 status=json.loads((P/'STATUS.json').read_text());status.update({'provider_mutation':'exclusive_durable_owner_only','active_session':{'mode':'development','unit':os.getenv('SYSTEMD_UNIT') or x.name+'.service','unit_manager':'user','pid':os.getpid(),'name':x.name,'artifact_root':str(out),'deadline_epoch':x.deadline_epoch,'expected_terminal':'paired BF16/FP8 raw captures, direct reference sentinel, executable score, authenticated cleanup','forward_progress':'precreate_passed_pending_provider_create'},'next_action':'Attach to the retained H200 development owner; repair first-call defects in place.'});put(P/'STATUS.json',status)
 iid=watchdog=ip=None;classification='typed_retained_development_failure';code=1
 try:
  with VerifiedRetainedOwner(x.name,out/'cleanup.json') as owner,retained_development_window(out,events,x.deadline_epoch,600):
   create=subprocess.run(build_create_command(name=x.name,disk_name=x.name+'-boot',cloud_init=make_cloud_init(PUB.read_text()),disk_gib=250,platform='gpu-h200-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180);write_create_diagnostic(out,create)
   if create.returncode:raise RuntimeError('provider_create_'+str(create.returncode))
   iid=extract_instance_id(json.loads(create.stdout));owner.bind_instance(iid);watchdog=start_independent_watchdog(iid,x.name+'-boot',x.deadline_epoch,x.name+'-watchdog',unit_manager='user');ev(events,'provider_create',instance_id=iid,watchdog=watchdog)
   for _ in range(120):
    ip=extract_public_ipv4(get_instance(iid) or {})
    if ip:break
    time.sleep(5)
   if not ip:raise RuntimeError('public_ip_timeout')
   wait_ssh(ip,KEY,min(x.deadline_epoch-1200,time.time()+600));call(ip,out,events,'workspace',f'mkdir -p {WORK}/checkpoint {WORK}/run {WORK}/suite',60,x.deadline_epoch)
   copy(ip,out,events,[P/'quality_suite.py',P/'reference_sentinel.py'],WORK+'/', 'scripts_transfer',x.deadline_epoch);copy(ip,out,events,list((P/'suite').iterdir()),WORK+'/suite/','suite_transfer',x.deadline_epoch);copy(ip,out,events,list(CK.iterdir()),WORK+'/checkpoint/','checkpoint_transfer',x.deadline_epoch)
   call(ip,out,events,'remote_hashes',f'sha256sum {WORK}/checkpoint/model.safetensors.index.json; python3 {WORK}/quality_suite.py validate',180,x.deadline_epoch);call(ip,out,events,'image_pull',f'sudo docker pull {IMAGE}',1200,x.deadline_epoch)
   launch(ip,out,events,'bfloat16',x.deadline_epoch);call(ip,out,events,'control_capture',f'python3 {WORK}/quality_suite.py capture --base http://127.0.0.1:30000 --output {WORK}/run/control',1500,x.deadline_epoch);retrieve(ip,out,events,f'{WORK}/run/control/CAPTURE_TERMINAL.json',out/'CONTROL_CAPTURE_TERMINAL.json','control_terminal_retrieval',x.deadline_epoch)
   launch(ip,out,events,'fp8_e5m2',x.deadline_epoch);call(ip,out,events,'candidate_capture',f'python3 {WORK}/quality_suite.py capture --base http://127.0.0.1:30000 --output {WORK}/run/candidate',1500,x.deadline_epoch);call(ip,out,events,'score',f'python3 {WORK}/quality_suite.py score --control {WORK}/run/control/captures.jsonl --candidate {WORK}/run/candidate/captures.jsonl --output {WORK}/run/PAIRED_SCORE.json',120,x.deadline_epoch);retrieve(ip,out,events,f'{WORK}/run/PAIRED_SCORE.json',out/'PAIRED_SCORE.json','score_retrieval',x.deadline_epoch)
   call(ip,out,events,'stop_for_reference','sudo docker rm -f gemma-quality',90,x.deadline_epoch);call(ip,out,events,'direct_reference',f'sudo docker run --rm --gpus all -v {WORK}:{WORK} {IMAGE} python3 {WORK}/reference_sentinel.py {WORK} {WORK}/suite {WORK}/run/reference.json',1200,x.deadline_epoch);retrieve(ip,out,events,f'{WORK}/run/reference.json',out/'REFERENCE_SENTINEL.json','reference_retrieval',x.deadline_epoch);retrieve(ip,out,events,f'{WORK}/run/control/captures.jsonl',out/'control_captures.jsonl','control_capture_retrieval',x.deadline_epoch);retrieve(ip,out,events,f'{WORK}/run/candidate/captures.jsonl',out/'candidate_captures.jsonl','candidate_capture_retrieval',x.deadline_epoch)
   score=json.loads((out/'PAIRED_SCORE.json').read_text());ref=json.loads((out/'REFERENCE_SENTINEL.json').read_text());control={z['case_id']:z for z in map(json.loads,(out/'control_captures.jsonl').read_text().splitlines())}['teacher_nll']['output']['input_token_logprobs']; identity=ref['input_ids'][1:1+min(len(control),len(ref['input_ids'])-1)]==[z['token_id'] for z in control[:len(ref['input_ids'])-1]]; terminal={'classification':'gemma_paired_quality_terminal','pass':bool(score.get('pass') and identity and ref['scored_tokens']>=128),'paired_score':score,'reference_prompt_token_identity':identity,'reference_scored_tokens':ref['scored_tokens'],'raw_hashes':{'control':sh(out/'control_captures.jsonl'),'candidate':sh(out/'candidate_captures.jsonl')},'instance_id':iid,'watchdog':watchdog};put(out/'TERMINAL.json',terminal);owner.complete('paired_quality_evaluated');classification='paired_quality_complete';code=0
 except Exception as e:put(out/'FAILURE.json',{'classification':'typed_retained_development_failure','type':type(e).__name__,'message':str(e)[:4000],'instance_id':iid,'watchdog':watchdog,'timestamp':now()});ev(events,'failure',error_type=type(e).__name__,message=str(e)[:1000])
 put(out/'SUMMARY.json',{'classification':classification,'controller_returncode':code,'instance_id':iid,'watchdog':watchdog,'completed_at_utc':now()});status=json.loads((P/'STATUS.json').read_text());status.update({'active_session':None,'reconciliation_pending':True,'terminal_artifact':str(out/'SUMMARY.json'),'provider_mutation':'forbidden_pending_reconciliation','next_action':'Reconcile paired quality terminal and authenticated cleanup.'});put(P/'STATUS.json',status);return code
if __name__=='__main__':raise SystemExit(main())
