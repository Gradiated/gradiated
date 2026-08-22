from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from grad_research.gpu_pool import GpuPool
from run_two_bench_owner import ExactClaimSession
from split_regenerated_data import SOURCES, split


class SplitTests(unittest.TestCase):
    def test_split_is_exact_stratified_and_request_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {}
            for source in SOURCES:
                path = root / f"{source}.jsonl"
                rows = []
                for index in range(8):
                    for generation in range(2):
                        rows.append(
                            {
                                "id": f"{source}-{index}_gen{generation}",
                                "primary_id": f"{source}-{index}",
                                "input_ids": [index, generation],
                                "loss_mask": [0, 1],
                            }
                        )
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                inputs[source] = path

            manifest = split(
                inputs,
                root / "output",
                train_per_source=5,
                holdout_per_source=2,
                seed=7,
            )

            self.assertEqual(20, manifest["train_unique_requests"])
            self.assertEqual(8, manifest["holdout_unique_requests"])
            for source in SOURCES:
                train = set(manifest["selected_ids"][source]["train"])
                holdout = set(manifest["selected_ids"][source]["holdout"])
                self.assertFalse(train & holdout)
                self.assertEqual(5, len(train))
                self.assertEqual(2, len(holdout))

    def test_split_fails_when_a_source_is_short(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {}
            for source in SOURCES:
                path = root / f"{source}.jsonl"
                path.write_text(
                    json.dumps(
                        {
                            "id": f"{source}-0",
                            "input_ids": [1],
                            "loss_mask": [1],
                        }
                    )
                    + "\n"
                )
                inputs[source] = path
            with self.assertRaisesRegex(ValueError, "unique requests"):
                split(
                    inputs,
                    root / "output",
                    train_per_source=1,
                    holdout_per_source=1,
                    seed=7,
                )


class OwnerLifecycleTests(unittest.TestCase):
    @staticmethod
    def bench(bench_id: str) -> dict:
        return {
            "id": bench_id,
            "provider": "nebius",
            "accelerator": "nvidia-h200-sxm",
            "resource": {"instance_id": bench_id},
            "contents": {},
            "lifecycle": {
                "watchdog": {
                    "unit": f"{bench_id}-watchdog.service",
                    "unit_manager": "user",
                },
                "deadline_utc": "2099-01-01T00:00:00Z",
            },
            "hourly_cost_usd": 2.45,
        }

    def test_one_owner_holds_and_releases_two_exact_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pool = GpuPool(Path(directory))
            pool.register(self.bench("target"))
            pool.register(self.bench("trainer"))
            with (
                ExactClaimSession(
                    pool,
                    "mtp-project",
                    "target",
                    lease_seconds=120,
                    heartbeat_seconds=10,
                    release_condition="ready",
                    release_contents={"role": "target"},
                ),
                ExactClaimSession(
                    pool,
                    "mtp-project",
                    "trainer",
                    lease_seconds=120,
                    heartbeat_seconds=10,
                    release_condition="ready",
                    release_contents={"role": "trainer"},
                ),
            ):
                self.assertEqual("claimed", pool.show("target")["status"])
                self.assertEqual("claimed", pool.show("trainer")["status"])
            self.assertEqual("available", pool.show("target")["status"])
            self.assertEqual("available", pool.show("trainer")["status"])


if __name__ == "__main__":
    unittest.main()
