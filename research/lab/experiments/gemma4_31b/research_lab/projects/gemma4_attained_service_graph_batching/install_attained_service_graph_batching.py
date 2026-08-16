#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil


ROOT = pathlib.Path(__file__).resolve().parent
CANDIDATE = ROOT / "attained_service_graph_batching.py"
EXPECTED = {
    "sglang/srt/managers/schedule_policy.py": (
        "9b96b54f6724c23d5853b585457e41a8f62b5e74aeb0a232943cbb4b289f6212"
    ),
    "sglang/srt/model_executor/cuda_graph_runner.py": (
        "7d1898247e80ff6a446eb42e4968d2eea0df30b109ee2d089a9ad78791bc079e"
    ),
    "sglang/srt/server_args.py": (
        "cc4f440c0987d7a6ee6868f3e41271809c5c1d3015ddcfbd6f79dc19367d5c8d"
    ),
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_schedule_policy(path: pathlib.Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "from sglang.srt.managers.schedule_batch import Req, ScheduleBatch\n",
        "from sglang.srt.managers.attained_service_graph_batching import (\n"
        "    attained_service_sort_key,\n"
        ")\n"
        "from sglang.srt.managers.schedule_batch import Req, ScheduleBatch\n",
        "schedule-policy import",
    )
    text = replace_once(
        text,
        '    ROUTING_KEY = "routing-key"  # prioritize by routing key frequency in running batch\n',
        '    ROUTING_KEY = "routing-key"  # prioritize by routing key frequency in running batch\n'
        '    ATTAINED_SERVICE = "attained-service"\n',
        "schedule-policy enum",
    )
    text = replace_once(
        text,
        "            elif policy == CacheAgnosticPolicy.ROUTING_KEY:\n"
        "                if running_batch is not None:\n"
        "                    SchedulePolicy._sort_by_routing_key(waiting_queue, running_batch)\n"
        "            else:\n",
        "            elif policy == CacheAgnosticPolicy.ROUTING_KEY:\n"
        "                if running_batch is not None:\n"
        "                    SchedulePolicy._sort_by_routing_key(waiting_queue, running_batch)\n"
        "            elif policy == CacheAgnosticPolicy.ATTAINED_SERVICE:\n"
        "                waiting_queue.sort(key=attained_service_sort_key)\n"
        "            else:\n",
        "schedule-policy dispatch",
    )
    path.write_text(text)


def patch_server_args(path: pathlib.Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        '                "routing-key",\n',
        '                "routing-key",\n                "attained-service",\n',
        "server-args CLI choice",
    )
    path.write_text(text)


def patch_cuda_graph(path: pathlib.Path) -> None:
    text = path.read_text()
    text = replace_once(
        text,
        "from sglang.srt.model_executor.forward_batch_info import (\n",
        "from sglang.srt.managers.attained_service_graph_batching import (\n"
        "    observe_graph_shape,\n"
        ")\n"
        "from sglang.srt.model_executor.forward_batch_info import (\n",
        "cuda-graph observer import",
    )
    text = replace_once(
        text,
        "        bs = self.capture_bs[index]\n\n        self.buffer_registry.fill_from(\n",
        "        bs = self.capture_bs[index]\n"
        "        observe_graph_shape(raw_bs=raw_bs, padded_bs=bs)\n\n"
        "        self.buffer_registry.fill_from(\n",
        "cuda-graph first shape consumer",
    )
    path.write_text(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-python", type=pathlib.Path, required=True)
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args()
    root = args.sglang_python

    for relative, expected in EXPECTED.items():
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"missing pinned source: {path}")
        observed = sha256(path)
        if not args.skip_hash_check and observed != expected:
            raise RuntimeError(
                f"{relative} binding mismatch: {observed} != {expected}"
            )

    installed = root / "sglang/srt/managers/attained_service_graph_batching.py"
    shutil.copyfile(CANDIDATE, installed)
    patch_schedule_policy(root / "sglang/srt/managers/schedule_policy.py")
    patch_server_args(root / "sglang/srt/server_args.py")
    patch_cuda_graph(root / "sglang/srt/model_executor/cuda_graph_runner.py")

    print(
        {
            "candidate": sha256(installed),
            "schedule_policy": sha256(
                root / "sglang/srt/managers/schedule_policy.py"
            ),
            "server_args": sha256(root / "sglang/srt/server_args.py"),
            "cuda_graph_runner": sha256(
                root / "sglang/srt/model_executor/cuda_graph_runner.py"
            ),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
