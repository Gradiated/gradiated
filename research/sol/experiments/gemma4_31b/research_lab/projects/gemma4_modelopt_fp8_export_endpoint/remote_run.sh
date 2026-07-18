#!/usr/bin/env bash
set -Eeuo pipefail

remote=/home/glmrunner/gemma-attention-endpoint
run_id=modelopt-fp8-export-c32-20260718t1900z
run_root="$remote/$run_id"
artifact="$run_root/artifacts"
partial="$remote/modelopt-export.partial"
exports="$remote/modelopt-exports"
image=docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a
deadline_epoch=1784407500
producer_deadline_epoch=1784406600

sudo install -d -o glmrunner -g glmrunner "$run_root" "$artifact" "$exports" "$remote/workspace"

event() {
  python3 - "$artifact/EVENTS.jsonl" "$1" <<'PY'
import datetime,json,pathlib,sys
with pathlib.Path(sys.argv[1]).open("a") as handle:
    handle.write(json.dumps({"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"),"phase":sys.argv[2]},sort_keys=True)+"\n")
PY
}

terminal() {
  python3 - "$artifact/TERMINAL.json" "$1" "$2" <<'PY'
import datetime,json,pathlib,sys
path=pathlib.Path(sys.argv[1]); temporary=path.with_suffix(".part")
temporary.write_text(json.dumps({"schema_version":1,"status":"terminal","pass":False,"classification":sys.argv[2],"message":sys.argv[3],"timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z")},indent=2,sort_keys=True)+"\n")
temporary.replace(path)
PY
}

fail() {
  terminal "$1" "$2"
  exit 1
}

package_artifacts() {
  sudo tar -C "$run_root" -czf "$run_root/artifacts.tar.gz.part" artifacts >/dev/null 2>&1 || return 0
  sudo mv "$run_root/artifacts.tar.gz.part" "$run_root/artifacts.tar.gz"
  sudo chown glmrunner:glmrunner "$run_root/artifacts.tar.gz"
  sha256sum "$run_root/artifacts.tar.gz" >"$run_root/artifacts.tar.gz.sha256"
}

sampler_pid=
cleanup() {
  if [[ -n "$sampler_pid" ]]; then kill "$sampler_pid" >/dev/null 2>&1 || true; wait "$sampler_pid" >/dev/null 2>&1 || true; fi
  sudo docker rm -f gemma-modelopt-producer >/dev/null 2>&1 || true
  if [[ ! -s "$artifact/TERMINAL.json" ]]; then terminal owner_failure "remote owner exited without a typed terminal"; fi
  sudo docker logs gemma-attention-endpoint >"$artifact/server-final.log" 2>&1 || true
  sudo docker inspect gemma-attention-endpoint >"$artifact/container-inspect-final.json" 2>&1 || true
  package_artifacts
}
trap cleanup EXIT
trap 'fail owner_failure "$BASH_COMMAND"' ERR

event preflight
(( $(date +%s) < producer_deadline_epoch )) || fail timeout before_producer
test "$(find "$remote/checkpoint" -maxdepth 1 -type f | wc -l)" -eq 8 || fail producer_failure checkpoint_file_count
test "$(find "$remote/checkpoint" -maxdepth 1 -type f -printf '%s\n' | awk '{s+=$1} END {printf "%.0f",s}')" = 62578655208 || fail producer_failure checkpoint_byte_count
sudo docker image inspect "$image" >"$artifact/image-inspect.json" || fail producer_failure pinned_image_missing
df -B1 "$remote" >"$artifact/disk-before.txt"
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits -lms 500 >"$artifact/gpu.csv" 2>"$artifact/gpu.stderr" &
sampler_pid=$!

event stop_resident_fused_server
sudo docker rm -f gemma-attention-endpoint >/dev/null 2>&1 || true
sudo rm -rf "$partial"
sudo install -d -o glmrunner -g glmrunner "$partial"

event install_declared_accelerate_dependency
sudo rm -rf "$remote/modelopt-python"
set +e
sudo docker run --rm -v "$remote:/work" "$image" python3 -m pip install --no-deps \
  --target /work/modelopt-python accelerate==1.1.0 >"$artifact/accelerate-install.log" 2>&1
accelerate_exit=$?
set -e
printf '%s\n' "$accelerate_exit" >"$artifact/accelerate-install.exit"
(( accelerate_exit == 0 )) || fail producer_failure "declared accelerate dependency install exit $accelerate_exit"
sudo docker run --rm -e PYTHONPATH=/work/modelopt-python -v "$remote:/work" "$image" \
  python3 -c 'import accelerate; assert accelerate.__version__ == "1.1.0"; print(accelerate.__version__)' \
  >"$artifact/accelerate-version.txt" 2>"$artifact/accelerate-import.stderr" \
  || fail producer_failure accelerate_import

