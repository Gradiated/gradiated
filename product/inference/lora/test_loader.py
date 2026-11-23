import concurrent.futures
import copy
import json
import math
import tempfile
import threading
import unittest
import urllib.error
import uuid
from pathlib import Path
from unittest import mock

from fixtures import (
    archive,
    cartridge_file,
    cartridge_grant,
    cartridge_model_config,
    grant,
    settings,
)
from loader import CANARY_TIMEOUT_SECONDS, CapacityError, CartridgeNotApplied, Loader
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

    def fetch(self, spec, path, hosts, deadline=None):
        self.fetches += 1
        path.write_bytes(self.payload)

    def engine(self, method, path, body=None):
        self.commands.append((method, path, body))
        if path == "/v1/models":
            return json.dumps({"data": [{"id": name} for name in self.models]}).encode()
        if path == "/load_lora_adapter":
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
        with (
            self.assertLogs("loader", level="WARNING") as captured,
            self.assertRaises(urllib.error.HTTPError),
        ):
            self.loader.resolve_version("version", str(uuid.uuid4()))
        event = json.loads(captured.records[-1].getMessage())
        self.assertEqual(event["error_type"], "HTTPError")
        self.assertEqual(event["upstream_status"], 401)
        self.assertNotIn("private-secret", json.dumps(event))
        self.assertEqual(self.loader.counters["failures"], 1)
        self.assertGreater(self.loader.last_failure, 0)

    def test_grant_receives_deadline_and_late_grant_never_downloads(self):
        import time

        spec = grant(self.payload)

        def resolve(name, workspace, deadline):
            self.assertGreater(deadline, time.monotonic())
            return spec

        self.loader.resolve = resolve
        with (
            mock.patch("loader.remaining", side_effect=TimeoutError),
            self.assertRaises(TimeoutError),
        ):
            self.loader.resolve_version(spec["version"]["name"], spec["workspace_id"])
        self.assertEqual(self.fetches, 0)
        self.assertEqual(self.loader.entries, {})

    def test_file_failure_is_counted_once_and_capacity_is_separate(self):
        spec = grant(self.payload)
        self.loader.resolve = lambda *_: spec
        self.loader.fetch = mock.Mock(side_effect=ValueError("private-secret"))
        with (
            self.assertLogs("loader", level="WARNING") as captured,
            self.assertRaises(ValueError),
        ):
            self.loader.resolve_version(spec["version"]["name"], spec["workspace_id"])
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

    def test_three_distinct_cold_preparations_wait_instead_of_rejecting(self):
        registered = [self.register() for _ in range(3)]
        started, release = threading.Event(), threading.Event()
        barrier = threading.Barrier(4)
        original = self.loader.fetch

        def fetch(*args):
            started.set()
            if not release.wait(5):
                raise TimeoutError("Synthetic test timed out")
            original(*args)

        def prepare(item):
            name, spec = item
            barrier.wait(timeout=5)
            return self.loader.prepare(name, spec["workspace_id"])

        self.loader.fetch = fetch
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(prepare, item) for item in registered]
            try:
                barrier.wait(timeout=5)
                self.assertTrue(started.wait(2))
                done, _ = concurrent.futures.wait(
                    futures,
                    timeout=0.1,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                self.assertFalse(done, "Cold preparation should wait for admission")
            finally:
                release.set()
            for future in futures:
                future.result(timeout=5)
        self.assertEqual(self.fetches, 3)
        self.assertEqual(len(self.models), 3)

    def test_cold_preparation_shares_deadline_between_waits_and_download(self):
        name, spec = self.register()
        clock = [90.0]
        admission, loading = mock.Mock(), mock.Mock()
        self.loader.admission, self.loader.loading = admission, loading

        def acquire(delay):
            def wait(**kwargs):
                clock[0] += delay
                return True

            return wait

        admission.acquire.side_effect = acquire(4)
        loading.acquire.side_effect = acquire(3)
        original = self.loader.fetch
        self.loader.fetch = mock.Mock(side_effect=original)
        with mock.patch("loader.time.monotonic", side_effect=lambda: clock[0]):
            self.loader.resolve_files(name, spec["workspace_id"], deadline=100)
        admission.acquire.assert_called_once_with(timeout=10)
        loading.acquire.assert_called_once_with(timeout=6)
        self.assertEqual(self.loader.fetch.call_args.args[3], 100)
        admission.release.assert_called_once()
        loading.release.assert_called_once()

    def test_queued_deadline_is_failure_instead_of_cache_capacity(self):
        name, spec = self.register()
        for blocked in ["admission", "loading"]:
            with self.subTest(blocked=blocked):
                admission, loading = mock.Mock(), mock.Mock()
                admission.acquire.return_value = blocked != "admission"
                loading.acquire.return_value = blocked != "loading"
                self.loader.admission, self.loader.loading = admission, loading
                with (
                    self.assertLogs("loader", level="WARNING"),
                    self.assertRaises(TimeoutError),
                ):
                    self.loader.operation(
                        "resolve",
                        lambda: self.loader.resolve_files(
                            name, spec["workspace_id"], 0
                        ),
                    )
                self.assertEqual(self.loader.last_capacity_rejection, 0)
                self.assertEqual(self.fetches, 0)
        self.assertEqual(self.loader.counters["failures"], 2)

    def test_native_cpu_capacity_does_not_limit_registration_or_trigger_unload(self):
        for _ in range(3):
            name, spec = self.register()
            self.loader.prepare(name, spec["workspace_id"])
        self.assertEqual(len(self.models), 3)
        self.assertEqual(self.config["cpu_adapter_slots"], 1)
        self.assertTrue(
            all(path == "/load_lora_adapter" for _, path, _ in self.commands)
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
            if path == "/load_lora_adapter":
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
        _second, spec = self.register()
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

    def test_validated_serving_revision_preserves_declared_training_provenance(self):
        spec = grant(self.payload)
        spec["version"]["adapter"]["base_model_revision"] = "different-training-revision"
        spec["version"]["adapter"]["validated_base_model_revision"] = self.config["base_model_revision"]
        name = self.loader.register_metadata(spec)
        self.assertEqual(self.loader.entries[name]["spec"]["version"]["adapter"]["base_model_revision"], "different-training-revision")
        spec["version"]["adapter"]["validated_base_model_revision"] = "wrong-serving-revision"
        with self.assertRaises(ValueError):
            self.loader.register_metadata(spec)
        self.assertEqual(self.fetches, 0)

    def test_startup_preloads_only_up_to_native_cpu_count(self):
        specs = [grant(self.payload) for _ in range(3)]
        names = {spec["version"]["name"]: spec for spec in specs}
        self.loader.resolve = lambda name, workspace, deadline=None: names[name]
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


class CartridgeLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = {**settings(), "model_config": cartridge_model_config()}
        self.payload = cartridge_file()
        self.fetches = 0
        self.commands = []
        self.loader = Loader(self.config, self.temp.name, 1, set(), fetch=self.fetch)
        self.loader.ready = True
        self.loader.engine = self.engine

    def fetch(self, spec, path, hosts, deadline=None):
        self.fetches += 1
        path.write_bytes(self.payload)

    def engine(self, method, path, body=None):
        self.commands.append((method, path, body))
        return b"ok"

    def test_resolution_returns_the_cartridge_kind_and_verified_path(self):
        spec = cartridge_grant(self.payload)
        self.loader.resolve = lambda name, workspace, deadline=None: spec

        files = self.loader.resolve_version(spec["version"]["name"], spec["workspace_id"])

        self.assertEqual(files["kind"], "cartridge")
        self.assertEqual(files["sha256"], spec["version"]["adapter"]["sha256"])
        self.assertEqual(files["num_tokens"], 3)
        self.assertEqual(Path(files["path"]).read_bytes(), self.payload)
        self.assertEqual(
            self.loader.resolve_version(spec["version"]["name"], spec["workspace_id"]),
            files,
        )
        self.assertEqual(self.fetches, 1)

    def test_preparation_never_registers_a_cartridge_as_a_lora_adapter(self):
        spec = cartridge_grant(self.payload)
        self.loader.resolve = lambda name, workspace, deadline=None: spec

        self.loader.prepare_version(spec["version"]["name"], spec["workspace_id"])

        self.assertEqual(self.commands, [])
        self.assertEqual(self.loader.status()["registered_adapters"], 0)

    def test_cartridges_need_the_pinned_model_dimensions(self):
        spec = cartridge_grant(self.payload, hidden=8)
        with self.assertRaises(ValueError):
            self.loader.register_metadata(spec)

        self.loader.config = {**self.config, "model_config": {"num_hidden_layers": 2}}
        with self.assertRaises(ValueError):
            self.loader.register_metadata(cartridge_grant(self.payload))

    def test_lora_versions_still_require_a_valid_rank(self):
        spec = grant(archive())
        spec["version"]["adapter"]["rank"] = 0
        with self.assertRaises(ValueError):
            self.loader.register_metadata(spec)

        del spec["version"]["adapter"]["rank"]
        with self.assertRaises(KeyError):
            self.loader.register_metadata(spec)

    def test_cartridge_disk_budget_evicts_unpinned_files_only(self):
        first = cartridge_grant(self.payload)
        self.loader.resolve = lambda name, workspace, deadline=None: first
        files = self.loader.resolve_version(first["version"]["name"], first["workspace_id"])

        self.loader.config = {
            **self.config,
            "disk_cache_bytes": len(self.payload) + 4096 + 128,
        }
        second = cartridge_grant(self.payload)
        self.loader.resolve = lambda name, workspace, deadline=None: second
        with self.assertRaises(CapacityError):
            self.loader.resolve_version(second["version"]["name"], second["workspace_id"])
        self.assertTrue(Path(files["path"]).is_file())


class CartridgeCanaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.payload = cartridge_file()
        self.spec = cartridge_grant(self.payload)
        self.loader = Loader(
            {**settings(), "model_config": cartridge_model_config()},
            self.temp.name,
            1,
            set(),
            fetch=lambda spec, path, hosts, deadline=None: path.write_bytes(self.payload),
        )
        self.loader.ready = True
        self.loader.resolve = lambda name, workspace, deadline=None: self.spec
        self.adapter = f"{self.spec['workspace_id']}/{self.spec['version']['name']}"
        self.models = [{"id": "base-model"}, {"id": "other/lora", "parent": "base-model"}]
        self.outputs = {}
        self.timeouts = []
        self.loader.engine = self.engine

    @staticmethod
    def position(token, *top):
        top_logprobs = [{"token": t, "logprob": math.log(p)} for t, p in top]
        return {"token": token, "top_logprobs": top_logprobs}

    def engine(self, method, path, body=None, timeout=None):
        self.timeouts.append(timeout)
        if path == "/v1/models":
            return json.dumps({"data": self.models}).encode()
        content = self.outputs.get(body["model"]) if body.get("logprobs") else None
        return json.dumps({"model": body["model"], "choices": [{"logprobs": {"content": content}}],
                           "usage": {"completion_tokens": 1}}).encode()

    def probe(self):
        self.loader.probe(self.spec["version"]["name"], self.spec["workspace_id"])

    def test_a_cartridge_passes_only_when_it_changes_the_canary_logits(self):
        base = [
            self.position("I", ("I", 0.6), ("We", 0.4)),
            self.position(" help", (" help", 0.9)),
        ]
        self.outputs = {"base-model": base, self.adapter: base}
        with self.assertRaises(CartridgeNotApplied):
            self.probe()

        self.outputs[self.adapter] = [self.position("I", ("I", 0.9), ("We", 0.1)), base[1]]
        self.probe()
        # A forced first token still passes once a later greedy token differs.
        self.outputs[self.adapter] = [base[0], self.position(" write", (" write", 0.9))]
        self.probe()
        # The two canary generations use the shorter budget the API's deadline counts.
        self.assertEqual(self.timeouts[-2:], [CANARY_TIMEOUT_SECONDS] * 2)

    def test_one_output_stopping_first_counts_as_a_change(self):
        base = [self.position("I", ("I", 0.6), ("We", 0.4)), self.position(".", (".", 0.9))]
        self.outputs = {"base-model": base, self.adapter: base[:1]}
        self.probe()
        self.outputs = {"base-model": base[:1], self.adapter: base}
        self.probe()

    def test_unreadable_canary_responses_are_a_retryable_runtime_fault(self):
        good = [self.position("I", ("I", 1.0))]
        self.outputs = {"base-model": good, self.adapter: good}
        engine = self.engine

        def truncated(method, path, body=None, timeout=None):
            if path == "/v1/models" or (body or {}).get("logprobs"):
                return b'{"choices": ['
            return engine(method, path, body, timeout)

        self.loader.engine = truncated
        with self.assertRaises(RuntimeError):
            self.probe()
        self.loader.engine = engine
        self.models = None
        with self.assertRaises(RuntimeError):
            self.probe()

    def test_malformed_canary_logprobs_are_a_retryable_runtime_fault(self):
        good = [self.position("I", ("I", 0.6), ("We", 0.4))]
        for broken in (
            [{"token": "I", "top_logprobs": None}],
            [{"token": "I", "top_logprobs": [{"token": "I"}]}],
            [{"token": "I", "top_logprobs": [{"logprob": -0.5}]}],
            [{"token": None, "top_logprobs": []}],
            [{"top_logprobs": []}],
            [None],
            [],
        ):
            self.outputs = {"base-model": good, self.adapter: broken}
            with self.subTest(broken=broken), self.assertRaises(RuntimeError):
                self.probe()

    def test_the_canary_needs_one_base_model_and_logprobs(self):
        base = [self.position("I", ("I", 1.0))]
        self.outputs = {"base-model": base, self.adapter: base}
        self.models = [{"id": "a"}, {"id": "b"}]
        with self.assertRaises(RuntimeError):
            self.probe()
        self.models = [{"id": "base-model"}]
        self.outputs = {"base-model": base}
        with self.assertRaises(RuntimeError):
            self.probe()


if __name__ == "__main__":
    unittest.main()
