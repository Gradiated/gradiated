#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
RUN = HERE / "artifacts/gemma-vllm-c16c32-20260717t1500z-run"
OWNER = HERE / "launch_owner.py"
RUNNER = HERE / "stale_trace_endpoint_runner.py"
RENDERED = RUN / "RENDERED_REMOTE.sh"
STATUS = HERE / "STATUS.json"
LOWER = HERE.parent / "exact_vllm_h200_transfer_view_endpoint/launch_transfer_view.py"
FIXED = HERE.parent / "exact_vllm_h200_fixed_session_endpoint/vllm_fixed_session_owner.py"
TRACE = HERE.parent / "gemma_exact_cache_trace_contract/TRACE_PACKET.json"
PREFIX = HERE.parent / "prefix_cache_primary_mix_bound/PREFIX_ARM_PACKET.json"
TOOLS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    status = json.loads(STATUS.read_text())
    owner_pid = int(status["active_session"]["owner_pid"] if "owner_pid" in status["active_session"] else 2009215)
    owner_text = OWNER.read_text()
    runner_text = RUNNER.read_text()
    rendered_text = RENDERED.read_text()
    cmdline = Path(f"/proc/{owner_pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    bind_paths = [
        OWNER,
        RUNNER,
        RENDERED,
        RUN / "FINAL_AUDIT.json",
        LOWER,
        FIXED,
        TRACE,
        PREFIX,
        TOOLS / "session_staging.py",
        TOOLS / "placement_control.py",
        TOOLS / "stock_control.py",
    ]
    checks = {
        "live_durable_owner": Path(f"/proc/{owner_pid}").is_dir() and "launch_owner.py run" in cmdline,
        "rendered_captured_before_create": owner_text.index("rendered = actual_lower_audit") < owner_text.index("stage = \"provider_create\""),
        "science_consumes_captured_local": "input_text=rendered" in owner_text,
        "science_does_not_reload_rendered_file": "RENDERED_REMOTE.sh\").read_text" not in owner_text,
        "stale_conditional_sglang_absent": "sglang.launch_server" not in rendered_text and "VLLM_MARKET_TRIGGER" not in rendered_text,
        "required_prefix_trigger_present": "PREFIX_RESCUE_TRIGGER" in rendered_text and "--no-enable-prefix-caching" in rendered_text,
        "semantic_human_readable_validation": all(token in runner_text for token in ("semantic_text", "non_repetitive", "math.isfinite", "prompt_token_ids")),
        "c16_stable_repetitions": "stable_repetitions" in runner_text,
        "c32_safe_decision_gate": all(token in runner_text for token in ("hbm_headroom", "allocator_headroom", "queue_seconds", "prefill_seconds", "decode_seconds", "c32_not_run")),
        "c32_independent_cache_state": "c32_independent_restart" in rendered_text,
        "ten_k_cache_contract": all(token in runner_text for token in ("cache_query_delta_tokens", "10000", "cache_hit_delta_tokens")),
        "parsed_service_metrics": all(token in runner_text for token in ("queue_seconds", "prefill_seconds", "decode_seconds", "pooling_seconds")),
        "observed_reload_count": all(
            token not in runner_text
            for token in ("reload_count = 0", "\"reload_count\": 0", "result[\"reload_count\"] = 0")
        ),
        "sudo_docker_info": "sudo docker info" in rendered_text,
        "both_market_thresholds": "2.094181" in rendered_text and "2.118591" in rendered_text,
        "production_and_experiment_cost": "3.25" in rendered_text and "2.45" in rendered_text and "disk" in rendered_text,
        "create_to_cleanup_accounting": "provider_created_epoch" in owner_text and "cleanup_completed_epoch" in owner_text,
        "live_owner_can_consume_replacement": False,
    }
    result = {
        "schema_version": 1,
        "classification": "postcreate_prescience_behavioral_audit_failed_live_program_immutable",
        "pass": all(checks.values()),
        "checks": checks,
        "owner_pid": owner_pid,
        "owner_cmdline": cmdline,
        "active_session": status.get("active_session"),
        "bound_executable_sha256": {str(path): sha(path) for path in bind_paths},
        "immutable_live_rendered_sha256": sha(RENDERED),
        "decision": "fail_closed_at_program_transfer_then_existing_verified_retained_owner_cleanup",
        "reason": "The live owner captured the stale rendered shell in a local variable before provider create; later source or artifact edits cannot change run_ssh(input_text=rendered).",
        "observed_epoch": time.time(),
    }
    output = HERE / "artifacts/POSTCREATE_PRE_SCIENCE_BEHAVIORAL_AUDIT.json"
    atomic_write(output, result)
    atomic_write(HERE / "artifacts/FINAL_AUDIT.json", result)
    return 0 if result["pass"] else 78


if __name__ == "__main__":
    raise SystemExit(main())
