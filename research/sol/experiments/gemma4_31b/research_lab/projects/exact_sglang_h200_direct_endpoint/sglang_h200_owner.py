#!/usr/bin/env python3
"""Durable one-allocation owner for the admitted exact Gemma H200 endpoint."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NEBIUS = Path('/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius')
sys.path.insert(0, str(NEBIUS))
from placement_control import VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, make_cloud_init, wait_ssh
from stock_control import run_ssh, scp_from
from vllm_smoke_control import start_independent_watchdog, write_create_diagnostic

KEY = Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
PUBLIC_KEY = KEY.with_suffix('.pub')
NEBIUS_CLI = '/root/.nebius/bin/nebius'
MODEL = 'google/gemma-4-31B-it'
REV = 'b9ea41a2887d8607f594846523f94c6cc75ac8a4'
SIMG = 'docker.io/lmsysorg/sglang:dev-gemma4@sha256:380cc6c6654b479c464177aa684aca520d6bd6e9833b23eba1df2f8396f63427'
VIMG = 'vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79'
CHECKPOINT = ROOT.parent / 'sglang_h200_matched_endpoint_falsifier/artifacts/checkpoint-owner-20260717T072831Z/checkpoint'
TRACE = ROOT.parent / 'gemma_exact_cache_trace_contract/TRACE_PACKET.json'
ASSERTION = ROOT / 'artifacts/DIRECTOR_IDENTITY_ASSERTION.json'
WORK = '/home/glmrunner/gemma-h200'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def emit(path, kind, **fields):
    with path.open('a') as f: f.write(json.dumps({'epoch':time.time(),'event':kind,**fields},sort_keys=True)+'\n')

def identities():
    a=json.loads(ASSERTION.read_text()); t=json.loads(TRACE.read_text())
    terminal=CHECKPOINT.parent/'CHECKPOINT_TERMINAL.json'
    c={'assertion_pass':a['pass'], 'trace_hash':sha(TRACE)==a['authoritative_inputs']['trace_packet']['sha256'],
       'checkpoint_terminal_hash':sha(terminal)==a['authoritative_inputs']['checkpoint_terminal']['sha256'],
       'checkpoint_pass':json.loads(terminal.read_text())['pass'], 'checkpoint_exists':CHECKPOINT.is_dir(),
       'checkpoint_index':sha(CHECKPOINT/'model.safetensors.index.json')==a['bound']['checkpoint_index_sha256'],
       'model':t['identity']['model']==MODEL, 'revision':t['identity']['revision']==REV,
       'groups':[g['concurrency'] for g in t['primary_groups']]==[1,4,8,16], 'separate_10k':t['separate_10k_stream']['concurrency']==1}
    if not all(c.values()): raise RuntimeError('immutable_identity_gate_failed:'+json.dumps(c,sort_keys=True))
    return c

RUNNER = r'''import argparse,concurrent.futures,json,pathlib,threading,time,urllib.request
def get(url,p):
 try:pathlib.Path(p).write_bytes(urllib.request.urlopen(url,timeout=30).read())
 except Exception as e:pathlib.Path(str(p)+'.error').write_text(repr(e))
def one(base,b,p,barrier=None):
 if barrier:barrier.wait()
 s=time.monotonic()
 try:r=json.loads(urllib.request.urlopen(urllib.request.Request(base+'/v1/completions',json.dumps(b).encode(),{'Content-Type':'application/json'}),timeout=1800).read()); e=None
 except Exception as x:r={};e=repr(x)
 row={'request':b,'response':r,'error':e,'wall_seconds':time.monotonic()-s};pathlib.Path(p).write_text(json.dumps(row,sort_keys=True));return row
def ok(r,p,o):
 u=r.get('response',{}).get('usage',{});return not r['error'] and u.get('prompt_tokens')==p and u.get('completion_tokens')==o
def arm(a,g):
 d=a.output/g['name'];d.mkdir();get(a.base+'/metrics',d/'before.prom');w=g['scored'][0]['request_body'].copy();w['max_tokens']=w['min_tokens']=1;warm=one(a.base,w,d/'warmup.json');get(a.base+'/metrics',d/'after_warmup.prom');b=threading.Barrier(g['concurrency']);s=time.monotonic()
 with concurrent.futures.ThreadPoolExecutor(max_workers=g['concurrency']) as x: rows=list(x.map(lambda q:one(a.base,q[1]['request_body'],d/f'scored-{q[0]}.json',b),enumerate(g['scored'])))
 wall=time.monotonic()-s;get(a.base+'/metrics',d/'after_scored.prom');z={'name':g['name'],'concurrency':g['concurrency'],'pass':ok(warm,g['metrics_assertions']['warmup_query_delta_tokens'],1) and all(ok(x,4214 if g['name']!='separate_10k' else 10000,358) for x in rows),'completed_rps':len(rows)/wall,'wall_seconds':wall,'raw_response_count':len(rows)}; (d/'TERMINAL.json').write_text(json.dumps(z,sort_keys=True));return z
p=argparse.ArgumentParser();p.add_argument('--trace');p.add_argument('--base');p.add_argument('--output',type=pathlib.Path);p.add_argument('--market-rps',type=float);a=p.parse_args();t=json.load(open(a.trace));a.output.mkdir();r=[arm(a,t['primary_groups'][0])]
if r[0]['pass']:
 for g in t['primary_groups'][1:]:r.append(arm(a,g))
 q=t['separate_10k_stream'];r.append(arm(a,{'name':'separate_10k','concurrency':1,'scored':[{'request_body':q['request_body']}],'metrics_assertions':{'warmup_query_delta_tokens':10000}}))
z={'semantic_pass':r[0]['pass'],'all_arms_pass':all(x['pass'] for x in r),'arms':r};z['market_trigger']=z['all_arms_pass'] and any(x['concurrency'] in (8,16) and x['completed_rps']>=a.market_rps for x in r);(a.output/'TERMINAL.json').write_text(json.dumps(z,sort_keys=True));raise SystemExit(0 if z['semantic_pass'] else 72)
'''

def remote(deadline):
    return f'''set -Eeuo pipefail
umask 077
w={WORK};m="$w/model";o="$w/artifacts";mkdir -p "$o/sglang" "$o/vllm";test -w "$w";test -w "$m"
sha256sum "$m/model.safetensors.index.json" > "$o/checkpoint-index.sha256"
engine() {{ n="$1";i="$2";c="$3";d="$o/$n"; sudo docker rm -f gemma-server >/dev/null 2>&1 || true; sudo docker image inspect "$i" > "$d/image-inspect.json"; sudo docker run -d --rm --name gemma-server --gpus all --ipc=host -p 30000:30000 -v "$w:$w" --entrypoint bash "$i" -lc "$c" > "$d/container-id"; for x in $(seq 1 120); do curl -fsS http://127.0.0.1:30000/v1/models > "$d/models.json" && break; sleep 5; done; test -s "$d/models.json"; python3 "$w/runner.py" --trace "$w/trace.json" --base http://127.0.0.1:30000 --output "$d" --market-rps 2.094181; r=$?; curl -fsS http://127.0.0.1:30000/metrics > "$d/metrics-final.prom" || true; nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu,power.draw --format=csv,noheader,nounits > "$d/gpu-final.csv" || true; sudo docker logs gemma-server > "$d/server.log" 2>&1 || true; sudo docker rm -f gemma-server >/dev/null 2>&1 || true; return $r; }}
engine sglang '{SIMG}' 'python3 -m sglang.launch_server --model-path '"$m"' --tokenizer-path '"$m"' --tp-size 1 --dtype bfloat16 --kv-cache-dtype fp8_e5m2 --served-model-name {MODEL} --enable-metrics --enable-cache-report --log-requests --context-length 12000 --host 0.0.0.0 --port 30000'
if python3 -c "import json;raise SystemExit(not json.load(open('$o/sglang/TERMINAL.json'))['market_trigger'])"; then engine vllm '{VIMG}' 'vllm serve '"$m"' --revision {REV} --tokenizer '"$m"' --tensor-parallel-size 1 --dtype bfloat16 --served-model-name {MODEL} --max-model-len 12000 --enable-metrics --host 0.0.0.0 --port 30000'; else printf '%s\n' '{{"classification":"vllm_not_triggered"}}' > "$o/vllm/TERMINAL.json"; fi
python3 -c "import json;from pathlib import Path;p=Path('$o');json.dump({{'classification':'exact_sglang_h200_endpoint_terminal','sglang':json.load(open(p/'sglang/TERMINAL.json')),'vllm':json.load(open(p/'vllm/TERMINAL.json'))}},open(p/'SUMMARY.json','w'),sort_keys=True)"
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w" -czf "$w/results.tar.gz" artifacts
sha256sum "$w/results.tar.gz" > "$w/results.tar.gz.sha256"'''

def audit(output, name):
    c=identities(); s=Path(__file__).read_text()
    c.update({'systemd_owner':'INVOCATION_ID' in s and 'SYSTEMD_EXEC_PID' in s,'shared_controller':'VerifiedRetainedOwner' in s,
      'workspace_before_transfer':"run_ssh(ip,KEY,'mkdir -p '+WORK+'/model" in s and "test -w '+WORK+'/model" in s,'entrypoint_override':'--entrypoint bash' in s,'exact_images':SIMG in s and VIMG in s,
      'fp8_kv':'--kv-cache-dtype fp8_e5m2' in s,'token_arrays':'trace.json' in s,'simultaneous':'Barrier' in RUNNER,
      'semantic_first':'semantic_pass' in RUNNER,'atomic_terminals':'TERMINAL.json' in RUNNER,'telemetry':'metrics' in RUNNER and 'nvidia-smi' in s,
      'conditional_vllm':'market_trigger' in RUNNER,'watchdog':'start_independent_watchdog' in s,'cleanup':'VerifiedRetainedOwner' in s,
      'name':name==name.lower() and all(x.islower() or x.isdigit() or x=='-' for x in name)})
    output.write_text(json.dumps({'classification':'final_program_audit','pass':all(c.values()),'checks':c,'deadline_seconds':5400},indent=2,sort_keys=True)+'\n');return 0 if all(c.values()) else 2

def run(parent,name):
    if not os.getenv('INVOCATION_ID') or os.getenv('SYSTEMD_EXEC_PID')!=str(os.getpid()):raise RuntimeError('durable systemd owner required')
    checks=identities();out=parent/(name+'-run');out.mkdir();events=out/'events.jsonl';deadline=time.time()+5400;emit(events,'owner_started',deadline_epoch=deadline,checks=checks);iid=None
    try:
      with VerifiedRetainedOwner(name,out/'cleanup.json') as owner:
        inv=subprocess.run([NEBIUS_CLI,'compute','instance','list','--format','json'],capture_output=True,text=True,timeout=60);(out/'inventory-before-create.json').write_text(inv.stdout)
        if inv.returncode or json.loads(inv.stdout):raise RuntimeError('authenticated_inventory_not_empty')
        q=subprocess.run(build_create_command(name=name,disk_name=name+'-boot',cloud_init=make_cloud_init(PUBLIC_KEY.read_text()),disk_gib=250,platform='gpu-h200-sxm',preset='1gpu-16vcpu-200gb',preemptible=True),capture_output=True,text=True,timeout=180);write_create_diagnostic(out,q)
        if q.returncode:raise RuntimeError('provider_create_failed')
        iid=extract_instance_id(json.loads(q.stdout));owner.bind_instance(iid);emit(events,'instance_created',instance_id=iid);watch=start_independent_watchdog(iid,name+'-boot',deadline,name+'-watchdog');emit(events,'watchdog_started',watchdog=watch)
        ip=None
        for _ in range(120):
          x=get_instance(iid);ip=extract_public_ipv4(x) if x else None
          if ip:break
          time.sleep(5)
        if not ip:raise RuntimeError('public_ip_timeout')
        wait_ssh(ip,KEY,time.time()+600);run_ssh(ip,KEY,'mkdir -p '+WORK+'/model '+WORK+'/artifacts && test -w '+WORK+'/model',timeout=60);emit(events,'workspace_ready',ip=ip)
        runner=out/'runner.py';runner.write_text(RUNNER)
        for src,dst in ((TRACE,'trace.json'),(runner,'runner.py')):
          z=subprocess.run(['scp','-i',str(KEY),'-o','BatchMode=yes',str(src),f'glmrunner@{ip}:{WORK}/{dst}'],capture_output=True,text=True,timeout=120)
          if z.returncode:raise RuntimeError('program_transfer_failed')
        z=subprocess.run(['scp','-i',str(KEY),'-o','BatchMode=yes',*map(str,sorted(CHECKPOINT.iterdir())),f'glmrunner@{ip}:{WORK}/model/'],capture_output=True,text=True,timeout=3600);(out/'checkpoint-transfer.stderr').write_text(z.stderr)
        if z.returncode:raise RuntimeError('checkpoint_transfer_failed')
        r=run_ssh(ip,KEY,'bash -s',timeout=max(60,int(deadline-time.time())),input_text=remote(int(deadline)));(out/'remote.stdout').write_text(r.stdout);(out/'remote.stderr').write_text(r.stderr)
        scp_from(ip,KEY,WORK+'/results.tar.gz',out/'results.tar.gz');scp_from(ip,KEY,WORK+'/results.tar.gz.sha256',out/'results.tar.gz.sha256')
        if r.returncode:raise RuntimeError('remote_scientific_program_failed')
        owner.complete('exact_sglang_h200_terminal')
    except Exception as e:
      (out/'failure.json').write_text(json.dumps({'classification':'typed_owner_failure','error_type':type(e).__name__,'message':str(e),'instance_id':iid},sort_keys=True)+'\n');emit(events,'owner_failure',error_type=type(e).__name__,message=str(e));return 1
    return 0

p=argparse.ArgumentParser();sub=p.add_subparsers(dest='mode',required=True);a=sub.add_parser('audit');a.add_argument('--output',type=Path,required=True);a.add_argument('--name',required=True);r=sub.add_parser('run');r.add_argument('--artifacts-parent',type=Path,required=True);r.add_argument('--name',required=True);x=p.parse_args();raise SystemExit(audit(x.output,x.name) if x.mode=='audit' else run(x.artifacts_parent,x.name))
