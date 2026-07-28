import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest


TOOL = pathlib.Path(__file__).parents[1] / "tools" / "manifest-pack"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def file_row(path: pathlib.Path, relative: str) -> dict[str, object]:
    value = path / relative
    return {
        "path": relative,
        "bytes": value.stat().st_size,
        "sha256": hashlib.sha256(value.read_bytes()).hexdigest(),
    }


class ManifestPackTests(unittest.TestCase):
    def test_list_manifest_drives_complete_archive_membership(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "source").mkdir()
            (root / "binding.json").write_text("{}\n")
            (root / "source" / "worker.py").write_text("result = 1\n")
            manifest = root / "PACKET_MANIFEST.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "files": [
                            file_row(root, "binding.json"),
                            file_row(root, "source/worker.py"),
                        ],
                    }
                )
            )
            archive = root / "packet.tar"

            result = run(
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--archive",
                str(archive),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["file_count"], 3)
            with tarfile.open(archive, "r:") as bundle:
                self.assertEqual(
                    sorted(bundle.getnames()),
                    ["PACKET_MANIFEST.json", "binding.json", "source/worker.py"],
                )

    def test_mapping_manifest_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            member = root / "runner.py"
            member.write_text("result = 1\n")
            manifest = root / "PACKET_MANIFEST.json"
            row = file_row(root, "runner.py")
            manifest.write_text(
                json.dumps(
                    {
                        "runner.py": {
                            "bytes": row["bytes"],
                            "sha256": row["sha256"],
                        }
                    }
                )
            )
            archive = root / "packet.tar"

            result = run(
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--archive",
                str(archive),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with tarfile.open(archive, "r:") as bundle:
                self.assertEqual(
                    sorted(bundle.getnames()),
                    ["PACKET_MANIFEST.json", "runner.py"],
                )

    def test_hash_mismatch_fails_without_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "worker.py").write_text("result = 1\n")
            manifest = root / "PACKET_MANIFEST.json"
            manifest.write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "path": "worker.py",
                                "bytes": 11,
                                "sha256": "0" * 64,
                            }
                        ]
                    }
                )
            )
            archive = root / "packet.tar"

            result = run(
                "--root",
                str(root),
                "--manifest",
                str(manifest),
                "--archive",
                str(archive),
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("manifest_hash_mismatch:worker.py", result.stderr)
            self.assertFalse(archive.exists())


if __name__ == "__main__":
    unittest.main()
