#!/usr/bin/env python3
"""Repair the retained consumer with SGLang's OpenAI completions route."""

from __future__ import annotations

import datetime as dt
import hashlib
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
import urllib.parse


PROJECT = Path(__file__).resolve().parent
ARTIFACT_ROOT = (
    PROJECT / "artifacts" / "rtxpro6000-fp8-endpoint-20260729t0338z"
)
GENERATION = "repair-1785301292"
PAIR_ROOT = ARTIFACT_ROOT / "endpoint-pair"
ATTEMPT2_ROOT = (
    ARTIFACT_ROOT
    / f"endpoint-pair-{GENERATION}-ssh-tunnel-generate-schema-error"
)
FRESH_ROOT = (
    ARTIFACT_ROOT / f"endpoint-pair-{GENERATION}-ssh-tunnel-openai-completions"
)
ATTEMPT2_MANIFEST = ARTIFACT_ROOT / f"{GENERATION}-attempt2-schema-error-manifest.json"
EVIDENCE_PATH = (
    ARTIFACT_ROOT / "ENDPOINT_CONSUMER_OPENAI_COMPLETIONS_ADAPTER_REPAIR.json"
)
STDOUT_PATH = (
    ARTIFACT_ROOT / f"{GENERATION}-openai-completions-endpoint-consumer.stdout"
)
STDERR_PATH = (
    ARTIFACT_ROOT / f"{GENERATION}-openai-completions-endpoint-consumer.stderr"
)
WORKLOAD = PROJECT / "inputs" / "c32_requests.jsonl"
LAB_ENDPOINT_PAIR = (
    PROJECT.parents[5] / "factory" / "tools" / "lab-endpoint-pair"
)
PUBLIC_HOST = "213.192.6.70"
PUBLIC_PORT = 60547
ADAPTER_PORT = 19124
TUNNEL_PORT = 19125
REMOTE_PORT = 19123
PUBLIC_URL = f"http://{PUBLIC_HOST}:{PUBLIC_PORT}"
SSH = [
    "ssh",
    "-F",
    "/dev/null",
    "-i",
    "/root/.config/nebius/glm-campaign/ssh_ed25519",
    "-o",
    "UserKnownHostsFile=/root/.config/runpod/gemma4/known_hosts",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ExitOnForwardFailure=yes",
    "-o",
    "ServerAliveInterval=15",
    "-o",
    "ServerAliveCountMax=4",
    "-p",
    "40070",
    "-N",
    "-L",
    f"127.0.0.1:{TUNNEL_PORT}:127.0.0.1:{REMOTE_PORT}",
    f"root@{PUBLIC_HOST}",
]
IPTABLES_RULE = [
    "-t",
    "nat",
    "-I",
    "OUTPUT",
    "1",
    "-p",
    "tcp",
    "-d",
    PUBLIC_HOST,
    "--dport",
    str(PUBLIC_PORT),
    "-j",
    "REDIRECT",
    "--to-ports",
    str(ADAPTER_PORT),
]
IPTABLES_DELETE = [
    "-t",
    "nat",
    "-D",
    "OUTPUT",
    "-p",
    "tcp",
    "-d",
    PUBLIC_HOST,
    "--dport",
    str(PUBLIC_PORT),
    "-j",
    "REDIRECT",
    "--to-ports",
    str(ADAPTER_PORT),
]
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def tree_manifest(root: Path) -> list[dict[str, object]]:
    return [
        {
            "relative_path": str(path.relative_to(root)),
            "sha256": digest(path)["sha256"],
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def wait_for_tunnel(process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"SSH tunnel exited with {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", TUNNEL_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError("SSH tunnel did not accept local connections")


class GenerateAdapter(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    forwarded_requests = 0
    source_paths: dict[str, int] = {}
    state_lock = threading.Lock()

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        source_path = urllib.parse.urlsplit(self.path).path
        with self.state_lock:
            type(self).forwarded_requests += 1
            type(self).source_paths[source_path] = (
                type(self).source_paths.get(source_path, 0) + 1
            )
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "host"
        }
        headers["Host"] = f"127.0.0.1:{REMOTE_PORT}"
        upstream = HTTPConnection("127.0.0.1", TUNNEL_PORT, timeout=900)
        response = None
        try:
            upstream.request("POST", "/v1/completions", body=body, headers=headers)
            response = upstream.getresponse()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(name, value)
            self.send_header("Connection", "close")
            self.end_headers()
            while True:
                chunk = response.read1(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            self.close_connection = True
            if response is not None:
                response.close()
            upstream.close()

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    started_at = utc_now()
    if PAIR_ROOT.exists() or FRESH_ROOT.exists() or EVIDENCE_PATH.exists():
        raise FileExistsError("repair output already exists; refusing a silent replay")
    attempt2_run_path = ATTEMPT2_ROOT / "run.json"
    json.loads(attempt2_run_path.read_text())
    request_metadata = [
        json.loads(path.read_text())
        for path in sorted(
            (ATTEMPT2_ROOT / "arms" / "control" / "requests").glob("*/metadata.json")
        )
    ]
    if (
        len(request_metadata) != 32
        or any(row.get("status") != 200 for row in request_metadata)
        or any(row.get("usage") is not None for row in request_metadata)
        or any(row.get("token_ids") for row in request_metadata)
        or any(row.get("finish_reason") is not None for row in request_metadata)
    ):
        raise RuntimeError("attempt 2 is not the expected pre-generation schema defect")
    response_paths = sorted(
        (ATTEMPT2_ROOT / "arms" / "control" / "requests").glob("*/response.body")
    )
    if any(b'"type":"invalid_request_error"' not in path.read_bytes() for path in response_paths):
        raise RuntimeError("attempt 2 response is not the expected schema error")
    manifest = tree_manifest(ATTEMPT2_ROOT)
    write_json_atomic(
        ATTEMPT2_MANIFEST,
        {
            "schema_version": 1,
            "kind": "invalid_endpoint_consumer_attempt_manifest",
            "classification": "pre_generation_generate_schema_adapter_defect",
            "root": str(ATTEMPT2_ROOT),
            "files": manifest,
        },
    )

    command = [
        str(LAB_ENDPOINT_PAIR),
        "run",
        "--workload",
        str(WORKLOAD),
        "--output-dir",
        str(FRESH_ROOT),
        "--control-url",
        PUBLIC_URL,
        "--candidate-url",
        PUBLIC_URL,
        "--arm-order",
        "control",
        "--concurrency",
        "32",
        "--timeout-seconds",
        "900",
    ]
    tunnel: subprocess.Popen[bytes] | None = None
    adapter: ThreadingHTTPServer | None = None
    adapter_thread: threading.Thread | None = None
    rule_installed = False
    returncode: int | None = None
    exception: str | None = None
    try:
        tunnel = subprocess.Popen(SSH)
        wait_for_tunnel(tunnel)
        adapter = ThreadingHTTPServer(("127.0.0.1", ADAPTER_PORT), GenerateAdapter)
        adapter_thread = threading.Thread(target=adapter.serve_forever, daemon=True)
        adapter_thread.start()
        subprocess.run(["iptables", *IPTABLES_RULE], check=True)
        rule_installed = True
        with STDOUT_PATH.open("wb") as stdout, STDERR_PATH.open("wb") as stderr:
            completed = subprocess.run(
                command,
                cwd=PROJECT.parents[6],
                stdout=stdout,
                stderr=stderr,
                check=False,
            )
        returncode = completed.returncode
    except Exception as error:
        exception = f"{type(error).__name__}: {error}"
    finally:
        if rule_installed:
            subprocess.run(["iptables", *IPTABLES_DELETE], check=True)
        if adapter is not None:
            adapter.shutdown()
            adapter.server_close()
        if adapter_thread is not None:
            adapter_thread.join(timeout=10)
        if tunnel is not None and tunnel.poll() is None:
            tunnel.send_signal(signal.SIGTERM)
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait(timeout=10)

    fresh_run_path = FRESH_ROOT / "run.json"
    fresh_run = json.loads(fresh_run_path.read_text()) if fresh_run_path.exists() else {}
    fresh_metadata = (
        [
            json.loads(path.read_text())
            for path in sorted(
                (FRESH_ROOT / "arms" / "control" / "requests").glob(
                    "*/metadata.json"
                )
            )
        ]
        if FRESH_ROOT.exists()
        else []
    )
    valid = bool(
        returncode == 0
        and fresh_run.get("complete")
        and fresh_run.get("artifact_complete")
        and fresh_run.get("all_requests_successful")
        and fresh_run.get("progress", {}).get("control", {}).get("complete_requests")
        == 32
        and fresh_run.get("progress", {}).get("control", {}).get(
            "successful_requests"
        )
        == 32
        and len(fresh_metadata) == 32
        and all(row.get("output_text") for row in fresh_metadata)
        and all(row.get("finish_reason") == "length" for row in fresh_metadata)
        and all(
            row.get("usage", {}).get("completion_tokens") == 358
            for row in fresh_metadata
        )
    )
    if valid:
        os.rename(FRESH_ROOT, PAIR_ROOT)

    evidence = {
        "schema_version": 1,
        "kind": "endpoint_consumer_openai_completions_adapter_repair",
        "generation": GENERATION,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "decision": "amend only the invalid endpoint adapter operation",
        "hypothesis": (
            "The unchanged token-ID payload matches the installed OpenAI "
            "CompletionRequest schema; rewriting only the bound URL's root path "
            "to /v1/completions will reach model generation."
        ),
        "scope": "endpoint_consumer_only",
        "sample_limit": 1,
        "attempt2": {
            "classification": "pre_generation_generate_schema_adapter_defect",
            "complete_requests": 32,
            "successful_requests": 0,
            "token_outputs": 0,
            "run": digest(attempt2_run_path),
            "manifest": digest(ATTEMPT2_MANIFEST),
        },
        "scientific_contract": {
            "arm_order": ["control"],
            "concurrency": 32,
            "endpoint_url": PUBLIC_URL,
            "endpoint_url_sha256": hashlib.sha256(PUBLIC_URL.encode()).hexdigest(),
            "timeout_seconds": 900,
            "workload": digest(WORKLOAD),
        },
        "transport_amendment": {
            "ssh_destination": f"root@{PUBLIC_HOST}:40070",
            "forward": f"127.0.0.1:{TUNNEL_PORT}->127.0.0.1:{REMOTE_PORT}",
            "redirect_destination": f"{PUBLIC_HOST}:{PUBLIC_PORT}",
            "adapter": f"127.0.0.1:{ADAPTER_PORT}",
            "path_mapping": {"/": "/v1/completions"},
            "redirect_removed": rule_installed,
            "forwarded_requests": GenerateAdapter.forwarded_requests,
            "source_paths": GenerateAdapter.source_paths,
        },
        "command": command,
        "returncode": returncode,
        "exception": exception,
        "valid_interpretable_sample": valid,
        "result": (
            digest(PAIR_ROOT / "run.json")
            if valid
            else (digest(fresh_run_path) if fresh_run_path.exists() else None)
        ),
        "stdout": digest(STDOUT_PATH) if STDOUT_PATH.exists() else None,
        "stderr": digest(STDERR_PATH) if STDERR_PATH.exists() else None,
    }
    write_json_atomic(EVIDENCE_PATH, evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
