#!/usr/bin/env bash
set -euo pipefail
project=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_multiresolution_global_kv_codesign
lab=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
artifact="$project/artifacts/h200-global-kv-20260728t1210z"
archive="$artifact/endpoint-repair4-compact.tar.gz"
terminal="$artifact/ENDPOINT_REPAIR4_TERMINAL_ADOPTION.json"
python3 - "$archive" "$terminal" <<'PY'
import hashlib, json, pathlib, tarfile, sys
archive, terminal = map(pathlib.Path, sys.argv[1:])
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
if digest != "3e0bae8f52a637ca664d01b3857c0e1bd19c4ed6b5b4a72300ade26a105a109c":
    raise SystemExit("repair4_archive_digest_mismatch")
with tarfile.open(archive, "r:gz") as bundle:
    names = {member.name: member for member in bundle.getmembers()}
    def text(name):
        stream = bundle.extractfile(names[name]); return stream.read().decode()
    root = "endpoint-artifacts-repair4/"
    activation = json.loads(text(root + "ACTIVATION_PROBE.json"))
    hook = json.loads(text(root + "candidate-hook-diagnostic.json"))
    marker = json.loads(text(root + "candidate-science-started.json"))
    requests = sorted(name for name in names if name.startswith(root + "candidate-c32/request-") and name.endswith(".json"))
    responses = sorted(name for name in names if name.startswith(root + "candidate-c32/response-") and name.endswith(".sse"))
    server_stderr = text(root + "candidate-server.stderr")
    driver_stderr = text(root + "candidate-driver.stderr")
result = {
    "schema_version": 1,
    "classification": "candidate_c32_consumed_oom_infeasible",
    "scope": "exact_global_kv_endpoint_implementation_c32_memory_geometry",
    "archive_sha256": digest,
    "activation_probe": {"pass": activation.get("pass"), "telemetry_rows": activation.get("telemetry_rows"), "fallback": False, "compact_entries": 26},
    "candidate": {"science_started": bool(marker), "request_files": len(requests), "response_files": len(responses), "latency_seconds_per_request": None, "post_run_metrics": "unavailable_connection_refused_after_server_exit", "driver_stderr_sha256": hashlib.sha256(driver_stderr.encode()).hexdigest()},
    "failure": {"hook_diagnostic": hook, "server_oom_global_layer": 35, "server_stderr_sha256": hashlib.sha256(server_stderr.encode()).hexdigest()},
    "preserved_stock_terminal_sha256": "90e389320a2faf0730d9a4916de3a12df1c593c141bb2f8382810914852ec3bc",
    "replay_prohibited": True,
}
tmp = terminal.with_suffix(".json.part")
tmp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
tmp.replace(terminal)
PY
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" update --project gemma4_multiresolution_global_kv_codesign --contents '{"schema_version":1,"project":"gemma4_multiresolution_global_kv_codesign","checkpoint":"Verified 62578655208-byte checkpoint resident at /home/glmrunner/gemma4-multiresolution-global-kv/checkpoint","image":"Pinned SGLang image resident","server_state":"No server after candidate global-layer-35 OOM","artifacts":"ENDPOINT_REPAIR4_TERMINAL_ADOPTION.json; repair4 compact archive retained","state":"maintenance: consumed c32 OOM terminal adopted"}'
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$lab" release --project gemma4_multiresolution_global_kv_codesign --condition maintenance
