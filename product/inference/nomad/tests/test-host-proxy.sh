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
      attempts = 1
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
      check {
        type = "http"
        path = "/health"
        interval = "1s"
        timeout = "1s"
      }
    }
    task "echo" {
      driver = "raw_exec"
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

request() { in_container curl -s -o /dev/stdout -w ' %{http_code}' ${2:+-H "Authorization: Bearer $2"} "http://127.0.0.1:8888$1"; }
read -ra allocs <<<"$(in_container nomad job allocs -json fake-runtime | grep -o '"ID": *"[0-9a-f-]\{36\}"' | grep -o '[0-9a-f-]\{36\}' | tr '\n' ' ')"
[[ ${#allocs[@]} == 2 ]] || { echo "expected two runtime allocations, got ${#allocs[@]}" >&2; exit 1; }

for _ in {1..60}; do
  [[ $(request "/alloc/${allocs[1]}/ready" "$token") == *" 200" ]] && break
  sleep 1
done

fail() {
  echo "$1" >&2
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
done
[[ $(request "/alloc/00000000-0000-4000-8000-000000000000/v1/models" "$token") == *" 404" ]] || fail "an unknown allocation was not rejected"

if [[ ${1:-} == --recovery ]]; then
  in_container nomad alloc signal -s SIGKILL -task echo "${allocs[0]}" >/dev/null
  restarted=false
  for _ in {1..60}; do
    [[ $(request "/alloc/${allocs[1]}/health" "$token") == *" 200" ]] || fail "healthy replica stopped serving during task recovery"
    restarts=$(in_container nomad alloc status -json "${allocs[0]}" | jq '.TaskStates.echo.Restarts')
    if ((restarts >= 1)) && [[ $(request "/alloc/${allocs[0]}/health" "$token") == *" 200" ]]; then
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
fi

in_container nomad alloc stop -detach "${allocs[0]}" >/dev/null
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

replacement=""
for _ in {1..60}; do
  replacement=$(in_container nomad job allocs -json fake-runtime | jq -r --arg old "${allocs[0]}" --arg other "${allocs[1]}" '.[] | select(.ClientStatus == "running" and .DesiredStatus == "run" and .ID != $old and .ID != $other) | .ID' | head -1)
  if [[ -n $replacement ]] && [[ $(request "/alloc/$replacement/health" "$token") == *" 200" ]]; then
    break
  fi
  sleep 1
done
[[ -n $replacement ]] && [[ $(request "/alloc/$replacement/health" "$token") == *" 200" ]] || fail "stopped allocation was not replaced and routed"
[[ $(request "/alloc/${allocs[1]}/health" "$token") == *" 200" ]] || fail "surviving replica lost its route"
echo 'Host proxy authentication, allocation routing, removal and replacement passed'
