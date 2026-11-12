#!/usr/bin/env bash
# Keep one unattended job alive across spot preemptions. Runs on the workstation, not the VM.
#
# Every INTERVAL seconds it checks the VM. If the job is finished (DONE marker on the VM) it stops the VM and exits.
# If the VM is running but the job is not, it relaunches the job. If the VM was preempted (STOPPED) it tries to
# start it again, keeping its disk. If that fails RESTART_TRIES times, or the VM is gone, it creates a replacement
# VM from SPECS, installs the bucket key and the S3 bundle, and launches the job there.
# The job counts as finished only if it exits 0; after 3 failed runs without a preemption the watchdog stops the VM.
# The job must be idempotent and resume from S3: bootstrap.sh, run-eval.sh, run-train.sh and campaign.sh are.
# s3-sync.sh uploads results and logs every 5 minutes; full training states upload once complete.
#
# Usage: watchdog.sh NAME DONE_MARKER 'JOB COMMAND'
#   DONE_MARKER is relative to ~/gdecide on the VM. JOB runs in ~/gdecide with env.sh sourced.
# Env: MATCH (pgrep pattern that also counts as "job running", for jobs not started by the watchdog; bracket one
#      letter, e.g. '[r]un-ensemble-eval.sh', so the check does not match its own shell),
#      INTERVAL=120, RESTART_TRIES=2, SPECS (one line of `dev_training.py up` arguments per fallback, tried in order;
#      the defaults end with an Ornn on-demand B300 node, capped at ORNN_MAX_PRICE USD per GPU-hour, default 7.5).
# Ornn VMs cannot be stopped: when the job ends there the watchdog waits for one more s3-sync.sh round, then deletes it.
# Start it detached, with the dev-training secrets loaded once so an expired AWS SSO session does not stop it:
#   setsid nohup bash vm/watchdog.sh gdecide-2 logs/ensemble-finished '...' > watchdog.log 2>&1 < /dev/null &
set -uo pipefail
NAME=$1; DONE=$2; JOB=$3
MATCH=${MATCH:-}; INTERVAL=${INTERVAL:-120}; RESTART_TRIES=${RESTART_TRIES:-2}
SPECS=${SPECS:-"--region eu-west2 --platform gpu-b300-sxm --preset 8gpu-192vcpu-2768gb --disk-gib 2000
--region eu-south1 --platform gpu-b300-sxm --preset 8gpu-192vcpu-2768gb --disk-gib 2000
--region uk-south1 --platform gpu-b300-sxm --preset 8gpu-192vcpu-2768gb --disk-gib 2000
--region us-north1 --platform gpu-b300-sxm --preset 8gpu-192vcpu-2768gb --disk-gib 2000
--region me-west1 --platform gpu-b200-sxm-a --preset 8gpu-160vcpu-1792gb --disk-gib 2000
--region us-central1 --platform gpu-b200-sxm --preset 8gpu-160vcpu-1792gb --disk-gib 2000
--region us-central1 --platform gpu-h200-sxm --preset 8gpu-128vcpu-1600gb --disk-gib 2000
--region eu-west1 --platform gpu-h200-sxm --preset 8gpu-128vcpu-1600gb --disk-gib 2000
--region eu-north1 --platform gpu-h200-sxm --preset 8gpu-128vcpu-1600gb --disk-gib 2000
--provider ornn --platform nvidia_b300 --term on-demand --max-price ${ORNN_MAX_PRICE:-7.5}"}
REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel); cd "$REPO" || exit 1
export PATH=$HOME/.nebius/bin:$PATH
DT=(python3 tools/dev-training/dev_training.py)
STATE=$REPO/.agents/runtime/gdecide/watchdog-$NAME; mkdir -p "$STATE"
VM=$(cat "$STATE/vm" 2>/dev/null || echo "$NAME")
log() { echo "$(date -u +%FT%TZ) [$VM] $*"; }

# Load the secrets dev_training.py needs into this process's environment (never to disk or the log).
eval "$(python3 -I - <<'EOF'
import json, shlex, subprocess
prefixes = ('NEBIUS_', 'ORNN_', 'DEV_TRAINING_', 'TAILSCALE_DEV_TRAINING_')
out = subprocess.run(['aws', '--profile', 'gradiated-readonly', '--region', 'us-east-1', 'secretsmanager',
                      'get-secret-value', '--secret-id', 'gradiated/dev/env', '--query', 'SecretString',
                      '--output', 'text'], capture_output=True, text=True)
env = json.loads(out.stdout) if out.returncode == 0 else {}
print('\n'.join(f'export {n}={shlex.quote(env[n])}' for n in sorted(env) if n.startswith(prefixes)))
EOF
)"
[ -n "${NEBIUS_SERVICE_ACCOUNT_CREDENTIALS_B64:-}" ] || { log "could not read gradiated/dev/env; run mise run aws:login"; exit 1; }

