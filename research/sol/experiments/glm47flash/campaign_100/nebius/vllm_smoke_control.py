#!/usr/bin/env python3
"""Bounded stock-vLLM disambiguation smoke for the GLM AWQ checkpoint."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from awq_smoke_control import (  # noqa: E402
    DISK_GIB,
    DISK_HOURLY_RATE_USD,
    HOURLY_RATE_USD,
    PLATFORM,
    PRESET,
    emit,
    probe_transfer,
    validate_local_model,
)
from placement_control import (  # noqa: E402
    PlacementError,
    build_create_command,
    delete_disk,
    delete_instance,
    extract_instance_id,
    extract_public_ipv4,
    find_named_instance,
    get_instance,
    list_items,
    make_cloud_init,
    metadata_id,
    metadata_name,
    wait_absent,
    wait_ssh,
)
from stock_control import extract_member, run_ssh, scp_from, scp_to, verify_internal_manifest  # noqa: E402
from session_staging import transfer_checkpoint, transfer_timeout_seconds, validate_local_files_cached  # noqa: E402
from selective_w4_scope import VALID_SCOPES  # noqa: E402


IMAGE = "vllm/vllm-openai:v0.15.0@sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"
TRANSFORMERS_REVISION = "1618d44b9295361607ec74d7be860ba886aac039"
RUNTIME_IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
ABSOLUTE_TIMEOUT_SECONDS = 4500
ARTIFACT_RESERVE_SECONDS = 300
RUNTIME_CONTRACT_SHA256 = hashlib.sha256(
    f"{IMAGE}\n{TRANSFORMERS_REVISION}\ntiktoken==0.12.0\n".encode()
).hexdigest()
# This launcher owns the H100 vLLM venue; AWQ's imported L40S constants must not leak into it.
PLATFORM = "gpu-h100-sxm"
PRESET = "1gpu-16vcpu-200gb"
DISK_GIB = 250
HOURLY_RATE_USD = 3.85
DISK_HOURLY_RATE_USD = 0.0243055
L40S_AWQ_PROFILE = ("gpu-l40s-a", "1gpu-16vcpu-64gb", 100, 0.8484, 0.0097222)
METHODOLOGY_LADDER = (1, 2, 4, 8, 16, 32, 64)
MOE_TOP2_NO_SHARED_PATCH = HERE.parent.parent / "research_lab" / "projects" / "adaptive_moe_architecture" / "moe_top2_no_shared_patch.py"
MOE_TOP2_NO_SHARED_PATCH_SHA256 = "69f34087f816038a8ba7e9c3874b42fb6837d4f4df794a11f0d8c797820dfa7e"


class VllmSmokeError(RuntimeError):
    pass


BF16_MODEL_REVISION = "33faccf4c2ba82142214d0d4e16232a4e9ccfe10"
BF16_MODEL_SHARDS = 48
BF16_MODEL_BYTES = 62_444_175_504


def validate_bf16_model(model_dir: Path) -> dict[str, object]:
    manifest_path = model_dir / "model-files-manifest.json"
    checksum_path = model_dir / "model-files.sha256"
    if not manifest_path.is_file() or not checksum_path.is_file():
        raise VllmSmokeError("BF16 model lacks manifest contract")
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("revision"), manifest.get("shard_count"), manifest.get("weight_bytes")) != (BF16_MODEL_REVISION, BF16_MODEL_SHARDS, BF16_MODEL_BYTES):
        raise VllmSmokeError("BF16 identity geometry mismatch")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len([row for row in rows if row.get("path", "").endswith(".safetensors")]) != BF16_MODEL_SHARDS:
        raise VllmSmokeError("BF16 shard manifest mismatch")
    validate_local_files_cached(model_dir, rows)
    return {"model_revision": BF16_MODEL_REVISION, "model_shard_count": BF16_MODEL_SHARDS, "model_weight_bytes": BF16_MODEL_BYTES, "model_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}


def redact_provider_text(value: str, limit: int = 4000) -> str:
    value = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
        "<redacted-private-key>",
        value,
        flags=re.DOTALL,
    )
    value = re.sub(
        r"(?i)((?:access[_-]?token|authorization|bearer|password|secret)\s*[:=]?\s*)\S+",
        r"\1<redacted>",
        value,
    )
    return value[-limit:]


def write_create_diagnostic(output_dir: Path, proc: subprocess.CompletedProcess[str]) -> None:
    (output_dir / "provider-create-diagnostic.json").write_text(
        json.dumps(
            {
                "stage": "provider_create",
                "returncode": proc.returncode,
                "stdout_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(proc.stderr.encode()).hexdigest(),
                "stdout_tail_redacted": redact_provider_text(proc.stdout),
                "stderr_tail_redacted": redact_provider_text(proc.stderr),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def resolve_created_instance(proc: subprocess.CompletedProcess[str], name: str) -> tuple[str, bool]:
    instance_id = None
    if proc.stdout.strip():
        try:
            instance_id = extract_instance_id(json.loads(proc.stdout))
        except (json.JSONDecodeError, PlacementError):
            instance_id = None
    if instance_id is None:
        instance_id = find_named_instance(name)
    if instance_id is None:
        raise VllmSmokeError(f"instance create failed with exit {proc.returncode}")
    return instance_id, proc.returncode != 0


def allocation_has_harness_error(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    if isinstance(result.get("error"), dict):
        return True
    for stage in ("quality", "performance", "profiler"):
        value = result.get(stage)
        if isinstance(value, dict) and isinstance(value.get(f"{stage}_error"), dict):
            return True
    return False


def background_completion_pass(
    result: dict | None,
    arm_envelope_seconds: float | None,
    *,
    allow_deferred_absolute_quality_failure: bool = False,
) -> bool:
    if not isinstance(result, dict) or arm_envelope_seconds is None or arm_envelope_seconds <= 0:
        return False
    if allocation_has_harness_error(result):
        return False
    semantic = result.get("semantic")
    quality = result.get("quality")
    if not isinstance(semantic, dict) or not isinstance(quality, dict):
        return False
    if semantic.get("pass") is not True:
        return False
    if quality.get("pass") is not True and not (
        allow_deferred_absolute_quality_failure
        and quality.get("absolute_bf16_quality_failure_carried_forward") is True
    ):
        return False
    performance = result.get("performance")
    if not isinstance(performance, dict):
        return False
    profiles = performance.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return False
    for profile in profiles:
        if not isinstance(profile, dict):
            return False
        if profile.get("success_fraction") != 1.0 or profile.get("exact_geometry_pass") is not True:
            return False
        if profile.get("requests") != 64 or len(profile.get("rows", [])) != 64:
            return False
        if profile.get("prefix_cache_disabled") is not True or profile.get("prefix_cache_zero_delta") is not True:
            return False
        if not isinstance(profile.get("wall_seconds"), (int, float)) or profile["wall_seconds"] > arm_envelope_seconds:
            return False
    return True


def execution_outcome(
    remote_returncode: int,
    result: dict | None,
    arm_envelope_seconds: float | None,
    *,
    allow_deferred_absolute_quality_failure: bool = False,
) -> tuple[str, bool]:
    background_pass = background_completion_pass(
        result,
        arm_envelope_seconds,
        allow_deferred_absolute_quality_failure=allow_deferred_absolute_quality_failure,
    )
    legacy_batch_pass = (
        remote_returncode == 0
        and isinstance(result, dict)
        and result.get("batch_pass") is True
    )
    return ("PASS" if legacy_batch_pass or background_pass else "FAIL", background_pass)


def methodology_completion_pass(result: dict | None) -> bool:
    if not isinstance(result, dict) or result.get("pass") is not True:
        return False
    single = result.get("single_request")
    rows = single.get("rows") if isinstance(single, dict) else None
    if (
        not isinstance(rows, list)
        or len(rows) != 7
        or single.get("geometry_pass") is not True
        or single.get("requests") != 7
        or len({row.get("prompt_sha256") for row in rows if isinstance(row, dict)}) != 7
    ):
        return False
    if any(
        not isinstance(row, dict)
        or row.get("input_tokens_o200k") != 10_000
        or not isinstance(row.get("output_tokens_server"), int)
        or row["output_tokens_server"] < 1_500
        or row.get("output_token_ids_complete") is not True
        for row in rows
    ):
        return False
    system_load = result.get("system_load")
    phases = system_load.get("phases") if isinstance(system_load, dict) else None
    if not isinstance(phases, list) or not phases:
        return False
    observed_ladder = [phase.get("concurrency") for phase in phases if isinstance(phase, dict)]
    if observed_ladder != list(METHODOLOGY_LADDER[: len(observed_ladder)]):
        return False
    if observed_ladder != list(METHODOLOGY_LADDER):
        plateau = system_load.get("plateau")
        if not (
            isinstance(plateau, dict)
            and plateau.get("at_concurrency") == observed_ladder[-1]
            and plateau.get("rule") == "two adjacent steps below 5% aggregate-throughput gain"
        ):
            return False
    return all(
        isinstance(phase, dict)
        and phase.get("planned_phase_seconds") == 180
        and isinstance(phase.get("wall_seconds"), (int, float))
        and phase["wall_seconds"] >= 180
        and phase.get("geometry_pass") is True
        and phase.get("success_fraction") == 1.0
        and isinstance(phase.get("requests_completed"), int)
        and phase["requests_completed"] > 0
        for phase in phases
    )


def methodology_useful_gpu_seconds(result: dict | None) -> float | None:
    if not isinstance(result, dict):
        return None
    single = result.get("single_request")
    rows = single.get("rows") if isinstance(single, dict) else None
    system_load = result.get("system_load")
    phases = system_load.get("phases") if isinstance(system_load, dict) else None
    seconds = 0.0
    found = False
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("end_to_end_ms"), (int, float)):
                seconds += float(row["end_to_end_ms"]) / 1000
                found = True
    if isinstance(phases, list):
        for phase in phases:
            if isinstance(phase, dict) and isinstance(phase.get("wall_seconds"), (int, float)):
                seconds += float(phase["wall_seconds"])
                found = True
    return round(seconds, 3) if found else None


def useful_gpu_seconds(result: dict | None) -> float | None:
    if not isinstance(result, dict):
        return None
    performance = result.get("performance")
    profiles = performance.get("profiles") if isinstance(performance, dict) else None
    if not isinstance(profiles, list):
        return None
    values = [
        float(profile["wall_seconds"])
        for profile in profiles
        if isinstance(profile, dict) and isinstance(profile.get("wall_seconds"), (int, float))
    ]
    return round(sum(values), 3) if values else None


def required_quality_files(quality_dir: Path) -> list[Path]:
    manifest = json.loads((quality_dir / "FROZEN_MANIFEST.json").read_text())
    return [quality_dir / name for name in sorted(manifest["files"])] + [quality_dir / "FROZEN_MANIFEST.json"]


def hold_for_repair_decision(
    output_dir: Path,
    events: Path,
    deadline: float,
    maximum_seconds: int = 0,
) -> None:
    """Wait only when a launcher explicitly opts into a bounded in-place repair window."""
    if maximum_seconds <= 0:
        emit(events, "repair_window_skipped")
        return
    decision_path = output_dir / "repair-decision.json"
    hold_deadline = min(deadline, time.time() + min(maximum_seconds, 600))
    emit(events, "repair_window_open", maximum_seconds=max(0, round(hold_deadline - time.time(), 3)))
    while time.time() < hold_deadline:
        if decision_path.exists():
            try:
                decision = json.loads(decision_path.read_text())
            except Exception:
                decision = {"action": "invalid"}
            emit(events, "repair_decision_received", action=decision.get("action"))
            if decision.get("action") == "teardown":
                return
        time.sleep(5)
    emit(events, "repair_window_expired")


@contextmanager
def measured_phase(events: Path, name: str):
    started = time.monotonic()
    state = {}
    emit(events, "phase_started", phase=name)
    try:
        yield state
    except Exception as error:
        emit(
            events,
            "phase_finished",
            phase=name,
            outcome="FAIL",
            elapsed_seconds=round(time.monotonic() - started, 3),
            error_type=type(error).__name__,
        )
        raise
    else:
        emit(
            events,
            "phase_finished",
            phase=name,
            outcome=state.pop("outcome", "PASS"),
            elapsed_seconds=round(time.monotonic() - started, 3),
            **state,
        )


def build_host_bootstrap() -> str:
    return f'''set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y docker.io curl ca-certificates gnupg
fi
sudo systemctl enable --now docker
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
RUNTIME_CONTRACT={RUNTIME_CONTRACT_SHA256}
CURRENT_CONTRACT="$(sudo docker image inspect {RUNTIME_IMAGE} --format '{{{{index .Config.Labels "org.gradiated.runtime-contract"}}}}' 2>/dev/null || true)"
if [ "$CURRENT_CONTRACT" = "$RUNTIME_CONTRACT" ]; then
  printf 'runtime_image_cache_hit=true contract=%s\n' "$RUNTIME_CONTRACT"
else
  printf 'runtime_image_cache_hit=false contract=%s\n' "$RUNTIME_CONTRACT"
  pull_ok=0
  for attempt in 1 2; do
    if sudo docker pull {IMAGE}; then pull_ok=1; break; fi
  done
  test "$pull_ok" = 1
  sudo docker image inspect {IMAGE} --format '{{{{json .RepoDigests}}}}'
  sudo docker build --network=host --label org.gradiated.runtime-contract="$RUNTIME_CONTRACT" -t {RUNTIME_IMAGE} - <<'DOCKERFILE'
FROM {IMAGE}
RUN python3 -m pip install --no-cache-dir --upgrade https://github.com/huggingface/transformers/archive/{TRANSFORMERS_REVISION}.tar.gz
RUN python3 -m pip install --no-cache-dir tiktoken==0.12.0
DOCKERFILE
fi
sudo docker image inspect {RUNTIME_IMAGE} --format '{{{{.Id}}}}'
sudo docker run --rm --gpus all -v /home/glmrunner/input:/input:ro --entrypoint bash {RUNTIME_IMAGE} -lc 'rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; ldconfig -p | grep libcuda.so.1; exec python3 /input/vllm_preflight.py'
docker --version
sudo dpkg-query -W -f='${{Package}}=${{Version}}\n' docker.io nvidia-container-toolkit
'''


def validate_frontier_concurrencies(values: tuple[int, ...], max_num_seqs: int) -> tuple[int, ...]:
    if values not in {(1, 8), (1, 8, 16), (16,), (16, 32), (16, 24, 32), (32,), (32, 36), (36,), (40,), (32, 24, 28, 30, 32)}:
        raise VllmSmokeError("frontier concurrencies must be c1,c8, c1,c8,c16, c16, c16,c32, c16,c24,c32, c32,c36, c36, or c32,c24,c28,c30,c32")
    if max_num_seqs < max(values):
        raise VllmSmokeError("max_num_seqs cannot admit the requested frontier")
    return values


def validate_timeout_seconds(value: int) -> int:
    if value <= 0 or value > 4500:
        raise VllmSmokeError("frontier timeout must be positive and no more than 4500 seconds")
    return value


def validate_scientific_owner(scientific_mode: str, environment: dict[str, str] | None = None) -> None:
    environment = os.environ if environment is None else environment
    service_pid = environment.get("SYSTEMD_EXEC_PID")
    if not environment.get("INVOCATION_ID") or service_pid != str(os.getpid()):
        raise VllmSmokeError(f"{scientific_mode} provider mutation requires durable service ownership")


def start_independent_watchdog(
    instance_id: str,
    disk_name: str,
    deadline_epoch: float,
    unit_name: str,
    *,
    unit_manager: str | None = None,
) -> dict[str, object]:
    unit_manager = unit_manager or (
        "user" if os.environ.get("XDG_RUNTIME_DIR") else "system"
    )
    if unit_manager not in {"system", "user"}:
        raise VllmSmokeError("cleanup watchdog unit manager must be system or user")
    manager_flag = f"--{unit_manager}"
    command = [
        "systemd-run", manager_flag, "--no-block", "--collect", f"--unit={unit_name}",
        f"--property=RuntimeMaxSec={max(1, int(deadline_epoch - time.time()) + 60)}s",
        sys.executable, str(HERE / "placement_control.py"), "watchdog", instance_id, disk_name, str(deadline_epoch),
    ]
    launch = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if launch.returncode:
        raise VllmSmokeError(f"independent cleanup watchdog launch failed: {redact_provider_text(launch.stderr)}")
    service = f"{unit_name}.service"
    show = subprocess.run(
        ["systemctl", manager_flag, "show", service, "--property=Id,ActiveState,MainPID,ControlGroup"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    properties = dict(line.split("=", 1) for line in show.stdout.splitlines() if "=" in line)
    main_pid = int(properties.get("MainPID", "0"))
    if show.returncode or properties.get("ActiveState") not in {"active", "activating"} or main_pid <= 0:
        raise VllmSmokeError("independent cleanup watchdog did not become an active systemd service")
    return {
        "unit": service,
        "main_pid": main_pid,
        "control_group": properties.get("ControlGroup"),
        "deadline_epoch": deadline_epoch,
        "unit_manager": unit_manager,
    }


def validate_methodology_contract(
    scientific_mode: str,
    profile: str,
    max_num_seqs: int,
    frontier_concurrencies: tuple[int, ...],
    run_methodology: bool,
) -> None:
    if run_methodology and (
        scientific_mode != "awq"
        or profile != "l40s-awq"
        or max_num_seqs != 32
        or frontier_concurrencies != (32,)
    ):
        raise VllmSmokeError(
            "methodology mode requires the L40S AWQ exact c32 internal control"
        )


def build_container_command(spec_hash: str, deadline_epoch: int, dtype: str = "bfloat16", max_num_batched_tokens: int = 32768, max_num_seqs: int = 8, frontier_concurrencies: tuple[int, ...] = (1, 8), decode_block_n: int = 32, decode_num_stages: int = 2, num_kv_splits: int = 4, kv_cache_dtype: str = "auto", scientific_mode: str = "awq", max_model_len: int = 32768, native_mtp: bool = False, exit35_mode: bool = False, moe_top2_no_shared: bool = False, ngram_prompt_lookup: bool = False, head_shared_w4: bool = False, selective_w4_scope: str = "combined", server_health_timeout_seconds: int = 360, run_methodology: bool = False) -> list[str]:
    if scientific_mode not in {"awq", "bf16-v2-quality"}:
        raise VllmSmokeError("unknown scientific mode")
    bf16 = scientific_mode == "bf16-v2-quality"
    if exit35_mode and bf16:
        raise VllmSmokeError("exit35 mode requires AWQ mode")
    if moe_top2_no_shared and bf16:
        raise VllmSmokeError("moe top2/no-shared mode requires AWQ mode")
    if selective_w4_scope not in VALID_SCOPES:
        raise VllmSmokeError("unknown selective-W4 scope")
    if selective_w4_scope != "combined" and not head_shared_w4:
        raise VllmSmokeError("an isolated selective-W4 scope requires selective-W4 mode")
    if ngram_prompt_lookup and (bf16 or native_mtp or exit35_mode or moe_top2_no_shared or max_num_seqs != 16 or frontier_concurrencies != (16,)):
        raise VllmSmokeError("ngram prompt lookup requires AWQ L40S c16 only")
    model_path = "/workspace/model-bf16" if bf16 else "/workspace/model-awq"
    manifest_path = f"{model_path}/model-files.sha256"
    if not bf16:
        frontier_concurrencies = validate_frontier_concurrencies(frontier_concurrencies, max_num_seqs)
    elif frontier_concurrencies != (1,) or max_num_seqs != 1:
        raise VllmSmokeError("bf16-v2-quality requires c1 and one sequence")
    return [
        "sudo", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "--shm-size=24g",
        "--cap-add", "SYS_NICE", "-v", "/home/glmrunner/input:/input:ro", "-v", "/workspace:/workspace",
        "-e", f"EXPERIMENT_SPEC_SHA256={spec_hash}", "-e", f"CAMPAIGN_DEADLINE_EPOCH={deadline_epoch}",
        "-e", "VLLM_RPC_TIMEOUT=1800000",
        "-e", f"VLLM_DTYPE={dtype}",
        "-e", f"VLLM_MAX_NUM_BATCHED_TOKENS={max_num_batched_tokens}",
        "-e", f"VLLM_MAX_NUM_SEQS={max_num_seqs}",
        "-e", f"VLLM_FRONTIER_CONCURRENCIES={','.join(str(value) for value in frontier_concurrencies)}",
        "-e", f"VLLM_DECODE_BLOCK_N={decode_block_n}",
        "-e", f"VLLM_DECODE_NUM_STAGES={decode_num_stages}",
        "-e", f"VLLM_NUM_KV_SPLITS={num_kv_splits}",
        "-e", f"VLLM_KV_CACHE_DTYPE={kv_cache_dtype}",
        "-e", f"VLLM_SCIENTIFIC_MODE={scientific_mode}",
        "-e", f"VLLM_EXIT35_MODE={'1' if exit35_mode else '0'}",
        "-e", f"VLLM_NGRAM_PROMPT_LOOKUP={'1' if ngram_prompt_lookup else '0'}",
        "-e", f"VLLM_RUN_METHODOLOGY={'1' if run_methodology else '0'}",
        "-e", f"GLM_MOE_TOP2_NO_SHARED={'1' if moe_top2_no_shared else '0'}",
        "-e", f"GLM_HEAD_SHARED_W4={'1' if head_shared_w4 else '0'}",
        "-e", f"GLM_SELECTIVE_W4_SCOPE={selective_w4_scope}",
        "-e", f"GLM_MOE_TOP2_NO_SHARED_PATCH_SHA256={MOE_TOP2_NO_SHARED_PATCH_SHA256 if moe_top2_no_shared else ''}",
        "-e", "VLLM_EXIT35_PREFILL_THRESHOLD=64",
        "-e", "VLLM_NATIVE_MTP=1" if native_mtp else "VLLM_NATIVE_MTP=0",
        "-e", f"MODEL_REVISION={BF16_MODEL_REVISION}",
        "-e", f"MODEL_MANIFEST_PATH={manifest_path}",
        "-e", f"VLLM_MAX_MODEL_LEN={max_model_len}",
        "-e", f"VLLM_SERVER_HEALTH_TIMEOUT_SECONDS={server_health_timeout_seconds}",
        "--entrypoint", "bash", RUNTIME_IMAGE, "-lc",
        "rm -f /etc/ld.so.conf.d/00-cuda-compat.conf /etc/ld.so.conf.d/cuda-compat.conf; ldconfig; exec bash /input/remote_vllm_awq_smoke.sh",
    ]


def run(output_dir: Path, name: str, key: Path, public_key: Path, model_dir: Path, tokenizer_dir: Path, spec_hash: str, keep_instance_after_result: bool = False, num_kv_splits: int = 4, max_num_seqs: int = 8, frontier_concurrencies: tuple[int, ...] = (1, 8), absolute_timeout_seconds: int = 3600, background_arm_envelope_seconds: float | None = None, kv_cache_dtype: str = "auto", scientific_mode: str = "awq", profile: str = "h100-bf16", native_mtp: bool = False, exit35_mode: bool = False, moe_top2_no_shared: bool = False, ngram_prompt_lookup: bool = False, head_shared_w4: bool = False, selective_w4_scope: str = "combined", repair_window_seconds: int = 0, run_methodology: bool = False, allow_deferred_absolute_quality_failure: bool = False) -> int:
    global PLATFORM, PRESET, DISK_GIB, HOURLY_RATE_USD, DISK_HOURLY_RATE_USD
    if profile == "l40s-awq":
        if scientific_mode != "awq":
            raise VllmSmokeError("l40s-awq requires awq mode")
        PLATFORM, PRESET, DISK_GIB, HOURLY_RATE_USD, DISK_HOURLY_RATE_USD = L40S_AWQ_PROFILE
    elif profile != "h100-bf16":
        raise VllmSmokeError("unknown profile")
    validate_methodology_contract(
        scientific_mode,
        profile,
        max_num_seqs,
        frontier_concurrencies,
        run_methodology,
    )
    validate_scientific_owner(scientific_mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "summary.json").exists():
        raise VllmSmokeError("completed output directory already exists")
    if scientific_mode == "bf16-v2-quality":
        max_num_seqs, frontier_concurrencies = 1, (1,)
    if moe_top2_no_shared and (scientific_mode != "awq" or profile != "l40s-awq" or max_num_seqs != 16 or frontier_concurrencies != (16,)):
        raise VllmSmokeError("moe top2/no-shared mode requires l40s-awq c16 only")
    if ngram_prompt_lookup and (scientific_mode != "awq" or profile != "l40s-awq" or native_mtp or exit35_mode or moe_top2_no_shared or max_num_seqs != 16 or frontier_concurrencies != (16,)):
        raise VllmSmokeError("ngram prompt lookup requires AWQ L40S c16 only")
    if selective_w4_scope not in VALID_SCOPES:
        raise VllmSmokeError("unknown selective-W4 scope")
    if selective_w4_scope != "combined" and not head_shared_w4:
        raise VllmSmokeError("an isolated selective-W4 scope requires selective-W4 mode")
    frontier_concurrencies = validate_frontier_concurrencies(frontier_concurrencies, max_num_seqs) if scientific_mode == "awq" else frontier_concurrencies
    absolute_timeout_seconds = validate_timeout_seconds(absolute_timeout_seconds)
    if not 0 <= repair_window_seconds <= 600:
        raise VllmSmokeError("repair window must be between zero and 600 seconds")
    if background_arm_envelope_seconds is not None and not 0 < background_arm_envelope_seconds <= absolute_timeout_seconds:
        raise VllmSmokeError("background arm envelope must be positive and no more than the experiment timeout")
    identities = validate_bf16_model(model_dir) if scientific_mode == "bf16-v2-quality" else validate_local_model(model_dir)
    remote_script = HERE / "remote_vllm_awq_smoke.sh"
    batch_runner = HERE / "vllm_batched_runner.py"
    methodology_runner = HERE / "vllm_methodology_runner.py"
    kernel_patcher = HERE / "vllm_decode_kernel_patch.py"
    exit35_patcher = HERE.parent.parent / "research_lab" / "projects" / "sequence_early_exit_architecture" / "exit35_vllm_source_patch.py"
    moe_patcher = MOE_TOP2_NO_SHARED_PATCH
    head_shared_binder = HERE.parent.parent / "research_lab" / "projects" / "full47_official_selective_w4_cuda_endpoint" / "official_head_shared_w4_bind.py"
    head_shared_cuda_oracle = HERE.parent.parent / "research_lab" / "projects" / "full47_official_selective_w4_cuda_endpoint" / "official_head_shared_w4_cuda_oracle.py"
    preflight = HERE / "vllm_preflight.py"
    quality_dir = HERE.parent / "quality"
    v2_dir = HERE.parent.parent / "research_lab" / "projects" / "quality_gate_calibration" / "executable_development_v2"
    v2_runner = HERE / "vllm_v2_quality_runner.py"
    required_tokenizer = [tokenizer_dir / name for name in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")]
    required_quality = required_quality_files(quality_dir)
    required_v2 = [v2_dir / "MANIFEST.json", v2_dir / "development.jsonl", v2_runner]
    if not all(path.is_file() for path in [remote_script, batch_runner, methodology_runner, kernel_patcher, preflight, *required_tokenizer, *required_quality, *required_v2, exit35_patcher, *([moe_patcher] if moe_top2_no_shared else []), *([head_shared_binder, head_shared_cuda_oracle] if head_shared_w4 else [])]):
        raise VllmSmokeError("batched vLLM inputs are incomplete")
    if moe_top2_no_shared and hashlib.sha256(moe_patcher.read_bytes()).hexdigest() != MOE_TOP2_NO_SHARED_PATCH_SHA256:
        raise VllmSmokeError("moe top2/no-shared patch identity mismatch")
    events = output_dir / "events.jsonl"
    started = time.time()
    deadline = started + absolute_timeout_seconds
    science_deadline = deadline - ARTIFACT_RESERVE_SECONDS
    instance_id = None
    disk_name = name + "-boot"
    outcome = "FAIL"
    artifact_hash = None
    manifest_files = 0
    allocation_result = None
    methodology_result = None
    methodology_pass = None
    control_useful_gpu_seconds = None
    methodology_useful_seconds = None
    measured_useful_gpu_seconds = None
    background_pass = False
    retain_after_result = False
    if list_items("instance"):
        raise VllmSmokeError("active instances exist")
    emit(events, "stock_control", instance_count=0, **identities)
    (output_dir / "provider-request.json").write_text(json.dumps({
        "name": name, "platform": PLATFORM, "preset": PRESET, "purchase_model": "preemptible_stop",
        "boot_disk_gib": DISK_GIB, "base_container_image": IMAGE,
        "derived_runtime_image": RUNTIME_IMAGE, "transformers_revision": TRANSFORMERS_REVISION,
        "hourly_rate_usd_vendor_calculator": HOURLY_RATE_USD,
        "disk_hourly_rate_usd_vendor_calculator": DISK_HOURLY_RATE_USD,
        "absolute_timeout_seconds": absolute_timeout_seconds,
        "artifact_reserve_seconds": ARTIFACT_RESERVE_SECONDS,
        "repair_window_seconds": repair_window_seconds,
        "scientific_mode": scientific_mode,
        "ngram_prompt_lookup": ngram_prompt_lookup,
        "moe_top2_no_shared": moe_top2_no_shared,
        "selective_w4_scope": selective_w4_scope if head_shared_w4 else None,
        "moe_top2_no_shared_patch_sha256": MOE_TOP2_NO_SHARED_PATCH_SHA256 if moe_top2_no_shared else None,
        "background_arm_envelope_seconds": background_arm_envelope_seconds,
        "max_total_cost_usd": (HOURLY_RATE_USD + DISK_HOURLY_RATE_USD) * absolute_timeout_seconds / 3600,
        **identities,
    }, indent=2, sort_keys=True) + "\n")
    try:
        with measured_phase(events, "provider_create"):
            create = build_create_command(name=name, disk_name=disk_name, cloud_init=make_cloud_init(public_key.read_text()), disk_gib=DISK_GIB, platform=PLATFORM, preset=PRESET, preemptible=True)
            proc = subprocess.run(create, capture_output=True, text=True, timeout=180)
            write_create_diagnostic(output_dir, proc)
            instance_id, reconciled_nonzero_exit = resolve_created_instance(proc, name)
        emit(
            events,
            "instance_created",
            instance_id=instance_id,
            create_returncode=proc.returncode,
            reconciled_nonzero_exit=reconciled_nonzero_exit,
        )
        watchdog = start_independent_watchdog(instance_id, disk_name, deadline, f"{name}-watchdog")
        emit(events, "independent_watchdog_started", **watchdog)
        with measured_phase(events, "ssh_readiness"):
            ip = None
            while time.time() < min(deadline, started + 600):
                payload = get_instance(instance_id)
                if payload is None:
                    raise VllmSmokeError("instance disappeared before readiness")
                ip = extract_public_ipv4(payload)
                if ip:
                    break
                time.sleep(5)
            if not ip:
                raise VllmSmokeError("public IP readiness exceeded 600 seconds")
            wait_ssh(ip, key, min(deadline, started + 600))
        emit(events, "ssh_ready", elapsed_seconds=round(time.time() - started, 3))
        if run_ssh(ip, key, "mkdir -p /home/glmrunner/input/model-config-only", timeout=30).returncode:
            raise VllmSmokeError("remote model-config preflight directory creation failed")
        scp_to(ip, key, [preflight], "/home/glmrunner/input/")
        scp_to(ip, key, [model_dir / "config.json"], "/home/glmrunner/input/model-config-only/")
        with measured_phase(events, "runtime_bootstrap"):
            bootstrap = run_ssh(ip, key, "bash -s", timeout=1800, input_text=build_host_bootstrap())
            (output_dir / "host-bootstrap.stdout.log").write_text(bootstrap.stdout)
            (output_dir / "host-bootstrap.stderr.log").write_text(bootstrap.stderr)
            if bootstrap.returncode:
                raise VllmSmokeError("vLLM host bootstrap failed")
        emit(events, "cuda_and_transformers_preflight_passed", transformers_revision=TRANSFORMERS_REVISION)
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory)
            staged = staging / remote_script.name
            shutil.copy2(remote_script, staged)
            shutil.copy2(batch_runner, staging / batch_runner.name)
            shutil.copy2(methodology_runner, staging / methodology_runner.name)
            shutil.copy2(kernel_patcher, staging / kernel_patcher.name)
            if exit35_mode: shutil.copy2(exit35_patcher, staging / exit35_patcher.name)
            if moe_top2_no_shared: shutil.copy2(moe_patcher, staging / moe_patcher.name)
            if head_shared_w4: shutil.copy2(head_shared_binder, staging / head_shared_binder.name)
            if head_shared_w4: shutil.copy2(head_shared_cuda_oracle, staging / head_shared_cuda_oracle.name)
            if scientific_mode == "bf16-v2-quality": shutil.copy2(v2_runner, staging / v2_runner.name)
            control_responses = staging / "bf16-control-responses.jsonl"
            with tarfile.open(HERE.parent / "allocations" / "nebius_h100_complete_stock_v13" / "stock_no_cache_fcfs-artifact.tar.gz", "r:gz") as bundle:
                member = next(row for row in bundle.getmembers() if row.name.endswith("/quality-stock_no_cache_fcfs-responses.jsonl"))
                handle = bundle.extractfile(member)
                if handle is None: raise VllmSmokeError("BF16 control responses missing")
                control_responses.write_bytes(handle.read())
            if run_ssh(ip, key, "mkdir -p /home/glmrunner/input/tokenizer /home/glmrunner/input/quality /home/glmrunner/input/v2", timeout=30).returncode:
                raise VllmSmokeError("remote input directory creation failed")
            extra = [staging / v2_runner.name] if scientific_mode == "bf16-v2-quality" else []
            if exit35_mode: extra.append(staging / exit35_patcher.name)
            if moe_top2_no_shared: extra.append(staging / moe_patcher.name)
            if head_shared_w4: extra.append(staging / head_shared_binder.name)
            if head_shared_w4: extra.append(staging / head_shared_cuda_oracle.name)
            scp_to(ip, key, [staged, staging / batch_runner.name, staging / methodology_runner.name, staging / kernel_patcher.name, control_responses, *extra], "/home/glmrunner/input/")
            scp_to(ip, key, required_tokenizer, "/home/glmrunner/input/tokenizer/")
            scp_to(ip, key, required_quality, "/home/glmrunner/input/quality/")
            if scientific_mode == "bf16-v2-quality": scp_to(ip, key, required_v2[:2], "/home/glmrunner/input/v2/")
        probe_hash = probe_transfer(ip, key)
        emit(events, "tiny_transfer_probe_passed", sha256=probe_hash)
        with measured_phase(events, "checkpoint_transfer"):
            derived_transfer_timeout = transfer_timeout_seconds(int(identities["model_weight_bytes"]))
            available_transfer_seconds = int(science_deadline - time.time() - 300)
            if available_transfer_seconds < 60:
                raise VllmSmokeError("insufficient retained session time for checkpoint staging and model load")
            transfer_result = transfer_checkpoint(
                ip,
                key,
                model_dir,
                "/workspace/model-bf16" if scientific_mode == "bf16-v2-quality" else "/workspace/model-awq",
                timeout_seconds=min(derived_transfer_timeout, available_transfer_seconds),
            )
        emit(events, "checkpoint_transfer_completed", **transfer_result.__dict__)
        emit(events, "verified_local_awq_transferred", elapsed_seconds=round(transfer_result.elapsed_seconds, 3), reusable_bytes=transfer_result.reusable_bytes)
        if time.time() >= science_deadline:
            raise VllmSmokeError("artifact-reserved science deadline elapsed before model execution")
        with measured_phase(events, "scientific_workload") as scientific_phase:
            remote = run_ssh(ip, key, build_container_command(spec_hash, int(science_deadline), max_num_batched_tokens=43008 if scientific_mode == "bf16-v2-quality" else 65536, max_num_seqs=max_num_seqs, frontier_concurrencies=frontier_concurrencies, num_kv_splits=num_kv_splits, kv_cache_dtype=kv_cache_dtype, scientific_mode=scientific_mode, max_model_len=43008 if scientific_mode == "bf16-v2-quality" else 32768, native_mtp=native_mtp, exit35_mode=exit35_mode, moe_top2_no_shared=moe_top2_no_shared, ngram_prompt_lookup=ngram_prompt_lookup, head_shared_w4=head_shared_w4, selective_w4_scope=selective_w4_scope, server_health_timeout_seconds=900 if scientific_mode == "bf16-v2-quality" else 360, run_methodology=run_methodology), timeout=max(60, int(deadline - time.time())))
            scientific_phase["outcome"] = "PASS" if remote.returncode == 0 else "FAIL"
            scientific_phase["returncode"] = remote.returncode
        (output_dir / "remote.stdout.log").write_text(remote.stdout)
        (output_dir / "remote.stderr.log").write_text(remote.stderr)
        with measured_phase(events, "artifact_retrieval"):
            archive = output_dir / "vllm-awq-batch.tar.gz"
            sidecar = output_dir / "vllm-awq-batch.remote.sha256"
            public = "public-bf16-v2-quality" if scientific_mode == "bf16-v2-quality" else "public-vllm-awq-batch"
            scp_from(ip, key, f"/workspace/{public}/vllm-awq-batch.tar.gz", archive)
            scp_from(ip, key, f"/workspace/{public}/vllm-awq-batch.tar.gz.sha256", sidecar)
            artifact_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            if artifact_hash != sidecar.read_text().split()[0]:
                raise VllmSmokeError("remote/local artifact hash mismatch")
            manifest_files = verify_internal_manifest(archive)
            allocation_result = json.loads(extract_member(archive, "/allocation-result.json"))
            control_useful_gpu_seconds = useful_gpu_seconds(allocation_result)
            if run_methodology:
                methodology_result = json.loads(extract_member(archive, "/aa-methodology-result.json"))
                methodology_pass = methodology_completion_pass(methodology_result)
                methodology_useful_seconds = methodology_useful_gpu_seconds(methodology_result)
            useful_parts = [value for value in (control_useful_gpu_seconds, methodology_useful_seconds) if value is not None]
            measured_useful_gpu_seconds = round(sum(useful_parts), 3) if useful_parts else None
        if allocation_has_harness_error(allocation_result):
            raise VllmSmokeError("typed allocation result contains a harness error")
        if run_methodology and methodology_pass is not True:
            raise VllmSmokeError("mandatory methodology result is incomplete or failed")
        outcome, background_pass = execution_outcome(
            remote.returncode,
            allocation_result,
            background_arm_envelope_seconds,
            allow_deferred_absolute_quality_failure=allow_deferred_absolute_quality_failure,
        )
        emit(
            events,
            "artifact_retrieved",
            sha256=artifact_hash,
            manifest_files=manifest_files,
            outcome=outcome,
            background_pass=background_pass,
            methodology_pass=methodology_pass,
            remote_returncode=remote.returncode,
        )
        retain_after_result = keep_instance_after_result and background_pass
    except Exception as error:
        emit(events, "experiment_error", error_type=type(error).__name__, message=str(error))
        if instance_id is not None and allocation_result is None:
            hold_for_repair_decision(output_dir, events, deadline, repair_window_seconds)
    finally:
        cleanup_started = time.monotonic()
        if instance_id is None:
            try: instance_id = find_named_instance(name)
            except Exception: instance_id = None
        delete_requested = time.time()
        if retain_after_result:
            absent = False
            emit(events, "instance_retained_for_next_preregistered_experiment", instance_id=instance_id)
        elif instance_id:
            delete_instance(instance_id)
            absent = wait_absent(instance_id, time.time() + 240)
        else:
            absent = True
        if not retain_after_result:
            for disk in list_items("disk"):
                if metadata_name(disk) == disk_name and metadata_id(disk): delete_disk(metadata_id(disk))
        final_instances = list_items("instance")
        final_disks = list_items("disk")
        cleanup = absent and not any(metadata_name(row) == name for row in final_instances) and not any(metadata_name(row) == disk_name for row in final_disks)
        elapsed = max(0.0, delete_requested - started)
        compute_cost = elapsed / 3600 * HOURLY_RATE_USD
        disk_cost = elapsed / 3600 * DISK_HOURLY_RATE_USD
        (output_dir / "summary.json").write_text(json.dumps({
            "outcome": outcome, "cleanup_pass": cleanup, "instance_id": instance_id,
            "remote_returncode": remote.returncode if remote is not None else None,
            "background_pass": background_pass,
            "background_arm_envelope_seconds": background_arm_envelope_seconds,
            "retained_for_next_experiment": retain_after_result,
            "allocation_seconds": round(elapsed, 3), "compute_cost_usd_derived": round(compute_cost, 9),
            "disk_cost_usd_derived": round(disk_cost, 9), "cost_usd_derived": round(compute_cost + disk_cost, 9),
            "cost_basis": "measured exposure at authenticated Nebius preemptible VM and disk rates; public IPv4/egress excluded; invoice pending",
            "artifact_sha256": artifact_hash, "manifest_file_count": manifest_files, "allocation_result": allocation_result,
            "methodology_pass": methodology_pass,
            "control_useful_gpu_seconds": control_useful_gpu_seconds,
            "methodology_useful_gpu_seconds": methodology_useful_seconds,
            "useful_gpu_seconds": measured_useful_gpu_seconds,
            "final_instance_count": len(final_instances), "final_disk_count": len(final_disks),
            "ended_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        }, indent=2, sort_keys=True) + "\n")
        emit(
            events,
            "cleanup_verified",
            cleanup_pass=cleanup,
            instance_get_not_found=absent,
            elapsed_seconds=round(time.monotonic() - cleanup_started, 3),
            useful_gpu_seconds=measured_useful_gpu_seconds,
        )
    return 0 if outcome == "PASS" and (cleanup or retain_after_result) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-public-key", type=Path, required=True)
    parser.add_argument("--local-model-dir", type=Path, required=True)
    parser.add_argument("--reference-tokenizer-dir", type=Path, required=True)
    parser.add_argument("--experiment-spec-sha256", required=True)
    parser.add_argument("--keep-instance-after-result", action="store_true")
    parser.add_argument("--num-kv-splits", type=int, choices=(4, 8, 16), default=4)
    parser.add_argument("--max-num-seqs", type=int, choices=(8, 16, 32, 36, 64), default=8)
    parser.add_argument("--frontier-concurrencies", default="1,8")
    parser.add_argument("--absolute-timeout-seconds", type=int, default=3600)
    parser.add_argument("--background-arm-envelope-seconds", type=float)
    parser.add_argument("--kv-cache-dtype", choices=("auto", "fp8_e4m3"), default="auto")
    parser.add_argument("--scientific-mode", choices=("awq", "bf16-v2-quality"), default="awq")
    parser.add_argument("--profile", choices=("h100-bf16", "l40s-awq"), default="h100-bf16")
    parser.add_argument("--native-mtp", action="store_true")
    parser.add_argument("--exit35-mode", action="store_true")
    parser.add_argument("--moe-top2-no-shared", action="store_true")
    parser.add_argument("--ngram-prompt-lookup", action="store_true")
    parser.add_argument("--head-shared-w4", action="store_true")
    parser.add_argument("--selective-w4-scope", choices=VALID_SCOPES, default="combined")
    parser.add_argument("--repair-window-seconds", type=int, default=0)
    parser.add_argument("--run-methodology", action="store_true")
    args = parser.parse_args()
    try:
        concurrencies = tuple(int(value) for value in args.frontier_concurrencies.split(","))
    except ValueError as error:
        raise VllmSmokeError("frontier concurrencies must be comma-separated integers") from error
    return run(args.output_dir, args.name, args.ssh_key, args.ssh_public_key, args.local_model_dir, args.reference_tokenizer_dir, args.experiment_spec_sha256, args.keep_instance_after_result, args.num_kv_splits, args.max_num_seqs, concurrencies, args.absolute_timeout_seconds, args.background_arm_envelope_seconds, args.kv_cache_dtype, args.scientific_mode, args.profile, args.native_mtp, args.exit35_mode, args.moe_top2_no_shared, args.ngram_prompt_lookup, args.head_shared_w4, args.selective_w4_scope, args.repair_window_seconds, args.run_methodology)


if __name__ == "__main__":
    raise SystemExit(main())
