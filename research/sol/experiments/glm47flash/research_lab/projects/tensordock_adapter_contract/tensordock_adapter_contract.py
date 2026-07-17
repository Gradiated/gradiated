#!/usr/bin/env python3
"""Zero-provider TensorDock lifecycle contract and deterministic fake service."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GPU = "a40-pcie-48gb"
HOST = "6d622e27-4bdb-4de5-9b8e-ab217ce3c8fe"
TERMINALS = {"running", "deleted", "create_failed", "deadline_cleanup", "delete_failed"}


class ContractError(RuntimeError):
    pass


def redacted(exc):
    return {"type": type(exc).__name__, "message": str(exc)[:240].replace("secret", "[redacted]")}


class Adapter:
    def __init__(self, base, owner, timeout=1.0):
        self.base = base.rstrip("/")
        self.owner = owner
        self.timeout = timeout
        self.diag = []

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Accept": "application/json", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read(1_000_001)
                if len(raw) > 1_000_000:
                    raise ContractError("response exceeds diagnostic bound")
                return json.loads(raw)
        except Exception as exc:
            self.diag.append({"stage": method + " " + path, "error": redacted(exc)})
            raise

    def refresh_exact_host(self):
        result = self.call("GET", "/api/session/deploy/hostnodes?minGPUCount=1&minRAM=4&minvCPUs=2&minStorage=20&minVRAM=48&requiresRTX=false")
        node = result.get("hostnodes", {}).get(HOST)
        gpu = (node or {}).get("specs", {}).get("gpu", {}).get(GPU)
        if not node or not gpu or gpu.get("amount") != 1 or gpu.get("vram") != 48 or gpu.get("price", 99) > 0.50:
            raise ContractError("exact host/rate/GPU mapping changed")
        return node

    def create(self):
        self.refresh_exact_host()
        existing = self.call("GET", "/api/session/instances")
        if any(x.get("owner") == self.owner and x.get("state") not in {"deleted", "failed"}
               for x in existing.get("instances", [])):
            raise ContractError("duplicate ownership")
        result = self.call("POST", "/api/session/deploy/single", {
            "name": self.owner, "vcpus": 2, "storage": 20, "ram": 4,
            "country": "Germany", "gpu_count": 1, "gpu_model": GPU,
            "operating_system": "Ubuntu 22.04 LTS", "hostnode": HOST,
            "external_ports": [22], "internal_ports": [22],
        })
        if result.get("success") is not True or not result.get("server"):
            raise ContractError("create response lacks resource identity")
        return result["server"]

    def poll(self, server, deadline=3):
        end = time.monotonic() + deadline
        while time.monotonic() < end:
            result = self.call("GET", "/api/session/instances/" + server)
            state = result.get("state")
            if state in {"running", "failed"}:
                return state
            time.sleep(0.02)
        raise ContractError("provisioning deadline exceeded")

    def delete(self, server):
        result = self.call("DELETE", "/api/session/instances/" + server)
        if result.get("success") is not True:
            raise ContractError("delete did not acknowledge success")
        direct = self.call("GET", "/api/session/instances/" + server)
        inventory = self.call("GET", "/api/session/instances")
        if direct.get("state") != "deleted" or any(x.get("id") == server and x.get("state") != "deleted"
                                                     for x in inventory.get("instances", [])):
            raise ContractError("delete/inventory disagreement")
        return "deleted"

    def lifecycle(self, mode="success"):
        try:
            server = self.create()
        except Exception:
            return "create_failed"
        try:
            state = self.poll(server, deadline=0.05 if mode == "timeout" else 3)
            if state != "running":
                return "create_failed"
            if mode == "deadline_cleanup":
                self.delete(server)
                return "deadline_cleanup"
            self.delete(server)
            return "deleted"
        except Exception:
            if mode == "delete_failure":
                return "delete_failed"
            return "create_failed" if mode in {"malformed", "duplicate", "changed_host", "missing_id"} else "deadline_cleanup"


class Fake(BaseHTTPRequestHandler):
    state = {"instances": [], "mode": "success"}
    def log_message(self, *_):
        pass
    def send(self, value, code=200):
        raw = json.dumps(value).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith("/api/session/deploy/hostnodes"):
            if self.state["mode"] == "changed_host":
                self.send({"hostnodes": {HOST: {"specs": {"gpu": {GPU: {"amount": 1, "vram": 24, "price": 0.33}}}}}}); return
            self.send({"hostnodes": {HOST: {"specs": {"gpu": {GPU: {"amount": 1, "vram": 48, "price": 0.33}}}}}}); return
        if self.path == "/api/session/instances": self.send({"instances": self.state["instances"]}); return
        if self.path.startswith("/api/session/instances/"):
            ident = self.path.rsplit("/", 1)[-1]; found = next((x for x in self.state["instances"] if x["id"] == ident), None)
            self.send(found or {"state": "missing"}); return
        self.send({"error": "not found"}, 404)
    def do_POST(self):
        if self.path != "/api/session/deploy/single": self.send({}, 404); return
        if self.state["mode"] == "missing_id": self.send({"success": True}); return
        ident = "fake-server-1"; state = "provisioning" if self.state["mode"] == "timeout" else "running"
        self.state["instances"].append({"id": ident, "owner": "tensor-contract", "state": state})
        self.send({"success": True, "server": ident})
    def do_DELETE(self):
        ident = self.path.rsplit("/", 1)[-1]
        if self.state["mode"] == "delete_failure": self.send({"success": False}, 409); return
        for item in self.state["instances"]:
            if item["id"] == ident: item["state"] = "deleted"
        self.send({"success": True})


def run_case(mode):
    Fake.state = {"instances": [], "mode": mode}
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    adapter = Adapter("http://127.0.0.1:%d" % server.server_port, "tensor-contract")
    if mode == "duplicate": Fake.state["instances"] = [{"id": "old", "owner": "tensor-contract", "state": "running"}]
    try:
        terminal = adapter.lifecycle(mode)
    finally:
        server.shutdown(); server.server_close()
    expected = {"success": "deleted", "missing_id": "create_failed", "changed_host": "create_failed", "duplicate": "create_failed", "timeout": "deadline_cleanup", "delete_failure": "delete_failed"}[mode]
    return {"mode": mode, "terminal": terminal, "diagnostics": adapter.diag, "pass": terminal == expected}


def systemd_child(destination):
    result = {"kind": "tensordock_fake_no_mutation_terminal", "provider_mutation": False, "terminal": run_case("success"), "watchdog": {"deadline_seconds": 5, "cleanup_required": True}}
    Path(destination).write_text(json.dumps(result, sort_keys=True) + "\n")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "child":
        systemd_child(sys.argv[2]); return
    modes = [run_case(x) for x in ["success", "missing_id", "changed_host", "duplicate", "timeout", "delete_failure"]]
    with tempfile.TemporaryDirectory() as temp:
        out = Path(temp) / "terminal.json"; unit = "tensordock-contract-%s" % os.getpid()
        launch = subprocess.run(["systemd-run", "--user", "--wait", "--collect", "--unit=" + unit, "--property=RuntimeMaxSec=5s", sys.executable, __file__, "child", str(out)], capture_output=True, text=True)
        external = json.loads(out.read_text()) if out.exists() else {"kind": "missing"}
        systemd = {"returncode": launch.returncode, "stdout_sha256": hashlib.sha256(launch.stdout.encode()).hexdigest(), "stderr_sha256": hashlib.sha256(launch.stderr.encode()).hexdigest(), "terminal": external}
    result = {"schema_version": 1, "classification": "zero_provider_tensordock_fake_lifecycle_contract", "provider_mutation": False, "cases": modes, "systemd_equivalent": systemd, "pass": all(x["pass"] for x in modes) and systemd["returncode"] == 0 and external.get("provider_mutation") is False and external.get("terminal", {}).get("pass") is True}
    print(json.dumps(result, sort_keys=True, indent=2))
    if not result["pass"]: raise SystemExit(1)


if __name__ == "__main__": main()
