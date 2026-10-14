import argparse
import http.server
import json
import socket
import threading
import time
import urllib.parse
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Disposable synthetic benchmark server; no model/customer data."
)
parser.add_argument("--token-file", required=True)
parser.add_argument("--public-port", type=int)
args = parser.parse_args()
TOKEN = Path(args.token_file).read_text().strip()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def setup(self):
        super().setup()
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def reply(self, data, status=200, kind="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            self.reply(b'{"error":"unauthorized"}', 401)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/healthz":
                self.reply(b'{"ok":true,"service":"tailscale-gpu-trial"}')
            elif path == "/stream":
                chunks = [
                    (
                        "data: "
                        + json.dumps({"sequence": i, "text": "synthetic token"})
                        + "\n\n"
                    ).encode()
                    for i in range(100)
                ] + [b"data: [DONE]\n\n"]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(sum(map(len, chunks))))
                self.end_headers()
                for x in chunks:
                    self.wfile.write(x)
                    self.wfile.flush()
                    time.sleep(0.02)
            elif path == "/blob":
                self.reply(b"x" * (16 * 1024 * 1024), kind="application/octet-stream")
            else:
                self.reply(b'{"error":"not_found"}', 404)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        if not self.allowed():
            return
        n = int(self.headers.get("Content-Length", 0))
        if n > 8 * 1024 * 1024:
            self.reply(b"{}", 413)
            return
        b = self.rfile.read(n)
        self.reply(json.dumps({"received": len(b)}).encode())


class Server(http.server.ThreadingHTTPServer):
    request_queue_size = 128


addresses = [("127.0.0.1", 8888)]
if args.public_port:
    addresses.append(("0.0.0.0", args.public_port))
for addr in addresses:
    s = Server(addr, Handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
print("Synthetic test server ready", flush=True)
threading.Event().wait()
