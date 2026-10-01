#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import signal
import ssl
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import uuid

CHECK_SECONDS = 15 * 60
RETRY_SECONDS = 60
DAY_SECONDS = 86400


def openssl(*args):
    return subprocess.run(["openssl", *map(str, args)], check=True, capture_output=True, timeout=10).stdout


def dates(certificate):
    values = openssl("x509", "-in", certificate, "-noout", "-startdate", "-enddate").decode().splitlines()
    return tuple(ssl.cert_time_to_seconds(value.split("=", 1)[1]) for value in values)


def needs_renewal(certificate, now=None):
    start, end = dates(certificate)
    return end - start > 31 * DAY_SECONDS or (time.time() if now is None else now) >= start + (end - start) * 2 / 3


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Certificate issuer redirects are forbidden")


def request_certificate(config, public_key=None, certificate=None):
    instance = str(uuid.UUID(config["instance_id"]))
    node = str(uuid.UUID(config["nomad_node_id"]))
    token = config["token"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise ValueError("Invalid renewal credential")
    body = {"nomad_node_id": node, "certificate": certificate}
    if public_key is not None:
        body["public_key"] = public_key
    request = urllib.request.Request(
        f"https://api.gradiated.com/api/internal/v1/instances/{instance}/nomad-certificates",
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
        expected_status = 201 if public_key is not None else 200
        if response.status != expected_status:
            raise RuntimeError("Certificate issuance failed")
        payload = response.read(4097)
        if len(payload) > 4096:
            raise ValueError("Certificate response is too large")
        result = json.loads(payload)
        if public_key is None:
            if result != {}:
                raise ValueError("Invalid heartbeat response")
            return None
        if set(result) != {"certificate"} or not isinstance(result["certificate"], str):
            raise ValueError("Invalid certificate response")
        return result["certificate"]


def sync_directory(directory):
    descriptor = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_private(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def point_current(directory, generation):
    temporary = directory / (".current-" + uuid.uuid4().hex)
    temporary.symlink_to(generation.name, target_is_directory=True)
    os.replace(temporary, directory / "current")
    sync_directory(directory)


def prepare_directory(tls):
    directory = tls / "renewal"
    directory.mkdir(mode=0o700, exist_ok=True)
    if not (directory / "current").exists():
        initial = directory / "initial"
        initial.mkdir(mode=0o700, exist_ok=True)
        for name in ("client.pem", "client-key.pem"):
            destination = initial / name
            if not destination.exists():
                write_private(destination, (tls / name).read_bytes())
        point_current(directory, initial)
    for name in ("client.pem", "client-key.pem"):
        target = Path("renewal/current") / name
        existing = tls / name
        if existing.is_symlink() and os.readlink(existing) == str(target):
            continue
        if existing.read_bytes() != (directory / "current" / name).read_bytes():
            raise RuntimeError("Unexpected TLS file while migrating renewal paths")
        temporary = tls / (".link-" + uuid.uuid4().hex)
        temporary.symlink_to(target)
        os.replace(temporary, existing)
    return directory


def validate_pair(certificate, key, ca):
    openssl("verify", "-CAfile", ca, "-purpose", "sslclient", "-verify_hostname", "client.global.nomad", certificate)
    openssl("verify", "-CAfile", ca, "-purpose", "sslserver", "-verify_hostname", "localhost", certificate)
    if openssl("x509", "-in", certificate, "-pubkey", "-noout") != openssl("pkey", "-in", key, "-pubout"):
        raise ValueError("Certificate does not match the local key")
    start, end = dates(certificate)
    if start > time.time() or end <= time.time() or end - start > 31 * DAY_SECONDS:
        raise ValueError("Certificate has an invalid lifetime")


def agent_pid(pid_file):
    pid = int(pid_file.read_text().strip())
    command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    if Path(os.fsdecode(command[0])).name != "nomad" or b"agent" not in command:
        raise RuntimeError("PID is not the Nomad agent")
    return pid


def reload_agent(tls, pid_file):
    pid = agent_pid(pid_file)
    expected = hashlib.sha256(ssl.PEM_cert_to_DER_cert((tls / "client.pem").read_text())).digest()
    os.kill(pid, signal.SIGHUP)
    context = ssl.create_default_context(cafile=str(tls / "ca.pem"))
    context.load_cert_chain(str(tls / "client.pem"), str(tls / "client-key.pem"))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 4646), timeout=2) as connection:
                with context.wrap_socket(connection, server_hostname="localhost") as secured:
                    if hashlib.sha256(secured.getpeercert(binary_form=True)).digest() == expected:
                        return
        except (OSError, ssl.SSLError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Nomad did not load the new certificate")


def agent_ready(pid_file):
    agent_pid(pid_file)
    with socket.create_connection(("127.0.0.1", 4646), timeout=2):
        pass


def renew_once(tls, config_file, pid_file, issue=request_certificate, reload=reload_agent, ready=agent_ready):
    ready(pid_file)
    directory = prepare_directory(tls)
    pending = directory / "reload-pending"
    if pending.exists():
        reload(tls, pid_file)
        pending.unlink()
        print(json.dumps({"event": "host_certificate_reloaded"}), flush=True)
    config = json.loads(config_file.read_text())
    if not needs_renewal(tls / "client.pem"):
        issue(config, certificate=(tls / "client.pem").read_text())
        return False
    generation = Path(tempfile.mkdtemp(prefix="generation-", dir=directory))
    previous = (directory / "current").resolve()
    try:
        key = generation / "client-key.pem"
        openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", key)
        os.chmod(key, 0o600)
        with open(key, "rb") as output:
            os.fsync(output.fileno())
        public_key = openssl("pkey", "-in", key, "-pubout").decode()
        certificate = generation / "client.pem"
        write_private(certificate, issue(config, public_key, (tls / "client.pem").read_text()).encode())
        validate_pair(certificate, key, tls / "ca.pem")
        sync_directory(generation)
        # The marker precedes the atomic switch, so a crash always retries reload.
        if not pending.exists():
            write_private(pending, b"pending\n")
        point_current(directory, generation)
    except Exception:
        if (directory / "current").resolve() != generation:
            shutil.rmtree(generation)
        raise
    reload(tls, pid_file)
    pending.unlink()
    issue(config, certificate=(tls / "client.pem").read_text())
    for old in directory.iterdir():
        if old.is_dir() and not old.is_symlink() and old not in (generation, previous):
            shutil.rmtree(old)
    print(json.dumps({"event": "host_certificate_renewed", "expires_at": dates(certificate)[1]}), flush=True)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    os.umask(0o077)
    tls = Path("/etc/nomad/tls")
    config = tls / "renewal.json"
    pid = Path("/var/lib/nomad/client/agent.pid")
    with open(tls / "renewal.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(75)
        while True:
            wait = CHECK_SECONDS
            try:
                renew_once(tls, config, pid)
            except Exception as error:
                # Exception messages can contain credentials or upstream response data.
                print(json.dumps({"event": "host_certificate_renewal_failed", "error_type": type(error).__name__, "http_status": error.code if isinstance(error, urllib.error.HTTPError) else None}), flush=True)
                if arguments.once:
                    raise SystemExit(1)
                wait = RETRY_SECONDS
            if arguments.once:
                return
            time.sleep(wait)


if __name__ == "__main__":
    main()
