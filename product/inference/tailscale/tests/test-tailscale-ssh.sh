#!/usr/bin/env bash
# Runs the pinned tailscaled through run-tailscale and checks that it creates
# SSH host keys. Without them Tailscale SSH is advertised as disabled.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
read -r version sha < <(python3 -c 'import ast,sys
t=ast.parse(open(sys.argv[1]).read())
v={n.targets[0].id:n.value.value for n in t.body if isinstance(n,ast.Assign) and getattr(n.targets[0],"id","") in ("VERSION","SHA256")}
print(v["VERSION"],v["SHA256"])' "$root/install-tailscale.py")
docker run --rm -i --platform linux/amd64 -e version="$version" -e sha="$sha" \
  -v "$root/run-tailscale.sh:/opt/gradiated/bin/run-tailscale:ro" \
  python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea bash -s <<'TEST'
set -euo pipefail
useradd --uid 10005 tailscale
python3 -c 'import sys,urllib.request; urllib.request.urlretrieve(sys.argv[1], "/tmp/ts.tgz")' "https://pkgs.tailscale.com/stable/tailscale_${version}_amd64.tgz"
echo "$sha  /tmp/ts.tgz" | sha256sum -c --quiet
mkdir -p /opt/gradiated/tailscale /etc/gradiated
tar xzf /tmp/ts.tgz -C /opt/gradiated/tailscale --strip-components=1
install -d -m 700 -o tailscale -g tailscale /var/lib/gradiated-tailscale
echo '{"hostname":"gpu-bootstrap-testpod","bootstrap":true}' >/etc/gradiated/tailscale.json
bash /opt/gradiated/bin/run-tailscale >/tmp/tailscale.log 2>&1 &
key=/var/lib/gradiated-tailscale/ssh/ssh_host_ed25519_key
for _ in {1..30}; do [[ -f "$key" ]] && break; sleep 1; done
if ! [[ -f "$key" && "$(stat -c %u "$key")" == 0 ]] || (( 8#$(stat -c %a "$key") & 077 )); then cat /tmp/tailscale.log; exit 1; fi
if grep -q 'unable to get SSH host keys' /tmp/tailscale.log; then cat /tmp/tailscale.log; exit 1; fi
TEST
echo 'Pinned tailscaled started by run-tailscale creates root-only SSH host keys'
