import hmac
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from artifacts import strict_json
from manager import CapacityError


def create_server(manager, port, control_token):
    if not control_token:
        raise ValueError("Missing adapter control token")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def respond(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Chunked requests are unsupported")
            size = int(self.headers.get("Content-Length", "0"))
            limit = 1024 * 1024 if self.path.startswith("/internal/") else 32_000_000
            if not 0 < size <= limit:
                raise ValueError("Invalid request size")
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError("Truncated request")
            return strict_json(body)

        def control(self):
            if not hmac.compare_digest(
                self.headers.get("X-Gradiated-Adapter-Control", ""), control_token
            ):
                self.respond(403, {"error": "forbidden"})
                return False
            return True

        def do_GET(self):
            if self.path == "/internal/adapters":
                if self.control():
                    self.respond(200, manager.status())
                return
            if self.path in ("/metrics", "/v1/models"):
                connection = http.client.HTTPConnection(
                    "127.0.0.1", manager.engine_port, timeout=5
                )
                try:
                    connection.request("GET", self.path)
                    response = connection.getresponse()
                    body = response.read(8 * 1024 * 1024 + 1)
                    if len(body) > 8 * 1024 * 1024:
                        raise ValueError("Oversized runtime response")
                    self.send_response(response.status)
                    self.send_header(
                        "Content-Type",
                        response.getheader("Content-Type", "application/json"),
                    )
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (OSError, ValueError, http.client.HTTPException):
                    self.respond(503, {"error": "runtime_unavailable"})
                finally:
                    connection.close()
                return
            if self.path != "/health":
                self.respond(404, {"error": "not_found"})
                return
            connection = http.client.HTTPConnection(
                "127.0.0.1", manager.engine_port, timeout=5
            )
            try:
                connection.request("GET", "/health")
                response = connection.getresponse()
                self.respond(
                    200
                    if response.status == 200 and not manager.failed and manager.ready
                    else 503,
                    {
                        "ready": response.status == 200
                        and not manager.failed
                        and manager.ready
                    },
                )
            except (OSError, http.client.HTTPException):
                self.respond(503, {"ready": False})
            finally:
                connection.close()

        def operation(self, action):
            try:
                action(self.body())
                self.respond(200, {"boot_id": manager.boot_id, "ready": True})
            except CapacityError:
                self.respond(503, {"error": "capacity_unavailable"})
            except LookupError:
                self.respond(503, {"error": "adapter_unavailable"})
            except (ValueError, KeyError, TypeError):
                self.respond(422, {"error": "invalid_adapter"})
            except (OSError, RuntimeError, http.client.HTTPException):
                self.respond(503, {"error": "preparation_failed"})

        def do_POST(self):
            if self.path == "/internal/adapters/probe":
                if self.control():
                    self.operation(lambda body: manager.probe(body["name"]))
                return
            if self.path == "/internal/adapters/prepare":
                self.operation(
                    lambda body: manager.prepare(body["name"], body["workspace_id"])
                )
                return
            if self.path not in ("/v1/chat/completions", "/v1/completions"):
                self.respond(404, {"error": "not_found"})
                return
            connection = None
            started = False
            try:
                body = self.body()
                workspace_id = self.headers.get("X-Gradiated-Workspace")
                if body["model"].startswith("ft-") and not workspace_id:
                    raise ValueError("Missing workspace identity")
                with manager.request(body["model"], workspace_id):
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", manager.engine_port, timeout=30
                    )
                    try:
                        connection.request(
                            "POST",
                            self.path,
                            json.dumps(body),
                            {"Content-Type": "application/json"},
                        )
                        upstream = connection.getresponse()
                        self.send_response(upstream.status)
                        self.send_header(
                            "Content-Type",
                            upstream.getheader("Content-Type", "application/json"),
                        )
                        self.end_headers()
                        started = True
                        deadline = time.monotonic() + 630
                        while chunk := upstream.read1(65536):
                            if time.monotonic() > deadline:
                                raise TimeoutError("Generation deadline exceeded")
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    finally:
                        connection.close()
            except (CapacityError, LookupError):
                if not started:
                    self.respond(503, {"error": "adapter_or_capacity_unavailable"})
            except (ValueError, KeyError, TypeError):
                if not started:
                    self.respond(400, {"error": "invalid_request"})
            except (OSError, RuntimeError, http.client.HTTPException):
                if not started:
                    self.respond(503, {"error": "runtime_unavailable"})
            finally:
                if connection:
                    connection.close()

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        permits = threading.BoundedSemaphore(manager.config["max_concurrency"] + 8)

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
