"""Offline, fail-closed observer dependency attribution contract."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

FORBIDDEN = {"credential", "address", "command", "path", "stdout", "stderr"}
REQUIRED = {
    "request", "scheduler_iteration", "clock_calibration", "stream", "graph_launch",
    "graph_node", "kernel", "dependency",
}
CONTRACT_VERSION = "observer-dependency-attribution-v1"
INPUT_ARTIFACT_REFS = (
    "18b738029e74f8169c57e6aa07ba2206553fb10a8b891c06ef4f119e94a36b3f",
    "b671c91a027b26c46b6cc86aa0e580a1a5a7426c6a3367d244d20bbb0ec9bc9d",
    "78eb2fb15013ceb0c1b07fcc14cdd2628998e0e585e342162a3630b61bd44862",
    "7472f76da4bcc3eb77cd659cc7008d214ad7727581407c8c3805b2fce7b214a0",
    "2902b0a101af27e95577a90a63c4a4d7265c27437524f18c0ea2769a12baad8e",
    "c86034940baff28908d80bf5ebf01511a47dacdfffad781a25703281147cd7b9",
)


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Attribution:
    coverage: float
    covered_ns: int
    scoped_ns: int
    linked_kernel_ids: tuple[str, ...]


def binding() -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_VERSION,
        "required_event_kinds": sorted(REQUIRED),
        "attribution": "union_of_non_overlapping_dependency_linked_intervals",
        "forbid_sum_or_timestamp_containment": True,
        "input_artifact_refs": list(INPUT_ARTIFACT_REFS),
        "fail_closed": True,
    }


def package_partial_evidence(
    request_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    manifest: dict[str, str],
) -> dict[str, Any]:
    """Validate and describe the exact raw rows retained by a partial archive."""
    if not request_rows or not event_rows:
        raise ContractError("partial evidence must retain raw request and event rows")
    if (
        not isinstance(manifest, dict)
        or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("raw_requests", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("raw_events", "")))
    ):
        raise ContractError("partial evidence manifest must hash raw request and event rows")
    return {
        "contract_id": CONTRACT_VERSION,
        "raw_request_rows": request_rows,
        "raw_event_rows": event_rows,
        "manifest": dict(manifest),
        "hash_manifest": True,
    }


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"{name} must be a non-empty string")
    return value


def _interval(event: dict[str, Any]) -> tuple[int, int]:
    start, end = event.get("start_ns"), event.get("end_ns")
    if not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ContractError(f"{event.get('event_id', 'event')}: invalid interval")
    return start, end


def _walk_forbidden(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if any(token in key.lower() for token in FORBIDDEN):
                raise ContractError(f"forbidden scored field: {path}.{key}")
            _walk_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{path}[{index}]")


def validate(events: list[dict[str, Any]]) -> Attribution:
    if not isinstance(events, list) or not events:
        raise ContractError("events must be non-empty")
    ids: set[str] = set()
    by_type: dict[str, list[dict[str, Any]]] = {}
    clocks: dict[str, list[int]] = {}
    for event in events:
        if not isinstance(event, dict):
            raise ContractError("event must be an object")
        _walk_forbidden(event)
        event_id = _text(event.get("event_id"), "event_id")
        if event_id in ids:
            raise ContractError(f"duplicate event_id: {event_id}")
        ids.add(event_id)
        kind = _text(event.get("kind"), f"{event_id}.kind")
        by_type.setdefault(kind, []).append(event)
        domain = _text(event.get("clock_domain"), f"{event_id}.clock_domain")
        start, end = _interval(event)
        if end <= start:
            raise ContractError("non-positive interval")
        clocks.setdefault(domain, []).append(start)
        if event.get("schema_version") != 1:
            raise ContractError("unsupported schema_version")
    if set(by_type) != REQUIRED:
        raise ContractError(f"required event kinds missing: {sorted(REQUIRED - set(by_type))}")
    for domain, values in clocks.items():
        if values != sorted(values):
            raise ContractError(f"timestamps are not monotonic in {domain}")

    calibrations = by_type["clock_calibration"]
    if (
        len(calibrations) != 1
        or calibrations[0].get("cpu_domain") != "cpu_monotonic_ns"
        or calibrations[0].get("cuda_domain") != "cuda_global_ns"
        or not isinstance(calibrations[0].get("offset_ns"), int)
        or not isinstance(calibrations[0].get("scale_num"), int)
        or not isinstance(calibrations[0].get("scale_den"), int)
        or calibrations[0].get("scale_den") <= 0
    ):
        raise ContractError("exactly one explicit CPU/CUDA clock calibration is required")
    requests = { _text(e.get("request_id"), "request_id") for e in by_type["request"] }
    iterations = { _text(e.get("scheduler_iteration_id"), "scheduler_iteration_id") for e in by_type["scheduler_iteration"] }
    scopes = {(e.get("request_id"), e.get("scheduler_iteration_id")): _interval(e) for e in by_type["scheduler_iteration"]}
    if any(request not in requests or iteration not in iterations for request, iteration in scopes):
        raise ContractError("scheduler scope references unknown identity")
    streams = {_text(e.get("cuda_stream_id"), "cuda_stream_id") for e in by_type["stream"]}
    launches = {_text(e.get("graph_launch_id"), "graph_launch_id") for e in by_type["graph_launch"]}
    nodes = {_text(e.get("graph_node_id"), "graph_node_id") for e in by_type["graph_node"]}
    kernels = {}
    kernel_events: dict[str, dict[str, Any]] = {}
    for event in by_type["kernel"]:
        kernel_id = _text(event.get("kernel_id"), "kernel_id")
        if kernel_id in kernels:
            raise ContractError("duplicate kernel_id")
        if event.get("cuda_stream_id") not in streams or event.get("graph_launch_id") not in launches or event.get("graph_node_id") not in nodes:
            raise ContractError("kernel lacks stream/graph linkage")
        graph_node = next(node for node in by_type["graph_node"] if node.get("graph_node_id") == event.get("graph_node_id"))
        if graph_node.get("graph_launch_id") != event.get("graph_launch_id"):
            raise ContractError("kernel graph launch/node linkage is cross-wired")
        scope = (event.get("request_id"), event.get("scheduler_iteration_id"))
        if scope not in scopes:
            raise ContractError("kernel has no exact request/iteration scope")
        kernels[kernel_id] = event
        kernel_events[event["event_id"]] = event
    linked: set[str] = set()
    for edge in by_type["dependency"]:
        source, target = _text(edge.get("source_event_id"), "source_event_id"), _text(edge.get("target_event_id"), "target_event_id")
        if source not in ids or target not in ids:
            raise ContractError("dependency edge has dangling reference")
        source_event = next(e for e in events if e["event_id"] == source)
        target_event = next(e for e in events if e["event_id"] == target)
        scope = (edge.get("request_id"), edge.get("scheduler_iteration_id"))
        if scope not in scopes or (source_event.get("request_id"), source_event.get("scheduler_iteration_id")) != scope or (target_event.get("request_id"), target_event.get("scheduler_iteration_id")) != scope:
            raise ContractError("dependency crosses exact request/iteration scope")
        if target in kernel_events:
            linked.add(target)
    scoped_ns = sum(end - start for start, end in scopes.values())
    intervals = sorted((_interval(kernel_events[k])[0], _interval(kernel_events[k])[1]) for k in linked)
    union = 0
    last_end = None
    for start, end in intervals:
        if last_end is None or start > last_end:
            union += end - start
        elif end > last_end:
            union += end - last_end
        last_end = max(last_end or end, end)
    return Attribution(min(union / scoped_ns, 1.0) if scoped_ns else 0.0, union, scoped_ns, tuple(sorted(linked)))


def fixture() -> list[dict[str, Any]]:
    def e(event_id: str, kind: str, start: int, end: int, **fields: Any) -> dict[str, Any]:
        return {"schema_version": 1, "event_id": event_id, "kind": kind, "clock_domain": fields.pop("clock_domain", "cuda_global_ns"), "start_ns": start, "end_ns": end, **fields}
    common = {"request_id": "req-47022401", "scheduler_iteration_id": "iter-01"}
    return [
        e("req", "request", 0, 1000, clock_domain="cpu_monotonic_ns", **common),
        e("iter", "scheduler_iteration", 100, 1000, clock_domain="cpu_monotonic_ns", **common),
        e("cal", "clock_calibration", 0, 1, clock_domain="calibration_ns", cpu_domain="cpu_monotonic_ns", cuda_domain="cuda_global_ns", offset_ns=100, scale_num=1, scale_den=1),
        e("stream", "stream", 100, 200, cuda_stream_id="stream-7", **common),
        e("launch", "graph_launch", 100, 200, graph_launch_id="launch-1", **common),
        e("node", "graph_node", 100, 200, graph_launch_id="launch-1", graph_node_id="node-1", **common),
        e("k1", "kernel", 100, 700, kernel_id="kernel-1", cuda_stream_id="stream-7", graph_launch_id="launch-1", graph_node_id="node-1", **common),
        e("dep", "dependency", 100, 101, source_event_id="iter", target_event_id="k1", **common),
        e("k2", "kernel", 650, 1000, kernel_id="kernel-2", cuda_stream_id="stream-7", graph_launch_id="launch-1", graph_node_id="node-1", **common),
        e("dep2", "dependency", 650, 651, source_event_id="k1", target_event_id="k2", **common),
    ]


def canonical(events: list[dict[str, Any]]) -> bytes:
    return b"".join(json.dumps(event, sort_keys=True, separators=(",", ":")).encode() + b"\n" for event in events)
