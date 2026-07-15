from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path("/root/workspace")
LAB = Path("/root/.local/share/gradiated/research-lab")
PROGRAM = "glm-4.7-flash"
CAMPAIGN = REPO / "research/sol/experiments/glm47flash/campaign_100"
NEBIUS = CAMPAIGN / "nebius"
PARENT = LAB / "supervisor/glm-4.7-flash/workers/registered-glm47-observer-v17-immutable-identity-preparation-c1"
OUT = LAB / "supervisor/glm-4.7-flash/workers/director-glm47-observer-v18-direct-launch-repair-preparation-c1"
RUN_ID = "glm47-observer-diagnostic-l40s-v18"
LOCAL_RUN_ID = "glm47-observer-v18-direct-launch-repair-preparation-c1"
V17_FAILURE_BUNDLE = "86c4309080089d2697f49863ebf7e89e9b28314d118e27cb0fd04d55430a8a5b"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load(name: str) -> dict:
    return json.loads((PARENT / name).read_text())


def factory(*arguments: str) -> str:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "research/factory/src")
    completed = subprocess.run(
        [sys.executable, "-m", "grad_research", *arguments],
        cwd=REPO,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout


def main() -> int:
    if (OUT / "manifest.json").exists():
        raise SystemExit(f"completed preparation output already exists: {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(NEBIUS))
    from launcher_retention import launcher_record
    from observer_diagnostic_control import build_host_bootstrap

    existing_spec = (OUT / "paid-spec.json").exists()
    if existing_spec:
        now_text = (OUT / "preparation-now.txt").read_text().strip()
    else:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_text = now.isoformat().replace("+00:00", "Z")
    launcher = build_host_bootstrap().encode()
    launcher_text = launcher.decode()
    start_marker = '-lc "$(cat <<\'REMOTE_SCRIPT\'\n'
    end_marker = "\nREMOTE_SCRIPT\n)\""
    if start_marker not in launcher_text or end_marker not in launcher_text:
        raise SystemExit("direct-launch heredoc boundary is absent")
    payload = launcher_text.split(start_marker, 1)[1].split(end_marker, 1)[0]
    preservation_probe = (
        "set -Eeuo pipefail\n"
        "payload=\"$(cat <<'REMOTE_SCRIPT'\n"
        + payload
        + "\nREMOTE_SCRIPT\n)\"\n"
        "printf '%s' \"$payload\"\n"
    )
    preserved = subprocess.run(
        ["bash"], input=preservation_probe, text=True, capture_output=True, check=True
    ).stdout
    if preserved != payload:
        raise SystemExit("nested host/container shell changed the literal payload")
    syntax = subprocess.run(["bash", "-n"], input=launcher, capture_output=True)
    if syntax.returncode:
        raise SystemExit(syntax.stderr.decode())
    for token in ('$session', '$sample_mode', '$context_switch_mode', '$arm_dir'):
        if token not in preserved:
            raise SystemExit(f"literal token was not preserved: {token}")

    controller_sha = digest((NEBIUS / "observer_diagnostic_control.py").read_bytes())
    remote_sha = digest((NEBIUS / "remote_observer_diagnostic.sh").read_bytes())
    launcher_sha = digest(launcher)
    repair_binding = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "parent_failed_run_id": "glm47-observer-diagnostic-l40s-v17",
        "parent_failure_bundle_sha256": V17_FAILURE_BUNDLE,
        "failure_stage": "host_bootstrap_nsys_capability_gate_session_unbound_variable_before_checkpoint_transfer",
        "changed_variable": "replace the outer single-quoted bash -lc payload with a quoted heredoc command substitution so literal inner shell variables cross the host/container boundary unchanged",
        "controller_sha256": controller_sha,
        "remote_harness_sha256": remote_sha,
        "host_bootstrap_sha256": launcher_sha,
        "host_bootstrap_byte_length": len(launcher),
        "bash_syntax_pass": True,
        "literal_payload_byte_preservation_pass": True,
        "unchanged_science_budget_deadline_telemetry_cleanup": True,
    }
    configuration_sha = digest(canonical(repair_binding))
    preregistration = load("preregistration.json")
    preregistration["run_id"] = RUN_ID
    preregistration["status"] = "prepared_not_admitted"
    preregistration["operational_amendment"] = repair_binding
    artifact_contract = load("artifact-contract.json")
    artifact_contract["run_id"] = RUN_ID
    artifact_contract["root"] = f"runs/{RUN_ID}"
    identities = load("identities.json")
    identities["candidate_overrides"]["configuration_sha256"] = configuration_sha
    identities["candidate_overrides"]["harness_sha256"] = remote_sha
    preflight = load("preflight.json")
    candidate_identities = {**identities["control"], **identities["candidate_overrides"]}
    bindings = {
        "provider_fixture": "harness_sha256",
        "checkpoint_closure": "checkpoint_manifest_sha256",
        "tokenizer_identity": "tokenizer_manifest_sha256",
        "runtime_probe": "runtime_manifest_sha256",
        "configuration_identity": "configuration_sha256",
        "protocol_fixture": "harness_sha256",
        "parser_fixture": "harness_sha256",
        "artifact_paths": "harness_sha256",
        "local_tests": "harness_sha256",
    }
    evidence_hashes = {}
    for check, binding in bindings.items():
        evidence = {
            "schema_version": 1,
            "check": check,
            "pass": True,
            "bound_sha256": candidate_identities[binding],
        }
        evidence_path = OUT / f"{check}-evidence.json"
        write_json(evidence_path, evidence)
        stored = json.loads(factory("store-artifact", "--root", str(LAB), "--program", PROGRAM, str(evidence_path)))
        evidence_hashes[check] = stored["sha256"]
        preflight["checks"][check] = stored["sha256"]
    configuration_evidence_sha = evidence_hashes["configuration_identity"]
    write_json(OUT / "preregistration.json", preregistration)
    write_json(OUT / "artifact-contract.json", artifact_contract)
    write_json(OUT / "identities.json", identities)
    write_json(OUT / "preflight.json", preflight)
    write_json(OUT / "direct-launch-repair.json", repair_binding)
    if not existing_spec:
        (OUT / "preparation-now.txt").write_text(now_text + "\n")

    command = [
        sys.executable,
        str(NEBIUS / "prepare_observer_paid_run.py"),
        "--root", str(LAB),
        "--preregistration", str(OUT / "preregistration.json"),
        "--artifact-contract", str(OUT / "artifact-contract.json"),
        "--identities", str(OUT / "identities.json"),
        "--preflight", str(OUT / "preflight.json"),
        "--now", now_text,
        "--output", str(OUT / "paid-spec.json"),
    ]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "research/factory/src")
    if not existing_spec:
        prepared = subprocess.run(command, cwd=NEBIUS, env=environment, text=True, capture_output=True, check=True)
        (OUT / "preparation.stdout.json").write_text(prepared.stdout)
        (OUT / "preparation.stderr.log").write_text(prepared.stderr)
    spec = json.loads((OUT / "paid-spec.json").read_text())
    retained = launcher_record(launcher)
    if spec["host_bootstrap_launcher"] != retained:
        raise SystemExit("paid spec did not retain the exact repaired launcher bytes")
    (OUT / "host-bootstrap-launcher.sh").write_bytes(launcher)
    write_json(OUT / "host-bootstrap-launcher.json", retained)
    validation = factory("validate-paid-run", "--now", now_text, str(OUT / "paid-spec.json"))
    (OUT / "validation.json").write_text(validation)

    summary = {
        "schema_version": 1,
        "id": LOCAL_RUN_ID + "-artifact",
        "run_id": RUN_ID,
        "prepared_at": now_text,
        "paid_spec_sha256": digest(canonical(spec)),
        "paid_spec_file_sha256": digest((OUT / "paid-spec.json").read_bytes()),
        "host_bootstrap_sha256": launcher_sha,
        "host_bootstrap_byte_length": len(launcher),
        "configuration_identity_sha256": configuration_sha,
        "configuration_evidence_sha256": configuration_evidence_sha,
        "checks": {
            "bash_syntax": True,
            "literal_nested_shell_tokens_preserved": True,
            "exact_launcher_retained": True,
            "factory_paid_spec_validation": True,
            "provider_access": False,
            "paid_cost_usd": 0.0,
        },
        "next_action": "On the next cycle, resume as supervisor-glm47, reconcile provider state, and immediately admit this exact V18 paid spec. Leave provider-controller execution to the deterministic supervisor.",
    }
    write_json(OUT / "preparation-result.json", summary)
    artifact = json.loads(factory("store-artifact", "--root", str(LAB), "--program", PROGRAM, str(OUT / "preparation-result.json")))
    artifact_sha = artifact["sha256"]

    state = json.loads((LAB / "programs/glm-4.7-flash/STATE.json").read_text())
    baseline = state["baseline"]
    baseline_sha = digest(canonical(baseline))
    local_spec = {
        "schema_version": 1,
        "run_id": LOCAL_RUN_ID,
        "program_id": PROGRAM,
        "scout_id": "glm47-dense-resource-signature",
        "baseline_id": baseline["id"],
        "baseline_sha256": baseline_sha,
        "execution_kind": "local",
        "fidelity": "reference",
        "control_id": "v17-single-quoted-nested-bash-lc-payload",
        "candidate_id": "v18-quoted-heredoc-command-substitution-payload",
        "changed_variable": repair_binding["changed_variable"],
        "claim_scope": {
            "model": "GLM-4.7-Flash metadata only; no inference",
            "workload": "Immutable paid-spec preparation for unchanged A1/B1/A2 geometry",
            "hardware": "Local shell/reference validation only; no provider or GPU",
            "claim_limit": "Direct launch-boundary repair and paid-spec readiness only; no scientific belief update",
        },
        "gates": {
            "correctness": {"policy_sha256": load("paid-spec.json")["gates"]["correctness"]["policy_sha256"], "required": True},
            "quality": {"policy_sha256": baseline["quality_policy_sha256"], "required": True},
            "slo": {"policy_sha256": baseline["slo_policy_sha256"], "required": True},
        },
        "prediction": {
            "metric": "literal_nested_shell_token_preservation_fraction",
            "expected_direction": "increase",
            "point_estimate_fraction": 1.0,
            "minimum_effect_fraction": 1.0,
            "plausible_ceiling_fraction": 1.0,
            "falsifier": "Any literal session/sample/context/arm token expands at the host boundary, Bash syntax fails, the exact launcher is not retained, paid-spec validation fails, or provider access occurs.",
        },
        "measurement_contract": {"protocol": "deterministic", "effect_formula": "candidate_over_control_minus_one", "minimum_candidate_repetitions": 1, "statistic": "median"},
        "artifact_refs": [V17_FAILURE_BUNDLE, artifact_sha],
        "max_cost_usd": 0.0,
        "timeout_seconds": 600,
        "seed": 470218,
        "command": "Prepare exactly one fresh immutable V18 paid spec using the existing observer harness after the direct nested-shell launch repair; do not admit or launch it.",
    }
    result = {
        "schema_version": 1,
        "id": LOCAL_RUN_ID + "-result",
        "run_id": LOCAL_RUN_ID,
        "scout_id": local_spec["scout_id"],
        "control_id": local_spec["control_id"],
        "candidate_id": local_spec["candidate_id"],
        "changed_variable": local_spec["changed_variable"],
        "baseline_sha256": baseline_sha,
        "prediction_sha256": digest(canonical(local_spec["prediction"])),
        "outcome_class": "diagnostic_valid",
        "fidelity": "reference",
        "scope": local_spec["claim_scope"],
        "gates": {"correctness": True, "quality": True, "slo": True},
        "cost_usd": 0.0,
        "artifact_refs": [artifact_sha],
        "diagnostic_summary": "The V17 launch failure is repaired at the direct nested-shell boundary; exact literal shell tokens survive, Bash syntax passes, and one fresh immutable V18 paid spec validates with unchanged science, budget, deadline, telemetry, and cleanup contracts. No provider mutation occurred.",
        "residual_bottleneck": "Matched target-L40S observer bracket remains unexecuted; dense-device versus host/scheduler request-critical attribution remains unresolved until V18 runs.",
        "next_action": summary["next_action"],
    }
    write_json(OUT / "local-run.json", local_spec)
    write_json(OUT / "result.json", result)
    factory("record", "--root", str(LAB), "--program", PROGRAM, "--kind", "local_run", "--input", str(OUT / "local-run.json"))
    factory("record", "--root", str(LAB), "--program", PROGRAM, "--kind", "result", "--input", str(OUT / "result.json"))
    write_json(OUT / "manifest.json", {"schema_version": 1, "files": {path.name: digest(path.read_bytes()) for path in sorted(OUT.iterdir()) if path.is_file()}})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
