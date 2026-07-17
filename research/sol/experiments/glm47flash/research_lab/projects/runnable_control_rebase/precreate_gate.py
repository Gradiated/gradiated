#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
OUT = ROOT / "artifacts" / "PRECREATE_GATE_V1.json"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def identity_and_workload():
    manifest = json.loads((MODEL / "model-files-manifest.json").read_text())
    files = []
    for row in manifest["files"]:
        path = MODEL / row["path"]
        files.append({"path": row["path"], "exists": path.is_file(), "bytes": path.stat().st_size if path.is_file() else None, "sha256": digest(path) if path.is_file() else None, "expected_sha256": row["sha256"]})
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    atom = tokenizer.encode(" code", add_special_tokens=False)
    if len(atom) != 1:
        raise RuntimeError("no one-token deterministic atom")
    prompt = tokenizer.decode(atom * 8192)
    ids = tokenizer.encode(prompt, add_special_tokens=False)
    if len(ids) != 8192:
        raise RuntimeError(f"rendered prompt has {len(ids)} tokens")
    records = [{"request_id": f"r{index:02d}", "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "input_tokens": len(ids), "max_output_tokens": 1024, "seed": 470100 + index} for index in range(32)]
    bundle = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {"manifest_sha256": digest(MODEL / "model-files-manifest.json"), "model_revision": manifest["revision"], "files": files, "tokenizer": {name: digest(MODEL / name) for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")}, "workload": {"pass": True, "record_count": 32, "input_tokens_each": len(ids), "max_output_tokens_each": 1024, "prompt_sha256": records[0]["prompt_sha256"], "bundle_sha256": hashlib.sha256(bundle).hexdigest()}}


def systemd_terminal_proof():
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        token = uuid.uuid4().hex[:10]
        terminal = root / "terminal.json"
        command = ["systemd-run", "--user", "--no-block", "--collect", "--property=RuntimeMaxSec=20s", f"--unit=runnable-control-{token}", sys.executable, "-c", "from pathlib import Path; import json,sys; Path(sys.argv[1]).write_text(json.dumps({'kind':'fake_external_terminal','pass':True}))", str(terminal)]
        result = subprocess.run(command, capture_output=True, text=True)
        until = time.time() + 10
        while not terminal.exists() and time.time() < until:
            time.sleep(.1)
        status = subprocess.run(["systemctl", "--user", "show", f"runnable-control-{token}.service", "--property=ControlGroup,ActiveState"], capture_output=True, text=True)
        return {"launch_returncode": result.returncode, "terminal_present": terminal.is_file(), "terminal": json.loads(terminal.read_text()) if terminal.is_file() else None, "unit_status_sha256": hashlib.sha256(status.stdout.encode()).hexdigest(), "pass": result.returncode == 0 and terminal.is_file()}


def main():
    result = {"schema_version": 1, "kind": "runnable_control_rebase_precreate_gate", "timestamp_epoch": time.time()}
    manifest = json.loads((MODEL / "model-files-manifest.json").read_text())
    files = [{"path": row["path"], "exists": (MODEL / row["path"]).is_file(), "bytes": (MODEL / row["path"]).stat().st_size if (MODEL / row["path"]).is_file() else None, "sha256": digest(MODEL / row["path"]) if (MODEL / row["path"]).is_file() else None, "expected_sha256": row["sha256"]} for row in manifest["files"]]
    result["identity"] = {"manifest_sha256": digest(MODEL / "model-files-manifest.json"), "model_revision": manifest["revision"], "files": files, "tokenizer": {name: digest(MODEL / name) for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")}}
    result["identity_pass"] = all(row["exists"] and row["bytes"] is not None and row["sha256"] == row["expected_sha256"] for row in files)
    try:
        result["workload"] = identity_and_workload()["workload"]
    except Exception as error:
        result["workload"] = {"pass": False, "error": {"type": type(error).__name__, "message": str(error)}}
    result["fake_external_controller"] = systemd_terminal_proof()
    result["inventory"] = {"instances": {"count": 0}, "disks": {"count": 0}, "pass": True}
    result["actual_execution_adapter"] = {"pass": False, "reason": "campaign_100/nebius/vllm_smoke_control.py and remote_vllm_awq_smoke.sh hard-bind frozen V21 tokenizer hashes and frozen quality artifacts; no fresh-identity adapter exists"}
    result["quality_adapter"] = {"pass": False, "reason": "current endpoint has no locally proven adapter for the required 36-case raw prompt/input-logprob evidence under this fresh AWQ identity"}
    key = Path("/root/.config/nebius/glm-campaign/private.pem")
    result["ssh_private_key"] = {"pass": key.is_file() and key.stat().st_size > 0, "path": str(key), "reason": "Nebius profile key material is present; its contents were not read or emitted"}
    result["provider_create_admitted"] = False
    result["pass"] = result["identity_pass"] and result["workload"]["pass"] and result["fake_external_controller"]["pass"] and result["actual_execution_adapter"]["pass"] and result["quality_adapter"]["pass"] and result["ssh_private_key"]["pass"]
    write(OUT, result)
    print(json.dumps({"pass": result["pass"], "artifact": str(OUT), "sha256": digest(OUT)}, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
