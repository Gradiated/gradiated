from __future__ import annotations

import contextlib
import contextvars
import json
import os
import re
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from ..util import canonical_json_bytes, utc_now
from .common import ScienceToolError


ResultT = TypeVar("ResultT")
VALID_MODES = {"stock", "candidate", "auto"}
_CONTEXT_SELECTIONS: contextvars.ContextVar[tuple[dict[str, str], ...]] = (
    contextvars.ContextVar("grad_replacement_selections", default=())
)


def _normalize_component(value: str | None) -> str | None:
    if value is None or value == "*":
        return None
    text = str(value).strip()
    if not text or "|" in text:
        raise ScienceToolError("replacement key components must be nonempty and omit '|'")
    return text


def normalize_shape(shape: Sequence[Any] | str | None) -> tuple[str, ...] | None:
    if shape is None or shape == "*":
        return None
    if isinstance(shape, str):
        values = tuple(part for part in re.split(r"[x, ]+", shape) if part)
    else:
        values = tuple(str(value) for value in shape)
    if not values or any(not value or "|" in value for value in values):
        raise ScienceToolError("replacement shape must contain safe dimensions")
    return values


@dataclass(frozen=True)
class ReplacementKey:
    operation: str
    phase: str | None = None
    shape: tuple[str, ...] | None = None

    @classmethod
    def make(
        cls,
        operation: str,
        *,
        phase: str | None = None,
        shape: Sequence[Any] | str | None = None,
    ) -> "ReplacementKey":
        normalized_operation = _normalize_component(operation)
        if normalized_operation is None:
            raise ScienceToolError("replacement operation must be specific")
        return cls(
            normalized_operation,
            _normalize_component(phase),
            normalize_shape(shape),
        )

    def selector(self) -> str:
        shape = "*" if self.shape is None else "x".join(self.shape)
        return f"{self.operation}|{self.phase or '*'}|{shape}"


@dataclass
class _Entry(Generic[ResultT]):
    stock: Callable[..., ResultT]
    candidate: Callable[..., ResultT] | None


def _callable_identity(function: Callable[..., Any]) -> str:
    module = getattr(function, "__module__", type(function).__module__)
    name = getattr(function, "__qualname__", type(function).__qualname__)
    return f"{module}.{name}"


