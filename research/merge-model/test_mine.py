import gzip
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from freeze import CUTOFF, emit, load
from mine import aligned, conflict_hash, git, replay, segments


class MiningTest(unittest.TestCase):
    def test_ambiguous_boundary_is_rejected(self):
        s = [
            ("text", ["head\n"]),
            ("conflict", [[], [], []]),
            ("text", ["anchor\n"]),
            ("conflict", [[], [], []]),
            ("text", ["tail\n"]),
        ]
        self.assertIsNone(
            aligned(
                s, ["head\n", "a\n", "anchor\n", "x\n", "anchor\n", "b\n", "tail\n"]
            )
        )

    def test_requires_complete_diff3(self):
        self.assertIsNone(
            segments(["<<<<<<< ours\n", "a\n", "=======\n", "b\n", ">>>>>>> theirs\n"])
        )

    def test_swapping_sides_preserves_dedup_key(self):
        self.assertEqual(
            conflict_hash(["a\n"], [], ["b\n"]), conflict_hash(["b"], [], ["a"])
        )

    def test_replays_committed_resolution_for_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git(repo, "init", "-q", "-b", "main")
            git(repo, "config", "user.email", "fixture@example.invalid")
            git(repo, "config", "user.name", "fixture")
            file = repo / "with space.py"

            def commit(value):
                file.write_text(f"head\n{value}\ntail\n")
                git(repo, "add", "--", file.name)
                git(repo, "commit", "-qm", value)
                return git(repo, "rev-parse", "HEAD").stdout.decode().strip()

            commit("original")
            git(repo, "branch", "other")
            left = commit("left")
            git(repo, "switch", "-q", "other")
            right = commit("right")
            git(repo, "merge", "--no-edit", "main", allowed=(1,))
            merge = commit("both")
            meta = dict(repo="fixture/project", id=1, license="MIT", language="Python")
            counts, records = replay(repo, meta, merge, ("1", merge, right, left))
            self.assertEqual(counts["accepted_hunks"], 1)
            (row,) = records
            self.assertEqual(row["resolution"], ["both\n"])
            self.assertEqual(row["base"], ["original\n"])
            self.assertEqual(row["path"], file.name)
            self.assertEqual(row["parents"], [right, left])
            self.assertEqual(row["cls"], "new_lines")

    def test_freeze_excludes_ambiguous_labels_and_prefers_holdout(self):
        def row(repo, merge, sides, answer):
            ours, base, theirs = sides
            return {
                "repo": repo,
                "repo_id": repo,
                "merge": merge,
                "ts": CUTOFF - 1,
                "path": "main.py",
                "hunk_index": 0,
                "n_hunks_in_file": 1,
                "language": "Python",
                "license": "MIT",
                "subjects": {},
                "before": [],
                "after": [],
                "cls": "new_lines",
                "ours": ours,
                "base": base,
                "theirs": theirs,
                "resolution": answer,
                "hash": conflict_hash(ours, base, theirs),
            }

        duplicate = (["a\n"], [], ["b\n"])
        ambiguous = (["c\n"], [], ["d\n"])
        rows = [
            row("dotnet/runtime", "1", duplicate, ["ab\n"]),
            row("qemu/qemu", "2", duplicate[::-1], ["ba\n"]),
            row("dotnet/runtime", "3", ambiguous, ["cd\n"]),
            row("dotnet/runtime", "4", ambiguous, ["dc\n"]),
        ]
        with tempfile.TemporaryDirectory() as tmp, sqlite3.connect(":memory:") as db:
            path = Path(tmp)
            data = gzip.compress("".join(json.dumps(r) + "\n" for r in rows).encode())
            (path / "part.jsonl.gz").write_bytes(data)
            (path / "part.json").write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "gzip_sha256": hashlib.sha256(data).hexdigest(),
                        "counts": {"accepted_hunks": len(rows)},
                    }
                )
            )
            counts = load(path, db)
            self.assertEqual(counts["verified_shards"], 1)
            splits = emit(db, path, per_repo=10)
            self.assertEqual(splits["train"]["rows"], 0)
            self.assertEqual(splits["test_repo"]["repos"], {"qemu/qemu": 1})


if __name__ == "__main__":
    unittest.main()
