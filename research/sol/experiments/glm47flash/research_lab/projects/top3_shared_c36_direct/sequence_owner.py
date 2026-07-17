#!/usr/bin/env python3
"""Durable owner for the admitted top-3/shared c32/c36/c40 session."""
import hashlib
import json
import os
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path("/root/workspace/research/sol/experiments/glm47flash")
NEBIUS = ROOT / "campaign_100/nebius"
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(NEBIUS))
import vllm_smoke_control as smoke
import vllm_recover_existing as recover
from placement_control import delete_disk, delete_instance, list_items, metadata_id, metadata_name, wait_absent

MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUB = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")
TIMEOUT = 3300
RESERVE = 600
MEMORY_LIMIT_MIB = 45556
KV_INCREMENT_MIB = 4 * 9216 * 47 * (512 + 256) * 2 / 1024**2


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def profile(summary: Path, concurrency: int) -> dict | None:
    try:
        profiles = json.loads(summary.read_text())["allocation_result"]["performance"]["profiles"]
        return next(row for row in profiles if row.get("concurrency") == concurrency)
    except (OSError, json.JSONDecodeError, KeyError, StopIteration, TypeError):
        return None


def background_valid(summary: Path, concurrencies: tuple[int, ...]) -> bool:
    try:
        value = json.loads(summary.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if value.get("retained_for_next_experiment") is not True:
        return False
    for concurrency in concurrencies:
        row = profile(summary, concurrency)
        if not row or not smoke.background_completion_pass(
            {"semantic": value["allocation_result"].get("semantic"), "quality": value["allocation_result"].get("quality"), "performance": {"profiles": [row]}},
            300,
            allow_deferred_absolute_quality_failure=True,
        ):
            return False
    return True


def rate(summary: Path, concurrency: int) -> float | None:
    row = profile(summary, concurrency)
    try:
        return float(row["output_tokens_per_second_conservative"])
    except (TypeError, KeyError, ValueError):
        return None


def peak_memory_mib(summary: Path) -> float | None:
    try:
        archive = json.loads(summary.read_text()).get("artifact_sha256")
        if not archive:
            return None
        path = summary.parent / "vllm-awq-batch.tar.gz"
        with tarfile.open(path, "r:gz") as bundle:
            member = next(row for row in bundle.getmembers() if row.name.endswith("/telemetry.csv"))
            handle = bundle.extractfile(member)
            if handle is None:
                return None
            values = []
            for line in handle.read().decode(errors="replace").splitlines():
                fields = [part.strip() for part in line.split(",")]
                if len(fields) >= 7:
                    values.append(float(fields[6]))
            return max(values) if values else None
    except (OSError, KeyError, StopIteration, tarfile.TarError, ValueError):
        return None


def c36_pass(summary: Path) -> bool:
    c32, c36, peak = rate(summary, 32), rate(summary, 36), peak_memory_mib(summary)
    return bool(background_valid(summary, (32, 36)) and c32 is not None and c36 is not None and peak is not None and c32 >= .97 * 644.318005 and c36 >= 663.647545 and c36 >= 1.03 * c32 and 46068 - peak >= 512)


def c40_admitted(summary: Path) -> bool:
    peak = peak_memory_mib(summary)
    return c36_pass(summary) and peak is not None and peak + KV_INCREMENT_MIB <= MEMORY_LIMIT_MIB


def cleanup(instance_id: str, name: str) -> bool:
    delete_instance(instance_id)
    absent = wait_absent(instance_id, time.time() + 240)
    for disk in list_items("disk"):
        if metadata_name(disk) == name + "-boot" and metadata_id(disk):
            delete_disk(metadata_id(disk))
    return absent and not list_items("instance") and not list_items("disk")


def recovery_args(out: Path, name: str, instance_id: str, deadline: float, spec: str, config: dict, max_seqs: int, concurrencies: str, keep: bool):
    value = type("Args", (), {})()
    value.output_dir = out; value.name = name; value.instance_id = instance_id; value.control_summary = None
    value.parent_experiment_id = "top3_shared_c36_direct"; value.session_deadline_epoch = deadline
    value.ssh_key = KEY; value.local_model_dir = MODEL; value.reference_tokenizer_dir = MODEL; value.repair_spec_sha256 = spec
    value.config_override = Path(config["path"]); value.config_override_sha256 = config["sha256"]
    value.reuse_staged_runtime = True; value.reuse_staged_runtime_and_checkpoint = True; value.keep_instance_after_result = keep
    value.dtype = "bfloat16"; value.max_num_batched_tokens = 65536; value.max_num_seqs = max_seqs; value.frontier_concurrencies = concurrencies
    value.decode_block_n = 32; value.decode_num_stages = 2; value.num_kv_splits = 4; value.kv_cache_dtype = "auto"
    value.repair_window_seconds = 0; value.background_arm_envelope_seconds = 300; value.allow_deferred_absolute_quality_failure = True
    return value


def main() -> int:
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise SystemExit("durable systemd main required")
    started, deadline = time.time(), time.time() + TIMEOUT
    out = PROJECT / "artifacts" / ("l40s_top3_shared_c36_" + time.strftime("%Y%m%d_r1", time.gmtime()))
    configs = out / "configs"; configs.mkdir(parents=True, exist_ok=False)
    stock = json.loads((MODEL / "config.json").read_text()); top3 = {**stock, "num_experts_per_tok": 3}
    config = configs / "top3_shared_config.json"; config.write_text(json.dumps(top3, sort_keys=True, indent=2) + "\n")
    binding = {"path": str(config), "sha256": sha(config), "num_experts_per_tok": 3, "n_shared_experts": top3["n_shared_experts"]}
    budget = {"measured_setup_and_bootstrap_seconds": 1250.081, "measured_retained_arm_seconds": 366.191, "measured_cleanup_seconds": 52.065, "c40_recovery_plus_arm_reserve_seconds": RESERVE, "reachable_total_seconds": 1250.081 + 366.191 + RESERVE + 52.065, "limit_seconds": TIMEOUT, "metered_rate_usd_per_hour": 0.8581222, "maximum_cost_usd": TIMEOUT / 3600 * 0.8581222}
    packet = {"checkpoint": str(MODEL), "checkpoint_config_sha256": sha(MODEL / "config.json"), "config": binding, "sequence": ["bootstrap_maxseq36", "top3_shared_c32_c36", "top3_shared_c40"], "conditional": {"name": "TOP3_C36_PASS_AND_C40_MEMORY_ADMISSION", "max_predicted_peak_mib": MEMORY_LIMIT_MIB, "kv_increment_mib": KV_INCREMENT_MIB, "remaining_seconds": RESERVE}, "budget": budget, "deadline_epoch": deadline}
    (out / "LAUNCH_PACKET.json").write_text(json.dumps(packet, sort_keys=True, indent=2) + "\n")
    spec, name = sha(out / "LAUNCH_PACKET.json"), "glm47-top3-shared-c36-20260716-r1"
    smoke.run(out / "bootstrap_maxseq36", name, key=KEY, public_key=PUB, model_dir=MODEL, tokenizer_dir=MODEL, spec_hash=spec, keep_instance_after_result=True, num_kv_splits=4, max_num_seqs=36, frontier_concurrencies=(32,), absolute_timeout_seconds=TIMEOUT, background_arm_envelope_seconds=300, kv_cache_dtype="auto", scientific_mode="awq", profile="l40s-awq", allow_deferred_absolute_quality_failure=True)
    bootstrap = out / "bootstrap_maxseq36/summary.json"
    if not background_valid(bootstrap, (32,)): return 1
    instance_id = json.loads(bootstrap.read_text())["instance_id"]
    primary = out / "top3_shared_c32_c36"
    recover.run(recovery_args(primary, name, instance_id, deadline, spec, binding, 36, "32,36", True))
    primary_summary = primary / "summary.json"
    if not c36_pass(primary_summary): cleanup(instance_id, name); return 0
    if not c40_admitted(primary_summary) or time.time() + RESERVE > deadline:
        cleanup(instance_id, name); return 0
    recover.run(recovery_args(out / "top3_shared_c40", name, instance_id, deadline, spec, binding, 40, "40", False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
