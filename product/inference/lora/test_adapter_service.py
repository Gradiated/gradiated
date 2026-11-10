import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from adapter_service import (
    AdapterService,
    engine_arguments,
    engine_settings,
    resolver_environment,
)


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

    def test_tp_and_revision_come_from_the_runtime(self):
        for tp in (2, 4):
            settings = engine_settings(
                self.environment(tp), "base-revision", tp, {"num_hidden_layers": 45}
            )
            self.assertEqual(settings["tensor_parallel_size"], tp)
            self.assertEqual(settings["model_config"]["num_hidden_layers"], 45)
            self.assertEqual(settings["base_model_revision"], "base-revision")

    def test_gpu_assignment_and_cache_budgets_are_checked_before_engine_start(self):
        for overrides in (
            {"NVIDIA_VISIBLE_DEVICES": "GPU-0"},
            {"LORA_DISK_CACHE_BYTES": "0"},
            {"LORA_GPU_SLOTS": "9"},
            {"LORA_CPU_SLOTS": "-1"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                engine_settings({**self.environment(2), **overrides}, "r", 2, {})

    def test_qualified_training_revision_does_not_change_serving_checkpoint(self):
        environment = {**self.environment(2), "LORA_BASE_MODEL_REVISION": "bf16"}
        settings = engine_settings(environment, "serving-revision", 2, {})
        self.assertEqual(settings["base_model_revision"], "bf16")

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
                engine_settings(environment, "r", 2, {})

    def test_native_slots_rank_and_targets_become_sglang_flags(self):
        settings = engine_settings(self.environment(2), "r", 2, {})
        arguments = engine_arguments(settings, ["q_proj", "o_proj"])
        for flag, value in [
            ("--max-lora-rank", "8"),
            ("--max-loras-per-batch", "2"),
            ("--max-loaded-loras", "8"),
        ]:
            self.assertEqual(arguments[arguments.index(flag) + 1], value)
        self.assertIn("--enable-lora", arguments)
        self.assertEqual(
            arguments[arguments.index("--lora-target-modules") + 1 :],
            ["q_proj", "o_proj"],
        )

    def test_resolver_hook_points_at_the_loopback_adapter_port(self):
        result = resolver_environment({"ADAPTER_PORT": "18082", "OTHER": "kept"})
        self.assertEqual(
            result["SGLANG_LORA_RESOLVER_URL"],
            "http://127.0.0.1:18082/internal/adapters/resolve",
        )
        self.assertEqual(result["OTHER"], "kept")

    def test_service_rejects_colliding_ports_and_remote_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = {
                **self.environment(2),
                "ADAPTER_PORT": "18082",
                "RUNTIME_PORT": "18080",
                "WARMUP_PORT": "18083",
                "LORA_CACHE_DIR": str(Path(temporary) / "lora"),
                "GRADIATED_API_BASE_URL": "http://127.0.0.1:3004",
            }
            settings = engine_settings(base, "r", 2, {})
            for environment, port in [
                (base, 18082),
                ({**base, "GRADIATED_API_BASE_URL": "http://example.com"}, 18084),
            ]:
                with self.subTest(port=port), self.assertRaises(ValueError):
                    AdapterService(environment, settings, port)

    def test_service_answers_health_before_preload_without_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                **self.environment(2),
                "ADAPTER_PORT": "0",
                "RUNTIME_PORT": "18080",
                "WARMUP_PORT": "18083",
                "LORA_CACHE_DIR": str(Path(temporary) / "lora"),
                "GRADIATED_API_BASE_URL": "http://127.0.0.1:3004",
            }
            settings = engine_settings(environment, "r", 2, {})
            with self.assertRaises(ValueError):
                AdapterService(environment, settings, 18084)
            environment["ADAPTER_PORT"] = "18282"
            service = AdapterService(environment, settings, 18284)
            service.start(lambda: False)
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen("http://127.0.0.1:18282/health", timeout=5)
                self.assertEqual(error.exception.code, 503)
                self.assertEqual(json.loads(error.exception.read()), {"ready": False})
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
