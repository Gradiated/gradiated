#!/usr/bin/env python3
import ast
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


FENCE = re.compile(r"^\s*```(?:python)?[ \t]*\r?\n(?P<body>.*?)\r?\n?```[ \t]*\s*$", re.DOTALL)


@dataclass(frozen=True)
class Decision:
    output: Any
    transformed: bool
    reason: str


def safe_python(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    defined_functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    allowed_calls = defined_functions | {"min", "max", "len", "range", "list", "tuple"}
    forbidden = (
        ast.Import, ast.ImportFrom, ast.Attribute, ast.ClassDef, ast.AsyncFunctionDef,
        ast.Global, ast.Nonlocal, ast.Lambda, ast.With, ast.AsyncWith, ast.Try,
        ast.Raise, ast.While, ast.Delete,
    )
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            return False
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return False
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls:
                return False
    return True


def request_requires_python_code_only(request_bytes: str) -> bool:
    try:
        request = json.loads(request_bytes)
    except (TypeError, json.JSONDecodeError):
        return False
    messages = request.get("messages")
    if not isinstance(messages, list):
        return False
    text = "\n".join(
        message.get("content", "")
        for message in messages
        if isinstance(message, dict) and message.get("role") == "user" and isinstance(message.get("content"), str)
    )
    return bool(re.search(r"\b(?:return|respond with|output)\s+only\s+(?:valid\s+)?python\s+code\b", text, re.IGNORECASE))


def adapt(request_bytes: str, output: Any) -> Decision:
    if not isinstance(output, str) or not request_requires_python_code_only(request_bytes):
        return Decision(output, False, "request_not_explicit_code_only")
    if output.count("```") != 2:
        return Decision(output, False, "not_exactly_one_outer_fence")
    match = FENCE.fullmatch(output)
    if match is None:
        return Decision(output, False, "not_a_supported_outer_fence")
    body = match.group("body")
    if not safe_python(body):
        return Decision(output, False, "unsafe_python")
    return Decision(body, True, "safe_outer_python_fence")


def digest(value: Any) -> str:
    if isinstance(value, str):
        encoded = value.encode("utf-8")
    else:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
