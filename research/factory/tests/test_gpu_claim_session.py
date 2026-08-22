from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from grad_research.gpu_claim_session import GpuClaimSession, GpuClaimSessionError
from grad_research.gpu_pool import GpuPool


def bench_spec() -> dict:
    return {
        "id": "gemma-rtx-1",
        "provider": "runpod",
        "accelerator": "rtx-pro-6000",
        "resource": {"pod_id": "pod-1"},
        "contents": {"model": "google/gemma-4-31b-it", "server": "running"},
        "lifecycle": {
            "watchdog": {
                "unit": "gemma-rtx-1-watchdog.service",
                "unit_manager": "user",
            },
            "deadline_utc": "2099-07-29T12:00:00Z",
        },
        "hourly_cost_usd": 1.89,
    }


class GpuClaimSessionTests(unittest.TestCase):
    def test_claims_exact_bench_heartbeats_and_releases_to_maintenance(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())

            with GpuClaimSession(
                pool,
                "norm-fusion",
                "gemma-rtx-1",
                lease_seconds=2,
                heartbeat_seconds=0.01,
                release_contents={"summary": "resident state preserved"},
            ) as session:
                deadline = time.monotonic() + 1
                while time.monotonic() < deadline:
                    events = (
                        Path(directory) / "runtime" / "gpu_events.jsonl"
                    ).read_text()
                    if '"event": "claim_heartbeat"' in events:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("claim session did not heartbeat")
                self.assertIsNotNone(session.claimed_at)
                self.assertFalse(session.released)

            bench = pool.show("gemma-rtx-1")
            self.assertEqual("maintenance", bench["status"])
            self.assertIsNone(bench["claim"])
            self.assertEqual(
                "resident state preserved",
                bench["contents"]["summary"],
            )

    def test_unhandled_owner_error_still_releases_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())

            with self.assertRaisesRegex(RuntimeError, "owner failed"):
                with GpuClaimSession(
                    pool,
                    "norm-fusion",
                    "gemma-rtx-1",
                    lease_seconds=2,
                    heartbeat_seconds=0.1,
                ):
                    raise RuntimeError("owner failed")

            bench = pool.show("gemma-rtx-1")
            self.assertEqual("maintenance", bench["status"])
            self.assertIsNone(bench["claim"])

    def test_repair_capable_owner_retains_and_heartbeats_after_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())
            session = GpuClaimSession(
                pool,
                "norm-fusion",
                "gemma-rtx-1",
                lease_seconds=2,
                heartbeat_seconds=0.01,
                release_on_exception=False,
            )

            with self.assertRaisesRegex(RuntimeError, "repairable"):
                with session:
                    raise RuntimeError("repairable")

            retained = pool.show("gemma-rtx-1")
            self.assertEqual("claimed", retained["status"])
            self.assertEqual("norm-fusion", retained["claim"]["project"])
            initial_heartbeat = retained["claim"]["heartbeat_at"]
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                retained = pool.show("gemma-rtx-1")
                if retained["claim"]["heartbeat_at"] != initial_heartbeat:
                    break
                time.sleep(0.01)
            else:
                self.fail("retained claim did not continue heartbeating")

            session.release(
                condition="ready",
                contents={"summary": "repair completed in place"},
            )
            released = pool.show("gemma-rtx-1")
            self.assertEqual("available", released["status"])
            self.assertIsNone(released["claim"])

    def test_rejects_a_different_preexisting_project_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())
            second = bench_spec()
            second["id"] = "gemma-rtx-2"
            second["resource"] = {"pod_id": "pod-2"}
            pool.register(second)
            pool.claim("other-project", bench_id="gemma-rtx-2")

            with self.assertRaisesRegex(
                ValueError,
                "no available GPU bench matches this project",
            ):
                with GpuClaimSession(
                    pool,
                    "norm-fusion",
                    "gemma-rtx-2",
                    lease_seconds=2,
                    heartbeat_seconds=0.1,
                ):
                    self.fail("mismatched claim must not enter")

            claimed = pool.show("gemma-rtx-2")
            self.assertEqual("claimed", claimed["status"])
            self.assertEqual("other-project", claimed["claim"]["project"])

    def test_release_is_generation_fenced(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())

            session = GpuClaimSession(
                pool,
                "norm-fusion",
                "gemma-rtx-1",
                lease_seconds=2,
                heartbeat_seconds=0.1,
            )
            session.__enter__()
            original_claimed_at = session.claimed_at
            inventory_path = Path(directory) / "runtime" / "gpus.json"
            inventory = json.loads(inventory_path.read_text())
            inventory["benches"]["gemma-rtx-1"]["claim"]["claimed_at"] = "other"
            inventory_path.write_text(json.dumps(inventory))

            with self.assertRaisesRegex(ValueError, "claim generation changed"):
                session.release()

            self.assertEqual(original_claimed_at, session.claimed_at)

    def test_replacement_owner_attaches_only_to_expected_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())
            claimed = pool.claim(
                "norm-fusion",
                bench_id="gemma-rtx-1",
                lease_seconds=2,
            )
            claimed_at = claimed["claim"]["claimed_at"]

            replacement = GpuClaimSession(
                pool,
                "norm-fusion",
                "gemma-rtx-1",
                lease_seconds=2,
                heartbeat_seconds=0.01,
                expected_claimed_at=claimed_at,
            )
            replacement.__enter__()
            self.assertEqual(claimed_at, replacement.claimed_at)
            replacement.release(condition="maintenance")

    def test_replacement_owner_rejects_a_different_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(bench_spec())
            claimed = pool.claim(
                "norm-fusion",
                bench_id="gemma-rtx-1",
                lease_seconds=2,
            )

            with self.assertRaisesRegex(
                GpuClaimSessionError,
                "does not match expected_claimed_at",
            ):
                GpuClaimSession(
                    pool,
                    "norm-fusion",
                    "gemma-rtx-1",
                    lease_seconds=2,
                    heartbeat_seconds=0.01,
                    expected_claimed_at="different-generation",
                ).__enter__()

            retained = pool.show("gemma-rtx-1")
            self.assertEqual("claimed", retained["status"])
            self.assertEqual(
                claimed["claim"]["claimed_at"],
                retained["claim"]["claimed_at"],
            )
