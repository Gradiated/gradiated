import concurrent.futures
import copy
import http.client
import tarfile
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock

from artifacts import extract, validate_tensors
from fixtures import archive, grant, settings
from manager import CapacityError, Manager
from server import create_server
from startup import preload_production


class LoraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = settings()
        self.bytes = archive()
        self.fetches = 0
        self.commands = []

        def fetch(_spec, destination, _hosts):
            self.fetches += 1
            destination.write_bytes(self.bytes)

        self.manager = Manager(
            self.config, self.temp.name, 1, {"bucket.s3.amazonaws.com"}, fetch
        )
        self.manager.engine = lambda path, body: self.commands.append((path, body))

    def spec(self):
        return grant(self.bytes)

    def name(self, spec):
        return f"ft-{spec['version']['id']}-{spec['version']['adapter']['sha256']}"

    def register(self):
        spec = self.spec()
        self.manager.register(spec)
        return self.name(spec)

    def test_same_adapter_load_is_coalesced(self):
        name = self.register()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda _index: self.manager.prepare(name), range(8)))
        self.assertEqual(self.fetches, 1)
        self.assertEqual(len(self.commands), 1)
        self.assertLess(
            self.manager.status()["cpu_cache_bytes"], self.config["cpu_cache_bytes"]
        )

    def test_cpu_eviction_keeps_disk_hit_and_protects_active_requests(self):
        first, second = self.register(), self.register()
        with self.manager.request(first):
            with self.assertRaises(CapacityError):
                self.manager.prepare(second)
            with self.assertRaises(CapacityError):
                self.manager.remove(first)
        self.manager.prepare(second)
        self.manager.prepare(first)
        self.assertEqual(
            self.fetches, 2, "CPU miss should reuse the verified local archive"
        )
        self.assertEqual(
            sum(entry["cpu_resident"] for entry in self.manager.entries.values()), 1
        )

    def test_failed_disk_eviction_preserves_accounted_bytes(self):
        name = self.register()
        self.manager.prepare(name)
        before = self.manager.status()["disk_cache_bytes"]
        with (
            mock.patch("manager.shutil.rmtree", side_effect=PermissionError),
            self.assertRaises(PermissionError),
        ):
            self.manager.evict(name, disk=True)
        self.assertEqual(self.manager.status()["disk_cache_bytes"], before)

    def test_invalid_cold_artifact_does_not_evict_a_healthy_cpu_entry(self):
        first = self.register()
        self.manager.prepare(first)
        second = self.register()
        self.manager.fetch = lambda spec, path, hosts: path.write_bytes(b"bad")
        with self.assertRaises(ValueError):
            self.manager.prepare(second)
        self.assertTrue(self.manager.entries[first]["cpu_resident"])
        self.assertFalse(self.manager.failed)
        self.assertEqual(len(self.commands), 1)

    def test_cold_waiters_do_not_consume_base_or_hot_inference_capacity(self):
        self.config["max_concurrency"] = 1
        self.manager.capacity = threading.BoundedSemaphore(1)
        self.config["cpu_adapter_slots"] = 2
        hot = self.register()
        self.manager.prepare(hot)
        cold = self.register()
        started, release = threading.Event(), threading.Event()

        def fetch(spec, path, hosts):
            started.set()
            if not release.wait(5):
                raise TimeoutError("Synthetic download timed out")
            path.write_bytes(self.bytes)

        self.manager.fetch = fetch
        self.addCleanup(release.set)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:

            def request():
                with self.manager.request(cold):
                    pass

            future = executor.submit(request)
            self.assertTrue(started.wait(2))
            with (
                self.manager.request("base"),
                self.assertRaises(CapacityError),
                self.manager.request(hot),
            ):
                pass
            with self.manager.request(hot):
                pass
            release.set()
            future.result(timeout=5)
        self.assertEqual(self.manager.entries[hot]["active"], 0)

    def test_cold_queue_is_bounded_and_hot_requests_bypass_it(self):
        hot = self.register()
        self.manager.prepare(hot)
        cold = self.register()
        with self.manager.cold_requests, self.manager.cold_requests:
            with self.assertRaises(CapacityError), self.manager.request(cold):
                pass
            with self.manager.request("base"):
                pass
            with self.manager.request(hot):
                pass

    def test_failure_logs_do_not_include_exception_secrets(self):
        cold = self.register()
        self.manager.fetch = mock.Mock(side_effect=OSError("secret-download-url"))
        with self.assertLogs(level="WARNING") as logs, self.assertRaises(OSError):
            self.manager.prepare(cold)
        self.assertNotIn("secret-download-url", "".join(logs.output))
        self.assertIn(
            "gradiated_lora_failures_total 1", self.manager.metrics().decode()
        )

    def test_base_and_adapter_share_one_allocation_limit(self):
        name = self.register()
        with (
            self.manager.request("base"),
            self.manager.request(name),
            self.assertRaises(CapacityError),
            self.manager.request("base"),
        ):
            self.fail("Exceeded physical capacity")
        with self.manager.request("base"):
            pass

    def test_failed_request_releases_capacity_and_active_reference(self):
        name = self.register()
        with self.assertRaises(RuntimeError), self.manager.request(name):
            raise RuntimeError("Client cancelled")
        self.manager.remove(name)
        self.assertNotIn(name, self.manager.entries)

    def test_registration_only_refreshes_the_signed_grant(self):
        spec = self.spec()
        self.manager.register(spec)
        changed = copy.deepcopy(spec)
        changed["download"]["url"] += "?fresh=1"
        self.manager.register(changed)
        changed["version"]["adapter"]["rank"] = 4
        with self.assertRaises(ValueError):
            self.manager.register(changed)

    def test_partial_engine_failure_closes_adapter_admission(self):
        name = self.register()

        def fail(*_args):
            raise RuntimeError("Engine worker lost")

        self.manager.engine = fail
        with self.assertRaises(RuntimeError):
            self.manager.prepare(name)
        self.assertFalse(self.manager.status()["healthy"])
        with self.assertRaises(LookupError):
            self.manager.prepare(name)

    def test_archives_reject_links_traversal_and_excess_bytes(self):
        for name, kind in (
            ("../escape", tarfile.REGTYPE),
            ("adapter_config.json", tarfile.SYMTYPE),
            ("/absolute", tarfile.REGTYPE),
        ):
            with self.subTest(name=name):
                bad = tarfile.TarInfo(name)
                bad.type = kind
                bad.size = 1 if kind == tarfile.REGTYPE else 0
                bad.mode = 0o644
                path = Path(self.temp.name) / "hostile.tar.gz"
                path.write_bytes(archive(hostile=bad))
                target = Path(self.temp.name) / str(uuid.uuid4())
                target.mkdir()
                with self.assertRaises(ValueError):
                    extract(path, target, 1024 * 1024)
        path = Path(self.temp.name) / "large.tar.gz"
        path.write_bytes(self.bytes)
        target = Path(self.temp.name) / "small"
        target.mkdir()
        with self.assertRaises(ValueError):
            extract(path, target, 10)

    def test_tensor_rank_and_full_layer_coverage_are_checked(self):
        spec = self.spec()
        path = Path(self.temp.name) / "valid.tar.gz"
        path.write_bytes(self.bytes)
        target = Path(self.temp.name) / "valid"
        target.mkdir()
        extract(path, target, 1024 * 1024)
        validate_tensors(target, spec, self.config["model_config"])
        changed = copy.deepcopy(spec)
        model_config = {"num_hidden_layers": 3}
        with self.assertRaises(ValueError):
            validate_tensors(target, changed, model_config)

    def test_controller_admin_is_private_and_raw_vllm_admin_is_absent(self):
        server = create_server(self.manager, 0, "test-control-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        self.addCleanup(connection.close)
        for method, path, status in (
            ("GET", "/internal/adapters", 403),
            ("POST", "/v1/load_lora_adapter", 404),
            ("POST", "/v1/unload_lora_adapter", 404),
        ):
            connection.request(method, path)
            response = connection.getresponse()
            self.assertEqual(response.status, status)
            response.read()

    def test_restart_invalidates_cpu_readiness_and_preserves_disk(self):
        name = self.register()
        self.manager.prepare(name)
        replacement = Manager(self.config, self.temp.name, 1, set())
        self.assertNotEqual(replacement.boot_id, self.manager.boot_id)
        self.assertTrue(
            all(not entry["cpu_resident"] for entry in replacement.status()["adapters"])
        )
        self.assertTrue((Path(self.temp.name) / name).exists())
        self.assertLessEqual(
            replacement.status()["disk_cache_bytes"], self.config["disk_cache_bytes"]
        )

    def test_cold_request_fetches_a_grant_and_coalesces_the_s3_download(self):
        spec = self.spec()
        self.manager.resolve = lambda name, workspace: spec
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(
                executor.map(
                    lambda _index: self.manager.prepare(
                        self.name(spec), spec["workspace_id"]
                    ),
                    range(8),
                )
            )
        self.assertEqual(self.fetches, 1)
        with self.assertRaises(LookupError):
            self.manager.prepare(self.name(spec), str(uuid.uuid4()))

    def test_startup_preloads_to_capacity_without_evicting_earlier_production(self):
        specs = [self.spec(), self.spec(), self.spec()]
        by_name = {self.name(spec): spec for spec in specs}
        self.manager.resolve = lambda name, workspace: by_name[name]
        preload_production(
            self.manager,
            [
                {
                    "version_id": spec["version"]["id"],
                    "sha256": spec["version"]["adapter"]["sha256"],
                    "workspace_id": spec["workspace_id"],
                }
                for spec in specs
            ],
        )
        self.assertEqual(self.fetches, 1)
        self.assertTrue(self.manager.entries[self.name(specs[0])]["cpu_resident"])

    def test_cpu_byte_pressure_evicts_idle_tensors_but_keeps_disk(self):
        self.config["cpu_adapter_slots"] = 2
        self.config["cpu_cache_bytes"] = 350
        first, second = self.register(), self.register()
        self.manager.prepare(first)
        self.manager.prepare(second)
        self.assertFalse(self.manager.entries[first]["cpu_resident"])
        self.assertTrue((Path(self.temp.name) / first).is_dir())
        self.assertLessEqual(self.manager.used_bytes("cpu"), 350)

    def test_disk_pressure_preserves_cpu_resident_adapters(self):
        self.config["cpu_adapter_slots"] = 2
        first, second = self.register(), self.register()
        self.manager.prepare(first)
        self.config["disk_cache_bytes"] = self.manager.used_bytes("disk") + 4096
        self.manager.prepare(second)
        self.assertTrue(self.manager.entries[first]["cpu_resident"])
        self.assertEqual(self.manager.entries[first]["disk"], 0)
        self.assertFalse((Path(self.temp.name) / first).exists())
        self.manager.prepare(first)
        self.assertEqual(self.fetches, 2)
        self.assertLessEqual(
            self.manager.used_bytes("disk"), self.config["disk_cache_bytes"]
        )

    def test_restart_reuses_verified_disk_without_an_s3_download(self):
        spec = self.spec()
        self.manager.register(spec)
        self.manager.prepare(self.name(spec))
        replacement = Manager(
            self.config, self.temp.name, 1, set(), fetch=self.manager.fetch
        )
        replacement.engine = self.manager.engine
        replacement.register(spec)
        replacement.prepare(self.name(spec))
        self.assertEqual(self.fetches, 1)

    def test_restart_refetches_corrupted_disk_before_loading(self):
        spec = self.spec()
        self.manager.register(spec)
        name = self.name(spec)
        self.manager.prepare(name)
        (Path(self.temp.name) / name / "adapter_model.safetensors").write_bytes(
            b"corrupt"
        )
        replacement = Manager(
            self.config, self.temp.name, 1, set(), fetch=self.manager.fetch
        )
        replacement.engine = self.manager.engine
        replacement.register(spec)
        replacement.prepare(name)
        self.assertEqual(self.fetches, 2)

    def test_definite_engine_rejection_leaves_base_serving_healthy(self):
        name = self.register()

        def reject(*_args):
            raise ValueError("Unsupported adapter")

        self.manager.engine = reject
        with self.assertRaises(ValueError):
            self.manager.prepare(name)
        self.assertTrue(self.manager.status()["healthy"])
        with self.manager.request("base"):
            pass

    def test_failed_corrupt_cache_refetch_does_not_leave_stale_disk_or_grant_state(
        self,
    ):
        spec = self.spec()
        name = self.name(spec)
        self.manager.register(spec)
        self.manager.prepare(name)
        (Path(self.temp.name) / name / "adapter_model.safetensors").write_bytes(
            b"corrupt"
        )
        grants = []
        attempts = []

        def resolve(_name, _workspace):
            grants.append(spec)
            return spec

        def fetch(_spec, destination, _hosts):
            attempts.append(1)
            if len(attempts) == 1:
                raise OSError("Temporary download failure")
            destination.write_bytes(self.bytes)

        replacement = Manager(
            self.config, self.temp.name, 1, set(), fetch=fetch, resolve=resolve
        )
        replacement.engine = self.manager.engine
        with self.assertRaises(OSError):
            replacement.prepare(name, spec["workspace_id"])
        self.assertEqual(replacement.entries[name]["disk"], 0)
        replacement.prepare(name, spec["workspace_id"])
        self.assertEqual(len(grants), 2)
        self.assertTrue(replacement.entries[name]["cpu_resident"])

    def test_artifact_base_revision_and_model_must_match_the_engine(self):
        for key in ("base_model_id", "base_model_revision"):
            spec = self.spec()
            if key == "base_model_id":
                spec["version"][key] = "different-model"
            else:
                spec["version"]["adapter"][key] = "different-checkpoint"
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.manager.register(spec)


if __name__ == "__main__":
    unittest.main()
