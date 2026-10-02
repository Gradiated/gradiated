#!/usr/bin/env bash
# Runs the real host-proxy job on a disposable Nomad with ACLs, against two fake
# runtime allocations. Only synthetic credentials are used.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
nomad_image=hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9
image=gradiated-host-proxy-test
container="host-proxy-test-$$"
token=synthetic_runtime_token_0000000000000000
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker build -q -t "$image" - >/dev/null <<EOF
FROM $nomad_image AS nomad
FROM nginx@sha256:1881968aff6f7cdcc4b888c00a11f4ce241ad7ec957e0cb4a9e19e93a3ff87ea
RUN useradd --uid 10004 --create-home --shell /usr/sbin/nologin desmond && install -d /etc/gradiated
COPY --from=nomad /bin/nomad /usr/local/bin/nomad
EOF

docker run -d --privileged --cgroupns=host --name "$container" \
  -v "$root/jobs:/jobs:ro" --entrypoint /bin/bash "$image" -c '
    printf "\"Bearer %s\" 1;\n" '"$token"' >/etc/gradiated/runtime-proxy-auth.conf
    chown desmond:desmond /etc/gradiated/runtime-proxy-auth.conf
    chmod 600 /etc/gradiated/runtime-proxy-auth.conf
    cat >/tmp/agent.hcl <<CONFIG
acl { enabled = true }
client {
  meta { serving_ingress = "host-proxy" }
  options { "fingerprint.denylist" = "env_aws,env_azure,env_digitalocean,env_gce" }
}
plugin "raw_exec" { config { enabled = true } }
CONFIG
    exec nomad agent -dev -config /tmp/agent.hcl' >/dev/null

in_container() { docker exec -i -e NOMAD_TOKEN="${boot:-}" "$container" "$@"; }
for _ in {1..30}; do
  boot=$(in_container nomad acl bootstrap -json 2>/dev/null | sed -n 's/.*"SecretID": *"\([^"]*\)".*/\1/p') && [[ -n $boot ]] && break
  sleep 1
done
[[ -n ${boot:-} ]] || { docker logs "$container" | tail -20 >&2; exit 1; }

in_container dd if=/dev/zero of=/tmp/slow-response bs=1024 count=64 status=none

in_container sh -c 'cat >/tmp/fake-runtime.nomad.hcl' <<'EOF'
job "fake-runtime" {
  group "replicas" {
    count = 2
    update {
      max_parallel = 1
      canary = 1
      auto_promote = true
      auto_revert = true
      min_healthy_time = "2s"
      healthy_deadline = "20s"
      progress_deadline = "30s"
    }
    restart {
      attempts = 3
      interval = "1m"
      delay = "1s"
      mode = "fail"
    }
    network {
      port "runtime" {}
    }
    service {
      name     = "gradiated-runtime"
      provider = "nomad"
      port     = "runtime"
      task     = "echo"
      check {
        type = "http"
        path = "/health"
        interval = "1s"
        timeout = "1s"
        check_restart {
          limit = 1
          grace = "2s"
        }
      }
    }
    service {
      name     = "gradiated-adapters"
      provider = "nomad"
      port     = "runtime"
      task     = "echo"
    }
    task "echo" {
      driver = "raw_exec"
      shutdown_delay = "20s"
      config {
        command = "/usr/sbin/nginx"
        args    = ["-c", "${NOMAD_TASK_DIR}/nginx.conf", "-g", "daemon off;"]
      }
      template {
        destination = "local/nginx.conf"
        data        = <<-CONF
          pid {{ env "NOMAD_TASK_DIR" }}/nginx.pid;
          error_log stderr warn;
          events {}
          http {
              access_log off;
              client_body_temp_path {{ env "NOMAD_TASK_DIR" }}/body;
              proxy_temp_path {{ env "NOMAD_TASK_DIR" }}/proxy;
              fastcgi_temp_path {{ env "NOMAD_TASK_DIR" }}/fastcgi;
              uwsgi_temp_path {{ env "NOMAD_TASK_DIR" }}/uwsgi;
              scgi_temp_path {{ env "NOMAD_TASK_DIR" }}/scgi;
              server {
                  listen {{ env "NOMAD_PORT_runtime" }};
                  location = /health {
                    if (-f /tmp/unhealthy-{{ env "NOMAD_ALLOC_ID" }}) { return 503; }
                    return 200 "healthy";
                  }
                  location /slow { alias /tmp/slow-response; limit_rate 4k; }
                  location / { return 200 "{{ env "NOMAD_ALLOC_ID" }} $request_uri auth=[$http_authorization]\n"; }
              }
          }
        CONF
      }
    }
  }
}
EOF
in_container nomad job run -detach /jobs/host-proxy.nomad.hcl >/dev/null
in_container nomad job run /tmp/fake-runtime.nomad.hcl >/dev/null

