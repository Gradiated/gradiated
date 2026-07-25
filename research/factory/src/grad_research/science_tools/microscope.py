"""Opt-in, dependency-free capture and first-divergence inspection.

The microscope is deliberately independent of models and the lab scheduler.
Nothing is captured unless a :class:`Recorder` is explicitly enabled.  Tensor
inspection uses duck typing so importing this module does not import NumPy,
PyTorch, CUDA, or another accelerator runtime.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import math
import numbers
import sys
import threading
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..util import canonical_json_bytes
from .common import ScienceToolError, read_jsonl, write_jsonl_atomic


SCHEMA_VERSION = 1
FILTER_FIELDS = (
    "request_id",
    "sequence_id",
    "layer",
    "phase",
    "decode_step",
    "draft_depth",
    "tensor_role",
    "operation",
    "cycle",
)
FIELD_ALIASES = {
    "request": "request_id",
    "sequence": "sequence_id",
    "step": "decode_step",
    "role": "tensor_role",
    "op": "operation",
}
SEMANTIC_FIELDS = ("kind", *FILTER_FIELDS, "name")


def _canonical_field(name: str) -> str:
    return FIELD_ALIASES.get(name, name)


def _criterion_values(value: Any) -> tuple[Any, ...] | None:
    if value is None:
        return None
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return (value,)
    return tuple(value)


def _event_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata")
    merged = dict(metadata) if isinstance(metadata, Mapping) else {}
    for source, destination in FIELD_ALIASES.items():
        if destination not in merged and source in merged:
            merged[destination] = merged[source]
        if destination not in merged and source in event:
            merged[destination] = event[source]
    for field in FILTER_FIELDS:
        if field in event:
            merged[field] = event[field]
    return merged


class CaptureSelector:
    """Match capture coordinates; unspecified coordinates are wildcards."""

    def __init__(
        self,
        *,
        request: Any = None,
        sequence: Any = None,
        layer: Any = None,
        phase: Any = None,
        decode_step: Any = None,
        draft_depth: Any = None,
        tensor_role: Any = None,
        operation: Any = None,
        cycle: Any = None,
        request_id: Any = None,
        sequence_id: Any = None,
        enabled: bool = True,
    ) -> None:
        if request is not None and request_id is not None:
            raise ValueError("use request or request_id, not both")
        if sequence is not None and sequence_id is not None:
            raise ValueError("use sequence or sequence_id, not both")
        self.enabled = enabled
        self.criteria = {
            "request_id": _criterion_values(
                request_id if request_id is not None else request
            ),
            "sequence_id": _criterion_values(
                sequence_id if sequence_id is not None else sequence
            ),
            "layer": _criterion_values(layer),
            "phase": _criterion_values(phase),
            "decode_step": _criterion_values(decode_step),
            "draft_depth": _criterion_values(draft_depth),
            "tensor_role": _criterion_values(tensor_role),
            "operation": _criterion_values(operation),
            "cycle": _criterion_values(cycle),
        }

    def matches(
        self,
        event: Mapping[str, Any] | None = None,
        **coordinates: Any,
    ) -> bool:
        if not self.enabled:
            return False
        actual = _event_metadata(event or {})
        for key, value in coordinates.items():
            actual[_canonical_field(key)] = value
        for field, accepted in self.criteria.items():
            if accepted is not None and actual.get(field) not in accepted:
                return False
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            field: None if values is None else list(values)
            for field, values in self.criteria.items()
        }


def _call_or_value(value: Any) -> Any:
    return value() if callable(value) else value


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        return [_json_safe(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except Exception:
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe(tolist())
        except Exception:
            pass
    return {"python_type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _shape(value: Any) -> list[int] | None:
    shape = getattr(value, "shape", None)
    if shape is not None:
        try:
            return [int(part) for part in shape]
        except (TypeError, ValueError):
            pass
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    ):
        dimensions: list[int] = []
        current: Any = value
        while isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray, memoryview)
        ):
            dimensions.append(len(current))
            if not current:
                break
            current = current[0]
        return dimensions
    return None


def _stride(value: Any) -> list[int] | None:
    for attribute in ("stride", "strides"):
        candidate = getattr(value, attribute, None)
        if candidate is None:
            continue
        try:
            candidate = _call_or_value(candidate)
            return [int(part) for part in candidate]
        except (TypeError, ValueError):
            continue
    return None


def _pointer(value: Any, attribute: str) -> int | None:
    candidate = getattr(value, attribute, None)
    if candidate is None:
        return None
    try:
        return int(_call_or_value(candidate))
    except (TypeError, ValueError, RuntimeError):
        return None


def _storage_pointer(value: Any) -> int | None:
    for attribute in ("untyped_storage", "storage"):
        storage = getattr(value, attribute, None)
        if storage is None:
            continue
        try:
            pointer = _pointer(_call_or_value(storage), "data_ptr")
        except Exception:
            pointer = None
        if pointer is not None:
            return pointer
    interface = getattr(value, "__array_interface__", None)
    if isinstance(interface, Mapping):
        data = interface.get("data")
        if isinstance(data, Sequence) and data:
            try:
                return int(data[0])
            except (TypeError, ValueError):
                pass
    return _pointer(value, "data_ptr")


def _plain_value(value: Any) -> Any:
    candidate = value
    for operation in ("detach", "cpu", "contiguous"):
        method = getattr(candidate, operation, None)
        if callable(method):
            try:
                candidate = method()
            except Exception:
                break
    tolist = getattr(candidate, "tolist", None)
    if callable(tolist):
        try:
            return tolist()
        except Exception:
            pass
    return value


def _tensor_bytes(value: Any) -> tuple[bytes, str]:
    if isinstance(value, bytes):
        return value, "bytes"
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value), "bytes"

    candidate = value
    for operation in ("detach", "cpu", "contiguous"):
        method = getattr(candidate, operation, None)
        if callable(method):
            try:
                candidate = method()
            except Exception:
                break
    numpy = getattr(candidate, "numpy", None)
    if callable(numpy):
        try:
            candidate = numpy()
        except Exception:
            pass
    tobytes = getattr(candidate, "tobytes", None)
    if callable(tobytes):
        try:
            return bytes(tobytes(order="C")), "logical-c-order"
        except TypeError:
            try:
                return bytes(tobytes()), "logical-order"
            except Exception:
                pass
        except Exception:
            pass

    return canonical_json_bytes(_json_safe(_plain_value(value))), "canonical-json"


def _numeric_values(value: Any) -> list[float]:
    plain = _plain_value(value)
    values: list[float] = []
    stack = [plain]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray, memoryview)
        ):
            stack.extend(reversed(current))
        elif isinstance(current, numbers.Real) and not isinstance(current, bool):
            values.append(float(current))
    return values


def _bounded_numeric_values(value: Any, limit: int) -> tuple[list[float], int | None]:
    if limit <= 0:
        return [], None
    candidate = value
    detach = getattr(candidate, "detach", None)
    if callable(detach):
        try:
            candidate = detach()
        except Exception:
            pass
    flattened = None
    reshape = getattr(candidate, "reshape", None)
    if callable(reshape):
        try:
            flattened = reshape(-1)
        except Exception:
            pass
    if flattened is None:
        flatten = getattr(candidate, "flatten", None)
        if callable(flatten):
            try:
                flattened = flatten()
            except Exception:
                pass
    if flattened is not None:
        count_value = getattr(flattened, "numel", None)
        try:
            count = int(_call_or_value(count_value)) if count_value is not None else len(flattened)
        except (TypeError, ValueError):
            count = None
        if count is not None:
            head_count = min(count, max(1, limit // 2))
            tail_count = min(count - head_count, limit - head_count)
            segments = [flattened[:head_count]]
            if tail_count:
                segments.append(flattened[-tail_count:])
            values: list[float] = []
            for segment in segments:
                values.extend(_numeric_values(segment))
            return values[:limit], count
    values = _numeric_values(value)
    return values[:limit], len(values)


def _numeric_rows(value: Any) -> list[list[float]]:
    plain = _plain_value(value)
    rows: list[list[float]] = []

    def visit(current: Any) -> None:
        if isinstance(current, Sequence) and not isinstance(
            current, (str, bytes, bytearray, memoryview)
        ):
            if all(
                isinstance(item, numbers.Real) and not isinstance(item, bool)
                for item in current
            ):
                rows.append([float(item) for item in current])
            else:
                for child in current:
                    visit(child)

    visit(plain)
    return rows


def _stats_from_values(values: Sequence[float]) -> dict[str, Any]:
    finite = [item for item in values if math.isfinite(item)]
    result: dict[str, Any] = {
        "count": len(values),
        "finite_count": len(finite),
        "nan_count": sum(math.isnan(item) for item in values),
        "posinf_count": sum(item == math.inf for item in values),
        "neginf_count": sum(item == -math.inf for item in values),
    }
    if finite:
        result.update(
            {
                "min": min(finite),
                "max": max(finite),
                "mean": math.fsum(finite) / len(finite),
                "l2_norm": math.sqrt(math.fsum(item * item for item in finite)),
            }
        )
    else:
        result.update({"min": None, "max": None, "mean": None, "l2_norm": None})
    return result


def _sample(raw: bytes, limit: int) -> bytes:
    if limit <= 0:
        return b""
    if len(raw) <= limit:
        return raw
    if limit == 1:
        return raw[:1]
    return bytes(raw[round(index * (len(raw) - 1) / (limit - 1))] for index in range(limit))


def tensor_metadata(
    value: Any,
    *,
    byte_mode: str = "none",
    max_bytes: int = 0,
) -> dict[str, Any]:
    """Return portable tensor evidence without importing a tensor library."""

    if byte_mode not in {"none", "sample", "complete"}:
        raise ValueError("byte_mode must be none, sample, or complete")
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    dtype = getattr(value, "dtype", None)
    device = getattr(value, "device", None)
    if dtype is None:
        dtype = type(value).__name__
    if device is None and isinstance(
        value, (list, tuple, bytes, bytearray, memoryview)
    ):
        device = "cpu"
    storage_ptr = _storage_pointer(value)
    data_ptr = _pointer(value, "data_ptr")
    result: dict[str, Any] = {
        "shape": _shape(value),
        "stride": _stride(value),
        "dtype": str(dtype),
        "device": None if device is None else str(device),
        "data_ptr": data_ptr,
        "storage_ptr": storage_ptr,
        "alias_pointer": storage_ptr if storage_ptr is not None else data_ptr,
        "capture_scope": byte_mode,
    }
    if byte_mode == "none":
        return result
    if byte_mode == "sample":
        if isinstance(value, (bytes, bytearray, memoryview)):
            source = bytes(value)
            captured = _sample(source, max_bytes) if max_bytes else b""
            raw = captured
            values: list[float] = []
            source_elements: int | None = len(source)
            logical_encoding = "sampled-bytes"
            source_bytes = len(source)
        else:
            sample_limit = max(1, max_bytes // 8) if max_bytes else 64
            values, source_elements = _bounded_numeric_values(value, sample_limit)
            raw = canonical_json_bytes(values)
            captured = _sample(raw, max_bytes) if max_bytes else b""
            logical_encoding = "sampled-numeric-json"
            source_bytes = len(raw)
        result.update(
            {
                "sample_values": values,
                "sampled_elements": len(values),
                "source_elements": source_elements,
                "digest": {
                    "algorithm": "sha256",
                    "value": hashlib.sha256(raw).hexdigest(),
                    "logical_encoding": logical_encoding,
                    "source_bytes": source_bytes,
                    "complete": (
                        source_elements is not None
                        and len(values) == source_elements
                    ),
                },
                "stats": _stats_from_values(values),
            }
        )
    else:
        raw, logical_encoding = _tensor_bytes(value)
        captured = raw[:max_bytes]
        result.update(
            {
                "digest": {
                    "algorithm": "sha256",
                    "value": hashlib.sha256(raw).hexdigest(),
                    "logical_encoding": logical_encoding,
                    "source_bytes": len(raw),
                    "complete": True,
                },
                "stats": _stats_from_values(_numeric_values(value)),
            }
        )
    result["bytes"] = {
            "encoding": "base64",
            "mode": byte_mode,
            "data": base64.b64encode(captured).decode("ascii"),
            "captured_bytes": len(captured),
            "source_bytes": source_bytes if byte_mode == "sample" else len(raw),
            "complete": len(captured)
            == (source_bytes if byte_mode == "sample" else len(raw)),
    }
    return result


class Recorder:
    """Record selected semantic events to stable-order JSONL."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        selector: CaptureSelector | None = None,
        metadata: Mapping[str, Any] | None = None,
        enabled: bool | None = None,
        byte_mode: str = "none",
        max_bytes: int = 0,
        resume: bool = False,
    ) -> None:
        self.path = None if path is None else Path(path)
        self.enabled = bool(path) if enabled is None else enabled
        self.selector = selector or CaptureSelector()
        self.metadata = _json_safe(dict(metadata or {}))
        self.byte_mode = byte_mode
        self.max_bytes = max_bytes
        self._events: list[dict[str, Any]] = []
        self._persisted_count = 0
        self._lock = threading.Lock()
        if self.enabled and self.path is not None:
            if self.path.exists():
                if not resume:
                    raise ScienceToolError(
                        f"capture already exists; pass resume=True to append: {self.path}"
                    )
                self._events = read_jsonl(self.path)
                self._persisted_count = len(self._events)
            else:
                write_jsonl_atomic(self.path, [])

    @classmethod
    def disabled(cls) -> "Recorder":
        return cls(enabled=False)

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *_: Any) -> None:
        self.flush()

    def flush(self) -> None:
        if self.enabled and self.path is not None:
            with self._lock:
                self._persist_locked()

    def _persist_locked(self) -> None:
        if self.path is None or self._persisted_count == len(self._events):
            return
        with self.path.open("ab") as handle:
            for event in self._events[self._persisted_count :]:
                handle.write(canonical_json_bytes(event) + b"\n")
            handle.flush()
        self._persisted_count = len(self._events)

    def _coordinates(
        self,
        metadata: Mapping[str, Any] | None,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged = dict(self.metadata)
        if metadata:
            merged.update(_json_safe(dict(metadata)))
        for key, value in context.items():
            merged[_canonical_field(key)] = _json_safe(value)
        return merged

    def _emit(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        coordinates = self._coordinates(metadata, context)
        if not self.selector.matches(**coordinates):
            return None
        with self._lock:
            event = {
                "schema_version": SCHEMA_VERSION,
                "order": len(self._events),
                "kind": str(kind),
                "metadata": coordinates,
                "payload": _json_safe(dict(payload or {})),
            }
            self._events.append(event)
            self._persist_locked()
        return event

    def record(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        return self._emit(
            kind,
            payload,
            metadata=metadata,
            **context,
        )

    def tensor(
        self,
        value: Any,
        *,
        name: str | None = None,
        tensor_role: str | None = None,
        byte_mode: str | None = None,
        max_bytes: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        coordinates = self._coordinates(metadata, context)
        if tensor_role is not None:
            coordinates["tensor_role"] = tensor_role
        if not self.selector.matches(**coordinates):
            return None
        payload = {
            "name": name,
            "tensor": tensor_metadata(
                value,
                byte_mode=self.byte_mode if byte_mode is None else byte_mode,
                max_bytes=self.max_bytes if max_bytes is None else max_bytes,
            ),
        }
        return self._emit("tensor", payload, metadata=coordinates)

    record_tensor = tensor

    def logits_topk(
        self,
        logits: Any,
        *,
        k: int = 5,
        name: str = "logits",
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        rows = _numeric_rows(logits)
        ranked_rows = [
            sorted(enumerate(values), key=lambda item: (-item[1], item[0]))[
                : max(k, 0)
            ]
            for values in rows
        ]
        if not ranked_rows:
            ranked_rows = [[]]
        top_k_by_row = [
            [
                {"token_id": token_id, "value": value}
                for token_id, value in ranked
            ]
            for ranked in ranked_rows
        ]
        payload: dict[str, Any] = {
            "name": name,
            "k": k,
            "row_count": len(top_k_by_row),
        }
        if len(top_k_by_row) == 1:
            payload["top_k"] = top_k_by_row[0]
        else:
            payload["top_k_by_row"] = top_k_by_row
        return self._emit(
            "logits_topk",
            payload,
            metadata=metadata,
            **context,
        )

    record_logits_topk = logits_topk

    def acceptance(
        self,
        *,
        accepted_prefix: Any,
        bonus_token: Any,
        committed_length: int,
        next_token: Any,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        return self._emit(
            "acceptance",
            {
                "accepted_prefix": _json_safe(accepted_prefix),
                "bonus_token": _json_safe(bonus_token),
                "committed_length": committed_length,
                "next_token": _json_safe(next_token),
            },
            metadata=metadata,
            **context,
        )

    record_acceptance = acceptance

    def kv(
        self,
        *,
        source: Any,
        destination: Any,
        valid_length: int,
        ownership: Any,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        return self._emit(
            "kv",
            {
                "source": _json_safe(source),
                "destination": _json_safe(destination),
                "valid_length": valid_length,
                "ownership": _json_safe(ownership),
            },
            metadata=metadata,
            **context,
        )

    record_kv = kv

    def correlation(
        self,
        *,
        stream: Any = None,
        event: Any = None,
        operator: Any = None,
        kernel: Any = None,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> dict[str, Any] | None:
        return self._emit(
            "correlation",
            {
                "stream": _json_safe(stream),
                "event": _json_safe(event),
                "operator": _json_safe(operator),
                "kernel": _json_safe(kernel),
            },
            metadata=metadata,
            **context,
        )

    record_correlation = correlation


def semantic_key(event: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _event_metadata(event)
    payload = event.get("payload")
    payload = payload if isinstance(payload, Mapping) else {}
    key: dict[str, Any] = {"kind": event.get("kind", event.get("event_type"))}
    for field in FILTER_FIELDS:
        if field in metadata:
            key[field] = metadata[field]
    if "name" in payload:
        key["name"] = payload["name"]
    elif "name" in event:
        key["name"] = event["name"]
    return key


def _key_bytes(event: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(semantic_key(event))


def _ignored(path: str, field: str, ignored: set[str]) -> bool:
    dotted = path.removeprefix("$.")
    return any(
        fnmatch.fnmatchcase(candidate, pattern)
        for pattern in ignored
        for candidate in (field, dotted, path)
    )


def _contains_complete_tensor(value: Any) -> bool:
    if isinstance(value, Mapping):
        if (
            value.get("capture_scope") == "complete"
            and "digest" in value
            and "shape" in value
        ):
            return True
        return any(_contains_complete_tensor(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return any(_contains_complete_tensor(child) for child in value)
    return False


def _first_value_difference(
    left: Any,
    right: Any,
    *,
    path: str,
    ignored: set[str],
    atol: float,
    rtol: float,
) -> dict[str, Any] | None:
    if isinstance(left, numbers.Real) and isinstance(right, numbers.Real):
        if isinstance(left, bool) or isinstance(right, bool):
            equal = left == right and type(left) is type(right)
        else:
            left_float = float(left)
            right_float = float(right)
            equal = (
                math.isnan(left_float)
                and math.isnan(right_float)
            ) or math.isclose(
                left_float,
                right_float,
                rel_tol=rtol,
                abs_tol=atol,
            )
        if equal:
            return None
        return {"path": path, "left_value": left, "right_value": right}

    if isinstance(left, Mapping) and isinstance(right, Mapping):
        for key in sorted(set(left) | set(right), key=str):
            key_string = str(key)
            child_path = f"{path}.{key_string}"
            if _ignored(child_path, key_string, ignored):
                continue
            if key not in left:
                return {
                    "path": child_path,
                    "left_value": None,
                    "right_value": _json_safe(right[key]),
                    "field_missing_from": "left",
                }
            if key not in right:
                return {
                    "path": child_path,
                    "left_value": _json_safe(left[key]),
                    "right_value": None,
                    "field_missing_from": "right",
                }
            difference = _first_value_difference(
                left[key],
                right[key],
                path=child_path,
                ignored=ignored,
                atol=atol,
                rtol=rtol,
            )
            if difference:
                return difference
        return None

    if (
        isinstance(left, Sequence)
        and isinstance(right, Sequence)
        and not isinstance(left, (str, bytes, bytearray))
        and not isinstance(right, (str, bytes, bytearray))
    ):
        for index in range(max(len(left), len(right))):
            child_path = f"{path}[{index}]"
            if index >= len(left):
                return {
                    "path": child_path,
                    "left_value": None,
                    "right_value": _json_safe(right[index]),
                    "field_missing_from": "left",
                }
            if index >= len(right):
                return {
                    "path": child_path,
                    "left_value": _json_safe(left[index]),
                    "right_value": None,
                    "field_missing_from": "right",
                }
            difference = _first_value_difference(
                left[index],
                right[index],
                path=child_path,
                ignored=ignored,
                atol=atol,
                rtol=rtol,
            )
            if difference:
                return difference
        return None

    if type(left) is type(right) and left == right:
        return None
    return {
        "path": path,
        "left_value": _json_safe(left),
        "right_value": _json_safe(right),
    }


def diff_events(
    left_events: Sequence[Mapping[str, Any]],
    right_events: Sequence[Mapping[str, Any]],
    *,
    ignore_fields: Iterable[str] = (),
    atol: float = 0.0,
    rtol: float = 0.0,
    compare_pointers: bool = False,
) -> dict[str, Any]:
    """Report the first chronological missing, reordered, or divergent event."""

    if atol < 0 or rtol < 0:
        raise ValueError("numeric tolerances must be non-negative")
    ignored = {"order", *ignore_fields}
    if not compare_pointers:
        ignored.update({"*.data_ptr", "*.storage_ptr", "*.alias_pointer"})
    complete_tensor_present = any(
        _contains_complete_tensor(event)
        for event in (*left_events, *right_events)
    )
    if (atol or rtol) and not complete_tensor_present:
        ignored.update({"*.digest", "*.bytes"})

    for index in range(max(len(left_events), len(right_events))):
        if index >= len(left_events):
            right = right_events[index]
            return {
                "equal": False,
                "difference": "missing_event",
                "missing_from": "left",
                "semantic_key": semantic_key(right),
                "left_index": None,
                "right_index": index,
                "path": "$",
                "left_value": None,
                "right_value": _json_safe(right),
            }
        if index >= len(right_events):
            left = left_events[index]
            return {
                "equal": False,
                "difference": "missing_event",
                "missing_from": "right",
                "semantic_key": semantic_key(left),
                "left_index": index,
                "right_index": None,
                "path": "$",
                "left_value": _json_safe(left),
                "right_value": None,
            }
        left = left_events[index]
        right = right_events[index]
        left_key = semantic_key(left)
        right_key = semantic_key(right)
        if _key_bytes(left) != _key_bytes(right):
            return {
                "equal": False,
                "difference": "event_order_or_identity",
                "left_semantic_key": left_key,
                "right_semantic_key": right_key,
                "left_index": index,
                "right_index": index,
                "path": "$.semantic_key",
                "left_value": left_key,
                "right_value": right_key,
            }
        difference = _first_value_difference(
            left,
            right,
            path="$",
            ignored=ignored,
            atol=atol,
            rtol=rtol,
        )
        if difference:
            return {
                "equal": False,
                "difference": "divergent_field",
                "semantic_key": left_key,
                "left_index": index,
                "right_index": index,
                **difference,
            }

    return {
        "equal": True,
        "difference": None,
        "left_event_count": len(left_events),
        "right_event_count": len(right_events),
        "atol": atol,
        "rtol": rtol,
        "compared_pointers": compare_pointers,
        "tolerant_tensor_comparison": bool(
            (atol or rtol) and not complete_tensor_present
        ),
    }


def diff_captures(
    left: str | Path,
    right: str | Path,
    *,
    ignore_fields: Iterable[str] = (),
    atol: float = 0.0,
    rtol: float = 0.0,
    compare_pointers: bool = False,
) -> dict[str, Any]:
    return diff_events(
        read_jsonl(left),
        read_jsonl(right),
        ignore_fields=ignore_fields,
        atol=atol,
        rtol=rtol,
        compare_pointers=compare_pointers,
    )


def import_capture(
    source: str | Path,
    destination: str | Path,
    *,
    selector: CaptureSelector | None = None,
) -> dict[str, Any]:
    rows = read_jsonl(source)
    selected = []
    for source_order, row in enumerate(rows):
        if selector is not None and not selector.matches(row):
            continue
        imported = dict(row)
        imported.setdefault("order", source_order)
        selected.append(imported)
    write_jsonl_atomic(destination, selected)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": str(source),
        "destination": str(destination),
        "input_event_count": len(rows),
        "captured_event_count": len(selected),
        "selector": None if selector is None else selector.as_dict(),
    }


def summarize_events(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    kinds = Counter(str(event.get("kind", event.get("event_type", "unknown"))) for event in events)
    dimensions: dict[str, list[Any]] = {}
    for field in FILTER_FIELDS:
        values = {
            canonical_json_bytes(metadata[field]): metadata[field]
            for event in events
            for metadata in [_event_metadata(event)]
            if field in metadata
        }
        if values:
            dimensions[field] = [
                values[key] for key in sorted(values)
            ]
    orders = [
        event["order"]
        for event in events
        if isinstance(event.get("order"), numbers.Integral)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "event_count": len(events),
        "kinds": dict(sorted(kinds.items())),
        "dimensions": dimensions,
        "first_order": min(orders) if orders else None,
        "last_order": max(orders) if orders else None,
    }


def summarize_capture(path: str | Path) -> dict[str, Any]:
    result = summarize_events(read_jsonl(path))
    result["path"] = str(path)
    return result


def _parse_cli_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _selector_from_args(args: argparse.Namespace) -> CaptureSelector:
    values = {
        field: None
        if getattr(args, field) is None
        else [_parse_cli_value(value) for value in getattr(args, field)]
        for field in FILTER_FIELDS
    }
    return CaptureSelector(**values)


def _add_selector_arguments(parser: argparse.ArgumentParser) -> None:
    for field in FILTER_FIELDS:
        flags = [f"--{field.replace('_', '-')}"]
        if field == "request_id":
            flags.append("--request")
        elif field == "sequence_id":
            flags.append("--sequence")
        parser.add_argument(
            *flags,
            dest=field,
            action="append",
            help=f"capture only matching {field}; repeat to allow multiple values",
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lab-microscope",
        description="Opt-in semantic capture and first-divergence inspection.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser(
        "capture", help="filter/import prebuilt event JSONL into a capture"
    )
    capture.add_argument("input_path", nargs="?")
    capture.add_argument("output_path", nargs="?")
    capture.add_argument("--input", dest="input_option")
    capture.add_argument("--output", dest="output_option")
    _add_selector_arguments(capture)

    difference = commands.add_parser(
        "diff", help="find the first missing event or divergent field"
    )
    difference.add_argument("left")
    difference.add_argument("right")
    difference.add_argument("--ignore-field", action="append", default=[])
    difference.add_argument("--atol", type=float, default=0.0)
    difference.add_argument("--rtol", type=float, default=0.0)
    difference.add_argument(
        "--compare-pointers",
        action="store_true",
        help="treat process-local storage/data pointer differences as evidence",
    )

    summary = commands.add_parser("summary", help="summarize a capture")
    summary.add_argument("capture")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "capture":
            source = args.input_option or args.input_path
            destination = args.output_option or args.output_path
            if not source or not destination:
                raise ScienceToolError("capture requires input and output paths")
            result = import_capture(
                source,
                destination,
                selector=_selector_from_args(args),
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "diff":
            result = diff_captures(
                args.left,
                args.right,
                ignore_fields=args.ignore_field,
                atol=args.atol,
                rtol=args.rtol,
                compare_pointers=args.compare_pointers,
            )
            print(json.dumps(result, sort_keys=True))
            return 0 if result["equal"] else 1
        result = summarize_capture(args.capture)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ScienceToolError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
