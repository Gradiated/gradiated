#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
import pathlib
import shutil


MODULES = {
    "sampler": "sglang.srt.layers.sampler",
    "model_runner": "sglang.srt.model_executor.model_runner",
    "scheduler": "sglang.srt.managers.scheduler",
    "schedule_batch": "sglang.srt.managers.schedule_batch",
    "batch_result_processor": "sglang.srt.managers.scheduler_components.batch_result_processor",
    "generation_result": "sglang.srt.managers.utils",
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    root = pathlib.Path(os.environ.get("LIVE_SOURCE_ROOT", "/work/live_sources"))
    root.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, object]] = {}
    for label, module_name in MODULES.items():
        module = importlib.import_module(module_name)
        source = pathlib.Path(inspect.getsourcefile(module) or module.__file__).resolve()
        destination = root / f"{label}-{source.name}"
        shutil.copyfile(source, destination)
        os.chmod(destination, 0o444)
        rows[label] = {
            "module": module_name,
            "runtime_path": str(source),
            "snapshot": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        }
    result_processor = inspect.getsource(
        importlib.import_module(
            MODULES["batch_result_processor"]
        ).SchedulerBatchResultProcessor
    )
    schedule_batch = inspect.getsource(
        importlib.import_module(MODULES["schedule_batch"]).ScheduleBatch
    )
    generation_result = inspect.getsource(
        importlib.import_module(MODULES["generation_result"]).GenerationBatchResult
    )
    scheduler = inspect.getsource(
        importlib.import_module(MODULES["scheduler"]).Scheduler
    )
    checks = {
        "result_tolist_present": "next_token_ids = next_token_ids.tolist()" in result_processor,
        "device_relay_present": "self.future_map.stash(future_indices, stash_payload)" in scheduler,
        "async_cpu_copy_present": 'self.next_token_ids.to("cpu", non_blocking=True)' in generation_result,
        "copy_event_present": "self.copy_done.record()" in generation_result,
        "decode_preparation_present": "def prepare_for_decode(self):" in schedule_batch,
    }
    atomic_json(
        root / "LIVE_SOURCE_BINDING.json",
        {
            "schema_version": 1,
            "files": rows,
            "checks": checks,
            "pass": all(checks.values()),
        },
    )
    return 0 if all(checks.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
