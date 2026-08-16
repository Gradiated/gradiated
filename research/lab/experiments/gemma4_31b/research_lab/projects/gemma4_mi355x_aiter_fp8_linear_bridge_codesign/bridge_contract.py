from __future__ import annotations

from dataclasses import asdict, dataclass


BASELINE_SECONDS_PER_REQUEST = 0.6000950932112802
TARGET_SECONDS_PER_REQUEST = 0.5910500600431771
CONCURRENCY = 32
OUTPUT_TOKENS = 358
TARGET_CYCLES = 15
PREFILL_M = 3679
DECODE_M = 32
VERIFICATION_M = 384
CONVERSION_AMORTIZATION_REQUESTS = 10_000
CONVERSION_AMORTIZATION_HURDLE_SECONDS = 0.0003613108999519

BASELINE_TRANSFORMER_SECONDS = {
    "prefill": 0.21629139633045502,
    "ordinary_decode_m32": 0.1370320896,
    "target_verification_m384": 0.0105828581376,
}


@dataclass(frozen=True)
class LinearShape:
    name: str
    n: int
    k: int
    layers: int
    family: str

    @property
    def parameters_per_layer(self) -> int:
        return self.n * self.k

    @property
    def executed_parameters(self) -> int:
        return self.parameters_per_layer * self.layers

    def as_dict(self) -> dict:
        return {
            **asdict(self),
            "parameters_per_layer": self.parameters_per_layer,
            "executed_parameters": self.executed_parameters,
        }


LINEAR_SHAPES = (
    LinearShape("sliding_qkv", 16_384, 5_376, 50, "sliding_attention"),
    LinearShape("sliding_o", 5_376, 8_192, 50, "sliding_attention"),
    LinearShape("global_qkv", 20_480, 5_376, 10, "global_attention"),
    LinearShape("global_o", 5_376, 16_384, 10, "global_attention"),
    LinearShape("gate_up", 43_008, 5_376, 60, "mlp"),
    LinearShape("down", 5_376, 21_504, 60, "mlp"),
)

PHASES = {
    "prefill": {"m": PREFILL_M, "request_multiplier": 1.0},
    "ordinary_decode_m32": {
        "m": DECODE_M,
        "request_multiplier": OUTPUT_TOKENS / CONCURRENCY,
    },
    "target_verification_m384": {
        "m": VERIFICATION_M,
        "request_multiplier": TARGET_CYCLES / CONCURRENCY,
    },
}


def total_transformer_parameters() -> int:
    return sum(shape.executed_parameters for shape in LINEAR_SHAPES)


def baseline_transformer_seconds() -> float:
    return sum(BASELINE_TRANSFORMER_SECONDS.values())


def unchanged_seconds_per_request() -> float:
    return BASELINE_SECONDS_PER_REQUEST - baseline_transformer_seconds()


def candidate_transformer_budget_seconds() -> float:
    return TARGET_SECONDS_PER_REQUEST - unchanged_seconds_per_request()


def candidate_runtime_budget_seconds() -> float:
    return (
        candidate_transformer_budget_seconds()
        - CONVERSION_AMORTIZATION_HURDLE_SECONDS
    )


def phase_runtime_hurdles() -> dict[str, float]:
    scale = candidate_runtime_budget_seconds() / baseline_transformer_seconds()
    return {
        name: seconds * scale
        for name, seconds in BASELINE_TRANSFORMER_SECONDS.items()
    }


def per_shape_timing_hurdles() -> list[dict]:
    total_parameters = total_transformer_parameters()
    rows = []
    for phase_name, phase in PHASES.items():
        full_pass_hurdle = (
            phase_runtime_hurdles()[phase_name] / phase["request_multiplier"]
        )
        for shape in LINEAR_SHAPES:
            per_call_seconds = (
                full_pass_hurdle
                * shape.parameters_per_layer
                / total_parameters
            )
            rows.append(
                {
                    "phase": phase_name,
                    "m": phase["m"],
                    "shape": shape.name,
                    "n": shape.n,
                    "k": shape.k,
                    "layers": shape.layers,
                    "candidate_apply_p95_hurdle_us_per_call": (
                        per_call_seconds * 1_000_000
                    ),
                    "request_multiplier": phase["request_multiplier"],
                }
            )
    return rows


def aggregate_runtime_seconds(timing_rows: list[dict], metric: str) -> float:
    indexed = {
        (row["phase"], row["shape"]): float(row[metric]) / 1_000_000
        for row in timing_rows
    }
    total = 0.0
    for phase_name, phase in PHASES.items():
        full_pass = sum(
            indexed[(phase_name, shape.name)] * shape.layers
            for shape in LINEAR_SHAPES
        )
        total += full_pass * phase["request_multiplier"]
    return total


assert total_transformer_parameters() == 29_396_828_160
