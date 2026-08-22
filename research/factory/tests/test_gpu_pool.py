from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from grad_research.gpu_pool import GpuPool, GpuPoolError, main as gpu_pool_main


def bench_spec() -> dict:
    return {
        "id": "gemma-h200-1",
        "provider": "nebius",
        "accelerator": "h200-sxm",
        "resource": {
            "instance_id": "instance-1",
            "disk_id": "disk-1",
        },
        "contents": {
            "model": "google/gemma-4-31b-it",
            "checkpoint": "b9ea41a2",
            "runtime": "sglang-v0.5.12",
            "image": "sha256:015f39a4",
            "server": "stopped",
            "notes": "BF16 weights and image cached",
        },
        "lifecycle": {
            "watchdog": {
                "unit": "gemma-h200-1-watchdog.service",
                "unit_manager": "user",
            },
            "deadline_utc": "2099-07-18T14:00:00Z",
        },
        "hourly_cost_usd": 2.65,
    }


class GpuPoolTests(unittest.TestCase):
    def test_rejects_runtime_inventory_directory_as_lab_root(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            runtime = lab / "runtime"
            runtime.mkdir()
            inventory = runtime / "gpus.json"
            inventory.write_text(
                json.dumps({"schema_version": 1, "updated_at": "", "benches": {}})
            )

            with self.assertRaisesRegex(GpuPoolError, "pass the lab root"):
                GpuPool(runtime)

            self.assertFalse((runtime / "runtime").exists())

    def test_rejects_inventory_file_as_lab_root(self):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "gpus.json"
            inventory.write_text(
                json.dumps({"schema_version": 1, "updated_at": "", "benches": {}})
            )

            with self.assertRaisesRegex(GpuPoolError, "pass the lab root"):
                GpuPool(inventory)

    def test_cli_can_register_a_nonclaimable_maintenance_bench(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            spec_path = lab / "bench.json"
            spec_path.write_text(json.dumps(bench_spec()))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "register",
                        "--spec",
                        str(spec_path),
                        "--condition",
                        "maintenance",
                    ]
                )

            self.assertEqual(0, result)
            bench = json.loads(stdout.getvalue())
            self.assertEqual("maintenance", bench["status"])
            self.assertIsNone(bench["idle_since"])
            with self.assertRaisesRegex(GpuPoolError, "no available GPU bench"):
                GpuPool(lab).claim("mtp", bench_id="gemma-h200-1")

    def test_register_rejects_duplicate_nonretired_provider_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec(), condition="maintenance")
            duplicate = bench_spec()
            duplicate["id"] = "gemma-h200-duplicate"
            duplicate["lifecycle"]["watchdog"]["unit"] = (
                "gemma-h200-duplicate-watchdog.service"
            )

            with self.assertRaisesRegex(
                GpuPoolError,
                "provider resource already registered by gemma-h200-1: "
                "instance_id=instance-1",
            ):
                pool.register(duplicate, condition="maintenance")

            self.assertEqual(1, len(pool.snapshot()["benches"]))

    def test_cli_show_reads_one_bench_from_keyed_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            GpuPool(lab).register(bench_spec())
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                result = gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "show",
                        "--bench",
                        "gemma-h200-1",
                    ]
                )

            self.assertEqual(0, result)
            bench = json.loads(stdout.getvalue())
            self.assertEqual("gemma-h200-1", bench["id"])
            self.assertEqual("available", bench["status"])

    def test_cli_accepts_inline_contents_object(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1")

            with redirect_stdout(io.StringIO()):
                result = gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "update",
                        "--project",
                        "mtp",
                        "--contents",
                        '{"server":"running","notes":"inline update"}',
                    ]
                )

            self.assertEqual(0, result)
            bench = GpuPool(lab).snapshot()["benches"][0]
            self.assertEqual("running", bench["contents"]["server"])
            self.assertEqual("inline update", bench["contents"]["notes"])

    def test_cli_heartbeat_and_release_accept_claim_bench_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec())
            claimed = pool.claim("mtp", bench_id="gemma-h200-1")

            with redirect_stdout(io.StringIO()):
                gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "heartbeat",
                        "--project",
                        "mtp",
                        "--bench",
                        "gemma-h200-1",
                        "--expected-claimed-at",
                        claimed["claim"]["claimed_at"],
                    ]
                )
                gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "release",
                        "--project",
                        "mtp",
                        "--bench",
                        "gemma-h200-1",
                        "--condition",
                        "ready",
                    ]
                )

            bench = GpuPool(lab).snapshot()["benches"][0]
            self.assertEqual("available", bench["status"])
            self.assertIsNone(bench["claim"])

    def test_cli_release_accepts_legacy_available_condition_as_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1")

            with redirect_stdout(io.StringIO()):
                result = gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "release",
                        "--project",
                        "mtp",
                        "--bench",
                        "gemma-h200-1",
                        "--condition",
                        "available",
                    ]
                )

            self.assertEqual(0, result)
            bench = GpuPool(lab).snapshot()["benches"][0]
            self.assertEqual("available", bench["status"])
            self.assertIsNone(bench["claim"])
            event = json.loads(
                (lab / "runtime" / "gpu_events.jsonl").read_text().splitlines()[-1]
            )
            self.assertEqual("ready", event["condition"])
            self.assertEqual("available", event["resulting_status"])

    def test_cli_release_accepts_a_plain_summary_without_stranding_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1")

            with redirect_stdout(io.StringIO()):
                result = gpu_pool_main(
                    [
                        "--lab",
                        str(lab),
                        "release",
                        "--project",
                        "mtp",
                        "--bench",
                        "gemma-h200-1",
                        "--condition",
                        "maintenance",
                        "--contents",
                        "pre-science build incomplete; retained state preserved",
                    ]
                )

            self.assertEqual(0, result)
            bench = GpuPool(lab).snapshot()["benches"][0]
            self.assertEqual("maintenance", bench["status"])
            self.assertIsNone(bench["claim"])
            self.assertEqual(
                "pre-science build incomplete; retained state preserved",
                bench["contents"]["summary"],
            )

    def test_claim_bench_identity_rejects_a_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1")

            with self.assertRaisesRegex(GpuPoolError, "owns gemma-h200-1"):
                pool.heartbeat("mtp", bench_id="other-bench")

    def test_heartbeat_can_compare_the_claim_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(bench_spec())
            first = pool.claim("mtp", bench_id="gemma-h200-1")
            first_claimed_at = first["claim"]["claimed_at"]
            pool.release("mtp", expected_claimed_at=first_claimed_at)
            current[0] = "2026-07-18T11:01:00Z"
            second = pool.claim("mtp", bench_id="gemma-h200-1")

            with self.assertRaisesRegex(
                GpuPoolError, "GPU claim generation changed"
            ):
                pool.heartbeat(
                    "mtp",
                    expected_claimed_at=first_claimed_at,
                )

            self.assertEqual(
                second["claim"]["heartbeat_at"],
                pool.snapshot()["benches"][0]["claim"]["heartbeat_at"],
            )

    def test_release_can_compare_the_claim_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(bench_spec())
            first = pool.claim("mtp", bench_id="gemma-h200-1")
            first_claimed_at = first["claim"]["claimed_at"]
            pool.release("mtp", expected_claimed_at=first_claimed_at)
            current[0] = "2026-07-18T11:01:00Z"
            second = pool.claim("mtp", bench_id="gemma-h200-1")

            with self.assertRaisesRegex(
                GpuPoolError, "GPU claim generation changed"
            ):
                pool.release("mtp", expected_claimed_at=first_claimed_at)

            self.assertEqual(
                second["claim"]["claimed_at"],
                pool.snapshot()["benches"][0]["claim"]["claimed_at"],
            )

    def test_researchers_claim_exclusively_and_release_preserves_resident_state(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab, now=lambda: "2026-07-18T11:00:00Z")
            pool.register(bench_spec())

            claimed = pool.claim(
                "mtp", accelerator="h200-sxm", model="google/gemma-4-31b-it"
            )
            self.assertEqual("claimed", claimed["status"])
            self.assertEqual("mtp", claimed["claim"]["project"])
            with self.assertRaisesRegex(GpuPoolError, "no available GPU bench"):
                pool.claim("kernel", accelerator="h200-sxm")

            released = pool.release(
                "mtp",
                contents={"server": "running", "notes": "MTP dependencies installed"},
            )
            self.assertEqual("available", released["status"])
            self.assertIsNone(released["claim"])
            self.assertEqual("running", released["contents"]["server"])
            self.assertEqual(
                "MTP dependencies installed", released["contents"]["notes"]
            )
            next_claim = pool.claim("kernel", bench_id="gemma-h200-1")
            self.assertEqual("kernel", next_claim["claim"]["project"])

    def test_one_project_can_claim_two_exact_benches(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            first_spec = bench_spec()
            second_spec = bench_spec()
            second_spec["id"] = "gemma-h200-2"
            second_spec["resource"] = {
                "instance_id": "instance-2",
                "disk_id": "disk-2",
            }
            pool.register(first_spec)
            pool.register(second_spec)

            first = pool.claim("mtp", bench_id="gemma-h200-1")
            second = pool.claim("mtp", bench_id="gemma-h200-2")

            self.assertEqual("gemma-h200-1", first["id"])
            self.assertEqual("gemma-h200-2", second["id"])
            self.assertEqual(
                "gemma-h200-1",
                pool.heartbeat("mtp", bench_id="gemma-h200-1")["id"],
            )
            self.assertEqual(
                "gemma-h200-2",
                pool.heartbeat("mtp", bench_id="gemma-h200-2")["id"],
            )

    def test_concurrent_claims_admit_only_one_project(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            GpuPool(lab).register(bench_spec())
            barrier = threading.Barrier(2)
            outcomes: list[str] = []

            def claim(project: str) -> None:
                barrier.wait()
                try:
                    GpuPool(lab).claim(project, bench_id="gemma-h200-1")
                    outcomes.append("claimed")
                except GpuPoolError:
                    outcomes.append("unavailable")

            threads = [
                threading.Thread(target=claim, args=(project,))
                for project in ("a", "b")
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(["claimed", "unavailable"], sorted(outcomes))

    def test_stale_claim_is_visible_and_requires_director_reclaim(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1", lease_seconds=60)
            current[0] = "2026-07-18T11:02:00Z"

            row = pool.snapshot()["benches"][0]
            self.assertTrue(row["claim"]["stale"])
            with self.assertRaisesRegex(GpuPoolError, "no available GPU bench"):
                pool.claim("kernel", bench_id="gemma-h200-1")

            reclaimed = pool.reclaim("gemma-h200-1", reason="researcher ended")
            self.assertEqual("maintenance", reclaimed["status"])
            self.assertIsNone(reclaimed["claim"])

    def test_claim_never_outlives_director_lifecycle_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            spec = bench_spec()
            spec["lifecycle"]["deadline_utc"] = "2026-07-18T11:05:00Z"
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(spec)

            claimed = pool.claim(
                "mtp", bench_id="gemma-h200-1", lease_seconds=3600
            )

            self.assertEqual(
                "2026-07-18T11:05:00Z", claimed["claim"]["lease_until_utc"]
            )
            current[0] = "2026-07-18T11:06:00Z"
            self.assertTrue(pool.snapshot()["benches"][0]["claim"]["stale"])

    def test_director_can_replace_watchdog_with_a_later_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            spec = bench_spec()
            spec["lifecycle"]["deadline_utc"] = "2026-07-18T12:00:00Z"
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(spec)
            pool.claim("mtp", bench_id="gemma-h200-1")

            extended = pool.replace_watchdog(
                "gemma-h200-1",
                lifecycle={
                    "watchdog": {
                        "unit": "gemma-h200-1-retained-watchdog.service",
                        "unit_manager": "user",
                    },
                    "deadline_utc": "2026-07-18T14:00:00Z",
                },
            )

            self.assertEqual(
                "2026-07-18T14:00:00Z", extended["lifecycle"]["deadline_utc"]
            )
            self.assertEqual(
                "gemma-h200-1-retained-watchdog.service",
                extended["lifecycle"]["watchdog"]["unit"],
            )
            event = json.loads(
                (lab / "runtime" / "gpu_events.jsonl").read_text().splitlines()[-1]
            )
            self.assertEqual("bench_watchdog_replaced", event["event"])

            with self.assertRaisesRegex(GpuPoolError, "later than the current"):
                pool.replace_watchdog(
                    "gemma-h200-1",
                    lifecycle={
                        "watchdog": {"unit": "shorter-watchdog.service"},
                        "deadline_utc": "2026-07-18T13:00:00Z",
                    },
                )

    def test_draining_claim_finishes_without_becoming_available(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            spec = bench_spec()
            spec["lifecycle"]["provider_started_at_utc"] = (
                "2026-07-18T10:55:00Z"
            )
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(spec)
            pool.claim("mtp", bench_id="gemma-h200-1")

            draining = pool.drain("gemma-h200-1")
            self.assertTrue(draining["drain_after_release"])
            released = pool.release("mtp")
            self.assertEqual("draining", released["status"])
            current[0] = "2026-07-18T12:00:00Z"
            retired = pool.retire("gemma-h200-1", cleanup_verified=True)
            self.assertEqual("retired", retired["status"])
            self.assertEqual(
                "provider_start_to_cleanup_verification",
                retired["provider_exposure"]["basis"],
            )
            self.assertEqual(3900.0, retired["provider_exposure"]["seconds"])
            self.assertAlmostEqual(
                3900.0 * 2.65 / 3600.0,
                retired["provider_exposure"]["cost_usd"],
            )
            self.assertTrue(
                retired["provider_exposure"]["covers_pre_registration"]
            )
            event = json.loads(
                (lab / "runtime" / "gpu_events.jsonl").read_text().splitlines()[-1]
            )
            self.assertEqual(
                retired["provider_exposure"], event["provider_exposure"]
            )

    def test_retire_labels_registration_based_exposure_as_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(bench_spec())
            current[0] = "2026-07-18T12:00:00Z"

            retired = pool.retire("gemma-h200-1", cleanup_verified=True)

            self.assertEqual(
                "inventory_registration_to_cleanup_verification_partial",
                retired["provider_exposure"]["basis"],
            )
            self.assertEqual(3600.0, retired["provider_exposure"]["seconds"])
            self.assertAlmostEqual(
                2.65, retired["provider_exposure"]["cost_usd"]
            )
            self.assertFalse(
                retired["provider_exposure"]["covers_pre_registration"]
            )

    def test_release_after_lifecycle_deadline_fences_bench_for_director(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            spec = bench_spec()
            spec["lifecycle"]["deadline_utc"] = "2026-07-18T11:05:00Z"
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(spec)
            pool.claim("mtp", bench_id="gemma-h200-1")
            current[0] = "2026-07-18T11:06:00Z"

            released = pool.release("mtp")

            self.assertEqual("draining", released["status"])
            self.assertIsNone(released["claim"])
            self.assertIsNone(released["idle_since"])
            event = json.loads(
                (lab / "runtime" / "gpu_events.jsonl").read_text().splitlines()[-1]
            )
            self.assertTrue(event["lifecycle_deadline_passed"])
            with self.assertRaisesRegex(GpuPoolError, "deadline has passed"):
                pool.ready("gemma-h200-1")

    def test_snapshot_fences_bench_released_before_lifecycle_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            spec = bench_spec()
            spec["lifecycle"]["deadline_utc"] = "2026-07-18T11:05:00Z"
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(spec)
            pool.claim("mtp", bench_id="gemma-h200-1")
            pool.release("mtp")
            self.assertEqual("available", pool.snapshot()["benches"][0]["status"])

            current[0] = "2026-07-18T11:06:00Z"
            expired = pool.snapshot()["benches"][0]

            self.assertEqual("draining", expired["status"])
            self.assertIsNone(expired["idle_since"])
            event = json.loads(
                (lab / "runtime" / "gpu_events.jsonl").read_text().splitlines()[-1]
            )
            self.assertEqual("bench_lifecycle_expired", event["event"])
            self.assertEqual("gemma-h200-1", event["bench_id"])

    def test_ready_preserves_continuous_available_idle_time(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            current = ["2026-07-18T11:00:00Z"]
            pool = GpuPool(lab, now=lambda: current[0])
            pool.register(bench_spec())
            original_idle_since = pool.show("gemma-h200-1")["idle_since"]
            current[0] = "2026-07-18T11:10:00Z"

            refreshed = pool.ready(
                "gemma-h200-1", contents={"notes": "successor selected"}
            )

            self.assertEqual("available", refreshed["status"])
            self.assertEqual(original_idle_since, refreshed["idle_since"])
            self.assertEqual("successor selected", refreshed["contents"]["notes"])
            self.assertEqual(current[0], refreshed["updated_at"])

    def test_inventory_and_events_are_durable_json(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = Path(directory)
            pool = GpuPool(lab)
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1")
            pool.heartbeat("mtp")
            pool.release("mtp", condition="maintenance")
            pool.ready("gemma-h200-1", contents={"server": "stopped"})

            inventory = json.loads((lab / "runtime" / "gpus.json").read_text())
            events = [
                json.loads(line)
                for line in (lab / "runtime" / "gpu_events.jsonl").read_text().splitlines()
            ]
            self.assertEqual(1, inventory["schema_version"])
            self.assertEqual(
                [
                    "bench_registered",
                    "bench_claimed",
                    "claim_heartbeat",
                    "bench_released",
                    "bench_ready",
                ],
                [event["event"] for event in events],
            )


if __name__ == "__main__":
    unittest.main()
