#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
import mla_microbench_control as controller
from placement_control import list_items, metadata_name

IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
PLATFORM = "gpu-h200-sxm"
PRESET = "1gpu-16vcpu-200gb"
RATE_USD = 2.45
DISK_RATE_USD = 0.0097222
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
PRIMARY_BENCH = PROJECT / "h200_bf16_linear_bench.py"
PRIMARY_REMOTE = PROJECT / "remote_h200_bf16_linear_stage.sh"
HEAD_PROJECT = PROJECT.parent / "gemma_l40s_parallel_lm_head_component"
HEAD_BENCH = HEAD_PROJECT / "vllm_parallel_lm_head_bench.py"
HEAD_REMOTE = HEAD_PROJECT / "remote_parallel_lm_head_stage.sh"
STRICT_SECONDS = 0.47201182295214134
LENIENT_SECONDS = 0.47751364375858635


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_log(text: str) -> None:
    with (PROJECT / "RESEARCH_LOG.md").open("a") as handle:
        handle.write(text)


def typed_precreate(output_dir: Path, name: str, final_audit: Path, identity: Path, deadline_epoch: float) -> dict[str, object]:
    audit = json.loads(final_audit.read_text())
    bound = json.loads(identity.read_text())
    instances = [metadata_name(item) for item in list_items("instance")]
    disks = [metadata_name(item) for item in list_items("disk")]
    bootstrap = controller.build_host_bootstrap(IMAGE)
    checks = {
        "durable_owner": bool(os.environ.get("INVOCATION_ID")) and os.environ.get("SYSTEMD_EXEC_PID") == str(os.getpid()),
        "lowercase_rfc1123_name": bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", name)),
        "director_identity_pass": bound.get("pass") is True,
        "final_staged_program_audit_pass": audit.get("pass") is True,
        "staged_bytes_match_audit": all(audit.get("staged_files", {}).get(path.name) == sha(path) for path in (PRIMARY_BENCH, PRIMARY_REMOTE, HEAD_BENCH, HEAD_REMOTE, NEBIUS / "mla_microbench_control.py")),
        "authenticated_inventory_empty": not instances and not disks,
        "ssh_keypair_present": KEY.is_file() and PUBLIC_KEY.is_file(),
        "h200_placement_and_rate_bound": PLATFORM == "gpu-h200-sxm" and PRESET == "1gpu-16vcpu-200gb" and RATE_USD == 2.45,
        "diagnostic_docker_nvidia_bootstrap": all(token in bootstrap for token in ("docker.io", "nvidia-ctk", "--gpus all", "torch.cuda.get_device_name")),
        "provider_deadline_within_budget": 0 < deadline_epoch - time.time() <= 1800,
    }
    terminal = {
        "schema_version": 1,
        "type": "h200_bf16_linear_typed_precreate_terminal",
        "timestamp": now(),
        "name": name,
        "platform": PLATFORM,
        "preset": PRESET,
        "rate_usd_per_gpu_hour": RATE_USD,
        "disk_gib": 100,
        "runtime_image": IMAGE,
        "inventory": {"instances": instances, "disks": disks},
        "checks": checks,
        "pass": all(checks.values()),
    }
    atomic(output_dir / "PRECREATE_TERMINAL.json", terminal)
    return terminal


def make_trigger(deadline_epoch: float, audit: dict[str, object]):
    head_hashes = {
        HEAD_BENCH.name: sha(HEAD_BENCH),
        HEAD_REMOTE.name: sha(HEAD_REMOTE),
    }

    def trigger(primary: dict[str, object]) -> bool:
        basis = primary.get("h200_head_trigger_basis")
        if not isinstance(basis, dict):
            basis = {}
            primary["h200_head_trigger_basis"] = basis
        basis["program_hashes_match_final_audit"] = all(audit.get("staged_files", {}).get(name) == digest for name, digest in head_hashes.items())
        basis["provider_deadline_reserve_seconds"] = max(0.0, deadline_epoch - time.time())
        basis["deadline_leaves_five_minute_reserve"] = deadline_epoch - time.time() >= 300
        basis["evaluated_at_utc"] = now()
        return (
            primary.get("stage") == "primary"
            and primary.get("pass") is True
            and basis.get("all_primary_rows_valid") is True
            and basis.get("m16_or_m32_at_most_120pct_strict") is True
            and basis.get("head_could_change_classification") is True
            and basis.get("program_hashes_match_final_audit") is True
            and basis.get("deadline_leaves_five_minute_reserve") is True
        )

    return trigger


