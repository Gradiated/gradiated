#!/usr/bin/env python3
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


CONTRACT = (
    "\n\nSafe-code output contract: Return exactly one Python function definition and no Markdown or prose. "
    "Call only functions defined in your response plus min, max, len, range, list, and tuple. "
    "Do not use imports, attributes, sorted, or any other calls."
)
EXPLICIT_CODE_ONLY = re.compile(
    r"\b(?:return|respond with|output)\s+only\s+(?:valid\s+)?python\s+code\b", re.IGNORECASE
)


@dataclass(frozen=True)
class TransformDecision:
    request_bytes: str
    transformed: bool
    reason: str
    original_sha256: str
    transformed_sha256: str


def digest_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def explicit_code_only_request(request: dict[str, Any]) -> bool:
    messages = request.get("messages")
    if not isinstance(messages, list):
        return False
    user_text = "\n".join(
        message["content"]
        for message in messages
        if isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(message.get("content"), str)
    )
    return bool(EXPLICIT_CODE_ONLY.search(user_text))


def transform_request(request_bytes: str) -> TransformDecision:
    original_sha256 = digest_bytes(request_bytes)
    try:
        request = json.loads(request_bytes)
    except (TypeError, json.JSONDecodeError):
        return TransformDecision(request_bytes, False, "invalid_json", original_sha256, original_sha256)
    if not isinstance(request, dict) or not explicit_code_only_request(request):
        return TransformDecision(request_bytes, False, "request_not_explicit_code_only", original_sha256, original_sha256)
    messages = request.get("messages")
    assert isinstance(messages, list)
    changed = False
    transformed_messages = []
    for message in messages:
        copied = dict(message) if isinstance(message, dict) else message
        if (
            isinstance(copied, dict)
            and copied.get("role") == "user"
            and isinstance(copied.get("content"), str)
        ):
            copied["content"] += CONTRACT
            changed = True
        transformed_messages.append(copied)
    if not changed:
        return TransformDecision(request_bytes, False, "no_string_user_message", original_sha256, original_sha256)
    transformed = dict(request)
    transformed["messages"] = transformed_messages
    transformed_bytes = canonical_json(transformed)
    return TransformDecision(
        transformed_bytes,
        True,
        "explicit_code_only_contract_appended",
        original_sha256,
        digest_bytes(transformed_bytes),
    )
