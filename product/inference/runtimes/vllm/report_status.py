#!/usr/bin/env python3
"""Report one vLLM deployment status over a persistent HTTPS connection."""

from __future__ import annotations

import http.client
import json
import os
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def metric_value(text: str, names: tuple[str, ...]) -> float:
    value = 0.0
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        metric_name = line.split("{", 1)[0].split(None, 1)[0]
        if metric_name not in names:
            continue
        try:
            value = float(line.rsplit(None, 1)[1])
        except (IndexError, ValueError):
            continue
    return value


@dataclass(frozen=True)
class RuntimeStatus:
    healthy: bool
    accepting_requests: bool
    reason_code: str | None


def classify_runtime(
    healthy: bool,
    metrics: str,
    kv_usage_limit: float,
) -> RuntimeStatus:
    """Classify deployment pressure from runtime metrics.

    The engine owns running-set admission. Do not gate on
    ``vllm:num_requests_running``: that counter tracks engine batch state, not a
    capacity limit, and it moves with prompt length and KV budget. The engine
    rejects excess load itself with HTTP 503 when ``max_num_queued_reqs`` or
    ``max_num_queued_tokens`` is reached.
    """
    if not healthy:
        return RuntimeStatus(False, False, "runtime_unhealthy")
    kv_usage = metric_value(
        metrics,
        (
            "vllm:kv_cache_usage_perc",
            "vllm_kv_cache_usage_perc",
            "vllm:gpu_cache_usage_perc",
            "vllm_gpu_cache_usage_perc",
        ),
    )
    if kv_usage >= kv_usage_limit:
        return RuntimeStatus(True, False, "kv_pressure")
    return RuntimeStatus(True, True, None)


class PersistentClient:
    def __init__(self, url: str, timeout: float):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("status URL must use HTTP or HTTPS")
        self.scheme = parsed.scheme
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.path = parsed.path or "/"
        if parsed.query:
            self.path = f"{self.path}?{parsed.query}"
        self.timeout = timeout
        self.connection: http.client.HTTPConnection | None = None

    def _connect(self) -> http.client.HTTPConnection:
        if self.connection is None:
            if self.scheme == "https":
                self.connection = http.client.HTTPSConnection(
                    self.host,
                    self.port,
                    timeout=self.timeout,
                    context=ssl.create_default_context(),
                )
            else:
                self.connection = http.client.HTTPConnection(
                    self.host,
                    self.port,
                    timeout=self.timeout,
                )
        return self.connection

    def request(
        self,
        method: str,
        path: str | None = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        try:
            connection = self._connect()
            connection.request(method, path or self.path, body=body, headers=headers or {})
            response = connection.getresponse()
            response_body = response.read()
            if response.will_close:
                self.close()
            return response.status, response_body
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class RuntimeObserver:
    def __init__(self, port: int, timeout: float):
        self.client = PersistentClient(f"http://127.0.0.1:{port}", timeout)

    def observe(self, kv_usage_limit: float) -> RuntimeStatus:
        try:
            health_status, _ = self.client.request("GET", "/health")
            if health_status != 200:
                return classify_runtime(False, "", kv_usage_limit)
            metrics_status, metrics = self.client.request("GET", "/metrics")
            if metrics_status != 200:
                return classify_runtime(False, "", kv_usage_limit)
            return classify_runtime(
                True,
                metrics.decode("utf-8", errors="replace"),
                kv_usage_limit,
            )
        except Exception:
            return classify_runtime(False, "", kv_usage_limit)


class StatusUploader:
    def __init__(self, url: str, token: str, timeout: float):
        self.client = PersistentClient(url, timeout)
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "gradiated-vllm-status/1",
        }

    def upload(self, payload: dict[str, object]) -> None:
        status, _ = self.client.request(
            "POST",
            body=json.dumps(payload, separators=(",", ":")).encode(),
            headers=self.headers,
        )
        if status != 204:
            self.client.close()
            raise RuntimeError(f"status endpoint returned HTTP {status}")


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    deployment_id = required("DEPLOYMENT_ID")
    runtime_port = int(required("RUNTIME_PORT"))
    runtime_revision = required("RUNTIME_REVISION")
    status_url = required("STATUS_URL")
    status_token = Path(required("STATUS_TOKEN_FILE")).read_text().strip()
    if not status_token:
        raise RuntimeError("status token file is empty")
    kv_usage_limit = float(os.environ.get("KV_USAGE_LIMIT", "0.90"))
    interval = float(os.environ.get("STATUS_INTERVAL_SECONDS", "1"))
    timeout = float(os.environ.get("STATUS_TIMEOUT_SECONDS", "2"))
    observer = RuntimeObserver(runtime_port, min(timeout, 0.75))
    uploader = StatusUploader(status_url, status_token, timeout)
    consecutive_failures = 0

    while True:
        started = time.monotonic()
        runtime = observer.observe(kv_usage_limit)
        payload: dict[str, object] = {
            "schema_version": 1,
            "deployment_id": deployment_id,
            "runtime_revision": runtime_revision,
            "healthy": runtime.healthy,
            "accepting_requests": runtime.accepting_requests,
            "reason_code": runtime.reason_code,
        }
        try:
            uploader.upload(payload)
            if consecutive_failures:
                print(
                    f"{timestamp()} deployment status upload recovered for "
                    f"{deployment_id} after {consecutive_failures} failures",
                    file=sys.stderr,
                    flush=True,
                )
            consecutive_failures = 0
        except Exception as error:
            consecutive_failures += 1
            print(
                f"{timestamp()} deployment status upload failed for {deployment_id}: "
                f"{type(error).__name__}",
                file=sys.stderr,
                flush=True,
            )
        elapsed = time.monotonic() - started
        delay = 0.1 if consecutive_failures else max(0.0, interval - elapsed)
        time.sleep(delay)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as error:
        print(f"status reporter configuration error: {error}", file=sys.stderr)
        raise SystemExit(64) from error
