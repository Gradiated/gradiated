#!/usr/bin/env python3
"""Exact-source-bound vLLM correlation instrumentation for observer runs."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


SCHEDULER_SHA256 = "96f7360982899fffdbd627f51e3daf8afbe7a79fad5dc17d6dc0eb093aa516a0"
RUNNER_SHA256 = "e8a73e1ccbfff37b880cd47ba9c115db572aef3c9d4d9eee50b18b729117f9bb"
MARKER = "GRAD_RESEARCH_OBSERVER_V1"


class ObserverPatchError(RuntimeError):
    pass


def verify_source_hash(data: bytes, expected: str, name: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ObserverPatchError(f"{name} source hash mismatch: {actual}")


def replace_once(source: str, old: str, new: str, name: str) -> str:
    if source.count(old) != 1:
        raise ObserverPatchError(f"{name} patch anchor count is {source.count(old)}, expected 1")
    return source.replace(old, new, 1)


def patch_scheduler_text(source: str) -> str:
    if MARKER in source:
        return source
    source = replace_once(
        source,
        "import itertools\nimport time\n",
        "import hashlib\nimport itertools\nimport json\nimport os\nimport time\n",
        "scheduler imports",
    )
    helper = '''\n\ndef _grad_research_iteration_signature(num_scheduled_tokens: dict[str, int]) -> str:\n    encoded = json.dumps(sorted(num_scheduled_tokens.items()), separators=(\",\", \":\")).encode()\n    return hashlib.sha256(encoded).hexdigest()[:16]\n\n\ndef _grad_research_schedule_record(scheduler: Any, scheduler_output: SchedulerOutput) -> None:\n    path = os.environ.get(\"GRAD_RESEARCH_SCHEDULER_EVENTS\")\n    if not path:\n        return\n    requests = []\n    for request_id, scheduled_tokens in sorted(scheduler_output.num_scheduled_tokens.items()):\n        request = scheduler.requests.get(request_id)\n        requests.append({\n            \"request_id\": request_id,\n            \"scheduled_tokens\": scheduled_tokens,\n            \"phase\": (\n                \"decode\"\n                if request is not None and request.num_computed_tokens >= request.num_prompt_tokens\n                else \"prefill\"\n            ),\n            \"num_computed_tokens\": request.num_computed_tokens if request is not None else None,\n            \"num_prompt_tokens\": request.num_prompt_tokens if request is not None else None,\n        })\n    record = {\n        \"schema_version\": 1,\n        \"signal\": \"scheduler_iteration_trace\",\n        \"marker\": \"GRAD_RESEARCH_OBSERVER_V1\",\n        \"monotonic_ns\": time.monotonic_ns(),\n        \"wall_clock_ns\": time.time_ns(),\n        \"iteration_id\": _grad_research_iteration_signature(scheduler_output.num_scheduled_tokens),\n        \"scheduled_tokens\": scheduler_output.total_num_scheduled_tokens,\n        \"batch_composition\": requests,\n        \"running_requests\": len(scheduler.running),\n        \"waiting_requests\": len(scheduler.waiting),\n        \"kv_state\": {\"preempted_request_ids\": sorted(scheduler_output.preempted_req_ids)},\n    }\n    encoded = json.dumps(record, sort_keys=True, separators=(\",\", \":\")) + \"\\n\"\n    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)\n    try:\n        os.write(descriptor, encoded.encode())\n    finally:\n        os.close(descriptor)\n'''
    helper = helper.replace(
        '\\"iteration_id\\": _grad_research_iteration_signature(scheduler_output.num_scheduled_tokens)',
        '\\"scheduler_iteration_id\\": scheduler_output.scheduler_iteration_id',
    )
    source = replace_once(
        source,
        "logger = init_logger(__name__)\n",
        "logger = init_logger(__name__)\n" + helper,
        "scheduler helper",
    )
    source = replace_once(
        source,
        "        return scheduler_output\n\n    def _preempt_request",
        "        self._grad_research_iteration_counter = getattr(self, \"_grad_research_iteration_counter\", 0) + 1\n        scheduler_output.scheduler_iteration_id = f\"scheduler-iteration-{self._grad_research_iteration_counter:020d}\"\n        _grad_research_schedule_record(self, scheduler_output)\n        return scheduler_output\n\n    def _preempt_request",
        "scheduler record",
    )
    return source


def patch_runner_text(source: str) -> str:
    if MARKER in source:
        return source
    source = replace_once(
        source,
        "import functools\nimport gc\nimport itertools\n",
        "import functools\nimport gc\nimport hashlib\nimport itertools\nimport json\n",
        "runner imports",
    )
    helper = '''\n\ndef _grad_research_iteration_range(num_scheduled_tokens: dict[str, int]) -> str:\n    encoded = json.dumps(sorted(num_scheduled_tokens.items()), separators=(\",\", \":\")).encode()\n    signature = hashlib.sha256(encoded).hexdigest()[:16]\n    return f\"GRAD_RESEARCH_OBSERVER_V1:iteration:{signature}\"\n'''
    helper = '''\n\ndef _grad_research_iteration_range(scheduler_output: Any) -> str:\n    iteration_id = getattr(scheduler_output, \"scheduler_iteration_id\", None)\n    if not isinstance(iteration_id, str) or not iteration_id:\n        raise RuntimeError(\"scheduler iteration identity is missing\")\n    return f\"GRAD_RESEARCH_OBSERVER_V1:iteration:{iteration_id}\"\n'''
    source = replace_once(
        source,
        "class GPUModelRunner(\n",
        helper + "\n\nclass GPUModelRunner(\n",
        "runner helper",
    )
    source = replace_once(
        source,
        '            record_function_or_nullcontext("gpu_model_runner: forward"),\n            self.maybe_get_kv_connector_output(scheduler_output) as kv_connector_output,\n',
        '            record_function_or_nullcontext("gpu_model_runner: forward"),\n            torch.cuda.nvtx.range(_grad_research_iteration_range(scheduler_output)),  # scheduler_output.num_scheduled_tokens is not identity\n            self.maybe_get_kv_connector_output(scheduler_output) as kv_connector_output,\n',
        "runner NVTX range",
    )
    return source


def apply_patch(scheduler_path: Path, runner_path: Path) -> None:
    scheduler_bytes = scheduler_path.read_bytes()
    runner_bytes = runner_path.read_bytes()
    scheduler_text = scheduler_bytes.decode()
    runner_text = runner_bytes.decode()
    if MARKER in scheduler_text or MARKER in runner_text:
        if MARKER not in scheduler_text or MARKER not in runner_text:
            raise ObserverPatchError("partial observer patch detected")
        return
    verify_source_hash(scheduler_bytes, SCHEDULER_SHA256, "scheduler")
    verify_source_hash(runner_bytes, RUNNER_SHA256, "GPU model runner")
    scheduler_path.write_text(patch_scheduler_text(scheduler_text))
    runner_path.write_text(patch_runner_text(runner_text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler", type=Path, required=True)
    parser.add_argument("--gpu-model-runner", type=Path, required=True)
    args = parser.parse_args()
    apply_patch(args.scheduler, args.gpu_model_runner)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
