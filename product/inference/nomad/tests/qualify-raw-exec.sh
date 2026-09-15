#!/usr/bin/env bash
# Run as root inside the selected pod: timeout --kill-after=15s 240s bash SCRIPT
# Only GPU inventory is read. Existing serving processes are not modified.
set -euo pipefail
source_root=${1:?Pass the runtime-launcher source directory}
source_root=$(realpath "$source_root")
work=$(mktemp -d /tmp/gradiated-nomad-live.XXXXXX)
account="nomad-test-$$"
uid=''
cleanup() {
  if [[ -n "$uid" ]]; then
    pkill -TERM -u "$uid" 2>/dev/null || true
    sleep 1
    pkill -KILL -u "$uid" 2>/dev/null || true
    userdel "$account" 2>/dev/null || true
  fi
  rm -rf "$work"
}
trap cleanup EXIT
trap 'echo "Probe watchdog expired"; exit 143' TERM
for port in 24646 24647 24648; do
  if ss -lnt | grep -q ":$port "; then
    printf 'Probe port %s is already in use\n' "$port" >&2
    exit 1
  fi
done
cd "$work"
g++ -std=c++20 -Wall -Wextra -Werror -I "$source_root" \
  "$source_root/supervise.cpp" "$source_root/tests/supervise-main.cpp" -o "$work/supervise"
curl -fsS --max-time 40 -o nomad.zip https://releases.hashicorp.com/nomad/2.0.6/nomad_2.0.6_linux_amd64.zip
printf '%s  nomad.zip\n' c6da734081a41d51cadf15ec880d5eab0313093a29d2ee0984ca5ae1cdf867ec | sha256sum -c -
unzip -q nomad.zip nomad
mkdir plugins
curl -fsS --max-time 40 -o nvidia.zip https://releases.hashicorp.com/nomad-device-nvidia/1.1.0/nomad-device-nvidia_1.1.0_linux_amd64.zip
printf '%s  nvidia.zip\n' 4c2ab571192ae465f1fbe09c47e5e6d1fcc8c1c7a6458b1ef563a9aec618d83d | sha256sum -c -
unzip -q nvidia.zip -d plugins
useradd --system --no-create-home --shell /usr/sbin/nologin "$account"
uid=$(id -u "$account")
cat >config.hcl <<HCL
bind_addr = "127.0.0.1"
plugin_dir = "$work/plugins"
ports { http = 24646 rpc = 24647 serf = 24648 }
server { num_schedulers = 1 }
client { max_kill_timeout = "60s" }
plugin "raw_exec" { config { enabled = true } }
plugin "nomad-device-nvidia" { config { enabled = true } }
HCL
cat >workload.sh <<'WORKLOAD'
#!/bin/bash
set -eu
printf '%s\n' "${NVIDIA_VISIBLE_DEVICES:?Missing assigned GPU IDs}" > "$1/gpus-$NOMAD_ALLOC_INDEX"
sleep 600 &
printf '%s\n' "$!" > "$1/child-$NOMAD_ALLOC_INDEX"
setsid bash -c 'trap "" TERM; exec sleep 600' &
printf '%s\n' "$!" > "$1/detached-$NOMAD_ALLOC_INDEX"
wait
WORKLOAD
chown -R "$uid:$uid" "$work"
runuser -u "$account" -- "$work/nomad" agent -dev -config "$work/config.hcl" -data-dir "$work/data" >agent.log 2>&1 &
export NOMAD_ADDR=http://127.0.0.1:24646
node_ready=false
for _ in $(seq 1 45); do
  if curl -fsS --max-time 2 "$NOMAD_ADDR/v1/nodes" >nodes.json && jq -e 'length == 1 and .[0].Status == "ready"' nodes.json >/dev/null; then
    node_ready=true
    break
  fi
  sleep 1
done
if [[ "$node_ready" != true ]]; then
  printf 'Nomad node did not become ready within 45 attempts\n' >&2
  tail -50 agent.log >&2
  exit 1
fi
node=$(jq -er '.[0].ID' nodes.json)
curl -fsS --max-time 3 "$NOMAD_ADDR/v1/node/$node" | jq '{devices:[.NodeResources.Devices[]|{Name,ids:[.Instances[].ID]}]}'
cat >job.hcl <<HCL
job "gpu-bookkeeping-probe" {
  datacenters = ["dc1"]
  group "replicas" {
    count = 2
    restart {
      attempts = 0
      mode = "fail"
    }
    reschedule {
      attempts = 0
      unlimited = false
    }
    task "probe" {
      driver = "raw_exec"
      kill_timeout = "60s"
      config {
        command = "$work/supervise"
        args = ["/bin/bash", "$work/workload.sh", "$work"]
      }
      resources {
        cpu = 100
        memory = 64
        device "nvidia/gpu" { count = 2 }
      }
    }
  }
}
HCL
"$work/nomad" job run -detach job.hcl
for _ in $(seq 1 30); do
  [[ -f gpus-0 && -f gpus-1 ]] && break
  sleep 1
done
if [[ ! -f gpus-0 || ! -f gpus-1 ]]; then
  curl -fsS --max-time 3 "$NOMAD_ADDR/v1/job/gpu-bookkeeping-probe/allocations" | jq '[.[]|{ClientStatus,TaskStates}]'
  exit 1
fi
cat gpus-0 gpus-1 | tr ',' '\n' | sort >assigned.txt
[[ "$(wc -l <assigned.txt)" -eq 4 && "$(sort -u assigned.txt | wc -l)" -eq 4 ]]
printf 'PASS: two disjoint pairs of assigned GPU UUIDs\n'
printf "Requesting job stop at %s\n" "$(date -u +%FT%TZ)"
curl -fsS --max-time 10 -X DELETE "$NOMAD_ADDR/v1/job/gpu-bookkeeping-probe?purge=true" >/dev/null
printf "Job stop accepted at %s\n" "$(date -u +%FT%TZ)"
for _ in $(seq 1 65); do
  survivors=0
  for pidfile in child-* detached-*; do
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then survivors=$((survivors + 1)); fi
  done
  [[ "$survivors" -eq 0 ]] && break
  sleep 1
done
leaks=0
for pidfile in child-* detached-*; do
  pid=$(cat "$pidfile")
  if kill -0 "$pid" 2>/dev/null; then
    printf 'FAIL: surviving %s process\n' "${pidfile%-*}"
    leaks=$((leaks + 1))
  fi
done
printf 'cleanup_survivors=%s\n' "$leaks"
[[ "$leaks" -eq 0 ]]