request() { in_container curl -s --max-time 3 -o /dev/stdout -w ' %{http_code}' ${2:+-H "Authorization: Bearer $2"} "http://127.0.0.1:8888$1"; }
read -ra allocs <<<"$(in_container nomad job allocs -json fake-runtime | grep -o '"ID": *"[0-9a-f-]\{36\}"' | grep -o '[0-9a-f-]\{36\}' | tr '\n' ' ')"
[[ ${#allocs[@]} == 2 ]] || { echo "expected two runtime allocations, got ${#allocs[@]}" >&2; exit 1; }

for _ in {1..60}; do
  [[ $(request "/alloc/${allocs[1]}/ready" "$token") == *" 200" ]] && break
  sleep 1
done

fail() {
  echo "$1" >&2
  in_container nomad job allocs fake-runtime >&2 || true
  proxy_alloc=$(in_container nomad job allocs -json host-proxy | grep -o '"ID": *"[0-9a-f-]\{36\}"' | grep -o '[0-9a-f-]\{36\}' | head -1)
  in_container nomad alloc status "$proxy_alloc" >&2 || true
  in_container nomad alloc logs -stderr "$proxy_alloc" >&2 || true
  exit 1
}
[[ $(request /healthz) == "ok"*" 200" ]] || fail "the unauthenticated health check did not answer"
[[ $(request "/alloc/${allocs[0]}/v1/chat/completions") == *" 401" ]] || fail "missing token was not rejected"
[[ $(request "/alloc/${allocs[0]}/v1/chat/completions" wrong-token) == *" 401" ]] || fail "wrong token was not rejected"
for alloc in "${allocs[@]}"; do
  response=$(request "/alloc/$alloc/v1/chat/completions?stream=true" "$token")
  [[ $response == "$alloc /v1/chat/completions?stream=true auth=[]"*" 200" ]] || fail "allocation $alloc was not routed with its prefix stripped: $response"
  response=$(request "/alloc/$alloc/internal/adapters" "$token")
  [[ $response == "$alloc /internal/adapters auth=[]"*" 200" ]] || fail "allocation $alloc control route was not preserved: $response"
  for operation in load unload; do
    [[ $(request "/alloc/$alloc/v1/${operation}_lora_adapter" "$token") == *" 404" ]] || fail "raw adapter admin API was exposed"
  done
done
[[ $(request "/alloc/00000000-0000-4000-8000-000000000000/v1/models" "$token") == *" 404" ]] || fail "an unknown allocation was not rejected"

if [[ ${1:-} == --proxy-drain ]]; then
  in_container dd if=/dev/zero of=/tmp/slow-response bs=1024 count=320 status=none
  in_container curl --fail --silent --show-error --max-time 120 \
    -H "Authorization: Bearer $token" \
    "http://127.0.0.1:8888/alloc/${allocs[0]}/slow" -o /tmp/proxy-drain-response &
  slow_request=$!
  for _ in {1..10}; do
    in_container test -s /tmp/proxy-drain-response && break
    sleep 1
  done
  in_container test -s /tmp/proxy-drain-response || fail "slow response did not start"

  in_container nomad job stop -detach host-proxy >/dev/null
  withdrawn=false
  for _ in {1..20}; do
    if [[ $(request "/alloc/${allocs[0]}/health" "$token") == *" 503" ]]; then
      withdrawn=true
      break
    fi
    sleep 1
  done
  $withdrawn || fail "proxy readiness did not withdraw before the drain budget"
  wait "$slow_request" || fail "proxy shutdown interrupted an in-flight response"
  bytes=$(in_container wc -c /tmp/proxy-drain-response | awk '{print $1}')
  [[ $bytes == 327680 ]] || fail "proxy shutdown truncated the response: $bytes bytes"
  echo 'Proxy readiness withdrew and an 80-second response survived shutdown'
  exit 0
fi

if [[ ${1:-} == --sdk-gate ]]; then
  TEST_CONTAINER="$container" TEST_NOMAD_TOKEN="$boot" node "$root/tests/sdk-gate.mjs"
  exit 0
fi

if [[ ${1:-} == --recovery ]]; then
  proxy_alloc=$(in_container nomad job allocs -json host-proxy | jq -r '.[] | select(.ClientStatus == "running") | .ID')
  for fault in crash hang crash crash crash; do
    restarts_before=$(in_container nomad alloc status -json "$proxy_alloc" | jq '.TaskStates.nginx.Restarts')
    if [[ $fault == crash ]]; then
      in_container nomad alloc signal -s SIGKILL -task nginx "$proxy_alloc" >/dev/null
    else
      in_container sh -s <<'SH'
for status in /proc/[0-9]*/status; do
  if grep -q '^Name:.*nginx' "$status" && grep -q '^Uid:[[:space:]]*10004' "$status"; then
    pid=${status#/proc/}
    kill -STOP "${pid%/status}"
  fi
done
SH
    fi
    recovered=false
    for _ in {1..90}; do
      restarts=$(in_container nomad alloc status -json "$proxy_alloc" | jq '.TaskStates.nginx.Restarts')
      if ((restarts > restarts_before)) && [[ $(request "/alloc/${allocs[0]}/health" "$token" || true) == *" 200" ]]; then
        recovered=true
        break
      fi
      sleep 1
    done
    $recovered || fail "host proxy did not recover from $fault"
    echo "Host proxy recovered from $fault and restored the allocation route"
  done

  restart_started=$SECONDS
  before=$(in_container nomad alloc status -json "${allocs[0]}" | jq '.TaskStates.echo')
  in_container touch "/tmp/unhealthy-${allocs[0]}"
  health_restarted=false
  for _ in {1..15}; do
    [[ $(request "/alloc/${allocs[1]}/health" "$token") == *" 200" ]] || fail "healthy replica stopped serving during health-check recovery"
    state=$(in_container nomad alloc status -json "${allocs[0]}" | jq '.TaskStates.echo')
    if jq -e --argjson before "$before" '.Restarts > $before.Restarts' <<<"$state" >/dev/null; then
      in_container rm -f "/tmp/unhealthy-${allocs[0]}"
      if jq -e --argjson before "$before" '.State == "running" and .StartedAt != $before.StartedAt' <<<"$state" >/dev/null &&
        [[ $(request "/alloc/${allocs[0]}/health" "$token") == *" 200" ]]; then
        health_restarted=true
        break
      fi
    fi
    sleep 1
  done
  $health_restarted || fail "health-check restart waited for allocation shutdown_delay"
  ((SECONDS - restart_started < 20)) || fail "health-check restart consumed the drain delay"
  echo 'Health-check failure restarted the task without allocation drain delay; the peer stayed available'

  before=$(in_container nomad alloc status -json "${allocs[0]}" | jq '.TaskStates.echo')
  in_container nomad alloc signal -s SIGKILL -task echo "${allocs[0]}" >/dev/null
  restarted=false
  for _ in {1..60}; do
    [[ $(request "/alloc/${allocs[1]}/health" "$token") == *" 200" ]] || fail "healthy replica stopped serving during task recovery"
    state=$(in_container nomad alloc status -json "${allocs[0]}" | jq '.TaskStates.echo')
    if jq -e --argjson before "$before" '.Restarts > $before.Restarts and .State == "running" and .StartedAt != $before.StartedAt' <<<"$state" >/dev/null &&
      [[ $(request "/alloc/${allocs[0]}/health" "$token") == *" 200" ]]; then
      restarted=true
      break
    fi
    sleep 1
  done
  $restarted || fail "Nomad did not restart the crashed task"
  echo 'Crashed task restarted; the other replica stayed available'

  in_container sh -c 'cp /tmp/fake-runtime.nomad.hcl /tmp/good.nomad.hcl; sed -i "s|command = \"/usr/sbin/nginx\"|command = \"/bin/false\"|" /tmp/fake-runtime.nomad.hcl'
  registration=$(in_container nomad job run -detach /tmp/fake-runtime.nomad.hcl)
  evaluation=$(awk '/^Evaluation ID:/ {print $3}' <<<"$registration")
  [[ $evaluation =~ ^[0-9a-f-]{36}$ ]] || fail "job registration did not return its evaluation ID"
  reverted=false
  for _ in {1..90}; do
    for alloc in "${allocs[@]}"; do
      [[ $(request "/alloc/$alloc/health" "$token") == *" 200" ]] || fail "bad canary interrupted a healthy replica"
    done
    job=$(in_container nomad job inspect fake-runtime)
    if jq -e '(.Job // .) | .Version >= 2 and .TaskGroups[0].Tasks[0].Config.command == "/usr/sbin/nginx"' <<<"$job" >/dev/null; then
      reverted=true
      break
    fi
    sleep 1
  done
  $reverted || fail "bad canary did not automatically revert"
  NOMAD_TOKEN="$boot" NOMAD_TEST_CONTAINER="$container" node --input-type=module - "$root/../../../tools/nomad/wait-deployments.mjs" "$evaluation" <<'JS'
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
const { waitForEvaluation } = await import(pathToFileURL(process.argv[2]));
await assert.rejects(waitForEvaluation(process.argv[3], "", {
  signal: AbortSignal.timeout(30_000),
  get: async (path) => JSON.parse(execFileSync("docker", ["exec", "-e", "NOMAD_TOKEN", process.env.NOMAD_TEST_CONTAINER, "nomad", "operator", "api", path], { encoding: "utf8" })),
}), /Deployment .* is failed/);
JS
  echo 'Bad canary reverted without interrupting either healthy replica; deployment gate rejected it'
  NOMAD_TOKEN="$boot" NOMAD_TEST_CONTAINER="$container" node --input-type=module - "$root/../../../tools/nomad/submit-jobs.mjs" <<'JS'
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
const { submitJob } = await import(pathToFileURL(process.argv[2]));
const cli = (args, input) => JSON.parse(execFileSync("docker", ["exec", "-i", "-e", "NOMAD_TOKEN", process.env.NOMAD_TEST_CONTAINER, "nomad", ...args], { input, encoding: "utf8" }));
const get = (path) => cli(["operator", "api", "-X", "GET", path]);
const job = cli(["job", "run", "-output", "/tmp/good.nomad.hcl"]).Job;
const result = await submitJob(job, {
  get,
  post: (path, body) => {
    assert.notEqual(path, "/v1/jobs");
    return cli(["operator", "api", "-X", "POST", path], JSON.stringify(body));
  },
  signal: AbortSignal.timeout(30_000),
});
if (result.deployment) {
  assert.notEqual(get(`/v1/deployment/${result.deployment}`).Status, "failed");
  const { waitForDeployment } = await import(new URL("./wait-deployments.mjs", pathToFileURL(process.argv[2])));
  await waitForDeployment(result.deployment, { get, signal: AbortSignal.timeout(60_000) });
}
JS
  echo 'A Git revert matching the restored job did not follow the failed canary deployment'

  in_container sh -s <<'SH'
sed -e 's/auto_promote = true/auto_promote = false/' \
    -e 's/canary = 1/canary = 2/' \
    -e '/driver = "raw_exec"/a\      env { RELEASE = "next" }' \
    /tmp/good.nomad.hcl >/tmp/next.nomad.hcl
SH
  in_container nomad job run -detach /tmp/next.nomad.hcl >/dev/null
  canaries='[]'
  for _ in {1..60}; do
    for alloc in "${allocs[@]}"; do
      [[ $(request "/alloc/$alloc/health" "$token") == *" 200" ]] || fail "healthy canary warmup interrupted the old release"
    done
    canaries=$(in_container nomad job allocs -json fake-runtime | jq '[.[] | select(.DesiredStatus == "run" and .DeploymentStatus.Canary == true)]')
    jq -e 'length == 2 and all(.[]; .DeploymentStatus.Healthy == true)' <<<"$canaries" >/dev/null && break
    sleep 1
  done
  jq -e 'length == 2 and all(.[]; .DeploymentStatus.Healthy == true)' <<<"$canaries" >/dev/null || fail "replacement set did not become healthy"
  read -ra canary_ids <<<"$(jq -r 'map(.ID) | join(" ")' <<<"$canaries")"
  for alloc in "${canary_ids[@]}"; do
    routed=false
    for _ in {1..30}; do
      if [[ $(request "/alloc/$alloc/health" "$token") == *" 200" ]]; then
        routed=true
        break
      fi
      sleep 1
    done
    $routed || fail "a healthy canary did not get an ingress route"
  done
  deployment=$(in_container nomad job deployments -json fake-runtime | jq -r 'max_by(.CreateIndex).ID')
  NOMAD_TOKEN="$boot" NOMAD_TEST_CONTAINER="$container" node --input-type=module - "$root/../../../tools/nomad/submit-jobs.mjs" "$deployment" <<'JS'
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
const { submitJob } = await import(pathToFileURL(process.argv[2]));
const cli = (args, input) => JSON.parse(execFileSync("docker", ["exec", "-i", "-e", "NOMAD_TOKEN", process.env.NOMAD_TEST_CONTAINER, "nomad", ...args], { input, encoding: "utf8" }));
const get = (path) => cli(["operator", "api", "-X", "GET", path]);
const post = (path, body) => cli(["operator", "api", "-X", "POST", path], JSON.stringify(body));
const job = cli(["job", "run", "-output", "/tmp/next.nomad.hcl"]).Job;
const before = get("/v1/job/fake-runtime").Version;
const result = await submitJob(job, { get, post, signal: AbortSignal.timeout(30_000) });
assert.deepEqual(result, { deployment: process.argv[3] });
assert.equal(get("/v1/job/fake-runtime").Version, before);
assert.equal(get(`/v1/deployment/${process.argv[3]}`).Status, "running");
job.ID = job.Name = "submission-fixture";
job.TaskGroups[0].Count = 0;
job.TaskGroups[0].Update.Canary = 0;
const created = await submitJob(job, { get, post, signal: AbortSignal.timeout(30_000) });
assert.match(created.evaluation, /^[0-9a-f-]{36}$/);
JS
  echo 'Unchanged submission preserved the active canaries and job version; new job submission returned its evaluation'
  in_container nomad deployment promote "$deployment" >/dev/null
  promoted=false
  for _ in {1..60}; do
    for alloc in "${canary_ids[@]}"; do
      [[ $(request "/alloc/$alloc/health" "$token") == *" 200" ]] || fail "promotion interrupted a replacement route"
    done
    if in_container nomad deployment status -json "$deployment" | jq -e '.Status == "successful"' >/dev/null; then
      promoted=true
      break
    fi
    sleep 1
  done
  $promoted || fail "healthy replacement set did not promote"
  promoted_allocations=$(in_container nomad job allocs -json fake-runtime | jq '[.[] | select(.DesiredStatus == "run" and .ClientStatus == "running")]')
  jq -e 'length == 2 and all(.[]; .DeploymentStatus.Canary == false)' <<<"$promoted_allocations" >/dev/null || fail "promotion did not clear Canary on the replacement set"
  read -ra allocs <<<"$(jq -r 'map(.ID) | join(" ")' <<<"$promoted_allocations")"
  echo 'Both replacement replicas warmed before promotion; promoted allocations cleared their Canary flag'
fi

in_container curl --fail --silent --show-error --max-time 45 \
  -H "Authorization: Bearer $token" \
  "http://127.0.0.1:8888/alloc/${allocs[0]}/slow" -o /tmp/draining-response &
slow_request=$!
for _ in {1..10}; do
  in_container test -s /tmp/draining-response && break
  sleep 1
done
in_container test -s /tmp/draining-response || fail "slow response did not start"
in_container nomad alloc stop -detach "${allocs[0]}" >/dev/null
if [[ ${1:-} == --recovery ]]; then
  NOMAD_TOKEN="$boot" NOMAD_TEST_CONTAINER="$container" node --input-type=module - "$root/../../../tools/nomad/submit-jobs.mjs" <<'JS'
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
const { submitJob } = await import(pathToFileURL(process.argv[2]));
const cli = (args, input) => JSON.parse(execFileSync("docker", ["exec", "-i", "-e", "NOMAD_TOKEN", process.env.NOMAD_TEST_CONTAINER, "nomad", ...args], { input, encoding: "utf8" }));
const get = (path) => cli(["operator", "api", "-X", "GET", path]);
const job = cli(["job", "run", "-output", "/tmp/next.nomad.hcl"]).Job;
job.ID = job.Name = "drain-probe";
job.TaskGroups[0].Count = 0;
job.TaskGroups[0].Update.Canary = 0;
const controller = new AbortController();
await assert.rejects(submitJob(job, {
  get,
  post: (path, body) => {
    assert.notEqual(path, "/v1/jobs", "registration must wait until draining processes release memory");
    return cli(["operator", "api", "-X", "POST", path], JSON.stringify(body));
  },
  signal: controller.signal,
  pause: async () => controller.abort(),
}), /deadline/);
JS
  echo 'A new job waited while another allocation drained instead of reclaiming its GPU resources'
fi
consecutive_removed=0
for _ in {1..60}; do
  if [[ $(request "/alloc/${allocs[0]}/v1/models" "$token") == *" 404" ]]; then
    consecutive_removed=$((consecutive_removed + 1))
  else
    consecutive_removed=0
  fi
  ((consecutive_removed >= 3)) && break
  sleep 1
done
((consecutive_removed >= 3)) || fail "a stopped allocation kept its route"
wait "$slow_request" || fail "an in-flight response was interrupted while draining"
response_bytes=$(in_container wc -c </dev/null /tmp/draining-response | awk '{print $1}')
[[ $response_bytes == 65536 ]] || fail "draining response was truncated: $response_bytes bytes"
echo 'In-flight response completed while its allocation was deregistered and stopped'

replacement=""
consecutive_ready=0
for _ in {1..60}; do
  candidate=$(in_container nomad job allocs -json fake-runtime | jq -r --arg old "${allocs[0]}" --arg other "${allocs[1]}" '.[] | select(.ClientStatus == "running" and .DesiredStatus == "run" and .ID != $old and .ID != $other) | .ID' | head -1)
  [[ $candidate == "$replacement" ]] || consecutive_ready=0
  replacement=$candidate
  response=$(request "/alloc/$replacement/health" "$token" || true)
  if [[ -n $replacement && $response == *" 200" ]]; then
    consecutive_ready=$((consecutive_ready + 1))
  else
    consecutive_ready=0
  fi
  # Nginx briefly serves both old and new routes while reload workers overlap.
  ((consecutive_ready >= 3)) && break
  sleep 1
done
((consecutive_ready >= 3)) || fail "stopped allocation was not replaced and routed: $replacement, $response"
[[ $(request "/alloc/${allocs[1]}/health" "$token") == *" 200" ]] || fail "surviving replica lost its route"
echo 'Host proxy authentication, allocation routing, removal and replacement passed'
