from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from livetune.knobs import VARIANT_KEY
from livetune.metrics import Scrape, parse


class UpdateFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class Server:
    url: str
    timeout_s: float = 30.0

    def _request(self, path: str, body: dict[str, Any] | None = None, timeout: float | None = None) -> bytes:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(request, timeout=timeout or self.timeout_s) as response:
            return response.read()

    def scrape(self) -> Scrape:
        return parse(self._request("/metrics").decode(), time.monotonic())

    def livetune_state(self) -> dict[str, Any]:
        state = json.loads(self._request("/server_info"))
        rows = state.get("internal_states", state)
        first = rows[0] if isinstance(rows, list) else rows
        return first.get("livetune", {})

    def apply(self, settings: dict[str, Any], timeout: float = 300.0) -> None:
        if not settings:
            return
        reply = json.loads(self._request("/set_internal_state", {"server_args": settings}, timeout=timeout))
        # One boolean per data-parallel scheduler.
        updated = reply if isinstance(reply, list) else [reply.get("updated", False)]
        if not updated or not all(updated):
            raise UpdateFailed(f"server rejected {settings}: {reply}")
        # A variant switch completes only once the scheduler drains, so poll for it.
        deadline = time.monotonic() + (timeout if VARIANT_KEY in settings else 0)
        while True:
            state = self.livetune_state()
            live = state.get("settings", {})
            mismatched = {k: (v, live.get(k)) for k, v in settings.items() if live.get(k) != v}
            if not mismatched:
                return
            if state.get("pending_variant") is None or time.monotonic() >= deadline:
                raise UpdateFailed(f"readback mismatch (wanted, live): {mismatched}; errors: {state.get('recent_errors')}")
            time.sleep(0.5)
