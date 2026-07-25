from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from grad_research.science_tools.common import ScienceToolError
from grad_research.science_tools.surgery import main as surgery_main
from grad_research.science_tools.tool_catalog import main as catalog_main
from grad_research.science_tools.workspace import (
    ENV_NAME,
    MANIFEST_NAME,
    initialize,
    main as workspace_main,
)


def call(main, argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        returncode = main(argv)
    return returncode, stdout.getvalue(), stderr.getvalue()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value))


class SurgeryRunnerTests(unittest.TestCase):
    def test_resume_requires_matching_phase_and_output_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "surgery.json"
            output = root / "run"
            script = (
                "from pathlib import Path; "
                "p=Path('count.txt'); "
                "p.write_text(str((int(p.read_text()) if p.exists() else 0)+1)); "
                "Path('artifact.bin').write_bytes(b'expected')"
            )
            write_json(
                config,
                {
                    "phases": {
                        "capture": {
                            "argv": [sys.executable, "-c", script],
                            "cwd": ".",
                            "env": {},
                            "timeout_seconds": 5,
                            "expected_outputs": ["artifact.bin"],
                        }
                    }
                },
            )

            first, _, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )
            self.assertEqual(first, 0)
            self.assertEqual((root / "count.txt").read_text(), "1")
            terminal = json.loads(
                (output / "phases" / "capture" / "terminal.json").read_text()
            )
            self.assertEqual(terminal["status"], "succeeded")
            self.assertTrue((output / "phases" / "capture" / "command.stdout.log").is_file())
            self.assertEqual(len(terminal["outputs"][0]["sha256"]), 64)

            second, second_stdout, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )
            self.assertEqual(second, 0)
            self.assertEqual((root / "count.txt").read_text(), "1")
            self.assertEqual(json.loads(second_stdout)["outcomes"][0]["status"], "resumed")

            (root / "artifact.bin").write_bytes(b"changed")
            third, _, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )
            self.assertEqual(third, 0)
            self.assertEqual((root / "count.txt").read_text(), "2")
            self.assertEqual((root / "artifact.bin").read_bytes(), b"expected")

    def test_failure_is_local_and_later_phase_does_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "surgery.json"
            output = root / "run"
            write_json(
                config,
                {
                    "phases": {
                        "capture": {
                            "argv": [sys.executable, "-c", "raise SystemExit(7)"],
                            "cwd": ".",
                            "env": {},
                            "timeout_seconds": 5,
                        },
                        "replace": {
                            "argv": [
                                sys.executable,
                                "-c",
                                "from pathlib import Path; Path('bad').touch()",
                            ],
                            "cwd": ".",
                            "env": {},
                            "timeout_seconds": 5,
                        },
                    }
                },
            )

            returncode, _, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )
            self.assertEqual(returncode, 1)
            terminal = json.loads(
                (output / "phases" / "capture" / "terminal.json").read_text()
            )
            self.assertEqual(terminal["status"], "failed")
            self.assertEqual(terminal["command"]["returncode"], 7)
            self.assertFalse((root / "bad").exists())
            self.assertFalse((output / "phases" / "replace").exists())

    def test_dry_run_and_from_phase(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "surgery.json"
            output = root / "run"
            phase = lambda marker: {
                "argv": [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path({marker!r}).touch()",
                ],
                "cwd": ".",
                "env": {},
                "timeout_seconds": 5,
            }
            write_json(
                config,
                {"phases": {"capture": phase("capture"), "recover": phase("recover")}},
            )

            dry, dry_stdout, _ = call(
                surgery_main,
                [
                    "--config",
                    str(config),
                    "--output-dir",
                    str(output),
                    "--dry-run",
                ],
            )
            self.assertEqual(dry, 0)
            self.assertTrue(json.loads(dry_stdout)["dry_run"])
            self.assertFalse(output.exists())
            self.assertFalse((root / "capture").exists())

            write_json(config, {"phases": {"recover": phase("recover")}})
            run, _, _ = call(
                surgery_main,
                [
                    "--config",
                    str(config),
                    "--output-dir",
                    str(output),
                    "--from-phase",
                    "recover",
                ],
            )
            self.assertEqual(run, 0)
            self.assertFalse((root / "capture").exists())
            self.assertTrue((root / "recover").exists())

    def test_changed_upstream_output_invalidates_downstream_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "surgery.json"
            output = root / "run"
            capture_value = root / "capture-value.txt"
            capture_value.write_text("old")
            capture_script = (
                "from pathlib import Path; "
                "Path('capture.bin').write_text(Path('capture-value.txt').read_text())"
            )
            recover_script = (
                "from pathlib import Path; "
                "p=Path('recover-count.txt'); "
                "p.write_text(str((int(p.read_text()) if p.exists() else 0)+1)); "
                "Path('checkpoint.bin').write_text(Path('capture.bin').read_text())"
            )
            write_json(
                config,
                {
                    "phases": {
                        "capture": {
                            "argv": [sys.executable, "-c", capture_script],
                            "cwd": ".",
                            "env": {},
                            "timeout_seconds": 5,
                            "expected_outputs": ["capture.bin"],
                        },
                        "recover": {
                            "argv": [sys.executable, "-c", recover_script],
                            "cwd": ".",
                            "env": {},
                            "timeout_seconds": 5,
                            "expected_outputs": ["checkpoint.bin"],
                        },
                    }
                },
            )
            first, _, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )
            self.assertEqual(first, 0)
            self.assertEqual((root / "recover-count.txt").read_text(), "1")
            capture_value.write_text("new")
            (root / "capture.bin").unlink()

            second, _, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )

            self.assertEqual(second, 0)
            self.assertEqual((root / "recover-count.txt").read_text(), "2")
            self.assertEqual((root / "checkpoint.bin").read_text(), "new")

    def test_recovery_metrics_and_checkpoint_identity_are_captured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "surgery.json"
            output = root / "run"
            script = (
                "from pathlib import Path; "
                "Path('checkpoint.bin').write_bytes(b'checkpoint'); "
                "Path('curve.jsonl').write_text("
                "'{\\\"step\\\":1,\\\"loss\\\":2.0}\\n"
                "{\\\"step\\\":2,\\\"loss\\\":1.0}\\n')"
            )
            write_json(
                config,
                {
                    "phases": {
                        "recover": {
                            "argv": [sys.executable, "-c", script],
                            "cwd": ".",
                            "env": {},
                            "timeout_seconds": 5,
                            "expected_outputs": ["checkpoint.bin"],
                            "metrics_jsonl": "curve.jsonl",
                        }
                    }
                },
            )
            returncode, _, _ = call(
                surgery_main,
                ["--config", str(config), "--output-dir", str(output)],
            )
            self.assertEqual(returncode, 0)
            terminal = json.loads(
                (output / "phases" / "recover" / "terminal.json").read_text()
            )
            self.assertEqual(len(terminal["checkpoint_identities"]), 1)
            self.assertEqual([row["step"] for row in terminal["recovery_curve"]], [1, 2])
            self.assertTrue((output / "phases" / "recover" / "metrics.jsonl").is_file())


