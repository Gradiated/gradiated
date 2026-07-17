#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="lmsysorg/sglang:v0.5.15-cu130@sha256:655d004115e384b56b73ad6869bb04b29cce7ba3e597ce8f92eeeb49e2acb0af"
if [[ "${V2_IN_CONTAINER:-0}" != 1 ]]; then
  SCRIPT_PATH="$(readlink -f "$0")"
  exec sudo docker run --rm --gpus all --ipc=host --shm-size=32g --cap-add SYS_NICE \
    -v /workspace:/workspace -v /home/glmrunner/input:/input:ro \
    -v "$SCRIPT_PATH:/input/remote_v2_capture.sh:ro" \
    -e V2_IN_CONTAINER=1 -e MODEL=/workspace/model-bf16 \
    -e SUITE=/input/development.jsonl -e OUTROOT=/workspace/v2-captures \
    -e PUBLIC=/workspace/public-v2 "$IMAGE" bash /input/remote_v2_capture.sh "$@"
fi
PHASE="${1:?phase required}"
DEADLINE="${2:?deadline required}"
MODEL="${MODEL:-/workspace/model-bf16}"
SUITE="${SUITE:-/home/glmrunner/input/development.jsonl}"
OUTROOT="${OUTROOT:-/workspace/v2-captures}"
PUBLIC="${PUBLIC:-/workspace/public-v2}"
ROOT="$OUTROOT/capture-$PHASE"
SERVER_PID=""
mkdir -p "$ROOT" "$PUBLIC"
stop_server() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
package() {
  local rc=$?
  set +e
  stop_server
  nvidia-smi -q > "$ROOT/nvidia-smi-final.txt" 2>&1
  printf '%s\n' "$rc" > "$ROOT/remote-exit-code"
  if [[ -f "$ROOT/capture-result.json" ]]; then
    tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C "$OUTROOT" -czf "$PUBLIC/v2-capture-$PHASE.tar.gz.tmp" "capture-$PHASE"
    mv "$PUBLIC/v2-capture-$PHASE.tar.gz.tmp" "$PUBLIC/v2-capture-$PHASE.tar.gz"
    sha256sum "$PUBLIC/v2-capture-$PHASE.tar.gz" > "$PUBLIC/v2-capture-$PHASE.tar.gz.sha256"
  fi
  exit "$rc"
}
trap package EXIT
if (( $(date +%s) >= DEADLINE )); then echo 'capture deadline reached' >&2; exit 71; fi
printf '{"phase":%s,"state":"bootstrap"}\n' "$PHASE" > "$ROOT/phases.jsonl"
python3 - "$MODEL" <<'PY'
import json, sys
p=json.load(open(sys.argv[1]+"/model-files-manifest.json"))
if p.get("revision") != "33faccf4c2ba82142214d0d4e16232a4e9ccfe10" or p.get("shard_count") != 48 or p.get("weight_bytes") != 62444175504:
    raise SystemExit("checkpoint identity mismatch")
PY
cp "$SUITE" "$ROOT/development.jsonl"
sha256sum "$ROOT/development.jsonl" > "$ROOT/suite.sha256"
nvidia-smi -q > "$ROOT/nvidia-smi-initial.txt" 2>&1
python3 -m sglang.launch_server --model-path "$MODEL" --served-model-name zai-org/GLM-4.7-Flash --model-impl sglang --host 127.0.0.1 --port 30000 --context-length 32768 --max-running-requests 32 --mem-fraction-static 0.90 --chunked-prefill-size 8192 --tool-call-parser glm47 --reasoning-parser glm45 --stream-interval 1 --disable-radix-cache --schedule-policy fcfs --random-seed 1234 > "$ROOT/server.stdout.log" 2> "$ROOT/server.stderr.log" &
SERVER_PID=$!
deadline_health=$(( $(date +%s) + 900 ))
until curl -fsS http://127.0.0.1:30000/health >/dev/null; do
  (( $(date +%s) < deadline_health && $(date +%s) < DEADLINE )) || { echo 'server readiness timeout' >&2; exit 72; }
  sleep 2
