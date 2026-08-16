#!/usr/bin/env python3
"""Materialize and interrogate the exact image without provider mutation."""
import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
PROJECT = Path(__file__).resolve().parent
W4_FQCN = "vllm.model_executor.layers.quantization.awq_marlin.AWQMarlinLinearMethod"
FP8_FQCN = "vllm.model_executor.layers.quantization.fp8.Fp8LinearMethod"
PROBE = r"""
import hashlib, importlib, inspect, json, pkgutil
import vllm
import vllm.model_executor.layers.quantization as q
names=[]; classes=[]
for item in pkgutil.iter_modules(q.__path__, q.__name__ + '.'):
    lower=item.name.lower()
    if not any(x in lower for x in ('awq','gptq','marlin','fp8')): continue
    names.append(item.name)
    try: module=importlib.import_module(item.name)
    except Exception as error:
        classes.append({'module':item.name,'import_error':{'type':type(error).__name__,'message':str(error)[:300]}}); continue
    for name, value in inspect.getmembers(module, inspect.isclass):
        text=(name + ' ' + value.__module__).lower()
        if any(x in text for x in ('awq','gptq','marlin','fp8')):
            classes.append({'module':item.name,'name':name,'fqcn':value.__module__+'.'+name,'create_weights':hasattr(value,'create_weights'),'apply':hasattr(value,'apply'),'signature':str(inspect.signature(value))[:1000],'source_sha256':hashlib.sha256(inspect.getsource(value).encode()).hexdigest()})
fp8=importlib.import_module('vllm.model_executor.layers.quantization.fp8')
classes.extend({'module':fp8.__name__,'name':name,'fqcn':value.__module__+'.'+name,'create_weights':hasattr(value,'create_weights'),'apply':hasattr(value,'apply'),'signature':str(inspect.signature(value))[:1000],'source_sha256':hashlib.sha256(inspect.getsource(value).encode()).hexdigest()} for name,value in inspect.getmembers(fp8,inspect.isclass) if name in ('Fp8Config','Fp8LinearMethod'))
w4=[x for x in classes if x.get('create_weights') and x.get('apply') and ('awq' in x.get('fqcn','').lower() or 'gptq' in x.get('fqcn','').lower())]
fp=[x for x in classes if x.get('fqcn','').endswith('.Fp8LinearMethod')]
print(json.dumps({'vllm_version':vllm.__version__,'quantization_modules':names,'classes':classes,'w4_candidates':w4,'fp8_candidates':fp},sort_keys=True))
"""

def write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)

def final_probe_json(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    selected = None
    for offset, char in enumerate(stdout):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "w4_candidates" in value and "fp8_candidates" in value:
            selected = value
    if selected is None:
        raise ValueError("probe stdout contains no complete final inspection JSON object")
    return selected

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--deadline-epoch", required=True, type=float)
    args = parser.parse_args()
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("runtime correction requires durable systemd ownership")
    root = args.artifact_root; root.mkdir(parents=True, exist_ok=False)
    if dt.datetime.now().timestamp() >= args.deadline_epoch:
        write(root / "runtime-correction-terminal.json", {"pass": False, "classification": "local_deadline_expired_before_image_probe"})
        return 1
    pull = subprocess.run(["docker", "pull", IMAGE], text=True, capture_output=True, timeout=max(60, int(args.deadline_epoch-dt.datetime.now().timestamp())))
    (root / "docker-pull.stdout.log").write_text(pull.stdout[-12000:])
    (root / "docker-pull.stderr.log").write_text(pull.stderr[-12000:])
    result = {"schema_version": 1, "image": IMAGE, "pull_returncode": pull.returncode, "provider_mutation": False}
    if pull.returncode == 0:
        probe = subprocess.run(["docker", "run", "--rm", "--network=none", "--entrypoint", "python3", IMAGE, "-c", PROBE], text=True, capture_output=True, timeout=180)
        (root / "probe.stderr.log").write_text(probe.stderr[-12000:])
        try:
            inspection = final_probe_json(probe.stdout)
        except ValueError as error:
            inspection = {"parser_error": str(error), "raw_stdout_tail": probe.stdout[-12000:]}
        write(root / "exact-image-inspection.json", inspection)
        candidates = inspection.get("classes", []) if isinstance(inspection, dict) else []
        w4 = [row for row in candidates if row.get("fqcn") == W4_FQCN and row.get("create_weights") and row.get("apply")]
        fp8 = [row for row in candidates if row.get("fqcn") == FP8_FQCN and row.get("create_weights") and row.get("apply")]
        staged = {name: hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() for name in ("vllm_w4_fp8_microbench.py", "remote_w4_fp8_stage.sh", "vllm_parallel_lm_head_bench.py", "remote_parallel_lm_head_stage.sh")}
        row_contract = {"required_shapes": 6, "m_values": [1, 2, 4, 8, 16], "representations": ["w4_marlin", "fp8"], "required_primary_rows": 60, "nonempty_rows_required": True}
        result.update({"probe_returncode": probe.returncode, "inspection_sha256": hashlib.sha256((root / "exact-image-inspection.json").read_bytes()).hexdigest(), "observed_runtime": inspection.get("vllm_version") if isinstance(inspection, dict) else None, "resolved_w4_consumer": w4, "resolved_fp8_consumer": fp8, "staged_files": staged, "staged_row_contract": row_contract, "pass": probe.returncode == 0 and len(w4) == 1 and len(fp8) == 1})
    else:
        result["pass"] = False
    result["classification"] = "exact_image_runtime_consumer_resolution_pass" if result["pass"] else "exact_image_runtime_consumer_resolution_fail"
    write(root / "runtime-correction-terminal.json", result)
    return 0 if result["pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