class WarmWorkspaceTests(unittest.TestCase):
    def test_init_record_env_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "warm"
            metadata = Path(directory) / "metadata.json"
            write_json(
                metadata,
                {
                    "hardware_identity": {"gpu": "H200", "count": 8},
                    "runtime_identity": {"name": "sglang", "commit": "abc"},
                    "checkpoint_identity": {"model": "gemma"},
                    "source_identity": {"commit": "def"},
                    "image_identity": {"digest": "sha256:123"},
                    "compatible_tags": ["cuda-12", "h200", "h200"],
                    "claim": {"project": "issue-27", "owner": "researcher-1"},
                },
            )
            old_secret = os.environ.get("LAB_TEST_SECRET_TOKEN")
            os.environ["LAB_TEST_SECRET_TOKEN"] = "must-not-leak"
            try:
                returncode, _, _ = call(
                    workspace_main,
                    ["init", "--workspace", str(root), "--metadata", str(metadata)],
                )
            finally:
                if old_secret is None:
                    os.environ.pop("LAB_TEST_SECRET_TOKEN", None)
                else:
                    os.environ["LAB_TEST_SECRET_TOKEN"] = old_secret
            self.assertEqual(returncode, 0)
            manifest = json.loads((root / MANIFEST_NAME).read_text())
            self.assertEqual(manifest["hardware_identity"]["gpu"], "H200")
            self.assertEqual(manifest["compatible_tags"], ["cuda-12", "h200"])
            env = (root / ENV_NAME).read_text()
            self.assertNotIn("must-not-leak", env)
            self.assertNotIn("LAB_TEST_SECRET_TOKEN", env)
            for name in (
                "HF_HOME",
                "TRITON_CACHE_DIR",
                "CUTE_DSL_CACHE_DIR",
                "TORCH_HOME",
                "TORCH_EXTENSIONS_DIR",
                "SCCACHE_DIR",
            ):
                self.assertIn(f"export {name}=", env)

            resident = root / "checkpoint" / "weights.bin"
            resident.parent.mkdir()
            resident.write_bytes(b"weights")
            recorded, _, _ = call(
                workspace_main,
                [
                    "record",
                    "--workspace",
                    str(root),
                    "--resident",
                    "checkpoint",
                    "--clear-claim",
                ],
            )
            self.assertEqual(recorded, 0)
            manifest = json.loads((root / MANIFEST_NAME).read_text())
            self.assertIsNone(manifest["claim"])
            self.assertEqual(manifest["resident_contents"][0]["file_count"], 1)
            self.assertEqual(len(manifest["resident_contents_sha256"]), 64)

            available = Path(sys.executable).name
            shown, stdout, _ = call(
                workspace_main,
                [
                    "status",
                    "--workspace",
                    str(root),
                    "--probe",
                    available,
                    "--probe",
                    "definitely-not-a-real-command-issue-27",
                ],
            )
            self.assertEqual(shown, 0)
            result = json.loads(stdout)
            self.assertTrue(result["commands"][available]["available"])
            self.assertFalse(
                result["commands"]["definitely-not-a-real-command-issue-27"][
                    "available"
                ]
            )
            self.assertIn("triton", result["caches"])

    def test_imported_api_rejects_secret_bearing_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ScienceToolError, "secret-bearing"):
                initialize(
                    Path(directory) / "warm",
                    {"claim": {"bearer": "sk-obvious-secret"}},
                )
            with self.assertRaisesRegex(ScienceToolError, "secret-bearing"):
                initialize(
                    Path(directory) / "jwt-workspace",
                    {
                        "claim": {
                            "note": (
                                "eyJhbGciOiJIUzI1NiJ9."
                                "eyJzdWIiOiJyZXNlYXJjaGVyIn0."
                                "dGVzdC1zaWduYXR1cmU"
                            )
                        }
                    },
                )


