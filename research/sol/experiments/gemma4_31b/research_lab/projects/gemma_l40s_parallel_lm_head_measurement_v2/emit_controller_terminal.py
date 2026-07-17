#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path("/root/workspace")
NEBIUS = ROOT / "research/sol/experiments/glm47flash/campaign_100/nebius"
sys.path.insert(0, str(NEBIUS))

from placement_control import list_items
from vllm_smoke_control import resolve_created_instance, write_create_diagnostic


PROJECT = Path(__file__).resolve().parent
CONTROLLER = NEBIUS / "mla_microbench_control.py"
TESTS = ROOT / "research/sol/experiments/glm47flash/campaign_100/tests"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_checks() -> dict[str, object]:
    fixtures = {
        "create_failure": "access_token=token-value authorization Bearer bearer-value password=pw-value secret=secret-value -----BEGIN PRIVATE KEY----- hidden -----END PRIVATE KEY-----",
        "success": '{"metadata":{"id":"computeinstance-direct"}}',
        "reconciled_nonzero": "operation wait failed",
    }
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)
        failure = subprocess.CompletedProcess(["provider"], 3, fixtures["create_failure"], fixtures["create_failure"])
        write_create_diagnostic(output, failure)
        diagnostic = json.loads((output / "provider-create-diagnostic.json").read_text())
        failure_ok = (
            diagnostic["returncode"] == 3
            and diagnostic["stdout_sha256"] == hashlib.sha256(failure.stdout.encode()).hexdigest()
            and diagnostic["stderr_sha256"] == hashlib.sha256(failure.stderr.encode()).hexdigest()
            and all(value not in diagnostic["stdout_tail_redacted"] + diagnostic["stderr_tail_redacted"] for value in ("token-value", "bearer-value", "pw-value", "secret-value", "hidden"))
        )
        success = subprocess.CompletedProcess(["provider"], 0, fixtures["success"], "")
        write_create_diagnostic(output, success)
        direct_id, direct_reconciled = resolve_created_instance(success, "unused")
        nonzero = subprocess.CompletedProcess(["provider"], 3, "", fixtures["reconciled_nonzero"])
        with patch("vllm_smoke_control.find_named_instance", return_value="computeinstance-reconciled"):
            reconciled_id, reconciled = resolve_created_instance(nonzero, "gemma-l40s-head")
        with patch("vllm_smoke_control.find_named_instance", return_value=None):
            try:
                resolve_created_instance(nonzero, "gemma-l40s-head")
            except RuntimeError:
                empty_failure = True
            else:
                empty_failure = False
    return {
        "pass": failure_ok and direct_id == "computeinstance-direct" and not direct_reconciled and reconciled_id == "computeinstance-reconciled" and reconciled and empty_failure,
        "fixture_sha256": {name: hashlib.sha256(value.encode()).hexdigest() for name, value in fixtures.items()},
        "failure_diagnostic": diagnostic,
        "successful_create_resolves_instance": direct_id == "computeinstance-direct" and not direct_reconciled,
        "nonzero_created_instance_reconciles_before_watchdog": reconciled_id == "computeinstance-reconciled" and reconciled,
        "nonzero_empty_instance_is_terminal": empty_failure,
    }


def main() -> int:
    before = "1c7448d956d9c65eaf64494bf3bbd16afcf813e30f57604a36affc873d23af2b"
    command = [sys.executable, "-m", "unittest", str(TESTS / "test_nebius_mla_microbench.py"), str(TESTS / "test_nebius_vllm_smoke_control.py")]
    tests = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
    fixtures = fixture_checks()
    inventory = {kind: list_items(kind) for kind in ("instance", "disk")}
    result = {
        "schema_version": 1,
        "classification": "no_provider_controller_terminal",
        "pass": tests.returncode == 0 and fixtures["pass"] and not inventory["instance"] and not inventory["disk"],
        "provider_mutation_occurred": False,
        "controller_before_sha256": before,
        "controller_after_sha256": sha256(CONTROLLER),
        "controller_path": str(CONTROLLER),
        "test_command": command,
        "test_returncode": tests.returncode,
        "test_stdout_sha256": hashlib.sha256(tests.stdout.encode()).hexdigest(),
        "test_stderr_sha256": hashlib.sha256(tests.stderr.encode()).hexdigest(),
        "fixture_checks": fixtures,
        "authenticated_initial_inventory": {"instances": inventory["instance"], "disks": inventory["disk"], "empty": not inventory["instance"] and not inventory["disk"]},
    }
    path = PROJECT / "artifacts/CONTROLLER_TERMINAL.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
