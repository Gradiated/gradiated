from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from grad_research.profiling import (
    ProfilingError,
    analyze_profile,
    append_shape_record,
    build_capture_command,
    compare_profiles,
    run_capture,
)


class ProfilingTests(unittest.TestCase):
    def test_baseline_capture_preserves_output_and_redacts_manifest_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "kernel.ptx"
            artifact.write_text(".version 8.0")
            result = run_capture(
                tier="baseline",
                command=["python3", "-c", "print('measured')", "--token", "private-value"],
                output_root=Path(directory),
                timeout_seconds=10,
                sample_interval_seconds=0.1,
                sampler_command=None,
                artifact_paths=[artifact],
            )
            run_dir = Path(result["run_dir"])
            manifest = json.loads((run_dir / "profile_manifest.json").read_text())

            self.assertEqual(0, manifest["exit_code"])
            self.assertIn("measured", (run_dir / "command.stdout.log").read_text())
            self.assertNotIn("private-value", json.dumps(manifest))
            self.assertEqual("<redacted>", manifest["command"][-1])
            self.assertEqual(artifact.stat().st_size, manifest["artifacts"][0]["size_bytes"])
            self.assertEqual(64, len(manifest["artifacts"][0]["sha256"]))

    def test_deep_capture_builds_nsys_and_ncu_commands_without_a_shell(self) -> None:
        timeline = build_capture_command("timeline", ["python3", "serve.py"], Path("/tmp/run"))
        compute = build_capture_command(
            "compute",
            ["python3", "serve.py"],
            Path("/tmp/run"),
            kernel_name="gemm",
            launch_count=3,
        )

        self.assertEqual("nsys", timeline[0])
        self.assertIn("--trace=cuda,nvtx,osrt", timeline)
        self.assertEqual(["python3", "serve.py"], timeline[-2:])
        self.assertEqual("ncu", compute[0])
        self.assertIn("gemm", compute)
        self.assertIn("3", compute)
        self.assertEqual(["python3", "serve.py"], compute[-2:])

        amd_timeline = build_capture_command(
            "timeline", ["python3", "serve.py"], Path("/tmp/run"), backend="amd"
        )
        amd_compute = build_capture_command(
            "compute", ["python3", "serve.py"], Path("/tmp/run"), backend="amd", kernel_name="gemm"
        )
        self.assertEqual("rocprofv3", amd_timeline[0])
        self.assertIn("--runtime-trace", amd_timeline)
        self.assertEqual("rocprof-compute", amd_compute[0])
        self.assertIn("gemm", amd_compute)

    def test_analysis_uses_kernel_interval_union_and_joins_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "trace.json"
            trace.write_text(json.dumps({"traceEvents": [
                {"ph": "X", "cat": "kernel", "name": "dense_gemm", "ts": 0, "dur": 100},
                {"ph": "X", "cat": "kernel", "name": "dense_epilogue", "ts": 50, "dur": 100},
                {"ph": "X", "cat": "cpu_op", "name": "launch", "ts": 0, "dur": 20},
            ]}))
            samples = root / "gpu_samples.csv"
            with samples.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "timestamp_seconds", "utilization_gpu_percent", "memory_used_mib", "power_w"
                ])
                writer.writeheader()
                writer.writerows([
                    {"timestamp_seconds": 0, "utilization_gpu_percent": 50, "memory_used_mib": 1000, "power_w": 200},
                    {"timestamp_seconds": 1, "utilization_gpu_percent": 70, "memory_used_mib": 1200, "power_w": 300},
                ])
            semantics = root / "semantics.json"
            semantics.write_text(json.dumps({
                "schema_version": 1,
                "operations": [{
                    "id": "dense",
                    "phase": "decode",
                    "kernel_patterns": ["dense_"],
                    "shapes": {"m": 8, "n": 4096, "k": 4096},
                    "dtype": "fp16",
                }],
            }))

            summary = analyze_profile(
                run_dir=root,
                torch_trace=trace,
                semantics_path=semantics,
            )

            self.assertEqual(200.0, summary["timeline"]["kernel_sum_us"])
            self.assertEqual(150.0, summary["timeline"]["kernel_union_us"])
            self.assertEqual(1.0, summary["attribution"]["kernel_union_coverage"])
            self.assertEqual(250.0, summary["gpu"]["energy_joules"])
            self.assertEqual("decode", summary["semantics"]["operations"][0]["phase"])
            self.assertTrue((root / "profile_summary.json").exists())
            self.assertTrue((root / "profile_summary.md").exists())

    def test_analysis_reads_nsys_sqlite_and_ncu_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "report.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE StringIds (id INTEGER PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO StringIds VALUES (1, 'flash_attention')")
                connection.execute(
                    "CREATE TABLE CUPTI_ACTIVITY_KIND_KERNEL "
                    "(start INTEGER, end INTEGER, demangledName INTEGER, streamId INTEGER, correlationId INTEGER)"
                )
                connection.executemany(
                    "INSERT INTO CUPTI_ACTIVITY_KIND_KERNEL VALUES (?, ?, ?, ?, ?)",
                    [(0, 1000, 1, 7, 10), (500, 1500, 1, 7, 11)],
                )
            ncu = root / "ncu.csv"
            with ncu.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Kernel Name", "Metric Name", "Metric Unit", "Metric Value"])
                writer.writeheader()
                writer.writerows([
                    {"Kernel Name": "flash_attention", "Metric Name": "gpu__time_duration.sum", "Metric Unit": "us", "Metric Value": "42"},
                    {"Kernel Name": "flash_attention", "Metric Name": "dram__bytes_read.sum", "Metric Unit": "byte", "Metric Value": "1024"},
                ])

            summary = analyze_profile(run_dir=root, nsys_sqlite=database, ncu_csv=ncu)

            self.assertEqual(2.0, summary["timeline"]["kernel_sum_us"])
            self.assertEqual(1.5, summary["timeline"]["kernel_union_us"])
            self.assertEqual(42.0, summary["compute"]["kernels"][0]["metrics"]["gpu__time_duration.sum"]["value"])

    def test_analysis_reads_rocprof_kernel_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "kernel_trace.csv"
            with trace.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Kernel_Name", "Start_Timestamp", "End_Timestamp"])
                writer.writeheader()
                writer.writerows([
                    {"Kernel_Name": "hip_gemm", "Start_Timestamp": 0, "End_Timestamp": 1000},
                    {"Kernel_Name": "hip_epilogue", "Start_Timestamp": 500, "End_Timestamp": 1500},
                ])

            summary = analyze_profile(run_dir=root, rocprof_kernel_csv=trace)

            self.assertEqual("rocprofv3_kernel_csv", summary["timeline"]["source"])
            self.assertEqual(2.0, summary["timeline"]["kernel_sum_us"])
            self.assertEqual(1.5, summary["timeline"]["kernel_union_us"])

    def test_shape_atlas_is_append_only_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "atlas.json"
            atlas.write_text(json.dumps({"schema_version": 1, "records": []}))
            record = {
                "id": "l40s-dense-m8-n4096-k4096",
                "captured_at_utc": "2026-07-15T12:00:00Z",
                "evidence_type": "measured",
                "model": {"id": "glm-4.7-flash", "revision": "test"},
                "operation": {"family": "dense", "phase": "decode", "shapes": {"m": 8, "n": 4096, "k": 4096}, "dtype": "fp16"},
                "hardware": {"accelerator_id": "nvidia-l40s"},
                "software": {"runtime": "vllm", "kernel": "gemm"},
                "metrics": {"latency_us": 42.0},
                "artifacts": ["profile_summary.json"],
            }

            first = append_shape_record(atlas, record)
            second = append_shape_record(atlas, record)

            self.assertTrue(first["added"])
            self.assertFalse(second["added"])
            self.assertEqual(1, len(json.loads(atlas.read_text())["records"]))

    def test_benchmark_economics_and_profile_comparison_are_derived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_dir = root / "control"
            candidate_dir = root / "candidate"
            control_dir.mkdir()
            candidate_dir.mkdir()
            for run_dir, throughput in ((control_dir, 100.0), (candidate_dir, 125.0)):
                benchmark = run_dir / "benchmark.json"
                benchmark.write_text(json.dumps({
                    "output_tokens_per_second": throughput,
                    "gpu_hourly_usd": 2.95,
                    "output_tokens_total": 1000,
                }))
                analyze_profile(run_dir=run_dir, benchmark_path=benchmark)

            result = compare_profiles(
                control_dir / "profile_summary.json",
                candidate_dir / "profile_summary.json",
            )

            self.assertEqual(0.25, result["metrics"]["output_tokens_per_second"]["fraction_change"])
            self.assertEqual(-0.2, result["metrics"]["usd_per_million_output_tokens"]["fraction_change"])
            self.assertAlmostEqual(8.194444, result["control"]["usd_per_million_output_tokens"], places=6)

    def test_capture_rejects_empty_commands(self) -> None:
        with self.assertRaises(ProfilingError):
            build_capture_command("baseline", [], Path("/tmp/run"))


if __name__ == "__main__":
    unittest.main()
