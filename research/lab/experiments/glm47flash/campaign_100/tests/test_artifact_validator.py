import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "specs"


class ArtifactValidatorTests(unittest.TestCase):
    def setUp(self):
        import sys

        sys.path.insert(0, str(SPECS))
        from validate_contracts import ContractError, validate_gpu_artifact

        self.ContractError = ContractError
        self.validate = validate_gpu_artifact
        self.raw = b"timestamp,gpu_utilization_percent\n2026-07-13T00:00:00Z,90\n"
        self.trace = b'{"traceEvents": []}\n'
        self.request_rows = [
            {
                "request_id": f"r{index}",
                "completed": True,
                "slo_eligible": True,
                "slo_compliant": True,
                "error": False,
                "silent_truncation": False,
                "input_tokens": 8192,
                "output_tokens": 1024,
                "ttft_ms": 2000,
                "inter_token_latency_ms": 40,
                "end_to_end_ms": 30000,
            }
            for index in range(100)
        ]
        self.requests = self._jsonl(self.request_rows)
        self.required_raw = {
            "requests.jsonl": (self.requests, "request_outcomes"),
            "scheduler.jsonl": (b'{"iteration":1,"batch_size":8}\n', "scheduler_samples"),
            "startup.json": (b'{"server_ready_seconds":120}\n', "startup_timings"),
            "billing.json": (b'{"hourly_price_usd":2.99}\n', "provider_billing"),
        }
        self.artifact = {
            "schema_version": "1.0.0",
            "artifact_id": "phase_b_stock_rep_1",
            "experiment_spec_sha256": "1" * 64,
            "workload_sha256": "2" * 64,
            "model": {
                "model_id": "zai-org/GLM-4.7-Flash",
                "checkpoint_revision": "75fce70",
                "tokenizer_revision": "75fce70",
                "representation": "bf16",
            },
            "runtime": {
                "name": "sglang",
                "source_revision": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
                "image_digest": "sha256:" + "3" * 64,
                "command_sha256": "4" * 64,
            },
            "hardware": {
                "provider": "runpod",
                "cloud_class": "secure",
                "gpu_model": "NVIDIA H100 80GB HBM3",
                "gpu_count": 1,
                "machine_id": "machine-redacted",
            },
            "allocation": {
                "provider_allocation_id": "pod-redacted",
                "started_at": "2026-07-13T00:00:00Z",
                "ended_at": "2026-07-13T00:10:00Z",
                "allocation_seconds": 600,
                "hourly_price_usd": 2.99,
                "provider_reported_cost_usd": 0.5,
                "conservative_cost_usd": 0.5,
            },
            "service_contract": {
                "max_p95_ttft_ms": 10000,
                "max_p95_itl_ms": 100,
                "min_request_success_fraction": 0.99,
                "silent_truncation_allowed": False,
            },
            "metrics": {
                "requests_scheduled": 100,
                "requests_completed": 100,
                "requests_slo_eligible": 100,
                "requests_slo_compliant": 100,
                "errors": 0,
                "silent_truncations": 0,
                "input_tokens": 819200,
                "output_tokens": 102400,
                "slo_input_tokens": 819200,
                "slo_output_tokens": 102400,
                "wall_seconds": 600,
                "input_tokens_per_second": 1365.333333,
                "output_tokens_per_second": 170.666667,
                "total_tokens_per_second": 1536,
                "completed_request_goodput_per_second": 0.166667,
                "latency_ms": {
                    "ttft": {"p50": 1000, "p95": 2000, "p99": 3000},
                    "inter_token": {"p50": 20, "p95": 40, "p99": 60},
                    "end_to_end": {"p50": 20000, "p95": 30000, "p99": 40000},
                },
            },
            "telemetry": {
                "cadence_seconds": 1,
                "gpu": {
                    "utilization_percent": {"p50": 90, "p95": 98, "p99": 99},
                    "vram_used_bytes": {"p50": 60000000000, "p95": 61000000000, "p99": 61500000000},
                    "power_watts": {"p50": 500, "p95": 650, "p99": 680},
                    "temperature_celsius": {"p50": 65, "p95": 72, "p99": 75},
                    "sm_clock_mhz": {"p50": 1500, "p95": 1800, "p99": 1850},
                    "memory_clock_mhz": {"p50": 2500, "p95": 2600, "p99": 2610},
                },
                "memory_throughput": {
                    "status": "measured",
                    "metric_name": "dram__bytes.sum.per_second",
                    "value": 1000000000000,
                    "unit": "bytes_per_second",
                },
                "scheduler": {
                    "iteration_count": 1000,
                    "batch_size": {"p50": 8, "p95": 16, "p99": 20},
                    "prefill_tokens": 819200,
                    "decode_tokens": 102400,
                    "kv_allocated_tokens_peak": 284098,
                    "prefix_cache_hits": 0,
                    "prefix_cache_misses": 100,
                },
                "startup": {
                    "container_seconds": 20,
                    "model_load_seconds": 80,
                    "cache_allocation_seconds": 10,
                    "server_ready_seconds": 120,
                },
                "profiler": {
                    "capture_seconds": 5,
                    "overhead_percent": 1.2,
                    "trace_sha256": hashlib.sha256(self.trace).hexdigest(),
                    "top_kernels": [{"name": "kernel", "time_share_fraction": 0.4}],
                },
                "raw_files": [
                    {
                        "path": "telemetry.csv",
                        "sha256": hashlib.sha256(self.raw).hexdigest(),
                        "bytes": len(self.raw),
                        "kind": "gpu_samples",
                    },
                    {
                        "path": "profiler.json",
                        "sha256": hashlib.sha256(self.trace).hexdigest(),
                        "bytes": len(self.trace),
                        "kind": "profiler_trace",
                    },
                ] + [
                    {
                        "path": path,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                        "kind": kind,
                    }
                    for path, (payload, kind) in self.required_raw.items()
                ],
            },
            "teardown": {
                "delete_requested_at": "2026-07-13T00:10:00Z",
                "delete_http_status": 204,
                "get_http_status": 404,
                "verified_at": "2026-07-13T00:10:10Z",
                "verification": "not_found",
                "watchdog_log_sha256": "6" * 64,
            },
            "validator": {
                "name": "campaign_100_validate_contracts",
                "version": "1.0.0",
                "result": "pass",
                "validated_at": "2026-07-13T00:11:00Z",
            },
        }

    @staticmethod
    def _jsonl(rows):
        return b"".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
            for row in rows
        )

    def _write_bundle(self, artifact=None, raw=None, request_rows=None):
        directory = tempfile.TemporaryDirectory()
        root = Path(directory.name)
        artifact = copy.deepcopy(artifact or self.artifact)
        (root / "telemetry.csv").write_bytes(self.raw if raw is None else raw)
        (root / "profiler.json").write_bytes(self.trace)
        for path, (payload, _) in self.required_raw.items():
            (root / path).write_bytes(payload)
        if request_rows is not None:
            payload = self._jsonl(request_rows)
            (root / "requests.jsonl").write_bytes(payload)
            descriptor = next(
                item
                for item in artifact["telemetry"]["raw_files"]
                if item["kind"] == "request_outcomes"
            )
            descriptor["sha256"] = hashlib.sha256(payload).hexdigest()
            descriptor["bytes"] = len(payload)
        (root / "artifact.json").write_text(json.dumps(artifact))
        return directory, root

    def test_complete_artifact_and_raw_hash_pass(self):
        directory, root = self._write_bundle()
        self.addCleanup(directory.cleanup)
        self.validate(root / "artifact.json", root)

    def test_missing_required_metric_fails_closed(self):
        artifact = copy.deepcopy(self.artifact)
        del artifact["telemetry"]["gpu"]["power_watts"]
        directory, root = self._write_bundle(artifact)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_unknown_field_fails_closed(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["metrics"]["peak_tokens_per_second"] = 999999
        directory, root = self._write_bundle(artifact)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_raw_hash_mismatch_fails_closed(self):
        directory, root = self._write_bundle(raw=b"tampered")
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_cost_below_conservative_floor_fails(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["allocation"]["conservative_cost_usd"] = 0.49
        directory, root = self._write_bundle(artifact)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_unverified_teardown_fails(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["teardown"]["verification"] = "delete_requested"
        directory, root = self._write_bundle(artifact)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_teardown_requires_delete_204_and_get_404(self):
        for changes in (
            {"delete_http_status": 500},
            {"get_http_status": 200},
            {"verification": "absent_from_inventory"},
        ):
            with self.subTest(changes=changes):
                artifact = copy.deepcopy(self.artifact)
                artifact["teardown"].update(changes)
                directory, root = self._write_bundle(artifact)
                self.addCleanup(directory.cleanup)
                with self.assertRaises(self.ContractError):
                    self.validate(root / "artifact.json", root)

    def test_throughput_must_match_tokens_and_wall_time(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["metrics"]["output_tokens_per_second"] = 999999
        directory, root = self._write_bundle(artifact)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_request_outcome_cardinality_must_match_scheduled_requests(self):
        directory, root = self._write_bundle(request_rows=self.request_rows[:-1])
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_slo_compliance_is_derived_from_request_outcomes(self):
        rows = copy.deepcopy(self.request_rows)
        rows[0]["ttft_ms"] = 20000
        directory, root = self._write_bundle(request_rows=rows)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)

    def test_missing_request_level_evidence_fails(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["telemetry"]["raw_files"] = [
            raw for raw in artifact["telemetry"]["raw_files"] if raw["kind"] != "request_outcomes"
        ]
        directory, root = self._write_bundle(artifact)
        self.addCleanup(directory.cleanup)
        with self.assertRaises(self.ContractError):
            self.validate(root / "artifact.json", root)


class ContractManifestTests(unittest.TestCase):
    def test_frozen_contract_hashes_match(self):
        manifest = json.loads((SPECS / "CONTRACT_MANIFEST.json").read_text())
        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["frozen_for_gate"], "A")
        for name, expected in manifest["files"].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((SPECS / name).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
