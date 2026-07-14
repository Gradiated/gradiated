from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ValidationError(ValueError):
    """A durable research record is malformed or unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValidationError(f"value is not canonical JSON: {error}") from error
    return encoded.encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValidationError(f"{name} must be a lowercase SHA-256")
    return value


def require_id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValidationError(f"{name} must be a safe nonempty identifier")
    return value


def require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be nonempty text")
    return value.strip()


def require_probability(name: str, value: Any) -> float:
    number = require_number(name, value)
    if not 0 <= number <= 1:
        raise ValidationError(f"{name} must be in [0,1]")
    return number


def require_number(name: str, value: Any, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{name} must be finite")
    if nonnegative and number < 0:
        raise ValidationError(f"{name} must be nonnegative")
    return number


def require_string_list(name: str, value: Any, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        suffix = "a nonempty" if nonempty else "a"
        raise ValidationError(f"{name} must be {suffix} list")
    rows = []
    for index, item in enumerate(value):
        rows.append(require_text(f"{name}[{index}]", item))
    return rows


def parse_utc(value: Any, name: str = "timestamp") -> datetime:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"{name} must be an RFC3339 UTC timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValidationError(f"{name} must be UTC")
    return parsed


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_relative_path(name: str, value: Any) -> str:
    text = require_text(name, value)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError(f"{name} must be a safe relative path")
    return text


def usd_to_micros(name: str, value: Any, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{name} must be decimal-compatible")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValidationError(f"{name} must be decimal-compatible") from error
    if not amount.is_finite() or amount < 0 or (positive and amount <= 0):
        condition = "positive" if positive else "nonnegative"
        raise ValidationError(f"{name} must be finite and {condition}")
    return int((amount * Decimal(1_000_000)).to_integral_value(rounding=ROUND_CEILING))


def micros_to_usd(value: int) -> float:
    return float(Decimal(value) / Decimal(1_000_000))