event official_modelopt_fp8_producer_start
producer_started=$(date +%s)
set +e
timeout --signal=TERM 5400 sudo docker run --rm --name gemma-modelopt-producer --gpus all --ipc=host --network host \
  -e PYTHONPATH=/work/modelopt-python -e HF_HOME=/work/modelopt-cache -e HF_DATASETS_CACHE=/work/modelopt-cache/datasets \
  -v "$remote:/work" "$image" \
  python3 /work/workspace/official_local_path_adapter.py quantize \
    --model-path /work/checkpoint --export-dir /work/modelopt-export.partial \
    --quantization-method modelopt_fp8 --device cuda \
  >"$artifact/producer.log" 2>&1
producer_exit=$?
set -e
producer_ended=$(date +%s)
printf '%s\n' "$producer_exit" >"$artifact/producer.exit"
if (( producer_exit != 0 )); then fail producer_failure "official producer exit $producer_exit"; fi
test -s "$partial/config.json" || fail producer_failure export_config_missing
test -s "$partial/tokenizer_config.json" || fail producer_failure export_tokenizer_missing
find "$partial" -maxdepth 1 -type f -name '*.safetensors' -print -quit | grep -q . || fail producer_failure export_weights_missing

event export_numerical_validation
set +e
sudo docker run --rm -v "$remote:/work" "$image" python3 /work/workspace/validate_export.py \
  --export /work/modelopt-export.partial --output /work/$run_id/artifacts/export-validation.json \
  >"$artifact/export-validation.log" 2>&1
validation_exit=$?
set -e
printf '%s\n' "$validation_exit" >"$artifact/export-validation.exit"
(( validation_exit == 0 )) || fail quality_sanity_failure "export numerical validation exit $validation_exit"

event content_address_export
python3 - "$partial" "$artifact/export-manifest.json" "$remote/modelopt-cache" "$producer_started" "$producer_ended" "$remote/modelopt-python" <<'PY'
import hashlib,json,os,pathlib,sys
root=pathlib.Path(sys.argv[1]); output=pathlib.Path(sys.argv[2]); cache=pathlib.Path(sys.argv[3])
files=[]
for path in sorted(x for x in root.rglob("*") if x.is_file()):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(8<<20),b""): digest.update(block)
    files.append({"path":str(path.relative_to(root)),"bytes":path.stat().st_size,"sha256":digest.hexdigest()})
canonical=json.dumps(files,sort_keys=True,separators=(",",":")).encode()
content_sha256=hashlib.sha256(canonical).hexdigest()
assert sum(x["bytes"] for x in files) <= 120*(1<<30), "export exceeds temporary-storage contract"
cache_files=[]
if cache.exists():
    for path in sorted(x for x in cache.rglob("*") if x.is_file()):
        digest=hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda:handle.read(8<<20),b""): digest.update(block)
        cache_files.append({"path":str(path.relative_to(cache)),"bytes":path.stat().st_size,"sha256":digest.hexdigest()})
config=json.loads((root/"config.json").read_text())
dependency=pathlib.Path(sys.argv[6]); dependency_files=[]
for path in sorted(x for x in dependency.rglob("*") if x.is_file()):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    dependency_files.append({"path":str(path.relative_to(dependency)),"bytes":path.stat().st_size,"sha256":digest})
manifest={"schema_version":1,"producer_terminal":"passed","content_sha256":content_sha256,"files":files,"total_bytes":sum(x["bytes"] for x in files),"source_checkpoint":{"path":"/home/glmrunner/gemma-attention-endpoint/checkpoint","file_count":8,"bytes":62578655208,"model":"google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"},"producer":{"image":"sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a","sglang":"0.5.12","nvidia_modelopt":"0.44.0","torch":"2.11.0+cu130","transformers":"5.6.0","accelerate":"1.1.0","dependency_layer_files":dependency_files,"workflow":"/sgl-workspace/sglang/examples/usage/modelopt_quantize_and_export.py","adapter":"official_local_path_adapter.py; only bypasses Hugging Face repo-id cache lookup for an existing local directory","quantization_method":"modelopt_fp8","recipe":"modelopt.torch.quantization.FP8_DEFAULT_CFG","weight_format":"float8_e4m3fn","accumulator_policy":"pinned SGLang/ModelOpt FP8_DEFAULT_CFG; no override","started_epoch":int(sys.argv[4]),"ended_epoch":int(sys.argv[5]),"wall_seconds":int(sys.argv[5])-int(sys.argv[4])},"calibration":{"dataset":"cnn_dailymail","num_samples":512,"batch_size":36,"include_labels":False,"identity_files":cache_files},"quantization_config":config.get("quantization_config"),"peak_additional_storage_contract_gib":120}
temporary=output.with_suffix(".part"); temporary.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n"); temporary.replace(output)
PY
content_sha256=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["content_sha256"])' "$artifact/export-manifest.json")
export_path="$exports/$content_sha256"
test ! -e "$export_path" || fail storage_failure content_address_collision
sudo mv "$partial" "$export_path"
sudo sync "$export_path"
printf '%s\n' "$export_path" >"$artifact/export-path.txt"
df -B1 "$remote" >"$artifact/disk-after-export.txt"

