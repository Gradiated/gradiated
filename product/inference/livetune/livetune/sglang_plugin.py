from __future__ import annotations

import atexit
import dataclasses
import json
import logging
import os
import queue
import threading
import time
from typing import Any

from livetune import trace, variants
from livetune.knobs import KNOBS, SCHEDULE_POLICIES, VARIANT_KEY, InvalidSetting

logger = logging.getLogger(__name__)

_TARGET = "sglang.srt.managers.scheduler_components.internal_state.SchedulerInternalStateController"
_SCHEDULER = "sglang.srt.managers.scheduler.Scheduler"
_MODEL_RUNNER = "sglang.srt.model_executor.model_runner.ModelRunner"
_STREAMER = "sglang.srt.managers.scheduler_components.output_streamer.SchedulerOutputStreamer"
_TIME_STATS = "sglang.srt.observability.req_time_stats.SchedulerReqTimeStats"
_REQ = "sglang.srt.managers.schedule_batch.Req"
# A replayed request that stopped early in production carries its recorded length here, and the
# server finishes it at exactly that many tokens: a client cutting the stream would see the stop
# only at a chunk boundary, and speculative decoding can accept several tokens past it.
REPLAY_STOP_KEY = "livetune_stop_after"


class NoUsableVariant(RuntimeError):
    pass


