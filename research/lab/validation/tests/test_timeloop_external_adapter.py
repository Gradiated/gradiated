import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from validation.timeloop_adapter.normalize import build_report


class TimeloopExternalAdapterTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("timeloopfe"), "timeloopfe is not installed"
    )
    def test_checked_problem_processes_with_pinned_v4_frontend(self) -> None:
        from timeloopfe.v4 import Specification

        root = Path(__file__).resolve().parents[2]
        specification = Specification.from_yaml_files(
            str(root / "configs/timeloop/qwen3-0.6b-o-proj-bf16-external-arch-v1.yaml"),
            str(
                root / "configs/timeloop/qwen3-0.6b-o-proj-bf16-external-mapper-v1.yaml"
            ),
            str(root / "experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.yaml"),
        )

        processed = specification._process()

        self.assertEqual(processed.problem.shape.name, "FoundryGemmBMNK")
        self.assertEqual(list(processed.problem.shape.dimensions), ["B", "M", "N", "K"])
        self.assertEqual(
            {key: processed.problem.instance[key] for key in ["B", "M", "N", "K"]},
            {"B": 1, "M": 1, "N": 1024, "K": 2048},
        )

    def test_normalizes_frontend_success_and_native_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._write_request(root)
            export = self._write_export(root)
            probe = self._write_probe(root)
            raw = root / "raw"
            raw.mkdir()
            (raw / "frontend.stdout").write_text(
                "FRONTEND_PARSE_OK\n", encoding="utf-8"
            )
            (raw / "frontend.stderr").write_text("", encoding="utf-8")
            (raw / "native.stdout").write_text(
                "Running apps: mapper\n", encoding="utf-8"
            )
            (raw / "native.stderr").write_text(
                "timeloop-mapper: command not found\n", encoding="utf-8"
            )
            probe_sha256 = hashlib.sha256(probe.read_bytes()).hexdigest()

            report = build_report(request, export, probe, raw)

        self.assertEqual(report["status"], "native_backend_blocked")
        self.assertEqual(report["reconciliation"]["multiply_accumulates"], 2_097_152)
        self.assertEqual(report["reconciliation"]["flops"], 4_194_304)
        self.assertEqual(report["reconciliation"]["total_tensor_bytes"], 4_200_448)
        self.assertTrue(report["reconciliation"]["exact_match"])
        self.assertEqual(report["runtime"]["frontend_parse_nanoseconds"], 2_000_000)
        self.assertEqual(report["runtime"]["native_probe_nanoseconds"], 3_000_000)
        self.assertEqual(len(report["input_artifacts"]), 3)
        self.assertEqual(
            report["source_identity"]["probe_sha256"],
            probe_sha256,
        )
        self.assertTrue(report["claims"]["frontend_parse_claim_permitted"])
        self.assertFalse(report["claims"]["native_mapping_claim_permitted"])
        self.assertFalse(report["claims"]["cycle_claim_permitted"])
        self.assertFalse(report["claims"]["calibration_claim_permitted"])
        self.assertFalse(report["claims"]["energy_claim_permitted"])
        self.assertFalse(report["claims"]["cost_claim_permitted"])
        self.assertIn(
            "native_dependency_missing:barvinok", report["claims"]["blockers"]
        )
        self.assertEqual(len(report["raw_artifacts"]), 4)
        self.assertEqual(len(report["content_identity_sha256"]), 64)

    def test_rejects_inexact_operation_accounting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._write_request(root)
            export = self._write_export(root)
            document = json.loads(export.read_text(encoding="utf-8"))
            document["accounting"]["flops"] = 4_194_305
            export.write_text(json.dumps(document), encoding="utf-8")
            probe = self._write_probe(root)
            raw = root / "raw"
            raw.mkdir()

            with self.assertRaisesRegex(ValueError, "FLOP accounting"):
                build_report(request, export, probe, raw)

    @staticmethod
    def _write_request(root: Path) -> Path:
        path = root / "request.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "inference-foundry.timeloop-external-smoke-request.v1",
                    "request_id": "test",
                    "problem_export_path": "export.json",
                    "problem_yaml_path": "problem.yaml",
                    "architecture_path": "arch.yaml",
                    "mapper_path": "mapper.yaml",
                    "frontend": {
                        "name": "timeloopfe",
                        "version": "0.4",
                        "revision": "5603893c0ff75183b5ffd6839aba33774fc3b6fe",
                    },
                    "accelergy": {
                        "name": "accelergy",
                        "version": "0.4",
                        "revision": "6911d15686ee7efdceba7d95605102df4472ae3a",
                    },
                    "native_backend": {
                        "name": "timeloop-mapper",
                        "repository": "https://github.com/NVlabs/timeloop",
                        "requested_revision": "32370826fdf1aa3c8deb0c93e6b2a2fc7cf053aa",
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _write_export(root: Path) -> Path:
        path = root / "export.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "content_id": "source-content-id",
                    "problem_dimensions": {"batch": 1, "m": 1, "n": 1024, "k": 2048},
                    "tensor_types": {
                        "input": "bf16",
                        "weight": "bf16",
                        "output": "bf16",
                        "accumulator": "fp32",
                    },
                    "accounting": {
                        "multiply_accumulates": 2_097_152,
                        "flops": 4_194_304,
                        "input_elements": 2_048,
                        "weight_elements": 2_097_152,
                        "output_elements": 1_024,
                        "input_bytes": 4_096,
                        "weight_bytes": 4_194_304,
                        "output_bytes": 2_048,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _write_probe(root: Path) -> Path:
        path = root / "probe.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "inference-foundry.timeloop-external-probe.v1",
                    "frontend": {
                        "status": "succeeded",
                        "runtime_nanoseconds": 2_000_000,
                        "shape_name": "FoundryGemmBMNK",
                        "dimensions": ["B", "M", "N", "K"],
                        "instance": {"B": 1, "M": 1, "N": 1024, "K": 2048},
                    },
                    "native_backend": {
                        "status": "executable_not_found",
                        "runtime_nanoseconds": 3_000_000,
                        "exit_code": 127,
                        "executable_path": None,
                    },
                    "environment": {
                        "platform": "macOS-15.6.1-arm64",
                        "machine": "arm64",
                        "python": "3.12.12",
                        "native_dependency_probe": {
                            "barvinok": {"found": False, "version": None}
                        },
                    },
                    "inputs": {
                        "architecture": {
                            "path": "arch.yaml",
                            "bytes": 1,
                            "sha256": "a" * 64,
                        },
                        "mapper": {
                            "path": "mapper.yaml",
                            "bytes": 1,
                            "sha256": "b" * 64,
                        },
                        "problem_yaml": {
                            "path": "problem.yaml",
                            "bytes": 1,
                            "sha256": "c" * 64,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
