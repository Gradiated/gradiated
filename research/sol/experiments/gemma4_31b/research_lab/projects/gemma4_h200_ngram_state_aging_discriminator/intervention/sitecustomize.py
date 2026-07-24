"""Install the frozen NGRAM aging discriminator before SGLang imports.

The scientific intervention is exactly one online-corpus reset when 650
distinct primary request IDs have entered NGRAM decoding. Prefix/SWA/KV state
is deliberately untouched. The remaining changes expose read-only corpus
state and time the existing production operations.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from types import MethodType


ROOT = Path(os.environ.get("NGRAM_AGING_ROOT", "/work"))
OUT = Path(os.environ.get("NGRAM_AGING_OUT", str(ROOT / "out")))
ARMED = OUT / "PRIMARY_ARMED"
TRACE = OUT / "ngram-ops.jsonl"
ROLLOVER_REQUESTS = 650


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _install_cpp_probe() -> dict[str, object]:
    import sglang

    package = Path(sglang.__file__).resolve().parent
    destination = package / "jit_kernel/csrc/ngram_corpus"
    files = ["trie.h", "trie.cpp", "ngram.h", "ngram.cpp", "ngram_corpus_ffi.cpp"]
    rows = []
    for name in files:
        source = ROOT / "intervention" / name
        target = destination / name
        target.chmod(0o644)
        shutil.copyfile(source, target)
        rows.append(
            {
                "file": name,
                "source_sha256": _sha256(source),
                "installed_sha256": _sha256(target),
            }
        )
    return {"package": str(package), "files": rows}


OUT.mkdir(parents=True, exist_ok=True)
_patch = _install_cpp_probe()

from sglang.srt.speculative.ngram_worker import NGRAMWorker  # noqa: E402


_original_init = NGRAMWorker.__init__
_original_forward = NGRAMWorker.forward_batch_generation
_state_lock = threading.Lock()


def _rss_kib() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except Exception:
        return None
    return None


def _stats(worker: NGRAMWorker) -> dict[str, int | float | bool | None]:
    state = worker._aging_state
    obj = worker.ngram_corpus._obj
    result: dict[str, int | float | bool | None] = {
        "wall_time": time.time(),
        "monotonic_ns": time.monotonic_ns(),
        "primary_unique_requests": len(state["seen"]),
        "rollover_done": state["rollover_done"],
        "prepare_calls": state["prepare_calls"],
        "update_calls": state["update_calls"],
        "outer_forward_calls": state["outer_forward_calls"],
        "synchronize_seconds": state["synchronize_ns"] / 1e9,
        "batch_get_seconds": state["batch_get_ns"] / 1e9,
        "batch_put_seconds": state["batch_put_ns"] / 1e9,
        "target_verify_seconds": state["target_verify_ns"] / 1e9,
        "target_other_seconds": state["target_other_ns"] / 1e9,
        "ngram_forward_seconds": state["outer_forward_ns"] / 1e9,
        "max_synchronize_ms": state["max_synchronize_ns"] / 1e6,
        "max_batch_get_ms": state["max_batch_get_ns"] / 1e6,
        "max_batch_put_ms": state["max_batch_put_ns"] / 1e6,
        "process_rss_kib": _rss_kib(),
    }
    try:
        result.update(
            {
                "online_trie_used_nodes": int(obj.online_trie_used_nodes()),
                "online_trie_capacity": int(obj.online_trie_capacity()),
                "native_match_state_count": int(obj.match_state_count()),
                "pending_insert_count": int(obj.pending_insert_count()),
                "python_match_state_count": len(
                    worker.ngram_corpus._req_id_to_state_id
                ),
            }
        )
    except Exception as exc:
        result["native_stats_error"] = repr(exc)
    return result


def _emit(worker: NGRAMWorker, event: str, force: bool = False) -> None:
    state = worker._aging_state
    now = time.monotonic_ns()
    if not force and now - state["last_emit_ns"] < 1_000_000_000:
        return
    with _state_lock:
        if not force and now - state["last_emit_ns"] < 1_000_000_000:
            return
        state["last_emit_ns"] = now
        row = {"event": event, **_stats(worker)}
        with TRACE.open("a") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _patched_init(self: NGRAMWorker, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self._aging_state = {
        "seen": set(),
        "rollover_done": False,
        "prepare_calls": 0,
        "update_calls": 0,
        "outer_forward_calls": 0,
        "synchronize_ns": 0,
        "batch_get_ns": 0,
        "batch_put_ns": 0,
        "target_verify_ns": 0,
        "target_other_ns": 0,
        "outer_forward_ns": 0,
        "max_synchronize_ns": 0,
        "max_batch_get_ns": 0,
        "max_batch_put_ns": 0,
        "last_emit_ns": 0,
    }
    target_original = self.target_worker.forward_batch_generation

    def target_timed(_target, *target_args, **target_kwargs):
        started = time.perf_counter_ns()
        try:
            return target_original(*target_args, **target_kwargs)
        finally:
            elapsed = time.perf_counter_ns() - started
            key = (
                "target_verify_ns"
                if target_kwargs.get("is_verify", False)
                else "target_other_ns"
            )
            self._aging_state[key] += elapsed

    self.target_worker.forward_batch_generation = MethodType(
        target_timed, self.target_worker
    )
    _emit(self, "worker_initialized", force=True)
    atexit.register(lambda: _emit(self, "process_exit", force=True))


def _patched_prepare(self: NGRAMWorker, batch):
    state = self._aging_state
    if ARMED.exists():
        state["seen"].update(str(req.rid) for req in batch.reqs)
        if len(state["seen"]) >= ROLLOVER_REQUESTS and not state["rollover_done"]:
            reset_started = time.perf_counter_ns()
            self.ngram_corpus.reset()
            state["rollover_done"] = True
            with TRACE.open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "event": "corpus_rollover",
                            "rollover_bound_requests": ROLLOVER_REQUESTS,
                            "observed_unique_requests": len(state["seen"]),
                            "reset_seconds": (
                                time.perf_counter_ns() - reset_started
                            )
                            / 1e9,
                            "wall_time": time.time(),
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    sync_started = time.perf_counter_ns()
    self.ngram_corpus.synchronize()
    sync_ns = time.perf_counter_ns() - sync_started
    state["synchronize_ns"] += sync_ns
    state["max_synchronize_ns"] = max(state["max_synchronize_ns"], sync_ns)

    req_ids = []
    batch_tokens = []
    total_lens = []
    for req in batch.reqs:
        check_token = self._efficient_concat_last_n(
            req.origin_input_ids, req.output_ids, self.max_trie_depth
        )
        req_ids.append(req.rid)
        batch_tokens.append(check_token)
        total_lens.append(len(req.origin_input_ids) + len(req.output_ids))

    get_started = time.perf_counter_ns()
    req_drafts, mask = self.ngram_corpus.batch_get(
        req_ids, batch_tokens, total_lens
    )
    get_ns = time.perf_counter_ns() - get_started
    state["batch_get_ns"] += get_ns
    state["max_batch_get_ns"] = max(state["max_batch_get_ns"], get_ns)
    state["prepare_calls"] += 1

    total_draft_token_num = len(req_drafts)
    expected = batch.batch_size() * self.draft_token_num
    assert total_draft_token_num == expected, (
        f"{total_draft_token_num=}, {expected=}"
    )
    _emit(self, "operations")
    return req_drafts, mask


def _patched_update(self: NGRAMWorker, batch):
    batch_tokens = []
    for req in batch.reqs:
        batch_tokens.append(
            self._efficient_concat_last_n(
                req.origin_input_ids, req.output_ids, self.max_trie_depth
            )
        )
    started = time.perf_counter_ns()
    self.ngram_corpus.batch_put(batch_tokens)
    elapsed = time.perf_counter_ns() - started
    state = self._aging_state
    state["batch_put_ns"] += elapsed
    state["max_batch_put_ns"] = max(state["max_batch_put_ns"], elapsed)
    state["update_calls"] += 1


def _patched_forward(self: NGRAMWorker, *args, **kwargs):
    started = time.perf_counter_ns()
    try:
        return _original_forward(self, *args, **kwargs)
    finally:
        state = self._aging_state
        state["outer_forward_ns"] += time.perf_counter_ns() - started
        state["outer_forward_calls"] += 1


NGRAMWorker.__init__ = _patched_init
NGRAMWorker._prepare_draft_tokens = _patched_prepare
NGRAMWorker._update_ngram_corpus = _patched_update
NGRAMWorker.forward_batch_generation = _patched_forward

_atomic(
    OUT / "PATCH_STATE.json",
    {
        "kind": "ngram_state_aging_candidate_patch",
        "rollover_requests": ROLLOVER_REQUESTS,
        "prefix_cache_reset": False,
        "swa_cache_reset": False,
        "kv_cache_reset": False,
        "cpp_probe": _patch,
        "sitecustomize_sha256": _sha256(Path(__file__)),
    },
)