class LiveTuner:
    def __init__(self, scheduler: Any) -> None:
        runner = scheduler.tp_worker.model_runner
        self.scheduler = scheduler
        self.page_size = int(getattr(scheduler, "page_size", 1) or 1)
        self.startup = _startup_settings(scheduler)
        self.startup[VARIANT_KEY] = getattr(runner, "_livetune_variant_id", variants.STOCK)
        from sglang.srt.runtime_context import get_parallel

        # The running-batch budget; it may have been set explicitly rather than derived from the cap.
        self.pp_micro_batch_startup = get_parallel().pp_max_micro_batch_size
        self.gpu = _gpu_name()
        self._runtime: dict[str, str | None] | None = None
        self._runtime_thread: threading.Thread | None = None
        # Speculative runtime states by variant id, least recently used first.
        self.states: dict[int, Any] = {}
        self.max_states = max(2, int(os.environ.get("LIVETUNE_VARIANT_STATES", "3") or 3))
        self.settings: dict[str, Any] = dict(self.startup)
        self.variant: variants.InstalledVariant | None = getattr(runner, "_livetune_variant", None)
        # The code installed at startup, by hash: re-registering a name later changes the catalog, not this.
        self.startup_variant = {"name": self.variant.source.name, "sha256": self.variant.source.sha256} if self.variant else None
        # Variant ids are mutable names in the manifest; the first hash this scheduler sees for an id
        # is the only code it will install under that id.
        self.pinned: dict[str, str] = {}
        if self.variant is not None:
            self.pinned[str(self.startup[VARIANT_KEY])] = self.variant.source.sha256
        self.pending_variant: int | None = None
        self.pending_since_step = 0
        self.drain_steps = int(os.environ.get("LIVETUNE_DRAIN_STEPS", "6000"))
        self.changes: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def validate(self, key: str, value: Any) -> None:
        if key == VARIANT_KEY:
            if not _live_variants():
                raise InvalidSetting(f"live {VARIANT_KEY} switching is disabled; set LIVETUNE_STARTUP_VARIANT and restart")
            from sglang.srt.runtime_context import get_parallel

            # Data-parallel schedulers drain independently, so their switches cannot be made atomic.
            if getattr(get_parallel(), "dp_size", 1) > 1:
                raise InvalidSetting(f"live {VARIANT_KEY} switching is not supported with data parallelism")
            # A speculative server switches whole runtime states, target and draft; one whose worker
            # cannot build them, or that switches them itself (adaptive steps), would keep old code.
            spec = getattr(self.scheduler, "spec_algorithm", None)
            if spec is not None and not spec.is_none():
                worker = _state_worker(self.scheduler)
                if worker is None:
                    raise InvalidSetting(f"live {VARIANT_KEY} switching needs a speculative worker that builds runtime states")
                if getattr(worker, "adaptive_controller", None) is not None:
                    raise InvalidSetting(f"live {VARIANT_KEY} switching is not supported with adaptive speculative steps")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidSetting(f"{VARIANT_KEY} must be a variant id (0 = stock)")
            if value != variants.STOCK:
                self._resolve(value)
            return
        KNOBS[key].validate(value, self.startup, self.page_size)
        if key == "schedule_policy":
            _schedule_policy(self.scheduler, SCHEDULE_POLICIES[value])  # incompatible policies raise here, not mid-apply

        if key == "max_running_requests" and value != self.startup[key]:
            from sglang.srt.runtime_context import get_parallel

            # The cap is enforced as a per-stage budget, so only multiples of pp_size are exact.
            pp_size = get_parallel().pp_size
            if value % pp_size:
                raise InvalidSetting(f"max_running_requests={value} must be a multiple of pp_size {pp_size}")

    def apply(self, key: str, value: Any) -> dict[str, Any] | None:
        # Never raises: SGLang treats an exception in an update handler as fatal to
        # the scheduler. A failure keeps the previous setting and shows in readback.
        started = time.perf_counter()
        try:
            overrides = self._apply(key, value)
        except Exception as exc:
            logger.exception("livetune: applying %s=%r failed; keeping %r", key, value, self.settings.get(key))
            self.errors.append({"t": time.time(), "key": key, "value": value, "error": f"{type(exc).__name__}: {exc}"})
            del self.errors[:-20]
            return None
        if key == VARIANT_KEY:
            return overrides
        self.settings[key] = value
        self.changes.append({"t": time.time(), "key": key, "value": value, "seconds": time.perf_counter() - started})
        del self.changes[:-50]
        logger.info("livetune: %s=%r applied in %.3fs", key, value, time.perf_counter() - started)
        return overrides

    def _apply(self, key: str, value: Any) -> dict[str, Any] | None:
        overrides: dict[str, Any] | None = None
        if key == "max_running_requests":
            from sglang.srt.runtime_context import get_parallel

            # The running-batch budget is pp_max_micro_batch_size; buffers stay at startup size.
            # The startup cap restores the startup budget exactly, explicit or derived.
            budget = self.pp_micro_batch_startup if value == self.startup[key] else value // get_parallel().pp_size
            overrides = {"pp_max_micro_batch_size": budget}
        elif key == "chunked_prefill_size":
            self.scheduler.chunked_prefill_size = value
            overrides = {key: value}
        elif key == "max_prefill_tokens":
            self.scheduler.max_prefill_tokens = value
            overrides = {key: value}
        elif key == "schedule_policy":
            name = SCHEDULE_POLICIES[value]
            # The scheduler holds a policy object built at startup; config is also read fresh in places.
            self.scheduler.policy = _schedule_policy(self.scheduler, name)
            self.scheduler.schedule_policy = name
            overrides = {key: name}
        elif key == "schedule_conservativeness":
            from sglang.srt.managers.scheduler_components.new_token_ratio_tracker import NewTokenRatioTracker
            from sglang.srt.runtime_context import get_context

            # The admission headroom tracker derives its ratios from config at construction.
            get_context().override(source="livetune", **{key: value})
            self.scheduler.new_token_ratio_tracker = NewTokenRatioTracker.from_config()
            overrides = {key: value}
        elif key == "stream_interval":
            overrides = {key: value}
        elif key == "policy_version":
            pass  # recorded in settings, read back by stage and guard
        elif key == "max_queued_requests":
            self.scheduler.max_queued_requests = value or None

        elif key == VARIANT_KEY:
            # Recapturing graphs under an in-flight overlap batch corrupts its buffers, so
            # the switch waits for an idle scheduler; admission pauses until then.
            if value == self.settings[VARIANT_KEY]:
                self.pending_variant = None
                return None
            self.pending_variant = value
            self.pending_since_step = getattr(self.scheduler, "forward_ct", 0)
            return None
        return overrides

    def admission_blocked(self) -> bool:
        if self.pending_variant is None:
            return False
        # Step counts, unlike clocks, are identical on every rank, so all ranks cancel together.
        if getattr(self.scheduler, "forward_ct", 0) - self.pending_since_step > self.drain_steps:
            self.errors.append({"t": time.time(), "key": VARIANT_KEY, "value": self.pending_variant, "error": "scheduler did not drain; switch cancelled"})
            self.pending_variant = None
            return False
        return True

    def on_idle(self) -> None:
        if self.pending_variant is None:
            return
        variant_id, self.pending_variant = self.pending_variant, None
        started = time.perf_counter()
        try:
            self._switch_variant(variant_id)
        except NoUsableVariant:
            raise
        except Exception as exc:
            logger.exception("livetune: switching to variant %s failed", variant_id)
            self.errors.append({"t": time.time(), "key": VARIANT_KEY, "value": variant_id, "error": f"{type(exc).__name__}: {exc}"})
            return
        self.settings[VARIANT_KEY] = variant_id
        self.changes.append({"t": time.time(), "key": VARIANT_KEY, "value": variant_id, "seconds": time.perf_counter() - started})
        logger.info("livetune: forward_variant=%s switched in %.1fs", variant_id, time.perf_counter() - started)

    def _install(self, variant_id: int) -> None:
        from sglang.srt.runtime_context import get_parallel

        runner = self.scheduler.tp_worker.model_runner
        parallel = get_parallel()
        ctx = {"model_runner": runner, "scheduler": self.scheduler, "tp_rank": parallel.tp_rank, "tp_size": parallel.tp_size}
        self.variant = variants.install(self._resolve(variant_id), runner.model, ctx)

    def _switch_variant(self, variant_id: int) -> None:
        previous = self.settings[VARIANT_KEY]
        error = self._try_variant(variant_id)
        if error is None:
            return
        # Fall back to the variant that was serving, then to stock. Every attempt ends in a
        # collective vote, so all ranks take the same branch and end on the same code.
        for fallback in dict.fromkeys([previous, variants.STOCK]):
            if self._try_variant(fallback) is None:
                self.settings[VARIANT_KEY] = fallback
                raise error
        # No code with working graphs is left; stop the scheduler rather than serve from it.
        raise NoUsableVariant(f"variant {variant_id} failed and neither {previous} nor stock could be restored") from error

    def _try_variant(self, variant_id: int) -> Exception | None:
        # Install and graph recapture succeed together on every rank, or the attempt fails. Ranks vote
        # after installing, before recapture: recapture runs tensor-parallel collectives, and a rank
        # that skipped it would leave the others blocked in them.
        if self.variant is not None:
            variants.uninstall(self.variant)
            self.variant = None
        error: Exception | None = None
        try:
            if variant_id != variants.STOCK:
                self._install(variant_id)
        except Exception as exc:
            error = exc
        if not self._all_ranks_agree(error is None):
            if self.variant is not None:
                variants.uninstall(self.variant)
                self.variant = None
            return error or RuntimeError("variant install failed on another tensor-parallel rank")
        try:
            self._rebuild(variant_id)
        except Exception as exc:
            error = exc
        if self._all_ranks_agree(error is None):
            return None
        return error or RuntimeError("variant switch failed on another tensor-parallel rank")

    def _rebuild(self, variant_id: int) -> None:
        """Put graphs captured with the installed code in place.

        A speculative worker gets a runtime state per variant, built the way SGLang builds its adaptive
        speculative states: fresh attention backends and graph runners for the target and draft
        models, captured with the variant installed. Switching to a state built before is a pointer
        swap, and no switch frees the graphs being left, so nothing serving can see freed memory.
        Other servers recapture in place with SGLang's elastic sequence.
        """
        worker = _state_worker(self.scheduler)
        if worker is None:
            self._recapture(self.scheduler.tp_worker.model_runner)
            return
        if not self.states:
            # The graphs captured at startup belong to the variant serving before the first switch.
            self.states[self.settings[VARIANT_KEY]] = _current_state(worker)
        state = self.states.pop(variant_id, None)
        if state is None:
            state = worker.build_adaptive_runtime_state(worker.speculative_num_steps, worker.speculative_num_draft_tokens)
        self.states[variant_id] = state  # most recently used last
        _apply_state(worker, state)
        # Keep a bounded number of states: drop the least recently used, never the one now serving.
        while len(self.states) > self.max_states:
            del self.states[next(iter(self.states))]

    def _all_ranks_agree(self, ok: bool) -> bool:
        group = getattr(self.scheduler, "tp_cpu_group", None)
        if group is None:
            return ok
        import torch
        import torch.distributed as dist

        flag = torch.tensor([1 if ok else 0], dtype=torch.int32)
        dist.all_reduce(flag, op=dist.ReduceOp.MIN, group=group)
        return bool(flag.item())

    @staticmethod
    def _recapture(runner: Any) -> None:
        # SGLang's own sequence for recapturing decode graphs on a running server (elastic EP):
        # free the old graphs through their backend, start a fresh graph memory pool, warm the
        # kernels again, then capture. Re-calling init_decode_cuda_graph() alone reused the old
        # pool and hit an illegal memory access at the first decode on DeepSeek V4.
        from sglang.srt.model_executor.model_runner_components.cuda_graph_setup import (
            drop_elastic_cuda_graph_state,
            recapture_elastic_cuda_graph,
        )

        drop_elastic_cuda_graph_state(decode_runner=runner.decode_cuda_graph_runner, eager_runner=runner.eager_runner)
        runner.decode_cuda_graph_runner = None
        runner.decode_cuda_graph_runner = recapture_elastic_cuda_graph(model_runner=runner).runner

    @property
    def runtime(self) -> dict[str, str | None] | None:
        """Digests of the code and inputs serving, or None while they are being computed.

        Hashing thousands of files takes about a second, which would stall serving on the scheduler
        thread. It starts at the first readback, after startup has written its caches, and runs in the
        background; clients wait for it.
        """
        if self._runtime is None and self._runtime_thread is None:
            self._runtime_thread = threading.Thread(target=self._compute_runtime, name="livetune-runtime", daemon=True)
            self._runtime_thread.start()
        return self._runtime

    def _compute_runtime(self) -> None:
        try:
            self._runtime = {
                "sglang": _source_digest("sglang"),
                "livetune": _source_digest("livetune"),
                "packages": _packages_digest(),
                "inputs": _inputs_digest(os.environ.get("LIVETUNE_RUNTIME_INPUTS", "")),
            }
        except Exception as exc:  # an unreadable input is a scope nobody can match, not a crash
            logger.exception("livetune: could not digest the runtime")
            self._runtime = {"error": f"{type(exc).__name__}: {exc}"}

    def _resolve(self, variant_id: int) -> variants.VariantSource:
        source = variants.resolve(variant_id)
        self._pin(str(variant_id), source.sha256)
        return source

    def _pin(self, variant_id: str, sha256: str) -> None:
        pinned = self.pinned.setdefault(variant_id, sha256)
        if pinned != sha256:
            raise variants.VariantError(f"variant {variant_id} changed after this scheduler pinned it ({pinned[:12]}); restart to use the new code")

    def _catalog(self) -> dict[str, str]:
        catalog = variants.catalog()
        for variant_id, sha256 in catalog.items():
            self._pin(variant_id, sha256)
        return catalog

    def oldest_unfinished(self) -> float | None:
        """Wall time the longest-waiting unfinished request entered the queue, or None when idle.

        Its record is written only when it finishes, so a trace window that began after this is
        not yet complete.
        """
        scheduler = self.scheduler
        running = getattr(getattr(scheduler, "running_batch", None), "reqs", None) or []
        chunked = getattr(scheduler, "chunked_req", None)
        stamps = []
        for req in [*(getattr(scheduler, "waiting_queue", None) or []), *running, *([chunked] if chunked else [])]:
            stats = getattr(req, "time_stats", None)
            stamp = getattr(stats, "livetune_first_entry", 0.0) or getattr(stats, "wait_queue_entry_time", 0.0)
            if stamp:
                stamps.append(stamp)
        if not stamps:
            return None
        # The stamps are on this process's perf_counter clock.
        return time.time() - (time.perf_counter() - min(stamps))

    def readback(self) -> dict[str, Any]:
        try:
            catalog: dict[str, str] | str = self._catalog()
        except Exception as exc:  # a broken manifest must not take down /server_info
            catalog = f"unreadable: {type(exc).__name__}: {exc}"
        return {
            "settings": dict(self.settings),
            "startup": dict(self.startup),
            "page_size": self.page_size,
            "pp_micro_batch_startup": self.pp_micro_batch_startup,
            "live_variants": _live_variants(),
            "replay_stops": _replay_stops(),
            "startup_variant": self.startup_variant,
            "runtime": self.runtime,
            "telemetry": telemetry.readback() if (telemetry := _TELEMETRY.get("rank0")) else None,
            "oldest_unfinished": self.oldest_unfinished(),
            "gpu": self.gpu,
            "variant": {"name": self.variant.source.name, "sha256": self.variant.source.sha256} if self.variant else None,
            "variants": catalog,
            "pending_variant": self.pending_variant,
            "variant_states": list(self.states),
            "recent_changes": self.changes[-10:],
            "recent_errors": self.errors[-5:],
        }


