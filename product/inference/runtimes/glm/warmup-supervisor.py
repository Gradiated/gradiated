#!/usr/bin/env python3
"""Keep GLM admission closed until real requests qualify this runtime process."""
import concurrent.futures
import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

MODEL = "zai-org/GLM-5.3-Flash"
SHAPES = (32, 2048, 6033, 8192, 16384)
CONCURRENCIES = (1, 2, 4, 8, 16)


class Supervisor:
    def __init__(self, command, runtime_url="http://127.0.0.1:8000", timeout=1800):
        self.command = command
        self.runtime_url = runtime_url
        self.deadline = time.monotonic() + timeout
        self.child = None
        self.qualified = threading.Event()
        self.stopping = threading.Event()

    def remaining(self, limit):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or self.stopping.is_set():
            raise RuntimeError("startup deadline or shutdown reached")
        if self.child is not None and self.child.poll() is not None:
            raise RuntimeError("runtime exited")
        return min(limit, remaining)

    def health(self):
        if self.child is None or self.child.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(self.runtime_url + "/health", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def ready(self):
        return self.qualified.is_set() and not self.stopping.is_set() and self.health()

    def probe(self, words, timeout, output_tokens=64):
        # A unique first token prevents the qualification pass reusing warmup KV.
        prompt = uuid.uuid4().hex + " " + "warmup " * words + "\nReply with a numbered list."
        payload = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                              "stream": True, "max_tokens": output_tokens,
                              "stream_options": {"include_usage": True}}).encode()
        request = urllib.request.Request(self.runtime_url + "/v1/chat/completions", data=payload,
                                         headers={"Content-Type": "application/json"})
        started = time.monotonic()
        saw_output = False
        usage = None
        with urllib.request.urlopen(request, timeout=self.remaining(timeout)) as response:
            for line in response:
                self.remaining(timeout)
                if not line.startswith(b"data:"):
                    continue
                data = line[5:].strip()
                if data == b"[DONE]":
                    if not saw_output or not usage:
                        raise RuntimeError("warmup stream had no output or usage")
                    if usage.get("prompt_tokens", 0) < words:
                        raise RuntimeError("warmup prompt shorter than requested shape")
                    details = usage.get("prompt_tokens_details")
                    cached_tokens = details.get("cached_tokens") if isinstance(details, dict) else None
                    if type(cached_tokens) is not int or cached_tokens != 0:
                        raise RuntimeError("warmup qualification requires explicit zero cached prompt tokens")
                    return {"prompt_tokens": usage["prompt_tokens"],
                            "elapsed_seconds": round(time.monotonic() - started, 3)}
                event = json.loads(data)
                if "error" in event:
                    raise RuntimeError("warmup stream returned an error")
                if event.get("usage"):
                    usage = event["usage"]
                for choice in event.get("choices", []):
                    delta = choice.get("delta", {})
                    saw_output |= bool(delta.get("content") or delta.get("reasoning") or delta.get("reasoning_content"))
        raise RuntimeError("warmup stream ended without DONE")

    def probe_group(self, phase, shapes, timeout):
        print(json.dumps({"phase": phase, "concurrency": len(shapes), "event": "started"}), flush=True)
        barrier = threading.Barrier(len(shapes))
        def request(words):
            barrier.wait(timeout=self.remaining(5))
            result = self.probe(words, timeout, 128)
            print(json.dumps({"phase": phase, "concurrency": len(shapes), **result}), flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(shapes)) as pool:
            futures = [pool.submit(request, words) for words in shapes]
            for future in futures:
                future.result()

    def warmup(self):
        while not self.health():
            self.remaining(2)
            self.stopping.wait(1)
        # Finish all cold shapes before applying the customer's idle-time budget.
        for words in SHAPES:
            self.probe_group("cold_prompt", [words], 180)
        for concurrency in CONCURRENCIES:
            self.probe_group("cold_concurrency", [32] * concurrency, 180)
        for words in SHAPES:
            self.probe_group("qualify_mixed_prompt", [words, 32], 25)
        for concurrency in CONCURRENCIES:
            self.probe_group("qualify_concurrency", [32] * concurrency, 25)
        if not self.health():
            raise RuntimeError("runtime unhealthy after warmup")
        self.remaining(1)
        self.qualified.set()
        print("GLM startup qualification passed through 16k prompt words and concurrency 16", flush=True)

    def stop(self, signum=signal.SIGTERM):
        self.stopping.set()
        self.qualified.clear()
        if self.child is not None:
            try:
                os.killpg(self.child.pid, signum)
            except ProcessLookupError:
                pass

    def run(self, port=8010):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler(self))
        self.child = subprocess.Popen(self.command, start_new_session=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *_: self.stop())
        signal.signal(signal.SIGINT, lambda *_: self.stop(signal.SIGINT))
        failure = []

        def qualify():
            try:
                self.warmup()
            except Exception as error:
                failure.append(type(error).__name__)
                print("GLM startup qualification failed: " + type(error).__name__, flush=True)
                self.stop()

        threading.Thread(target=qualify, daemon=True).start()
        try:
            while self.child.poll() is None and not self.stopping.wait(0.25):
                if not self.qualified.is_set() and time.monotonic() >= self.deadline:
                    failure.append("StartupDeadline")
                    self.stop()
            self.stop()
            try:
                result = self.child.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(self.child.pid, signal.SIGKILL)
                result = self.child.wait(timeout=5)
            return 1 if failure else result
        finally:
            self.qualified.clear()
            server.shutdown()
            server.server_close()


def handler(supervisor):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                code, body = (200, b"ready\n") if supervisor.ready() else (503, b"warming or unhealthy\n")
            elif self.path == "/metrics":
                try:
                    with urllib.request.urlopen(supervisor.runtime_url + "/metrics", timeout=2) as response:
                        code, body = response.status, response.read(4 * 1024 * 1024)
                except Exception:
                    code, body = 503, b"runtime metrics unavailable\n"
            else:
                code, body = 404, b"not found\n"
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass
    return Handler


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: warmup-supervisor.py command [args...]")
    raise SystemExit(Supervisor(sys.argv[1:], runtime_url=os.environ.get("RUNTIME_URL", "http://127.0.0.1:8000")).run(
        port=int(os.environ.get("WARMUP_PORT", "8010"))))
