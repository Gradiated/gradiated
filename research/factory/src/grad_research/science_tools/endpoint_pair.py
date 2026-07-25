from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import hashlib
import json
import os
import shlex
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

from ..util import canonical_json_bytes, utc_now
from .common import (
    ScienceToolError,
    artifact_identity,
    load_json,
    read_jsonl,
    run_command,
    write_json_atomic,
    write_jsonl_atomic,
)


SCHEMA_VERSION = 1
ARMS = ("control", "candidate")
PUBLIC_RESPONSE_HEADERS = {
    "content-type",
    "openai-processing-ms",
    "server-timing",
    "x-request-id",
}


@dataclass(frozen=True)
class WorkloadRequest:
    index: int
    request_id: str
    payload: dict[str, Any]
    body: bytes
    scheduled_offset_seconds: float


def _write_bytes_atomic(path: Path, value: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _request_directory(root: Path, request: WorkloadRequest) -> Path:
    identifier_hash = hashlib.sha256(request.request_id.encode("utf-8")).hexdigest()[:16]
    return root / f"{request.index:06d}-{identifier_hash}"


def _load_workload(
    path: str | Path,
    seed: int | None,
    request_interval_seconds: float,
) -> list[WorkloadRequest]:
    rows = read_jsonl(path)
    requests: list[WorkloadRequest] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        request_id = row.get("request_id")
        payload = row.get("payload")
        if not isinstance(request_id, str) or not request_id:
            raise ScienceToolError(
                f"workload row {index + 1} requires a nonempty string request_id"
            )
        if request_id in seen:
            raise ScienceToolError(f"duplicate workload request_id: {request_id}")
        if not isinstance(payload, dict):
            raise ScienceToolError(
                f"workload row {index + 1} requires an object payload"
            )
        raw_offset = row.get(
            "scheduled_offset_seconds", index * request_interval_seconds
        )
        if (
            isinstance(raw_offset, bool)
            or not isinstance(raw_offset, (int, float))
            or raw_offset < 0
        ):
            raise ScienceToolError(
                f"workload row {index + 1} scheduled_offset_seconds must be non-negative"
            )
        seen.add(request_id)
        effective_payload = copy.deepcopy(payload)
        if seed is not None:
            effective_payload["seed"] = seed
        body = canonical_json_bytes(effective_payload)
        requests.append(
            WorkloadRequest(
                index=index,
                request_id=request_id,
                payload=effective_payload,
                body=body,
                scheduled_offset_seconds=float(raw_offset),
            )
        )
    if not requests:
        raise ScienceToolError("workload must contain at least one request")
    return requests


def _header_digest(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        name.lower(): hashlib.sha256(value.encode("utf-8")).hexdigest()
        for name, value in sorted(headers.items(), key=lambda item: item[0].lower())
    }


def _safe_endpoint_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ScienceToolError(f"endpoint must be an HTTP(S) URL: {value!r}")
    host = parsed.hostname
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _contract(
    *,
    workload_path: Path,
    requests: Sequence[WorkloadRequest],
    endpoints: Mapping[str, str],
    headers: Mapping[str, Mapping[str, str]],
    arm_order: Sequence[str],
    seed: int | None,
    timeout_seconds: float,
    concurrency: int,
    request_interval_seconds: float,
    parallel_arms: bool,
    compare_latency: bool,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "workload": artifact_identity(workload_path),
        "requests": [
            {
                "index": request.index,
                "request_id": request.request_id,
                "request_body_sha256": _sha256(request.body),
                "scheduled_offset_seconds": request.scheduled_offset_seconds,
            }
            for request in requests
        ],
        "endpoints": {arm: _safe_endpoint_url(url) for arm, url in endpoints.items()},
        "endpoint_url_sha256": {
            arm: _sha256(url.encode("utf-8")) for arm, url in endpoints.items()
        },
        "request_header_names": {
            arm: sorted(name.lower() for name in headers[arm]) for arm in ARMS
        },
        "request_header_value_sha256": {
            arm: _header_digest(headers[arm]) for arm in ARMS
        },
        "arm_order": list(arm_order),
        "seed": seed,
        "timeout_seconds": timeout_seconds,
        "concurrency": concurrency,
        "request_interval_seconds": request_interval_seconds,
        "parallel_arms": parallel_arms,
        "compare_latency": compare_latency,
    }


def _read_response_bytes(response: BinaryIO) -> tuple[bytes, str | None, bool]:
    chunks: list[bytes] = []
    first_byte_at: str | None = None
    try:
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                return b"".join(chunks), first_byte_at, True
            if first_byte_at is None:
                first_byte_at = utc_now()
            chunks.append(chunk)
    except (OSError, socket.timeout) as error:
        return b"".join(chunks), first_byte_at, False


def _parse_sse_event(raw: bytes, index: int, received_at: str) -> dict[str, Any]:
    event: dict[str, Any] = {
        "index": index,
        "received_at": received_at,
        "raw_base64": base64.b64encode(raw).decode("ascii"),
    }
    data_lines: list[bytes] = []
    for line in raw.splitlines():
        if not line or line.startswith(b":"):
            continue
        field, separator, value = line.partition(b":")
        if separator and value.startswith(b" "):
            value = value[1:]
        name = field.decode("utf-8", errors="replace")
        text = value.decode("utf-8", errors="replace")
        if name == "data":
            data_lines.append(value)
        elif name in {"event", "id", "retry"}:
            event[name] = text
    if data_lines:
        data = b"\n".join(data_lines)
        event["data"] = data.decode("utf-8", errors="replace")
        if data.strip() != b"[DONE]":
            try:
                event["json"] = json.loads(data)
            except (UnicodeDecodeError, json.JSONDecodeError):
                event["json_error"] = "invalid_json"
    return event


def _read_sse(
    response: BinaryIO,
) -> tuple[bytes, list[dict[str, Any]], str | None, bool]:
    raw_parts: list[bytes] = []
    event_parts: list[bytes] = []
    events: list[dict[str, Any]] = []
    first_byte_at: str | None = None
    transport_complete = False
    try:
        while True:
            line = response.readline()
            if not line:
                if event_parts:
                    raw = b"".join(event_parts)
                    events.append(_parse_sse_event(raw, len(events), utc_now()))
                transport_complete = True
                break
            if first_byte_at is None:
                first_byte_at = utc_now()
            raw_parts.append(line)
            event_parts.append(line)
            if line in {b"\n", b"\r\n"}:
                raw = b"".join(event_parts)
                events.append(_parse_sse_event(raw, len(events), utc_now()))
                event_parts = []
    except (OSError, socket.timeout):
        if event_parts:
            raw = b"".join(event_parts)
            events.append(_parse_sse_event(raw, len(events), utc_now()))
    return b"".join(raw_parts), events, first_byte_at, transport_complete


def _walk_json(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk_json(child)


def _token_ids(values: Sequence[Any]) -> list[int] | None:
    found: list[int] = []
    present = False
    accepted_names = {
        "token_ids",
        "output_token_ids",
        "generated_token_ids",
        "completion_token_ids",
    }
    for value in values:
        for key, child in _walk_json(value):
            if key not in accepted_names or not isinstance(child, list):
                continue
            if all(isinstance(token, int) and not isinstance(token, bool) for token in child):
                present = True
                found.extend(child)
    return found if present else None


def _finish_reason(values: Sequence[Any]) -> str | None:
    result: str | None = None
    for value in values:
        for key, child in _walk_json(value):
            if key == "finish_reason" and isinstance(child, str):
                result = child
        if isinstance(value, dict):
            event_type = value.get("type")
            if event_type in {
                "response.completed",
                "response.failed",
                "response.incomplete",
            }:
                result = str(event_type).removeprefix("response.")
    return result


def _usage(values: Sequence[Any]) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    for value in values:
        for key, child in _walk_json(value):
            if key == "usage" and isinstance(child, dict):
                result = child
    return result


def _content_text(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "".join(parts)
    return None


def _output_piece(value: Any, *, streaming: bool) -> str | None:
    if not isinstance(value, dict):
        return None
    event_type = value.get("type")
    if event_type == "response.output_text.delta" and isinstance(
        value.get("delta"), str
    ):
        return value["delta"]
    choices = value.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        choice = choices[0]
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = _content_text(delta.get("content"))
            if content is not None:
                return content
        if isinstance(choice.get("text"), str):
            return choice["text"]
        if not streaming:
            message = choice.get("message")
            if isinstance(message, dict):
                content = _content_text(message.get("content"))
                if content is not None:
                    return content
    if not streaming:
        if isinstance(value.get("output_text"), str):
            return value["output_text"]
        output = value.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = _content_text(item.get("content"))
                if content is not None:
                    parts.append(content)
            if parts:
                return "".join(parts)
    return None


def _parsed_evidence(
    parsed_values: Sequence[Any],
    *,
    streaming: bool,
) -> dict[str, Any]:
    pieces = [
        piece
        for value in parsed_values
        if (piece := _output_piece(value, streaming=streaming)) is not None
    ]
    return {
        "output_text": "".join(pieces) if pieces else None,
        "token_ids": _token_ids(parsed_values),
        "finish_reason": _finish_reason(parsed_values),
        "usage": _usage(parsed_values),
    }


def _sse_protocol_complete(events: Sequence[Mapping[str, Any]]) -> bool:
    for event in events:
        if event.get("data") == "[DONE]":
            return True
        value = event.get("json")
        if isinstance(value, dict) and value.get("type") in {
            "response.completed",
            "response.failed",
            "response.incomplete",
        }:
            return True
        if isinstance(value, dict) and _finish_reason([value]) is not None:
            return True
    return False


def _response_headers(
    response: Any,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    headers: dict[str, list[str]] = {}
    digests: dict[str, list[str]] = {}
    for name, value in response.headers.items():
        normalized = name.lower()
        digests.setdefault(normalized, []).append(_sha256(value.encode("utf-8")))
        if normalized in PUBLIC_RESPONSE_HEADERS:
            headers.setdefault(normalized, []).append(value)
    return headers, digests


def _perform_request(
    *,
    arm: str,
    endpoint_url: str,
    request: WorkloadRequest,
    headers: Mapping[str, str],
    timeout_seconds: float,
    artifact_dir: Path,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_path = _write_bytes_atomic(artifact_dir / "request.body", request.body)
    metadata_path = artifact_dir / "metadata.json"
    started_at = utc_now()
    started_clock = time.monotonic()
    initial = {
        "schema_version": SCHEMA_VERSION,
        "arm": arm,
        "request_index": request.index,
        "request_id": request.request_id,
        "endpoint_url": _safe_endpoint_url(endpoint_url),
        "endpoint_url_sha256": _sha256(endpoint_url.encode("utf-8")),
        "started_at": started_at,
        "complete": False,
        "request": artifact_identity(request_path),
    }
    write_json_atomic(metadata_path, initial)

    request_headers = {"Content-Type": "application/json"}
    request_headers["Accept"] = (
        "text/event-stream"
        if request.payload.get("stream") is True
        else "application/json"
    )
    request_headers.update(headers)
    http_request = urllib.request.Request(
        endpoint_url,
        data=request.body,
        headers=request_headers,
        method="POST",
    )

    response: Any | None = None
    status: int | None = None
    response_headers: dict[str, list[str]] = {}
    response_header_digests: dict[str, list[str]] = {}
    raw_response = b""
    events: list[dict[str, Any]] = []
    first_byte_at: str | None = None
    transport_complete = False
    error: dict[str, Any] | None = None
    streaming_response = False
    parsed_values: list[Any] = []
    try:
        try:
            response = urllib.request.urlopen(http_request, timeout=timeout_seconds)
        except urllib.error.HTTPError as http_error:
            response = http_error
            error = {
                "kind": "http",
                "message": str(http_error.reason),
                "status": http_error.code,
            }
        status = int(response.status)
        response_headers, response_header_digests = _response_headers(response)
        content_type = response.headers.get_content_type()
        streaming_response = content_type == "text/event-stream"
        if streaming_response:
            (
                raw_response,
                events,
                first_byte_at,
                transport_complete,
            ) = _read_sse(response)
            parsed_values = [
                event["json"] for event in events if "json" in event
            ]
        else:
            raw_response, first_byte_at, transport_complete = _read_response_bytes(
                response
            )
            if raw_response:
                try:
                    parsed_values = [json.loads(raw_response)]
                except (UnicodeDecodeError, json.JSONDecodeError) as parse_error:
                    if error is None:
                        error = {
                            "kind": "invalid_json",
                            "message": str(parse_error),
                        }
        if not transport_complete and error is None:
            error = {
                "kind": "transport",
                "message": "response ended before the transport completed",
            }
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as request_error:
        error = {
            "kind": "transport",
            "message": str(request_error),
        }
    finally:
        if response is not None:
            response.close()

    response_path = _write_bytes_atomic(artifact_dir / "response.body", raw_response)
    events_path = write_jsonl_atomic(artifact_dir / "events.jsonl", events)
    protocol_complete = (
        _sse_protocol_complete(events) if streaming_response else transport_complete
    )
    complete = transport_complete and protocol_complete
    evidence = _parsed_evidence(parsed_values, streaming=streaming_response)
    metadata = {
        **initial,
        "completed_at": utc_now(),
        "first_byte_at": first_byte_at,
        "latency_seconds": time.monotonic() - started_clock,
        "status": status,
        "response_headers": response_headers,
        "response_header_value_sha256": response_header_digests,
        "stream_requested": request.payload.get("stream") is True,
        "streaming_response": streaming_response,
        "transport_complete": transport_complete,
        "protocol_complete": protocol_complete,
        "complete": complete,
        "successful": bool(
            complete and status is not None and 200 <= status < 300 and error is None
        ),
        "response": artifact_identity(response_path),
        "events": artifact_identity(events_path),
        "event_count": len(events),
        "finish_reason": evidence["finish_reason"],
        "token_ids": evidence["token_ids"],
        "usage": evidence["usage"],
        "output_text": evidence["output_text"],
        "error": error,
    }
    write_json_atomic(metadata_path, metadata)
    return metadata


def _parse_arm_order(value: str | Sequence[str]) -> tuple[str, str]:
    parts = (
        [part.strip() for part in value.split(",")]
        if isinstance(value, str)
        else [str(part).strip() for part in value]
    )
    if len(parts) != 2 or set(parts) != set(ARMS):
        raise ScienceToolError(
            "arm order must contain control and candidate exactly once"
        )
    return parts[0], parts[1]


def _request_complete(path: Path, request: WorkloadRequest, arm: str) -> bool:
    metadata_path = path / "metadata.json"
    if not metadata_path.is_file():
        return False
    try:
        metadata = load_json(metadata_path)
    except ScienceToolError:
        return False
    metadata_matches = bool(
        isinstance(metadata, dict)
        and metadata.get("complete") is True
        and metadata.get("request_id") == request.request_id
        and metadata.get("request_index") == request.index
        and metadata.get("arm") == arm
        and isinstance(metadata.get("request"), dict)
        and metadata["request"].get("sha256") == _sha256(request.body)
    )
    if not metadata_matches:
        return False
    for name in ("request", "response", "events"):
        recorded = metadata.get(name)
        if not isinstance(recorded, dict) or not isinstance(recorded.get("path"), str):
            return False
        try:
            current = artifact_identity(recorded["path"])
        except ScienceToolError:
            return False
        if (
            current["sha256"] != recorded.get("sha256")
            or current["size_bytes"] != recorded.get("size_bytes")
        ):
            return False
    return True


def _progress(
    root: Path, requests: Sequence[WorkloadRequest]
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for arm in ARMS:
        complete = 0
        successful = 0
        for request in requests:
            request_path = _request_directory(
                root / "arms" / arm / "requests", request
            )
            if not _request_complete(request_path, request, arm):
                continue
            complete += 1
            try:
                metadata = load_json(request_path / "metadata.json")
            except ScienceToolError:
                continue
            if isinstance(metadata, dict) and _valid_request_metadata(metadata):
                successful += 1
        result[arm] = {
            "complete_requests": complete,
            "successful_requests": successful,
            "total_requests": len(requests),
        }
    return result


def run_endpoint_pair(
    *,
    workload_path: str | Path,
    output_dir: str | Path,
    control_url: str,
    candidate_url: str,
    arm_order: str | Sequence[str] = ARMS,
    seed: int | None = None,
    headers: Mapping[str, str] | None = None,
    control_headers: Mapping[str, str] | None = None,
    candidate_headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 120.0,
    restart_commands: Mapping[str, Sequence[str] | None] | None = None,
    restart_timeout_seconds: float = 900.0,
    concurrency: int = 1,
    request_interval_seconds: float = 0.0,
    parallel_arms: bool = False,
    compare_latency: bool = False,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ScienceToolError("timeout_seconds must be positive")
    if concurrency <= 0:
        raise ScienceToolError("concurrency must be positive")
    if request_interval_seconds < 0:
        raise ScienceToolError("request_interval_seconds must be non-negative")
    if compare_latency and not parallel_arms:
        raise ScienceToolError("compare_latency requires parallel_arms")
    order = _parse_arm_order(arm_order)
    workload = Path(workload_path).resolve()
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    requests = _load_workload(workload, seed, request_interval_seconds)
    endpoints = {"control": control_url, "candidate": candidate_url}
    shared_headers = dict(headers or {})
    effective_headers = {
        "control": {**shared_headers, **dict(control_headers or {})},
        "candidate": {**shared_headers, **dict(candidate_headers or {})},
    }
    contract = _contract(
        workload_path=workload,
        requests=requests,
        endpoints=endpoints,
        headers=effective_headers,
        arm_order=order,
        seed=seed,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
        request_interval_seconds=request_interval_seconds,
        parallel_arms=parallel_arms,
        compare_latency=compare_latency,
    )
    run_path = root / "run.json"
    if run_path.exists():
        existing = load_json(run_path)
        if not isinstance(existing, dict) or existing.get("contract") != contract:
            raise ScienceToolError(
                f"{run_path} belongs to a different endpoint-pair contract"
            )
        created_at = existing.get("created_at", utc_now())
        restarts = list(existing.get("restarts", []))
    else:
        created_at = utc_now()
        restarts = []

    state_lock = threading.RLock()

    def update_run(*, errors: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with state_lock:
            progress = _progress(root, requests)
            artifact_complete = all(
                row["complete_requests"] == row["total_requests"]
                for row in progress.values()
            )
            all_requests_successful = all(
                row["successful_requests"] == row["total_requests"]
                for row in progress.values()
            )
            value = {
                "schema_version": SCHEMA_VERSION,
                "kind": "endpoint_pair_run",
                "created_at": created_at,
                "updated_at": utc_now(),
                "complete": artifact_complete,
                "artifact_complete": artifact_complete,
                "all_requests_successful": all_requests_successful,
                "performance_comparable": bool(
                    artifact_complete
                    and all_requests_successful
                    and contract["parallel_arms"]
                    and contract["compare_latency"]
                ),
                "contract": contract,
                "progress": progress,
                "restarts": list(restarts),
                "errors": list(errors or []),
            }
            write_json_atomic(run_path, value)
            return value

    errors: list[dict[str, Any]] = []
    update_run()
    restart_map = dict(restart_commands or {})

    def run_arm(arm: str) -> None:
        request_root = root / "arms" / arm / "requests"
        pending = [
            request
            for request in requests
            if not _request_complete(
                _request_directory(request_root, request), request, arm
            )
        ]
        if not pending:
            return
        command = restart_map.get(arm)
        if command:
            try:
                restart = run_command(
                    command,
                    output_dir=root / "restarts",
                    name=f"{arm}-restart-{len(restarts):03d}",
                    timeout_seconds=restart_timeout_seconds,
                )
                restart["arm"] = arm
                with state_lock:
                    restarts.append(restart)
                update_run(errors=errors)
                if restart["returncode"] != 0:
                    with state_lock:
                        errors.append(
                            {
                                "arm": arm,
                                "kind": "restart",
                                "message": f"restart command returned {restart['returncode']}",
                            }
                        )
                    update_run(errors=errors)
                    return
            except ScienceToolError as restart_error:
                with state_lock:
                    errors.append(
                        {"arm": arm, "kind": "restart", "message": str(restart_error)}
                    )
                update_run(errors=errors)
                return

        arm_started = time.monotonic()

        def perform(request: WorkloadRequest) -> None:
            delay = arm_started + request.scheduled_offset_seconds - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            artifact_dir = _request_directory(request_root, request)
            _perform_request(
                arm=arm,
                endpoint_url=endpoints[arm],
                request=request,
                headers=effective_headers[arm],
                timeout_seconds=timeout_seconds,
                artifact_dir=artifact_dir,
            )
            update_run(errors=errors)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix=f"endpoint-{arm}",
        ) as executor:
            futures = [executor.submit(perform, request) for request in pending]
            for future in futures:
                future.result()

    if parallel_arms:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="endpoint-arm",
        ) as executor:
            futures = [executor.submit(run_arm, arm) for arm in order]
            for future in futures:
                future.result()
    else:
        for arm in order:
            run_arm(arm)
    return update_run(errors=errors)


def _load_request_metadata(
    root: Path, request: Mapping[str, Any], arm: str
) -> dict[str, Any] | None:
    workload_request = WorkloadRequest(
        index=int(request["index"]),
        request_id=str(request["request_id"]),
        payload={},
        body=b"",
        scheduled_offset_seconds=0.0,
    )
    path = (
        _request_directory(root / "arms" / arm / "requests", workload_request)
        / "metadata.json"
    )
    if not path.is_file():
        return None
    value = load_json(path)
    if not isinstance(value, dict):
        raise ScienceToolError(f"{path} must contain a JSON object")
    return value


def _valid_request_metadata(value: dict[str, Any] | None) -> bool:
    if (
        value is None
        or value.get("complete") is not True
        or value.get("successful") is not True
        or not isinstance(value.get("status"), int)
        or not 200 <= value["status"] < 300
    ):
        return False
    for name in ("request", "response", "events"):
        recorded = value.get(name)
        if not isinstance(recorded, dict) or not isinstance(recorded.get("path"), str):
            return False
        try:
            current = artifact_identity(recorded["path"])
        except ScienceToolError:
            return False
        if (
            current["sha256"] != recorded.get("sha256")
            or current["size_bytes"] != recorded.get("size_bytes")
        ):
            return False
    return True


def _usage_delta(
    control: Any, candidate: Any
) -> dict[str, Any] | float | int | None:
    if (
        isinstance(control, (int, float))
        and not isinstance(control, bool)
        and isinstance(candidate, (int, float))
        and not isinstance(candidate, bool)
    ):
        return candidate - control
    if isinstance(control, dict) and isinstance(candidate, dict):
        result: dict[str, Any] = {}
        for key in sorted(set(control) | set(candidate)):
            delta = _usage_delta(control.get(key), candidate.get(key))
            if delta is not None:
                result[key] = delta
        return result
    return None


def compare_endpoint_pair(
    *,
    run_dir: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run_dir).resolve()
    run_metadata = load_json(root / "run.json")
    if not isinstance(run_metadata, dict):
        raise ScienceToolError("run.json must contain an object")
    contract = run_metadata.get("contract")
    if not isinstance(contract, dict) or not isinstance(contract.get("requests"), list):
        raise ScienceToolError("run.json does not contain an endpoint-pair contract")

    comparisons: list[dict[str, Any]] = []
    latency_comparable = bool(
        run_metadata.get("performance_comparable")
        and contract.get("parallel_arms")
    )
    exact_output_count = 0
    exact_token_count = 0
    matched_count = 0
    for request in contract["requests"]:
        if not isinstance(request, dict):
            raise ScienceToolError("run contract contains an invalid request")
        control = _load_request_metadata(root, request, "control")
        candidate = _load_request_metadata(root, request, "candidate")
        present_pair = control is not None and candidate is not None
        matched = _valid_request_metadata(control) and _valid_request_metadata(candidate)
        if matched:
            matched_count += 1
        output_equivalent = (
            control.get("output_text") == candidate.get("output_text")
            if matched
            and control.get("output_text") is not None
            and candidate.get("output_text") is not None
            else None
        )
        token_equivalent = (
            control.get("token_ids") == candidate.get("token_ids")
            if matched
            and control.get("token_ids") is not None
            and candidate.get("token_ids") is not None
            else None
        )
        response_bytes_equivalent = (
            control.get("response", {}).get("sha256")
            == candidate.get("response", {}).get("sha256")
            if matched
            and isinstance(control.get("response"), dict)
            and isinstance(candidate.get("response"), dict)
            else None
        )
        if output_equivalent is True:
            exact_output_count += 1
        if token_equivalent is True:
            exact_token_count += 1
        control_latency = control.get("latency_seconds") if matched else None
        candidate_latency = candidate.get("latency_seconds") if matched else None
        latency_delta = (
            candidate_latency - control_latency
            if latency_comparable
            and isinstance(control_latency, (int, float))
            and isinstance(candidate_latency, (int, float))
            else None
        )
        latency_ratio = (
            candidate_latency / control_latency
            if latency_comparable
            and isinstance(control_latency, (int, float))
            and isinstance(candidate_latency, (int, float))
            and control_latency > 0
            else None
        )
        comparisons.append(
            {
                "request_index": request.get("index"),
                "request_id": request.get("request_id"),
                "matched": matched,
                "both_present": present_pair,
                "control_present": control is not None,
                "candidate_present": candidate is not None,
                "control_complete": (
                    control.get("complete") if control is not None else None
                ),
                "candidate_complete": (
                    candidate.get("complete") if candidate is not None else None
                ),
                "control_status": (
                    control.get("status") if control is not None else None
                ),
                "candidate_status": (
                    candidate.get("status") if candidate is not None else None
                ),
                "exact_output_equivalent": output_equivalent,
                "exact_token_equivalent": token_equivalent,
                "exact_response_bytes_equivalent": response_bytes_equivalent,
                "control_finish_reason": (
                    control.get("finish_reason") if control is not None else None
                ),
                "candidate_finish_reason": (
                    candidate.get("finish_reason") if candidate is not None else None
                ),
                "control_latency_seconds": control_latency,
                "candidate_latency_seconds": candidate_latency,
                "latency_comparable": latency_comparable,
                "latency_delta_seconds": latency_delta,
                "latency_ratio_candidate_over_control": latency_ratio,
                "control_usage": (
                    control.get("usage") if control is not None else None
                ),
                "candidate_usage": (
                    candidate.get("usage") if candidate is not None else None
                ),
                "usage_delta_candidate_minus_control": (
                    _usage_delta(control.get("usage"), candidate.get("usage"))
                    if matched
                    else None
                ),
                "control_error": (
                    control.get("error") if control is not None else None
                ),
                "candidate_error": (
                    candidate.get("error") if candidate is not None else None
                ),
            }
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "endpoint_pair_comparison",
        "created_at": utc_now(),
        "run_dir": str(root),
        "request_count": len(comparisons),
        "matched_request_count": matched_count,
        "latency_comparable": latency_comparable,
        "exact_output_equivalent_count": exact_output_count,
        "exact_token_equivalent_count": exact_token_count,
        "requests": comparisons,
    }
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else root / "comparison.json"
    )
    write_json_atomic(destination, report)
    return report


def _parse_header(value: str) -> tuple[str, str]:
    separator = ":" if ":" in value else "="
    name, found, header_value = value.partition(separator)
    if not found or not name.strip():
        raise argparse.ArgumentTypeError("header must be NAME: VALUE or NAME=VALUE")
    if any(
        word in name.strip().lower()
        for word in ("authorization", "cookie", "password", "secret", "token", "api-key")
    ):
        raise argparse.ArgumentTypeError(
            "sensitive headers must use --header-env or an arm-specific header-env"
        )
    return name.strip(), header_value.lstrip()


def _headers(values: Sequence[tuple[str, str]] | None) -> dict[str, str]:
    return dict(values or [])


def _parse_header_env(value: str) -> tuple[str, str]:
    name, found, environment_name = value.partition("=")
    if (
        not found
        or not name.strip()
        or not environment_name.strip()
        or not environment_name.strip().isidentifier()
    ):
        raise argparse.ArgumentTypeError("environment header must be NAME=ENV_VAR")
    return name.strip(), environment_name.strip()


def _environment_headers(
    values: Sequence[tuple[str, str]] | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, environment_name in values or []:
        if environment_name not in os.environ:
            raise ScienceToolError(
                f"header environment variable is absent: {environment_name}"
            )
        headers[name] = os.environ[environment_name]
    return headers


def _restart_command(value: str | None) -> list[str] | None:
    if value is None:
        return None
    command = shlex.split(value)
    if not command:
        raise ScienceToolError("restart command must not be empty")
    return command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Replay an ordered JSONL workload against paired OpenAI-compatible "
            "endpoints and compare the recorded evidence."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run or resume a paired endpoint replay")
    run.add_argument("--workload", required=True)
    run.add_argument("--output-dir", required=True)
    run.add_argument("--control-url", required=True)
    run.add_argument("--candidate-url", required=True)
    run.add_argument(
        "--arm-order",
        default="control,candidate",
        help="control,candidate or candidate,control",
    )
    run.add_argument("--seed", type=int)
    run.add_argument("--timeout-seconds", type=float, default=120.0)
    run.add_argument("--restart-timeout-seconds", type=float, default=900.0)
    run.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="maximum concurrent requests within each arm",
    )
    run.add_argument(
        "--request-interval-seconds",
        type=float,
        default=0.0,
        help="default scheduled interval; rows may override scheduled_offset_seconds",
    )
    run.add_argument(
        "--parallel-arms",
        action="store_true",
        help="run control and candidate schedules concurrently on independent endpoints",
    )
    run.add_argument(
        "--compare-latency",
        action="store_true",
        help=(
            "emit paired latency deltas; asserts independent equally warm "
            "endpoints and requires --parallel-arms"
        ),
    )
    run.add_argument("--header", action="append", type=_parse_header)
    run.add_argument("--control-header", action="append", type=_parse_header)
    run.add_argument("--candidate-header", action="append", type=_parse_header)
    run.add_argument(
        "--header-env",
        action="append",
        type=_parse_header_env,
        help="read a shared header from NAME=ENV_VAR without exposing its value",
    )
    run.add_argument(
        "--control-header-env",
        action="append",
        type=_parse_header_env,
        help="read a control header from NAME=ENV_VAR",
    )
    run.add_argument(
        "--candidate-header-env",
        action="append",
        type=_parse_header_env,
        help="read a candidate header from NAME=ENV_VAR",
    )
    run.add_argument(
        "--control-restart-command",
        help="shell-like argv executed once before pending control requests",
    )
    run.add_argument(
        "--candidate-restart-command",
        help="shell-like argv executed once before pending candidate requests",
    )

    compare = commands.add_parser("compare", help="compare a recorded paired run")
    compare.add_argument("--run-dir", required=True)
    compare.add_argument("--output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "run":
            result = run_endpoint_pair(
                workload_path=args.workload,
                output_dir=args.output_dir,
                control_url=args.control_url,
                candidate_url=args.candidate_url,
                arm_order=args.arm_order,
                seed=args.seed,
                headers={
                    **_headers(args.header),
                    **_environment_headers(args.header_env),
                },
                control_headers={
                    **_headers(args.control_header),
                    **_environment_headers(args.control_header_env),
                },
                candidate_headers={
                    **_headers(args.candidate_header),
                    **_environment_headers(args.candidate_header_env),
                },
                timeout_seconds=args.timeout_seconds,
                concurrency=args.concurrency,
                request_interval_seconds=args.request_interval_seconds,
                parallel_arms=args.parallel_arms,
                compare_latency=args.compare_latency,
                restart_commands={
                    "control": _restart_command(args.control_restart_command),
                    "candidate": _restart_command(args.candidate_restart_command),
                },
                restart_timeout_seconds=args.restart_timeout_seconds,
            )
            print(json.dumps(result, sort_keys=True))
            return 0 if result["all_requests_successful"] else 1
        result = compare_endpoint_pair(
            run_dir=args.run_dir,
            output_path=args.output,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ScienceToolError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
