import concurrent.futures
import copy
import json
import tempfile
import threading
import unittest
import urllib.error
import uuid
from pathlib import Path
from unittest import mock

from fixtures import archive, grant, settings
from loader import CapacityError, Loader
from startup import start_preload


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = settings()
        self.payload = archive()
        self.fetches = 0
        self.commands = []
        self.models = set()
        self.loader = Loader(self.config, self.temp.name, 1, set(), fetch=self.fetch)
        self.loader.ready = True
        self.loader.engine = self.engine

    def fetch(self, spec, path, hosts):
        self.fetches += 1
        path.write_bytes(self.payload)

    def engine(self, method, path, body=None):
        self.commands.append((method, path, body))
        if path == "/v1/models":
            return json.dumps({"data": [{"id": name} for name in self.models]}).encode()
        if path == "/v1/load_lora_adapter":
            self.models.add(body["lora_name"])
        return b"ok"

    def register(self):
        spec = grant(self.payload)
        return self.loader.register_metadata(spec), spec

    def test_grant_failure_is_counted_and_logs_only_safe_error_fields(self):
        error = urllib.error.HTTPError(
            "https://api.example?credential=private-secret",
            401,
            "private-secret",
            {},
            None,
        )
        self.loader.resolve = mock.Mock(side_effect=error)
        with self.assertLogs("loader", level="WARNING") as captured:
            with self.assertRaises(urllib.error.HTTPError):
                self.loader.resolve_version("version", str(uuid.uuid4()))
        event = json.loads(captured.records[-1].getMessage())
        self.assertEqual(event["error_type"], "HTTPError")
        self.assertEqual(event["upstream_status"], 401)
        self.assertNotIn("private-secret", json.dumps(event))
        self.assertEqual(self.loader.counters["failures"], 1)
        self.assertGreater(self.loader.last_failure, 0)

    def test_file_failure_is_counted_once_and_capacity_is_separate(self):
        spec = grant(self.payload)
        self.loader.resolve = lambda *_: spec
        self.loader.fetch = mock.Mock(side_effect=ValueError("private-secret"))
        with self.assertLogs("loader", level="WARNING") as captured:
            with self.assertRaises(ValueError):
                self.loader.resolve_version(
                    spec["version"]["name"], spec["workspace_id"]
                )
        self.assertEqual(self.loader.counters["failures"], 1)
        self.assertNotIn("private-secret", "".join(captured.output))
        self.loader.ready = False
        with self.assertRaises(CapacityError):
            self.loader.resolve_version(spec["version"]["name"], spec["workspace_id"])
        self.assertEqual(self.loader.counters["failures"], 1)
        self.assertGreater(self.loader.last_capacity_rejection, 0)

    def test_preparation_is_coalesced_and_registered_paths_remain_available(self):
        name, spec = self.register()
        started, release = threading.Event(), threading.Event()
        original = self.loader.fetch

        def fetch(*args):
            started.set()
            if not release.wait(5):
                raise TimeoutError("Synthetic test timed out")
            original(*args)

        self.loader.fetch = fetch
        self.addCleanup(release.set)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(self.loader.prepare, name, spec["workspace_id"])
            self.assertTrue(started.wait(2))
            second = executor.submit(self.loader.prepare, name, spec["workspace_id"])
            release.set()
            first.result(timeout=5)
            second.result(timeout=5)
        self.loader.prepare(name, spec["workspace_id"])
        self.assertEqual(self.fetches, 1)
        self.assertEqual(len(self.commands), 1)
        self.assertTrue(
            (Path(self.temp.name) / name / "adapter_model.safetensors").is_file()
        )

    def test_native_cpu_capacity_does_not_limit_registration_or_trigger_unload(self):
        for _ in range(3):
            name, spec = self.register()
            self.loader.prepare(name, spec["workspace_id"])
        self.assertEqual(len(self.models), 3)
        self.assertEqual(self.config["cpu_adapter_slots"], 1)
        self.assertTrue(
            all(path == "/v1/load_lora_adapter" for _, path, _ in self.commands)
        )
        self.assertTrue(all(entry["pinned"] for entry in self.loader.entries.values()))
        self.assertFalse(hasattr(self.loader, "capacity"))

    def test_disk_pressure_never_deletes_registered_reload_paths(self):
        first, spec = self.register()
        self.loader.prepare(first, spec["workspace_id"])
        self.config["disk_cache_bytes"] = self.loader.status()["disk_cache_bytes"] + 64
        second, spec = self.register()
        with self.assertRaises(CapacityError):
            self.loader.prepare(second, spec["workspace_id"])
        self.assertTrue(
            (Path(self.temp.name) / first / "adapter_model.safetensors").is_file()
        )
        self.assertTrue(self.loader.ready)
        self.assertEqual(len(self.models), 1)

    def test_restart_reuses_verified_disk_and_starts_with_no_registered_adapters(self):
        name, spec = self.register()
        self.loader.prepare(name, spec["workspace_id"])
        second = Loader(self.config, self.temp.name, 1, set(), fetch=self.fetch)
        second.engine = self.engine
        second.ready = True
        second.register_metadata(spec)
        self.assertNotEqual(second.boot_id, self.loader.boot_id)
        self.assertFalse(second.entries[name]["pinned"])
        second.prepare(name, spec["workspace_id"])
        self.assertEqual(self.fetches, 1)
        self.assertEqual(len(self.commands), 2)

    def test_restart_can_evict_unregistered_disk_files(self):
        first, spec = self.register()
        self.loader.prepare(first, spec["workspace_id"])
        used = self.loader.disk_bytes()
        second, spec = self.register()
        self.loader.prepare(second, spec["workspace_id"])
        config = {**self.config, "disk_cache_bytes": used}
        restarted = Loader(config, self.temp.name, 1, set())
        self.assertLessEqual(restarted.disk_bytes(), used)
        self.assertEqual(
            sum(bool(entry["disk"]) for entry in restarted.entries.values()), 1
        )

    def test_failed_registration_pins_files_but_does_not_disable_base_or_restart_engine(
        self,
    ):
        name, spec = self.register()
        self.loader.engine = mock.Mock(side_effect=TimeoutError)
        with self.assertRaises(TimeoutError):
            self.loader.prepare(name, spec["workspace_id"])
        self.assertTrue(self.loader.entries[name]["pinned"])
        self.assertFalse(self.loader.entries[name]["registered"])
        self.assertTrue(self.loader.ready)
        self.models.add(f"{spec['workspace_id']}/{spec['version']['name']}")
        self.loader.engine = self.engine
        self.loader.prepare(name, spec["workspace_id"])
        self.assertTrue(self.loader.entries[name]["registered"])
        self.assertEqual(self.commands[-1][1], "/v1/models")

    def test_retry_handles_a_previous_registration_finishing_during_retry(self):
        name, spec = self.register()
        attempts = 0

        def engine(method, path, body=None):
            nonlocal attempts
            if path == "/v1/load_lora_adapter":
                attempts += 1
                if attempts == 1:
                    raise TimeoutError
                self.models.add(f"{spec['workspace_id']}/{spec['version']['name']}")
                raise ValueError("Already registered")
            return self.engine(method, path, body)

        self.loader.engine = engine
        with self.assertRaises(TimeoutError):
            self.loader.prepare(name, spec["workspace_id"])
        self.loader.prepare(name, spec["workspace_id"])
        self.assertTrue(self.loader.entries[name]["registered"])
        self.assertTrue(self.loader.entries[name]["pinned"])

    def test_runtime_rejection_keeps_exposed_files_pinned(self):
        name, spec = self.register()

        def engine(method, path, body=None):
            if method == "GET":
                return b'{"data":[]}'
            raise ValueError("Invalid module")

        self.loader.engine = engine
        with self.assertRaises(ValueError):
            self.loader.prepare(name, spec["workspace_id"])
        self.assertTrue(self.loader.entries[name]["pinned"])
        self.assertTrue(self.loader.ready)

    def test_bad_artifact_preserves_registered_paths_and_redacts_failure_logs(self):
        first, spec = self.register()
        self.loader.prepare(first, spec["workspace_id"])
        second, spec = self.register()
        self.loader.fetch = mock.Mock(side_effect=OSError("secret-url"))
        self.loader.resolve = lambda *_: spec
        with self.assertLogs(level="WARNING") as logs, self.assertRaises(OSError):
            self.loader.prepare_version(spec["version"]["name"], spec["workspace_id"])
        self.assertNotIn("secret-url", "".join(logs.output))
        self.assertTrue(self.loader.entries[first]["registered"])
        self.assertIn(b"gradiated_lora_failures_total 1", self.loader.metrics())

    def test_corrupt_recovered_disk_is_refetched(self):
        name, spec = self.register()
        self.loader.prepare(name, spec["workspace_id"])
        (Path(self.temp.name) / name / "adapter_model.safetensors").write_bytes(b"bad")
        restarted = Loader(self.config, self.temp.name, 1, set(), fetch=self.fetch)
        restarted.engine = self.engine
        restarted.ready = True
        restarted.register_metadata(spec)
        restarted.prepare(name, spec["workspace_id"])
        self.assertEqual(self.fetches, 2)

    def test_cached_registration_still_checks_workspace(self):
        name, spec = self.register()
        self.loader.prepare(name, spec["workspace_id"])
        with self.assertRaises(LookupError):
            self.loader.prepare(name, str(uuid.uuid4()))

    def test_immutable_metadata_allows_only_download_refresh(self):
        name, spec = self.register()
        refreshed = copy.deepcopy(spec)
        refreshed["download"]["url"] += "?fresh"
        self.assertEqual(self.loader.register_metadata(refreshed), name)
        refreshed["version"]["adapter"]["rank"] = 4
        with self.assertRaises(ValueError):
            self.loader.register_metadata(refreshed)

    def test_base_revision_mismatch_rejected_before_download(self):
        spec = grant(self.payload)
        spec["version"]["adapter"]["base_model_revision"] = "wrong"
        with self.assertRaises(ValueError):
            self.loader.register_metadata(spec)
        self.assertEqual(self.fetches, 0)

    def test_startup_preloads_only_up_to_native_cpu_count(self):
        specs = [grant(self.payload) for _ in range(3)]
        names = {spec["version"]["name"]: spec for spec in specs}
        self.loader.resolve = lambda name, workspace: names[name]
        start_preload(
            self.loader,
            lambda: [
                {
                    "version_name": spec["version"]["name"],
                    "workspace_id": spec["workspace_id"],
                }
                for spec in specs
            ],
        )
        self.assertEqual(len(self.models), 1)
        self.assertEqual(self.fetches, 1)


if __name__ == "__main__":
    unittest.main()
