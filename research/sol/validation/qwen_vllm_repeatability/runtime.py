from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuntimeEstimate:
    pair_count: int
    measured_run_count: int
    measured_burst_seconds: float
    client_setup_seconds: float
    server_startup_seconds: float
    cooldown_seconds: float
    overhead_seconds: float
    total_seconds: float

    def to_mapping(self) -> dict:
        return asdict(self)


def estimate_runtime(
    durations_by_concurrency: dict[int, float],
    repeats: int,
    startup_seconds: float,
    cooldown_seconds: int,
    per_pair_overhead_seconds: float,
    per_run_client_setup_seconds: float,
) -> RuntimeEstimate:
    pair_count = len(durations_by_concurrency) * repeats
    measured_burst_seconds = 2 * repeats * sum(durations_by_concurrency.values())
    server_startup_seconds = pair_count * startup_seconds
    client_setup_seconds = pair_count * 2 * per_run_client_setup_seconds
    cooldown_total = pair_count * cooldown_seconds
    overhead_seconds = pair_count * per_pair_overhead_seconds
    total = (
        measured_burst_seconds
        + client_setup_seconds
        + server_startup_seconds
        + cooldown_total
        + overhead_seconds
    )
    return RuntimeEstimate(
        pair_count=pair_count,
        measured_run_count=pair_count * 2,
        measured_burst_seconds=measured_burst_seconds,
        client_setup_seconds=client_setup_seconds,
        server_startup_seconds=server_startup_seconds,
        cooldown_seconds=float(cooldown_total),
        overhead_seconds=overhead_seconds,
        total_seconds=total,
    )
