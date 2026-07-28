#!/usr/bin/env bash
set -Eeuo pipefail
root=/home/glmrunner/gemma4-dflash/work; source_dir="$root/sglang"; models="$root/models"; run="$root/dflash-cycle-oracle"; project=/home/glmrunner/gemma4-dflash/cycle-project
base=gemma4-dflash-sglang:588d1f7bc942-tied-head-adapter; image=gemma4-dflash-sglang:588d1f7bc942-cycle-oracle; commit=588d1f7bc9424201f89957e145f9d5af633a3eb8
mkdir -p "$run"; stage=preflight; science_started=false
finish() { rc=$?; sudo docker logs gemma4-dflash > "$run/server.log" 2>&1 || true; sudo docker inspect gemma4-dflash > "$run/server.inspect.json" 2>&1 || true; python3 - "$run/REMOTE_TERMINAL.json" "$stage" "$rc" "$science_started" <<'PY'
import json,pathlib,sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({"stage":sys.argv[2],"exit_code":int(sys.argv[3]),"science_started":sys.argv[4]=="true"},sort_keys=True)+"\n")
PY
}
trap finish EXIT
test "$(git -C "$source_dir" rev-parse HEAD)" = "$commit"; test -f "$models/target/model.safetensors.index.json"; test -f "$models/draft/model.safetensors"; sha256sum -c "$project/BOUND.sha256"
git -C "$source_dir" apply --check "$project/DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch"; git -C "$source_dir" apply "$project/DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch"
test "$(grep -c 'direct_carry_valid: bool = False' "$source_dir/python/sglang/srt/speculative/dflash_info_v2.py")" = 1
mkdir -p "$run/overlay" "$run/oracle"; install -m 0444 "$source_dir/python/sglang/srt/speculative/dflash_info_v2.py" "$run/overlay/dflash_info_v2.py"; install -m 0444 "$project/cycle_oracle_sitecustomize.py" "$run/oracle/sitecustomize.py"; printf 'FROM %s\nCOPY dflash_info_v2.py /sgl-workspace/sglang/python/sglang/srt/speculative/dflash_info_v2.py\n' "$base" > "$run/overlay/Dockerfile"; sudo docker build -t "$image" "$run/overlay" > "$run/image-build.log" 2>&1
stage=server; sudo docker rm -f gemma4-dflash >/dev/null 2>&1 || true
sudo docker run -d --name gemma4-dflash --gpus all --ipc=host --network host -e PYTHONPATH=/oracle -e DFLASH_CYCLE_CAPTURE=/work/oracle-cycles.jsonl -v "$models:/models:ro" -v "$project:/project:ro" -v "$run:/work" -v "$run/oracle:/oracle:ro" "$image" python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --dtype bfloat16 --tp-size 1 --attention-backend triton --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 1 --mem-fraction-static 0.85 --skip-server-warmup --speculative-algorithm DFLASH --speculative-draft-model-path /models/draft --speculative-draft-model-revision eabd648301ce28583cc14757912e5e0f84e152e1 --speculative-num-draft-tokens 16 --speculative-draft-attention-backend fa4 > "$run/container-id"
for i in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models > "$run/models.json" && break; sleep 5; done
test -s "$run/models.json"; stage=oracle_request; science_started=true
sudo docker exec gemma4-dflash python3 /project/dflash_endpoint_runner.py --arm cycle-oracle --concurrency 1 --output /work/request
stage=oracle_consumer; test -s "$run/oracle-cycles.jsonl"; test ! -e "$run/oracle-cycles.observer-error"
python3 - "$project/dflash_cycle_oracle.py" "$run/oracle-cycles.jsonl" "$run/DFLASH_CYCLE_ORACLE_TERMINAL.json" <<'PY'
import importlib.util,json,pathlib,sys
spec=importlib.util.spec_from_file_location("oracle",sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rows=[]
for i,line in enumerate(pathlib.Path(sys.argv[2]).read_text().splitlines()):
 row=json.loads(line); row["cycle_index"]=i; rows.append({"cycle":row,"result":m.evaluate_cycle(row)})
bad=next((x for x in rows if not x["result"]["pass"]),None); pathlib.Path(sys.argv[3]).write_text(json.dumps({"schema_version":1,"classification":"cycle_oracle","pass":bad is None,"cycles":rows,"first_divergent_field":None if bad is None else bad["result"]["issues"][0]},indent=2,sort_keys=True)+"\n"); raise SystemExit(0 if bad is None else 1)
PY
stage=terminal; sudo docker rm -f gemma4-dflash >/dev/null
