"""vLLM worker extension: hot-reload a candidate forward pass on every rank.

Loaded with ``worker_extension_cls="tkcc.worker_ext.TkccWorkerExtension"`` and
driven through ``LLM.collective_rpc``. A candidate is a Python source file that
defines either

* ``install(model, patch, ctx)``: free-form patching; every change must go
  through ``patch(obj_or_module_path, name, value)`` so teardown can undo it, or
* ``forward(self, input_ids, positions, intermediate_tensors=None,
  inputs_embeds=None, **kwargs)``: a replacement for the text model's forward.

After installation the CUDA graphs are recaptured so replayed decode steps run
the candidate code. Teardown undoes the patches and recaptures again.
"""

from __future__ import annotations

import gc
import hashlib
import os
import sys
import time
import traceback
import types
from pathlib import Path
from typing import Any

import torch

from tkcc.patcher import Patcher

JOB_ROOT = Path(os.environ.get("TKCC_JOB_ROOT", "/home/tkcc/jobs"))


def _rank() -> int:
    if torch.distributed.is_available() and torch.distributed.is_initialized():
        return torch.distributed.get_rank()
    return 0


def _content_checksum(tensor: torch.Tensor) -> torch.Tensor:
    """Sum and xor of every 4-byte word (zero-padded), so any byte change is caught."""
    raw = tensor.contiguous().reshape(-1).view(torch.uint8)
    pad = (-raw.numel()) % 4
    if pad:
        raw = torch.cat([raw, raw.new_zeros(pad)])
    words = raw.view(torch.int32)
    total = words.sum(dtype=torch.int64)
    if hasattr(torch, "hash_tensor"):
        mixed = torch.hash_tensor(words, mode=0).view(torch.int64)
    else:
        weights = torch.arange(words.numel(), device=words.device, dtype=torch.int64) % 2_147_483_629 + 1
        mixed = (words.to(torch.int64) * weights).sum()
    return torch.stack([total, mixed])


def _text_model(model: torch.nn.Module) -> torch.nn.Module:
    for module in model.modules():
        if type(module).__name__ == "DeepseekV4Model":
            return module
    return model


