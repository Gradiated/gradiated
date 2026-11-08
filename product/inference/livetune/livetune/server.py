from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from livetune.knobs import KNOBS, VARIANT_KEY
from livetune.metrics import Scrape, parse


class UpdateFailed(RuntimeError):
    pass


KV_TOLERANCE = 0.05


# Every launch argument that can change serving performance is in scope. Left out: what differs
# between replicas of one deployment (addresses, ports, ranks, paths), what the controller itself
# changes, the random seed, and anything that can hold a secret. KV capacity is derived from free
# memory, so it is recorded on its own and compared with a tolerance.
_INSTANCE = re.compile(r"^_|key|password|secret|(^|_)(host|ports?|addr|endpoints?|rank|dir|folder|path|file)$|^log_")
_KEEP = {"model_path", "tokenizer_path", "speculative_draft_model_path", "quantization_param_path", "max_lora_rank", "mamba_max_states_per_path"}
_NOT_SCOPE = {
    "internal_states", "status", "startup_time", "launch_command", "base_gpu_id", "weight_version", "warmups",
    "served_model_name", "max_total_num_tokens", "random_seed", "pp_max_micro_batch_size", *KNOBS,
}


def serving_config(info: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in sorted(info.items()) if k in _KEEP or not (k in _NOT_SCOPE or _INSTANCE.search(k))}


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
        # Page size bounds which knob values the server accepts. The startup variant id (in startup)
        # and the verified catalog fix the forward code; the live variant is state, not scope.
        envelope = ("gpu", "page_size", "pp_micro_batch_startup", "startup", "variants", "live_variants")
        scopes = [{key: state.get(key) for key in envelope} for state in self.livetune_states()]
        # The scheduler reports its own GPU; the client running this may have none, or different ones.
        if not all(scope["gpu"] for scope in scopes):
            raise UpdateFailed(f"{self.url} does not report its GPU; upgrade its livetune plugin")
        if any(scope != scopes[0] for scope in scopes):
            raise UpdateFailed(f"{self.url} has data-parallel schedulers with different scopes: {scopes}")
        # Weights can be replaced in place; /model_info names the ones serving now.
        model = json.loads(self._request("/model_info"))
        live_model = {key: model.get(key) for key in ("model_path", "weight_version")}
        return {"server_args": serving_config(info), "model": live_model, "kv_tokens": info.get("max_total_num_tokens"), **scopes[0]}

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
