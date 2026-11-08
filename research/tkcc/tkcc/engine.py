"""Tiered persistent engine: start vLLM once, then hot-reload candidate jobs.

One process per tier. The fast tier serves a layer subset, the slow tier serves
the whole model. Both tiers share the GPUs, so GPU work is serialized through a
file lock while agents think in parallel.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import queue
import statistics
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from tkcc import workload
from tkcc.scoring import compare_outputs, geomean_speedup


@dataclass
class EngineConfig:
    tier: str
    model: str
    port: int
    run_dir: Path
    workload: Path
    gpu_util: float
    concurrencies: list[int]
    output_len: int
    repeats: int
    check_requests: int
    check_tokens: int
    job_timeout_s: float
    max_model_len: int
    capture_sizes: list[int]
    rebaseline_every: int
    cudagraph_mode: str


@dataclass
class Job:
    id: str
    agent: str
    name: str
    source: str
    profile: bool
    submitted: float
    status: str = "queued"
    result: dict[str, Any] = field(default_factory=dict)


def _now() -> float:
    return time.time()


def _descendants(pid: int) -> list[int]:
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            ppid = int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        children.setdefault(ppid, []).append(int(entry.name))
    out, stack = [], [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            out.append(child)
            stack.append(child)
    return out


def hard_exit(code: int) -> None:
    """Exit and take the engine core and GPU workers down with us."""
    import signal

    for child in reversed(_descendants(os.getpid())):
        try:
            os.kill(child, signal.SIGKILL)
        except OSError:
            pass
    os._exit(code)


class Engine:
    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.run_dir = config.run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events = (self.run_dir / "events.jsonl").open("a")
        self.jobs_log = (self.run_dir / "jobs.jsonl").open("a")
        self.jobs: dict[str, Job] = {}
        self.order: list[str] = []
        self.pending: "queue.Queue[str]" = queue.Queue()
        self.current: Job | None = None
        self.current_started = 0.0
        self.baseline: dict[str, Any] = {}
        self.reference: dict[str, Any] = {}
        self.best: dict[str, Any] = {}
        self.completed_since_baseline = 0
        self.lock_path = self.run_dir.parent / "gpu.lock"
        self.prompts, self.workload_meta = workload.load(config.workload)
        self.state_lock = threading.Lock()

    def log(self, kind: str, **data: Any) -> None:
        self.events.write(json.dumps({"t": _now(), "tier": self.config.tier, "kind": kind, **data}) + "\n")
        self.events.flush()

    @contextmanager
    def gpu(self):
        with self.lock_path.open("a") as handle:
            waited = time.perf_counter()
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield time.perf_counter() - waited
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def start(self) -> None:
        from vllm import LLM

        config = self.config
        t0 = time.perf_counter()
        self.log("startup_begin")
        self.llm = LLM(
            model=config.model,
            tokenizer=config.model,
            tensor_parallel_size=4,
            worker_extension_cls="tkcc.worker_ext.TkccWorkerExtension",
            language_model_only=True,
            engram_config={"cpu_offload": False},
            tokenizer_mode="deepseek_v41",
            max_model_len=config.max_model_len,
            max_num_seqs=max(64, max(config.concurrencies)),
            max_num_batched_tokens=8192,
            gpu_memory_utilization=config.gpu_util,
            enable_prefix_caching=True,
            disable_log_stats=False,
            compilation_config={"cudagraph_capture_sizes": config.capture_sizes, "cudagraph_mode": config.cudagraph_mode},
            seed=0,
        )
        startup_s = time.perf_counter() - t0
        kinds = self.llm.collective_rpc("tkcc_runner_kind")
        memory = self.llm.collective_rpc("tkcc_free_memory")
        self.log("startup_done", startup_s=startup_s, runner=kinds[0], memory=memory)
        with self.gpu():
            warm_start = time.perf_counter()
            self._generate(self.prompts, 1)
            warm_s = time.perf_counter() - warm_start
            self.log("prefix_warm", seconds=warm_s, requests=len(self.prompts))
            self.reference = self._check_run()
            repeats = [compare_outputs(self.reference, self._check_run()) for _ in range(2)]
            self.reference_repeat = {
                key: min(r[key] for r in repeats) if key != "mean_abs_logprob_delta" else max(r[key] or 0.0 for r in repeats)
                for key in ("mean_prefix_fraction", "prefix_match_rate", "mean_abs_logprob_delta", "mean_logprob")
            }
            self.baseline = self._measure()
        self.log("baseline", baseline=self.baseline, self_agreement=self.reference_repeat)
        self.startup = {"startup_s": startup_s, "prefix_warm_s": warm_s, "runner": kinds[0]}

    def _sampling(self, max_tokens: int, logprobs: int | None = None):
        from vllm import SamplingParams

        return SamplingParams(
            max_tokens=max_tokens,
            temperature=0.0,
            ignore_eos=True,
            logprobs=logprobs,
        )

    def _generate(self, prompts: list[list[int]], max_tokens: int, logprobs: int | None = None):
        requests = [{"prompt_token_ids": prompt} for prompt in prompts]
        return self.llm.generate(requests, self._sampling(max_tokens, logprobs), use_tqdm=False)

    def _check_run(self) -> dict[str, Any]:
        prompts = self.prompts[: self.config.check_requests]
        outputs = self._generate(prompts, self.config.check_tokens, logprobs=0)
        tokens, logprobs = [], []
        for output in outputs:
            completion = output.outputs[0]
            tokens.append(list(completion.token_ids))
            values = []
            for token, entry in zip(completion.token_ids, completion.logprobs or []):
                item = entry.get(token) if entry else None
                values.append(float(item.logprob) if item is not None else float("nan"))
            logprobs.append(values)
        return {"tokens": tokens, "logprobs": logprobs}

    def _decode_run(self, prompts: list[list[int]], max_tokens: int) -> dict[str, float]:
        """Step the engine and measure steady-state decode rates from engine-core timestamps.

        Each request's window opens at its first observation after every
        request has emitted a token (all prefills done) and closes at its final
        token. Rates use the engine core's per-token timestamps, so frontend
        output queuing does not distort them.
        """
        engine = self.llm.llm_engine
        params = self._sampling(max_tokens)
        latest: dict[str, tuple[int, float]] = {}
        for prompt in prompts:
            request_id = f"m-{uuid.uuid4().hex[:10]}"
            engine.add_request(request_id, {"prompt_token_ids": prompt}, params)
            latest[request_id] = (0, 0.0)
        opened: dict[str, tuple[int, float]] = {}
        all_decoding = False
        while engine.has_unfinished_requests():
            for output in engine.step():
                if not output.outputs or output.metrics is None:
                    continue
                latest[output.request_id] = (len(output.outputs[0].token_ids), output.metrics.last_token_ts)
            if not all_decoding and all(count > 0 for count, _ in latest.values()):
                all_decoding = True
                opened = dict(latest)
        rates = []
        for request_id, (count, stamp) in latest.items():
            first_count, first_stamp = opened.get(request_id, (0, 0.0))
            if count - first_count >= 8 and stamp > first_stamp:
                rates.append((count - first_count) / (stamp - first_stamp))
        if len(rates) < len(prompts):
            raise RuntimeError(f"decode window too short for {len(prompts) - len(rates)} requests")
        rates.sort()
        return {"tps_per_user": statistics.median(rates), "slowest_tps_per_user": rates[0], "tokens": min(c for c, _ in latest.values())}

    def _measure(self) -> dict[str, Any]:
        config = self.config
        result: dict[str, Any] = {}
        for concurrency in config.concurrencies:
            prompts = self.prompts[:concurrency]
            samples = []
            for _ in range(config.repeats):
                self._generate(prompts, 1)
                samples.append(self._decode_run(prompts, config.output_len))
            values = [s["tps_per_user"] for s in samples]
            value = statistics.median(values)
            result[str(concurrency)] = {
                "tps_per_user": value,
                "aggregate_tps": value * concurrency,
                "spread": (max(values) - min(values)) / value,
                "samples": samples,
            }
        return result

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = payload.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source is required")
        job = Job(
            id=f"{self.config.tier}-{time.strftime('%H%M%S')}-{uuid.uuid4().hex[:6]}",
            agent=str(payload.get("agent", "anon"))[:40],
            name=str(payload.get("name", ""))[:120],
            source=source,
            profile=bool(payload.get("profile", False)),
            submitted=_now(),
        )
        # Same lock as _stop_admitting, so a job is either refused or marked by the shutdown.
        with self.state_lock:
            if not getattr(self, "accepting", True):
                raise ValueError("engine is restarting; resubmit in a few minutes")
            self.jobs[job.id] = job
            self.order.append(job.id)
            position = self.pending.qsize()
            self.pending.put(job.id)
        self.log("submitted", job=job.id, agent=job.agent, name=job.name)
        return {"job_id": job.id, "queue_position": position}

    def run_forever(self) -> None:
        while True:
            job_id = self.pending.get()
            job = self.jobs[job_id]
            if not getattr(self, "accepting", True) or job.status != "queued":
                continue
            self._run_job(job)
            self.completed_since_baseline += 1
            if self.config.rebaseline_every and self.completed_since_baseline >= self.config.rebaseline_every:
                with self.gpu():
                    self.baseline = self._measure()
                self.completed_since_baseline = 0
                self.log("rebaseline", baseline=self.baseline)

    def _run_job(self, job: Job) -> None:
        job.status = "running"
        # The watchdog times only GPU work; waiting for another tier's lock is not a hang.
        self.current_started = 0.0
        self.current = job
        result: dict[str, Any] = {"job_id": job.id, "agent": job.agent, "name": job.name, "tier": self.config.tier}
        started = _now()
        result["queue_wait_s"] = started - job.submitted
        try:
            with self.gpu() as lock_wait:
                self.current_started = time.perf_counter()
                result["gpu_lock_wait_s"] = lock_wait
                t = time.perf_counter()
                reload = self.llm.collective_rpc("tkcc_hot_reload", args=(job.id, job.source))
                result["hot_reload_s"] = time.perf_counter() - t
                failures = [r for r in reload if not r.get("ok")]
                installed = len(failures) < len(reload)
                result["install"] = {
                    "patches": reload[0].get("patches"),
                    "recapture_s": max(r.get("recapture_s", 0.0) for r in reload),
                }
                try:
                    if failures:
                        result["status"] = "install_error"
                        result["error"] = failures[0].get("error")
                        result["traceback"] = failures[0].get("traceback")
                        result["teardown_error"] = failures[0].get("teardown_error")
                        if any(f.get("teardown_error") for f in failures):
                            self.restart_after_job = True
                    else:
                        self._evaluate(job, result)
                finally:
                    # Even a candidate that failed to install may have edited weights before raising.
                    self._check_weights(result)
                    if installed:
                        self._teardown(result)
        except Exception as exc:
            result["status"] = "engine_error"
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["traceback"] = traceback.format_exc()[-6000:]
            if "EngineDead" in type(exc).__name__ or "EngineDead" in result["traceback"]:
                self.restart_after_job = True
                result["error"] += " (engine core died; engine restarting)"
        result["job_s"] = _now() - started
        result["finished"] = _now()
        job.result = result
        job.status = result.get("status", "unknown")
        self.current = None
        self.current_started = 0.0
        self.jobs_log.write(json.dumps({**result, "source_sha": _sha(job.source)}) + "\n")
        self.jobs_log.flush()
        (self.run_dir / "sources").mkdir(exist_ok=True)
        (self.run_dir / "sources" / f"{job.id}.py").write_text(job.source)
        if result.get("status") == "ok" and result["speedup"] > self.best.get("speedup", 0):
            self.best = {"job_id": job.id, "agent": job.agent, "name": job.name, "speedup": result["speedup"]}
        self.log("finished", job=job.id, status=job.status, speedup=result.get("speedup"), job_s=result["job_s"])
        if getattr(self, "restart_after_job", False):
            self._exit_for_restart(job.id)

    def _evaluate(self, job: Job, result: dict[str, Any]) -> None:
        t = time.perf_counter()
        check = compare_outputs(self.reference, self._check_run(), self.reference_repeat)
        result["check_s"] = time.perf_counter() - t
        result["correctness"] = check
        result["status"] = "ok" if check["pass"] else "incorrect"
        if check["pass"]:
            t = time.perf_counter()
            measured = self._measure()
            result["measure_s"] = time.perf_counter() - t
            result["measurement"] = measured
            result["speedup"] = geomean_speedup(measured, self.baseline)
            result["per_concurrency_speedup"] = {
                c: measured[c]["tps_per_user"] / self.baseline[c]["tps_per_user"] for c in measured
            }
            if job.profile and self.config.tier == "slow":
                result["profile_note"] = "profiling is disabled on the slow tier (CUPTI overhead persists in-process); use --tier fast --profile"
            elif job.profile:
                self.restart_after_job = True
                result["profile_note"] = "fast engine restarts after a profiled job to clear CUPTI overhead (~3-4 min)"
                result["profile"] = self._profile()
    def _check_weights(self, result: dict[str, Any]) -> None:
        try:
            weights = self.llm.collective_rpc("tkcc_weights_unchanged")
        except Exception as exc:
            result["weights_error"] = f"{type(exc).__name__}: {exc}"
            self.restart_after_job = True
            return
        if not all(w["ok"] for w in weights):
            # Teardown cannot restore tensor contents, so only a restart gives back a stock model.
            result["status"] = "weights_modified"
            result["changed"] = weights[0].get("changed")
            self.restart_after_job = True

    def _teardown(self, result: dict[str, Any]) -> None:
        t = time.perf_counter()
        try:
            self.llm.collective_rpc("tkcc_teardown")
        except Exception as exc:
            # A candidate that cannot be removed would be measured as the next baseline.
            result["teardown_error"] = f"{type(exc).__name__}: {exc}"
            self.restart_after_job = True
        result["teardown_s"] = time.perf_counter() - t

    def _profile(self) -> list[dict[str, Any]]:
        self.llm.collective_rpc("tkcc_profile_start")
        self._generate(self.prompts[:1], 16)
        self._generate(self.prompts[: max(self.config.concurrencies)], 16)
        rows = self.llm.collective_rpc("tkcc_profile_stop")
        return rows[0]

    @contextmanager
    def _candidate(self, source: str | None, label: str):
        """Install a candidate for a utility call; restart if it cannot be cleanly removed."""
        if not source:
            yield
            return
        reload = self.llm.collective_rpc("tkcc_hot_reload", args=(f"{label}-{uuid.uuid4().hex[:6]}", source))
        failures = [r for r in reload if not r.get("ok")]
        if any(f.get("teardown_error") for f in failures):
            self._schedule_restart()
        if failures:
            self._restart_if_weights_changed()
            if len(failures) < len(reload):
                self._teardown_or_restart()
            raise ValueError(f"candidate failed to install: {failures[0].get('error')}")
        self.utility_started = time.perf_counter()
        try:
            yield
        finally:
            self.utility_started = 0.0
            self._restart_if_weights_changed()
            self._teardown_or_restart()

    def _restart_if_weights_changed(self) -> None:
        result: dict[str, Any] = {}
        self._check_weights(result)
        if result.get("status") == "weights_modified" or "weights_error" in result:
            self._schedule_restart()

    def _teardown_or_restart(self) -> None:
        try:
            self.llm.collective_rpc("tkcc_teardown")
        except Exception:
            self._schedule_restart()
            raise

    def _schedule_restart(self) -> None:
        if getattr(self, "restart_scheduled", False):
            return
        self.restart_scheduled = True
        self._stop_admitting()
        threading.Thread(target=lambda: (time.sleep(15), hard_exit(0)), daemon=True).start()

    def _exit_for_restart(self, after_job: str | None) -> None:
        self._stop_admitting()
        self.log("restart", after_job=after_job)
        # Give polling clients time to read the engine_restarting results.
        time.sleep(15)
        hard_exit(0)

    def _stop_admitting(self) -> None:
        self.accepting = False
        with self.state_lock:
            for job_id in self.order:
                job = self.jobs[job_id]
                if job.status == "queued":
                    job.status = "engine_restarting"
                    job.result = {"job_id": job.id, "status": "engine_restarting", "error": "engine restarted before this job ran; resubmit"}

    def experiment(self, payload: dict[str, Any]) -> dict[str, Any]:
        sets: dict[str, list[list[int]]] = payload["prompt_sets"]
        max_tokens = int(payload.get("max_tokens", 1))
        out: dict[str, Any] = {}
        with self.gpu(), self._candidate(payload["source"], "exp"):
            for name, prompts in sets.items():
                self.llm.collective_rpc("tkcc_call", args=("reset",))
                for prompt in prompts:
                    # Every prompt must be a full prefill, or shared leading blocks would hide tokens from the probe.
                    self.llm.reset_prefix_cache()
                    self._generate([prompt], max_tokens)
                out[name] = self.llm.collective_rpc("tkcc_call", args=("collect",))[0]
        return out

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        from vllm import SamplingParams

        params = SamplingParams(max_tokens=int(payload.get("max_tokens", 256)), temperature=0.0, stop=payload.get("stop"))
        with self.gpu(), self._candidate(payload.get("source"), "gen"):
            outputs = self.llm.generate([{"prompt_token_ids": p} for p in payload["prompts"]], params, use_tqdm=False)
        return {"texts": [o.outputs[0].text for o in outputs]}

    def profile_baseline(self) -> list[dict[str, Any]]:
        if self.config.tier == "slow":
            raise ValueError("profiling is disabled on the slow tier")
        try:
            with self.gpu():
                return self._profile()
        finally:
            self._schedule_restart()

    def watchdog(self) -> None:
        while True:
            time.sleep(5)
            utility = getattr(self, "utility_started", 0.0)
            if utility and time.perf_counter() - utility > self.config.job_timeout_s:
                self.log("watchdog_kill", job="utility-call")
                hard_exit(17)
            job = self.current
            if job is not None and self.current_started and time.perf_counter() - self.current_started > self.config.job_timeout_s:
                result = {
                    "job_id": job.id,
                    "agent": job.agent,
                    "name": job.name,
                    "tier": self.config.tier,
                    "status": "timeout",
                    "error": f"job exceeded {self.config.job_timeout_s}s; engine restarting",
                    "finished": _now(),
                }
                self.jobs_log.write(json.dumps(result) + "\n")
                self.jobs_log.flush()
                self.log("watchdog_kill", job=job.id)
                hard_exit(17)

    def status(self) -> dict[str, Any]:
        done = [self.jobs[j].result for j in self.order if self.jobs[j].result]
        durations = [r["job_s"] for r in done if "job_s" in r]
        return {
            "tier": self.config.tier,
            "layers": self.workload_meta.get("layers_hint"),
            "queue_depth": self.pending.qsize(),
            "running": self.current.id if self.current else None,
            "jobs_done": len(done),
            "median_job_s": statistics.median(durations) if durations else None,
            "baseline_tps_per_user": {c: v["tps_per_user"] for c, v in self.baseline.items()},
            "best": self.best,
            "startup": getattr(self, "startup", {}),
        }


def _sha(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            return

        def _send(self, code: int, body: Any) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if url.path == "/status":
                return self._send(200, engine.status())
            if url.path == "/result":
                job = engine.jobs.get(query.get("id", [""])[0])
                if job is None:
                    return self._send(404, {"error": "unknown job"})
                return self._send(200, {"status": job.status, "result": job.result})
            if url.path == "/baseline":
                return self._send(200, {"baseline": engine.baseline, "self_agreement": engine.reference_repeat})
            if url.path == "/admin/rebaseline":
                with engine.gpu():
                    engine.baseline = engine._measure()
                engine.completed_since_baseline = 0
                engine.log("rebaseline", baseline=engine.baseline, manual=True)
                return self._send(200, {"baseline_tps_per_user": {c: v["tps_per_user"] for c, v in engine.baseline.items()}})
            if url.path == "/admin/reload_ext":
                with engine.gpu():
                    return self._send(200, {"rebound": engine.llm.collective_rpc("tkcc_reload_ext")[0]})
            if url.path == "/profile_baseline":
                return self._send(200, {"profile": engine.profile_baseline()})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            if path not in ("/submit", "/experiment", "/generate"):
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length))
                if path == "/experiment":
                    return self._send(200, engine.experiment(payload))
                if path == "/generate":
                    return self._send(200, engine.generate(payload))
                return self._send(200, engine.submit(payload))
            except (ValueError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": str(exc)})

    return Handler


def parse_args(argv: list[str] | None = None) -> EngineConfig:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--gpu-util", type=float, default=0.6)
    parser.add_argument("--concurrency", default="1,8,32")
    parser.add_argument("--output-len", type=int, default=128)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--check-requests", type=int, default=32)
    parser.add_argument("--check-tokens", type=int, default=32)
    parser.add_argument("--job-timeout", type=float, default=600)
    parser.add_argument("--max-model-len", type=int, default=131072)
    parser.add_argument("--capture-sizes", default="1,2,4,8,16,32,64")
    parser.add_argument("--rebaseline-every", type=int, default=4)
    parser.add_argument("--cudagraph-mode", default="FULL_DECODE_ONLY")
    args = parser.parse_args(argv)
    return EngineConfig(
        tier=args.tier,
        model=args.model,
        port=args.port,
        run_dir=args.run_dir,
        workload=args.workload,
        gpu_util=args.gpu_util,
        concurrencies=[int(c) for c in args.concurrency.split(",")],
        output_len=args.output_len,
        repeats=args.repeats,
        check_requests=args.check_requests,
        check_tokens=args.check_tokens,
        job_timeout_s=args.job_timeout,
        max_model_len=args.max_model_len,
        capture_sizes=[int(c) for c in args.capture_sizes.split(",")],
        rebaseline_every=args.rebaseline_every,
        cudagraph_mode=args.cudagraph_mode,
    )


def main(argv: list[str] | None = None) -> None:
    engine = Engine(parse_args(argv))
    engine.start()
    server = ThreadingHTTPServer(("127.0.0.1", engine.config.port), _handler(engine))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=engine.watchdog, daemon=True).start()
    engine.log("serving", port=engine.config.port)
    engine.run_forever()


if __name__ == "__main__":
    main()
