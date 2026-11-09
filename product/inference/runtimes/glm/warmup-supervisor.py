#!/usr/bin/env python3
"""Keep GLM admission closed until real requests qualify this runtime process."""
import concurrent.futures
import hashlib
import http.server
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

MODEL = "dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4"
# Cover the ~1K checkpoint reached by ~1.2K-token prompts before readiness.
SHAPES = (32, 576, 2048, 6033, 8192, 16384)
CONCURRENCIES = (1, 2, 3, 4, 8, 16)
COLD_TIMEOUT, QUALIFY_TIMEOUT = 180, 25
# A record of a full qualification lets later starts of the same bundle on the
# same GPUs, driver and settings run one short pass. Records expire so every
# combination is fully requalified at least weekly.
RECORD_VERSION = 1
RECORD_MAX_AGE_SECONDS = 7 * 24 * 3600
# A short pass falls back to the full qualification when a group is this much
# slower than its recorded latency.
SLOWDOWN_FACTOR, SLOWDOWN_SLACK_SECONDS = 2.0, 1.0


def gpu_inventory(devices):
    """Name, driver and UUID of each assigned GPU, or None when they cannot be read."""
    try:
        output = subprocess.run(["nvidia-smi", "--query-gpu=uuid,name,driver_version", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = {row[0]: row for row in (tuple(field.strip() for field in line.split(",")) for line in output.splitlines())
            if len(row) == 3}
    wanted = [device.strip() for device in devices.split(",") if device.strip()]
    if not wanted or any(device not in rows for device in wanted):
        return None
    return [rows[device] for device in wanted]


class Supervisor:
    def __init__(self, command, runtime_url="http://127.0.0.1:8000", timeout=1800,
                 max_queued_tokens=None, max_queued_requests=None, record_dir=None, identity=None):
        for limit in (max_queued_tokens, max_queued_requests):
            if limit is not None and (type(limit) is not int or limit < 1):
                raise ValueError("queue limits must be positive integers")
        self.max_queued_tokens = max_queued_tokens
        self.max_queued_requests = max_queued_requests
        # Without both, every start runs the full qualification and records nothing.
        self.record_dir = Path(record_dir) if record_dir else None
        self.identity = identity
        self.mode = None
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
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(shapes)) as pool:
            futures = [pool.submit(request, words) for words in shapes]
            return [future.result() for future in futures]

    def plan(self, prompt_bounds):
        """The concurrency and mixed groups these admission limits allow."""
        maximum = min(self.max_queued_requests or 16, 16)
        if self.max_queued_tokens is not None:
            maximum = min(maximum, max(1, self.max_queued_tokens // prompt_bounds[32]))
        concurrencies = [count for count in CONCURRENCIES if count <= maximum]
        mixed_prefills = [8192, 8192, 32]
        fits_mixed = maximum >= 3 and (self.max_queued_tokens is None or
            sum(prompt_bounds[words] for words in mixed_prefills) <= self.max_queued_tokens)
        mixed_prompts = []
        for words in SHAPES:
            fits_tokens = self.max_queued_tokens is None or prompt_bounds[words] + prompt_bounds[32] <= self.max_queued_tokens
            mixed_prompts.append([words, 32] if maximum >= 2 and fits_tokens else [words])
        return concurrencies, (mixed_prefills if fits_mixed else None), mixed_prompts

    def timed_group(self, phase, shapes, timeout):
        return max(result["elapsed_seconds"] for result in self.probe_group(phase, shapes, timeout))

    def qualify_groups(self, prompt_bounds, recorded=None, rerun=None):
        """Run the qualification groups at the idle-time budget and return each group's latency.

        With recorded latencies, a group much slower than its record fails the pass.
        With rerun, only the groups it names run; the others keep their cold latency.
        """
        concurrencies, mixed_prefills, mixed_prompts = self.plan(prompt_bounds)
        groups = [("qualify_mixed_prompt", f"mixed_prompt:{shapes[0]}", shapes) for shapes in mixed_prompts]
        if mixed_prefills:
            groups.append(("qualify_mixed_prefills", "mixed_prefills", mixed_prefills))
        groups += [("qualify_concurrency", f"concurrency:{count}", [32] * count) for count in concurrencies]
        latency = {}
        for phase, name, shapes in groups:
            if rerun is not None and name not in rerun:
                continue
            latency[name] = self.timed_group(phase, shapes, QUALIFY_TIMEOUT)
            if recorded is not None:
                bound = recorded.get(name)
                if bound is None or latency[name] > bound * SLOWDOWN_FACTOR + SLOWDOWN_SLACK_SECONDS:
                    raise RuntimeError("short qualification group slower than its record")
        return latency

    def full_qualification(self):
        # Finish all cold shapes before applying the customer's idle-time budget.
        prompt_bounds = {}
        for words in SHAPES:
            result = self.probe_group("cold_prompt", [words], COLD_TIMEOUT)[0]
            # Each probe starts with a fresh 32-character UUID, whose token count can vary.
            prompt_bounds[words] = result['prompt_tokens'] + 32
        concurrencies, mixed_prefills, _ = self.plan(prompt_bounds)
        latency = {}
        for concurrency in concurrencies:
            latency[f"concurrency:{concurrency}"] = self.timed_group("cold_concurrency", [32] * concurrency, COLD_TIMEOUT)
        if mixed_prefills:
            latency["mixed_prefills"] = self.timed_group("cold_mixed_prefills", mixed_prefills, COLD_TIMEOUT)
        # A cold group that already finished within the idle-time budget proved
        # what its qualification rerun would, so only slower groups run again.
        # Mixed prompts have no cold counterpart and always run.
        rerun = {name for name, elapsed in latency.items() if elapsed > QUALIFY_TIMEOUT}
        rerun |= {f"mixed_prompt:{words}" for words in SHAPES}
        latency.update(self.qualify_groups(prompt_bounds, rerun=rerun))
        return prompt_bounds, latency

    def record_key(self):
        if self.record_dir is None or self.identity is None:
            return None
        gpus = gpu_inventory(os.environ.get("CUDA_VISIBLE_DEVICES", ""))
        if gpus is None:
            return None
        identity = {"version": RECORD_VERSION, "identity": self.identity, "gpus": gpus,
                    "shapes": SHAPES, "concurrencies": CONCURRENCIES,
                    "max_queued_tokens": self.max_queued_tokens, "max_queued_requests": self.max_queued_requests}
        try:
            return hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        except (TypeError, ValueError):
            return None

    def load_record(self, key):
        try:
            record = json.loads((self.record_dir / f"{key}.json").read_text())
            age = time.time() - record["qualified_at"]
            bounds = {int(words): tokens for words, tokens in record["prompt_bounds"].items()}
            latency = record["latency"]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        valid = (record.get("version") == RECORD_VERSION and record.get("key") == key
                 and 0 <= age <= RECORD_MAX_AGE_SECONDS and set(bounds) == set(SHAPES)
                 and all(type(tokens) is int and tokens > 0 for tokens in bounds.values())
                 and isinstance(latency, dict) and latency
                 and all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
                         for value in latency.values()))
        return (bounds, latency) if valid else None

    def save_record(self, key, prompt_bounds, latency):
        record = {"version": RECORD_VERSION, "key": key, "qualified_at": time.time(),
                  "prompt_bounds": {str(words): tokens for words, tokens in prompt_bounds.items()}, "latency": latency}
        try:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            temporary = self.record_dir / f".{key}.{os.getpid()}.tmp"
            temporary.write_text(json.dumps(record, sort_keys=True))
            os.replace(temporary, self.record_dir / f"{key}.json")
        except OSError as error:
            # A missing record only makes the next start run the full qualification.
            print(json.dumps({"qualification_record": "unwritten", "error": type(error).__name__}), flush=True)

    def warmup(self):
        self.mode = None
        while not self.health():
            self.remaining(2)
            self.stopping.wait(1)
        key = self.record_key()
        record = self.load_record(key) if key else None
        mode = "full"
        if record is not None:
            try:
                self.qualify_groups(*record)
                mode = "short"
            except Exception as error:
                # Shutdown and the startup deadline end qualification; anything else retries in full.
                self.remaining(1)
                mode = "short_to_full"
                print(json.dumps({"qualification": "short_failed", "error": type(error).__name__}), flush=True)
        if mode != "short":
            prompt_bounds, latency = self.full_qualification()
        if not self.health():
            raise RuntimeError("runtime unhealthy after warmup")
        self.remaining(1)
        if key and mode != "short":
            self.save_record(key, prompt_bounds, latency)
        self.mode = mode
        self.qualified.set()
        print(json.dumps({"qualification": mode, "key": key}), flush=True)
        print("GLM startup qualification passed through 16k prompt words and concurrency "
              f"{max(self.plan(record[0] if mode == 'short' else prompt_bounds)[0])}", flush=True)

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
    raise SystemExit(Supervisor(sys.argv[1:], runtime_url=os.environ.get("RUNTIME_URL", "http://127.0.0.1:8000"),
        max_queued_tokens=int(os.environ["MAX_QUEUED_TOKENS"]) if os.environ.get("MAX_QUEUED_TOKENS") else None,
        max_queued_requests=int(os.environ["MAX_QUEUED_REQUESTS"]) if os.environ.get("MAX_QUEUED_REQUESTS") else None).run(
        port=int(os.environ.get("WARMUP_PORT", "8010"))))