done
printf '{"phase":%s,"state":"healthy"}\n' "$PHASE" >> "$ROOT/phases.jsonl"
python3 - "$SUITE" "$ROOT" "$PHASE" <<'PY'
import base64, hashlib, json, sys, time, urllib.request
from pathlib import Path
suite, root, phase = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
rows=[json.loads(x) for x in suite.read_text().splitlines() if x.strip()]
raw=[]; normalized=[]; evidence=[]
def post(path, payload):
    body=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
    req=urllib.request.Request("http://127.0.0.1:30000"+path, body, {"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r: data=r.read()
    return data, json.loads(data)
for case in rows:
    cid=case["case_id"]
    if case["category"] == "teacher_forced_loss":
        payload={"text":case["teacher_forced_text"],"sampling_params":{"temperature":0.0,"max_new_tokens":256},"return_logprob":True,"logprob_start_len":0,"top_logprobs_num":0}
        b, value=post("/generate", payload)
        values=value.get("meta_info",{}).get("input_token_logprobs")
        if not isinstance(values,list) or len(values)<case["scorer"]["minimum_scored_tokens"]: raise SystemExit("incomplete runtime logprobs")
        output={"source":"runtime_teacher_forced_input_token_logprobs","token_sequence_sha256":case["token_sequence_sha256"],"input_token_logprobs":[{"logprob":float(x[0]),"token_id":int(x[1])} for x in values if x[0] is not None]}
    else:
        messages=case.get("history",[])+[{"role":"user","content":(case.get("synthetic_context","")+"\n\n" if case["category"]=="long_context_retrieval" else "")+case["prompt"]}]
        payload={"model":"zai-org/GLM-4.7-Flash","messages":messages,"temperature":0.0,"top_p":1.0,"max_tokens":256,"seed":470200,"stream":False,"chat_template_kwargs":{"enable_thinking":False}}
        reps=case.get("deterministic_repetitions",1); results=[]
        for _ in range(reps): b,value=post("/v1/chat/completions",payload); results.append((b,value))
        outputs=[x[1]["choices"][0]["message"].get("content") for x in results]
        if len(set(outputs)) != 1: raise SystemExit("deterministic repetition mismatch")
        output=outputs[0]
    raw.append({"case_id":cid,"phase":phase,"raw_response_b64":base64.b64encode(b).decode(),"raw_response_sha256":hashlib.sha256(b).hexdigest()})
    normalized.append({"case_id":cid,"output":output})
    evidence.append({"case_id":cid,"raw_response_sha256":hashlib.sha256(b).hexdigest(),"phase":phase})
(root/"raw-response-bytes.json").write_text(json.dumps(raw,sort_keys=True)+"\n")
(root/"normalized-output-bytes.json").write_text(json.dumps(normalized,sort_keys=True)+"\n")
(root/"transform-decisions.json").write_text(json.dumps({"normalization":"contract runner only","holdout_accessed":False})+"\n")
(root/"responses.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in normalized))
(root/"runtime-evidence.json").write_text(json.dumps({"phase":phase,"cases":evidence,"source":"runtime"},sort_keys=True)+"\n")
(root/"identity-manifest.json").write_text(json.dumps({"model_revision":"33faccf4c2ba82142214d0d4e16232a4e9ccfe10","checkpoint_marker":"verified-48-shard-manifest","suite_sha256":hashlib.sha256(suite.read_bytes()).hexdigest()},sort_keys=True)+"\n")
(root/"capture-result.json").write_text(json.dumps({"phase":phase,"case_count":len(rows),"pass":True,"generated_at":time.time()},sort_keys=True)+"\n")
PY
printf '{"phase":%s,"state":"complete"}\n' "$PHASE" >> "$ROOT/phases.jsonl"
