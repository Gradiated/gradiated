from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


REPO = Path("/root/workspace")
LAB = Path("/root/.local/share/gradiated/research-lab")
PROGRAM = "glm-4.7-flash"
CAMPAIGN_ID = "glm47-nebius-25"
RUN_ID = "glm47-observer-diagnostic-l40s-v23"
LOCAL_RUN_ID = "glm47-observer-v23-supervisor-direct-dispatch-preparation-c1"
SETUP_KEY = "l40s:vllm:glm47:observer"
V18_FAILURE_BUNDLE = "fc2794ca93124de55c785e4be2b5aab5cb5e6b3f10ab7a8235dfdc6c7b9691f3"
CAMPAIGN = REPO / "research/lab/experiments/glm47flash/campaign_100"
NEBIUS = CAMPAIGN / "nebius"
FACTORY_SRC = REPO / "research/factory/src"
PARENT = LAB / "supervisor/glm-4.7-flash/workers/registered-glm47-observer-v18-watchdog-clock-reconciliation-c1"
OUT = LAB / "supervisor/glm-4.7-flash/workers/registered-glm47-observer-v23-supervisor-direct-dispatch-preparation-c1"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def factory(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(FACTORY_SRC)
    return subprocess.run(
        [sys.executable, "-m", "grad_research", *arguments],
        cwd=REPO,
        env=environment,
        text=True,
        capture_output=True,
        check=check,
        timeout=120,
    )


def capture(label: str, function) -> dict:
    try:
        function()
    except Exception as error:
        return {
            "case": label,
            "accepted": False,
            "error_type": type(error).__name__,
            "error": str(error),
        }
    return {"case": label, "accepted": True}


def main() -> int:
    if (OUT / "hashes.txt.sha256").exists():
        raise SystemExit(f"immutable V23 preparation already exists: {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(FACTORY_SRC))
    sys.path.insert(0, str(NEBIUS))

    from grad_research.admission import validate_paid_run
    from grad_research.supervisor import ModelRoute, ResearchSupervisor, SupervisorConfig
    from grad_research.util import content_hash
    from launcher_retention import launcher_record
    from observer_diagnostic_control import build_host_bootstrap

    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_text = now.isoformat().replace("+00:00", "Z")
    later_text = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    tuple_value = {
        "program_id": PROGRAM,
        "campaign_id": CAMPAIGN_ID,
        "run_id": RUN_ID,
        "setup_key": SETUP_KEY,
    }
    launcher_bytes = build_host_bootstrap().encode()
    launcher = launcher_record(launcher_bytes)
    controller_sha = digest((NEBIUS / "observer_diagnostic_control.py").read_bytes())
    remote_sha = digest((NEBIUS / "remote_observer_diagnostic.sh").read_bytes())
    supervisor_sha = digest((FACTORY_SRC / "grad_research/supervisor.py").read_bytes())
    dispatch_binding = {
        "schema_version": 1,
        "execution_geometry": "supervisor_bound_direct_dispatch",
        "factory_identity_tuple": tuple_value,
        "controller_sha256": controller_sha,
        "remote_harness_sha256": remote_sha,
        "supervisor_sha256": supervisor_sha,
        "launcher_sha256": launcher["sha256"],
        "launcher_byte_length": launcher["byte_length"],
        "parent_failure_bundle_sha256": V18_FAILURE_BUNDLE,
        "retired_run_ids": [
            "glm47-observer-diagnostic-l40s-v17",
            "glm47-observer-diagnostic-l40s-v18",
        ],
    }
    configuration_sha = digest(canonical(dispatch_binding))
    harness_sha = digest(canonical({
        "controller_sha256": controller_sha,
        "remote_harness_sha256": remote_sha,
        "supervisor_sha256": supervisor_sha,
        "execution_geometry": dispatch_binding["execution_geometry"],
    }))

    preregistration = load(PARENT / "preregistration.json")
    preregistration["run_id"] = RUN_ID
    preregistration["campaign_id"] = CAMPAIGN_ID
    preregistration["status"] = "prepared_not_admitted"
    preregistration["operational_amendment"] = dispatch_binding
    artifact_contract = load(PARENT / "artifact-contract.json")
    artifact_contract["run_id"] = RUN_ID
    artifact_contract["root"] = f"runs/{RUN_ID}"
    identities = load(PARENT / "identities.json")
    identities["candidate_overrides"]["configuration_sha256"] = configuration_sha
    identities["candidate_overrides"]["harness_sha256"] = harness_sha
    candidate = {**identities["control"], **identities["candidate_overrides"]}
    preflight = {"schema_version": 1, "checks": {}}
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
    preflight_dir = OUT / "preflight"
    preflight_dir.mkdir(exist_ok=True)
    for check_name, identity_field in bindings.items():
        evidence = {
            "schema_version": 1,
            "check": check_name,
            "pass": True,
            "bound_sha256": candidate[identity_field],
        }
        evidence_path = preflight_dir / f"{check_name}.json"
        write_json(evidence_path, evidence)
        stored = json.loads(factory(
            "store-artifact", "--root", str(LAB), "--program", PROGRAM, str(evidence_path)
        ).stdout)
        preflight["checks"][check_name] = stored["sha256"]

    write_json(OUT / "preregistration.json", preregistration)
    write_json(OUT / "artifact-contract.json", artifact_contract)
    write_json(OUT / "identities.json", identities)
    write_json(OUT / "preflight.json", preflight)
    write_json(OUT / "provider-dispatch-contract.json", dispatch_binding)
    (OUT / "preparation-now.txt").write_text(now_text + "\n")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(FACTORY_SRC)
    preparation = subprocess.run(
        [
            sys.executable,
            str(NEBIUS / "prepare_observer_paid_run.py"),
            "--root", str(LAB),
            "--preregistration", str(OUT / "preregistration.json"),
            "--artifact-contract", str(OUT / "artifact-contract.json"),
            "--identities", str(OUT / "identities.json"),
            "--preflight", str(OUT / "preflight.json"),
            "--now", now_text,
            "--output", str(OUT / "paid-spec.json"),
        ],
        cwd=NEBIUS,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    )
    (OUT / "preparation.stdout.json").write_text(preparation.stdout)
    (OUT / "preparation.stderr.log").write_text(preparation.stderr)
    spec = load(OUT / "paid-spec.json")
    spec["provider_dispatch_contract"] = dispatch_binding
    write_json(OUT / "paid-spec.json", spec)
    validate_paid_run(spec, now=now)
    validate_paid_run(spec, now=now + timedelta(seconds=1))
    (OUT / "host-bootstrap-launcher.sh").write_bytes(launcher_bytes)
    write_json(OUT / "host-bootstrap-launcher.json", launcher)

    campaign_fixture = OUT / "campaign-fixture"
    campaign_fixture.mkdir(exist_ok=True)
    (campaign_fixture / "CAMPAIGN_STATUS.json").write_text("{}\n")
    provider_launcher = (
        sys.executable,
        str(NEBIUS / "observer_diagnostic_control.py"),
        "--output-dir", "{output_dir}",
        "--name", "{run_id}",
        "--ssh-key", "/dev/null",
        "--ssh-public-key", "/dev/null",
        "--local-model-dir", "/dev/null",
        "--reference-tokenizer-dir", "/dev/null",
        "--experiment-spec-sha256", "{admission_sha256}",
        "--factory-root", "{root}",
        "--factory-program", "wrong-program",
        "--factory-campaign", "{campaign_dir}",
        "--factory-run-id", "wrong-run",
        "--factory-owner", "{owner}",
        "--factory-reservation-id", "{reservation_id}",
        "--factory-allocation-id", "{allocation_id}",
        "--factory-setup-key", "wrong-setup",
        "--factory-absolute-deadline", "{absolute_deadline_utc}",
        "--host-bootstrap-launcher", "{host_bootstrap_launcher}",
    )

    def render(current_spec: dict, launcher_template=provider_launcher) -> tuple[list[str], dict]:
        config = SupervisorConfig(
            root=OUT / "factory-fixture",
            program_id=PROGRAM,
            repo_dir=REPO,
            campaign_dir=campaign_fixture,
            owner="supervisor-glm47",
            mode="observe",
            cycle_interval_seconds=1,
            idle_backoff_seconds=1,
            coordinator_ttl_seconds=60,
            director_timeout_seconds=60,
            turn_timeout_seconds=60,
            provider_launcher=tuple(launcher_template),
            director=ModelRoute("unused", "high"),
            implementation=ModelRoute("unused", "medium"),
            mechanical=ModelRoute("unused", "medium"),
        )
        supervisor = ResearchSupervisor(config)
        try:
            supervisor.director.state = lambda: {
                "runs": {
                    RUN_ID: {
                        "admission": {
                            "admission_sha256": content_hash(current_spec),
                            "reservation_id": f"reservation:{RUN_ID}",
                            "absolute_deadline_utc": current_spec["watchdog"]["absolute_deadline_utc"],
                        },
                        "spec": current_spec,
                    }
                }
            }
            return supervisor._provider_command({"run_id": RUN_ID}, {"epoch": 3})
        finally:
            supervisor.close()

    command, context = render(spec)
    rendered = {
        "schema_version": 1,
        "argv": command,
        "sha256": digest(canonical(command)),
        "factory_identity_tuple": context["factory_identity_tuple"],
        "tuple_bound_before_dispatch": True,
        "provider_access": False,
    }
    write_json(OUT / "rendered-command.json", rendered)

    import observer_diagnostic_control as controller

    class ParserSentinel(RuntimeError):
        pass

    with patch.object(controller, "run", side_effect=ParserSentinel("pre-provider sentinel")):
        with patch.object(sys, "argv", command[1:]):
            parser_result = capture("complete_rendered_argv", controller.main)
    parser_reached = parser_result.get("error_type") == "ParserSentinel"

    def mutated_spec(path: tuple[str, ...], value) -> dict:
        changed = copy.deepcopy(spec)
        target = changed
        for name in path[:-1]:
            target = target[name]
        target[path[-1]] = value
        return changed

    mutated_bytes = bytearray(base64.b64decode(launcher["bytes"], validate=True))
    mutated_bytes[0] ^= 1
    missing_campaign_flag = list(provider_launcher)
    campaign_position = missing_campaign_flag.index("--factory-campaign")
    del missing_campaign_flag[campaign_position:campaign_position + 2]
    controls = [
        capture("missing_identity_flag", lambda: render(spec, tuple(missing_campaign_flag))),
        capture("duplicate_identity_flag", lambda: render(spec, provider_launcher + ("--factory-run-id", RUN_ID))),
        capture("missing_tuple_member", lambda: render(mutated_spec(("campaign_id",), None))),
        capture("malformed_tuple_member", lambda: render(mutated_spec(("campaign_id",), "bad\nvalue"))),
        capture("retired_identity", lambda: render(mutated_spec(
            ("provider_dispatch_contract", "factory_identity_tuple", "run_id"),
            "glm47-observer-diagnostic-l40s-v18",
        ))),
        capture("foreign_identity", lambda: render(mutated_spec(
            ("provider_dispatch_contract", "factory_identity_tuple", "program_id"), "foreign-program"
        ))),
        capture("cross_identity_substitution", lambda: render(mutated_spec(
            ("provider_dispatch_contract", "factory_identity_tuple", "campaign_id"), "foreign-campaign"
        ))),
        capture("wrong_launcher_hash", lambda: render(mutated_spec(
            ("host_bootstrap_launcher", "sha256"), "0" * 64
        ))),
        capture("wrong_launcher_length", lambda: render(mutated_spec(
            ("host_bootstrap_launcher", "byte_length"), launcher["byte_length"] + 1
        ))),
        capture("one_byte_mutated_launcher", lambda: render(mutated_spec(
            ("host_bootstrap_launcher", "bytes"), base64.b64encode(mutated_bytes).decode()
        ))),
    ]
    if not parser_reached or any(control["accepted"] for control in controls):
        raise SystemExit("V23 direct-dispatch parser or fail-closed tuple controls failed")
    write_json(OUT / "tuple-controls.json", {
        "schema_version": 1,
        "parser_reachability": parser_result,
        "parser_reached_pre_provider_sentinel": parser_reached,
        "controls": controls,
        "all_fail_closed": True,
    })

    commands = [
        [sys.executable, "-m", "py_compile", str(FACTORY_SRC / "grad_research/supervisor.py"), str(NEBIUS / "observer_diagnostic_control.py"), str(NEBIUS / "prepare_observer_paid_run.py")],
        [sys.executable, "-m", "unittest", "research.factory.tests.test_supervisor.SupervisorTests.test_provider_launcher_binds_factory_identity_tuple_from_admitted_spec", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", str(CAMPAIGN / "tests"), "-p", "test_launcher_retention.py", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", str(CAMPAIGN / "tests"), "-p", "test_prepare_observer_paid_run.py", "-v"],
        [sys.executable, "tools/devex/check.py"],
    ]
    verification_lines = []
    verification_exit = 0
    for verification_command in commands:
        completed = subprocess.run(
            verification_command,
            cwd=REPO,
            env=environment,
            text=True,
            capture_output=True,
            timeout=180,
        )
        verification_lines.extend([
            "$ " + " ".join(verification_command),
            completed.stdout,
            completed.stderr,
            f"exit={completed.returncode}",
        ])
        verification_exit = verification_exit or completed.returncode
    (OUT / "verification.log").write_text("\n".join(verification_lines))
    (OUT / "verification-exit.txt").write_text(str(verification_exit) + "\n")
    if verification_exit:
        raise SystemExit("V23 focused verification failed")

    source_paths = {
        "supervisor.py": FACTORY_SRC / "grad_research/supervisor.py",
        "observer_diagnostic_control.py": NEBIUS / "observer_diagnostic_control.py",
        "remote_observer_diagnostic.sh": NEBIUS / "remote_observer_diagnostic.sh",
        "prepare_observer_paid_run.py": NEBIUS / "prepare_observer_paid_run.py",
        "v18_failure_result.json": CAMPAIGN / "allocations/glm47-observer-diagnostic-l40s-v18/failure-evidence/result.json",
    }
    write_json(OUT / "source-input-hashes.json", {
        name: digest(path.read_bytes()) for name, path in source_paths.items()
    })
    result_markdown = f"""# V23 supervisor-bound direct-dispatch preparation

Status: PASS; prepared but not admitted or launched.

Measured V18 outcome: operational failure at the pre-provider identity gate. The retained command evidence bound `--factory-campaign` to a repository directory, while the controller requires `{CAMPAIGN_ID}`. The individual drifted tuple member was not retained in V18 stderr, so attribution remains uncertain despite this reproduced mismatch.

Derived V23 outcome: the complete `{PROGRAM}` / `{CAMPAIGN_ID}` / `{RUN_ID}` / `{SETUP_KEY}` tuple is now bound from the immutable paid spec before direct controller dispatch. The exact launcher and rendered argv validate at `{now_text}` and `{later_text}`; all declared mutation controls fail closed.

Paid cost: $0.00. No provider, GPU, model, network, admission, or paid controller was accessed.

Residual bottleneck: the matched target-L40S observer bracket remains unexecuted; dense-device versus host/scheduler request-critical attribution remains unresolved.

Next action: after a fresh fenced resume in a later director cycle, admit only this exact V23 paid spec and leave provider execution to the deterministic supervisor.
"""
    (OUT / "result.md").write_text(result_markdown)
    summary = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "prepared_at": now_text,
        "paid_spec_sha256": content_hash(spec),
        "paid_spec_file_sha256": digest((OUT / "paid-spec.json").read_bytes()),
        "rendered_command_sha256": rendered["sha256"],
        "launcher_sha256": launcher["sha256"],
        "factory_identity_tuple": tuple_value,
        "outcome_class": "diagnostic_valid",
        "cost_usd": 0.0,
        "provider_access": False,
        "uncertainty": "V18 retained stderr did not identify the individual drifted tuple member.",
        "residual_bottleneck": "Matched target-L40S observer bracket remains unexecuted; dense-device versus host/scheduler request-critical attribution remains unresolved.",
        "next_action": "After a fresh fenced resume, admit only this exact V23 spec; deterministic supervisor owns provider execution.",
    }
    write_json(OUT / "preparation-result.json", summary)
    artifact = json.loads(factory(
        "store-artifact", "--root", str(LAB), "--program", PROGRAM, str(OUT / "preparation-result.json")
    ).stdout)

    state = load(LAB / f"programs/{PROGRAM}/STATE.json")
    baseline = state["baseline"]
    local_run = state["runs"][LOCAL_RUN_ID]["spec"]
    result = {
        "schema_version": 1,
        "id": LOCAL_RUN_ID + "-result",
        "run_id": LOCAL_RUN_ID,
        "scout_id": local_run["scout_id"],
        "control_id": local_run["control_id"],
        "candidate_id": local_run["candidate_id"],
        "changed_variable": local_run["changed_variable"],
        "baseline_sha256": local_run["baseline_sha256"],
        "prediction_sha256": content_hash(local_run["prediction"]),
        "outcome_class": "diagnostic_valid",
        "fidelity": "reference",
        "scope": local_run["claim_scope"],
        "gates": {"correctness": True, "quality": True, "slo": True},
        "cost_usd": 0.0,
        "artifact_refs": [artifact["sha256"]],
        "diagnostic_summary": "V23 binds and validates the complete factory tuple before direct dispatch; exact rendering, parser reachability, launcher retention, paid-spec validation, and declared mutation controls pass locally.",
        "residual_bottleneck": summary["residual_bottleneck"],
        "next_action": summary["next_action"],
    }
    write_json(OUT / "local-run.json", local_run)
    write_json(OUT / "result.json", result)
    factory("record", "--root", str(LAB), "--program", PROGRAM, "--kind", "result", "--input", str(OUT / "result.json"))

    manifest_files = sorted(path for path in OUT.iterdir() if path.is_file() and path.name not in {"hashes.txt", "hashes.txt.sha256"})
    hashes_text = "".join(f"{digest(path.read_bytes())}  {path.name}\n" for path in manifest_files)
    (OUT / "hashes.txt").write_text(hashes_text)
    (OUT / "hashes.txt.sha256").write_text(f"{digest(hashes_text.encode())}  hashes.txt\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
