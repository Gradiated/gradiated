from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from grad_research.director import ResearchDirector
from grad_research.labd import LabDatabase, LabError
from grad_research.operations import resume_program

from helpers import HASH_A


class ResumeOperationsTests(unittest.TestCase):
    def _runtime(self, directory: str) -> tuple[ResearchDirector, LabDatabase]:
        director = ResearchDirector(directory, "glm47")
        lab = LabDatabase(Path(directory) / "lab.sqlite3")
        lease = lab.acquire_coordinator("glm47", "old-codex", ttl_seconds=30, now=1000)
        lab.ensure_budget("campaign", authorized_usd=1.0)
        lab.reserve(
            reservation_id="reservation-1",
            campaign_id="campaign",
            program_id="glm47",
            owner="old-codex",
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
            owner="old-codex",
            epoch=lease["epoch"],
            absolute_deadline=1190,
            now=1002,
        )
        lab.mark_retained(
            "allocation-1",
            owner="old-codex",
            epoch=lease["epoch"],
            resident_manifest_sha256=HASH_A,
            now=1003,
        )
        return director, lab

    def test_resume_adopts_live_retained_setup_and_writes_restart_views(self):
        with tempfile.TemporaryDirectory() as directory:
            director, lab = self._runtime(directory)
            resumed = resume_program(
                director,
                lab,
                owner="new-codex",
                ttl_seconds=300,
                now=datetime.fromtimestamp(1040, timezone.utc),
            )
            allocation = resumed["runtime"]["allocations"][0]
            self.assertEqual("new-codex", allocation["owner"])
            self.assertEqual(resumed["lease"]["epoch"], allocation["lease_epoch"])
            self.assertTrue(resumed["safe_to_start_new_provider_mutation"])
            self.assertTrue(Path(resumed["resume_path"]).is_file())
            self.assertTrue(Path(resumed["work_queue_path"]).is_file())
            lab.close()

    def test_expired_or_cleanup_required_allocation_cannot_be_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            _, lab = self._runtime(directory)
            lease = lab.acquire_coordinator("glm47", "new-codex", ttl_seconds=300, now=1040)
            lab.adopt_allocation(
                "allocation-1", owner="new-codex", epoch=lease["epoch"], now=1040
            )
            lab.request_cleanup(
                "allocation-1", owner="new-codex", epoch=lease["epoch"], now=1041
            )
            with self.assertRaisesRegex(LabError, "active or retained"):
                lab.adopt_allocation(
                    "allocation-1", owner="new-codex", epoch=lease["epoch"], now=1042
                )
            lab.close()

    def test_resume_blocks_new_mutation_when_cleanup_is_due(self):
        with tempfile.TemporaryDirectory() as directory:
            director, lab = self._runtime(directory)
            resumed = resume_program(
                director,
                lab,
                owner="new-codex",
                ttl_seconds=300,
                now=datetime.fromtimestamp(1191, timezone.utc),
            )
            self.assertFalse(resumed["safe_to_start_new_provider_mutation"])
            self.assertEqual("cleanup_now", resumed["actions"][0]["action"])
            lab.close()

    def test_settled_provider_intent_without_allocation_is_not_reconciled_again(self):
        with tempfile.TemporaryDirectory() as directory:
            director = ResearchDirector(directory, "glm47")
            director.state = lambda: {
                "event_head_sha256": HASH_A,
                "observations": {},
                "scouts": {},
                "portfolios": {},
                "runs": {
                    "run-1": {
                        "status": "admitted",
                        "admission": {"reservation_id": "reservation-1"},
                        "spec": {
                            "artifact_refs": [],
                            "scout_id": "scout-1",
                            "provider_contract": {
                                "provider": "fake",
                                "idempotency_key": "run-1",
                                "resource_tags": {"run_id": "run-1"},
                            },
                        },
                    }
                },
                "residual_bottleneck": "unchanged",
                "next_action": "prepare a fresh identity",
            }
            director.write_state = lambda: Path(directory) / "STATE.json"
            director.write_coordinator_context = lambda: Path(directory) / "COORDINATOR.md"
            lab = LabDatabase(Path(directory) / "lab.sqlite3")
            lease = lab.acquire_coordinator("glm47", "old-codex", ttl_seconds=30, now=1000)
            lab.ensure_budget("campaign", authorized_usd=1.0)
            lab.reserve(
                reservation_id="reservation-1",
                campaign_id="campaign",
                program_id="glm47",
                owner="old-codex",
                epoch=lease["epoch"],
                amount_usd=0.5,
                cleanup_reserve_usd=0.1,
                expires_at=1200,
                admission_sha256=HASH_A,
                now=1001,
            )
            lab.settle_session(
                "reservation-1", actual_cost_usd=0, cost_evidence_sha256=HASH_A
            )

            resumed = resume_program(
                director,
                lab,
                owner="new-codex",
                ttl_seconds=300,
                now=datetime.fromtimestamp(1040, timezone.utc),
            )

            self.assertEqual([], resumed["actions"])
            lab.close()


if __name__ == "__main__":
    unittest.main()
