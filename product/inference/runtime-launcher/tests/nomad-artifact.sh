#!/usr/bin/env bash
set -euo pipefail
# Local CPU fixture. No production connection or GPU allocation.
work=$(mktemp -d)
server=
agent=
cleanup() {
  result=$?
  if [[ "$result" != 0 && -f "$work/agent.log" ]]; then tail -50 "$work/agent.log"; fi
  [[ -z "$agent" ]] || kill "$agent" 2>/dev/null || true
  [[ -z "$server" ]] || kill "$server" 2>/dev/null || true
  wait 2>/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT
chmod 755 "$work"
chown nobody "$work"
mkdir "$work/bundle" "$work/state"
chmod 777 "$work/state"
echo test-base-v1 > "$work/bundle/base-id"
cat > "$work/bundle/entrypoint" <<'ENTRY'
#!/bin/sh
test "$1" = 'literal $(false)'
test -f "$GRADIATED_RUNTIME_ROOT/base-id"
echo artifact-launch-passed
ENTRY
chmod +x "$work/bundle/entrypoint"
tar -czf "$work/bundle.tar.gz" -C "$work/bundle" .
digest=$(sha256sum "$work/bundle.tar.gz" | cut -d' ' -f1)
openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj /CN=localhost -addext subjectAltName=DNS:localhost \
  -keyout "$work/key.pem" -out "$work/cert.pem" >/dev/null 2>&1
cp "$work/cert.pem" /usr/local/share/ca-certificates/nomad-fixture.crt
update-ca-certificates >/dev/null 2>&1
(cd "$work" && exec openssl s_server -quiet -accept 19443 -cert cert.pem -key key.pem -WWW) > "$work/tls.log" 2>&1 &
server=$!
cat > "$work/client.hcl" <<'HCL'
server { num_schedulers = 1 }
plugin "raw_exec" {
  config { enabled = true }
}
client {
  artifact { http_read_timeout = "10s" }
}
HCL
# Running as an ordinary user avoids cgroup setup in the test container.
runuser -u nobody -- nomad agent -dev -bind=127.0.0.1 \
  -data-dir="$work/state" -config="$work/client.hcl" > "$work/agent.log" 2>&1 &
agent=$!
for attempt in $(seq 1 100); do
  kill -0 "$agent" 2>/dev/null || exit 1
  nomad node status 2>/dev/null | grep -q ready && break
  sleep 0.1
done
nomad node status | grep -q ready
for mode in valid invalid; do
  checksum=$digest
  [[ "$mode" != invalid ]] || checksum=$(printf '%064d' 0)
  cat > "$work/job.hcl" <<HCL
job "artifact-$mode" {
  type = "batch"
  group "test" {
    restart { attempts = 0 }
    reschedule {
      attempts = 0
      unlimited = false
    }
    task "runtime" {
      driver = "raw_exec"
      artifact {
        source = "https://localhost:19443/bundle.tar.gz"
        destination = "local/runtime"
        options {
          checksum = "sha256:$checksum"
          archive = "tar.gz"
        }
      }
      config {
        command = "/build/runtime-launch"
        args = ["\${NOMAD_TASK_DIR}/runtime", "--", "literal \$(false)"]
      }
    }
  }
}
HCL
  nomad job run -detach "$work/job.hcl" >/dev/null
  if [[ "$mode" == valid ]]; then
    for attempt in $(seq 1 200); do
      grep -rl artifact-launch-passed "$work/state/alloc" 2>/dev/null | grep -q stdout && break
      sleep 0.1
    done
    grep -rl artifact-launch-passed "$work/state/alloc" | grep -q stdout
    echo PASS: Nomad-HTTPS-artifact-launch
  else
    for attempt in $(seq 1 200); do
      grep -qi 'checksums did not match' "$work/agent.log" && break
      sleep 0.1
    done
    grep -qi 'checksums did not match' "$work/agent.log"
    # Only the valid job may have produced the entrypoint marker.
    [[ "$(grep -rl artifact-launch-passed "$work/state/alloc" | grep -c stdout)" == 1 ]]
    echo PASS: Nomad-artifact-checksum-rejection
  fi
done