class ReplacementRegistry:
    """Thread-safe stock/candidate dispatch with scoped and environment selection."""

    def __init__(
        self,
        *,
        proof_path: str | Path | None = None,
        environment_variable: str = "LAB_HOT_REPLACEMENTS",
        default_mode: str = "stock",
    ) -> None:
        if default_mode not in VALID_MODES:
            raise ScienceToolError(f"invalid default replacement mode: {default_mode}")
        self._entries: dict[ReplacementKey, _Entry[Any]] = {}
        self._lock = threading.RLock()
        self.proof_path = None if proof_path is None else Path(proof_path)
        self.environment_variable = environment_variable
        self.default_mode = default_mode

    def register(
        self,
        operation: str,
        stock: Callable[..., ResultT],
        candidate: Callable[..., ResultT] | None = None,
        *,
        phase: str | None = None,
        shape: Sequence[Any] | str | None = None,
        replace: bool = False,
    ) -> ReplacementKey:
        if not callable(stock) or (candidate is not None and not callable(candidate)):
            raise ScienceToolError("stock and candidate replacements must be callable")
        key = ReplacementKey.make(operation, phase=phase, shape=shape)
        with self._lock:
            if key in self._entries and not replace:
                raise ScienceToolError(f"replacement is already registered: {key.selector()}")
            self._entries[key] = _Entry(stock=stock, candidate=candidate)
        return key

    def unregister(
        self,
        operation: str,
        *,
        phase: str | None = None,
        shape: Sequence[Any] | str | None = None,
    ) -> None:
        key = ReplacementKey.make(operation, phase=phase, shape=shape)
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _entry(
        self, requested: ReplacementKey
    ) -> tuple[ReplacementKey, _Entry[Any]]:
        candidates = (
            requested,
            ReplacementKey(requested.operation, requested.phase, None),
            ReplacementKey(requested.operation, None, requested.shape),
            ReplacementKey(requested.operation, None, None),
        )
        with self._lock:
            for key in dict.fromkeys(candidates):
                if key in self._entries:
                    return key, self._entries[key]
        raise ScienceToolError(f"replacement is not registered: {requested.selector()}")

    def _environment_selections(self) -> dict[str, str]:
        raw = os.environ.get(self.environment_variable)
        if not raw:
            return {}
        if raw in VALID_MODES:
            return {"*": raw}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ScienceToolError(
                f"{self.environment_variable} must be a mode or JSON selector mapping"
            ) from error
        if not isinstance(value, Mapping):
            raise ScienceToolError(
                f"{self.environment_variable} must contain a JSON object"
            )
        selections = {str(key): str(mode) for key, mode in value.items()}
        invalid = [mode for mode in selections.values() if mode not in VALID_MODES]
        if invalid:
            raise ScienceToolError(
                f"{self.environment_variable} contains invalid mode: {invalid[0]}"
            )
        return selections

    @staticmethod
    def _match_selection(selections: Mapping[str, str], key: ReplacementKey) -> str | None:
        options = (
            key.selector(),
            f"{key.operation}|{key.phase or '*'}|*",
            (
                f"{key.operation}|*|{'*' if key.shape is None else 'x'.join(key.shape)}"
            ),
            f"{key.operation}|*|*",
            key.operation,
            "*",
        )
        return next((selections[item] for item in options if item in selections), None)

    def _mode(self, key: ReplacementKey, explicit: str | None) -> str:
        if explicit is not None:
            if explicit not in VALID_MODES:
                raise ScienceToolError(f"invalid replacement mode: {explicit}")
            return explicit
        for selections in reversed(_CONTEXT_SELECTIONS.get()):
            selected = self._match_selection(selections, key)
            if selected is not None:
                return selected
        selected = self._match_selection(self._environment_selections(), key)
        return selected or self.default_mode

    @contextlib.contextmanager
    def select(
        self,
        mode: str,
        *,
        operation: str | None = None,
        phase: str | None = None,
        shape: Sequence[Any] | str | None = None,
    ) -> Iterator[None]:
        if mode not in VALID_MODES:
            raise ScienceToolError(f"invalid replacement mode: {mode}")
        if operation is None:
            selector = "*"
        else:
            selector = ReplacementKey.make(
                operation, phase=phase, shape=shape
            ).selector()
        current = _CONTEXT_SELECTIONS.get()
        token = _CONTEXT_SELECTIONS.set((*current, {selector: mode}))
        try:
            yield
        finally:
            _CONTEXT_SELECTIONS.reset(token)

    def _append_proof(self, event: Mapping[str, Any]) -> None:
        if self.proof_path is None:
            return
        encoded = canonical_json_bytes(dict(event)) + b"\n"
        with self._lock:
            self.proof_path.parent.mkdir(parents=True, exist_ok=True)
            with self.proof_path.open("ab") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

    def resolve(
        self,
        operation: str,
        *,
        phase: str | None = None,
        shape: Sequence[Any] | str | None = None,
        mode: str | None = None,
    ) -> tuple[Callable[..., Any], dict[str, Any]]:
        requested = ReplacementKey.make(operation, phase=phase, shape=shape)
        registered, entry = self._entry(requested)
        requested_mode = self._mode(requested, mode)
        use_candidate = requested_mode in {"candidate", "auto"}
        fallback_reason = None
        if use_candidate and entry.candidate is None:
            use_candidate = False
            fallback_reason = "candidate_not_registered"
        selected = "candidate" if use_candidate else "stock"
        function = entry.candidate if use_candidate else entry.stock
        assert function is not None
        proof = {
            "schema_version": 1,
            "event": "replacement_resolved",
            "timestamp": utc_now(),
            "invocation_id": uuid.uuid4().hex,
            "requested_key": requested.selector(),
            "registered_key": registered.selector(),
            "requested_mode": requested_mode,
            "selected": selected,
            "fallback": fallback_reason is not None,
            "fallback_reason": fallback_reason,
            "callable": _callable_identity(function),
        }
        return function, proof

    def call(
        self,
        operation: str,
        *args: Any,
        phase: str | None = None,
        shape: Sequence[Any] | str | None = None,
        mode: str | None = None,
        fallback_on_error: bool = False,
        **kwargs: Any,
    ) -> Any:
        function, proof = self.resolve(
            operation, phase=phase, shape=shape, mode=mode
        )
        try:
            result = function(*args, **kwargs)
        except Exception as error:
            if proof["selected"] != "candidate" or not fallback_on_error:
                proof.update(
                    {
                        "event": "replacement_failed",
                        "success": False,
                        "error_type": type(error).__name__,
                    }
                )
                self._append_proof(proof)
                raise
            requested = ReplacementKey.make(operation, phase=phase, shape=shape)
            _, entry = self._entry(requested)
            proof.update(
                {
                    "selected": "stock",
                    "fallback": True,
                    "fallback_reason": "candidate_raised",
                    "candidate_error_type": type(error).__name__,
                    "callable": _callable_identity(entry.stock),
                }
            )
            result = entry.stock(*args, **kwargs)
        proof.update({"event": "replacement_invoked", "success": True})
        self._append_proof(proof)
        return result


default_registry = ReplacementRegistry()


def register_replacement(
    operation: str,
    stock: Callable[..., ResultT],
    candidate: Callable[..., ResultT] | None = None,
    **key: Any,
) -> ReplacementKey:
    return default_registry.register(operation, stock, candidate, **key)


def invoke_replacement(operation: str, *args: Any, **kwargs: Any) -> Any:
    return default_registry.call(operation, *args, **kwargs)


def replacement_selection(mode: str, **key: Any) -> contextlib.AbstractContextManager[None]:
    return default_registry.select(mode, **key)
