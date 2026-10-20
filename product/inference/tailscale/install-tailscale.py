#!/usr/bin/env python3
import hashlib
import io
import ipaddress
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
import urllib.error
import urllib.request
import uuid
from pathlib import Path

VERSION = "1.104.1"
SHA256 = "108d1d96ecf410d305571e173516f27038f870919a9b89c914a167c6d33a4528"
BOOTSTRAP_TAG = "tag:gpu-bootstrap"
SUPERVISOR = b"/opt/gradiated/bin/run-tailscale"


def supervisors(proc=Path("/proc"), uid=0):
    found = []
    for path in proc.glob("[0-9]*"):
        try:
            args = (path / "cmdline").read_bytes().split(b"\0")
            if len(args) > 1 and Path(os.fsdecode(args[0])).name == "bash" and args[1] == SUPERVISOR and path.stat().st_uid == uid:
                found.append(int(path.name))
        except (OSError, ValueError):
            pass
    return found


def schedule_promotion(delay=10):
    """Restart tailscaled after the enrollment session has ended.

    The staged auth key re-authenticates the pod as tag:gpu-inference, which
    drops the ops-mcp SSH session that installed it.
    """
    if not Path("/var/lib/gradiated-tailscale/reauth").exists():
        return False
    pids = supervisors()
    if len(pids) != 1:
        raise RuntimeError("Expected exactly one root Tailscale supervisor")
    subprocess.Popen(
        ["/bin/sh", "-c", f"sleep {int(delay)}; kill -USR1 {pids[0]}"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def registered_instance_id(identity_path=Path("/etc/gradiated/host-identity.json")):
    return str(uuid.UUID(json.loads(identity_path.read_text())["instance_id"]))


def install(payload):
    instance = str(uuid.UUID(payload["instance_id"]))
    if registered_instance_id() != instance:
        raise ValueError("Registered host identity mismatch")
    hostname = "gpu-" + instance
    config = Path("/etc/gradiated/tailscale.json")
    existing = json.loads(config.read_text()) if config.exists() else {}
    if existing and existing["hostname"] != hostname and existing.get("bootstrap") is not True:
        raise ValueError("Existing Tailscale identity mismatch")
    if existing.get("bootstrap") is True:
        existing = {}
    proxy_port = payload.get("proxy_port", existing.get("proxy_port", 8888))
    if proxy_port not in (8888, 8889):
        raise ValueError("Unexpected inference proxy port")
    if "proxy_port" in payload:
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{proxy_port}/healthz", timeout=5
                ) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            if time.monotonic() >= deadline:
                raise ValueError("Private host proxy is not ready")
            time.sleep(1)
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

    private_write(
        config,
        json.dumps(
            {"hostname": hostname, "instance_id": instance, "proxy_port": proxy_port}
        ),
    )
    if "control_endpoints" in payload:
        endpoints = payload["control_endpoints"]
        if set(endpoints) != {"api"} or any(
            ipaddress.ip_address(address) not in ipaddress.ip_network("100.64.0.0/10")
            for address in endpoints.values()
        ):
            raise ValueError("Invalid private control endpoints")
        control_config = Path("/etc/gradiated/tailscale-control.json")
        private_write(control_config, json.dumps(endpoints), 0, 0)
        control_config.chmod(0o644)
    names = ["run-tailscale", "start-tailscale"]
    if "control_endpoints" in payload:
        names.extend(["forward-control", "run-control", "start-control"])
    for name in names:
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
    current = json.loads(status.stdout) if status.returncode == 0 else {}
    running = current.get("BackendState") == "Running"
    promotion = running and BOOTSTRAP_TAG in current.get("Self", {}).get("Tags", [])
    if not running or promotion:
        private_write(root / "auth-key", payload["auth_key"])
    if promotion:
        # A bootstrap pod re-authenticates as tag:gpu-inference only after the
        # enrollment session ends; see schedule_promotion.
        private_write(root / "reauth", "")
    log = Path("/var/log/gradiated-tailscale.log")
    if not log.exists():
        private_write(log, "", 0, 0)
    subprocess.run(
        ["bash", "/opt/gradiated/bin/start-tailscale"], check=True, timeout=10
    )
    if promotion:
        ip = next((value for value in current.get("TailscaleIPs", []) if "." in value), None)
        if not ip:
            raise RuntimeError("Bootstrap Tailscale address is unavailable")
        print(json.dumps({"instance_id": instance, "tailscale_ip": ip, "hostname": hostname, "promotion": True}))
        return
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
                    subprocess.run(
                        [
                            str(destination / "tailscale"),
                            "--socket=" + str(root / "socket"),
                            "serve",
                            "--bg",
                            "--tcp=8888",
                            f"tcp://127.0.0.1:{proxy_port}",
                        ],
                        check=True,
                        capture_output=True,
                        timeout=10,
                    )
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
