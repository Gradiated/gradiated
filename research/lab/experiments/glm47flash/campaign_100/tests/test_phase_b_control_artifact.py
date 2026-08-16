import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


CAMPAIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN / "phase_b"))
sys.path.insert(0, str(CAMPAIGN / "specs"))

from artifact_builder import build_artifact, write_internal_manifest
from validate_contracts import validate_gpu_artifact


class ArtifactBuilderTests(unittest.TestCase):
    def test_writes_content_addressed_internal_manifest_without_self_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "evidence.txt").write_bytes(b"evidence\n")
            output = root / "manifest.json"

            rows = write_internal_manifest(root, output)

            self.assertEqual(rows, [{
                "path": "evidence.txt",
                "bytes": 9,
                "sha256": hashlib.sha256(b"evidence\n").hexdigest(),
            }])
            self.assertEqual(json.loads(output.read_text()), rows)

    def test_builds_valid_conservative_artifact_and_economics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payloads = {
                "gpu.csv": (b"gpu\n", "gpu_samples"),
                "requests.jsonl": (json.dumps({
                    "request_id": "request-1",
                    "completed": True,
                    "slo_eligible": True,
                    "slo_compliant": True,
                    "error": False,
                    "silent_truncation": False,
                    "input_tokens": 800000,
                    "output_tokens": 200000,
                    "ttft_ms": 2,
                    "inter_token_latency_ms": 2,
                    "end_to_end_ms": 3,
                }).encode() + b"\n", "request_outcomes"),
                "scheduler.jsonl": (b"{}\n", "scheduler_samples"),
                "startup.json": (b"{}\n", "startup_timings"),
                "billing.json": (b"{}\n", "provider_billing"),
                "profiler.json": (b"{}\n", "profiler_trace"),
            }
            for name, (content, _) in payloads.items():
                (root / name).write_bytes(content)
            artifact, economics = build_artifact(
                bundle_root=root,
                raw_kinds={name: kind for name, (_, kind) in payloads.items()},
                identity={
                    "artifact_id": "stock-1",
                    "experiment_spec_sha256": "1" * 64,
                    "workload_sha256": "2" * 64,
                    "model": {"model_id": "zai-org/GLM-4.7-Flash", "checkpoint_revision": "rev", "tokenizer_revision": "tok", "representation": "bf16"},
                    "runtime": {"name": "sglang", "source_revision": "src", "image_digest": "sha256:" + "3" * 64, "command_sha256": "4" * 64},
                    "hardware": {"provider": "runpod", "cloud_class": "secure", "gpu_model": "H100", "gpu_count": 1, "machine_id": "m"},
                },
                allocation={
                    "provider_allocation_id": "p", "started_at": "2026-07-13T00:00:00Z", "ended_at": "2026-07-13T00:10:00Z",
                    "allocation_seconds": 600, "hourly_price_usd": 2.99, "provider_reported_cost_usd": 0.49,
                },
                metrics={
                    "requests_scheduled": 1, "requests_completed": 1, "requests_slo_eligible": 1, "requests_slo_compliant": 1,
                    "errors": 0, "silent_truncations": 0, "input_tokens": 800000, "output_tokens": 200000,
                    "slo_input_tokens": 800000, "slo_output_tokens": 200000, "wall_seconds": 600,
                    "input_tokens_per_second": 1333.333, "output_tokens_per_second": 333.333,
                    "total_tokens_per_second": 1666.666, "completed_request_goodput_per_second": 0.001667,
                    "latency_ms": {"ttft": {"p50": 1, "p95": 2, "p99": 3}, "inter_token": {"p50": 1, "p95": 2, "p99": 3}, "end_to_end": {"p50": 1, "p95": 2, "p99": 3}},
                },
                telemetry={
                    "cadence_seconds": 1,
                    "gpu": {name: {"p50": 1, "p95": 2, "p99": 3} for name in ("utilization_percent", "vram_used_bytes", "power_watts", "temperature_celsius", "sm_clock_mhz", "memory_clock_mhz")},
                    "memory_throughput": {"status": "unsupported", "metric_name": None, "value": None, "unit": None},
                    "scheduler": {"iteration_count": 1, "batch_size": {"p50": 1, "p95": 1, "p99": 1}, "prefill_tokens": 800000, "decode_tokens": 200000, "kv_allocated_tokens_peak": 1, "prefix_cache_hits": 0, "prefix_cache_misses": 1},
                    "startup": {"container_seconds": 1, "model_load_seconds": 1, "cache_allocation_seconds": 1, "server_ready_seconds": 3},
                    "profiler": {"capture_seconds": 1, "overhead_percent": 1, "trace_sha256": hashlib.sha256(payloads["profiler.json"][0]).hexdigest(), "top_kernels": [{"name": "k", "time_share_fraction": 1}]},
                },
                teardown={"delete_requested_at": "2026-07-13T00:10:00Z", "delete_http_status": 204, "get_http_status": 404, "verified_at": "2026-07-13T00:10:01Z", "verification": "not_found", "watchdog_log_sha256": "5" * 64},
                validated_at="2026-07-13T00:11:00Z",
                input_token_weight="0.25",
                non_gpu_sensitivity_fraction="0.20",
            )
            artifact_path = root / "artifact.json"
            artifact_path.write_text(json.dumps(artifact))
            validate_gpu_artifact(artifact_path, root)
            self.assertEqual(artifact["allocation"]["conservative_cost_usd"], 0.49833333333333335)
            self.assertEqual(economics["gpu_cost_usd"], "0.4983333333333333333333333333")


if __name__ == "__main__":
    unittest.main()
