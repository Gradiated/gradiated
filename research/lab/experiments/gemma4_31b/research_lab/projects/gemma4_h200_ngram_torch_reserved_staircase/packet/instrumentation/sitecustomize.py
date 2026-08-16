"""Bounded allocator-history observer for the stock SWA attribution prefix."""

from __future__ import annotations

import json
import os
from pathlib import Path
import pickle
import threading
import time

import torch


OUT = Path(os.environ.get("TORCH_STAIRCASE_OUT", "/work/out"))
PID = os.getpid()


def _atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n")
    temporary.replace(path)


def _snapshot(name: str) -> None:
    value = torch.cuda.memory._snapshot()
    temporary = OUT / f".{name}.{PID}.pickle.part"
    with temporary.open("wb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(OUT / f"{name}.{PID}.pickle")


def _watch() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    active = False
    dumped = False
    stats_path = OUT / f"allocator-stats.{PID}.jsonl"
    while not dumped:
        if not active and (OUT / "START_HISTORY").exists():
            if torch.cuda.is_initialized():
                torch.cuda.memory._record_memory_history(
                    enabled="all",
                    context="all",
                    stacks="python",
                    max_entries=200000,
                    clear_history=True,
                )
                _snapshot("allocator-start")
                active = True
                _atomic(
                    OUT / f"HISTORY_STARTED.{PID}.json",
                    {"pid": PID, "wall_time": time.time()},
                )
        if active:
            row = {
                "pid": PID,
                "wall_time": time.time(),
                "allocated_bytes": torch.cuda.memory_allocated(),
                "reserved_bytes": torch.cuda.memory_reserved(),
                "max_allocated_bytes": torch.cuda.max_memory_allocated(),
                "max_reserved_bytes": torch.cuda.max_memory_reserved(),
            }
            with stats_path.open("a") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            if (OUT / "DUMP_HISTORY").exists():
                torch.cuda.synchronize()
                _snapshot("allocator-end")
                torch.cuda.memory._record_memory_history(enabled=None)
                _atomic(
                    OUT / f"HISTORY_DUMPED.{PID}.json",
                    {"pid": PID, "wall_time": time.time()},
                )
                dumped = True
        time.sleep(0.25)


threading.Thread(target=_watch, name="torch-staircase-observer", daemon=True).start()
