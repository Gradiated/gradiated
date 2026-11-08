from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class InvalidSetting(ValueError):
    pass


@dataclass(frozen=True)
class Knob:
    name: str
    minimum: int
    startup_field: str
    multiple_of_page: bool = False

    def validate(self, value: Any, startup: Mapping[str, Any], page_size: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidSetting(f"{self.name} must be an integer, got {value!r}")
        ceiling = startup.get(self.startup_field)
        if ceiling is None:
            raise InvalidSetting(f"{self.name} is unavailable: server started without {self.startup_field}")
        if not self.minimum <= value <= ceiling:
            raise InvalidSetting(f"{self.name}={value} is outside [{self.minimum}, {ceiling}]")
        if self.multiple_of_page and value % page_size:
            raise InvalidSetting(f"{self.name}={value} must be a multiple of the page size {page_size}")
        return value


KNOBS: dict[str, Knob] = {
    knob.name: knob
    for knob in (
        Knob("max_running_requests", minimum=1, startup_field="max_running_requests"),
        Knob("chunked_prefill_size", minimum=1, startup_field="chunked_prefill_size", multiple_of_page=True),
        Knob("max_prefill_tokens", minimum=1, startup_field="max_prefill_tokens", multiple_of_page=True),
    )
}

VARIANT_KEY = "forward_variant"


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
