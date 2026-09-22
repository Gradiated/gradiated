#!/usr/bin/env python3
"""Report one Kev deployment status over a persistent HTTPS connection.

The gateway refuses to route to a deployment whose status is missing or stale, so
one of these runs per replica. The decision adapter has no queue and answers 429
while its GPU is busy, which the gateway already treats as capacity exhaustion and
retries elsewhere; this reporter therefore describes whether the replica is
serving at all, not how loaded it is.
"""

from __future__ import annotations

import http.client
import json
import os
import ssl
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PersistentClient:
    """One connection reused across reports, reopened only when it breaks."""

    def __init__(self, url: str, timeout: float):
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise RuntimeError("status URL must be an absolute HTTP(S) URL")
        self.secure = parsed.scheme == "https"
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path or "/"
        self.timeout = timeout
        self.connection: http.client.HTTPConnection | None = None

    def connect(self) -> http.client.HTTPConnection:
        if self.connection is None:
            if self.secure:
                self.connection = http.client.HTTPSConnection(
                    self.host, self.port, timeout=self.timeout,
                    context=ssl.create_default_context(),
                )
            else:
                self.connection = http.client.HTTPConnection(
                    self.host, self.port, timeout=self.timeout
                )
        return self.connection

    def request(self, method: str, body: bytes, headers: dict[str, str]) -> int:
        for attempt in (0, 1):
            try:
                connection = self.connect()
                connection.request(method, self.path, body=body, headers=headers)
                response = connection.getresponse()
                response.read()
                return response.status
            except (OSError, http.client.HTTPException):
                self.close()
                if attempt:
                    raise
        raise RuntimeError("unreachable")

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None


def observe(port: int, timeout: float) -> bool:
    """Whether the replica answers its health route."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        response.read()
        return response.status == 200
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def main() -> int:
    deployment_id = required("DEPLOYMENT_ID")
    runtime_port = int(required("RUNTIME_PORT"))
    runtime_revision = required("RUNTIME_REVISION")
    status_url = required("STATUS_URL")
    status_token = Path(required("STATUS_TOKEN_FILE")).read_text().strip()
    if not status_token:
        raise RuntimeError("status token file is empty")
    interval = float(os.environ.get("STATUS_INTERVAL_SECONDS", "1"))
    timeout = float(os.environ.get("STATUS_TIMEOUT_SECONDS", "2"))

    client = PersistentClient(status_url, timeout)
    headers = {
        "Authorization": f"Bearer {status_token}",
        "Content-Type": "application/json",
        "User-Agent": "gradiated-kev-status/1",
    }
    failures = 0

    while True:
        started = time.monotonic()
        healthy = observe(runtime_port, min(timeout, 0.75))
        payload = {
            "schema_version": 1,
            "deployment_id": deployment_id,
            "runtime_revision": runtime_revision,
            "healthy": healthy,
            "accepting_requests": healthy,
            "reason_code": None if healthy else "runtime_unreachable",
        }
        try:
            status = client.request(
                "POST", json.dumps(payload, separators=(",", ":")).encode(), headers
            )
            if status != 204:
                client.close()
                raise RuntimeError(f"status endpoint returned HTTP {status}")
            if failures:
                print(
                    f"{timestamp()} deployment status upload recovered for "
                    f"{deployment_id} after {failures} failures",
                    file=sys.stderr, flush=True,
                )
            failures = 0
        except Exception as error:  # noqa: BLE001 - reported, never fatal
            failures += 1
            print(
                f"{timestamp()} deployment status upload failed for "
                f"{deployment_id} ({failures}): {type(error).__name__}",
                file=sys.stderr, flush=True,
            )
        time.sleep(max(0.0, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