event pinned_sglang_consumer_start
(( $(date +%s) < producer_deadline_epoch )) || fail timeout producer_consumed_endpoint_reserve
sudo docker run -d --name gemma-attention-endpoint --gpus all --ipc=host --network host \
  -v "$remote:/work" "$image" python3 -m sglang.launch_server \
  --model-path "/work/modelopt-exports/$content_sha256" --tokenizer-path "/work/modelopt-exports/$content_sha256" \
  --quantization modelopt --dtype bfloat16 --tp-size 1 --kv-cache-dtype fp8_e5m2 \
  --served-model-name google/gemma-4-31B-it --host 0.0.0.0 --port 30000 \
  --context-length 5000 --max-running-requests 32 --mem-fraction-static 0.85 \
  --enable-metrics --skip-server-warmup --enable-dynamic-chunking --chunked-prefill-size 2048 \
  --enable-fused-qk-norm-rope >"$artifact/container-id.txt"

ready=0
for attempt in $(seq 1 180); do
  if curl -fsS http://127.0.0.1:30000/v1/models >"$artifact/models.json" 2>"$artifact/models.stderr"; then ready=1; break; fi
  if ! sudo docker inspect -f '{{.State.Running}}' gemma-attention-endpoint 2>/dev/null | grep -q true; then break; fi
  sleep 5
done
sudo docker logs gemma-attention-endpoint >"$artifact/server-start.log" 2>&1 || true
sudo docker inspect gemma-attention-endpoint >"$artifact/container-inspect.json" 2>&1 || true
(( ready == 1 )) || fail consumer_load_failure exported_server_not_ready
curl -fsS http://127.0.0.1:30000/get_server_info >"$artifact/server-info.json" || fail precision_path_unproven server_info_missing

event bounded_output_sanity
sanity_status=$(curl -sS -o "$artifact/sanity-response.json" -w '%{http_code}' -H 'Content-Type: application/json' \
  -d '{"model":"google/gemma-4-31B-it","prompt":"The capital of France is","max_tokens":16,"min_tokens":16,"ignore_eos":true,"temperature":0}' \
  http://127.0.0.1:30000/v1/completions)
printf '%s\n' "$sanity_status" >"$artifact/sanity-http-status.txt"
python3 - "$artifact" <<'PY'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]); status=(root/"sanity-http-status.txt").read_text().strip(); response=json.loads((root/"sanity-response.json").read_text())
choice=(response.get("choices") or [{}])[0]; usage=response.get("usage") or {}
assert status=="200" and bool(choice.get("text")) and int(usage.get("completion_tokens",0))==16
(root/"output-sanity.json").write_text(json.dumps({"pass":True,"http_status":200,"text_nonempty":True,"completion_tokens":16,"response_sha256":__import__("hashlib").sha256((root/"sanity-response.json").read_bytes()).hexdigest()},indent=2,sort_keys=True)+"\n")
PY

event idle_and_flush_boundary
curl -fsS http://127.0.0.1:30000/metrics >"$artifact/idle-metrics.prom"
python3 - "$artifact/idle-metrics.prom" "$artifact/idle-boundary.json" <<'PY'
import json,pathlib,sys
raw=pathlib.Path(sys.argv[1]).read_text(); required=("sglang:num_running_reqs", "sglang:num_queue_reqs")
values={}
for name in required:
    rows=[float(x.rsplit(" ",1)[1]) for x in raw.splitlines() if x.startswith(name+"{")]
    assert rows and all(x==0 for x in rows), (name,rows)
    values[name]=rows
