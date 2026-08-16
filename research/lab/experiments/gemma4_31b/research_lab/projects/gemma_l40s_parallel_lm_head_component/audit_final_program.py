#!/usr/bin/env python3
import argparse
import hashlib
import inspect
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
CONTROLLER = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py")
BENCH = PROJECT / "vllm_parallel_lm_head_bench.py"
REMOTE = PROJECT / "remote_parallel_lm_head_stage.sh"

PROBE = r'''
import hashlib,inspect,json,types,vllm,torch
from vllm.config import DeviceConfig,VllmConfig,set_current_vllm_config
from vllm.distributed.parallel_state import ensure_model_parallel_initialized,init_distributed_environment
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
c=VllmConfig(device_config=DeviceConfig(device='cpu')); c.model_config=types.SimpleNamespace(dtype=torch.bfloat16,head_dtype=None,is_moe=False)
with set_current_vllm_config(c):
 init_distributed_environment(world_size=1,rank=0,distributed_init_method='tcp://127.0.0.1:29501',local_rank=0,backend='gloo')
 ensure_model_parallel_initialized(1,1,backend='gloo')
 with torch.device('meta'): h=ParallelLMHead(262144,5376,params_dtype=torch.bfloat16,prefix='model.lm_head')
print(json.dumps({'vllm_version':vllm.__version__,'consumer':type(h).__module__+'.'+type(h).__name__,'method':type(h.quant_method).__module__+'.'+type(h.quant_method).__name__,'consumer_source_sha256':hashlib.sha256(inspect.getsource(type(h)).encode()).hexdigest(),'method_source_sha256':hashlib.sha256(inspect.getsource(type(h.quant_method)).encode()).hexdigest(),'weight_shape':list(h.weight.shape),'weight_dtype':str(h.weight.dtype)},sort_keys=True))
'''

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    source, remote, controller = BENCH.read_text(), REMOTE.read_text(), CONTROLLER.read_text()
    probe = subprocess.run(["docker","run","--rm","--network=none","--entrypoint","python3",IMAGE,"-c",PROBE],capture_output=True,text=True,timeout=180)
    observed = None
    if probe.returncode == 0:
        for line in reversed(probe.stdout.splitlines()):
            try:
                observed = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    checks = {
        "exact_image_cpu_safe_consumer_construction": probe.returncode == 0 and isinstance(observed,dict) and observed.get("consumer","").endswith(".ParallelLMHead") and observed.get("weight_shape") == [262144,5376],
        "actual_pinned_consumer_and_method": all(token in source for token in ("ParallelLMHead", "head.quant_method.apply(head, activations, None)", "set_current_vllm_config")),
        "all_six_required_m_rows": "MS = (1, 2, 4, 8, 16, 32)" in source and "len(rows) == len(MS)" in source,
        "oracle_consumes_timed_outputs": "timed ParallelLMHead output violated finite zero oracle" in source and "output = fn()" in source,
        "cuda_and_wall_timing_memory_telemetry": all(token in source + remote for token in ("torch.cuda.Event", "wall_ms", "peak_allocated_bytes", "peak_reserved_bytes", "telemetry.csv", "useful_gpu_seconds")),
        "budget_translation": all(token in source for token in ("STEPS = 358", "PLANNING_SECONDS = 1.394581", "CONSERVATIVE_SECONDS = 0.86329", "per_request_head_seconds_at_358_steps")),
        "typed_nonzero_failure_and_manifest": "return 0 if result[\"pass\"] else 1" in source and "stage-terminal.json" in remote and "manifest.json" in remote and "exit \"$rc\"" in remote,
        "shared_durable_controller": all(token in controller for token in ("VerifiedRetainedOwner", "start_independent_watchdog", "conditional_trigger", "validate_durable_owner")),
    }
    result = {"schema_version":1,"classification":"final_staged_exact_image_parallel_lm_head_audit","image":IMAGE,"image_probe_returncode":probe.returncode,"image_probe_stderr_tail":probe.stderr[-2000:],"observed_runtime":observed,"staged_files":{BENCH.name:digest(BENCH),REMOTE.name:digest(REMOTE),CONTROLLER.name:digest(CONTROLLER)},"checks":checks,"pass":all(checks.values())}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return 0 if result['pass'] else 1

if __name__ == '__main__': raise SystemExit(main())
