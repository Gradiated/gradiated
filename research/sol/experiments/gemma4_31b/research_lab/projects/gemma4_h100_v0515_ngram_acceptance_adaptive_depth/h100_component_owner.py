#!/usr/bin/env python3
"""Bounded controller for the single claimed component bench."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, subprocess, sys, tarfile, tempfile, threading, time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = Path('/root/workspace/research/factory/src')
BENCH = 'h100-v0515-adaptive-depth-component-e00gbzwff2ty4wznzj'
PN = 'gemma4_h100_v0515_ngram_acceptance_adaptive_depth'
IP = '89.169.124.46'; KEY = '/root/.config/nebius/glm-campaign/ssh_ed25519'
REMOTE = '/home/glmrunner/gemma4-h100-adaptive-depth-component'
IMAGE = 'docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd'
LOCAL_IMAGE = 'adaptive-depth-sglang:bound-v0515'

def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def pool(action):
    return subprocess.run(['env', f'PYTHONPATH={FACTORY}', 'python3','-m','grad_research.gpu_pool','--lab',str(LAB),action,'--project',PN], text=True, capture_output=True, timeout=60)
def ssh(cmd, timeout=1800):
    base=['ssh','-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts','-o','ConnectTimeout=15',f'glmrunner@{IP}']
    return subprocess.run([*base,'bash','-s'],input=cmd,text=True,capture_output=True,timeout=timeout)
def atomic(path, value):
    tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n'); os.replace(tmp,path)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def heartbeat(stop, events):
    while not stop.wait(45):
        r=pool('heartbeat'); events.append({'at':now(),'returncode':r.returncode})
def main():
    ap=__import__('argparse').ArgumentParser(); ap.add_argument('--artifact-root',required=True); ap.add_argument('--deadline-epoch',type=float,required=True); a=ap.parse_args()
    out=Path(a.artifact_root).resolve(); out.mkdir(parents=True,exist_ok=True); events=[]; stop=threading.Event(); threading.Thread(target=heartbeat,args=(stop,events),daemon=True).start()
    terminal={'schema_version':1,'project':PN,'bench':BENCH,'started_at_utc':now(),'candidate_sample_consumed':False,'checkpoint_loaded':False}
    try:
        if time.time()>a.deadline_epoch: raise RuntimeError('absolute_deadline_before_start')
        for p in [PROJECT/'h100_component_runner.py', PROJECT/'adaptive_depth_runtime.py']:
            if not p.exists(): raise RuntimeError('missing_runner:'+str(p))
        r=ssh(f"set -euo pipefail; mkdir -p {REMOTE}/payload {REMOTE}/out; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; sudo -n docker --version; df -h {REMOTE}",120)
        (out/'REMOTE_PREFLIGHT.stdout').write_text(r.stdout); (out/'REMOTE_PREFLIGHT.stderr').write_text(r.stderr)
        if r.returncode: raise RuntimeError('remote_preflight_failed')
        # Immutable project-local payload; the named bound sources are staged too.
        with tempfile.NamedTemporaryFile(suffix='.tar',delete=False) as t:
            tar_path=Path(t.name)
        with tarfile.open(tar_path,'w') as tf:
            for p in [PROJECT/'h100_component_runner.py',PROJECT/'adaptive_depth_runtime.py',PROJECT/'inputs/candidate-v0.5.15']:
                tf.add(p,arcname=p.relative_to(PROJECT))
        pipe=f"tar -C {REMOTE}/payload -xf -"
        base=['ssh','-i',KEY,'-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts',f'glmrunner@{IP}',pipe]
        with tar_path.open('rb') as fh: r=subprocess.run(base,stdin=fh,text=False,capture_output=True,timeout=600)
        tar_path.unlink(missing_ok=True); (out/'STAGE.stderr').write_bytes(r.stderr)
        if r.returncode: raise RuntimeError('stage_failed')
        # The digest is bound and was verified by docker image inspect.  Use a
        # local tag after the first pull: this avoids Docker 29.5's broken
        # remote digest resolver (it hangs before container creation).
        r=ssh(f"set -euo pipefail; sudo -n docker image inspect {LOCAL_IMAGE} >/dev/null; sudo -n docker rm -f adaptive-depth-component >/dev/null 2>&1 || true; sudo -n docker run --name adaptive-depth-component --gpus all --ipc=host -v {REMOTE}/payload:/work/payload:ro -v {REMOTE}/out:/work/out {LOCAL_IMAGE} python3 /work/payload/h100_component_runner.py --out /work/out --repetitions 200",3600)
        (out/'GPU_RUN.stdout').write_text(r.stdout); (out/'GPU_RUN.stderr').write_text(r.stderr)
        if r.returncode: raise RuntimeError('gpu_component_failed')
        rr=ssh(f"set -e; test -s {REMOTE}/out/RESULT.json; cp {REMOTE}/out/RESULT.json {REMOTE}/out/RESULT.final.json; sha256sum {REMOTE}/out/RESULT.json {REMOTE}/out/short_trace.json",120)
        (out/'REMOTE_RESULT_HASH.stdout').write_text(rr.stdout); (out/'REMOTE_RESULT_HASH.stderr').write_text(rr.stderr)
        if rr.returncode: raise RuntimeError('result_retrieval_failed')
        # Pull compact JSON and trace; scientific result is only marked consumed now.
        for name in ['RESULT.json','short_trace.json']:
            r=ssh(f"cat {REMOTE}/out/{name}",120)
            if r.returncode: raise RuntimeError('artifact_retrieval_failed:'+name)
            (out/name).write_text(r.stdout)
        result=json.loads((out/'RESULT.json').read_text()); terminal.update({'result':'valid_component_measurement','finished_at_utc':now(),'candidate_sample_consumed':True,'summary':{'repetitions_per_arm':result['repetitions_per_arm'],'gpu':result['gpu'],'correctness':result['correctness'],'result_sha256':sha(out/'RESULT.json')}})
        atomic(out/'ADAPTIVE_DEPTH_H100_COMPONENT_RESULT.json',result); atomic(out/'ADAPTIVE_DEPTH_H100_COMPONENT_TERMINAL.json',terminal)
        stop.set(); pool('release'); return 0
    except Exception as e:
        terminal.update({'result':'typed_controller_failure','finished_at_utc':now(),'error':str(e),'heartbeat_events':events})
        atomic(out/'ADAPTIVE_DEPTH_H100_COMPONENT_TERMINAL.json',terminal)
        # Keep a claim on recoverable failures for director repair; only release
        # after a decision-bearing result or a typed external boundary.
        atomic(out/'REPAIR_READY.json',{'schema_version':1,'project':PN,'bench':BENCH,'diagnostic':str(e),'repair_deadline_utc':'2026-07-25T15:40:00Z'})
        stop.set(); return 2
if __name__=='__main__': raise SystemExit(main())
