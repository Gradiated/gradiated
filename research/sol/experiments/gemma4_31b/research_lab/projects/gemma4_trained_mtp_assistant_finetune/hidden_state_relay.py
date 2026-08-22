#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "GemmaHiddenStateRelay/1"

    def _resolved(self) -> Path:
        root = self.server.root.resolve()  # type: ignore[attr-defined]
        relative = unquote(urlsplit(self.path).path).lstrip("/")
        if not relative or relative == "health":
            raise ValueError("not a hidden-state path")
        candidate = (root / relative).resolve()
        if root not in candidate.parents:
            raise ValueError("path escapes relay root")
        if candidate.suffix != ".safetensors":
            raise ValueError("only safetensors artifacts are served")
        return candidate

    def do_GET(self) -> None:  # noqa: N802
        if urlsplit(self.path).path == "/health":
            body = b'{"status":"ok"}\n'
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        try:
            path = self._resolved()
            data = path.read_bytes()
        except (ValueError, FileNotFoundError):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        digest = hashlib.sha256(data).hexdigest()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", digest)
        self.end_headers()
        self.wfile.write(data)

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            path = self._resolved()
            path.unlink()
        except (ValueError, FileNotFoundError):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        record = {
            "client": self.client_address[0],
            "message": format % args,
            "pid": os.getpid(),
        }
        print(json.dumps(record, sort_keys=True), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), RelayHandler)
    server.root = args.root  # type: ignore[attr-defined]
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
