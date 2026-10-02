import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from launch import engine_settings


class LaunchTests(unittest.TestCase):
    def environment(self, tp):
        return {
            "MODEL_ID": "base",
            "NVIDIA_VISIBLE_DEVICES": ",".join(f"GPU-{index}" for index in range(tp)),
            "LORA_GPU_SLOTS": "2",
            "LORA_CPU_SLOTS": "8",
            "LORA_MAX_RANK": "8",
            "LORA_DISK_CACHE_BYTES": "2097152",
            "LORA_DOWNLOAD_HOSTS": "adapters.s3.amazonaws.com",
        }

    def command(self, tp):
        return [
            "python",
            "warmup-supervisor.py",
            "python",
            "-m",
            "vllm",
            "serve",
            "base-repository",
            "--revision",
            "base-revision",
            "--tensor-parallel-size",
            str(tp),
            "--max-num-seqs",
            "16",
        ]

    def test_tp_and_revision_come_from_the_existing_engine_command(self):
        for tp in (2, 4):
            settings, model, revision = engine_settings(
                self.command(tp), self.environment(tp), {"num_hidden_layers": 45}
            )
            self.assertEqual(settings["tensor_parallel_size"], tp)
            self.assertEqual(settings["model_config"]["num_hidden_layers"], 45)
            self.assertEqual((model, revision), ("base-repository", "base-revision"))

    def test_gpu_assignment_and_cache_budgets_are_checked_before_engine_start(self):
        for overrides in (
            {"NVIDIA_VISIBLE_DEVICES": "GPU-0"},
            {"LORA_DISK_CACHE_BYTES": "0"},
            {"LORA_GPU_SLOTS": "9"},
            {"LORA_CPU_SLOTS": "-1"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                engine_settings(
                    self.command(2), {**self.environment(2), **overrides}, {}
                )

    def test_empty_download_allowlist_is_rejected_before_engine_start(self):
        for value in (None, "", " , , "):
            environment = self.environment(2)
            environment.pop("LORA_DOWNLOAD_HOSTS")
            if value is not None:
                environment["LORA_DOWNLOAD_HOSTS"] = value
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "LORA_DOWNLOAD_HOSTS"),
            ):
                engine_settings(self.command(2), environment, {})

    def test_bundle_entrypoint_keeps_lora_disabled_and_uses_allocation_cache_when_enabled(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "python/bin/python3"
            binary.parent.mkdir(parents=True)
            binary.write_text(
                f"#!{sys.executable}\n"
                + 'import json,os,sys\nfrom pathlib import Path\nPath(os.environ["CAPTURE_FILE"]).write_text(json.dumps({"args":sys.argv[1:],"cache":os.environ.get("LORA_CACHE_DIR"),"mask":os.environ["CUDA_VISIBLE_DEVICES"],"runtime_url":os.environ["RUNTIME_URL"]}))\n'
            )
            binary.chmod(0o755)
            capture = root / "capture.json"
            token = root / "control-token"
            token.write_text("synthetic-control-token")
            environment = {
                **os.environ,
                "GRADIATED_RUNTIME_ROOT": str(root),
                "CAPTURE_FILE": str(capture),
                "NVIDIA_VISIBLE_DEVICES": "GPU-2,GPU-3,GPU-4,GPU-5",
                "TENSOR_PARALLEL_SIZE": "4",
                "RUNTIME_PORT": "8000",
                "ADAPTER_PORT": "8001",
                "WARMUP_PORT": "8002",
                "NOMAD_ALLOC_DIR": str(root / "allocation"),
                "LORA_CONTROL_TOKEN_FILE": str(token),
            }
            entrypoint = (
                Path(__file__).resolve().parents[1] / "bundles/glm-5-3-flash/entrypoint"
            )
            if not entrypoint.is_file():
                entrypoint = Path(__file__).resolve().parents[1] / "entrypoint"
            for enabled in (False, True):
                subprocess.run(
                    ["bash", str(entrypoint)],
                    env={**environment, "LORA_ENABLED": "true" if enabled else "false"},
                    check=True,
                    timeout=10,
                )
                result = json.loads(capture.read_text())
                self.assertEqual(result["args"][0].endswith("lora/launch.py"), enabled)
                self.assertEqual(
                    result["cache"], str(root / "allocation/lora") if enabled else None
                )
                self.assertEqual(result["mask"], environment["NVIDIA_VISIBLE_DEVICES"])
                self.assertIn("4", result["args"])
                self.assertEqual(result["runtime_url"], "http://127.0.0.1:8000")
                self.assertEqual(
                    result["args"][result["args"].index("--port") + 1], "8000"
                )


if __name__ == "__main__":
    unittest.main()
