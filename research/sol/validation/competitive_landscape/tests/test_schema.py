import copy
import json
import unittest
from pathlib import Path

from validation.competitive_landscape.schema import validate_landscape


ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = (
    ROOT
    / "validation/results/inference-codesign-competitive-simulation-landscape-2026-07-12.json"
)


class CompetitiveLandscapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_checked_artifact_is_valid_and_identity_verifies(self) -> None:
        validate_landscape(self.document)

    def test_required_competitive_surfaces_are_present(self) -> None:
        expected = {
            "nvidia_dynosim_aiconfigurator",
            "nvidia_model_hardware_codesign",
            "fireworks_fireoptimizer_3d",
            "etched_vertical_inference_clusters",
            "furiosa_rngd_model_compiler",
            "astra_sim",
            "timeloop_accelergy",
            "llmservingsim_2",
            "mlperf_inference",
            "aa_agentperf",
            "indexcache_cross_layer_dsa",
            "tisa_temporal_dsa",
            "hisa_hierarchical_dsa",
            "misa_indexer_head_routing",
            "unique_page_sparse_attention",
            "spin_sparse_hierarchical_kv",
            "intra_token_sparse_gather",
            "salca_sparse_attention_accelerator",
            "nosa_locality_trained_offload",
        }

        self.assertEqual(
            {entry["entry_id"] for entry in self.document["entries"]},
            expected,
        )

    def test_glm_sparse_attention_opportunity_is_explicitly_occupied(self) -> None:
        occupied = next(
            layer
            for layer in self.document["commoditized_layers"]
            if layer["layer_id"] == "glm_dsa_index_and_memory_optimization"
        )

        self.assertEqual(
            set(occupied["evidence_entry_ids"]),
            {
                "indexcache_cross_layer_dsa",
                "tisa_temporal_dsa",
                "hisa_hierarchical_dsa",
                "misa_indexer_head_routing",
                "unique_page_sparse_attention",
                "spin_sparse_hierarchical_kv",
                "intra_token_sparse_gather",
                "salca_sparse_attention_accelerator",
                "nosa_locality_trained_offload",
            },
        )

    def test_claim_permissions_remain_fail_closed(self) -> None:
        self.assertTrue(self.document["claim_permissions"])
        self.assertTrue(
            all(value is False for value in self.document["claim_permissions"].values())
        )
        self.assertFalse(self.document["surviving_wedge"]["moat_claim_permitted"])

    def test_vendor_and_author_claims_are_not_marked_independently_reproduced(
        self,
    ) -> None:
        for entry in self.document["entries"]:
            for claim in entry["public_claims"]:
                if claim["evidence_class"] in {
                    "vendor_assertion",
                    "author_reported_result",
                }:
                    self.assertFalse(claim["independently_reproduced"])

    def test_has_five_falsifiable_fail_closed_gates(self) -> None:
        gates = self.document["decision_gates"]

        self.assertEqual(len(gates), 5)
        self.assertTrue(all(gate["current_status"] == "not_met" for gate in gates))
        self.assertTrue(all(gate["promotion_if_all"] for gate in gates))
        self.assertTrue(all(gate["kill_if_any"] for gate in gates))

    def test_unknown_source_reference_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["entries"][0]["source_ids"].append("missing")

        with self.assertRaisesRegex(ValueError, "unknown source"):
            validate_landscape(document, verify_identity=False)

    def test_enabling_business_claim_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["claim_permissions"]["measured_cost_per_token"] = True

        with self.assertRaisesRegex(ValueError, "claim permissions"):
            validate_landscape(document, verify_identity=False)

    def test_non_primary_source_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["sources"][0]["primary_source"] = False

        with self.assertRaisesRegex(ValueError, "primary"):
            validate_landscape(document, verify_identity=False)

    def test_unsubstantiated_independent_fact_count_fails_closed(self) -> None:
        document = copy.deepcopy(self.document)
        document["evidence_policy"]["independently_reproduced_fact_count"] = 1

        with self.assertRaisesRegex(ValueError, "independently reproduced"):
            validate_landscape(document, verify_identity=False)


if __name__ == "__main__":
    unittest.main()
