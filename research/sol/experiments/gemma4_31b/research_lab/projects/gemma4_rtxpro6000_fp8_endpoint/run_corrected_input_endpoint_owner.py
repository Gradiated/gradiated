#!/usr/bin/env python3
"""Durable owner for the single director-bound corrected-input c32 sample."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parent.parent
FACTORY = ROOT.parents[5] / "factory"
PAIR = FACTORY / "tools" / "lab-endpoint-pair"
POOL = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
BENCH = "rtxpro6000-gemma4-fp8-f4nbtoufbwf66f"
PROJECT = "gemma4_rtxpro6000_fp8_endpoint"
CLAIMED_AT = "2026-07-29T05:22:44.337347Z"
DEADLINE = dt.datetime(2026, 7, 29, 6, 25, tzinfo=dt.timezone.utc)
HOST, SSH_PORT, REMOTE_PORT, LOCAL_PORT, TUNNEL_PORT = "213.192.6.70", 40070, 19123, 19124, 19125
ARTIFACT = ROOT / "artifacts" / "rtxpro6000-corrected-input-20260729t0523z"
STATUS = ROOT / "STATUS.json"
WORKLOAD = ROOT / "inputs" / "c32_requests.jsonl"
BINDING = ROOT / "DIRECTOR_RTXPRO6000_RESIDENT_SERVER_CORRECTED_INPUT_ENDPOINT_RECLAIM_20260729T0517Z.json"
PACKET = ROOT / "RTXPRO6000_FP8_EXECUTION_PACKET.json"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, path)


def ident(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def run(command: list[str], *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def heartbeat_loop(stop: threading.Event) -> None:
    while not stop.wait(45):
        result = run([*POOL, "heartbeat", "--project", PROJECT, "--bench", BENCH])
        (ARTIFACT / "heartbeat.log").open("a").write(f"{now()} rc={result.returncode} {result.stdout.strip()} {result.stderr.strip()}\n")


class Adapter(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests = 0
    lock = threading.Lock()

    def do_POST(self) -> None:
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            incoming = json.loads(raw)
            prompt = incoming["prompt"]
            if not (isinstance(prompt, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in prompt)):
                raise ValueError("frozen prompt must be flat integer token IDs")
            sampling = {
                "max_new_tokens": incoming["max_tokens"],
                "min_new_tokens": incoming["min_tokens"],
                "ignore_eos": incoming["ignore_eos"],
                "temperature": incoming["temperature"],
                "sampling_seed": incoming["seed"],
            }
            if sampling != {"max_new_tokens": 358, "min_new_tokens": 358, "ignore_eos": True, "temperature": 0, "sampling_seed": 20260718}:
                raise ValueError("frozen sampling contract mismatch")
            native = {"input_ids": prompt, "sampling_params": sampling, "stream": True}
        except Exception as error:
            self.send_error(400, str(error))
            return
        with type(self).lock:
            type(self).requests += 1
        upstream = HTTPConnection("127.0.0.1", TUNNEL_PORT, timeout=900)
        try:
            upstream.request("POST", "/generate", body=json.dumps(native).encode(), headers={"Content-Type": "application/json", "Accept": "text/event-stream"})
            response = upstream.getresponse()
            self.send_response(response.status, response.reason)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            final_seen = False
            for line in response:
                if not line.startswith(b"data:"):
                    continue
                payload = line[5:].strip()
                if payload == b"[DONE]":
                    continue
                native_event = json.loads(payload)
                meta = native_event.get("meta_info", {})
                finish = meta.get("finish_reason")
                finish_type = finish.get("type") if isinstance(finish, dict) else finish
                event = {"choices": [{"text": native_event.get("text") or "", "finish_reason": finish_type}], "native": {"output_token_ids": native_event.get("output_ids", [])}}
                if finish_type is not None:
                    event["usage"] = {"prompt_tokens": meta.get("prompt_tokens"), "completion_tokens": meta.get("completion_tokens"), "total_tokens": (meta.get("prompt_tokens") or 0) + (meta.get("completion_tokens") or 0)}
                    final_seen = True
                self.wfile.write(b"data: " + json.dumps(event, separators=(",", ":")).encode() + b"\n\n")
                self.wfile.flush()
            if not final_seen:
                self.wfile.write(b"data: {\"error\":{\"message\":\"native stream omitted terminal finish\"}}\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        finally:
            upstream.close()
            self.close_connection = True

    def log_message(self, *_: object) -> None:
        return


def update_status(active: dict[str, object] | None, summary: str) -> None:
    data = json.loads(STATUS.read_text())
    data["actual_spend_usd"] = 9.45
    data["active_session"] = active
    data["summary"] = summary
    data["updated_at_utc"] = now()
    atomic(STATUS, data)


def main() -> int:
    ARTIFACT.mkdir(parents=True, exist_ok=False)
    if hashlib.sha256(BINDING.read_bytes()).hexdigest() != "c59a2c914fa75b53e369cf3408b3310f503a3d1754caf6a28f83fd4cef4c9423":
        raise RuntimeError("binding digest mismatch")
    if hashlib.sha256(PACKET.read_bytes()).hexdigest() != "f7c932bb6684ceaed67092123a2737ba14234c89dcf23aa878683fac080fc1b1":
        raise RuntimeError("packet digest mismatch")
    atomic(ARTIFACT / "CORRECTED_INPUT_ADAPTER.json", {"native_route": "/generate", "input_field": "input_ids", "sampling_params": {"max_new_tokens": 358, "min_new_tokens": 358, "ignore_eos": True, "temperature": 0, "sampling_seed": 20260718}, "source": ident(Path(__file__))})
    stop = threading.Event()
    heartbeat = threading.Thread(target=heartbeat_loop, args=(stop,), daemon=True)
    heartbeat.start()
    tunnel = subprocess.Popen(["ssh", "-F", "/dev/null", "-i", "/root/.config/nebius/glm-campaign/ssh_ed25519", "-o", "UserKnownHostsFile=/root/.config/runpod/gemma4/known_hosts", "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes", "-p", str(SSH_PORT), "-N", "-L", f"127.0.0.1:{TUNNEL_PORT}:127.0.0.1:{REMOTE_PORT}", f"root@{HOST}"])
    server = None
    terminal: dict[str, object] = {}
    try:
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if tunnel.poll() is not None:
                raise RuntimeError(f"ssh_tunnel_exit_{tunnel.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", TUNNEL_PORT), timeout=1): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError("ssh_tunnel_timeout")
        server = ThreadingHTTPServer(("127.0.0.1", LOCAL_PORT), Adapter)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        atomic(ARTIFACT / "CORRECTED_INPUT_SCIENCE_STARTED.json", {"at_utc": now(), "contract": "one true concurrent-c32 control arm", "workload": ident(WORKLOAD), "adapter": ident(ARTIFACT / "CORRECTED_INPUT_ADAPTER.json")})
        command = [str(PAIR), "run", "--workload", str(WORKLOAD), "--output-dir", str(ARTIFACT / "endpoint-pair"), "--control-url", f"http://127.0.0.1:{LOCAL_PORT}", "--candidate-url", f"http://127.0.0.1:{LOCAL_PORT}", "--arm-order", "control", "--concurrency", "32", "--timeout-seconds", str(max(1, int((DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds() - 60)))]
        result = run(command, timeout=max(1, int((DEADLINE - dt.datetime.now(dt.timezone.utc)).total_seconds() - 20)))
        (ARTIFACT / "endpoint-pair.stdout").write_text(result.stdout)
        (ARTIFACT / "endpoint-pair.stderr").write_text(result.stderr)
        pair = json.loads((ARTIFACT / "endpoint-pair" / "run.json").read_text()) if (ARTIFACT / "endpoint-pair" / "run.json").exists() else {}
        rows = [json.loads(p.read_text()) for p in sorted((ARTIFACT / "endpoint-pair" / "arms" / "control" / "requests").glob("*/metadata.json"))]
        valid = result.returncode == 0 and len(rows) == 32 and pair.get("all_requests_successful") is True and all(r.get("token_ids") and len(r["token_ids"]) == 358 and r.get("usage", {}).get("completion_tokens") == 358 and not r.get("error") for r in rows)
        terminal = {"schema_version": 1, "kind": "corrected_input_rtxpro6000_fp8_endpoint_terminal", "classification": "valid_corrected_input_endpoint_sample" if valid else "invalid_corrected_input_endpoint_attempt", "science_consumed": True, "started_marker": ident(ARTIFACT / "CORRECTED_INPUT_SCIENCE_STARTED.json"), "binding": ident(BINDING), "invalid_predecessor_sha256": "c79a2f6067cf85b9e073d2bf9bc39a1906d84dfe3626887427dcf0c1f16ab9f8", "adapter": ident(ARTIFACT / "CORRECTED_INPUT_ADAPTER.json"), "pair_run": ident(ARTIFACT / "endpoint-pair" / "run.json") if pair else None, "returncode": result.returncode, "requests": len(rows), "successful_requests": sum(bool(r.get("successful")) for r in rows), "generated_token_rows": sum(bool(r.get("token_ids") and len(r["token_ids"]) == 358) for r in rows), "wall_seconds": max((r.get("latency_seconds", 0) for r in rows), default=0), "service_seconds_per_request": sum(r.get("latency_seconds", 0) for r in rows) / 32 if len(rows) == 32 else None, "target_seconds_per_request": 1.048637203302411, "actual_spend_usd": 9.45, "adapter_requests": Adapter.requests, "finished_at_utc": now()}
    except Exception as error:
        terminal = {"schema_version": 1, "kind": "corrected_input_rtxpro6000_fp8_endpoint_terminal", "classification": "invalid_corrected_input_endpoint_attempt", "science_consumed": (ARTIFACT / "CORRECTED_INPUT_SCIENCE_STARTED.json").exists(), "error": f"{type(error).__name__}: {error}", "binding": ident(BINDING), "actual_spend_usd": 9.45, "finished_at_utc": now()}
    finally:
        if server: server.shutdown(); server.server_close()
        if tunnel.poll() is None: tunnel.send_signal(signal.SIGTERM); tunnel.wait(timeout=15)
        stop.set(); heartbeat.join(timeout=2)
    atomic(ARTIFACT / "CORRECTED_INPUT_RTXPRO6000_FP8_ENDPOINT_TERMINAL.json", terminal)
    update_status(None, f"Corrected-input endpoint owner completed: {terminal['classification']}; terminal {ARTIFACT / 'CORRECTED_INPUT_RTXPRO6000_FP8_ENDPOINT_TERMINAL.json'}.")
    contents = {"state": "resident_stock_fp8_endpoint_corrected_input_terminal", "server_state": "Healthy resident SGLang server PID 16036 intentionally preserved; review corrected-input terminal before reuse.", "artifacts": str(ARTIFACT / "CORRECTED_INPUT_RTXPRO6000_FP8_ENDPOINT_TERMINAL.json"), "project": PROJECT, "packet_sha256": "f7c932bb6684ceaed67092123a2737ba14234c89dcf23aa878683fac080fc1b1"}
    atomic(ARTIFACT / "release-contents.json", contents)
    released = run([*POOL, "release", "--project", PROJECT, "--bench", BENCH, "--expected-claimed-at", CLAIMED_AT, "--condition", "maintenance", "--contents", str(ARTIFACT / "release-contents.json")])
    (ARTIFACT / "release.log").write_text(released.stdout + released.stderr)
    return 0 if terminal.get("classification") == "valid_corrected_input_endpoint_sample" else 1


if __name__ == "__main__":
    raise SystemExit(main())
