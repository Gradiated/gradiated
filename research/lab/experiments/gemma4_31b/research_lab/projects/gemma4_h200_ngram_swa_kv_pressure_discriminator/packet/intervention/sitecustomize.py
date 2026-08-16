"""Bind and observe the single SWA leaf-split pressure intervention."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time


ROOT = Path(os.environ.get("SWA_PRESSURE_ROOT", "/work"))
OUT = Path(os.environ.get("SWA_PRESSURE_OUT", str(ROOT / "out")))
TRACE = OUT / "swa-ownership.jsonl"
SOURCE = ROOT / "inputs/source/mem_cache/swa_radix_cache.py"
_write_lock = threading.Lock()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


OUT.mkdir(parents=True, exist_ok=True)

import sglang  # noqa: E402


package = Path(sglang.__file__).resolve().parent
target = package / "srt/mem_cache/swa_radix_cache.py"
target.chmod(0o644)
shutil.copyfile(SOURCE, target)

from sglang.srt.mem_cache.swa_radix_cache import SWARadixCache  # noqa: E402
import torch  # noqa: E402


_original_init = SWARadixCache.__init__
_original_inc_lock_ref = SWARadixCache.inc_lock_ref
_original_evict = SWARadixCache.evict


def _memory() -> dict[str, int | None]:
    try:
        stats = torch.cuda.memory_stats()
        return {
            "torch_allocated_bytes": torch.cuda.memory_allocated(),
            "torch_reserved_bytes": torch.cuda.memory_reserved(),
            "torch_inactive_split_bytes": stats.get(
                "inactive_split_bytes.all.current"
            ),
            "torch_active_bytes": stats.get("active_bytes.all.current"),
        }
    except Exception:
        return {
            "torch_allocated_bytes": None,
            "torch_reserved_bytes": None,
            "torch_inactive_split_bytes": None,
            "torch_active_bytes": None,
        }


def _emit(cache: SWARadixCache, event: str, detail: dict | None = None) -> None:
    now = time.monotonic_ns()
    if (
        event not in {"cache_initialized", "process_exit"}
        and now - cache._pressure_last_emit_ns < 1_000_000_000
    ):
        return
    cache._pressure_last_emit_ns = now
    allocator = cache.token_to_kv_pool_allocator
    row = {
        "event": event,
        "wall_time": time.time(),
        "monotonic_ns": now,
        "pid": os.getpid(),
        "full_available_tokens": allocator.full_available_size(),
        "swa_available_tokens": allocator.swa_available_size(),
        "full_evictable_tokens": cache.full_evictable_size(),
        "swa_evictable_tokens": cache.swa_evictable_size(),
        "full_protected_tokens": cache.full_protected_size(),
        "swa_protected_tokens": cache.swa_protected_size(),
        **_memory(),
        **(detail or {}),
    }
    with _write_lock:
        with TRACE.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _patched_init(self: SWARadixCache, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self._pressure_last_emit_ns = 0
    _emit(self, "cache_initialized")
    atexit.register(lambda: _emit(self, "process_exit"))


def _patched_inc_lock_ref(self: SWARadixCache, node):
    leaf_tokens = len(node.value) if node is not self.root_node else 0
    result = _original_inc_lock_ref(self, node)
    _emit(
        self,
        "inc_lock_ref",
        {
            "locked_leaf_tokens": leaf_tokens,
            "locked_leaf_full_ref": node.full_lock_ref,
            "locked_leaf_swa_ref": node.swa_lock_ref,
            "swa_uuid_for_lock": result.swa_uuid_for_lock,
        },
    )
    return result


def _patched_evict(self: SWARadixCache, params):
    result = _original_evict(self, params)
    _emit(
        self,
        "evict",
        {
            "requested_full_tokens": params.num_tokens,
            "requested_swa_tokens": params.swa_num_tokens,
            "evicted_full_tokens": result.num_tokens_evicted,
            "evicted_swa_tokens": result.swa_num_tokens_evicted,
        },
    )
    return result


SWARadixCache.__init__ = _patched_init
SWARadixCache.inc_lock_ref = _patched_inc_lock_ref
SWARadixCache.evict = _patched_evict

_atomic(
    OUT / "PATCH_STATE.json",
    {
        "kind": "page_aligned_swa_leaf_split_on_insert",
        "environment": os.environ.get("SGLANG_OPT_SWA_SPLIT_LEAF_ON_INSERT"),
        "source_path": str(SOURCE),
        "source_sha256": _sha256(SOURCE),
        "installed_path": str(target),
        "installed_sha256": _sha256(target),
        "semantics": "cache ownership geometry only; requests and scheduler unchanged",
    },
)
