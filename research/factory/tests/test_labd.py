from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from grad_research.labd import BudgetExceeded, LabDatabase, LabError, LeaseBusy

from helpers import HASH_A


class LabDatabaseTests(unittest.TestCase):
    def test_budget_authority_can_only_be_increased_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = LabDatabase(Path(directory) / "lab.sqlite3")
            lab.ensure_budget("campaign", authorized_usd=25.0, already_spent_usd=18.0)
            lab.amend_budget("campaign", authorized_usd=28.60)
            self.assertEqual(28.6, lab.snapshot()["budgets"][0]["authorized_usd"])
            self.assertEqual(18.0, lab.snapshot()["budgets"][0]["settled_usd"])
            with self.assertRaises(LabError):
                lab.amend_budget("campaign", authorized_usd=28.0)
            lab.close()

    def test_lease_budget_retention_adoption_and_cleanup_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab.sqlite3"
            lab = LabDatabase(path)
            lease = lab.acquire_coordinator("glm47", "codex-a", ttl_seconds=30, now=1000)
            with self.assertRaises(LeaseBusy):
                lab.acquire_coordinator("glm47", "codex-b", ttl_seconds=30, now=1001)
            lab.ensure_budget("campaign", authorized_usd=1.0)
            lab.reserve(
                reservation_id="reservation-1",
                campaign_id="campaign",
                program_id="glm47",
                owner="codex-a",
                epoch=lease["epoch"],
                amount_usd=0.7,
                cleanup_reserve_usd=0.1,
                expires_at=1200,
                admission_sha256=HASH_A,
                now=1002,
            )
            with self.assertRaises(BudgetExceeded):
                lab.reserve(
                    reservation_id="reservation-2",
                    campaign_id="campaign",
                    program_id="glm47",
                    owner="codex-a",
                    epoch=lease["epoch"],
                    amount_usd=0.4,
                    cleanup_reserve_usd=0.1,
                    expires_at=1200,
                    admission_sha256=HASH_A,
                    now=1003,
                )
            lab.register_allocation(
                allocation_id="allocation-1",
                reservation_id="reservation-1",
                provider="fake",
                provider_resource_id="gpu-1",
                setup_key="l40s:vllm:glm47",
                owner="codex-a",
                epoch=lease["epoch"],
                absolute_deadline=1190,
                now=1004,
            )
            lab.mark_retained("allocation-1", owner="codex-a", epoch=lease["epoch"], resident_manifest_sha256=HASH_A, now=1005)
            lab.close()

            restarted = LabDatabase(path)
            recovered = restarted.acquire_coordinator("glm47", "codex-b", ttl_seconds=30, now=1040)
            restarted.adopt_allocation("allocation-1", owner="codex-b", epoch=recovered["epoch"], now=1041)
            self.assertEqual("codex-b", restarted.snapshot()["allocations"][0]["owner"])
            self.assertEqual(["allocation-1"], [row["allocation_id"] for row in restarted.due_cleanup(now=1191)])
            restarted.mark_cleanup_verified(
                "allocation-1",
                owner="codex-b",
                epoch=recovered["epoch"],
                now=1192,
                get_absent=True,
                inventory_absent=True,
                verification_sha256=HASH_A,
            )
            restarted.settle_session(
                "reservation-1", actual_cost_usd=0.5, cost_evidence_sha256=HASH_A
            )
            snapshot = restarted.snapshot()
            self.assertEqual("cleaned", snapshot["allocations"][0]["state"])
            self.assertEqual(0.5, snapshot["budgets"][0]["settled_usd"])
            self.assertEqual(0.0, snapshot["budgets"][0]["reserved_usd"])
            restarted.close()

    def test_concurrent_reservations_cannot_overspend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab.sqlite3"
            initial = LabDatabase(path)
            lease = initial.acquire_coordinator("glm47", "codex-a", ttl_seconds=300, now=1000)
            initial.ensure_budget("campaign", authorized_usd=1.0)
            initial.close()
            outcomes: list[str] = []
            barrier = threading.Barrier(2)

            def reserve(name: str) -> None:
                lab = LabDatabase(path)
                barrier.wait()
                try:
                    lab.reserve(
                        reservation_id=name,
                        campaign_id="campaign",
                        program_id="glm47",
                        owner="codex-a",
                        epoch=lease["epoch"],
                        amount_usd=0.7,
                        cleanup_reserve_usd=0.1,
                        expires_at=1200,
                        admission_sha256=HASH_A,
                        now=1001,
                    )
                    outcomes.append("admit")
                except BudgetExceeded:
                    outcomes.append("reject")
                finally:
                    lab.close()

            threads = [threading.Thread(target=reserve, args=(name,)) for name in ("one", "two")]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertCountEqual(["admit", "reject"], outcomes)

    def test_identical_reservation_retry_is_idempotent_and_adoptable_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lab.sqlite3"
            lab = LabDatabase(path)
            first_lease = lab.acquire_coordinator("glm47", "codex-a", ttl_seconds=30, now=1000)
            lab.ensure_budget("campaign", authorized_usd=1.0)
            arguments = {
                "reservation_id": "reservation-1",
                "campaign_id": "campaign",
                "program_id": "glm47",
                "amount_usd": 0.7,
                "cleanup_reserve_usd": 0.1,
                "expires_at": 1200,
                "admission_sha256": HASH_A,
            }
            lab.reserve(owner="codex-a", epoch=first_lease["epoch"], now=1001, **arguments)
            lab.reserve(owner="codex-a", epoch=first_lease["epoch"], now=1002, **arguments)
            self.assertEqual(0.7, lab.snapshot()["budgets"][0]["reserved_usd"])
            lab.close()

            restarted = LabDatabase(path)
            second_lease = restarted.acquire_coordinator("glm47", "codex-b", ttl_seconds=30, now=1040)
            restarted.reserve(owner="codex-b", epoch=second_lease["epoch"], now=1041, **arguments)
            reservation = restarted.snapshot()["reservations"][0]
            self.assertEqual("codex-b", reservation["owner"])
            self.assertEqual(second_lease["epoch"], reservation["lease_epoch"])
            self.assertEqual(0.7, restarted.snapshot()["budgets"][0]["reserved_usd"])
            restarted.close()

    def test_one_reservation_cannot_fund_multiple_provider_allocations(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = LabDatabase(Path(directory) / "lab.sqlite3")
            lease = lab.acquire_coordinator("glm47", "codex-a", ttl_seconds=300, now=1000)
            lab.ensure_budget("campaign", authorized_usd=1.0)
            lab.reserve(
                reservation_id="reservation-1",
                campaign_id="campaign",
                program_id="glm47",
                owner="codex-a",
                epoch=lease["epoch"],
                amount_usd=0.5,
                cleanup_reserve_usd=0.1,
                expires_at=1200,
                admission_sha256=HASH_A,
                now=1001,
            )
            common = {
                "reservation_id": "reservation-1",
                "provider": "fake",
                "setup_key": "l40s:vllm:glm47",
                "owner": "codex-a",
                "epoch": lease["epoch"],
                "absolute_deadline": 1190,
            }
            lab.register_allocation(
                allocation_id="allocation-1",
                provider_resource_id="gpu-1",
                now=1002,
                **common,
            )
            with self.assertRaisesRegex(LabError, "already funds"):
                lab.register_allocation(
                    allocation_id="allocation-2",
                    provider_resource_id="gpu-2",
                    now=1003,
                    **common,
                )
            lab.close()

    def test_expired_unused_reservation_releases_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = LabDatabase(Path(directory) / "lab.sqlite3")
            lease = lab.acquire_coordinator("glm47", "codex-a", ttl_seconds=300, now=1000)
            lab.ensure_budget("campaign", authorized_usd=1.0)
            lab.reserve(
                reservation_id="reservation-1",
                campaign_id="campaign",
                program_id="glm47",
                owner="codex-a",
                epoch=lease["epoch"],
                amount_usd=1.0,
                cleanup_reserve_usd=0.1,
                expires_at=1010,
                admission_sha256=HASH_A,
                now=1001,
            )
            self.assertEqual(0.0, lab.snapshot()["budgets"][0]["available_usd"])
            self.assertTrue(
                lab.release_expired_unused_reservation(
                    "reservation-1", owner="codex-a", epoch=lease["epoch"], now=1011
                )
            )
            self.assertEqual(1.0, lab.snapshot()["budgets"][0]["available_usd"])
            lab.close()

    def test_stopped_owner_can_relinquish_only_after_provider_state_is_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            lab = LabDatabase(Path(directory) / "lab.sqlite3")
            lease = lab.acquire_coordinator("glm47", "stopped-owner", ttl_seconds=900, now=1000)
            released = lab.relinquish_coordinator("glm47", "stopped-owner", now=1001)
            self.assertTrue(released["released"])
            reacquired = lab.acquire_coordinator("glm47", "new-owner", ttl_seconds=900, now=1002)
            self.assertEqual(reacquired["epoch"], lease["epoch"] + 1)
            lab.close()

    def test_cleanup_sweep_fails_closed_until_both_provider_views_are_absent(self):
        class FakeAdapter:
            def __init__(self, *, still_in_inventory: bool):
                self.still_in_inventory = still_in_inventory

            def delete(self, resource_id: str) -> None:
                self.resource_id = resource_id

            def exists(self, resource_id: str) -> bool:
                return False

            def inventory_contains(self, resource_id: str) -> bool:
                return self.still_in_inventory

        with tempfile.TemporaryDirectory() as directory:
            lab = LabDatabase(Path(directory) / "lab.sqlite3")
            lease = lab.acquire_coordinator("glm47", "codex-a", ttl_seconds=30, now=1000)
            lab.ensure_budget("campaign", authorized_usd=1.0)
            lab.reserve(
                reservation_id="reservation-1",
                campaign_id="campaign",
                program_id="glm47",
                owner="codex-a",
                epoch=lease["epoch"],
                amount_usd=0.5,
                cleanup_reserve_usd=0.1,
                expires_at=1200,
                admission_sha256=HASH_A,
                now=1001,
            )
            lab.register_allocation(
                allocation_id="allocation-1",
                reservation_id="reservation-1",
                provider="fake",
                provider_resource_id="gpu-1",
                setup_key="l40s:vllm:glm47",
                owner="codex-a",
                epoch=lease["epoch"],
                absolute_deadline=1100,
                now=1002,
            )

            failed = lab.sweep_due({"fake": FakeAdapter(still_in_inventory=True)}, now=1101)
            self.assertEqual("failed", failed[0]["status"])
            self.assertNotEqual("cleaned", lab.snapshot()["allocations"][0]["state"])

            cleaned = lab.sweep_due({"fake": FakeAdapter(still_in_inventory=False)}, now=1102)
            self.assertEqual("cleaned", cleaned[0]["status"])
            self.assertEqual("cleaned", lab.snapshot()["allocations"][0]["state"])
            lab.close()


if __name__ == "__main__":
    unittest.main()
