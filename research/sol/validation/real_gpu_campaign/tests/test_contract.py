from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.real_gpu_campaign.contract import validate_campaign


class CampaignContractTests(unittest.TestCase):
    def fixture(self) -> tuple[Path, Path]:
        directory = Path(tempfile.mkdtemp())
        (directory / "server.metrics.txt").write_text("# HELP sglang_requests_total requests\nsglang_requests_total 2\n")
        (directory / "bench.json").write_text(json.dumps({"total_input_tokens": 8192, "total_output_tokens": 1024, "duration": 10, "completed": 2, "failed": 0, "mean_ttft_ms": 100, "mean_tpot_ms": 20}))
        with (directory / "telemetry.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["phase", "utilization.gpu", "power.draw"])
            writer.writeheader()
            for phase in ("allocation", "startup", "warmup", "benchmark", "teardown"):
                writer.writerow({"phase": phase, "utilization.gpu": 50, "power.draw": 250})
        phases = [{"name": name, "started_at": f"2026-07-13T00:0{i}:00Z", "finished_at": f"2026-07-13T00:0{i}:01Z", "missing_counters": []} for i, name in enumerate(("allocation", "startup", "warmup", "benchmark", "teardown"))]
        contract = {"identity": {"run_id": "r1", "model": "glm", "model_revision": "rev", "workload_id": "w", "workload_hash": "h", "slo_id": "slo"}, "provenance": {"result_kind": "measured", "published_inputs_used": False}, "phases": phases, "server": {"healthy": True}, "teardown": {"complete": True}, "workload": {"slo_identity": "slo"}, "benchmark_result": "bench.json", "cost": {"hourly_rate_usd": 2.99}}
        (directory / "contract.json").write_text(json.dumps(contract))
        files = ["server.metrics.txt", "bench.json", "telemetry.csv", "contract.json"]
        manifest = [{"name": name, "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest()} for name in files]
        (directory / "manifest.json").write_text(json.dumps(manifest))
        return directory, directory / "contract.json"

    def test_valid_contract_computes_conservative_economics(self) -> None:
        directory, _ = self.fixture()
        report = validate_campaign(directory, {"allocation_seconds": 3600, "hourly_rate_usd": 2.99})
        self.assertTrue(report.valid)
        self.assertTrue(report.economic_win_permitted)
        self.assertAlmostEqual(report.metrics["economics"]["usd_per_million_8_to_1_output_equivalent"], 2.99 / 2048 * 1_000_000)

    def test_missing_phase_benchmark_server_teardown_and_mixed_provenance_fail(self) -> None:
        directory, _ = self.fixture()
        contract = json.loads((directory / "contract.json").read_text())
        contract["phases"] = []
        contract["benchmark_result"] = "missing.json"
        contract["server"]["healthy"] = False
        contract["teardown"]["complete"] = False
        contract["provenance"]["published_inputs_used"] = True
        (directory / "contract.json").write_text(json.dumps(contract))
        report = validate_campaign(directory, {"allocation_seconds": 1, "hourly_rate_usd": 1})
        self.assertFalse(report.valid)
        self.assertFalse(report.economic_win_permitted)
        for expected in ("missing phase marker", "missing benchmark result", "server failure", "incomplete teardown", "mixed published/measured"):
            self.assertIn(expected, " ".join(report.errors))

    def test_manifest_hash_mismatch_fails(self) -> None:
        directory, _ = self.fixture()
        (directory / "bench.json").write_text("{}")
        report = validate_campaign(directory, {"allocation_seconds": 1, "hourly_rate_usd": 1})
        self.assertIn("artifact hash mismatch: bench.json", report.errors)


if __name__ == "__main__":
    unittest.main()
