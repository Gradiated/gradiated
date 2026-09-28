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
    network {
      port "runtime" {}
    }
    service {
      name     = "gradiated-runtime"
      provider = "nomad"
      port     = "runtime"
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

echo 'Host proxy authentication, allocation routing and route removal passed'
