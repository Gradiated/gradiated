from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.predictive_validity.gate import (
    default_gate_spec,
    evaluate_pairs,
)


def _scope(
    intervention_id: str,
    context_regime: str,
) -> dict[str, object]:
    return {
        "model_id": "Qwen/Qwen3-0.6B",
        "model_revision": "model-revision-1",
        "workload_id": "agent-trace",
        "workload_revision": f"workload-{context_regime}-revision-1",
        "context_regime": context_regime,
        "hardware_id": "accelerator-a",
        "hardware_revision": "hardware-revision-1",
        "software_id": "runtime-a",
        "software_revision": "software-revision-1",
        "intervention_id": intervention_id,
        "intervention_revision": f"{intervention_id}-revision-1",
        "metric_id": "output_throughput",
        "metric_unit": "tokens_per_second",
        "higher_is_better": True,
    }


def _artifact_binding(
    artifact_root: Path,
    pair_id: str,
    evidence_kind: str,
    content_digit: str,
    fields: dict[str, object],
) -> dict[str, object]:
    content_id = content_digit * 64
    relative_path = f"evidence/{pair_id}-{evidence_kind}.json"
    path = artifact_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"content_id": content_id, **copy.deepcopy(fields)}
    payload = (json.dumps(document, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    return {
        "artifact_path": relative_path,
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "artifact_content_id": content_id,
        "artifact_content_id_json_path": "content_id",
    }


def _rewrite_observation(
    artifact_root: Path,
    observation: dict[str, object],
    *,
    scope: dict[str, object] | None = None,
    candidate: float | None = None,
) -> None:
    path = artifact_root / str(observation["artifact_path"])
    document = json.loads(path.read_text())
    if scope is not None:
        document["predictive_scope"] = copy.deepcopy(scope)
    if candidate is not None:
        document["candidate"] = candidate
        observation["candidate"] = candidate
    payload = (json.dumps(document, sort_keys=True) + "\n").encode()
    path.write_bytes(payload)
    observation["artifact_sha256"] = hashlib.sha256(payload).hexdigest()


def _cost_evidence(
    artifact_root: Path,
    pair_id: str,
    scope: dict[str, object],
) -> dict[str, object]:
    execution_scope = {
        key: value
        for key, value in scope.items()
        if key not in {"metric_id", "metric_unit", "higher_is_better"}
    }
    result = {}
    for evidence_kind, digit, criterion in (
        ("quality", "c", "quality_noninferiority"),
        ("slo", "d", "agent_slo"),
    ):
        result[evidence_kind] = {
            "bound_pair_id": pair_id,
            "execution_scope": copy.deepcopy(execution_scope),
            **_artifact_binding(
                artifact_root,
                pair_id,
                evidence_kind,
                digit,
                {
                    "predictive_scope": execution_scope,
                    "criterion": {
                        "id": criterion,
                        "revision": "criterion-revision-1",
                        "passed": True,
                    },
                },
            ),
            "artifact_scope_json_path": "predictive_scope",
            "criterion_id_json_path": "criterion.id",
            "criterion_revision_json_path": "criterion.revision",
            "passed_json_path": "criterion.passed",
            "criterion_id": criterion,
            "criterion_revision": "criterion-revision-1",
            "passed": True,
        }
    return result


def _pair(
    artifact_root: Path,
    pair_id: str,
    intervention_id: str,
    context_regime: str,
    predicted_effect: float,
    measured_effect: float,
    *,
    exact_cost_evidence: bool = False,
) -> dict[str, object]:
    scope = _scope(intervention_id, context_regime)
    predicted_baseline = 100.0
    predicted_candidate = 100.0 * (1.0 + predicted_effect)
    measured_baseline = 100.0
    measured_candidate = 100.0 * (1.0 + measured_effect)
    pair = {
        "pair_id": pair_id,
        "prediction_scope": copy.deepcopy(scope),
        "measurement_scope": copy.deepcopy(scope),
        "protocol": {
            "prediction_locked_at_unix_ms": 100,
            "measurement_started_at_unix_ms": 200,
            "prediction_commit_id": "a" * 40,
            "blinded_holdout": True,
            "calibration_case_ids": [f"calibration-{pair_id}"],
            "holdout_case_id": f"holdout-{pair_id}",
        },
        "prediction": {
            "baseline": predicted_baseline,
            "candidate": predicted_candidate,
            **_artifact_binding(
                artifact_root,
                pair_id,
                "prediction",
                "1",
                {
                    "predictive_scope": scope,
                    "baseline": predicted_baseline,
                    "candidate": predicted_candidate,
                },
            ),
            "artifact_scope_json_path": "predictive_scope",
            "baseline_json_path": "baseline",
            "candidate_json_path": "candidate",
        },
        "measurement": {
            "baseline": measured_baseline,
            "candidate": measured_candidate,
            **_artifact_binding(
                artifact_root,
                pair_id,
                "measurement",
                "2",
                {
                    "predictive_scope": scope,
                    "baseline": measured_baseline,
                    "candidate": measured_candidate,
                },
            ),
            "artifact_scope_json_path": "predictive_scope",
            "baseline_json_path": "baseline",
            "candidate_json_path": "candidate",
        },
        "cost_evidence": {},
    }
    if exact_cost_evidence:
        pair["cost_evidence"] = _cost_evidence(artifact_root, pair_id, scope)
    return pair


def _passing_pairs(
    artifact_root: Path,
    *,
    exact_cost_evidence: bool = False,
) -> list[dict[str, object]]:
    return [
        _pair(
            artifact_root,
            "pair-int4-short",
            "packed-int4",
            "short-context",
            0.20,
            0.18,
            exact_cost_evidence=exact_cost_evidence,
        ),
        _pair(
            artifact_root,
            "pair-kv-long",
            "tiered-kv",
            "long-context",
            0.10,
            0.105,
            exact_cost_evidence=exact_cost_evidence,
        ),
        _pair(
            artifact_root,
            "pair-scheduler-short",
            "scheduler-change",
            "short-context",
            -0.05,
            -0.052,
            exact_cost_evidence=exact_cost_evidence,
        ),
    ]


class PredictiveValidityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.artifact_root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_predeclared_thresholds_are_frozen(self) -> None:
        self.assertEqual(
            default_gate_spec(),
            {
                "required_distinct_interventions": 3,
                "required_context_regimes": 2,
                "maximum_relative_effect_size_error": 0.15,
                "minimum_spearman_rank_correlation": 0.8,
                "effect_size_definition": (
                    "fractional_candidate_change_from_each_baseline_oriented_positive_is_better"
                ),
                "relative_effect_size_error_definition": (
                    "absolute_predicted_minus_measured_benefit_effect_divided_by_absolute_measured_benefit_effect"
                ),
                "rank_correlation_definition": (
                    "spearman_of_predicted_and_measured_benefit_effects_with_average_tie_ranks"
                ),
                "pair_contract_version": "inference-foundry.predictive-pair.v1",
                "exact_scope_fields": [
                    "model_id",
                    "model_revision",
                    "workload_id",
                    "workload_revision",
                    "context_regime",
                    "hardware_id",
                    "hardware_revision",
                    "software_id",
                    "software_revision",
                    "intervention_id",
                    "intervention_revision",
                    "metric_id",
                    "metric_unit",
                    "higher_is_better",
                ],
                "exact_cost_execution_scope_fields": [
                    "model_id",
                    "model_revision",
                    "workload_id",
                    "workload_revision",
                    "context_regime",
                    "hardware_id",
                    "hardware_revision",
                    "software_id",
                    "software_revision",
                    "intervention_id",
                    "intervention_revision",
                ],
                "artifact_binding_fields": [
                    "artifact_path",
                    "artifact_sha256",
                    "artifact_content_id",
                    "artifact_content_id_json_path",
                    "artifact_scope_json_path",
                ],
                "observation_value_binding_fields": [
                    "baseline_json_path",
                    "candidate_json_path",
                ],
                "cost_criterion_binding_fields": [
                    "criterion_id_json_path",
                    "criterion_revision_json_path",
                    "passed_json_path",
                ],
                "artifact_binding_verification": (
                    "safe_workspace_relative_file_sha256_and_in_file_json_content_id"
                ),
                "require_all_directions_correct": True,
                "require_at_least_one_predicted_regression": True,
                "require_blinded_holdout": True,
                "require_prediction_locked_before_measurement": True,
                "require_global_calibration_holdout_nonoverlap": True,
                "require_exact_scope_identity": True,
                "require_exact_quality_and_slo_for_cost_promotion": True,
            },
        )

    def test_returned_gate_spec_cannot_mutate_frozen_contract(self) -> None:
        mutable_copy = default_gate_spec()
        mutable_copy["exact_scope_fields"].append("unexpected")

        self.assertNotIn("unexpected", default_gate_spec()["exact_scope_fields"])

    def test_three_interventions_two_regimes_and_regression_can_meet_gate(self) -> None:
        result = evaluate_pairs(
            _passing_pairs(self.artifact_root), artifact_root=self.artifact_root
        )

        self.assertEqual(result["status"], "MET")
        self.assertEqual(result["admitted_pair_count"], 3)
        self.assertEqual(result["distinct_intervention_count"], 3)
        self.assertEqual(result["context_regime_count"], 2)
        self.assertEqual(result["predicted_regression_count"], 1)
        self.assertAlmostEqual(result["spearman_rank_correlation"], 1.0)
        self.assertLessEqual(result["maximum_relative_effect_size_error"], 0.15)
        self.assertTrue(result["all_directions_correct"])
        self.assertFalse(result["cost_promotion_permitted"])

    def test_exact_scope_mismatch_rejects_pair(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["measurement_scope"]["software_revision"] = "different"

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertEqual(result["admitted_pair_count"], 2)
        self.assertIn(
            "scope_identity_mismatch",
            result["pairs"][0]["rejection_codes"],
        )

    def test_lower_is_better_metrics_are_oriented_as_benefits(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["prediction_scope"]["higher_is_better"] = False
        pairs[0]["measurement_scope"]["higher_is_better"] = False
        _rewrite_observation(
            self.artifact_root,
            pairs[0]["prediction"],
            scope=pairs[0]["prediction_scope"],
            candidate=80.0,
        )
        _rewrite_observation(
            self.artifact_root,
            pairs[0]["measurement"],
            scope=pairs[0]["measurement_scope"],
            candidate=82.0,
        )

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "MET")
        self.assertGreater(result["pairs"][0]["predicted_benefit_effect"], 0.0)
        self.assertTrue(result["pairs"][0]["direction_correct"])

    def test_duplicate_pair_ids_fail_closed(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[1]["pair_id"] = pairs[0]["pair_id"]

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertEqual(result["admitted_pair_count"], 1)
        self.assertTrue(
            all(
                "duplicate_pair_id" in pair["rejection_codes"]
                for pair in result["pairs"][:2]
            )
        )

    def test_zero_measured_effect_is_not_an_accuracy_success(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        _rewrite_observation(
            self.artifact_root,
            pairs[0]["measurement"],
            candidate=100.0,
        )

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertIn("measured_effect_is_zero", result["pairs"][0]["rejection_codes"])

    def test_invented_artifact_hash_and_content_id_fail_closed(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["prediction"]["artifact_sha256"] = "0" * 64
        pairs[1]["measurement"]["artifact_content_id"] = "f" * 64

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["admitted_pair_count"], 1)
        self.assertIn(
            "prediction_artifact_binding_invalid",
            result["pairs"][0]["rejection_codes"],
        )
        self.assertIn(
            "measurement_artifact_binding_invalid",
            result["pairs"][1]["rejection_codes"],
        )

    def test_pair_scope_must_match_scope_inside_bound_artifacts(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["prediction_scope"]["model_revision"] = "fabricated"
        pairs[0]["measurement_scope"]["model_revision"] = "fabricated"

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["admitted_pair_count"], 2)
        self.assertIn(
            "prediction_artifact_binding_invalid",
            result["pairs"][0]["rejection_codes"],
        )
        self.assertIn(
            "measurement_artifact_binding_invalid",
            result["pairs"][0]["rejection_codes"],
        )

    def test_pair_values_must_match_values_inside_bound_artifacts(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["prediction"]["candidate"] = 140.0

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["admitted_pair_count"], 2)
        self.assertIn(
            "prediction_artifact_binding_invalid",
            result["pairs"][0]["rejection_codes"],
        )

    def test_artifact_path_cannot_escape_verification_root(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["prediction"]["artifact_path"] = "../outside.json"

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertIn(
            "prediction_artifact_binding_invalid",
            result["pairs"][0]["rejection_codes"],
        )

    def test_unknown_pair_protocol_and_observation_fields_fail_closed(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["unexpected"] = True
        pairs[1]["protocol"]["unexpected"] = True
        pairs[2]["prediction"]["unexpected"] = True

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["admitted_pair_count"], 0)
        self.assertIn(
            "pair_contract_fields_invalid", result["pairs"][0]["rejection_codes"]
        )
        self.assertIn("protocol_fields_invalid", result["pairs"][1]["rejection_codes"])
        self.assertIn(
            "prediction_fields_invalid",
            result["pairs"][2]["rejection_codes"],
        )

    def test_global_calibration_holdout_overlap_rejects_affected_pairs(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[1]["protocol"]["holdout_case_id"] = "calibration-pair-int4-short"

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertEqual(result["admitted_pair_count"], 1)
        self.assertEqual(
            result["global_calibration_holdout_overlap_ids"],
            ["calibration-pair-int4-short"],
        )
        self.assertTrue(
            all(
                "calibration_holdout_overlap" in pair["rejection_codes"]
                for pair in result["pairs"][:2]
            )
        )

    def test_prediction_must_be_blinded_and_locked_before_measurement(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        pairs[0]["protocol"]["blinded_holdout"] = False
        pairs[1]["protocol"]["prediction_locked_at_unix_ms"] = 300

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertIn("holdout_not_blinded", result["pairs"][0]["rejection_codes"])
        self.assertIn(
            "prediction_not_locked_before_measurement",
            result["pairs"][1]["rejection_codes"],
        )

    def test_effect_error_above_fifteen_percent_fails_gate(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        _rewrite_observation(
            self.artifact_root,
            pairs[0]["measurement"],
            candidate=125.0,
        )

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertGreater(result["maximum_relative_effect_size_error"], 0.15)
        self.assertIn("effect_size_error_above_limit", result["reasons"])

    def test_rank_correlation_below_point_eight_fails_gate(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        _rewrite_observation(
            self.artifact_root,
            pairs[0]["measurement"],
            candidate=105.0,
        )
        _rewrite_observation(
            self.artifact_root,
            pairs[1]["measurement"],
            candidate=120.0,
        )

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertLess(result["spearman_rank_correlation"], 0.8)
        self.assertIn("rank_correlation_below_limit", result["reasons"])

    def test_correct_directions_without_predicted_regression_fail_gate(self) -> None:
        pairs = _passing_pairs(self.artifact_root)
        _rewrite_observation(
            self.artifact_root,
            pairs[2]["prediction"],
            candidate=105.0,
        )
        _rewrite_observation(
            self.artifact_root,
            pairs[2]["measurement"],
            candidate=105.2,
        )

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "NOT_MET")
        self.assertEqual(result["predicted_regression_count"], 0)
        self.assertIn("predicted_regression_missing", result["reasons"])

    def test_cost_promotion_requires_exact_quality_and_slo_evidence(self) -> None:
        without_cost_evidence = evaluate_pairs(
            _passing_pairs(self.artifact_root), artifact_root=self.artifact_root
        )
        with_cost_evidence = evaluate_pairs(
            _passing_pairs(self.artifact_root, exact_cost_evidence=True),
            artifact_root=self.artifact_root,
        )

        self.assertTrue(without_cost_evidence["predictive_validity_met"])
        self.assertFalse(without_cost_evidence["cost_promotion_permitted"])
        self.assertTrue(with_cost_evidence["cost_promotion_permitted"])
        self.assertEqual(with_cost_evidence["quality_slo_exact_pair_count"], 3)

    def test_quality_scope_mismatch_blocks_cost_promotion(self) -> None:
        pairs = _passing_pairs(self.artifact_root, exact_cost_evidence=True)
        pairs[0]["cost_evidence"]["quality"]["execution_scope"]["model_revision"] = (
            "different"
        )

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "MET")
        self.assertFalse(result["cost_promotion_permitted"])
        self.assertEqual(result["quality_slo_exact_pair_count"], 2)

    def test_unverified_quality_hash_blocks_cost_promotion(self) -> None:
        pairs = _passing_pairs(self.artifact_root, exact_cost_evidence=True)
        pairs[0]["cost_evidence"]["quality"]["artifact_sha256"] = "0" * 64

        result = evaluate_pairs(pairs, artifact_root=self.artifact_root)

        self.assertEqual(result["status"], "MET")
        self.assertFalse(result["cost_promotion_permitted"])
        self.assertEqual(result["quality_slo_exact_pair_count"], 2)


if __name__ == "__main__":
    unittest.main()
