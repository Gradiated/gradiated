from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class SpecError(ValueError):
    pass


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SpecError(f"{name} must be an object")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpecError(f"{name} must be an integer")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{name} must be a number")
    return float(value)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SpecError(f"{name} must be a non-empty string")
    return value


def _hex(value: Any, length: int, name: str) -> str:
    result = _string(value, name)
    if len(result) != length or any(char not in "0123456789abcdef" for char in result):
        raise SpecError(f"{name} must be {length} lowercase hexadecimal characters")
    return result


@dataclass(frozen=True)
class WorkloadSpec:
    dataset_seed: int
    num_prompts: int
    input_tokens: int
    output_tokens: int
    request_rate: str
    ignore_eos: bool
    prompt_content_id: str

    @property
    def geometry(self) -> tuple[int, int, int]:
        return self.num_prompts, self.input_tokens, self.output_tokens


@dataclass(frozen=True)
class EngineSpec:
    python: Path
    checkout: Path
    expected_revision: str
    expected_version: str
    expected_tracked_diff_sha256: str
    expected_installed_binary_sha256: str
    model_path: Path
    served_model_name: str
    model_revision: str
    checkpoint_sha256: str
    tokenizer_revision: str
    host: str
    port: int
    environment: tuple[tuple[str, str], ...]
    server_arguments: tuple[str, ...]


@dataclass(frozen=True)
class IsolationSpec:
    cooldown_seconds: int
    startup_timeout_seconds: int
    quiet_process_cpu_percent: float
    minimum_available_memory_bytes: int
    require_ac_power: bool
    require_no_thermal_warning: bool
    retry_wait_seconds: int
    maximum_isolation_retries_per_pair: int
    quiet_consecutive_samples: int
    quiet_sample_interval_seconds: int
    preflight_wait_timeout_seconds: int


@dataclass(frozen=True)
class AcceptanceSpec:
    minimum_repeats_per_cell: int
    maximum_coefficient_of_variation: float
    maximum_relative_ci_half_width: float
    primary_metrics: tuple[str, ...]


