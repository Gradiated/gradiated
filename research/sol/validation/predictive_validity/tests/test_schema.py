from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from validation.predictive_validity.schema import validate_current_state


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = (
    ROOT / "validation/results/simulator-predictive-validity-gate-2026-07-12.json"
)


class PredictiveValidityCurrentStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_checked_current_state_is_valid(self) -> None:
        validate_current_state(self.document, root=ROOT)

    def test_all_snapshot_files_and_declared_content_ids_are_bound(self) -> None:
        inventory = self.document["audit_inventory"]

        self.assertEqual(inventory["artifact_count"], len(inventory["artifacts"]))
        self.assertEqual(inventory["artifact_count"], 61)
        self.assertTrue(
            all("file_sha256" in artifact for artifact in inventory["artifacts"])
        )
        self.assertGreater(
            sum(
                bool(artifact["declared_content_ids"])
                for artifact in inventory["artifacts"]
            ),
            30,
        )

    def test_downstream_exclusions_are_exact_and_inventory_is_complete(self) -> None:
        inventory = self.document["audit_inventory"]
        exclusions = inventory["selection"]["exclusions"]
        expected_exclusions = [
            {
                "path": "validation/results/simulator-predictive-validity-gate-2026-07-12.json",
                "reason": "gate output excluded to prevent self-reference",
            },
            {
                "path": "validation/results/model-stack-business-decision-2026-07-12.json",
                "reason": "downstream decision synthesis excluded to prevent circular identity",
            },
        ]
        workspace_paths = {
            str(path.relative_to(ROOT))
            for source_root in (ROOT / "experiments", ROOT / "validation/results")
            for path in source_root.rglob("*.json")
        }
        inventory_paths = {artifact["path"] for artifact in inventory["artifacts"]}

        self.assertEqual(exclusions, expected_exclusions)
        self.assertEqual(
            inventory_paths | {exclusion["path"] for exclusion in exclusions},
            workspace_paths,
        )

    def test_extra_inventory_exclusion_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["audit_inventory"]["selection"]["exclusions"].append(
            {
                "path": "validation/results/provider-economics-2026-07-12.json",
                "reason": "unsupported omission",
            }
        )

        with self.assertRaisesRegex(ValueError, "inventory selection"):
            validate_current_state(
                document,
                root=ROOT,
                verify_identity=False,
            )

    def test_current_state_admits_one_prospective_pair_but_gate_is_not_met(
        self,
    ) -> None:
        result = self.document["gate_result"]

        self.assertEqual(len(self.document["admitted_pairs"]), 1)
        self.assertEqual(
            self.document["admitted_pairs"][0]["pair_id"],
            "qwen3-0.6b-int4-aarch64-neon-v1",
        )
        self.assertEqual(result["status"], "NOT_MET")
        self.assertEqual(result["admitted_pair_count"], 1)
        self.assertEqual(result["distinct_intervention_count"], 1)
        self.assertEqual(result["context_regime_count"], 1)
        self.assertAlmostEqual(
            result["maximum_relative_effect_size_error"],
            0.447465830931747,
        )
        self.assertIsNone(result["spearman_rank_correlation"])
        self.assertTrue(result["all_directions_correct"])
        self.assertFalse(result["cost_promotion_permitted"])

    def test_neon_pair_is_bound_to_precommit_and_real_holdout_files(self) -> None:
        pair = self.document["admitted_pairs"][0]

        self.assertEqual(
            pair["protocol"]["prediction_commit_id"],
            "4b7b172ea4ee66b3e49629d1155b0907c7fdcc89",
        )
        self.assertEqual(
            pair["protocol"]["prediction_locked_at_unix_ms"], 1783843333000
        )
        self.assertEqual(
            pair["protocol"]["measurement_started_at_unix_ms"], 1783843360279
        )
        self.assertEqual(
            pair["prediction"]["artifact_path"],
            "validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json",
        )
        self.assertEqual(
            pair["measurement"]["artifact_path"],
            "experiments/qwen3-0.6b/int4-aarch64-neon-v1.json",
        )
        self.assertEqual(pair["prediction"]["baseline"], 0.005299750000000001)
        self.assertEqual(pair["prediction"]["candidate"], 0.003028428571428572)
        self.assertEqual(pair["measurement"]["baseline"], 0.004740665999999999)
        self.assertEqual(pair["measurement"]["candidate"], 0.0010635829999999999)

    def test_every_snapshot_artifact_is_covered_by_candidate_audit(self) -> None:
        inventory_paths = {
            artifact["path"]
            for artifact in self.document["audit_inventory"]["artifacts"]
        }
        audited_paths = {
            path
            for audit in self.document["candidate_pair_audits"]
            for path in audit["artifact_paths"]
        }

        self.assertEqual(audited_paths, inventory_paths)
        admitted = [
            audit
            for audit in self.document["candidate_pair_audits"]
            if audit["admission_status"] == "ADMITTED"
        ]
        rejected = [
            audit
            for audit in self.document["candidate_pair_audits"]
            if audit["admission_status"] == "REJECTED"
        ]

        self.assertEqual(len(admitted), 1)
        self.assertEqual(admitted[0]["same_scope_pair_count"], 1)
        self.assertEqual(
            admitted[0]["pair_ids"],
            ["qwen3-0.6b-int4-aarch64-neon-v1"],
        )
        self.assertEqual(admitted[0]["rejection_codes"], [])
        self.assertTrue(
            all(
                audit["same_scope_pair_count"] == 0
                and audit["pair_ids"] == []
                and audit["rejection_codes"]
                for audit in rejected
            )
        )

    def test_weakening_predeclared_threshold_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["gate_spec"]["maximum_relative_effect_size_error"] = 0.20

        with self.assertRaisesRegex(ValueError, "gate spec"):
            validate_current_state(
                document,
                root=ROOT,
                verify_identity=False,
            )

    def test_enabling_cost_promotion_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["claim_permissions"]["cost_promotion"] = True

        with self.assertRaisesRegex(ValueError, "claim permissions"):
            validate_current_state(
                document,
                root=ROOT,
                verify_identity=False,
            )

    def test_file_hash_mismatch_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["audit_inventory"]["artifacts"][0]["file_sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "file hash"):
            validate_current_state(
                document,
                root=ROOT,
                verify_identity=False,
            )

    def test_declared_content_id_mismatch_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        artifact = next(
            item
            for item in document["audit_inventory"]["artifacts"]
            if item["declared_content_ids"]
        )
        artifact["declared_content_ids"][0]["value"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "declared content id"):
            validate_current_state(
                document,
                root=ROOT,
                verify_identity=False,
            )


if __name__ == "__main__":
    unittest.main()
