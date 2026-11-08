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

    def livetune_states(self) -> list[dict[str, Any]]:
        # One entry per data-parallel scheduler.
        state = json.loads(self._request("/server_info"))
        rows = state.get("internal_states", state)
        return [row.get("livetune", {}) for row in (rows if isinstance(rows, list) else [rows])]

    def livetune_state(self) -> dict[str, Any]:
        return self.livetune_states()[0]

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
            states = self.livetune_states()
            mismatched = {
                index: {k: (v, state.get("settings", {}).get(k)) for k, v in settings.items() if state.get("settings", {}).get(k) != v}
                for index, state in enumerate(states)
            }
            mismatched = {index: diff for index, diff in mismatched.items() if diff}
            if not mismatched:
                return
            pending = any(states[index].get("pending_variant") is not None for index in mismatched)
            if not pending or time.monotonic() >= deadline:
                errors = [states[index].get("recent_errors") for index in mismatched]
                raise UpdateFailed(f"readback mismatch by scheduler (wanted, live): {mismatched}; errors: {errors}")
            time.sleep(0.5)
