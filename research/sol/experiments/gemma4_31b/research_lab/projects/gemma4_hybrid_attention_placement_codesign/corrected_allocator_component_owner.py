#!/usr/bin/env python3
"""One bounded corrected-allocator TARGET_VERIFY component owner."""
from __future__ import annotations
import hashlib, json, os, pathlib, subprocess, sys, threading, time
R=pathlib.Path(__file__).resolve().parent; L=R.parents[1]; P="gemma4_hybrid_attention_placement_codesign"; B="h200-dflash-adapter-e00vyqp7gxsr34wrtz"
K="/root/.config/nebius/glm-campaign/ssh_ed25519"; H="/root/.config/nebius/glm-campaign/known_hosts"; HOST="89.169.109.132"
A=R/"artifacts/corrected-allocator-h200-component-20260726t0614z"; Q="/home/glmrunner/hybrid-corrected-allocator-20260726t0614z"; D="2026-07-26T06:52:00Z"
def w(p,x):
 p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+".part"); t.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n"); os.replace(t,p)
def run(a): return subprocess.run(a,text=True,capture_output=True)
def ssh(s): return run(["ssh","-i",K,"-o",f"UserKnownHostsFile={H}","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=20",f"glmrunner@{HOST}",s])
def pool(a): return run([sys.executable,"-m","grad_research.gpu_pool","--lab",str(L),a,"--project",P,"--bench",B])
def save(n,x): (A/(n+".stdout.log")).write_text(x.stdout); (A/(n+".stderr.log")).write_text(x.stderr)
def main():
 A.mkdir(parents=True,exist_ok=True); stop=threading.Event(); threading.Thread(target=lambda: [pool("heartbeat") for _ in iter(lambda:not stop.wait(45),False)],daemon=True).start()
 def finish(kind,reason,science,cuda):
  logs=ssh("sudo -n docker logs phase-selective-readmission 2>&1 || true"); save("server_raw",logs); ssh("sudo -n docker rm -f phase-selective-readmission >/dev/null 2>&1 || true")
  terminal={"schema_version":1,"classification":kind,"failure_kind":reason,"scientific_component_consumed":False,"science_started":science,"candidate_cuda_invocation_started":cuda,"artifact_root":str(A),"binding":"DIRECTOR_CORRECTED_ALLOCATOR_H200_COMPONENT_20260726T0604Z.json","source_sha256":hashlib.sha256((R/'forward_batch_dual_cache_driver.py').read_bytes()).hexdigest(),"raw_evidence":{"consumer":str(A/'target_verify_consumer.stdout.log'),"retrieval":str(A/'retrieved.stdout.log'),"server":str(A/'server_raw.stdout.log')}}
  w(R/"CORRECTED_ALLOCATOR_H200_COMPONENT_TERMINAL.json",terminal); w(R/"CORRECTED_ALLOCATOR_OWNER_STATE.json",{"phase":"terminal","terminal":terminal,"deadline_utc":D}); pool("release"); stop.set(); return 0 if kind=="component_execution_record" else 2
 files=[R/n for n in ("sitecustomize.py","forward_batch_dual_cache_driver.py","full_model_memory_adapter.py","phase_selective_full_model_remote.py","forward_batch_activation_component.py")]
 manifest={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in files}; w(A/"source_manifest.json",manifest); w(R/"CORRECTED_ALLOCATOR_OWNER_STATE.json",{"phase":"staging","artifact_root":str(A),"deadline_utc":D,"science_started":False,"source_manifest":manifest})
 prep=ssh(f"set -eu; rm -rf {Q}.tmp; mkdir -p {Q}.tmp/source {Q}.tmp/artifact; mv {Q}.tmp {Q}; test -d /home/glmrunner/phase-selective-full-model-v2/checkpoint") ; save("remote_prepare",prep)
 if prep.returncode: return finish("infrastructure_terminal","remote_prepare_failed",False,False)
 cp=run(["scp","-i",K,"-o",f"UserKnownHostsFile={H}","-o","StrictHostKeyChecking=yes",*map(str,files),f"glmrunner@{HOST}:{Q}/source/"]); save("source_copy",cp)
 if cp.returncode: return finish("infrastructure_terminal","source_copy_failed",False,False)
 launch=ssh(f"set -eu; sudo -n docker rm -f phase-selective-readmission >/dev/null 2>&1 || true; sudo -n docker run -d --name phase-selective-readmission --gpus all -p 30000:30000 -v {Q}:/work -v /home/glmrunner/phase-selective-full-model-v2/checkpoint:/models/target:ro -w /work -e PYTHONPATH=/work/source gemma4-dflash-sglang:588d1f7bc942 python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 --speculative-algorithm NGRAM --speculative-num-steps 12 --speculative-num-draft-tokens 12 --skip-server-warmup"); save("server_launch",launch)
 if launch.returncode: return finish("infrastructure_terminal","server_launch_failed",False,False)
 ready=False
 for _ in range(100):
  p=ssh(f"set +e; cat {Q}/artifact/adapter_attach.json 2>/dev/null; cat {Q}/artifact/forward_batch_dual_cache.json 2>/dev/null; sudo -n docker inspect -f '{{{{.State.Running}}}}' phase-selective-readmission; sudo -n docker logs --tail 700 phase-selective-readmission 2>&1 | grep -F 'The server is fired up and ready to roll!' | tail -1; exit 0"); save("readiness",p)
  if '"attached": true' in p.stdout and 'true' in p.stdout and 'ready to roll' in p.stdout: ready=True; break
  time.sleep(3)
 if not ready: return finish("infrastructure_terminal","server_readiness_missing",False,False)
 w(R/"CORRECTED_ALLOCATOR_OWNER_STATE.json",{"phase":"target_verify_component","artifact_root":str(A),"deadline_utc":D,"science_started":True,"candidate_cuda_invocation_started":False})
 work=ssh(f"set +e; sudo -n docker exec phase-selective-readmission python3 /work/source/forward_batch_activation_component.py; rc=$?; sudo -n docker logs phase-selective-readmission >{Q}/artifact/server_raw.log 2>&1; cat {Q}/artifact/forward_batch_dual_cache.json 2>/dev/null; cat {Q}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {Q}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; exit $rc"); save("target_verify_consumer",work)
 got=ssh(f"set +e; cat {Q}/artifact/forward_batch_dual_cache.json 2>/dev/null; cat {Q}/artifact/forward-batch-activation-c32/INVOCATION.json 2>/dev/null; cat {Q}/artifact/forward-batch-activation-c32/TERMINAL.json 2>/dev/null; cat {Q}/artifact/server_raw.log 2>/dev/null; exit 0"); save("retrieved",got)
 return finish("component_execution_record", "activation_consumer_completed" if work.returncode==0 else "component_consumer_failed", True, "candidate_cuda_invocation_started\\\": true" in got.stdout)

if __name__ == "__main__":
    raise SystemExit(main())