def build_scientific_summary(output_dir: Path, controller_code: int) -> dict[str, object]:
    control = json.loads((output_dir / "summary.json").read_text())
    primary_record = json.loads((output_dir / "primary-stage.json").read_text()) if (output_dir / "primary-stage.json").exists() else None
    conditional_record = json.loads((output_dir / "conditional-stage.json").read_text()) if (output_dir / "conditional-stage.json").exists() else None
    trigger = json.loads((output_dir / "conditional-trigger.json").read_text()) if (output_dir / "conditional-trigger.json").exists() else None
    primary = primary_record.get("terminal", {}).get("result", {}) if primary_record else {}
    head = conditional_record.get("terminal", {}).get("result", {}) if conditional_record else {}
    weighted = primary.get("architecture_weighted", [])
    head_rows = {row.get("m"): row for row in head.get("rows", [])}
    combined = []
    for row in weighted:
        m = row.get("m")
        combined_seconds = None
        if m in head_rows:
            head_seconds = float(head_rows[m]["wall_ms"]["p50"]) * 358 / int(m) / 1000.0
            combined_seconds = float(row["wall_request_seconds_358_steps"]) + head_seconds
        combined.append({
            "m": m,
            "linear_wall_request_seconds": row.get("wall_request_seconds_358_steps"),
            "head_wall_request_seconds": None if m not in head_rows else float(head_rows[m]["wall_ms"]["p50"]) * 358 / int(m) / 1000.0,
            "combined_wall_request_seconds": combined_seconds,
            "combined_exceeds_strict": None if combined_seconds is None else combined_seconds > STRICT_SECONDS,
            "combined_exceeds_lenient": None if combined_seconds is None else combined_seconds > LENIENT_SECONDS,
        })
    high_linear = [row for row in weighted if row.get("m") in (16, 32)]
    high_combined = [row for row in combined if row.get("m") in (16, 32) and row.get("combined_wall_request_seconds") is not None]
    primary_pass = primary.get("pass") is True
    if not primary_pass:
        classification = "malformed_or_failed_primary_science"
    elif high_combined:
        classification = "combined_linear_head_floor_falsifies_high_batch_bf16" if all(row["combined_exceeds_lenient"] for row in high_combined) else "combined_linear_head_floor_preserves_at_least_one_high_batch_point"
    elif high_linear and all(row.get("linear_floor_exceeds_lenient") for row in high_linear):
        classification = "transformer_linear_floor_falsifies_high_batch_bf16_head_not_needed"
    else:
        classification = "transformer_linear_floor_preserves_candidate_head_trigger_not_executed"
    return {
        "schema_version": 1,
        "classification": classification,
        "evidence_scope": "measured exact-shape synthetic-weight BF16 H200 component lower bound; not endpoint, quality, or complete latency",
        "primary_pass": primary_pass,
        "primary_result": primary,
        "h200_head_trigger": trigger,
        "conditional_head_result": head if conditional_record else None,
        "combined_floor": combined,
        "controller_returncode": controller_code,
        "controller_summary": control,
        "cleanup_pass": control.get("cleanup_pass") is True,
        "provider_exposure_seconds": control.get("allocation_seconds"),
        "spend_usd_derived": control.get("cost_usd_derived"),
        "completed_at_utc": now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--final-audit", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    terminal = typed_precreate(output_dir, args.name, args.final_audit.resolve(), args.identity.resolve(), args.deadline_epoch)
    if terminal["pass"] is not True:
        atomic(PROJECT / "STATUS.json", {"status": "complete", "summary": "Typed pre-create terminal failed; no provider mutation.", "provider_spend_usd": 0.0, "terminal_artifact": str(output_dir / "PRECREATE_TERMINAL.json"), "last_result_classification": "typed_precreate_failure"})
        append_log(f"\n## {now()} — typed pre-create failure\n\n- Question: can the exact BF16 transformer linears clear the H200 gate?\n- Action: final staged bytes were checked under the durable owner; provider creation remained gated.\n- Evidence: `{output_dir / 'PRECREATE_TERMINAL.json'}` failed.\n- Interpretation: no scientific or provider claim; project closes per stop rule.\n")
        return 1
    atomic(PROJECT / "STATUS.json", {"status": "active", "summary": "One durable H200 owner passed the typed pre-create gate and controls the sequential linear/head session.", "provider_mutation": "exclusive_durable_owner", "active_session": {"unit": os.environ.get("SYSTEMD_UNIT"), "pid": os.getpid(), "invocation_id": os.environ.get("INVOCATION_ID"), "name": args.name, "output_dir": str(output_dir), "deadline_epoch": args.deadline_epoch}, "authorized_spend_usd": 1.5, "terminal_artifact": None})
    controller.PLATFORM = PLATFORM
    controller.PRESET = PRESET
    controller.DISK_GIB = 100
    controller.HOURLY_RATE_USD = RATE_USD
    controller.DISK_HOURLY_RATE_USD = DISK_RATE_USD
    audit = json.loads(args.final_audit.read_text())
    controller.conditional_trigger = make_trigger(args.deadline_epoch, audit)
    code = controller.run(
        output_dir,
        args.name,
        KEY,
        PUBLIC_KEY,
        sha(PROJECT / "PROJECT.md"),
        PRIMARY_REMOTE,
        PRIMARY_BENCH,
        (),
        "h200-bf16-linears",
        max(1, int(args.deadline_epoch - time.time())),
        IMAGE,
        HEAD_REMOTE,
        HEAD_BENCH,
        (),
        "h200-parallel-lm-head",
    )
    try:
        summary = build_scientific_summary(output_dir, code)
    except Exception as error:
        summary = {"schema_version": 1, "classification": "terminal_reconciliation_failure", "error": {"type": type(error).__name__, "message": str(error)[:2000]}, "controller_returncode": code, "completed_at_utc": now()}
    atomic(PROJECT / "artifacts" / "SUMMARY.json", summary)
    complete = summary.get("primary_pass") is True and summary.get("cleanup_pass") is True and summary.get("spend_usd_derived", 99) <= 1.5
    atomic(PROJECT / "STATUS.json", {
        "status": "complete",
        "summary": summary.get("classification"),
        "provider_spend_usd": summary.get("spend_usd_derived"),
        "provider_exposure_seconds": summary.get("provider_exposure_seconds"),
        "active_session": None,
        "cleanup_pass": summary.get("cleanup_pass"),
        "last_result_classification": summary.get("classification"),
        "terminal_artifact": str(PROJECT / "artifacts" / "SUMMARY.json"),
    })
    append_log(
        f"\n## {now()} — H200 exact BF16 linear terminal\n\n"
        f"- Question: do exact architecture-weighted BF16 transformer linears alone falsify one-H200 economics, and does the conditional actual head change the classification?\n"
        f"- Action: ran one retained H200 session through the shared lifecycle; the head was controlled by the preregistered typed trigger.\n"
        f"- Evidence: `{PROJECT / 'artifacts' / 'SUMMARY.json'}`; classification `{summary.get('classification')}`; exposure `{summary.get('provider_exposure_seconds')}` s; derived spend `${summary.get('spend_usd_derived')}`; cleanup `{summary.get('cleanup_pass')}`.\n"
        f"- Interpretation: component lower bound only; omitted attention, KV, scheduler, sampling, prefill, quality, and endpoint reliability remain unmeasured.\n"
    )
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
