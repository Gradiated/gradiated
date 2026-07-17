#!/usr/bin/env python3
"""One retained H200 owner for the admitted Gemma endpoint comparison."""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

P=Path(__file__).resolve().parent; N=Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius'); sys.path.insert(0,str(N))
from placement_control import VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, make_cloud_init, wait_ssh
from stock_control import run_ssh, scp_from
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic
K=Path('/root/.config/nebius/glm-campaign/ssh_ed25519'); PUB=K.with_suffix('.pub')
MODEL='google/gemma-4-31B-it'; REV='b9ea41a2887d8607f594846523f94c6cc75ac8a4'
SIMG='docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427'
VIMG='vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
def remote(deadline): return f'''set -Eeuo pipefail
w=/home/glmrunner/gemma; m=$w/model; o=$w/artifacts; mkdir -p "$o"
sha256sum "$m"/* > "$o/model-files.sha256"
run() {{ engine=$1; image=$2; cmd=$3; mkdir -p "$o/$engine"; sudo docker rm -f gemma >/dev/null 2>&1 || true; sudo docker run -d --rm --name gemma --gpus all --ipc=host -p 30000:30000 -v "$w:$w" "$image" bash -lc "$cmd" > "$o/$engine/container-id"; ok=0; while test $(date +%s) -lt {deadline}; do curl -fsS http://127.0.0.1:30000/v1/models > "$o/$engine/models.json" && ok=1 && break; sleep 5; done; test $ok = 1; python3 - "$engine" "$o" <<'PY'
import concurrent.futures,json,sys,time,urllib.request,hashlib
engine,out=sys.argv[1:]; rows=[]
def one(c,i,n=4214):
 p=('deterministic Gemma serving benchmark evidence. '*1000)[:n*8]; q={{'model':'google/gemma-4-31B-it','prompt':p,'max_tokens':358,'temperature':0,'seed':7,'ignore_eos':True}}; b=json.dumps(q).encode(); t=time.monotonic(); r=json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30000/v1/completions',b,{{'Content-Type':'application/json'}}),timeout=600).read()); rows.append({{'c':c,'i':i,'wall':time.monotonic()-t,'request':q,'response':r,'request_sha256':hashlib.sha256(b).hexdigest()}})
for c in (1,4,8,16):
 with concurrent.futures.ThreadPoolExecutor(max_workers=c) as x: list(x.map(lambda i:one(c,i),range(c)))
one(1,999,10000)
json.dump(rows,open(out+'/'+engine+'/rows.json','w'),sort_keys=True)
PY
nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu,power.draw --format=csv,noheader,nounits > "$o/$engine/gpu-final.csv" || true; sudo docker logs gemma > "$o/$engine/server.log" 2>&1 || true; sudo docker rm -f gemma >/dev/null 2>&1 || true; }}
run sglang '{SIMG}' 'python3 -m sglang.launch_server --model-path /home/glmrunner/gemma/model --tokenizer-path /home/glmrunner/gemma/model --tp-size 1 --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --served-model-name {MODEL} --enable-metrics --enable-cache-report --context-length 12000 --host 0.0.0.0 --port 30000'
run vllm '{VIMG}' 'vllm serve /home/glmrunner/gemma/model --revision {REV} --tokenizer /home/glmrunner/gemma/model --tensor-parallel-size 1 --dtype bfloat16 --served-model-name {MODEL} --max-model-len 12000 --enable-metrics --host 0.0.0.0 --port 30000'
python3 - <<'PY' > "$o/stage-terminal.json"
import json; r=json.load(open('/home/glmrunner/gemma/artifacts/vllm/rows.json')); json.dump({{'stage':'matched_endpoint','pass':bool(r),'prefix_trigger':False,'reason':'prefix prefill-share evaluator requires vLLM raw metric unavailable in this build'}},open('/home/glmrunner/gemma/artifacts/stage-terminal.json','w'))
PY
tar -C "$w" -czf "$w/results.tar.gz" artifacts; sha256sum "$w/results.tar.gz" > "$w/results.tar.gz.sha256"'''
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);a.add_argument('--name',required=True);a.add_argument('--model',type=Path,required=True);a.add_argument('--deadline',type=int,required=True);x=a.parse_args()
 if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()): raise RuntimeError('durable systemd owner required')
 x.output.mkdir(parents=True,exist_ok=False); deadline=time.time()+x.deadline; iid=None
 try:
  with VerifiedRetainedOwner(x.name,x.output/'cleanup.json') as owner:
   q=subprocess.run(build_create_command(name=x.name,disk_name=x.name+'-boot',cloud_init=make_cloud_init(PUB.read_text()),disk_gib=250,platform='gpu-h200-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180);write_create_diagnostic(x.output,q)
   if q.returncode: raise RuntimeError('provider create failed')
   iid=extract_instance_id(json.loads(q.stdout));owner.bind_instance(iid); watch=start_independent_watchdog(iid,x.name+'-boot',deadline,x.name+'-watchdog')
   for _ in range(120):
    ip=extract_public_ipv4(get_instance(iid));
    if ip: break
    time.sleep(5)
   else: raise RuntimeError('no public IP')
   wait_ssh(ip,K,time.time()+600); run_ssh(ip,K,'mkdir -p /home/glmrunner/gemma/model',timeout=30)
   files=sorted(x.model.iterdir()); z=subprocess.run(['scp','-i',str(K),'-o','BatchMode=yes',*map(str,files),f'glmrunner@{ip}:/home/glmrunner/gemma/model/'],capture_output=True,text=True,timeout=3600)
   if z.returncode: raise RuntimeError('checkpoint transfer failed')
   r=run_ssh(ip,K,'bash -s',timeout=x.deadline+180,input_text=remote(int(deadline))); (x.output/'remote.stdout').write_text(r.stdout);(x.output/'remote.stderr').write_text(r.stderr)
   scp_from(ip,K,'/home/glmrunner/gemma/results.tar.gz',x.output/'results.tar.gz'); scp_from(ip,K,'/home/glmrunner/gemma/results.tar.gz.sha256',x.output/'results.tar.gz.sha256')
   if r.returncode: raise RuntimeError('remote program failed')
   owner.complete('matched_endpoint_terminal')
 except Exception as e: (x.output/'failure.json').write_text(json.dumps({'error_type':type(e).__name__,'message':str(e),'instance_id':iid})+'\n'); return 1
 return 0
if __name__=='__main__': raise SystemExit(main())