remote() { timeout "${T:-120}" "${DT[@]}" ssh "$VM" "$@" 2>/dev/null; }
vm_state() { local out; out=$(timeout 300 "${DT[@]}" ls 2>/dev/null) || { echo UNKNOWN; return; }
  # Columns: NAME PROVIDER TERM REGION STATE ...
  awk -v n="$VM" '$1==n {print $5; f=1} END {if (!f) print "MISSING"}' <<<"$out"; }
# Stop a Nebius VM (keeping its disk); an Ornn VM cannot stop, so let s3-sync.sh upload once more and delete it.
park() { if timeout 300 "${DT[@]}" ls 2>/dev/null | awk -v n="$VM" '$1==n && $2=="ornn" {f=1} END {exit !f}'; then
    sleep 360; timeout 600 "${DT[@]}" down "$VM"; else timeout 600 "${DT[@]}" stop "$VM"; fi; }

launch() {
  local job; job=$(printf '%s' "($JOB) && touch $DONE" | base64 -w0)
  remote "mkdir -p ~/gdecide/logs && echo $job | base64 -d > ~/gdecide/logs/watchdog-job.sh && cd ~/gdecide && \
    (setsid nohup bash -c 'source ~/gdecide/env.sh; cd ~/gdecide; bash logs/watchdog-job.sh' \
      >> logs/watchdog-job.log 2>&1 < /dev/null &) && echo launched" && log "job launched"
}

wait_ssh() { for _ in $(seq 1 40); do remote true && return 0; sleep 20; done; return 1; }

provision() {  # Create a replacement VM and give it the bucket key, the code bundle and env.sh.
  local name spec
  name=$NAME-r$(date -u +%m%d%H%M)
  while read -r spec; do
    log "creating $name: $spec"
    if timeout 1500 "${DT[@]}" up "$name" $spec > "$STATE/up.log" 2>&1; then
      VM=$name; echo "$VM" > "$STATE/vm"
      wait_ssh || { log "no ssh on $VM"; return 1; }
      timeout 300 "${DT[@]}" s3 "$VM" > /dev/null 2>&1 || { log "bucket key install failed"; return 1; }
      T=900 remote "set -e; curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; export PATH=\$HOME/.local/bin:\$PATH
        command -v aws >/dev/null || uv tool install -q awscli >/dev/null 2>&1; mkdir -p ~/gdecide/logs; cd ~/gdecide
        aws s3 cp --only-show-errors s3://$DEV_TRAINING_S3_BUCKET/gradiated-decide/bundle.tgz . && tar xzf bundle.tgz
        echo 'export S3_PREFIX=s3://$DEV_TRAINING_S3_BUCKET/gradiated-decide ROOT=\$HOME/gdecide PATH=\$HOME/.local/bin:\$PATH HF_HUB_DISABLE_XET=1' > env.sh" \
        || { log "setup failed on $VM"; return 1; }
      log "replacement $VM ready"; return 0
    fi
    log "no capacity: $(tail -1 "$STATE/up.log" | cut -c1-160)"
    timeout 600 "${DT[@]}" down "$name" > /dev/null 2>&1
  done <<<"$SPECS"
  return 1
}

log "watching (done marker $DONE)"
unreachable=0; failures=0
while true; do
  case $(vm_state) in
    RUNNING)
      status=$(remote "cd ~/gdecide; if [ -f '$DONE' ]; then echo DONE; elif pgrep -f 'logs/[w]atchdog-job.sh${MATCH:+|$MATCH}' >/dev/null; then echo RUNNING; else echo IDLE; fi")
      case $status in
        DONE) log "job finished; stopping $VM (results are in S3; delete it with dev_training.py down)"
              park; exit 0;;
        RUNNING) unreachable=0;;
        IDLE) failures=$((failures + 1))
              if [ "$failures" -gt 3 ]; then log "job exited without finishing 3 times; stopping $VM, see logs/watchdog-job.log"
                park; exit 1; fi
              log "job not running; relaunching ($failures)"; launch;;
        *) unreachable=$((unreachable + 1)); log "ssh unreachable ($unreachable)"
           # Running but unreachable for 30 minutes: treat it as lost.
           [ "$unreachable" -ge $((1800 / INTERVAL)) ] && { log "giving up on $VM"; unreachable=0; provision && launch; };;
      esac;;
    STOPPED|STOPPING)
      log "preempted; restarting"; failures=0
      started=""
      for i in $(seq 1 "$RESTART_TRIES"); do
        timeout 600 "${DT[@]}" start "$VM" > "$STATE/start.log" 2>&1
        for _ in $(seq 1 30); do [ "$(vm_state)" = RUNNING ] && { started=1; break; }; sleep 20; done
        [ -n "$started" ] && break
        log "restart attempt $i failed: $(grep -m1 -o 'NotEnoughResources\|not enough[^.]*' "$STATE/start.log")"
      done
      if [ -n "$started" ]; then wait_ssh && launch
      else log "no capacity for $VM; moving to a new VM (the old one stays STOPPED)"; provision && launch; fi;;
    MISSING) log "VM is gone; moving to a new VM"; provision && launch || sleep 600;;
    *) ;;  # UNKNOWN (API error) or a transition such as STARTING: look again next round.
  esac
  sleep "$INTERVAL"
done