class TkccWorkerExtension:
    _tkcc_patcher: Patcher | None = None
    _tkcc_module: types.ModuleType | None = None
    _tkcc_fingerprint: dict[str, tuple[int, ...]] | None = None
    _tkcc_profiler: Any = None

    def _tkcc_runner(self):
        return self.model_runner

    def _tkcc_model(self) -> torch.nn.Module:
        return self._tkcc_runner().get_model()

    def _tkcc_clear_graphs(self) -> None:
        runner = self._tkcc_runner()
        manager = getattr(runner, "cudagraph_manager", None)
        if manager is not None and hasattr(manager, "graphs"):
            manager.graphs.clear()
            manager._graphs_captured = False
            breakable = getattr(manager, "breakable_cg_runner", None)
            if breakable is not None and hasattr(type(breakable), "clear_all_graphs"):
                type(breakable).clear_all_graphs()
        else:
            from vllm.compilation.cuda_graph import CUDAGraphWrapper

            CUDAGraphWrapper.clear_all_graphs()
            try:
                from vllm.compilation.breakable_cuda_graph import BreakableCUDAGraphWrapper

                BreakableCUDAGraphWrapper.clear_all_graphs()
            except ImportError:
                pass
        gc.collect()
        torch.cuda.synchronize()

    def _tkcc_recapture(self) -> float:
        start = time.perf_counter()
        try:
            from vllm.compilation.breakable_cudagraph import BreakableCUDAGraphCapture

            stale = BreakableCUDAGraphCapture.current()
            if stale is not None:
                print(f"[tkcc rank {_rank()}] clearing stale breakable capture {stale!r}", file=sys.stderr, flush=True)
                BreakableCUDAGraphCapture._tls.active = None
        except ImportError:
            pass
        self._tkcc_clear_graphs()
        self._tkcc_runner().capture_model()
        torch.cuda.synchronize()
        return time.perf_counter() - start

    def tkcc_runner_kind(self) -> dict[str, Any]:
        runner = self._tkcc_runner()
        manager = getattr(runner, "cudagraph_manager", None)
        return {
            "runner": f"{type(runner).__module__}.{type(runner).__qualname__}",
            "graph_manager": type(manager).__name__ if manager is not None else None,
            "model": type(self._tkcc_model()).__name__,
            "text_model": type(_text_model(self._tkcc_model())).__name__,
            "rank": _rank(),
        }

    def tkcc_fingerprint(self) -> dict[str, tuple[int, ...]]:
        """Pointer plus full-content checksums of every parameter, computed on the GPU."""
        names: list[str] = []
        pointers: list[int] = []
        sums: list[torch.Tensor] = []
        with torch.no_grad():
            for name, param in self._tkcc_model().named_parameters():
                if param.device.type != "cuda" or param.numel() == 0:
                    continue
                names.append(name)
                pointers.append(param.data_ptr())
                sums.append(_content_checksum(param.detach()))
            values = torch.stack(sums).tolist() if sums else []
        return {name: (pointer, *map(int, value)) for name, pointer, value in zip(names, pointers, values)}

    def tkcc_hot_reload(self, job_id: str, source: str) -> dict[str, Any]:
        rank = _rank()
        result: dict[str, Any] = {"rank": rank, "ok": False}
        if self._tkcc_patcher is not None:
            self.tkcc_teardown()
        lowered = source.lower()
        if any(word in lowered for word in ("torch.profiler", "cupti", "kineto", "_enable_profiler")):
            return {**result, "error": "candidates may not start profilers: CUPTI overhead persists in the engine process and corrupts later measurements; use `tkcc submit --tier fast --profile`"}
        job_dir = JOB_ROOT / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        path = job_dir / f"candidate_rank{rank}.py"
        path.write_text(source)
        model = self._tkcc_model()
        text_model = _text_model(model)
        patcher = Patcher()
        self._tkcc_patcher = patcher
        try:
            if TkccWorkerExtension._tkcc_fingerprint is None:
                # Stock weights never legitimately change, so one startup fingerprint serves every job.
                TkccWorkerExtension._tkcc_fingerprint = self.tkcc_fingerprint()
            start = time.perf_counter()
            module_name = f"tkcc_candidate_{hashlib.sha1(job_id.encode()).hexdigest()[:12]}"
            module = types.ModuleType(module_name)
            module.__file__ = str(path)
            sys.modules[module_name] = module
            # Recorded before exec so teardown purges its imports even if top-level code raises.
            self._tkcc_module = module
            exec(compile(source, str(path), "exec"), module.__dict__)
            ctx = {
                "rank": rank,
                "tp_size": torch.distributed.get_world_size() if torch.distributed.is_initialized() else 1,
                "device": torch.cuda.current_device(),
                "vllm_config": getattr(self, "vllm_config", None),
                "text_model": text_model,
                "job_dir": str(job_dir),
            }
            if hasattr(module, "install"):
                module.install(model, patcher, ctx)
            elif hasattr(module, "forward"):
                patcher(text_model, "forward", types.MethodType(module.forward, text_model))
            else:
                raise ValueError("candidate must define install(model, patch, ctx) or forward(...)")
            torch.cuda.synchronize()
            result["install_s"] = time.perf_counter() - start
            result["patches"] = len(patcher)
            result["recapture_s"] = self._tkcc_recapture()
            result["ok"] = True
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["traceback"] = traceback.format_exc()[-6000:]
            print(f"[tkcc rank {rank}] hot_reload failed:\n{result['traceback']}", file=sys.stderr, flush=True)
            try:
                self.tkcc_teardown()
            except Exception as undo_exc:
                result["teardown_error"] = f"{type(undo_exc).__name__}: {undo_exc}"
        return result

    def tkcc_weights_unchanged(self) -> dict[str, Any]:
        before = TkccWorkerExtension._tkcc_fingerprint
        if before is None:
            return {"ok": True, "checked": 0}
        after = self.tkcc_fingerprint()
        changed = [name for name, value in before.items() if after.get(name) != value]
        return {"ok": not changed, "checked": len(before), "changed": changed[:20]}

    def tkcc_teardown(self) -> dict[str, Any]:
        restored = 0
        if self._tkcc_patcher is not None:
            restored = self._tkcc_patcher.undo()
        if self._tkcc_module is not None:
            sys.modules.pop(self._tkcc_module.__name__, None)
            # Candidates may import helper modules from their job directory; drop those too.
            job_dir = os.path.dirname(self._tkcc_module.__file__ or "") + os.sep
            for name, module in list(sys.modules.items()):
                if (getattr(module, "__file__", None) or "").startswith(job_dir):
                    sys.modules.pop(name, None)
            gc.collect()
        self._tkcc_patcher = None
        self._tkcc_module = None
        recapture_s = self._tkcc_recapture()
        torch.cuda.empty_cache()
        return {"rank": _rank(), "restored": restored, "recapture_s": recapture_s}

    def tkcc_profile_start(self) -> bool:
        if _rank() != 0:
            return False
        self._tkcc_profiler = torch.profiler.profile(
            activities=[torch.profiler.ProfilerActivity.CUDA]
        )
        self._tkcc_profiler.__enter__()
        return True

    def tkcc_profile_stop(self, top: int = 30) -> list[dict[str, Any]]:
        if _rank() != 0 or self._tkcc_profiler is None:
            return []
        profiler = self._tkcc_profiler
        self._tkcc_profiler = None
        torch.cuda.synchronize()
        profiler.__exit__(None, None, None)
        rows = []
        total = 0.0
        for event in profiler.key_averages():
            device_us = getattr(event, "device_time_total", None)
            if device_us is None:
                device_us = getattr(event, "cuda_time_total", 0.0)
            if device_us <= 0:
                continue
            total += device_us
            rows.append({"kernel": event.key[:160], "calls": event.count, "device_us": round(device_us, 1)})
        rows.sort(key=lambda row: -row["device_us"])
        for row in rows:
            row["share"] = round(row["device_us"] / total, 4) if total else 0.0
        return rows[:top]

    def tkcc_call(self, name: str) -> Any:
        """Call ``name()`` in the installed candidate (used by measurement experiments)."""
        if self._tkcc_module is None:
            raise RuntimeError("no candidate installed")
        return getattr(self._tkcc_module, name)()

    def tkcc_reload_ext(self) -> list[str]:
        """Re-import this module and rebind its methods, so worker fixes need no restart."""
        import importlib

        import tkcc.patcher
        import tkcc.worker_ext

        importlib.reload(tkcc.patcher)
        module = importlib.reload(tkcc.worker_ext)
        rebound = []
        for name, value in vars(module.TkccWorkerExtension).items():
            if callable(value) and (name.startswith("tkcc_") or name.startswith("_tkcc_")):
                setattr(type(self), name, value)
                rebound.append(name)
        return rebound

    def tkcc_free_memory(self) -> dict[str, float]:
        free, total = torch.cuda.mem_get_info()
        return {"rank": _rank(), "free_gib": free / 2**30, "total_gib": total / 2**30}
