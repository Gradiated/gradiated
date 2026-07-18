#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

P = Path(__file__).resolve().parent
N = Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius')
sys.path.insert(0, str(N))
from placement_control import VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, list_items, make_cloud_init, wait_ssh, get_instance
from stock_control import run_ssh, scp_from, scp_to
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic
from mla_microbench_control import retained_development_window

KEY = Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
PUB = KEY.with_suffix('.pub')
MODEL = 'google/gemma-4-31B-it'
REV = 'b9ea41a2887d8607f594846523f94c6cc75ac8a4'
IMAGE = 'docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427'
CK = (P / '../sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint').resolve()
TRACE = (P / '../gemma_exact_cache_trace_contract/TRACE_PACKET.json').resolve()
WORK = '/home/glmrunner/sglang-gemma-h200'
RATE, DISK, LIMIT = 2.45, 0.0097222, 3.75

def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); temp=path.with_suffix(path.suffix+'.part'); temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); temp.replace(path)
def emit(path, phase, **data):
    with path.open('a') as f: f.write(json.dumps({'timestamp':now(),'phase':phase,**data},sort_keys=True)+'\n')

def bound_check(deadline):
    b=json.loads((P/'BINDINGS.json').read_text()); rows=[]
    for row in b['authoritative_inputs']:
        path=(P/row['path']).resolve(); rows.append((row['role'],path,sha(path)==row['sha256']))
    checkpoint=json.loads((CK.parent/'CHECKPOINT_TERMINAL.json').read_text())
    checks={'all_bound_digests':all(x[2] for x in rows),'checkpoint_terminal_pass':checkpoint.get('pass') is True,
      'checkpoint_files':CK.is_dir() and len(list(CK.iterdir()))==8,'checkpoint_index':sha(CK/'model.safetensors.index.json')=='d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2',
      'runner':(P/'sglang_endpoint_runner.py').is_file(),'owner_regression':subprocess.run([sys.executable,str(P/'test_retained_owner.py')],capture_output=True,text=True,timeout=60).returncode==0,
      'bound_corrected_regression':subprocess.run([sys.executable,str(P.parent/'h200_w4_full_endpoint_background_frontier/test_owner_regression.py')],capture_output=True,text=True,timeout=60).returncode==0,
      'empty_inventory':not list_items('instance') and not list_items('disk'),'keypair':KEY.is_file() and PUB.is_file(),
      'budget':1200 < deadline-time.time() <= 4800 and (RATE+DISK)*(deadline-time.time())/3600 <= LIMIT,
      'placement':b['placement']=={'platform':'gpu-h200-sxm','preset':'1gpu-16vcpu-200gb','disk_gib':250}}
    return {'classification':'sglang_h200_c32_precreate','pass':all(checks.values()),'checks':checks,'bindings':[{ 'role':r,'path':str(p),'pass':ok} for r,p,ok in rows],'requested_provider_seconds':deadline-time.time()}

def stage(ip,out,events,label,command,timeout):
    emit(events,label,state='start',timeout_seconds=timeout); r=run_ssh(ip,KEY,command,timeout=timeout)
    (out/f'{label}.stdout.log').write_text(r.stdout);(out/f'{label}.stderr.log').write_text(r.stderr)
    put(out/f'{label}.json',{'returncode':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr.encode()).hexdigest()});emit(events,label,state='complete',returncode=r.returncode)
    if r.returncode: raise RuntimeError(f'{label}_failed:{r.returncode}')
    return r

def diagnostics(ip,out,events,label):
    stage(ip,out,events,label+'_capture',f'''set +e; mkdir -p {WORK}/diagnostics; sudo docker logs sglang-endpoint >{WORK}/diagnostics/{label}.log 2>&1; sudo docker inspect -f '{{{{json .State}}}}' sglang-endpoint >{WORK}/diagnostics/{label}.state.json 2>&1; nvidia-smi --query-gpu=name,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits >{WORK}/diagnostics/{label}.gpu.csv 2>&1; exit 0''',120)
    d=out/'diagnostics';d.mkdir(exist_ok=True)
    for n in (f'{label}.log',f'{label}.state.json',f'{label}.gpu.csv'): scp_from(ip,KEY,f'{WORK}/diagnostics/{n}',d/n)
    put(out/f'{label}_diagnostics.json',{'files':[n for n in (f'{label}.log',f'{label}.state.json',f'{label}.gpu.csv')],'pass':all((d/n).is_file() for n in (f'{label}.log',f'{label}.state.json',f'{label}.gpu.csv'))})

