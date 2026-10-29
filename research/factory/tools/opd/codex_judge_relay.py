#!/usr/bin/env python3
"""Serve judge completions from the Codex CLI (ChatGPT subscription) over a localhost HTTP endpoint.

The eval harness on the GPU host reaches this through an SSH reverse tunnel, so the ChatGPT credentials never
leave this machine. Each request runs one non-interactive, ephemeral `codex exec` in a read-only sandbox and
returns its last message. Requests are spread over the configured Codex homes (one per signed-in account) with a
per-account concurrency limit.

    codex_judge_relay.py --homes /root/.codex,/root/.codex-judge-b --per-home 6 --port 18777
    POST /complete {"prompt": "...", "model": "gpt-6.1-sol", "reasoning_effort": "medium"} -> {"text": "...", "usage": {...}}
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PREAMBLE = ("You are being used as an evaluation judge, not as a coding agent. Do not run commands or edit files. "
            "Read the task below and reply with only the requested output.\n\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--homes", required=True, help="comma-separated CODEX_HOME directories, one per account")
    p.add_argument("--per-home", type=int, default=6)
    p.add_argument("--port", type=int, default=18777)
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()

    homes = [h for h in args.homes.split(",") if h]
    gates = {h: threading.Semaphore(args.per_home) for h in homes}
    order = itertools.cycle(homes)
    lock = threading.Lock()
    counters = {h: {"ok": 0, "error": 0} for h in homes}

    def run(prompt: str, model: str, effort: str | None) -> dict:
        with lock:
            home = next(order)
        with gates[home], tempfile.TemporaryDirectory() as work:
            out = os.path.join(work, "last.txt")
            cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-C", work,
                   "-m", model, "-o", out]
            if effort:
                cmd += ["-c", f"model_reasoning_effort={effort}"]
            cmd.append("-")
            started = time.time()
            proc = subprocess.run(cmd, input=PREAMBLE + prompt, capture_output=True, text=True, timeout=args.timeout,
                                  env={**os.environ, "CODEX_HOME": home})
            text = open(out).read() if os.path.exists(out) else ""
            with lock:
                counters[home]["ok" if proc.returncode == 0 and text else "error"] += 1
            if proc.returncode != 0 or not text:
                raise RuntimeError(f"codex exit {proc.returncode}: {proc.stderr[-300:]}")
            return {"text": text, "usage": {"seconds": round(time.time() - started, 1), "account": homes.index(home)}}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep request contents out of logs
            pass

        def do_GET(self):
            body = json.dumps({"homes": len(homes), "counters": list(counters.values())}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            try:
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                res = run(req["prompt"], req.get("model", "gpt-6.1-sol"), req.get("reasoning_effort"))
                code, body = 200, res
            except Exception as error:  # noqa: BLE001 - surface as 502 so the caller retries
                code, body = 502, {"error": str(error)[:400]}
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
