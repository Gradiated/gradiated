import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from artifacts import strict_json
from loader import CapacityError, CartridgeNotApplied


def create_server(loader, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def respond(self, status, value, content_type="application/json"):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.respond(200 if loader.ready else 503, {"ready": loader.ready})
            elif self.path == "/internal/adapters":
                self.respond(200, loader.status())
            elif self.path == "/internal/adapters/metrics":
                self.respond(200, loader.metrics(), "text/plain; version=0.0.4")
            elif self.path not in ("/internal/adapters", "/internal/adapters/metrics"):
                self.respond(404, {"error": "not_found"})

        def do_POST(self):
            if self.path not in (
                "/internal/adapters/prepare",
                "/internal/adapters/resolve",
                "/internal/adapters/probe",
            ):
                self.respond(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if self.headers.get("Transfer-Encoding") or not 0 < size <= 1024 * 1024:
                    raise ValueError("Invalid request size")
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ValueError("Truncated request")
                body = strict_json(data)
                if (
                    not isinstance(body["name"], str)
                    or not isinstance(body["workspace_id"], str)
                    or not body["workspace_id"]
                ):
                    raise ValueError("Invalid adapter identity")
                if self.path.endswith("/resolve"):
                    files = loader.resolve_version(body["name"], body["workspace_id"])
                    self.respond(200, files)
                    return
                action = (
                    loader.prepare_version
                    if self.path.endswith("/prepare")
                    else loader.probe
                )
                action(body["name"], body["workspace_id"])
                self.respond(200, {"boot_id": loader.boot_id, "ready": True})
            except CapacityError:
                self.respond(503, {"error": "capacity_unavailable"})
            except CartridgeNotApplied:
                self.respond(422, {"error": "cartridge_not_applied"})
            except LookupError:
                self.respond(503, {"error": "adapter_unavailable"})
            except (ValueError, KeyError, TypeError):
                self.respond(422, {"error": "invalid_adapter"})
            except (OSError, RuntimeError, http.client.HTTPException):
                self.respond(503, {"error": "preparation_failed"})

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        permits = threading.BoundedSemaphore(8)

        def process_request(self, request, address):
            if not self.permits.acquire(blocking=False):
                try:
                    request.sendall(
                        b"HTTP/1.0 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n"
                    )
                finally:
                    self.shutdown_request(request)
                return
            try:
                super().process_request(request, address)
            except Exception:
                self.permits.release()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                self.permits.release()

        def handle_error(self, *_args):
            pass

    return Server(("127.0.0.1", port), Handler)