@dataclass(frozen=True)
class CampaignSpec:
    schema_version: int
    campaign_id: str
    schedule_seed: int
    concurrency_levels: tuple[int, ...]
    repeat_pairs: int
    workload: WorkloadSpec
    engine: EngineSpec
    isolation: IsolationSpec
    acceptance: AcceptanceSpec
    claim_gates: tuple[tuple[str, bool], ...]

    @property
    def expected_run_count(self) -> int:
        return len(self.concurrency_levels) * self.repeat_pairs * 2

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CampaignSpec:
        try:
            schema_version = _integer(value["schema_version"], "schema_version")
            campaign_id = _string(value["campaign_id"], "campaign_id")
            schedule_seed = _integer(value["schedule_seed"], "schedule_seed")
            concurrency_raw = value["concurrency_levels"]
            repeat_pairs = _integer(value["repeat_pairs"], "repeat_pairs")
            workload_raw = _mapping(value["workload"], "workload")
            engine_raw = _mapping(value["engine"], "engine")
            isolation_raw = _mapping(value["isolation"], "isolation")
            acceptance_raw = _mapping(value["acceptance"], "acceptance")
            claim_raw = _mapping(value["claim_gates"], "claim_gates")
        except KeyError as error:
            raise SpecError(f"missing required field {error.args[0]}") from error

        if schema_version != 1:
            raise SpecError("schema_version must equal 1")
        if not isinstance(concurrency_raw, list):
            raise SpecError("concurrency_levels must be an array")
        concurrency_levels = tuple(
            _integer(item, "concurrency_levels item") for item in concurrency_raw
        )
        if concurrency_levels != (1, 2, 4, 8):
            raise SpecError("concurrency_levels must be exactly [1, 2, 4, 8]")
        if repeat_pairs != 5:
            raise SpecError("repeat_pairs must provide exactly five paired repeats")

        workload = WorkloadSpec(
            dataset_seed=_integer(workload_raw.get("dataset_seed"), "dataset_seed"),
            num_prompts=_integer(workload_raw.get("num_prompts"), "num_prompts"),
            input_tokens=_integer(workload_raw.get("input_tokens"), "input_tokens"),
            output_tokens=_integer(workload_raw.get("output_tokens"), "output_tokens"),
            request_rate=_string(workload_raw.get("request_rate"), "request_rate"),
            ignore_eos=workload_raw.get("ignore_eos"),
            prompt_content_id=_hex(
                workload_raw.get("prompt_content_id"), 64, "prompt_content_id"
            ),
        )
        if workload.geometry != (8, 128, 32):
            raise SpecError("workload geometry must remain exactly 8x128x32")
        if workload.request_rate != "inf" or workload.ignore_eos is not True:
            raise SpecError("workload must remain an infinite-rate exact-output burst")

        environment_raw = _mapping(engine_raw.get("environment"), "environment")
        if not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in environment_raw.items()
        ):
            raise SpecError("environment must map strings to strings")
        server_arguments_raw = engine_raw.get("server_arguments")
        if not isinstance(server_arguments_raw, list) or not all(
            isinstance(item, str) and item for item in server_arguments_raw
        ):
            raise SpecError("server_arguments must be an array of non-empty strings")
        engine = EngineSpec(
            python=Path(_string(engine_raw.get("python"), "engine.python")),
            checkout=Path(_string(engine_raw.get("checkout"), "engine.checkout")),
            expected_revision=_hex(
                engine_raw.get("expected_revision"), 40, "expected_revision"
            ),
            expected_version=_string(
                engine_raw.get("expected_version"), "expected_version"
            ),
            expected_tracked_diff_sha256=_hex(
                engine_raw.get("expected_tracked_diff_sha256"),
                64,
                "expected_tracked_diff_sha256",
            ),
            expected_installed_binary_sha256=_hex(
                engine_raw.get("expected_installed_binary_sha256"),
                64,
                "expected_installed_binary_sha256",
            ),
            model_path=Path(_string(engine_raw.get("model_path"), "model_path")),
            served_model_name=_string(
                engine_raw.get("served_model_name"), "served_model_name"
            ),
            model_revision=_hex(engine_raw.get("model_revision"), 40, "model_revision"),
            checkpoint_sha256=_hex(
                engine_raw.get("checkpoint_sha256"), 64, "checkpoint_sha256"
            ),
            tokenizer_revision=_hex(
                engine_raw.get("tokenizer_revision"), 40, "tokenizer_revision"
            ),
            host=_string(engine_raw.get("host"), "host"),
            port=_integer(engine_raw.get("port"), "port"),
            environment=tuple(sorted(environment_raw.items())),
            server_arguments=tuple(server_arguments_raw),
        )
        if not 1024 <= engine.port <= 65535:
            raise SpecError("port must be between 1024 and 65535")

        isolation = IsolationSpec(
            cooldown_seconds=_integer(
                isolation_raw.get("cooldown_seconds"), "cooldown_seconds"
            ),
            startup_timeout_seconds=_integer(
                isolation_raw.get("startup_timeout_seconds"),
                "startup_timeout_seconds",
            ),
            quiet_process_cpu_percent=_number(
                isolation_raw.get("quiet_process_cpu_percent"),
                "quiet_process_cpu_percent",
            ),
            minimum_available_memory_bytes=_integer(
                isolation_raw.get("minimum_available_memory_bytes"),
                "minimum_available_memory_bytes",
            ),
            require_ac_power=isolation_raw.get("require_ac_power"),
            require_no_thermal_warning=isolation_raw.get("require_no_thermal_warning"),
            retry_wait_seconds=_integer(
                isolation_raw.get("retry_wait_seconds"), "retry_wait_seconds"
            ),
            maximum_isolation_retries_per_pair=_integer(
                isolation_raw.get("maximum_isolation_retries_per_pair"),
                "maximum_isolation_retries_per_pair",
            ),
            quiet_consecutive_samples=_integer(
                isolation_raw.get("quiet_consecutive_samples"),
                "quiet_consecutive_samples",
            ),
            quiet_sample_interval_seconds=_integer(
                isolation_raw.get("quiet_sample_interval_seconds"),
                "quiet_sample_interval_seconds",
            ),
            preflight_wait_timeout_seconds=_integer(
                isolation_raw.get("preflight_wait_timeout_seconds"),
                "preflight_wait_timeout_seconds",
            ),
        )
        if isolation.cooldown_seconds < 0 or isolation.startup_timeout_seconds <= 0:
            raise SpecError("isolation durations are invalid")
        if isolation.quiet_process_cpu_percent <= 0:
            raise SpecError("quiet_process_cpu_percent must be positive")
        if isolation.minimum_available_memory_bytes <= 0:
            raise SpecError("minimum_available_memory_bytes must be positive")
        if (
            isolation.retry_wait_seconds <= 0
            or isolation.maximum_isolation_retries_per_pair < 0
            or isolation.quiet_consecutive_samples <= 0
            or isolation.quiet_sample_interval_seconds <= 0
            or isolation.preflight_wait_timeout_seconds <= 0
        ):
            raise SpecError("isolation retry policy is invalid")
        if not isinstance(isolation.require_ac_power, bool) or not isinstance(
            isolation.require_no_thermal_warning, bool
        ):
            raise SpecError("isolation requirements must be booleans")

        metrics_raw = acceptance_raw.get("primary_metrics")
        if (
            not isinstance(metrics_raw, list)
            or not metrics_raw
            or not all(isinstance(item, str) and item for item in metrics_raw)
        ):
            raise SpecError("primary_metrics must be a non-empty string array")
        acceptance = AcceptanceSpec(
            minimum_repeats_per_cell=_integer(
                acceptance_raw.get("minimum_repeats_per_cell"),
                "minimum_repeats_per_cell",
            ),
            maximum_coefficient_of_variation=_number(
                acceptance_raw.get("maximum_coefficient_of_variation"),
                "maximum_coefficient_of_variation",
            ),
            maximum_relative_ci_half_width=_number(
                acceptance_raw.get("maximum_relative_ci_half_width"),
                "maximum_relative_ci_half_width",
            ),
            primary_metrics=tuple(metrics_raw),
        )
        if acceptance.minimum_repeats_per_cell < 5:
            raise SpecError("minimum_repeats_per_cell must be at least five")
        if not 0 < acceptance.maximum_coefficient_of_variation < 1:
            raise SpecError(
                "maximum_coefficient_of_variation must be between zero and one"
            )
        if not 0 < acceptance.maximum_relative_ci_half_width < 1:
            raise SpecError(
                "maximum_relative_ci_half_width must be between zero and one"
            )

        required_claims = {
            "provider_comparison",
            "gpu_performance",
            "simulator_calibration",
            "cost_per_token",
        }
        if set(claim_raw) != required_claims or any(
            claim_raw[name] is not False for name in required_claims
        ):
            raise SpecError("all claim gates must be present and false")

        return cls(
            schema_version=schema_version,
            campaign_id=campaign_id,
            schedule_seed=schedule_seed,
            concurrency_levels=concurrency_levels,
            repeat_pairs=repeat_pairs,
            workload=workload,
            engine=engine,
            isolation=isolation,
            acceptance=acceptance,
            claim_gates=tuple(sorted((name, False) for name in required_claims)),
        )
