import json
import logging
import os
import re
import signal
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from runtime import TrainingRuntime

logger = logging.getLogger(__name__)


class Host:
    def __init__(self):
        self.trainer = TrainingRuntime(
            os.environ["GRADIATED_RUNTIME_DIR"] + "/training",
            json.loads(
                os.environ.get("TRAINING_RECIPE_JSON")
                or Path(__file__).with_name("recipe.json").read_text()
            ),
        )
        self.lock = threading.Lock()
        self.job = None
        self.deadline = time.monotonic() + 24 * 60 * 60
        self.lease = time.monotonic() + 15 * 60
        self.allocation_id = os.environ["GRADIATED_POD_UID"]
        threading.Thread(target=self.watchdog, daemon=True).start()

    def renew(self, allocation_id):
        with self.lock:
            now = time.monotonic()
            if allocation_id != self.allocation_id:
                raise ValueError("Wrong allocation")
            if self.trainer.stop.is_set() or now >= min(self.lease, self.deadline):
                raise ValueError("Reservation expired")
            self.lease = min(now + 180, self.deadline)

    def start(self, command):
        identifier = command.get("id", "")
        if not re.fullmatch(r"[a-z0-9-]{1,100}", identifier):
            raise ValueError("Invalid operation id")
        with self.lock:
            if self.trainer.stop.is_set() or time.monotonic() >= min(
                self.lease, self.deadline
            ):
                raise ValueError("Reservation expired")
            if self.job and self.job["id"] == identifier:
                return
            if self.job and self.job["status"] == "running":
                raise ValueError("Host is busy")
            self.job = {
                "id": identifier,
                "status": "running",
                "events": [],
                "result": None,
            }
        threading.Thread(target=self.run, args=(command,), daemon=True).start()

    def emit(self, event):
        if event["type"] not in {
            "trainer_progress",
            "trainer_checkpoint",
            "note",
            "evaluation_progress",
        }:
            name = event["type"]
            event = {
                "type": "trainer_observation",
                "name": name,
                "message": event.get("message", name.replace("_", " ")),
                "level": "error" if name == "trainer_failed" else "info",
                "details": {
                    key: value for key, value in event.items() if key != "type"
                },
            }
        with self.lock:
            if len(self.job["events"]) >= 10000:
                raise ValueError("Event limit exceeded")
            self.job["events"].append(event)

    def run(self, command):
        try:
            result = self.trainer.run(command, self.emit)
            with self.lock:
                self.job.update(status="complete", result=result)
        except Exception as error:
            logger.exception("Training operation failed")
            code = (
                "cancelled" if isinstance(error, InterruptedError) else "trainer_failed"
            )
            failure = {"error_type": type(error).__name__}
            if isinstance(error, urllib.error.URLError) and isinstance(
                error.reason, BaseException
            ):
                failure["cause_type"] = type(error.reason).__name__
            if isinstance(error, urllib.error.HTTPError):
                failure["upstream_status"] = error.code
            self.emit(
                {
                    "type": "trainer_failed",
                    "error_code": "internal",
                    **failure,
                    "message": code,
                }
            )
            with self.lock:
                self.job.update(status="failed", result=None)

    def poll(self, identifier, offset):
        with self.lock:
            if not self.job or self.job["id"] != identifier:
                raise LookupError("Operation not found")
            return {
                "id": identifier,
                "status": self.job["status"],
                "events": self.job["events"][offset : offset + 100],
                "next": min(offset + 100, len(self.job["events"])),
                "total": len(self.job["events"]),
                "result": self.job["result"],
            }

    def watchdog(self):
        while True:
            time.sleep(1)
            with self.lock:
                expired = time.monotonic() >= min(self.lease, self.deadline)
                if expired:
                    self.trainer.stop.set()
            if expired:
                time.sleep(10)
                os._exit(75)


def serve():
    host = Host()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, value):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.respond(200, {"ready": True})
                return
            match = re.fullmatch(
                r"/operations/([a-z0-9-]{1,100})\?after=(\d{1,5})", self.path
            )
            if not match:
                self.respond(404, {"error": "not_found"})
                return
            try:
                self.respond(200, host.poll(match[1], int(match[2])))
            except LookupError:
                self.respond(404, {"error": "not_found"})

        def do_POST(self):
            if self.path not in {"/operations", "/reservation"}:
                self.respond(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("Invalid request size")
                command = json.loads(self.rfile.read(size))
                if self.path == "/reservation":
                    host.renew(command["allocation_id"])
                    self.respond(200, {"renewed": True})
                else:
                    host.start(command)
                    self.respond(202, {"id": command["id"]})
            except (ValueError, KeyError, TypeError):
                self.respond(400, {"error": "invalid_operation"})

    server = ThreadingHTTPServer(
        ("127.0.0.1", int(os.environ["RUNTIME_PORT"])), Handler
    )
    server.timeout = 1

    def stop(_signal, _frame):
        host.trainer.stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever(poll_interval=0.5)
    server.server_close()


if __name__ == "__main__":
    serve()
