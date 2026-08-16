import json
import re
import urllib.error
import urllib.request


SAFE_HEADERS = {
    "cf-ray",
    "content-length",
    "content-type",
    "date",
    "retry-after",
    "server",
    "x-amzn-requestid",
    "x-request-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
}
SENSITIVE_KEY = re.compile(r"(?:authorization|cookie|credential|secret|token|api.?key)", re.I)
BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+\-/=]+")


class RunPodHttpError(RuntimeError):
    def __init__(self, details):
        super().__init__(f"RunPod HTTP {details['status']}: {details['reason']}")
        self.details = details


def sanitize_headers(headers):
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() in SAFE_HEADERS
    }


def sanitize_value(value):
    if isinstance(value, dict):
        return {
            key: "<redacted>" if SENSITIVE_KEY.search(key) else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return BEARER.sub("Bearer <redacted>", value)
    return value


def sanitize_body(body, limit=16384):
    text = body[:limit].decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return BEARER.sub("Bearer <redacted>", text)
    return json.dumps(sanitize_value(parsed), separators=(",", ":"), ensure_ascii=False)


def capture_http_error(error):
    return {
        "status": error.code,
        "reason": str(error.reason),
        "headers": sanitize_headers(error.headers or {}),
        "body": sanitize_body(error.read()),
    }


def validate_openapi_object(value, schema):
    errors = []
    properties = schema.get("properties", {})
    for key in sorted(value):
        if key not in properties:
            errors.append(f"{key} is not defined by the schema")
            continue
        item = value[key]
        rule = properties[key]
        expected = rule.get("type")
        type_matches = {
            "array": lambda candidate: isinstance(candidate, list),
            "boolean": lambda candidate: isinstance(candidate, bool),
            "integer": lambda candidate: isinstance(candidate, int)
            and not isinstance(candidate, bool),
            "number": lambda candidate: isinstance(candidate, (int, float))
            and not isinstance(candidate, bool),
            "object": lambda candidate: isinstance(candidate, dict),
            "string": lambda candidate: isinstance(candidate, str),
        }
        if expected in type_matches and not type_matches[expected](item):
            errors.append(f"{key} must have type {expected}")
            continue
        if "enum" in rule and item not in rule["enum"]:
            errors.append(f"{key} is not an allowed value")
        if "minimum" in rule and item < rule["minimum"]:
            errors.append(f"{key} must be >= {rule['minimum']}")
        if expected == "array":
            item_rule = rule.get("items", {})
            for index, member in enumerate(item):
                if "enum" in item_rule and member not in item_rule["enum"]:
                    errors.append(f"{key}[{index}] is not an allowed value")
    for key in schema.get("required", []):
        if key not in value:
            errors.append(f"{key} is required")
    return errors


def request_json(base_url, api_key, path, method="GET", payload=None, timeout=60):
    headers = {"Authorization": "Bearer " + api_key}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        base_url + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        raise RunPodHttpError(capture_http_error(error)) from None