pathlib.Path(sys.argv[2]).write_text(json.dumps({"pass":True,"running_requests":0,"queued_requests":0,"metric_values":values},indent=2,sort_keys=True)+"\n")
PY
flush_status=$(curl -sS -o "$artifact/flush-body.txt" -w '%{http_code}' -X POST http://127.0.0.1:30000/flush_cache)
printf '%s\n' "$flush_status" >"$artifact/flush-status.txt"
[[ "$flush_status" == 200 ]] || fail quality_sanity_failure "flush HTTP $flush_status"

event exact_mix_once
(( $(date +%s) < 1784407200 )) || fail timeout exact_mix_reserve_exhausted
sudo rm -rf "$run_root/exact_mix"
set +e
sudo docker exec gemma-attention-endpoint python3 /work/workspace/exact_mix_runner.py \
  --output "/work/$run_id/exact_mix" --arm modelopt_fp8_export_fused_qk_norm_rope_c32 \
  >"$artifact/exact-mix.stdout" 2>"$artifact/exact-mix.stderr"
runner_exit=$?
set -e
printf '%s\n' "$runner_exit" >"$artifact/exact-mix.exit"
sudo cp "$run_root/exact_mix/TERMINAL.json" "$artifact/candidate-terminal.json" || fail quality_sanity_failure candidate_terminal_missing
sudo chown glmrunner:glmrunner "$artifact/candidate-terminal.json"
sudo tar -C "$run_root" -czf "$artifact/exact-mix.tar.gz" exact_mix
sudo chown glmrunner:glmrunner "$artifact/exact-mix.tar.gz"
(( runner_exit == 0 )) || fail quality_sanity_failure "exact mix exit $runner_exit"
sudo docker logs gemma-attention-endpoint >"$artifact/server-final.log" 2>&1
curl -fsS http://127.0.0.1:30000/get_server_info >"$artifact/server-info-final.json"

event decision
python3 - "$artifact" "$content_sha256" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); content_sha=sys.argv[2]
candidate=json.loads((root/"candidate-terminal.json").read_text()); info=json.loads((root/"server-info-final.json").read_text()); config=json.loads((pathlib.Path((root/"export-path.txt").read_text().strip())/"config.json").read_text()); validation=json.loads((root/"export-validation.json").read_text())
args=(root/"container-inspect-final.json").read_text() if (root/"container-inspect-final.json").exists() else (root/"container-inspect.json").read_text(); log=(root/"server-final.log").read_text(errors="replace")
quant_cfg=config.get("quantization_config") or {}; path_verified=("FP8" in str(quant_cfg.get("quant_algo","")) and "--quantization" in args and "modelopt" in args.lower() and ("Detected ModelOpt FP8 checkpoint" in log or "modelopt_fp8" in log.lower() or "quant=\"modelopt\"" in log.lower()))
cache=candidate["cache"]; valid=bool(candidate["pass"] and candidate["complete_requests"]==32 and validation["pass"] and path_verified and cache["cached_prompt_tokens_delta"]==17120 and cache["uncached_prompt_tokens_delta"]==117728)
service=float(candidate["service_seconds_per_request"]); baseline=.9194573941250042; ceiling=.8734845244187539
classification="negative" if not valid else "promote_h200_export" if service<=ceiling else "retain_incremental" if service<baseline else "negative"
result={"schema_version":1,"status":"terminal","classification":classification,"pass":valid and classification in ("promote_h200_export","retain_incremental"),"candidate":candidate,"content_sha256":content_sha,"export_path":(root/"export-path.txt").read_text().strip(),"export_manifest_sha256":hashlib.sha256((root/"export-manifest.json").read_bytes()).hexdigest(),"comparator_sha256":"1a7e778eff080bf2eec27da939ea85a894ea9884036bdebd562af371405e78c3","runner_sha256":"143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7","comparator_service_seconds_per_request":baseline,"promotion_ceiling_seconds_per_request":ceiling,"service_seconds_per_request_reduction":1-service/baseline,"exported_fp8_path_consumed":path_verified,"numerical_output_sanity_verified":validation["pass"] and json.loads((root/"output-sanity.json").read_text())["pass"],"idle_flush_verified":json.loads((root/"idle-boundary.json").read_text())["pass"] and (root/"flush-status.txt").read_text().strip()=="200","cache_accounting_verified":cache["cached_prompt_tokens_delta"]==17120 and cache["uncached_prompt_tokens_delta"]==117728,"server_state":"healthy exported FP8 c32 server remains loaded on port 30000"}
temporary=root/"TERMINAL.json.part"; temporary.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); temporary.replace(root/"TERMINAL.json")
PY
event terminal_complete
