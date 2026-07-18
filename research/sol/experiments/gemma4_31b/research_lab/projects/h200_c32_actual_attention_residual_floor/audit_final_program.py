#!/usr/bin/env python3
import argparse, hashlib, json, subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
FILES = (PROJECT / "attention_bench.py", PROJECT / "remote_attention_stage.sh", PROJECT / "attention_owner.py",
         Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py"))

def main():
    p = argparse.ArgumentParser(); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    probe = subprocess.run(["docker","run","--rm","--network=none","--entrypoint","python3",IMAGE,"-c",
      "import hashlib,json,vllm; import vllm.vllm_flash_attn.flash_attn_interface as fa; import vllm.v1.attention.ops.triton_unified_attention as tu; print(json.dumps({'vllm':vllm.__version__,'fa_file':fa.__file__,'fa_sha':hashlib.sha256(open(fa.__file__,'rb').read()).hexdigest(),'fa_symbol':callable(fa.flash_attn_varlen_func),'triton_file':tu.__file__,'triton_sha':hashlib.sha256(open(tu.__file__,'rb').read()).hexdigest(),'triton_symbol':callable(tu.unified_attention)}))"], capture_output=True, text=True, timeout=180)
    observed = None
    if probe.returncode == 0:
        try: observed = json.loads(probe.stdout.splitlines()[-1])
        except (IndexError, json.JSONDecodeError): pass
    source = (PROJECT / "attention_bench.py").read_text(); remote = (PROJECT / "remote_attention_stage.sh").read_text(); owner = (PROJECT / "attention_owner.py").read_text()
    checks = {"exact_image_imports_concrete_consumers": isinstance(observed,dict) and observed.get("fa_symbol") and observed.get("triton_symbol"),
      "sliding_actual_pinned_flash_symbol": "flash_attn_varlen_func" in source and "32, 16, 256, 1024" in source,
      "global_actual_pinned_triton_symbol": "unified_attention" in source and "32, 4, 512" in source and "range(4214, 4572)" in source,
      "k_equals_v_global": "v = k" in source, "cuda_wall_oracle_and_h200": all(x in source for x in ("torch.cuda.Event", "torch.isfinite", "H200", "peak_allocated_bytes")),
      "architecture_formula_no_kv_double_count": "50 * sliding + 10 * globals_ms" in source and "LINEARS_HEAD + attention" in source,
      "typed_artifact_telemetry": all(x in remote for x in ("stage-terminal.json", "telemetry.csv", "manifest.json")),
      "shared_durable_controller": "controller.run(" in owner and all(x in Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius/mla_microbench_control.py").read_text() for x in ("validate_durable_owner", "start_independent_watchdog", "VerifiedRetainedOwner")),
      "all_staged_files_present": all(x.is_file() for x in FILES)}
    result={"schema_version":1,"type":"final_pinned_h200_c32_attention_program_audit","image":IMAGE,"image_probe_returncode":probe.returncode,"image_probe_stderr_tail":probe.stderr[-2000:],"observed_runtime":observed,"staged_files":{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in FILES},"checks":checks,"pass":all(checks.values())}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); return 0 if result["pass"] else 1
if __name__ == "__main__": raise SystemExit(main())