def main():
    q=argparse.ArgumentParser();q.add_argument('--output-dir',type=Path,required=True);q.add_argument('--name',required=True);q.add_argument('--deadline-epoch',type=float,required=True);a=q.parse_args()
    if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()): raise RuntimeError('durable user systemd owner required')
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);events=out/'events.jsonl';pre=bound_check(a.deadline_epoch);put(out/'PRECREATE_TERMINAL.json',pre)
    if not pre['pass']: return 2
    iid=watchdog=None; code=1; classification='sglang_h200_c32_typed_failure'; ip=None
    status=json.loads((P/'STATUS.json').read_text());status.update({'provider_mutation':'exclusive_retained_development_owner','active_session':{'mode':'development','unit':os.getenv('SYSTEMD_UNIT') or a.name+'.service','unit_manager':'user','pid':os.getpid(),'name':a.name,'artifact_root':str(out),'deadline_epoch':a.deadline_epoch,'expected_terminal':'atomic SGLang c32 bundle, conditional 10K bundle, or typed retained failure with authenticated cleanup'},'next_action':'Attach to the retained H200 development owner; repair ordinary first-call defects in place.'});put(P/'STATUS.json',status)
    try:
      with VerifiedRetainedOwner(a.name,out/'cleanup.json') as owner, retained_development_window(out,events,a.deadline_epoch,600):
        create=subprocess.run(build_create_command(name=a.name,disk_name=a.name+'-boot',cloud_init=make_cloud_init(PUB.read_text()),disk_gib=250,platform='gpu-h200-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180);write_create_diagnostic(out,create)
        if create.returncode: raise RuntimeError(f'provider_create_returned_{create.returncode}')
        iid=extract_instance_id(json.loads(create.stdout)); owner.bind_instance(iid); watchdog=start_independent_watchdog(iid,a.name+'-boot',a.deadline_epoch,a.name+'-watchdog',unit_manager='user');emit(events,'provider_create',instance_id=iid,watchdog=watchdog)
        owner = None
        for _ in range(120):
          x=get_instance(iid);ip=extract_public_ipv4(x) if x else None
          if ip:break
          time.sleep(5)
        if not ip: raise RuntimeError('public_ip_timeout')
        wait_ssh(ip,KEY,min(a.deadline_epoch-660,time.time()+600));stage(ip,out,events,'workspace',f'mkdir -p {WORK}',60);scp_to(ip,KEY,[P/'sglang_endpoint_runner.py',TRACE],WORK+'/')
        stage(ip,out,events,'checkpoint_directory',f'mkdir -p {WORK}/checkpoint && test -w {WORK}/checkpoint',60)
        transfer=subprocess.run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts',*map(str,sorted(CK.iterdir())),f'glmrunner@{ip}:{WORK}/checkpoint/'],capture_output=True,text=True,timeout=min(3600,max(900,int(a.deadline_epoch-time.time()-1100))));put(out/'checkpoint_transfer.json',{'returncode':transfer.returncode,'stderr_sha256':hashlib.sha256(transfer.stderr.encode()).hexdigest(),'stderr_tail':transfer.stderr[-2000:]})
        if transfer.returncode:raise RuntimeError('checkpoint_transfer_failed')
        stage(ip,out,events,'checkpoint_remote_identity',f'sha256sum {WORK}/checkpoint/model.safetensors.index.json',60)
        stage(ip,out,events,'image_pull',f'sudo docker pull {IMAGE}',min(1800,max(120,int(a.deadline_epoch-time.time()-850))))
        launch=f"sudo docker rm -f sglang-endpoint >/dev/null 2>&1 || true; sudo docker run -d --name sglang-endpoint --gpus all --ipc=host --shm-size=16g -p 30000:30000 -v {WORK}:{WORK} --entrypoint bash {IMAGE} -lc 'python3 -m sglang.launch_server --model-path {WORK}/checkpoint --tokenizer-path {WORK}/checkpoint --tp-size 1 --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --served-model-name {MODEL} --enable-metrics --enable-cache-report --log-requests --context-length 12000 --host 0.0.0.0 --port 30000'"
        stage(ip,out,events,'server_launch',launch,180);stage(ip,out,events,'telemetry_start',f"nohup bash -c 'while sudo docker inspect -f '{{{{.State.Running}}}}' sglang-endpoint 2>/dev/null | grep -qx true; do date -u +%FT%TZ; nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits; sleep 5; done' >{WORK}/telemetry.csv 2>&1 &",60)
        ready=False
        for _ in range(120):
          p=run_ssh(ip,KEY,'curl -fsS http://127.0.0.1:30000/v1/models || true',timeout=30)
          if MODEL in p.stdout:ready=True;break
          time.sleep(10)
        if not ready: diagnostics(ip,out,events,'readiness_failure');raise RuntimeError('server_readiness_failed')
        emit(events,'server_readiness',state='complete');stage(ip,out,events,'c32_runner_start',f'nohup python3 {WORK}/sglang_endpoint_runner.py --trace {WORK}/TRACE_PACKET.json --output {WORK}/run --deadline {a.deadline_epoch} >{WORK}/runner.stdout.log 2>{WORK}/runner.stderr.log & echo $! >{WORK}/runner.pid',60)
        while time.time()<a.deadline_epoch-620:
          s=run_ssh(ip,KEY,f'test -f {WORK}/run/TERMINAL.json && echo terminal || true; sudo docker inspect -f "{{{{.State.Running}}}}" sglang-endpoint 2>/dev/null || echo server-exited',timeout=45)
          if 'terminal' in s.stdout:break
          if 'server-exited' in s.stdout:diagnostics(ip,out,events,'server_exit');raise RuntimeError('server_exited_before_terminal')
          time.sleep(30)
        else:raise RuntimeError('c32_terminal_before_repair_reserve_not_reached')
        stage(ip,out,events,'result_bundle',f'tar --sort=name --mtime="UTC 1970-01-01" --owner=0 --group=0 --numeric-owner -C {WORK} -czf {WORK}/result.tar.gz run telemetry.csv runner.stdout.log runner.stderr.log; sha256sum {WORK}/result.tar.gz >{WORK}/result.tar.gz.sha256',180)
        archive=out/'result.tar.gz';scp_from(ip,KEY,f'{WORK}/result.tar.gz',archive);scp_from(ip,KEY,f'{WORK}/result.tar.gz.sha256',out/'result.tar.gz.sha256')
        if sha(archive)!=(out/'result.tar.gz.sha256').read_text().split()[0]:raise RuntimeError('result_hash_mismatch')
        with tarfile.open(archive) as t:t.extractall(out/'result',filter='data')
        terminal=json.loads((out/'result/run/TERMINAL.json').read_text());put(out/'C32_TERMINAL.json',terminal)
        owner.complete('sglang_h200_c32_complete');classification='sglang_h200_c32_complete';code=0
    except Exception as e:
      put(out/'failure.json',{'classification':'typed_retained_development_failure','type':type(e).__name__,'message':str(e)[:4000],'instance_id':iid,'watchdog':watchdog,'timestamp':now()});emit(events,'failure',error_type=type(e).__name__,message=str(e)[:1000])
    put(out/'SUMMARY.json',{'classification':classification,'controller_returncode':code,'instance_id':iid,'watchdog':watchdog,'completed_at_utc':now()})
    status=json.loads((P/'STATUS.json').read_text());status.update({'active_session':None,'reconciliation_pending':True,'terminal_artifact':str(out/'SUMMARY.json'),'provider_mutation':'forbidden_pending_reconciliation','next_action':'Reconcile typed c32 terminal and authenticated cleanup.'});put(P/'STATUS.json',status);return code
if __name__=='__main__':main()
