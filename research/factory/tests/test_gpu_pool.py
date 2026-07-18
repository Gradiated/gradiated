from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path

from grad_research.gpu_pool import GpuPool, GpuPoolError


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
            pool = GpuPool(lab)
            pool.register(bench_spec())
            pool.claim("mtp", bench_id="gemma-h200-1")

            draining = pool.drain("gemma-h200-1")
            self.assertTrue(draining["drain_after_release"])
            released = pool.release("mtp")
            self.assertEqual("draining", released["status"])
            retired = pool.retire("gemma-h200-1", cleanup_verified=True)
            self.assertEqual("retired", retired["status"])

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
