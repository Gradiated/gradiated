from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping


class InvalidSetting(ValueError):
    pass


@dataclass(frozen=True)
class Knob:
    """A live setting. ``/set_internal_state`` carries numbers only, so a choice is its index.

    kind "cap":    an integer from ``minimum`` up to the server's startup value, which sized the buffers.
    kind "int":    an integer in [minimum, maximum].
    kind "float":  a number in [minimum, maximum].
    kind "choice": an index into ``choices``.
    """

    name: str
    kind: str
    minimum: float = 0
    maximum: float = math.inf
    multiple_of_page: bool = False
    choices: tuple[str, ...] = ()
    doc: str = ""

    def validate(self, value: Any, startup: Mapping[str, Any], page_size: int) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidSetting(f"{self.name} must be a number, got {value!r}")
        if self.kind != "float" and not isinstance(value, int):
            raise InvalidSetting(f"{self.name} must be an integer, got {value!r}")
        if self.kind == "choice":
            if not 0 <= value < len(self.choices):
                raise InvalidSetting(f"{self.name}={value} is not one of {dict(enumerate(self.choices))}")
            return value
        ceiling = self.maximum
        if self.kind == "cap":
            ceiling = startup.get(self.name)
            if ceiling is None:
                raise InvalidSetting(f"{self.name} is unavailable: the server started without it")
        if not self.minimum <= value <= ceiling:
            raise InvalidSetting(f"{self.name}={value} is outside [{self.minimum}, {ceiling}]")
        if self.multiple_of_page and value % page_size:
            raise InvalidSetting(f"{self.name}={value} must be a multiple of the page size {page_size}")
        return value

    def label(self, value: Any) -> Any:
        return self.choices[value] if self.kind == "choice" and isinstance(value, int) and 0 <= value < len(self.choices) else value


# Order is the wire format of "choice" knobs: append, never reorder.
SCHEDULE_POLICIES = ("fcfs", "lpm", "dfs-weight", "lof", "random", "hrrn", "shortest-prefill-first", "routing-key")

KNOBS: dict[str, Knob] = {
    knob.name: knob
    for knob in (
        Knob("max_running_requests", "cap", minimum=1, doc="running-batch cap: time to first token against per-user speed"),
        Knob("chunked_prefill_size", "cap", minimum=1, multiple_of_page=True, doc="prefill chunk: decode stalls against prefill efficiency"),
        Knob("max_prefill_tokens", "cap", minimum=1, multiple_of_page=True, doc="tokens admitted per prefill batch"),
        Knob("schedule_policy", "choice", choices=SCHEDULE_POLICIES, doc="waiting-queue order; lpm and dfs-weight raise prefix-cache hits"),
        Knob("schedule_conservativeness", "float", minimum=0.1, maximum=2.0, doc="how much decode headroom prefill admission reserves; low admits more and risks retraction"),
        Knob("stream_interval", "int", minimum=1, maximum=64, doc="tokens per streamed chunk; higher cuts per-token output overhead"),
        Knob("max_queued_requests", "int", minimum=0, maximum=1_000_000, doc="waiting-queue limit, 0 = unlimited; arrivals beyond it are rejected"),
        # Not a tuning lever: `control` sets it to the version of the policy it has loaded, so a stage
        # or guard can tell a replica running that policy from one that merely has matching settings.
        Knob("policy_version", "int", minimum=0, maximum=(1 << 48) - 1, doc="version of the policy the controller has loaded; no effect on serving"),
    )
}

VARIANT_KEY = "forward_variant"
# Commands, not settings: they act once and are never read back as a setting.
COMMAND_KEYS = frozenset({"profile_seconds"})


def validate_settings(settings: Mapping[str, Any], startup: Mapping[str, Any], page_size: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in settings.items():
        if name == VARIANT_KEY:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise InvalidSetting(f"{VARIANT_KEY} must be a variant id (0 = stock)")
            out[name] = value
            continue
        knob = KNOBS.get(name)
        if knob is None:
            raise InvalidSetting(f"unknown setting {name!r}; known: {sorted(KNOBS) + [VARIANT_KEY]}")
        out[name] = knob.validate(value, startup, page_size)
    return out
