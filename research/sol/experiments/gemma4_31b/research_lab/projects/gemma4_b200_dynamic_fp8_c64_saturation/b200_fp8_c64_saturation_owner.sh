#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT=/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_b200_dynamic_fp8_c64_saturation
LAB=/root/workspace/research/sol/experiments/gemma4_31b/research_lab
BENCH=b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j
PRECLAIM=$PROJECT/PRECLAIM_TERMINAL.json
DEADLINE=${C64_DEADLINE_UTC:?set C64_DEADLINE_UTC before launch}
RUN_ID=${C64_RUN_ID:?set C64_RUN_ID before launch}
OUT=$PROJECT/artifacts/$RUN_ID
mkdir -p "$OUT"

phase() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$1" >>"$OUT/OWNER_PROGRESS.log"; }
heartbeat() { PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" heartbeat --project gemma4_b200_dynamic_fp8_c64_saturation --bench "$BENCH" >>"$OUT/heartbeat.log" 2>&1; }
while true; do heartbeat; sleep 45; done &
HEARTBEAT=$!
trap 'kill "$HEARTBEAT" 2>/dev/null || true' EXIT

repair() {
  phase "repair:$1"
  printf '%s\n' "$2" >"$OUT/REPAIR_DIAGNOSTIC.txt"
  /root/workspace/research/factory/tools/repair-handshake ready --root "$OUT" --repair-id "c64-saturation-$(date -u +%Y%m%dT%H%M%SZ)" --failure-kind "$1" --diagnostic "$OUT/REPAIR_DIAGNOSTIC.txt" --retry-scope endpoint_consumer --deadline "$DEADLINE" >>"$OUT/repair.log" 2>&1 || true
  while [ "$(date -u +%s)" -lt "$(date -u -d "$DEADLINE" +%s)" ]; do
    request=$(find "$OUT/.repair-handshakes" -name REPAIR_REQUEST.json -type f -print -quit 2>/dev/null || true)
    [ -n "$request" ] && exit 75
    sleep 30
  done
  exit 75
}

python3 - "$PRECLAIM" "$0" "$PROJECT/b200_fp8_c64_driver.py" <<'PY' || repair packet_binding "local packet binding did not validate"
import hashlib, json, pathlib, sys
p, owner, driver = map(pathlib.Path, sys.argv[1:])
x = json.loads(p.read_text())
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert x['owner_sha256'] == sha(owner.resolve())
assert x['driver_sha256'] == sha(driver)
assert x['bench_gate']['bench'] == 'b200-nvfp4-computeinstance-i00rqcq5yzr6xc991j'
PY

row=$(PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" show --bench "$BENCH") || repair inventory "unable to read claimed bench"
eval "$(ROW="$row" python3 - <<'PY'
import json, os, shlex
r=json.loads(os.environ['ROW'])['resource']
for key, value in {'HOST':r['public_ipv4'],'USER':r['ssh_user'],'KEY':r['identity_file'],'KNOWN':r['known_hosts_namespace']}.items(): print(f'{key}={shlex.quote(value)}')
PY
)"
[ -f "$KEY" ] || repair identity "inventory identity file is absent"
ssh_cmd=(ssh -n -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST")
REMOTE=/home/$USER/$RUN_ID
phase predecessor_executor_fence
python3 - <<'PY' >"$OUT/predecessor-executor-fence.json" || repair predecessor_executor "a predecessor endpoint executor is still live"
import json, os, pathlib
needles = ('run_endpoint_pair.sh', 'dynamic_fp8_endpoint_driver.py', 'endpoint_driver.py', 'b200_dynamic_fp8_owner', 'gemma4_b200_dynamic_fp8_endpoint')
matches = []
for entry in pathlib.Path('/proc').iterdir():
    if not entry.name.isdigit() or int(entry.name) == os.getpid():
        continue
    try:
        command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
    except OSError:
        continue
    if any(needle in command for needle in needles):
        matches.append({'pid': int(entry.name), 'command': command})
print(json.dumps({'matches': matches}, sort_keys=True))
raise SystemExit(bool(matches))
PY
phase pre_science_health
"${ssh_cmd[@]}" "ps -eo pid=,args=" >"$OUT/remote-process-census.txt" 2>"$OUT/remote-process-census.stderr" || repair remote_executor_census "could not inspect remote process census"
python3 - "$OUT/remote-process-census.txt" <<'PY' >"$OUT/remote-executor-census.json" || repair remote_executor_census "another remote endpoint executor is live"
import json, pathlib, re, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
requester = re.compile(r'run_endpoint_pair\.sh|dynamic_fp8_endpoint_driver\.py|endpoint_driver\.py|/v1/completions|curl .*30001|python\S* .*30001|ssh\S* .*30001')
allowed = re.compile(r'vllm|gemma4-b200-dynamic_fp8_candidate')
matches = [line for line in lines if requester.search(line) and not allowed.search(line)]
print(json.dumps({'request_executor_matches': matches, 'retained_server_exceptions': [line for line in lines if requester.search(line) and allowed.search(line)]}, sort_keys=True))
raise SystemExit(bool(matches))
PY
"${ssh_cmd[@]}" "sudo -n docker ps --format '{{.Names}} {{.Status}}' | awk '\$1 == \"gemma4-b200-dynamic_fp8_candidate\" && \$2 == \"Up\" { found=1 } END { exit !found }' && curl -fsS --max-time 10 http://127.0.0.1:30001/health" >"$OUT/server-health.stdout" 2>"$OUT/server-health.stderr" || repair resident_server "resident dynamic-FP8 server is not healthy"
"${ssh_cmd[@]}" "sudo -n docker logs --tail 400 gemma4-b200-dynamic_fp8_candidate" >"$OUT/server-preflight.log" 2>"$OUT/server-preflight.stderr" || repair fp8_evidence "could not retrieve resident server evidence"
grep -F 'CutlassFP8ScaledMMLinearKernel' "$OUT/server-preflight.log" >/dev/null || repair fp8_evidence "resident server logs lack CutlassFP8ScaledMMLinearKernel evidence"

phase packet_stage
"${ssh_cmd[@]}" "mkdir -p '$REMOTE'" >"$OUT/stage.stdout" 2>"$OUT/stage.stderr" || repair packet_stage "could not create c64 remote artifact root"
scp -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$PROJECT/b200_fp8_c64_driver.py" "$PRECLAIM" "$USER@$HOST:$REMOTE/" >>"$OUT/stage.stdout" 2>>"$OUT/stage.stderr" || repair packet_copy "could not stage immutable c64 packet"
"${ssh_cmd[@]}" "cd '$REMOTE' && sha256sum b200_fp8_c64_driver.py PRECLAIM_TERMINAL.json" >"$OUT/remote-packet.sha256" 2>>"$OUT/stage.stderr" || repair packet_verify "could not hash remote packet"

phase endpoint_execution
"${ssh_cmd[@]}" "cd '$REMOTE' && python3 b200_fp8_c64_driver.py --host 127.0.0.1 --port 30001 --output '$REMOTE/artifacts' --binding PRECLAIM_TERMINAL.json" >"$OUT/worker.stdout" 2>"$OUT/worker.stderr" || repair endpoint_consumer "c64 consumer exited without a valid terminal"
phase terminal_retrieval
mkdir -p "$OUT/remote-artifacts"
scp -r -i "$KEY" -o UserKnownHostsFile="$KNOWN" -o StrictHostKeyChecking=yes "$USER@$HOST:$REMOTE/artifacts/." "$OUT/remote-artifacts/" >>"$OUT/retrieve.stdout" 2>>"$OUT/retrieve.stderr" || repair terminal_retrieval "could not retrieve c64 terminal"
python3 - "$OUT/remote-artifacts/TERMINAL.json" "$OUT/remote-artifacts/SCIENCE_STARTED.json" <<'PY' || repair terminal_validation "retrieved c64 terminal is invalid"
import json, sys
t=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2]))
assert t['classification'] == 'endpoint_measurement'
assert t['complete_requests'] == 64
assert t['identity']['workload'] == 'c64/4214/358/text-only/non-reasoning'
assert s['arm'] == t['arm']
PY
python3 - "$OUT" "$PRECLAIM" <<'PY' || repair terminal_finalize "could not finalize c64 terminal"
import hashlib, json, os, pathlib, sys
out, preclaim = map(pathlib.Path, sys.argv[1:])
t = json.loads((out / 'remote-artifacts' / 'TERMINAL.json').read_text())
p = json.loads(preclaim.read_text())
log = (out / 'server-preflight.log').read_bytes()
assert b'CutlassFP8ScaledMMLinearKernel' in log
target = p['absolute_comparator']['h200_equivalent_target_seconds_per_request']
value = {
    'schema_version': 1,
    'classification': 'c64_endpoint_measurement',
    'science_consumed': True,
    'candidate': t,
    'preclaim_sha256': hashlib.sha256(preclaim.read_bytes()).hexdigest(),
    'fp8_consumption_evidence': 'resident server log contains CutlassFP8ScaledMMLinearKernel',
    'fp8_server_log_sha256': hashlib.sha256(log).hexdigest(),
    'candidate_vs_c32_fraction': t['service_seconds_per_request'] / p['absolute_comparator']['c32_service_seconds_per_request'] - 1,
    'candidate_vs_target_fraction': t['service_seconds_per_request'] / target - 1,
}
temporary = out / 'FINAL_TERMINAL.json.part'
temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
os.replace(temporary, out / 'FINAL_TERMINAL.json')
PY
phase scientific_terminal
PYTHONPATH=/root/workspace/research/factory/src python3 -m grad_research.gpu_pool --lab "$LAB" release --project gemma4_b200_dynamic_fp8_c64_saturation --bench "$BENCH" --condition maintenance >>"$OUT/release.log" 2>&1
