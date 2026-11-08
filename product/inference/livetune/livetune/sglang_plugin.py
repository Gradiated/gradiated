from __future__ import annotations

import logging
import os
import time
from typing import Any

from livetune import trace, variants
from livetune.knobs import KNOBS, SCHEDULE_POLICIES, VARIANT_KEY, InvalidSetting

logger = logging.getLogger(__name__)

_TARGET = "sglang.srt.managers.scheduler_components.internal_state.SchedulerInternalStateController"
_SCHEDULER = "sglang.srt.managers.scheduler.Scheduler"
_MODEL_RUNNER = "sglang.srt.model_executor.model_runner.ModelRunner"
_STREAMER = "sglang.srt.managers.scheduler_components.output_streamer.SchedulerOutputStreamer"


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
        # Install and graph recapture succeed together on every rank, or the attempt fails.
        if self.variant is not None:
            variants.uninstall(self.variant)
            self.variant = None
        error: Exception | None = None
        try:
            if variant_id != variants.STOCK:
                self._install(variant_id)
            self._recapture(self.scheduler.tp_worker.model_runner)
        except Exception as exc:
            error = exc
        if self._all_ranks_agree(error is None):
            return None
        return error or RuntimeError("variant switch failed on another tensor-parallel rank")

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
    def runtime(self) -> dict[str, str | None]:
        # Hashing thousands of files takes seconds on a busy host, so it waits for the first readback.
        if self._runtime is None:
            self._runtime = {
                "sglang": _source_digest("sglang"),
                "livetune": _source_digest("livetune"),
                "packages": _packages_digest(),
                "inputs": _inputs_digest(os.environ.get("LIVETUNE_RUNTIME_INPUTS", "")),
            }
        return self._runtime

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
            "startup_variant": self.startup_variant,
            "runtime": self.runtime,
            "telemetry": telemetry.readback() if (telemetry := _TELEMETRY.get("rank0")) else None,
            "gpu": self.gpu,
            "variant": {"name": self.variant.source.name, "sha256": self.variant.source.sha256} if self.variant else None,
            "variants": catalog,
            "pending_variant": self.pending_variant,
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

    def __init__(self, directory: str | None, page_size: int = 1, keys: trace.PrefixKeys | None = None) -> None:
        self.writer = trace.Writer(directory) if directory else None
        self.keys = keys or trace.PrefixKeys(directory=directory)
        self.page_size = max(page_size, 1)
        self.batches = trace.BatchStats()
        self.recent: list[str] = []
        self.dropped = 0
        self.error: str | None = None

    def record(self, req: Any, now_wall: float, now: float) -> trace.Record:
        ts = req.time_stats
        # Waiting-queue entry and prefill completion share the scheduler's perf_counter clock;
        # scheduler_recv_time is calibrated against another process and read 2 s early on the pod.
        arrival = ts.wait_queue_entry_time
        first = ts.prefill_finished_time
        done = ts.completion_time or now
        ids = req.origin_input_ids
        cached = int(getattr(req, "cached_tokens", 0) or 0)
        params = req.sampling_params
        verify = getattr(req, "spec_verify_ct", 0)
        reason = type(req.finished_reason).__name__ if req.finished_reason is not None else "unknown"
        cached_pages = cached // self.page_size * self.page_size
        return trace.Record(
            t=now_wall,
            prompt_tokens=len(ids),
            cached_tokens=cached,
            output_tokens=len(req.output_ids),
            queue_s=getattr(ts, "queue_duration_s", None),
            ttft_s=first - arrival if first and arrival else None,
            decode_s=done - first if first else None,
            finish=_FINISH_NAMES.get(reason, reason.lower()),
            retractions=int(getattr(req, "retraction_count", 0) or 0),
            spec_accept=getattr(req, "spec_num_correct_drafts", 0) / verify + 1 if verify else None,
            temperature=getattr(params, "temperature", None),
            max_new_tokens=getattr(params, "max_new_tokens", None),
            constrained=any(getattr(params, key, None) for key in ("json_schema", "regex", "ebnf", "structural_tag")),
            priority=getattr(req, "priority", None),
            lora=getattr(req, "lora_id", None) is not None,
            session=getattr(req, "session_id", None) is not None,
            families=self.keys.families(ids),
            cached_family=self.keys.digest(ids, cached_pages) if cached_pages else None,
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

    def on_finish(self, req: Any) -> None:
        # With overlap scheduling a finished request can reach the output path twice.
        if req.rid in self.recent:
            return
        self.recent = (self.recent + [req.rid])[-256:]
        if self.writer is not None:
            self.writer.write(self.record(req, time.time(), time.perf_counter()))

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
            "records": self.writer.written if self.writer else 0,
            "dropped": self.dropped,
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
    req = kwargs.get("req")
    if req is not None and req.finished():
        telemetry = _telemetry()
        if telemetry is not None:
            try:
                telemetry.on_finish(req)
            except Exception:  # telemetry must never fail a request
                telemetry.dropped += 1
                logger.debug("livetune: could not record request", exc_info=True)
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
