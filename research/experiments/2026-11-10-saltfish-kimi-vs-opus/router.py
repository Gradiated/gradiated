#!/usr/bin/env python3
"""Local Anthropic-Messages router for running Saltfish Studio's seats on two backends.

Saltfish's llm.ts sends every claude-* seat through @anthropic-ai/sdk. Point the studio at
this router (ANTHROPIC_BASE_URL=http://127.0.0.1:8899) and:

  model == KIMI_ALIAS  -> Gradiated gateway (api.gradiated.com), model rewritten to KIMI_MODEL
  any other model      -> CLIProxyAPI subscription proxy (Opus 5.5 etc.)

Streams pass through untouched except the model name in message_start. Every call's model,
status, latency and usage are appended to calls.jsonl (no prompts, no keys).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KIMI_ALIAS = os.environ.get("KIMI_ALIAS", "claude-kimi-k3-1-pro")
KIMI_MODEL = os.environ.get("KIMI_MODEL", "moonshotai/kimi-k3.1-pro")
GATEWAY = os.environ.get("KIMI_GATEWAY", "https://api.gradiated.com")
PROXY = os.environ.get("CLIPROXY_URL", "http://100.105.48.19:8317")
PROXY_KEY_FILE = os.environ.get(
    "CLIPROXY_KEY_FILE", "/root/.t3/worktrees/workspace/t3-cb1453dc/.agents/runtime/cliproxy/client.key")
LOG = Path(os.environ.get("ROUTER_LOG", "/root/.t3/worktrees/workspace/t3-aeba9a3a/.agents/runtime/saltfish_compare/calls.jsonl"))
PORT = int(os.environ.get("ROUTER_PORT", "8899"))


def gateway_key() -> str:
    if os.environ.get("AI_GATEWAY_GRADIATED_API_KEY"):
        return os.environ["AI_GATEWAY_GRADIATED_API_KEY"]
    out = subprocess.run(["aws", "--profile", "gradiated-readonly", "secretsmanager", "get-secret-value",
                          "--secret-id", "gradiated/dev/env", "--query", "SecretString", "--output", "text"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)["AI_GATEWAY_GRADIATED_API_KEY"]


GW_KEY = gateway_key()
PX_KEY = Path(PROXY_KEY_FILE).read_text().strip()
LOCK = threading.Lock()
LOG.parent.mkdir(parents=True, exist_ok=True)
PASS_HEADERS = {"anthropic-version", "anthropic-beta", "content-type", "accept"}


def log(rec: dict) -> None:
    with LOCK, LOG.open("a") as f:
        f.write(json.dumps(rec) + "\n")


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        self._forward(None)

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        self._forward(self.rfile.read(n))

    def _forward(self, raw: bytes | None):
        t0 = time.time()
        body = json.loads(raw) if raw else None
        model = (body or {}).get("model", "")
        kimi = model == KIMI_ALIAS
        if kimi:
            body["model"] = KIMI_MODEL
            raw = json.dumps(body).encode()
            base, auth = GATEWAY, {"x-api-key": GW_KEY}
        else:
            base, auth = PROXY, {"x-api-key": PX_KEY}
        hdrs = {k: v for k, v in self.headers.items() if k.lower() in PASS_HEADERS}
        hdrs.update(auth)
        req = urllib.request.Request(base + self.path, data=raw, method=self.command, headers=hdrs)
        rec = {"t": round(t0, 3), "path": self.path, "model": model, "backend": "gateway" if kimi else "cliproxy",
               "stream": bool((body or {}).get("stream")), "seat_hint": (body or {}).get("metadata", {}).get("user_id")}
        usage: dict = {}
        try:
            resp = urllib.request.urlopen(req, timeout=3600)
            status = resp.status
        except urllib.error.HTTPError as e:
            resp, status = e, e.code
        except Exception as e:  # connection failure -> 502 in Anthropic error shape
            msg = json.dumps({"type": "error", "error": {"type": "api_error", "message": f"router: {e}"}}).encode()
            self.send_response(502)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            log({**rec, "status": 502, "error": str(e)[:500], "s": round(time.time() - t0, 1)})
            return
        ctype = resp.headers.get("content-type", "")
        self.send_response(status)
        for k, v in resp.headers.items():
            if k.lower() in ("content-type", "request-id", "x-request-id", "retry-after"):
                self.send_header(k, v)
        err = None
        if "text/event-stream" in ctype:
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            buf = b""
            try:
                for line in resp:
                    if kimi and line.startswith(b"data:") and b'"message_start"' in line:
                        line = line.replace(KIMI_MODEL.encode(), KIMI_ALIAS.encode())
                    if line.startswith(b"data:"):
                        try:
                            ev = json.loads(line[5:])
                            if ev.get("type") == "message_start":
                                usage.update(ev["message"].get("usage") or {})
                            elif ev.get("type") == "message_delta":
                                usage.update(ev.get("usage") or {})
                                rec["stop_reason"] = (ev.get("delta") or {}).get("stop_reason")
                            elif ev.get("type") == "error":
                                err = ev.get("error")
                        except Exception:
                            pass
                    buf += line
                    if line in (b"\n", b"\r\n") or len(buf) > 8192:
                        self.wfile.write(f"{len(buf):x}\r\n".encode() + buf + b"\r\n")
                        self.wfile.flush()
                        buf = b""
                if buf:
                    self.wfile.write(f"{len(buf):x}\r\n".encode() + buf + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError) as e:
                err = f"client gone: {e}"
        else:
            data = resp.read()
            if kimi:
                data = data.replace(KIMI_MODEL.encode(), KIMI_ALIAS.encode())
            try:
                j = json.loads(data)
                usage.update(j.get("usage") or {})
                rec["stop_reason"] = j.get("stop_reason")
                if status >= 400:
                    err = j.get("error") or j
            except Exception:
                pass
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        log({**rec, "status": status, "s": round(time.time() - t0, 1), "usage": usage,
             **({"error": str(err)[:1500]} if err else {})})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"router on 127.0.0.1:{PORT}: {KIMI_ALIAS} -> {GATEWAY} ({KIMI_MODEL}); else -> {PROXY}", flush=True)
    srv.serve_forever()
