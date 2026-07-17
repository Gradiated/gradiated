#!/usr/bin/env bash
set -Eeuo pipefail
deadline=${1:?deadline epoch required}
w=/home/glmrunner/gemma
rm -rf "$w/artifacts/baseline"
set +e
sudo docker exec -e VLLM_MODEL='google/gemma-4-31B-it' gemma-vllm python3 "$w/input/gemma_exact_vllm_runner.py" --output "$w/artifacts/baseline" --tokenizer "$w/model" --mode baseline
runner_rc=$?
set -e
curl -fsS http://127.0.0.1:30000/metrics > "$w/artifacts/baseline/metrics-owner-after.prom" || true
sudo docker inspect gemma-vllm > "$w/artifacts/baseline/container-inspect-after.json" || true
sudo docker logs gemma-vllm > "$w/artifacts/baseline/server.log" 2>&1 || true
cp "$w/runtime/gpu-telemetry.csv" "$w/artifacts/baseline/gpu-telemetry-through-baseline.csv"
python3 - "$w/artifacts/baseline" "$runner_rc" <<'PY'
import json,sys,time
from pathlib import Path
root=Path(sys.argv[1]); rc=int(sys.argv[2]); result=json.loads((root/'runner-result.json').read_text())
profiles=result.get('profiles') or []
terminal={
 'schema_version':2,'stage':'exact_gemma_vllm_h200_baseline','pass':rc==0 and result.get('pass') is True,
 'runner_returncode':rc,'complete_count':result.get('complete_count'),'failure_count':result.get('failure_count'),
 'useful_gpu_seconds':result.get('useful_gpu_seconds'),'prefill_decode':result.get('prefill_decode'),
 'raw_metric_contract':result.get('raw_metric_contract'),'reload_count':0,
 'terminal_concurrency':profiles[-1].get('concurrency') if profiles else None,
 'terminal_completed_requests_per_second':profiles[-1].get('completed_requests_per_second') if profiles else None,
 'written_at_epoch':time.time(),
}
tmp=root/'BASELINE_STAGE_TERMINAL.json.part'; tmp.write_text(json.dumps(terminal,indent=2,sort_keys=True)+'
'); tmp.replace(root/'BASELINE_STAGE_TERMINAL.json')
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$w/artifacts" -czf "$w/baseline-stage.tar.gz" baseline
sha256sum "$w/baseline-stage.tar.gz" > "$w/baseline-stage.tar.gz.sha256"+n+exit "$runner_rc"
