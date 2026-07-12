from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.business_decision.validator import (
    REQUIRED_NEW_LEVER_IDS,
    REQUIRED_SOURCE_IDS,
    validate_ledger,
)


ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "validation/results/model-stack-business-decision-2026-07-12.json"


class BusinessDecisionValidatorTests(unittest.TestCase):
    def test_current_ledger_is_content_bound_and_fail_closed(self) -> None:
        document = json.loads(LEDGER.read_text())
        self.assertEqual(
            set(REQUIRED_SOURCE_IDS).difference(
                source["source_id"] for source in document["sources"]
            ),
            set(),
        )
        self.assertEqual(validate_ledger(LEDGER, ROOT), [])

    def test_rejects_mismatched_source_hash(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["sources"][0]["file_sha256"] = "0" * 64
        self.assertIn("file sha256 mismatch", " ".join(self._validate_copy(document)))

    def test_rejects_enabled_business_claim(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["claim_permissions"]["five_x_improvement"] = True
        self.assertIn(
            "five_x_improvement: must be false", " ".join(self._validate_copy(document))
        )

    def test_new_cross_artifact_sources_are_exactly_bound(self) -> None:
        document = json.loads(LEDGER.read_text())
        sources = {source["source_id"]: source for source in document["sources"]}
        expected = {
            "competitive_simulation_landscape": (
                "b3314e342f440a4139957c19af0a60106b7754ad616a1760c5dd549edd0e7f1c",
                "bbffa8a7c236ab030f4f74a855fbd424f5e8362ca6f2b77fd90dafd503ab9464",
            ),
            "glm_agentic_mapping_screen": (
                "0e87a43ea19ca45b286b6bf8f0b588a3854c85ae3609cccc13517790f73906e8",
                "f501dd1a2beba380f605c080ef0a6f405b506efb832c98374cfa043da092e5a5",
            ),
            "ramulator2_hbm3_synthetic_irregular": (
                "ad3aaa4cedfe487d5b1fd78ac53412190d6397f9289abe077e329ecb2c492aa9",
                "8215dbe19f3480cd8c9c3040aad9f9186a4b9a1e84a52e637663e7abb6d72c0b",
            ),
            "simulator_predictive_validity_gate": (
                "d35cee28674afb0c0d0d8d0b50ba6b1967b69d7ad98316a99af2fd944a9c1acc",
                "83921cf8311aab4ecb4a3d180766d4b18610393a259476c663b3ae634bf63e42",
            ),
            "qwen_int4_aarch64_neon_holdout": (
                "2428ccbbf26adc3c993c4b0aa12491be2d10ae395e2473470fb67134d8686e62",
                "5494727ab064f8c189f89e88794bbd7c9234baf23ab657c11bae62eaa6f35d40",
            ),
            "small_model_proxy_selection_memo": (
                "27b68401ff5ae85db2775dd15882931ba569fcc2737dd3adeabdd296870a2643",
                None,
            ),
        }

        self.assertTrue(set(expected).issubset(sources))
        for source_id, (file_sha256, content_id) in expected.items():
            self.assertEqual(sources[source_id]["file_sha256"], file_sha256)
            self.assertEqual(sources[source_id]["internal_content_id"], content_id)

    def test_new_decisions_are_explicit_and_fail_closed(self) -> None:
        document = json.loads(LEDGER.read_text())
        decisions = {lever["lever_id"]: lever for lever in document["lever_decisions"]}

        self.assertTrue(set(REQUIRED_NEW_LEVER_IDS).issubset(decisions))
        self.assertEqual(
            decisions["generic_simulator_and_obvious_dsa_moat"]["decision"],
            "kill",
        )
        self.assertEqual(
            decisions["glm_synthetic_hbm3_locality_geometry"]["decision"],
            "kill",
        )
        self.assertEqual(
            decisions["simulator_predictive_validity"]["checked_facts"]["status"],
            "NOT_MET",
        )
        self.assertEqual(
            decisions["simulator_predictive_validity"]["checked_facts"][
                "admitted_exact_scope_pair_count"
            ],
            1,
        )
        self.assertEqual(
            decisions["qwen_aarch64_neon_local_kernel_holdout"]["decision"],
            "pursue",
        )
        self.assertFalse(
            decisions["qwen_aarch64_neon_local_kernel_holdout"]["claims"][
                "cost_per_token_reduction_permitted"
            ]
        )
        self.assertFalse(
            decisions["small_model_proxy_scope"]["claims"][
                "small_model_to_glm_transfer_permitted"
            ]
        )

    def test_markdown_proxy_memo_fact_is_verified(self) -> None:
        document = json.loads(LEDGER.read_text())
        checks = {
            check["check_id"]: check for check in document["evidence_fact_verification"]
        }

        self.assertEqual(
            checks["small_proxy_no_glm_transfer"]["check_kind"],
            "text_contains",
        )
        self.assertEqual(validate_ledger(LEDGER, ROOT), [])

    def test_rejects_mismatched_markdown_fact(self) -> None:
        document = json.loads(LEDGER.read_text())
        check = next(
            check
            for check in document["evidence_fact_verification"]
            if check["check_id"] == "small_proxy_no_glm_transfer"
        )
        check["expected"] = "a sentence that is not in the bound memo"

        self.assertIn("evidence fact mismatch", " ".join(self._validate_copy(document)))

    def test_rejects_enabled_calibrated_simulation_claim(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["claim_permissions"]["calibrated_simulation"] = True

        self.assertIn(
            "calibrated_simulation: must be false",
            " ".join(self._validate_copy(document)),
        )

    def test_business_promotion_permissions_remain_false(self) -> None:
        document = json.loads(LEDGER.read_text())
        permissions = document["claim_permissions"]

        for key in (
            "measured_fully_loaded_cost_per_token_reduction",
            "provider_superiority",
            "five_x_improvement",
            "ten_x_improvement",
            "calibrated_simulation",
            "custom_hardware_buildability",
            "custom_silicon_tapeout_go",
        ):
            self.assertFalse(permissions[key], key)

    def test_refresh_preserves_and_extends_integrity_counts(self) -> None:
        document = json.loads(LEDGER.read_text())

        self.assertEqual(
            document["integrity_summary"],
            {
                "source_count": 31,
                "file_sha256_bound_source_count": 31,
                "internal_content_id_bound_source_count": 27,
                "evidence_fact_check_count": 100,
                "lever_decision_count": 20,
                "arithmetic_check_count": 30,
                "binding_rule": document["integrity_summary"]["binding_rule"],
            },
        )

    def test_rejects_mismatched_new_source_content_id(self) -> None:
        document = json.loads(LEDGER.read_text())
        source = next(
            source
            for source in document["sources"]
            if source["source_id"] == "simulator_predictive_validity_gate"
        )
        source["internal_content_id"] = "0" * 64

        self.assertIn(
            "internal content id mismatch", " ".join(self._validate_copy(document))
        )

    def test_rejects_promoted_new_lever_claim(self) -> None:
        document = json.loads(LEDGER.read_text())
        lever = next(
            lever
            for lever in document["lever_decisions"]
            if lever["lever_id"] == "simulator_predictive_validity"
        )
        lever["claims"]["cost_promotion_permitted"] = True

        self.assertIn(
            "required lever contract mismatch", " ".join(self._validate_copy(document))
        )

    def test_rejects_changed_generic_moat_decision(self) -> None:
        document = json.loads(LEDGER.read_text())
        lever = next(
            lever
            for lever in document["lever_decisions"]
            if lever["lever_id"] == "generic_simulator_and_obvious_dsa_moat"
        )
        lever["decision"] = "pursue"

        self.assertIn(
            "required lever contract mismatch", " ".join(self._validate_copy(document))
        )

    def test_rejects_fabricated_proxy_revision(self) -> None:
        document = json.loads(LEDGER.read_text())
        lever = next(
            lever
            for lever in document["lever_decisions"]
            if lever["lever_id"] == "small_model_proxy_scope"
        )
        lever["checked_facts"]["nosa_revision"] = "fabricated"

        self.assertIn(
            "required lever contract mismatch", " ".join(self._validate_copy(document))
        )

    def test_rejects_full_end_to_end_simulation_promotion(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["overall_decision"][
            "current_evidence_supports_a_full_end_to_end_simulation_claim"
        ] = True

        self.assertIn(
            "current_evidence_supports_a_full_end_to_end_simulation_claim: must be false",
            " ".join(self._validate_copy(document)),
        )

    def test_rejects_removal_of_new_fact_checks(self) -> None:
        document = json.loads(LEDGER.read_text())
        new_source_ids = {
            "competitive_simulation_landscape",
            "glm_agentic_mapping_screen",
            "ramulator2_hbm3_synthetic_irregular",
            "simulator_predictive_validity_gate",
            "small_model_proxy_selection_memo",
            "qwen_int4_aarch64_neon_holdout",
        }
        document["evidence_fact_verification"] = [
            check
            for check in document["evidence_fact_verification"]
            if check["source_id"] not in new_source_ids
        ]
        document["integrity_summary"]["evidence_fact_check_count"] = len(
            document["evidence_fact_verification"]
        )

        self.assertIn(
            "missing required fact check ids", " ".join(self._validate_copy(document))
        )

    def test_rejects_unknown_lever_source(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["lever_decisions"][0]["source_ids"] = ["not-a-source"]
        self.assertIn("unknown source ids", " ".join(self._validate_copy(document)))

    def test_rejects_mismatched_evidence_fact(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["evidence_fact_verification"] = [
            {
                "check_id": "deliberate_mismatch",
                "source_id": document["sources"][0]["source_id"],
                "source_scope": "schema_version",
                "expected": "not-the-schema",
            }
        ]
        document["integrity_summary"]["evidence_fact_check_count"] = 1
        self.assertIn("evidence fact mismatch", " ".join(self._validate_copy(document)))

    def test_rejects_mismatched_ledger_content_identity(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["content_identity_sha256"] = "0" * 64
        self.assertIn(
            "ledger content identity mismatch", " ".join(self._validate_copy(document))
        )

    def test_rejects_promoted_neon_cost_claim(self) -> None:
        document = json.loads(LEDGER.read_text())
        lever = next(
            lever
            for lever in document["lever_decisions"]
            if lever["lever_id"] == "qwen_aarch64_neon_local_kernel_holdout"
        )
        lever["claims"]["cost_per_token_reduction_permitted"] = True

        self.assertIn(
            "required lever contract mismatch", " ".join(self._validate_copy(document))
        )

    def test_rejects_promoted_legacy_lever_claim(self) -> None:
        document = json.loads(LEDGER.read_text())
        lever = next(
            lever
            for lever in document["lever_decisions"]
            if lever["lever_id"] == "qwen_selective_int4_o_gate_up"
        )
        lever["claims"]["cost_per_token_reduction_permitted"] = True

        self.assertIn(
            "unapproved true lever claims", " ".join(self._validate_copy(document))
        )

    def test_rejects_mismatched_arithmetic_result(self) -> None:
        document = json.loads(LEDGER.read_text())
        document["arithmetic_verification"]["checks"][0]["result"] = 999
        self.assertIn("arithmetic mismatch", " ".join(self._validate_copy(document)))

    def _validate_copy(self, document: dict[str, object]) -> list[str]:
        copied = copy.deepcopy(document)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=ROOT, delete=False
        ) as handle:
            json.dump(copied, handle)
            path = Path(handle.name)
        try:
            return validate_ledger(path, ROOT)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