class ToolCatalogTests(unittest.TestCase):
    def test_filter_explain_and_safe_probe_without_external_tools(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            python = Path(sys.executable).name
            write_json(
                catalog,
                {
                    "schema_version": 1,
                    "tools": [
                        {
                            "id": "python",
                            "tier": "base",
                            "category": "build-download",
                            "platforms": ["cpu"],
                            "summary": "Python runtime.",
                            "probe": [python, "--version"],
                        },
                        {
                            "id": "missing",
                            "tier": "route",
                            "category": "kernel",
                            "platforms": ["nvidia"],
                            "summary": "Absent fixture.",
                            "probe": [
                                "definitely-not-a-real-command-issue-27",
                                "--version",
                            ],
                        },
                        {
                            "id": "paper",
                            "tier": "reference",
                            "category": "quality",
                            "platforms": ["cpu"],
                            "summary": "Reference only.",
                        },
                    ],
                },
            )

            listed, stdout, _ = call(
                catalog_main,
                [
                    "--catalog",
                    str(catalog),
                    "list",
                    "--tier",
                    "base",
                    "--json",
                ],
            )
            self.assertEqual(listed, 0)
            self.assertEqual([tool["id"] for tool in json.loads(stdout)], ["python"])

            explained, stdout, _ = call(
                catalog_main,
                ["--catalog", str(catalog), "explain", "paper"],
            )
            self.assertEqual(explained, 0)
            self.assertEqual(json.loads(stdout)["tier"], "reference")

            probed, stdout, _ = call(
                catalog_main,
                [
                    "--catalog",
                    str(catalog),
                    "probe",
                    "python",
                    "missing",
                ],
            )
            self.assertEqual(probed, 0)
            statuses = {
                result["id"]: result["status"] for result in json.loads(stdout)
            }
            self.assertEqual(statuses["python"], "available")
            self.assertEqual(statuses["missing"], "unavailable")

    def test_catalog_rejects_installing_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            write_json(
                catalog,
                {
                    "schema_version": 1,
                    "tools": [
                        {
                            "id": "unsafe",
                            "tier": "base",
                            "category": "build-download",
                            "platforms": ["cpu"],
                            "probe": ["python3", "install", "something"],
                        }
                    ],
                },
            )
            returncode, _, stderr = call(
                catalog_main,
                ["--catalog", str(catalog), "list", "--json"],
            )
            self.assertEqual(returncode, 2)
            self.assertIn("not read-only", stderr)


if __name__ == "__main__":
    unittest.main()
