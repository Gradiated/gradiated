#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run_native_abba.sh IMAGE MANIFEST OUTPUT_PREFIX [CANDIDATE_ENV=VALUE ...]

Run clean-container A-B-B-A native-runtime benchmarks while temporarily stopping the
production Desmond service. Environment assignments after OUTPUT_PREFIX are applied only
to the B candidate. Common runtime settings can be supplied through GRADIATED_ABBA_COMMON_ENV
as a newline-delimited list of NAME=VALUE assignments.

Optional environment:
  GRADIATED_ABBA_SERVICE          systemd service (default: desmond.service)
  GRADIATED_ABBA_ENV_FILE         Docker/runtime env file
  GRADIATED_ABBA_BENCHMARK        native_open_loop.py path
  GRADIATED_ABBA_CONTAINER        temporary container name
  GRADIATED_ABBA_READY_TIMEOUT_S  readiness timeout (default: 240)
EOF
}

if (( $# < 3 )); then
  usage >&2
  exit 2
fi

image=$1
manifest=$2
output_prefix=$3
shift 3
candidate_environment=("$@")

service=${GRADIATED_ABBA_SERVICE:-desmond.service}
environment_file=${GRADIATED_ABBA_ENV_FILE:-/etc/gradiated/desmond.env}
benchmark=${GRADIATED_ABBA_BENCHMARK:-/tmp/gradiated-ragged-v22/product/inference/benchmarks/native_open_loop.py}
container=${GRADIATED_ABBA_CONTAINER:-desmond-native-abba}
ready_timeout=${GRADIATED_ABBA_READY_TIMEOUT_S:-240}

if [[ ! -f $manifest || ! -f $benchmark || ! $ready_timeout =~ ^[1-9][0-9]*$ ]]; then
  echo "manifest, benchmark, or readiness timeout is invalid" >&2
  exit 2
fi
for assignment in "${candidate_environment[@]}"; do
  if [[ ! $assignment =~ ^[A-Za-z_][A-Za-z0-9_]*=.*$ ]]; then
    echo "invalid candidate environment assignment: $assignment" >&2
    exit 2
  fi
done

common_environment=()
if [[ -n ${GRADIATED_ABBA_COMMON_ENV:-} ]]; then
  while IFS= read -r assignment; do
    [[ -z $assignment ]] && continue
    if [[ ! $assignment =~ ^[A-Za-z_][A-Za-z0-9_]*=.*$ ]]; then
      echo "invalid common environment assignment: $assignment" >&2
      exit 2
    fi
    common_environment+=("$assignment")
  done <<<"$GRADIATED_ABBA_COMMON_ENV"
fi

docker_environment_args=()
for assignment in "${common_environment[@]}"; do
  docker_environment_args+=(--env "$assignment")
done

production_was_active=false
if sudo systemctl is-active --quiet "$service"; then
  production_was_active=true
fi

cleanup() {
  sudo docker rm -f "$container" >/dev/null 2>&1 || true
  if [[ $production_was_active == true ]]; then
    sudo systemctl start "$service"
  fi
}
trap cleanup EXIT INT TERM

sudo systemctl stop "$service"
sudo docker rm -f "$container" >/dev/null 2>&1 || true

wait_ready() {
  local deadline=$((SECONDS + ready_timeout))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 3 http://127.0.0.1:9090/health/ready >/dev/null; then
      return 0
    fi
    if ! sudo docker inspect "$container" >/dev/null 2>&1; then
      echo "benchmark container exited before becoming ready" >&2
      return 1
    fi
    sleep 2
  done
  echo "benchmark container did not become ready within ${ready_timeout}s" >&2
  sudo docker logs --tail 100 "$container" >&2 || true
  return 1
}

run_variant() {
  local label=$1
  local variant=$2
  local output="${output_prefix}-${label}-${variant}.json"
  local log="${output_prefix}-${label}-${variant}.log"
  local variant_environment_args=()
  if [[ $variant == candidate ]]; then
    local assignment
    for assignment in "${candidate_environment[@]}"; do
      variant_environment_args+=(--env "$assignment")
    done
  fi

  echo "START ${label} ${variant}"
  sudo docker run --detach --name "$container" \
    --network host \
    --gpus all \
    --ipc host \
    --shm-size 32g \
    --cap-add SYS_NICE \
    --ulimit memlock=-1:-1 \
    --env-file "$environment_file" \
    --volume /var/lib/gradiated/huggingface:/var/lib/gradiated/huggingface \
    "${docker_environment_args[@]}" \
    "${variant_environment_args[@]}" \
    "$image" >/dev/null
  wait_ready
  sudo bash -c 'set -a; . "$1"; set +a; shift; exec "$@"' \
    benchmark-with-secrets "$environment_file" \
    python3 "$benchmark" --manifest "$manifest" --output "$output" >"$log"
  sudo docker rm -f "$container" >/dev/null
  echo "DONE ${label} ${variant} ${output}"
}

run_variant a1 control
run_variant b1 candidate
run_variant b2 candidate
run_variant a2 control
