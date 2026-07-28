#!/usr/bin/env python3
"""Retained-claim, sequential stock/candidate endpoint-pair executor."""
from __future__ import annotations
import argparse, hashlib, json, shlex, subprocess, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
KEY=Path('/root/.config/nebius/glm-campaign/ssh_ed25519')
MODEL='google/gemma-4-31B-it'
REVISION='b9ea41a2887d8607f594846523f94c6cc75ac8a4'
CONVERTED=[11,23,35,47,59]

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def atomic(p:Path,v:dict):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+'.part'); q.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n');q.replace(p)
def main():
 a=argparse.ArgumentParser();a.add_argument('--authority',type=Path,required=True);a.add_argument('--phase',required=True);a.add_argument('--artifact-root',type=Path,required=True);ns=a.parse_args()
 if ns.phase!='run-pair-and-retrieve': raise RuntimeError('retained_adoption_only_all_prior_phases_consumed')
 b=json.loads(ns.authority.read_text()); ri=b['resident_inputs']; r=b['bench']['resource']; art=ns.artifact_root.resolve(); old=ROOT/ri['staging_artifact']; ci=ROOT/ri['candidate_install_artifact']; work=Path(ri['workload']); cand=ROOT/ri['candidate_source']; pair=ROOT/ri['pair_source']
 expected={old:ri['staging_artifact_sha256'],ci:ri['candidate_install_artifact_sha256'],work:ri['workload_sha256'],cand:ri['candidate_source_sha256'],pair:ri['pair_source_sha256']}
 if any(not p.is_file() or sha(p)!=d for p,d in expected.items()): raise RuntimeError('retained_input_hash_binding_failed')
 ssh=['ssh','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={r['known_hosts_namespace']}",f"{r['ssh_user']}@{r['public_ipv4']}"]
 def run(x,timeout=900): return subprocess.run(x,text=True,capture_output=True,check=False,timeout=timeout)
 remote='/home/glmrunner/hybrid-55l5g/adopt-0255'; target=ri['checkpoint_path']; image=ri['image']
 prep=run([*ssh,f"mkdir -p {remote} && rm -rf {remote}/pair && mkdir {remote}/pair"],60)
 if prep.returncode: raise RuntimeError('remote_pair_root_prepare_failed')
 for p in (work,cand,pair):
  x=run(['scp','-p','-i',str(KEY),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',f"UserKnownHostsFile={r['known_hosts_namespace']}",str(p),f"{r['ssh_user']}@{r['public_ipv4']}:{remote}/pair/{p.name}"],300)
  if x.returncode: raise RuntimeError('pair_packet_transfer_failed')
 # The runner uses the actual fixed pair consumer.  A single model is retained:
 # stock rows are persisted before the mounted candidate server replaces it.
 runner='''import json,sys;from pathlib import Path;sys.path.insert(0,"/work");import run_h200_55l5g_endpoint_pair as p
w=json.loads(Path("/work/qualified_c32_workload.json").read_text());o=Path("/work/out");o.mkdir(exist_ok=True)
arm=p.run_arm(sys.argv[1],sys.argv[2],w,240.0);(o/(sys.argv[1]+".json")).write_text(json.dumps(arm));print(json.dumps(arm))'''
 encoded=shlex.quote(runner)
 def launch(name,mount=None,port=30000):
  candidate_mount='' if mount is None else f' -v {mount}:/usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py:ro'
  cmd=f"sudo -n docker rm -f {name} >/dev/null 2>&1 || true; sudo -n docker run -d --name {name} --gpus all -p {port}:30000 -v {target}:/models/target:ro -v {remote}/pair:/work{candidate_mount} -w /work {image} python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision {REVISION} --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --skip-server-warmup"
  z=run([*ssh,cmd],120); 
  if z.returncode: raise RuntimeError('server_launch_failed:'+name)
  deadline=time.time()+420
  while time.time()<deadline:
   ok=run([*ssh,f"curl -fsS http://127.0.0.1:{port}/health >/dev/null"],20)
   if ok.returncode==0:return
   state=run([*ssh,f"sudo -n docker inspect --format '{{{{json .State}}}}' {name}"],20)
   try: statej=json.loads(state.stdout)
   except json.JSONDecodeError: statej=None
   if state.returncode==0 and isinstance(statej,dict) and not statej.get('Running',False):
    logs=run([*ssh,f"sudo -n docker logs {name} 2>&1 | tail -n 400"],60)
    atomic(art/(name+'.startup-failure.json'),{'classification':'pre_science_server_exit','science_consumed':False,'container':name,'observed_at_epoch':time.time(),'inspect_returncode':state.returncode,'state':statej,'log_tail':logs.stdout[-12000:]})
    raise RuntimeError('server_exited_before_ready:'+name)
   time.sleep(4)
  raise RuntimeError('server_readiness_timeout:'+name)
 launch('hybrid-55l5g-stock')
 stock=run([*ssh,f"cd {remote}/pair && sudo -n docker exec hybrid-55l5g-stock python3 -c {encoded} stock http://127.0.0.1:30000"],900)
 run([*ssh,'sudo -n docker rm -f hybrid-55l5g-stock >/dev/null 2>&1 || true'],60)
 if stock.returncode: raise RuntimeError('stock_pair_consumer_failed')
 launch('hybrid-55l5g-candidate',f'{remote}/pair/{cand.name}')
 # Candidate proof is emitted only after the mounted bytes are observed in the live container.
 proof=run([*ssh,f"sudo -n docker exec hybrid-55l5g-candidate sha256sum /usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py"],60)
 if ri['candidate_source_sha256'] not in proof.stdout: raise RuntimeError('candidate_mount_identity_failed')
 candidate=run([*ssh,f"cd {remote}/pair && sudo -n docker exec hybrid-55l5g-candidate python3 -c {encoded} permanent_55local_5global http://127.0.0.1:30000"],900)
 logs=run([*ssh,'sudo -n docker logs hybrid-55l5g-candidate 2>&1 | tail -n 400'],60)
 run([*ssh,'sudo -n docker rm -f hybrid-55l5g-candidate >/dev/null 2>&1 || true'],60)
 if candidate.returncode: raise RuntimeError('candidate_pair_consumer_failed')
 stockj=json.loads(stock.stdout.strip().splitlines()[-1]);candj=json.loads(candidate.stdout.strip().splitlines()[-1]); valid=stockj['complete_requests']==32 and candj['complete_requests']==32 and not stockj['failures'] and not candj['failures']
 term={'schema_version':1,'classification':'scientific_terminal' if valid else 'invalid_endpoint_pair','science_consumed':valid,'candidate_cuda_invocation_started':valid,'converted_layers':CONVERTED,'workload':{'concurrency':32,'prompt_tokens':4214,'output_tokens':358,'sha256':ri['workload_sha256']},'candidate_path_proof':{'candidate_endpoint_path_executed':valid,'converted_layers':CONVERTED,'candidate_source_sha256':ri['candidate_source_sha256'],'live_container_mount_sha256':ri['candidate_source_sha256']},'control':stockj,'candidate':candj,'candidate_server_log_tail':logs.stdout[-12000:]}
 term['service_time_delta_seconds_per_request']=candj['service_seconds_per_request']-stockj['service_seconds_per_request'] if valid else None
 atomic(art/'retrieved'/'HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json',term); return 0 if valid else 72
if __name__=='__main__': main()
