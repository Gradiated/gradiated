#!/usr/bin/env python3
import hashlib
import io
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

VERSION = "1.104.1"
SHA256 = "108d1d96ecf410d305571e173516f27038f870919a9b89c914a167c6d33a4528"


def registered_instance_id(
    identity_path=Path("/etc/gradiated/host-identity.json"),
    node_config=Path("/etc/nomad/node.hcl"),
):
    if identity_path.exists():
        return str(uuid.UUID(json.loads(identity_path.read_text())["instance_id"]))

    matches = re.findall(
        r'^\s*gradiated_instance_id\s*=\s*"([^"\n]+)"\s*$',
        node_config.read_text(),
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise ValueError("Registered host identity missing or ambiguous")

    return str(uuid.UUID(matches[0]))


def install(payload):
    instance = str(uuid.UUID(payload["instance_id"]))
    if registered_instance_id() != instance:
        raise ValueError("Registered host identity mismatch")
    hostname = "gpu-" + instance
    config = Path("/etc/gradiated/tailscale.json")
    if config.exists() and json.loads(config.read_text())["hostname"] != hostname:
        raise ValueError("Existing Tailscale identity mismatch")
    try:
        account = pwd.getpwnam("tailscale")
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--uid",
                "10005",
                "--create-home",
                "--shell",
                "/usr/sbin/nologin",
                "tailscale",
            ],
            check=True,
        )
        account = pwd.getpwnam("tailscale")
    if account.pw_uid != 10005:
        raise ValueError("Unexpected Tailscale account")
    root = Path("/var/lib/gradiated-tailscale")
    root.mkdir(parents=True, exist_ok=True)
    os.chown(root, account.pw_uid, account.pw_gid)
    root.chmod(0o700)
    with urllib.request.urlopen(
        f"https://pkgs.tailscale.com/stable/tailscale_{VERSION}_amd64.tgz", timeout=30
    ) as response:
        archive = response.read(64 * 1024 * 1024)
    if hashlib.sha256(archive).hexdigest() != SHA256:
        raise ValueError("Tailscale archive checksum mismatch")
    destination = Path("/opt/gradiated/tailscale")
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o755)
    with tempfile.TemporaryDirectory() as stage:
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(stage, filter="data")
        for name in ("tailscale", "tailscaled"):
            source = Path(stage) / f"tailscale_{VERSION}_amd64" / name
            target = destination / name
            temporary = destination / (name + ".new")
            shutil.copyfile(source, temporary)
            temporary.chmod(0o755)
            temporary.replace(target)

    def private_write(path, content, uid=account.pw_uid, gid=account.pw_gid):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as output:
            os.fchmod(output.fileno(), 0o600)
            os.fchown(output.fileno(), uid, gid)
            output.write(content)

    private_write(config, json.dumps({"hostname": hostname, "instance_id": instance}))
    for name in ("run-tailscale", "start-tailscale"):
        target = Path("/opt/gradiated/bin") / name
        private_write(target, payload["scripts"][name], 0, 0)
        target.chmod(0o755)
    status_command = [
        str(destination / "tailscale"),
        "--socket=" + str(root / "socket"),
        "status",
        "--json",
    ]
    status = subprocess.run(
        status_command, capture_output=True, text=True, timeout=10, check=False
    )
    running = (
        status.returncode == 0
        and json.loads(status.stdout).get("BackendState") == "Running"
    )
    if not running:
        private_write(root / "auth-key", payload["auth_key"])
    log = Path("/var/log/gradiated-tailscale.log")
    if not log.exists():
        private_write(log, "", 0, 0)
    subprocess.run(
        ["bash", "/opt/gradiated/bin/start-tailscale"], check=True, timeout=10
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        status = subprocess.run(
            status_command, capture_output=True, text=True, timeout=5, check=False
        )
        if status.returncode == 0:
            data = json.loads(status.stdout)
            if (
                data.get("BackendState") == "Running"
                and not (root / "auth-key").exists()
            ):
                if "tag:gpu-inference" not in data.get("Self", {}).get("Tags", []):
                    raise ValueError("GPU enrollment must use tag:gpu-inference")
                ips = data.get("TailscaleIPs", [])
                ip = next((value for value in ips if "." in value), None)
                if ip:
                    print(
                        json.dumps(
                            {
                                "instance_id": instance,
                                "tailscale_ip": ip,
                                "hostname": hostname,
                            }
                        )
                    )
                    return
        time.sleep(1)
    raise RuntimeError("Tailscale enrollment did not become ready")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        install(json.load(sys.stdin))
    except Exception:  # noqa: BLE001 - credential-bearing errors must not escape
        print(
            "Tailscale installation failed; existing GPU workloads were not reset",
            file=sys.stderr,
        )
        sys.exit(1)