def _source_digest(package: str) -> str | None:
    # Every .py file of the installed package, overlays included: a rebuilt runtime is a new scope.
    import hashlib
    import importlib
    from pathlib import Path

    try:
        paths = list(getattr(importlib.import_module(package), "__path__", []))
    except ImportError:
        return None
    if not paths:
        return None
    root = Path(paths[0])
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _inputs_digest(spec: str) -> str | None:
    # Runtime inputs outside Python distributions, such as kernel artifact manifests and autotune
    # seeds, named by the deployment. Paths are hashed relative to themselves so replicas match.
    import hashlib
    from pathlib import Path

    if not spec:
        return None
    digest = hashlib.sha256()
    for index, raw in enumerate(spec.split(os.pathsep)):
        root = Path(raw)
        files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else [root] if root.is_file() else []
        digest.update(f"input {index}: {len(files)} files\n".encode())
        for path in files:
            digest.update(str(path.relative_to(root) if root.is_dir() else path.name).encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _packages_digest() -> str:
    # Every installed distribution's name, version and RECORD, whose per-file hashes cover native
    # libraries (torch, flashinfer, CUDA wheels): a rebuilt kernel stack is a new scope.
    import hashlib
    from importlib import metadata

    digest = hashlib.sha256()
    entries = sorted(((dist.metadata["Name"] or "").lower(), dist.version, dist.read_text("RECORD") or "") for dist in metadata.distributions())
    for name, version, record in entries:
        digest.update(f"{name}=={version}\n".encode() + record.encode())
    return digest.hexdigest()


def _state_worker(scheduler: Any) -> Any:
    """The speculative worker, if it can build and apply complete runtime states."""
    worker = getattr(scheduler, "draft_worker", None)
    if worker is None or not all(callable(getattr(worker, name, None)) for name in ("build_adaptive_runtime_state", "apply_runtime_state")):
        return None
    return worker


def _current_state(worker: Any) -> Any:
    from sglang.srt.speculative.adaptive_runtime_state import SpecRuntimeState

    draft, target = worker._draft_worker, worker._target_worker.model_runner
    return SpecRuntimeState(
        speculative_num_steps=worker.speculative_num_steps,
        speculative_num_draft_tokens=worker.speculative_num_draft_tokens,
        draft_attn_backend=draft.draft_attn_backend,
        cuda_graph_runner=draft.cuda_graph_runner,
        target_attn_backend=target.attn_backend,
        target_graph_runner=target.decode_cuda_graph_runner,
        draft_extend_attn_backend=draft.draft_extend_attn_backend,
        cuda_graph_runner_for_draft_extend=draft.cuda_graph_runner_for_draft_extend,
    )


def _apply_state(worker: Any, state: Any) -> None:
    # SGLang applies a state only when the step count changes (its adaptive use); a variant's state
    # has the same steps, so mark the worker unset to make it apply every resource.
    worker.speculative_num_steps = -1
    worker.apply_runtime_state(state)


def _live_variants() -> bool:
    return os.environ.get("LIVETUNE_LIVE_VARIANTS") == "1"


def _gpu_name() -> str | None:
    try:
        import torch
    except ImportError:
        return None
    return torch.cuda.get_device_name() if torch.cuda.is_available() else None


def _startup_settings(scheduler: Any) -> dict[str, Any]:
    from sglang.srt.runtime_context import get_schedule, get_serving

    policy = getattr(scheduler, "schedule_policy", None)
    startup = {
        "max_running_requests": scheduler.max_running_requests,
        "chunked_prefill_size": scheduler.chunked_prefill_size,
        "max_prefill_tokens": scheduler.max_prefill_tokens,
        "schedule_policy": SCHEDULE_POLICIES.index(policy) if policy in SCHEDULE_POLICIES else None,
        "schedule_conservativeness": get_schedule().schedule_conservativeness,
        "stream_interval": get_serving().stream_interval,
        "max_queued_requests": getattr(scheduler, "max_queued_requests", None) or 0,
    }
    # A knob whose startup value is unknown is left out, which makes it unavailable.
    return {key: value for key, value in startup.items() if value is not None}


def _schedule_policy(scheduler: Any, name: str) -> Any:
    from sglang.srt.managers.schedule_policy import SchedulePolicy

    return SchedulePolicy(
        name,
        scheduler.tree_cache,
        scheduler.enable_hierarchical_cache,
        scheduler.enable_priority_scheduling,
        scheduler.schedule_low_priority_values_first,
    )


# SGLang's defaults; a request that differs is recorded and replayed with the same values.
_SAMPLING_DEFAULTS = {"top_p": 1.0, "top_k": -1, "min_p": 0.0, "repetition_penalty": 1.0, "frequency_penalty": 0.0, "presence_penalty": 0.0,
                      "min_new_tokens": 0, "stream_interval": None, "sampling_seed": None}

_FINISH_NAMES = {"FINISH_LENGTH": "length", "FINISH_ABORT": "abort", "FINISH_MATCHED_TOKEN": "stop", "FINISH_MATCHED_STR": "stop", "FINISHED_MATCHED_REGEX": "stop"}


class Telemetry:
    """What the scheduler saw, on attention-TP rank 0: one record per finished request, counters per batch."""

    # Finished requests waiting to be hashed and written; beyond this the scheduler drops records
    # rather than wait or grow memory.
    BACKLOG = 8192

    def __init__(self, directory: str | None, page_size: int = 1, keys: trace.PrefixKeys | None = None) -> None:
        self.writer = trace.Writer(directory) if directory else None
        self.keys = keys or trace.PrefixKeys(directory=directory)
        self.page_size = max(page_size, 1)
        self.batches = trace.BatchStats()
        self.recent: list[str] = []
        self.since = time.time()  # wall clock: a trace window before this was not recorded by this process
        self.enqueued = 0  # snapshots handed to the writer thread
        self.processed = 0  # of those, written or failed: once it reaches a count read earlier, those are on disk
        self.dropped = 0  # on the scheduler thread: the backlog was full
        self.failed = 0  # on the writer thread: a record could not be hashed or written
        self.error: str | None = None
        # Seconds spent recording, on the scheduler thread and on the writer thread.
        self.scheduler_s = 0.0
        self.writer_s = 0.0
        self._queue: queue.Queue[tuple[trace.Record, Any, int, str | None]] = queue.Queue(self.BACKLOG)
        if self.writer is not None:
            # Hashing a long prompt takes milliseconds, which would stall every running request if
            # the scheduler did it; the scheduler only snapshots the request.
            threading.Thread(target=self._write_loop, name="livetune-trace", daemon=True).start()
            atexit.register(self.drain)

    def record(self, req: Any, now_wall: float, now: float) -> trace.Record:
        """The complete record of a finished request."""
        return self._hashed(*self._snapshot(req, now_wall, now))

    def _hashed(self, record: trace.Record, ids: Any, cached_pages: int, namespace: str | None) -> trace.Record:
        depths = [d for d in trace.FAMILY_DEPTHS if len(ids) >= d]
        found = self.keys.digests(ids, depths + ([cached_pages] if cached_pages else []), namespace)
        return dataclasses.replace(record, families=tuple(found[d] for d in depths),
                                   cached_family=found[cached_pages] if cached_pages else None)

    def _snapshot(self, req: Any, now_wall: float, now: float) -> tuple[trace.Record, Any, int, str | None]:
        """Everything but the prefix hashes, cheap enough for the scheduler thread; SGLang does not
        change a finished request's prompt ids, so they are kept by reference."""
        ts = req.time_stats
        # Waiting-queue entry and prefill completion share the scheduler's perf_counter clock;
        # scheduler_recv_time is calibrated against another process and read 2 s early on the pod.
        # A retracted request re-enters the queue and SGLang restamps wait_queue_entry_time, so the
        # first entry comes from the stamp _keep_first_entry kept.
        arrival = getattr(ts, "livetune_first_entry", 0.0) or ts.wait_queue_entry_time
        forward = getattr(ts, "forward_entry_time", 0.0)  # SGLang sets it once, at the first forward
        first = ts.prefill_finished_time
        done = ts.completion_time or now
        ids = req.origin_input_ids
        cached = int(getattr(req, "cached_tokens", 0) or 0)
        params = req.sampling_params
        verify = getattr(req, "spec_verify_ct", 0)
        reason = type(req.finished_reason).__name__ if req.finished_reason is not None else "unknown"
        cached_pages = min(cached // self.page_size * self.page_size, len(ids))
        # Both parts, typed and in order, so ("a|b", None) and ("a", "b") stay distinct namespaces.
        parts = (getattr(req, "cache_salt", None), getattr(req, "extra_key", None))
        namespace = json.dumps(parts, default=str, separators=(",", ":")) if any(parts) else None
        record = trace.Record(
            t=now_wall,
            prompt_tokens=len(ids),
            cached_tokens=cached,
            output_tokens=len(req.output_ids),
            queue_s=getattr(ts, "queue_duration_s", None),
            ttft_s=first - arrival if first and arrival else None,
            decode_s=done - first if first else None,
            finish=_FINISH_NAMES.get(reason, reason.lower()),
            retractions=int(getattr(req, "retraction_count", 0) or 0),
            lookup_s=forward - arrival if forward and arrival else None,
            spec_accept=getattr(req, "spec_num_correct_drafts", 0) / verify + 1 if verify else None,
            temperature=getattr(params, "temperature", None),
            max_new_tokens=getattr(params, "max_new_tokens", None),
            constrained=any(getattr(params, key, None) for key in ("json_schema", "regex", "ebnf", "structural_tag")),
            priority=getattr(req, "priority", None),
            lora=getattr(req, "lora_id", None) is not None,
            session=getattr(req, "session_id", None) is not None,
            salted=namespace is not None,
            hidden_states=bool(getattr(req, "return_hidden_states", False)),
            cached_family_tokens=cached_pages,
            # Integers stay integers: a seed above 2**53 would not survive a float.
            sampling={key: value if isinstance(value, int) and not isinstance(value, bool) else float(value)
                      for key, default in _SAMPLING_DEFAULTS.items()
                      if (value := getattr(params, key, default)) not in (None, default)},
            logprobs=int(getattr(getattr(req, "logprob", None), "top_logprobs_num", 0) or 0) if getattr(req, "return_logprob", False) else -1,
            logprob_start=int(getattr(req, "logprob_start_len", -1)) if getattr(req, "return_logprob", False) else -1,
            stream=bool(getattr(req, "stream", True)),
            launched=bool(getattr(ts, "forward_entry_time", 0.0)),
            server_s=done - arrival if arrival else None,
            multimodal=getattr(req, "multimodal_inputs", None) is not None or getattr(req, "input_embeds", None) is not None
            or getattr(req, "origin_input_ids_unpadded", ids) is not ids,
        )
        return record, ids, cached_pages, namespace

    def on_finish(self, req: Any) -> None:
        # With overlap scheduling a finished request can reach the output path twice.
        if req.rid in self.recent:
            return
        self.recent = (self.recent + [req.rid])[-256:]
        if self.writer is None:
            return
        started = time.perf_counter()
        try:
            self._queue.put_nowait(self._snapshot(req, time.time(), started))
            self.enqueued += 1
        except queue.Full:
            self.dropped += 1
        self.scheduler_s += time.perf_counter() - started

    FLUSH_S = 0.2  # a busy writer still flushes this often, so records reach readers promptly

    def _write_loop(self) -> None:
        unflushed, flushed_at = 0, time.monotonic()
        while True:
            item = self._queue.get()
            started = time.perf_counter()
            try:
                self.writer.write(self._hashed(*item), flush=False)
                unflushed += 1
            except Exception as exc:
                self.failed += 1
                self.processed += 1  # it will never be written
                self.error = f"{type(exc).__name__}: {exc}"
                logger.debug("livetune: could not write a record", exc_info=True)
            try:
                # A burst is flushed once, but never held longer than FLUSH_S. A record counts as
                # processed only once flushed, so a reader waiting on the count finds it on disk.
                if unflushed and (self._queue.empty() or time.monotonic() - flushed_at >= self.FLUSH_S):
                    self.writer.flush()
                    self.processed += unflushed
                    unflushed, flushed_at = 0, time.monotonic()
            except Exception as exc:
                self.failed += unflushed
                self.processed += unflushed
                unflushed = 0
                self.error = f"{type(exc).__name__}: {exc}"
            finally:
                self.writer_s += time.perf_counter() - started
                self._queue.task_done()

    def drain(self, timeout: float = 5.0) -> bool:
        """Wait for queued records to reach the trace file; true if none are left."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.005)
        return not self._queue.unfinished_tasks

    def on_batch(self, batch: Any, result: Any) -> None:
        mode = getattr(getattr(batch, "forward_mode", None), "name", "unknown").lower()
        requests = len(getattr(batch, "reqs", ()) or ())
        # A decode step makes one token per request; extend_num_tokens is only meaningful for prefill.
        tokens = requests if mode == "decode" else int(getattr(batch, "extend_num_tokens", 0) or 0)
        launched = getattr(batch, "launch_ts", None)
        self.batches.add(mode, requests, int(tokens), bool(getattr(result, "can_run_cuda_graph", False)), time.monotonic() - launched if launched else None)

    def readback(self) -> dict[str, Any]:
        return {
            "trace_path": str(self.writer.path) if self.writer else None,
            "since": self.since,
            "records": self.writer.written if self.writer else 0,
            "dropped": self.dropped + self.failed,
            "pending": self._queue.qsize(),
            "enqueued": self.enqueued,
            "processed": self.processed,
            "scheduler_s": round(self.scheduler_s, 6),
            "writer_s": round(self.writer_s, 6),
            "error": self.error,
            "batches": self.batches.snapshot(),
        }


_TELEMETRY: dict[str, Telemetry] = {}


def _telemetry(page_size: int = 1) -> Telemetry | None:
    from sglang.srt.runtime_context import get_parallel

    if getattr(get_parallel(), "attn_tp_rank", 0) != 0:
        return None
    if "rank0" not in _TELEMETRY:
        try:
            _TELEMETRY["rank0"] = Telemetry(os.environ.get("LIVETUNE_TRACE_DIR"), page_size)
        except Exception as exc:  # telemetry is optional: a bad key or directory disables it, never serving
            logger.exception("livetune: telemetry disabled")
            disabled = Telemetry(None, page_size, keys=trace.PrefixKeys(os.urandom(32)))
            disabled.error = f"{type(exc).__name__}: {exc}"
            _TELEMETRY["rank0"] = disabled
    return _TELEMETRY["rank0"]


def _record_finished(result: Any, streamer: Any, *args: Any, **kwargs: Any) -> Any:
    # f171859 declares req keyword-only; a positional call is accepted too, so a signature change
    # upstream cannot silently empty the trace.
    req = kwargs.get("req", args[0] if args else None)
    if req is not None and req.finished():
        telemetry = _telemetry()
        if telemetry is not None:
            try:
                telemetry.on_finish(req)
            except Exception:  # telemetry must never fail a request
                telemetry.dropped += 1
                logger.debug("livetune: could not record request", exc_info=True)
    return result


def _replay_stops() -> bool:
    # Canaries that replay traffic enable it; production never pays the per-step hook.
    return os.environ.get("LIVETUNE_REPLAY_STOPS") == "1"


_FINISH_LENGTH: Any = None


def _replay_stop(result: Any, req: Any, *args: Any, **kwargs: Any) -> Any:
    global _FINISH_LENGTH
    if req.finished_reason is None:
        params = getattr(req.sampling_params, "custom_params", None)
        stop = params.get(REPLAY_STOP_KEY) if params else None
        if stop and len(req.output_ids) >= stop:
            if _FINISH_LENGTH is None:
                from sglang.srt.managers.schedule_batch import FINISH_LENGTH as _FINISH_LENGTH
            # finished_len trims tokens a speculative step accepted past the stop, as SGLang does for stop tokens.
            req.finished_reason = _FINISH_LENGTH(length=stop)
            req.finished_len = stop
    return result


def _keep_first_entry(result: Any, stats: Any, *args: Any, **kwargs: Any) -> Any:
    if not getattr(stats, "livetune_first_entry", 0.0):
        stats.livetune_first_entry = stats.wait_queue_entry_time
    return result


def _forget_first_entry(result: Any, stats: Any, *args: Any, **kwargs: Any) -> Any:
    # A prefill retry starts the request's timing over.
    stats.livetune_first_entry = 0.0
    return result


def _record_batch(result: Any, scheduler: Any, batch: Any, batch_result: Any, *args: Any, **kwargs: Any) -> Any:
    telemetry = _telemetry(int(getattr(scheduler, "page_size", 1) or 1))
    if telemetry is not None and batch is not None:
        try:
            telemetry.on_batch(batch, batch_result)
        except Exception:
            telemetry.dropped += 1
    return result


def _tuner(controller: Any) -> LiveTuner:
    tuner = getattr(controller, "_livetune", None)
    if tuner is None:
        tuner = LiveTuner(controller.scheduler)
        controller._livetune = tuner
        controller.scheduler._livetune = tuner
    return tuner


def _add_handlers(handlers: dict, controller: Any) -> dict:
    from sglang.srt.managers.scheduler_components.internal_state import UpdateRejected, _UpdateHandler

    tuner = _tuner(controller)

    def validate(key: str, value: Any) -> None:
        # Any error, expected or not, must become a rejection: an exception
        # escaping an update handler takes the scheduler down.
        try:
            tuner.validate(key, value)
        except Exception as exc:
            raise UpdateRejected(f"{key}={value!r} rejected: {exc}") from exc

    for key in [*KNOBS, VARIANT_KEY]:
        handlers[key] = _UpdateHandler(validate, tuner.apply)
    return handlers


def _add_readback(output: Any, controller: Any, *args: Any, **kwargs: Any) -> Any:
    output.internal_state["livetune"] = _tuner(controller).readback()
    return output


def _gate_admission(original: Any, scheduler: Any, *args: Any, **kwargs: Any) -> int:
    tuner = getattr(scheduler, "_livetune", None)
    if tuner is not None and tuner.admission_blocked():
        return 0
    return original(scheduler, *args, **kwargs)


def _switch_when_idle(result: Any, scheduler: Any, *args: Any, **kwargs: Any) -> Any:
    tuner = getattr(scheduler, "_livetune", None)
    if tuner is not None:
        tuner.on_idle()
    return result


def _install_startup_variant(runner: Any, *args: Any, **kwargs: Any) -> None:
    variant_id = int(os.environ.get("LIVETUNE_STARTUP_VARIANT", "0") or 0)
    if variant_id == variants.STOCK or getattr(runner, "_livetune_variant", None) is not None:
        return None
    from sglang.srt.runtime_context import get_parallel

    parallel = get_parallel()
    ctx = {"model_runner": runner, "scheduler": None, "tp_rank": parallel.tp_rank, "tp_size": parallel.tp_size}
    # Fail startup rather than serve a model whose ranks may run different code.
    runner._livetune_variant = variants.install(variants.resolve(variant_id), runner.model, ctx)
    runner._livetune_variant_id = variant_id
    logger.info("livetune: installed startup variant %s before CUDA graph capture", variant_id)
    return None


def register() -> None:
    from sglang.srt.plugins.hook_registry import HookRegistry, HookType

    HookRegistry.register(f"{_TARGET}._update_handlers", _add_handlers, HookType.AFTER)
    HookRegistry.register(f"{_TARGET}.get_internal_state", _add_readback, HookType.AFTER)
    HookRegistry.register(f"{_SCHEDULER}.get_num_allocatable_reqs", _gate_admission, HookType.AROUND)
    HookRegistry.register(f"{_SCHEDULER}.on_idle", _switch_when_idle, HookType.AFTER)
    HookRegistry.register(f"{_MODEL_RUNNER}.init_cuda_graphs", _install_startup_variant, HookType.BEFORE)
    HookRegistry.register(f"{_STREAMER}._maybe_log_time_stats", _record_finished, HookType.AFTER)
    HookRegistry.register(f"{_SCHEDULER}.process_batch_result", _record_batch, HookType.AFTER)
    HookRegistry.register(f"{_TIME_STATS}.set_wait_queue_entry_time", _keep_first_entry, HookType.AFTER)
    HookRegistry.register(f"{_TIME_STATS}.reset_prefill_retry_time", _forget_first_entry, HookType.AFTER)
    if _replay_stops():
        HookRegistry.register(f"{_REQ}.update_finish_state", _replay_stop, HookType.AFTER)
