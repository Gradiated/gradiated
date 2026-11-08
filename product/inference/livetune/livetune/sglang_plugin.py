from __future__ import annotations

import gc
import logging
import os
import time
from typing import Any

from livetune import variants
from livetune.knobs import KNOBS, VARIANT_KEY, InvalidSetting

logger = logging.getLogger(__name__)

_TARGET = "sglang.srt.managers.scheduler_components.internal_state.SchedulerInternalStateController"
_SCHEDULER = "sglang.srt.managers.scheduler.Scheduler"
_MODEL_RUNNER = "sglang.srt.model_executor.model_runner.ModelRunner"


class LiveTuner:
    def __init__(self, scheduler: Any) -> None:
        runner = scheduler.tp_worker.model_runner
        self.scheduler = scheduler
        self.page_size = int(getattr(scheduler, "page_size", 1) or 1)
        self.startup = {
            "max_running_requests": scheduler.max_running_requests,
            "chunked_prefill_size": scheduler.chunked_prefill_size,
            "max_prefill_tokens": scheduler.max_prefill_tokens,
        }
        self.startup[VARIANT_KEY] = getattr(runner, "_livetune_variant_id", variants.STOCK)
        self.settings: dict[str, Any] = dict(self.startup)
        self.variant: variants.InstalledVariant | None = getattr(runner, "_livetune_variant", None)
        self.pending_variant: int | None = None
        self.pending_since_step = 0
        self.drain_steps = int(os.environ.get("LIVETUNE_DRAIN_STEPS", "6000"))
        self.changes: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []

    def validate(self, key: str, value: Any) -> None:
        if key == VARIANT_KEY:
            if os.environ.get("LIVETUNE_LIVE_VARIANTS") != "1":
                raise InvalidSetting(f"live {VARIANT_KEY} switching is disabled; set LIVETUNE_STARTUP_VARIANT and restart")
            from sglang.srt.runtime_context import get_parallel

            # Data-parallel schedulers drain independently, so their switches cannot be made atomic.
            if getattr(get_parallel(), "dp_size", 1) > 1:
                raise InvalidSetting(f"live {VARIANT_KEY} switching is not supported with data parallelism")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidSetting(f"{VARIANT_KEY} must be a variant id (0 = stock)")
            if value != variants.STOCK:
                variants.resolve(value)
            return
        KNOBS[key].validate(value, self.startup, self.page_size)

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
            overrides = {"pp_max_micro_batch_size": max(value // get_parallel().pp_size, 1)}
        elif key == "chunked_prefill_size":
            self.scheduler.chunked_prefill_size = value
            overrides = {key: value}
        elif key == "max_prefill_tokens":
            self.scheduler.max_prefill_tokens = value
            overrides = {key: value}
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
        self.variant = variants.install(variants.resolve(variant_id), runner.model, ctx)

    def _switch_variant(self, variant_id: int) -> None:
        runner = self.scheduler.tp_worker.model_runner
        previous = self.settings[VARIANT_KEY]
        if self.variant is not None:
            variants.uninstall(self.variant)
            self.variant = None
        error: Exception | None = None
        if variant_id != variants.STOCK:
            try:
                self._install(variant_id)
            except Exception as exc:
                error = exc
        if not self._all_ranks_agree(error is None):
            if self.variant is not None:
                variants.uninstall(self.variant)
                self.variant = None
            error = error or RuntimeError("variant failed on another tensor-parallel rank")
            # Fall back to the variant that was serving; stock only if it cannot come back on every rank.
            restored_ok = True
            if previous != variants.STOCK:
                try:
                    self._install(previous)
                except Exception:
                    restored_ok = False
                if not self._all_ranks_agree(restored_ok) and self.variant is not None:
                    variants.uninstall(self.variant)
                    self.variant = None
            self.settings[VARIANT_KEY] = previous if self.variant is not None or previous == variants.STOCK else variants.STOCK
        # Graphs must always match the code now installed, stock or variant.
        self._recapture(runner)
        if error is not None:
            raise error

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
        import torch

        runner.decode_cuda_graph_runner = None
        gc.collect()
        torch.cuda.synchronize()
        runner.init_decode_cuda_graph()
        torch.cuda.synchronize()

    def readback(self) -> dict[str, Any]:
        return {
            "settings": dict(self.settings),
            "startup": dict(self.startup),
            "page_size": self.page_size,
            "variant": {"name": self.variant.source.name, "sha256": self.variant.source.sha256} if self.variant else None,
            "pending_variant": self.pending_variant,
            "recent_changes": self.changes[-10:],
            "recent_errors": self.errors[-5:],
        }


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
