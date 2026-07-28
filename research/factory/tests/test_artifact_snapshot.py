import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import unittest


TOOL = pathlib.Path(__file__).parents[1] / "tools" / "artifact-snapshot"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def archive(path: pathlib.Path, name: str, value: str) -> pathlib.Path:
    source = path / f"{name}.txt"
    source.write_text(value)
    output = path / f"{name}.tar.gz"
    with tarfile.open(output, "w:gz") as bundle:
        bundle.add(source, arcname="artifact.txt")
    return output


class ArtifactSnapshotTests(unittest.TestCase):
    def test_repeated_archive_reuses_content_addressed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = archive(root, "first", "one")
            snapshots = root / "snapshots"

            first = run("--archive", str(source), "--root", str(snapshots))
            second = run("--archive", str(source), "--root", str(snapshots))

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_value = json.loads(first.stdout)
            second_value = json.loads(second.stdout)
            self.assertFalse(first_value["idempotent"])
            self.assertTrue(second_value["idempotent"])
            self.assertEqual(first_value["destination"], second_value["destination"])
            self.assertEqual(
                pathlib.Path(first_value["destination"], "artifact.txt").read_text(),
                "one",
            )

    def test_changed_archive_gets_distinct_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            first_archive = archive(root, "first", "one")
            second_archive = archive(root, "second", "two")
            snapshots = root / "snapshots"

            first = run("--archive", str(first_archive), "--root", str(snapshots))
            second = run("--archive", str(second_archive), "--root", str(snapshots))

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            first_value = json.loads(first.stdout)
            second_value = json.loads(second.stdout)
            self.assertNotEqual(first_value["destination"], second_value["destination"])
            self.assertEqual(
                pathlib.Path(second_value["destination"], "artifact.txt").read_text(),
                "two",
            )

    def test_existing_unmarked_destination_fails_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            source = archive(root, "first", "one")
            snapshots = root / "snapshots"
            snapshots.mkdir()
            import hashlib

            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            conflict = snapshots / digest
            conflict.mkdir()
            sentinel = conflict / "keep.txt"
            sentinel.write_text("keep")

            result = run("--archive", str(source), "--root", str(snapshots))

            self.assertEqual(result.returncode, 2)
            self.assertIn("snapshot_destination_conflict", result.stderr)
            self.assertEqual(sentinel.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
