#!/usr/bin/env python3
"""Durable top4/top3/top4 retained L40S experiment owner."""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path("/root/workspace/research/lab/experiments/glm47flash")
NEBIUS = ROOT / "campaign_100/nebius"
PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(NEBIUS))
import vllm_smoke_control as smoke
import vllm_recover_existing as recover
from placement_control import delete_disk, delete_instance, list_items, metadata_id, metadata_name, wait_absent

MODEL = Path("/root/.cache/glm47flash-awq-ab31d120")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUB = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")
ARM_ENVELOPE_SECONDS = 300
ARTIFACT_AND_CLEANUP_RESERVE_SECONDS = smoke.ARTIFACT_RESERVE_SECONDS + 240


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def background_valid(summary: Path) -> bool:
    try:
        value = json.loads(summary.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return value.get("retained_for_next_experiment") is True and smoke.background_completion_pass(
        value.get("allocation_result"), ARM_ENVELOPE_SECONDS, allow_deferred_absolute_quality_failure=True
    )


def throughput(summary: Path) -> float | None:
    try:
        profiles = json.loads(summary.read_text())["allocation_result"]["performance"]["profiles"]
        row = next(row for row in profiles if row.get("concurrency") == 32)
        return float(row["output_tokens_per_second_conservative"])
    except (OSError, json.JSONDecodeError, KeyError, StopIteration, TypeError, ValueError):
        return None


def top3_gate(pre: float | None, candidate: float | None, post: float | None) -> bool:
    if None in (pre, candidate, post):
        return False
    anchor = (pre + post) / 2
    return abs(pre - post) / anchor <= 0.03 and candidate >= 606.355 and candidate >= 1.03 * anchor


def cleanup(instance_id: str, name: str) -> bool:
    delete_instance(instance_id)
    absent = wait_absent(instance_id, time.time() + 240)
    for disk in list_items("disk"):
        if metadata_name(disk) == name + "-boot" and metadata_id(disk):
            delete_disk(metadata_id(disk))
    return absent and not list_items("instance") and not list_items("disk")


def recovery_args(out: Path, name: str, instance_id: str, deadline: float, spec: str, config: dict, keep: bool):
    value = type("Args", (), {})()
    value.output_dir = out; value.name = name; value.instance_id = instance_id; value.control_summary = None
    value.parent_experiment_id = "full47_top3_shared_c32_direct"; value.session_deadline_epoch = deadline
    value.ssh_key = KEY; value.local_model_dir = MODEL; value.reference_tokenizer_dir = MODEL; value.repair_spec_sha256 = spec
    value.config_override = Path(config["path"]); value.config_override_sha256 = config["sha256"]
    value.reuse_staged_runtime = True; value.reuse_staged_runtime_and_checkpoint = True; value.keep_instance_after_result = keep
    value.dtype = "bfloat16"; value.max_num_batched_tokens = 65536; value.max_num_seqs = 32; value.frontier_concurrencies = "32"
    value.decode_block_n = 32; value.decode_num_stages = 2; value.num_kv_splits = 4; value.kv_cache_dtype = "auto"
    value.repair_window_seconds = 0; value.background_arm_envelope_seconds = ARM_ENVELOPE_SECONDS
    value.allow_deferred_absolute_quality_failure = True
    return value


def main() -> int:
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise SystemExit("durable systemd main required")
    deadline = time.time() + 3000
    out = PROJECT / "artifacts" / ("l40s_top3_shared_c32_" + time.strftime("%Y%m%d_r1", time.gmtime()))
    configs = out / "configs"; configs.mkdir(parents=True, exist_ok=False)
    stock_bytes = (MODEL / "config.json").read_bytes(); stock = json.loads(stock_bytes)
    binding = {}
    for label, topk in (("top4", 4), ("top3", 3)):
        path = configs / f"{label}_shared_config.json"
        path.write_bytes(stock_bytes if label == "top4" else (json.dumps({**stock, "num_experts_per_tok": topk}, sort_keys=True, indent=2) + "\n").encode())
        value = json.loads(path.read_text())
        binding[label] = {"path": str(path), "sha256": sha(path), "num_experts_per_tok": topk, "n_shared_experts": value["n_shared_experts"]}
    packet = {"checkpoint": str(MODEL), "checkpoint_config_sha256": sha(MODEL / "config.json"), "configs": binding, "sequence": ["top4_shared_c32_pre", "top3_shared_c32", "top4_shared_c32_post"], "deadline_epoch": deadline}
    (out / "LAUNCH_PACKET.json").write_text(json.dumps(packet, sort_keys=True, indent=2) + "\n")
    spec = sha(out / "LAUNCH_PACKET.json")
    name = "glm47-top3-shared-c32-20260716-r1"
    smoke.run(out / "top4_shared_c32_pre", name, key=KEY, public_key=PUB, model_dir=MODEL, tokenizer_dir=MODEL, spec_hash=spec, keep_instance_after_result=True, num_kv_splits=4, max_num_seqs=32, frontier_concurrencies=(32,), absolute_timeout_seconds=3000, background_arm_envelope_seconds=ARM_ENVELOPE_SECONDS, kv_cache_dtype="auto", scientific_mode="awq", profile="l40s-awq", allow_deferred_absolute_quality_failure=True)
    pre_summary = out / "top4_shared_c32_pre/summary.json"
    if not background_valid(pre_summary):
        return 1
    instance_id = json.loads(pre_summary.read_text())["instance_id"]
    for label, cfg, keep in (("top3_shared_c32", "top3", True), ("top4_shared_c32_post", "top4", True)):
        if time.time() + ARM_ENVELOPE_SECONDS + ARTIFACT_AND_CLEANUP_RESERVE_SECONDS > deadline:
            cleanup(instance_id, name); return 1
        recover.run(recovery_args(out / label, name, instance_id, deadline, spec, binding[cfg], keep))
        if not background_valid(out / label / "summary.json"):
            cleanup(instance_id, name); return 1
    pre, candidate, post = (throughput(out / f"{label}/summary.json") for label in ("top4_shared_c32_pre", "top3_shared_c32", "top4_shared_c32_post"))
    cleanup(instance_id, name)
    return 0 if top3_gate(pre, candidate, post) else 1


if __name__ == "__main__":
    raise SystemExit(main())
