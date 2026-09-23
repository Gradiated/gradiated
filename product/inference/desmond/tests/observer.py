#!/usr/bin/env python3
"""End-to-end tests for desmondd in observe and supervise modes."""
import http.server
import json
import mmap
import os
from pathlib import Path
import signal
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

STATUS_TOKEN = "observer-test-token"
CONTROL_TOKEN = "control-test-token"
RUNTIME_METRICS = b"vllm:num_requests_running 0\nvllm:num_requests_waiting 0\nvllm:kv_cache_usage_perc 0.1\n"


class QuietHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass


class FakeServices:
    def __init__(self):
        self.ready = False
        self.metrics = True
        self.ingest_status = 204
        self.reports = []
        self.report_times = []
        self.profiling_batches = []
        self.authorizations = []
        self.runtime = serve(local_server(self.runtime_handler()))
        self.ingest = serve(local_server(self.ingest_handler()))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.runtime.shutdown()
        self.ingest.shutdown()

    def runtime_handler(self):
        services = self

        class Runtime(QuietHandler):
            def do_GET(self):
                if self.path == "/metrics":
                    self.send_response(200 if services.metrics else 503)
                    self.end_headers()
                    self.wfile.write(RUNTIME_METRICS)
                else:
                    self.send_response(200 if services.ready else 503)
                    self.end_headers()

        return Runtime

    def ingest_handler(self):
        services = self

        class Ingest(QuietHandler):
            def do_POST(self):
                services.authorizations.append(self.headers["Authorization"])
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/v1/profiling-events":
                    services.profiling_batches.append(body)
                else:
                    services.reports.append(body)
                    services.report_times.append((time.monotonic(), body))
                self.send_response(services.ingest_status)
                self.end_headers()

        return Ingest

    def last_report(self):
        return self.reports[-1] if self.reports else {}


