#!/usr/bin/env python3
"""Exercise the Nomad observer against a separately owned runtime and status API."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

binary = sys.argv[1]
state = {"ready": False, "metrics": True, "ingest": 204, "reports": []}

class Runtime(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200 if state["metrics"] else 503)
            self.end_headers()
            self.wfile.write(b"vllm:num_requests_running 0\nvllm:num_requests_waiting 0\nvllm:kv_cache_usage_perc 0.1\n")
        else:
            self.send_response(200 if state["ready"] else 503)
            self.end_headers()

class Ingest(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_POST(self):
        assert self.headers["Authorization"] == "Bearer observer-test-token"
        report = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        state["reports"].append(report)
        self.send_response(state["ingest"])
        self.end_headers()


def server(handler):
    instance = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=instance.serve_forever, daemon=True).start()
    return instance


def wait(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.1)
    raise AssertionError("observer condition timed out")


def get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, ""
    except (OSError, urllib.error.URLError):
        return 0, ""

runtime, ingest = server(Runtime), server(Ingest)
# Reserve a port until immediately before the observer starts.
control = http.server.HTTPServer(("127.0.0.1", 0), Runtime)
port = control.server_port
control.server_close()
with tempfile.TemporaryDirectory() as directory:
    token = Path(directory) / "token"
    token.write_text("observer-test-token\n")
    token.chmod(0o600)
    env = {**os.environ, "DESMOND_CONTROL_HOST": "127.0.0.1", "DESMOND_CONTROL_PORT": str(port),
           "DESMOND_RUNTIME_PORT": str(runtime.server_port), "DESMOND_STATUS_HOST": "127.0.0.1",
           "DESMOND_STATUS_PORT": str(ingest.server_port), "DESMOND_STATUS_TOKEN_FILE": str(token),
           "DESMOND_DEPLOYMENT_ID": "00000000-0000-4000-8000-000000000001",
           "DESMOND_RELEASE": "test-release", "DESMOND_MODEL": "test/model"}
    missing = dict(env)
    missing.pop("DESMOND_STATUS_TOKEN_FILE")
    assert subprocess.run([binary, "--observe"], env=missing, capture_output=True, timeout=5).returncode != 0
    process = subprocess.Popen([binary, "--observe"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait(lambda: state["reports"] and not state["reports"][-1]["healthy"])
        assert get(port, "/health/ready")[0] == 503
        state["ready"] = True
        wait(lambda: state["reports"][-1]["accepting_requests"] and get(port, "/health/ready")[0] == 200)
        assert "vllm:num_requests_running" in get(port, "/metrics")[1]
        state["metrics"] = False
        wait(lambda: state["reports"][-1].get("reason_code") == "metrics_unavailable")
        assert not state["reports"][-1]["accepting_requests"]
        state["metrics"] = True
        wait(lambda: state["reports"][-1]["accepting_requests"])
        # A dead ingest path must invalidate reporter readiness even while vLLM is healthy.
        state["ingest"] = 503
        wait(lambda: get(port, "/health/ready")[0] == 503, seconds=14)
        assert get(runtime.server_port, "/health")[0] == 200
        state["ingest"] = 204
        wait(lambda: get(port, "/health/ready")[0] == 200)
        state["ready"] = False
        wait(lambda: not state["reports"][-1]["healthy"])
        assert get(port, "/health/ready")[0] == 503
        state["ready"] = True
        wait(lambda: get(port, "/health/ready")[0] == 200)
        process.terminate()
        process.wait(timeout=8)
        assert get(runtime.server_port, "/health")[0] == 200
        # A new observer attaches without restarting the separately managed runtime.
        process = subprocess.Popen([binary, "--observe"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait(lambda: get(port, "/health/ready")[0] == 200)
        process.terminate()
        process.wait(timeout=8)
        # A self-signed peer must never receive the bearer credential or a status body.
        cert, private_key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(private_key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost"], check=True, capture_output=True)
        tls = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ingest)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, private_key)
        tls.socket = context.wrap_socket(tls.socket, server_side=True)
        threading.Thread(target=tls.serve_forever, daemon=True).start()
        count = len(state["reports"])
        tls_env = {**env, "DESMOND_STATUS_URL": f"https://127.0.0.1:{tls.server_port}/v1/deployment-status"}
        process = subprocess.Popen([binary, "--observe"], env=tls_env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait(lambda: any(line.startswith("desmond_status_failures_total ") and float(line.split()[-1]) > 0
                             for line in get(port, "/metrics")[1].splitlines()))
            assert get(port, "/health/ready")[0] == 503
            assert len(state["reports"]) == count
        finally:
            process.terminate()
            process.wait(timeout=8)
            tls.shutdown()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=8)
        runtime.shutdown()
        ingest.shutdown()
print("observer: reports startup, health, upload failure, recovery, and preserves runtime on stop, and rejects untrusted TLS")
