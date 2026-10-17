import ast
import importlib.metadata
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from checkpoint_paths import validated_checkpoint_files


class CheckpointPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "checkpoint"
        self.root.mkdir()

    def test_regular_shards_are_sorted_deduplicated_and_keep_their_suffix(self):
        (self.root / "nested").mkdir()
        for name in ["a.safetensors", "nested/b.bin"]:
            (self.root / name).write_bytes(b"synthetic")
        result = validated_checkpoint_files(
            self.root, ["nested/b.bin", "a.safetensors", "a.safetensors"]
        )
        self.assertEqual(
            result, [str(self.root / "a.safetensors"), str(self.root / "nested/b.bin")]
        )

    def test_traversal_absolute_and_non_string_entries_fail_before_file_checks(self):
        outside = Path(self.temp.name) / "outside.bin"
        outside.write_bytes(b"synthetic")
        with patch(
            "checkpoint_paths.os.path.isfile",
            side_effect=AssertionError("file check reached"),
        ):
            for name in ["../outside.bin", str(outside), "", 1, None, [], {}]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validated_checkpoint_files(self.root, [name])

    def test_directory_missing_file_and_fifo_are_rejected_without_opening(self):
        fifo = self.root / "pipe.bin"
        os.mkfifo(fifo)
        with patch("builtins.open", side_effect=AssertionError("checkpoint opened")):
            for name in [".", "missing.bin", "pipe.bin"]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validated_checkpoint_files(self.root, [name])

    def test_external_regular_file_symlink_is_rejected(self):
        outside = Path(self.temp.name) / "outside.bin"
        outside.write_bytes(b"synthetic")
        (self.root / "shard.bin").symlink_to(outside)
        with self.assertRaises(ValueError):
            validated_checkpoint_files(self.root, ["shard.bin"])

    def test_internal_symlink_is_accepted(self):
        (self.root / "target.bin").write_bytes(b"synthetic")
        (self.root / "shard.bin").symlink_to("target.bin")
        self.assertEqual(
            validated_checkpoint_files(self.root, ["shard.bin"]),
            [str(self.root / "shard.bin")],
        )

    def test_huggingface_blob_links_are_allowed_without_losing_file_extensions(self):
        repo = Path(self.temp.name) / "models--example--model"
        snapshot = repo / "snapshots" / ("a" * 40)
        snapshot.mkdir(parents=True)
        blobs = repo / "blobs"
        blobs.mkdir()
        (blobs / "hash").write_bytes(b"synthetic")
        (snapshot / "shard.safetensors").symlink_to("../../blobs/hash")
        self.assertEqual(
            validated_checkpoint_files(snapshot, ["shard.safetensors"]),
            [str(snapshot / "shard.safetensors")],
        )
        with self.assertRaises(ValueError):
            validated_checkpoint_files(snapshot, ["../../blobs/hash"])

    def test_huggingface_cache_cannot_relabel_an_external_directory_as_blobs(self):
        repo = Path(self.temp.name) / "models--example--model"
        snapshot = repo / "snapshots" / ("a" * 40)
        snapshot.mkdir(parents=True)
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "hash").write_bytes(b"synthetic")
        (repo / "blobs").symlink_to(outside, target_is_directory=True)
        (snapshot / "shard.bin").symlink_to("../../blobs/hash")
        with self.assertRaises(ValueError):
            validated_checkpoint_files(snapshot, ["shard.bin"])

    def test_package_guard_matches_tested_source_and_runs_before_state_loading(self):
        try:
            distribution = importlib.metadata.distribution("accelerate")
        except importlib.metadata.PackageNotFoundError:
            if os.environ.get("GRADIATED_REQUIRE_ACCELERATE_GUARD") == "1":
                self.fail("The packaged Accelerate guard must be present")
            self.skipTest("Accelerate is not installed in this development environment")
        installed = distribution.locate_file(
            "accelerate/utils/gradiated_checkpoint_paths.py"
        )
        self.assertEqual(
            Path(installed).read_bytes(),
            Path(__file__).with_name("checkpoint_paths.py").read_bytes(),
        )
        tree = ast.parse(
            Path(distribution.locate_file("accelerate/utils/modeling.py")).read_text()
        )
        loader = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "load_checkpoint_in_model"
        )
        calls = [
            node
            for node in ast.walk(loader)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        guard = [node for node in calls if node.func.id == "validated_checkpoint_files"]
        loads = [node for node in calls if node.func.id == "load_state_dict"]
        self.assertEqual(len(guard), 1)
        self.assertTrue(loads)
        self.assertTrue(all(guard[0].lineno < node.lineno for node in loads))


@unittest.skipUnless(
    os.environ.get("GRADIATED_REQUIRE_ACCELERATE_GUARD") == "1",
    "Full runtime build runs the real CPU loader integration",
)
class PackagedLoaderTests(unittest.TestCase):
    def test_sharded_safetensors_cache_loads_on_cpu(self):
        import torch
        from accelerate.utils.modeling import load_checkpoint_in_model
        from safetensors.torch import save_file

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "models--example--model"
            snapshot = repo / "snapshots" / ("a" * 40)
            snapshot.mkdir(parents=True)
            (repo / "blobs").mkdir()
            expected = torch.arange(4, dtype=torch.float32).reshape(2, 2)
            save_file(
                {"weight": expected},
                str(repo / "blobs" / "hash"),
                metadata={"format": "pt"},
            )
            (snapshot / "shard.safetensors").symlink_to("../../blobs/hash")
            index = snapshot / "model.safetensors.index.json"
            index.write_text('{"weight_map":{"weight":"shard.safetensors"}}')
            model = torch.nn.Linear(2, 2, bias=False)
            load_checkpoint_in_model(model, str(index), device_map={"": "cpu"})
            self.assertTrue(torch.equal(model.weight, expected))

    def test_real_loader_rejects_traversal_and_fifo_before_reading_shards(self):
        import torch
        from accelerate.utils.modeling import load_checkpoint_in_model

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "checkpoint"
            folder.mkdir()
            os.mkfifo(folder / "pipe.bin")
            index = folder / "model.bin.index.json"
            for name in ["../outside.bin", "pipe.bin"]:
                index.write_text('{"weight_map":{"weight":"' + name + '"}}')
                with self.subTest(name=name), patch(
                    "accelerate.utils.modeling.load_state_dict",
                    side_effect=AssertionError("untrusted shard read"),
                ), self.assertRaises(ValueError):
                    load_checkpoint_in_model(
                        torch.nn.Linear(2, 2, bias=False),
                        str(index),
                        device_map={"": "cpu"},
                    )