def local_server(handler):
    return http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait(predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("condition timed out")


def get(port, path, token=None):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, ""
    except (OSError, urllib.error.URLError):
        return 0, ""


def write_secret(path, value):
    path.write_text(value + "\n")
    path.chmod(0o600)
    return str(path)


def desmond_environment(directory, services, control_port):
    return {
        **os.environ,
        "DESMOND_CONTROL_HOST": "127.0.0.1",
        "DESMOND_CONTROL_PORT": str(control_port),
        "DESMOND_CONTROL_TOKEN_FILE": write_secret(directory / "control-token", CONTROL_TOKEN),
        "DESMOND_RUNTIME_PORT": str(services.runtime.server_port),
        "DESMOND_STATUS_HOST": "127.0.0.1",
        "DESMOND_STATUS_PORT": str(services.ingest.server_port),
        "DESMOND_STATUS_TOKEN_FILE": write_secret(directory / "status-token", STATUS_TOKEN),
        "DESMOND_DEPLOYMENT_ID": "00000000-0000-4000-8000-000000000001",
        "DESMOND_RELEASE": "test-release",
        "DESMOND_MODEL": "test/model",
    }


def start(binary, arguments, env):
    return subprocess.Popen([binary, *arguments], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop(process):
    if process.poll() is None:
        process.terminate()
    return process.wait(timeout=8)


def observe_mode_requires_status_token(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        env = desmond_environment(Path(directory), services, free_port())
        env.pop("DESMOND_STATUS_TOKEN_FILE")
        assert subprocess.run([binary, "--observe"], env=env, capture_output=True, timeout=5).returncode != 0


def bad_usage_exits_64(binary):
    for arguments in (["--observe", "extra"], ["--"], []):
        assert subprocess.run([binary, *arguments], capture_output=True, timeout=5).returncode == 64, arguments


def observe_mode_reports_and_recovers(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        port = free_port()
        env = desmond_environment(Path(directory), services, port)
        process = start(binary, ["--observe"], env)
        try:
            wait(lambda: services.reports and not services.last_report()["healthy"])
            assert get(port, "/health/ready")[0] == 503

            services.ready = True
            wait(lambda: services.last_report()["accepting_requests"] and get(port, "/health/ready")[0] == 200)
            assert "vllm:num_requests_running" in get(port, "/metrics")[1]
            assert get(port, "/v1/desmond/status")[0] == 401
            assert get(port, "/v1/desmond/status", "wrong-token")[0] == 401
            status, body = get(port, "/v1/desmond/status", CONTROL_TOKEN)
            assert status == 200 and json.loads(body)["release"] == "test-release"

            services.metrics = False
            wait(lambda: services.last_report().get("reason_code") == "metrics_unavailable")
            assert not services.last_report()["accepting_requests"]
            services.metrics = True
            wait(lambda: services.last_report()["accepting_requests"])

            services.ingest_status = 503
            wait(lambda: get(port, "/health/ready")[0] == 503, seconds=14)
            assert get(services.runtime.server_port, "/health")[0] == 200
            services.ingest_status = 204
            wait(lambda: get(port, "/health/ready")[0] == 200)

            services.ready = False
            wait(lambda: not services.last_report()["healthy"])
            assert get(port, "/health/ready")[0] == 503
            services.ready = True
            wait(lambda: get(port, "/health/ready")[0] == 200)

            assert stop(process) == 0
            assert get(services.runtime.server_port, "/health")[0] == 200
            assert services.last_report()["healthy"] is False
            assert services.last_report()["reason_code"] == "draining"

            process = start(binary, ["--observe"], env)
            wait(lambda: get(port, "/health/ready")[0] == 200)
            assert stop(process) == 0
            assert set(services.authorizations) == {f"Bearer {STATUS_TOKEN}"}
        finally:
            stop(process)


def observe_mode_rejects_untrusted_tls(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        cert, private_key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(private_key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost"], check=True, capture_output=True)
        tls = local_server(services.ingest_handler())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, private_key)
        tls.socket = context.wrap_socket(tls.socket, server_side=True)
        serve(tls)
        services.ready = True
        port = free_port()
        env = {**desmond_environment(Path(directory), services, port),
               "DESMOND_STATUS_URL": f"https://127.0.0.1:{tls.server_port}/v1/deployment-status"}
        process = start(binary, ["--observe"], env)
        try:
            wait(lambda: any(line.startswith("desmond_status_failures_total ") and float(line.split()[-1]) > 0
                             for line in get(port, "/metrics")[1].splitlines()))
            assert get(port, "/health/ready")[0] == 503
            assert services.reports == [] and services.authorizations == []
        finally:
            stop(process)
            tls.shutdown()


def fake_runtime_command(behavior, directory):
    return ["--", sys.executable, os.path.abspath(__file__), "--fake-runtime", behavior, str(directory)]


def supervise_mode_reports_draining_before_stopping_the_runtime(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        port = free_port()
        env = {**desmond_environment(Path(directory), services, port), "DESMOND_RUNTIME_PORT": str(free_port())}
        process = start(binary, fake_runtime_command("ready", directory), env)
        try:
            wait(lambda: get(port, "/health/ready")[0] == 200)
            wait(lambda: services.last_report().get("accepting_requests"))
            assert stop(process) == 0
            terminated_at = float((Path(directory) / "terminated").read_text())
            drained = [at for at, report in services.report_times if report["reason_code"] == "draining"]
            assert drained and drained[0] < terminated_at, (drained, terminated_at)
        finally:
            stop(process)


def supervise_mode_forwards_runtime_traces_to_profiling(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        port = free_port()
        env = {**desmond_environment(Path(directory), services, port),
               "DESMOND_RUNTIME_PORT": str(free_port()),
               "DESMOND_TRACE_PATH": str(Path(directory) / "trace-ring"),
               "DESMOND_PROFILING_HOST": "127.0.0.1",
               "DESMOND_PROFILING_PORT": str(services.ingest.server_port),
               "DESMOND_PROFILING_TOKEN": "profiling-token"}
        process = start(binary, fake_runtime_command("trace", directory), env)
        try:
            wait(lambda: get(port, "/health/ready")[0] == 200)
            assert stop(process) == 0
            events = [event for batch in services.profiling_batches for event in batch["events"]]
            admitted = [event for event in events if event["event_type"] == "runtime.request.admitted"]
            assert admitted and admitted[0]["properties"] == {
                "monotonic_ns": 5, "request_id_high": "0", "request_id_low": "77",
                "input_tokens": 128, "cached_input_tokens": 64, "slot_id": 2, "queue_us": 900}, admitted
            types = [event["event_type"] for event in events]
            assert types[0] == "runtime.started" and "runtime.stopping" in types, types
        finally:
            stop(process)


def write_trace_event(path):
    with open(path, "r+b") as ring_file, mmap.mmap(ring_file.fileno(), 0) as ring:
        capacity = struct.unpack_from("<Q", ring, 16)[0]
        head = struct.unpack_from("<Q", ring, 64)[0]
        request_admitted = 1
        struct.pack_into("<8QIHH", ring, 256 + (head & (capacity - 1)) * 72,
                         5, 0, 77, 0, 900, 0, 128, 64, 2, 0, request_admitted)
        struct.pack_into("<Q", ring, 64, head + 1)


def supervise_mode_reports_an_unexpected_exit_as_runtime_unavailable(binary):
    for behavior, expected in (("exit-3", 3), ("exit-0", 70), ("kill-9", 128 + 9)):
        with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
            env = {**desmond_environment(Path(directory), services, free_port()), "DESMOND_RUNTIME_PORT": str(free_port())}
            process = start(binary, fake_runtime_command(behavior, directory), env)
            try:
                assert process.wait(timeout=10) == expected, behavior
                assert services.last_report().get("reason_code") == "runtime_unavailable", services.last_report()
            finally:
                stop(process)


def supervise_mode_fails_fast_when_runtime_is_missing(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        env = desmond_environment(Path(directory), services, free_port())
        process = start(binary, ["--", "/nonexistent/desmond-runtime"], env)
        try:
            assert process.wait(timeout=5) == 70
        finally:
            stop(process)


def supervise_mode_refuses_bound_control_port(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory, socket.socket() as occupant:
        occupant.bind(("127.0.0.1", 0))
        occupant.listen()
        env = {**desmond_environment(Path(directory), services, occupant.getsockname()[1]),
               "DESMOND_RUNTIME_PORT": str(free_port())}
        process = start(binary, fake_runtime_command("ready", directory), env)
        try:
            assert process.wait(timeout=5) != 0
            assert not (Path(directory) / "started").exists()
        finally:
            stop(process)


def supervise_mode_hides_credentials_from_runtime(binary):
    with FakeServices() as services, tempfile.TemporaryDirectory() as directory:
        port = free_port()
        env = {**desmond_environment(Path(directory), services, port),
               "DESMOND_RUNTIME_PORT": str(free_port()),
               "DESMOND_STATUS_TOKEN": "inline-status-token",
               "DESMOND_PROFILING_TOKEN": "inline-profiling-token",
               "DESMOND_RUNTIME_API_KEY": "runtime-api-key",
               "DESMOND_TRACE_PATH": str(Path(directory) / "trace-ring")}
        process = start(binary, fake_runtime_command("dump-env", directory), env)
        try:
            wait(lambda: get(port, "/health/ready")[0] == 200)
            runtime_environment = json.loads((Path(directory) / "environment.json").read_text())
            leaked = [name for name in runtime_environment
                      if name.startswith("DESMOND_") and (name.endswith("_TOKEN") or name.endswith("_TOKEN_FILE"))]
            assert leaked == [], leaked
            assert "DESMOND_RUNTIME_API_KEY" not in runtime_environment
            arguments = json.loads((Path(directory) / "arguments.json").read_text())
            assert arguments[-2:] == ["--api-key", "runtime-api-key"], arguments
            assert "DESMOND_TRACE_PATH" not in runtime_environment
            assert not (Path(directory) / "trace-ring").exists()
        finally:
            stop(process)


def fake_runtime(behavior, directory):
    directory = Path(directory)
    (directory / "started").touch()
    if behavior == "dump-env":
        (directory / "environment.json").write_text(json.dumps(dict(os.environ)))
        (directory / "arguments.json").write_text(json.dumps(sys.argv))
    if behavior == "trace":
        write_trace_event(os.environ["DESMOND_TRACE_PATH"])

    def terminate(*_):
        (directory / "terminated").write_text(str(time.monotonic()))
        os._exit(0)

    signal.signal(signal.SIGTERM, terminate)

    class Runtime(QuietHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            if self.path == "/metrics":
                self.wfile.write(RUNTIME_METRICS)
            elif behavior.startswith("exit-"):
                threading.Timer(0.2, os._exit, (int(behavior[5:]),)).start()
            elif behavior == "kill-9":
                threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGKILL)).start()

    http.server.ThreadingHTTPServer(("127.0.0.1", int(os.environ["DESMOND_RUNTIME_PORT"])), Runtime).serve_forever()


SCENARIOS = [
    bad_usage_exits_64,
    observe_mode_requires_status_token,
    observe_mode_reports_and_recovers,
    observe_mode_rejects_untrusted_tls,
    supervise_mode_reports_draining_before_stopping_the_runtime,
    supervise_mode_forwards_runtime_traces_to_profiling,
    supervise_mode_reports_an_unexpected_exit_as_runtime_unavailable,
    supervise_mode_fails_fast_when_runtime_is_missing,
    supervise_mode_refuses_bound_control_port,
    supervise_mode_hides_credentials_from_runtime,
]


def main():
    if sys.argv[1] == "--fake-runtime":
        fake_runtime(sys.argv[2], sys.argv[3])
        return
    failed = []
    for scenario in SCENARIOS:
        started = time.monotonic()
        try:
            scenario(sys.argv[1])
            print(f"PASS {scenario.__name__} ({time.monotonic() - started:.1f}s)")
        except Exception as error:
            failed.append(scenario.__name__)
            print(f"FAIL {scenario.__name__}: {error!r}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
