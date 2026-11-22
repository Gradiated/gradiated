#!/bin/bash
# Ubuntu build host only. Run locally as root after a verified Tailscale SSH login.
set -euo pipefail
umask 027

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $(id -u) == 0 ]] || fail "Run with sudo; never put a password in this script."
[[ $# == 1 && $1 =~ ^[a-z_][a-z0-9_-]*$ ]] || fail "Usage: sudo bash desktop-setup.sh USER"
desktop_user=$1
[[ $desktop_user != root ]] || fail "Choose an individual non-root desktop account."
# Bound package installation and service changes, including user-launched runs.
if [[ ${FPGA_DESKTOP_SETUP_BOUNDED:-0} != 1 ]]; then
    exec timeout --foreground --signal=TERM --kill-after=30s 20m \
        env FPGA_DESKTOP_SETUP_BOUNDED=1 /bin/bash "$0" "$desktop_user"
fi
exec 9>/run/lock/gradiated-fpga-desktop.lock
flock -n 9 || fail "Another desktop setup is running."

source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 22.04 && $(uname -m) == x86_64 ]] ||
    fail "This setup is only for Ubuntu 22.04 x86-64."
desktop_home=$(getent passwd "$desktop_user" | cut -d: -f6)
desktop_uid=$(id -u "$desktop_user")
desktop_gid=$(id -g "$desktop_user")
[[ $desktop_uid -ge 1000 && $desktop_home == /home/* && -d $desktop_home ]] ||
    fail "Expected a regular user with an existing /home directory."
[[ ! -L $desktop_home/.xsession ]] || fail "Refusing a symlinked .xsession."
tailscale debug prefs | python3 -c '
import json, sys
prefs = json.load(sys.stdin)
if not prefs.get("RunSSH") or not prefs.get("WantRunning"):
    raise SystemExit("Tailscale SSH must already be enabled and tested.")
'
tailscale status --json | python3 -c '
import json, sys
state = json.load(sys.stdin)
if state.get("BackendState") != "Running" or not state.get("Self", {}).get("Online"):
    raise SystemExit("The server must already be connected to Tailscale.")
'

state_dir=/var/lib/gradiated-fpga-desktop
install -d -m 0700 "$state_dir"
log_file=/var/log/gradiated-fpga-desktop-setup.log
touch "$log_file"
chmod 0600 "$log_file"
exec > >(tee -a "$log_file") 2>&1
printf 'Preparing private desktop for %s on Ubuntu %s\n' "$desktop_user" "$VERSION_ID"

# Fail closed: package post-install hooks must not expose an unconfigured RDP port.
[[ ! -e /usr/sbin/policy-rc.d && ! -L /usr/sbin/policy-rc.d ]] ||
    fail "Existing service-start policy found; preserve it and review before proceeding."
policy_created=0
setup_complete=0
cleanup() {
    if [[ $policy_created == 1 ]]; then
        if grep -q '^# gradiated-fpga-desktop setup$' /usr/sbin/policy-rc.d; then
            rm /usr/sbin/policy-rc.d
        else
            printf '%s\n' "Service-start policy changed unexpectedly; leaving it for review." >&2
        fi
    fi
    if [[ $setup_complete != 1 ]]; then
        systemctl stop xrdp.service xrdp-sesman.service || true
        systemctl mask xrdp.service xrdp-sesman.service || true
        printf '%s\n' "Setup incomplete; desktop services remain stopped/masked. See the setup log." >&2
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
systemctl mask --now xrdp.service xrdp-sesman.service
cat > /usr/sbin/policy-rc.d <<'SERVICE_POLICY'
#!/bin/sh
# gradiated-fpga-desktop setup
case "$1" in
    xrdp|xrdp.service|xrdp-sesman|xrdp-sesman.service) exit 101 ;;
esac
exit 0
SERVICE_POLICY
chmod 0755 /usr/sbin/policy-rc.d
policy_created=1

export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=120 update
apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends \
    xfce4 xfce4-terminal xrdp xorgxrdp dbus-x11 x11-xserver-utils mesa-utils
for config in xrdp.ini sesman.ini; do
    [[ -f "$state_dir/$config.before-setup" ]] ||
        cp -p "/etc/xrdp/$config" "$state_dir/$config.before-setup"
done
if [[ -e $desktop_home/.xsession && ! -e $state_dir/xsession.before-setup ]]; then
    cp -p "$desktop_home/.xsession" "$state_dir/xsession.before-setup"
fi

python3 - /etc/xrdp/xrdp.ini /etc/xrdp/sesman.ini <<'DESKTOP_CONFIG'
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

def configure(path, changes):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise SystemExit("Expected a regular configuration file.")
    original = path.stat()
    lines = path.read_text().splitlines(keepends=True)
    requested = {name.casefold(): values for name, values in changes.items()}
    sections = {}
    occurrences = {}
    replacements = {}
    current = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        header = re.fullmatch(r"\[([^]]+)\]\s*(?:[;#].*)?", stripped)
        if header:
            if current in sections:
                sections[current][1] = index
            current = header[1].casefold()
            if current in requested:
                if current in sections:
                    raise SystemExit(f"Duplicate configuration section: {current}")
                sections[current] = [index, len(lines)]
                occurrences[current] = set()
        elif current in requested and stripped and not stripped.startswith(("#", ";")):
            key, separator, _ = stripped.partition("=")
            key = key.strip().casefold()
            targets = {name.casefold(): (name, value)
                       for name, value in requested[current].items()}
            if separator and key in targets:
                if key in occurrences[current]:
                    raise SystemExit(f"Duplicate configuration key: {current}.{key}")
                occurrences[current].add(key)
                name, value = targets[key]
                replacements[index] = f"{name}={value}\n"
    missing_sections = requested.keys() - sections.keys()
    if missing_sections:
        raise SystemExit(f"Missing required configuration sections: {sorted(missing_sections)}")
    insertions = {}
    for section, values in requested.items():
        additions = [f"{name}={value}\n" for name, value in values.items()
                     if name.casefold() not in occurrences[section]]
        if additions:
            insertions.setdefault(sections[section][1], []).extend(additions)
    output_lines = []
    for index in range(len(lines) + 1):
        if index in insertions:
            if output_lines and not output_lines[-1].endswith("\n"):
                output_lines[-1] += "\n"
            output_lines.extend(insertions[index])
        if index < len(lines):
            output_lines.append(replacements.get(index, lines[index]))
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.writelines(output_lines)
            output.flush()
            os.fsync(output.fileno())
            os.chmod(temporary, stat.S_IMODE(original.st_mode))
            os.chown(temporary, original.st_uid, original.st_gid)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

if len(sys.argv) != 3:
    raise SystemExit("Expected xrdp.ini and sesman.ini paths.")
configure(sys.argv[1], {
    "Globals": {
        "port": "tcp://127.0.0.1:3389",
        "security_layer": "tls",
        "ssl_protocols": "TLSv1.2,TLSv1.3",
    },
    "Channels": {"rdpdr": "false"},
})
configure(sys.argv[2], {
    "Globals": {"ListenAddress": "127.0.0.1"},
    "Security": {"AllowRootLogin": "false"},
    "Sessions": {"IdleTimeLimit": "900", "KillDisconnected": "false"},
})
DESKTOP_CONFIG

cat > "$desktop_home/.xsession" <<'DESKTOP_SESSION'
#!/bin/sh
unset DBUS_SESSION_BUS_ADDRESS
unset SESSION_MANAGER
exec dbus-run-session -- startxfce4
DESKTOP_SESSION
chown "$desktop_uid:$desktop_gid" "$desktop_home/.xsession"
chmod 0700 "$desktop_home/.xsession"
# Ubuntu's xrdp service needs access to its packaged TLS key; never print the key.
adduser xrdp ssl-cert

systemctl unmask xrdp.service xrdp-sesman.service
systemctl enable --now xrdp-sesman.service xrdp.service
python3 - <<'DESKTOP_LISTENERS'
import socket
import subprocess
import time


def validate_listeners(output):
    # Ubuntu xrdp's IPv6 build can bind sesman to ::1 even when its INI says
    # 127.0.0.1. Both are local-only; wildcard and other addresses must fail.
    allowed = {3389: {"127.0.0.1:3389"},
               3350: {"127.0.0.1:3350", "[::1]:3350"}}
    found = {port: [] for port in allowed}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            raise SystemExit("Unrecognised ss listener output.")
        address = fields[3]
        port_text = address.rsplit(":", 1)[-1]
        for port, permitted in allowed.items():
            if port_text == str(port):
                if address not in permitted:
                    raise SystemExit(f"Unsafe desktop listener on {port}: {address}")
                found[port].append(address)
    return found


def main():
    for attempt in range(20):
        found = validate_listeners(
            subprocess.check_output(["ss", "-H", "-ltn"], text=True))
        missing = [port for port, addresses in found.items() if not addresses]
        if not missing:
            break
        time.sleep(0.25)
    else:
        raise SystemExit(f"Desktop listener did not start: {missing}")
    for port, addresses in found.items():
        for address in addresses:
            host = address.rsplit(":", 1)[0].strip("[]")
            with socket.create_connection((host, port), timeout=3):
                pass
    print("Verified: RDP and session manager listen only on loopback.")


if __name__ == "__main__":
    main()
DESKTOP_LISTENERS

# Tailscale runs its own SSH server; the public OpenSSH service is unnecessary.
# Recovery access remains available through Netcup SCP's Screen console.
systemctl mask --now ssh.service ssh.socket
if ss -H -ltn | awk '{print $4}' | grep -Eq ':22$'; then
    fail "An unexpected kernel SSH listener remains; inspect before continuing."
fi
dpkg-query -W -f='${Package} ${Version}\n' \
    xfce4 xfce4-terminal xrdp xorgxrdp dbus-x11 x11-xserver-utils mesa-utils \
    > "$state_dir/package-versions.txt"
openssl x509 -in /etc/xrdp/cert.pem -noout -fingerprint -sha256
setup_complete=1
printf '%s\n' "Desktop configured. Next verify a fresh Tailscale SSH login and tunnel from the Mac."
