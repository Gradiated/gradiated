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

    def fingerprint(self) -> dict[str, Any]:
        info = json.loads(self._request("/server_info"))
        keys = ("model_path", "served_model_name", "revision", "tp_size", "dp_size", "ep_size", "pp_size", "attn_cp_size", "kv_cache_dtype", "quantization", "version")
        state = self.livetune_state()
        # The scheduler reports its own GPU; the client running this may have none, or different ones.
        if not state.get("gpu"):
            raise UpdateFailed(f"{self.url} does not report its GPU; upgrade its livetune plugin")
        # Page size bounds which knob values the server accepts; the variant code, installed and
        # selectable by id, is what a policy's forward_variant settings were measured with.
        envelope = ("gpu", "page_size", "startup", "variant", "variants")
        return {**{key: info.get(key) for key in keys}, **{key: state.get(key) for key in envelope}}

    def livetune_states(self) -> list[dict[str, Any]]:
        # One entry per data-parallel scheduler.
        state = json.loads(self._request("/server_info"))
        rows = state.get("internal_states", state)
        return [row.get("livetune", {}) for row in (rows if isinstance(rows, list) else [rows])]

    def livetune_state(self) -> dict[str, Any]:
        return self.livetune_states()[0]

    def apply(self, settings: dict[str, Any], timeout: float = 300.0) -> dict[str, Any]:
        """Send the settings that differ from any scheduler's live state; return what was sent."""
        live = self.livetune_states()
        settings = {k: v for k, v in settings.items() if any(state.get("settings", {}).get(k) != v for state in live)}
        if not settings:
            return settings
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
                return settings
            pending = any(states[index].get("pending_variant") is not None for index in mismatched)
            if not pending or time.monotonic() >= deadline:
                errors = [states[index].get("recent_errors") for index in mismatched]
                raise UpdateFailed(f"readback mismatch by scheduler (wanted, live): {mismatched}; errors: {errors}")
            time.sleep(0.5)
