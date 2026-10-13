#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
container="tailscale-supervisor-test-$$"
image=gradiated-tailscale-supervisor-test
trap 'docker rm -f "$container" >/dev/null 2>&1 || true' EXIT

docker build -q -t "$image" - >/dev/null <<'DOCKER'
FROM busybox:1.37.0-musl@sha256:5cec3fc171c87218698e85a52af7087de727372aae264a787b8112901a5b0092 AS busybox
FROM python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
COPY --from=busybox /bin/busybox /usr/local/bin/pgrep
RUN useradd --uid 10005 --create-home tailscale && useradd --uid 10001 runtime \
    && install -d -m 700 -o tailscale -g tailscale /var/lib/gradiated-tailscale \
    && mkdir -p /etc/gradiated /opt/gradiated/bin /opt/gradiated/tailscale
DOCKER
docker run -d --name "$container" --cpus=1 --memory=512m \
  -v "$root/run-tailscale.sh:/opt/gradiated/bin/run-tailscale:ro" \
  -v "$root/forward-control.py:/opt/gradiated/bin/forward-control:ro" \
  -v "$root/run-control.sh:/opt/gradiated/bin/run-control:ro" \
  -v "$root/start-control.sh:/opt/gradiated/bin/start-control:ro" \
  -v "$root/start-tailscale.sh:/opt/gradiated/bin/start-tailscale:ro" "$image" sleep 180 >/dev/null

docker exec -i "$container" bash -s <<'SETUP'
set -euo pipefail
cat >/etc/gradiated/tailscale.json <<'CONFIG'
{"hostname":"gpu-00000000-0000-4000-8000-000000000001"}
CONFIG
cat >/etc/gradiated/tailscale-control.json <<'CONTROL'
{"api":"100.64.0.1"}
CONTROL
printf 'tskey-auth-synthetic\n'  >/var/lib/gradiated-tailscale/auth-key
chown tailscale:tailscale /etc/gradiated/tailscale.json /var/lib/gradiated-tailscale/auth-key
chmod 600 /etc/gradiated/tailscale.json /var/lib/gradiated-tailscale/auth-key
cat >/opt/gradiated/tailscale/tailscaled <<'DAEMON'
#!/usr/bin/env python3
import signal,socket,time
s=socket.socket(socket.AF_UNIX);s.bind('/var/lib/gradiated-tailscale/socket');s.listen()
signal.signal(signal.SIGTERM,lambda *_:exit(0))
while True:time.sleep(1)
DAEMON
cat >/opt/gradiated/tailscale/tailscale <<'CLIENT'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>/var/lib/gradiated-tailscale/calls
case "$2" in
up)
  [[ -f /var/lib/gradiated-tailscale/state || "$*" == *'--auth-key=file:'* ]]
  printf 'enrolled\n' >/var/lib/gradiated-tailscale/state
  ;;
serve) [[ "$*" == *'--tcp=8888 tcp://127.0.0.1:8888'* ]] ;;
nc) cat ;;
*) exit 1 ;;
esac
CLIENT
chmod 755 /opt/gradiated/tailscale/{tailscale,tailscaled}
bash /opt/gradiated/bin/start-tailscale
SETUP

for _ in {1..30}; do
  if docker exec "$container" test -f /var/lib/gradiated-tailscale/state; then break; fi
  sleep .2
done
docker exec "$container" test ! -f /var/lib/gradiated-tailscale/auth-key
docker exec "$container" test -f /var/lib/gradiated-tailscale/state
if docker exec -u runtime "$container" test -r /var/lib/gradiated-tailscale/state; then exit 1; fi
if docker exec -u runtime "$container" test -r /etc/gradiated/tailscale.json; then exit 1; fi

docker exec "$container" bash /opt/gradiated/bin/start-tailscale
supervisor=$(docker exec "$container" pgrep -f '^bash /opt/gradiated/bin/run-tailscale$')
[[ "$supervisor" =~ ^[0-9]+$ ]]
child=$(docker exec "$container" cat "/proc/$supervisor/task/$supervisor/children" | xargs)
docker exec "$container" bash -c 'kill -KILL "$1"' _ "$child"
for _ in {1..30}; do
  calls=$(docker exec "$container" grep -c ' up ' /var/lib/gradiated-tailscale/calls)
  if ((calls >= 2)); then break; fi
  sleep .2
done
((calls >= 2))
docker exec "$container" bash -c 'kill -0 "$1"' _ "$supervisor"
if docker exec "$container" grep -q 'tskey-auth-synthetic' /var/lib/gradiated-tailscale/calls; then exit 1; fi
echo 'Tailscale supervisor restarts with persistent state, scopes Serve to TCP/8888 and isolates credentials'

docker exec -i "$container" python3 - <<'CHECK'
import socket, time
payload = b"synthetic-control-bytes" * 2500
for _ in range(30):
    try:
        connection = socket.create_connection(("127.0.0.1", 3004), timeout=2)
        break
    except OSError:
        time.sleep(.2)
with connection:
    connection.sendall(payload)
    received = bytearray()
    while len(received) < len(payload):
        received.extend(connection.recv(65536))
    assert bytes(received) == payload
host = socket.gethostbyname(socket.gethostname())
try:
    with socket.create_connection((host, 3004), timeout=1):
        raise AssertionError("Control bridge must be loopback-only")
except (ConnectionRefusedError, TimeoutError):
    pass
CHECK
control=$(docker exec "$container" pgrep -f '^python3 /opt/gradiated/bin/forward-control$')
[[ "$control" =~ ^[0-9]+$ ]]
if docker exec -u runtime "$container" bash -c 'kill -TERM "$1"' _ "$control" 2>/dev/null; then exit 1; fi
docker exec "$container" bash -c 'kill -KILL "$1"' _ "$control"
for _ in {1..30}; do
  next=$(docker exec "$container" pgrep -f '^python3 /opt/gradiated/bin/forward-control$' || true)
  if [[ -n "$next" && "$next" != "$control" ]]; then break; fi
  sleep .2
done
[[ -n "$next" && "$next" != "$control" ]]
echo 'Private control forwarding preserves bytes, binds only loopback and restarts under its isolated UID'
