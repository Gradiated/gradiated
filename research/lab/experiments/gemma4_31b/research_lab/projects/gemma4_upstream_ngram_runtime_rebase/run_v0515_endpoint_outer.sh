#!/usr/bin/env bash
set -Eeuo pipefail
p=$(cd "$(dirname "$0")" && pwd); lab=/root/workspace/research/lab/experiments/gemma4_31b/research_lab; f=/root/workspace/research/factory/src; pr=gemma4_upstream_ngram_runtime_rebase; b=h200-ngram-verifier-e00kcm9nfhwt7e7gbc; r=/home/glmrunner/gemma4-upstream-ngram-v0515; k=/root/.config/nebius/glm-campaign/ssh_ed25519; kh=/root/.config/nebius/glm-campaign/known_hosts; a="$p/artifacts/v0515-endpoint-$(date -u +%Y%m%dt%H%M%Sz)"; mkdir -p "$a"
h=$(python3 - <<'PY'
import json,sys
sys.path.insert(0,'/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius')
from placement_control import extract_public_ipv4,get_instance
x=json.load(open('/root/workspace/research/lab/experiments/gemma4_31b/research_lab/runtime/gpus.json'))['benches']['h200-ngram-verifier-e00kcm9nfhwt7e7gbc']
print(extract_public_ipv4(get_instance(x['resource']['instance_id'])))
PY
)
s() { ssh -i "$k" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$kh" "glmrunner@$h" "$@"; }
( while true; do PYTHONPATH="$f" python3 -m grad_research.gpu_pool --lab "$lab" heartbeat --project "$pr" >>"$a/heartbeats.log" 2>&1 || true; sleep 45; done ) & hp=$!; trap 'kill $hp 2>/dev/null || true' EXIT
tar -cf "$a/PACKET.tar" -C "$p" remote_runtime_discriminator.py remote_v0515_endpoint.py remote_v0515_endpoint_worker.sh -C "$p/artifacts/candidate-v0.5.15" CANDIDATE_RUNTIME.json inputs
q=$(sha256sum "$a/PACKET.tar"|awk '{print $1}')
scp -p -i "$k" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$kh" "$a/PACKET.tar" "glmrunner@$h:$r/ENDPOINT_PACKET.tar"
s "cd '$r' && test \"\$(sha256sum ENDPOINT_PACKET.tar|awk '{print \$1}')\" = '$q' && rm -rf endpoint-stage && mkdir endpoint-stage && tar -xf ENDPOINT_PACKET.tar -C endpoint-stage && chmod 0555 endpoint-stage/remote_v0515_endpoint_worker.sh && ./detached-owner start --state ENDPOINT_OWNER.json --log ENDPOINT_OWNER.log --cwd '$r/endpoint-stage' --unit-manager remote-shell -- env UPSTREAM_REBASE_ROOT='$r/endpoint-stage' ./remote_v0515_endpoint_worker.sh" >"$a/guest-launch.stdout" 2>"$a/guest-launch.stderr"
while [[ $(date -u +%Y-%m-%dT%H:%M:%SZ) < 2026-07-25T07:00:00Z ]]; do
 sleep 20; z=$(s "cd '$r' && ./detached-owner status --state ENDPOINT_OWNER.json 2>/dev/null; test -f endpoint-stage/out-endpoint/ENDPOINT_TERMINAL.json && echo ENDPOINT || true; test -f endpoint-stage/out-endpoint/ATTEMPT_TERMINAL.json && echo ATTEMPT || true" || true); printf '%s\n' "$z" >"$a/remote-state.log"
 if grep -qx ENDPOINT <<<"$z"; then s "cd '$r' && tar -czf endpoint-compact.tar.gz ENDPOINT_OWNER.json ENDPOINT_OWNER.log endpoint-stage/out-endpoint && sha256sum endpoint-compact.tar.gz > endpoint-compact.tar.gz.sha256"; scp -p -i "$k" -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$kh" "glmrunner@$h:$r/endpoint-compact.tar.gz" "$a/"; mkdir -p "$a/retrieved"; tar -xzf "$a/endpoint-compact.tar.gz" -C "$a/retrieved"; cp "$p/BENCH_ENDPOINT_HANDOFF.json" "$a/BENCH_CONTENTS.json"; PYTHONPATH="$f" python3 -m grad_research.gpu_pool --lab "$lab" release --project "$pr" --condition maintenance --contents "$a/BENCH_CONTENTS.json" >"$a/release.stdout" 2>"$a/release.stderr"; exit 0; fi
 if grep -qx ATTEMPT <<<"$z"; then /root/workspace/research/factory/tools/repair-handshake ready --root "$a" --deadline 2026-07-25T06:55:00Z --failure-kind endpoint_consumer --diagnostic remote_attempt --retry-scope endpoint_only || true; /root/workspace/research/factory/tools/repair-handshake wait --root "$a" || exit 2; fi
done
exit 3
