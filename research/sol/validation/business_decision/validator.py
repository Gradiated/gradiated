from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path
from typing import Any


REQUIRED_SOURCE_IDS = frozenset(
    {
        "glm_current_cost_claim_composition",
        "competitive_simulation_landscape",
        "glm_agentic_mapping_screen",
        "glm_parallel_mapping_context_frontier",
        "glm_pd_serving_control",
        "qwen_int4_bf16_scale_piqa_256",
        "qwen_int4_bf16_scale_wikitext_4096",
        "qwen_int4_bf16_scale_wikitext_512",
        "qwen_int4_aarch64_neon_holdout",
        "qwen_int4_packed_batch_frontier",
        "qwen_int4_packed_scalar_smoke",
        "qwen_kv_head_dedup_frontier",
        "qwen_kv_head_recovery_2k",
        "qwen_vllm_cpu_repeatability_terminal",
        "ramulator2_hbm3_synthetic_irregular",
        "scalesim_qwen_glm_gemm_sweep",
        "simulator_predictive_validity_gate",
        "small_model_proxy_selection_memo",
        "timeloop_qwen_external_smoke",
    }
)

REQUIRED_NEW_LEVER_IDS = frozenset(
    {
        "generic_simulator_and_obvious_dsa_moat",
        "glm_agentic_mapping_deployment",
        "glm_synthetic_hbm3_locality_geometry",
        "simulator_predictive_validity",
        "small_model_proxy_scope",
        "qwen_aarch64_neon_local_kernel_holdout",
    }
)

REQUIRED_NEW_FACT_IDS = frozenset(
    {
        "agentic_mapping_c64_candidate_uncertain",
        "agentic_mapping_deployment_claim",
        "agentic_mapping_exact_evaluation_count",
        "agentic_mapping_prompt_equivalence",
        "agentic_mapping_proxy_request_count",
        "agentic_mapping_source_hashes_verified",
        "agentic_mapping_token_only_retarget",
        "agentic_mapping_weighted_evaluation_count",
        "competitive_business_claim_status",
        "competitive_entry_count",
        "competitive_first_glm_adjacent_entry",
        "competitive_gate_count",
        "competitive_moat_claim",
        "competitive_nosa_entry",
        "competitive_primary_source_count",
        "predictive_gate_admitted_pairs",
        "predictive_gate_all_directions_correct",
        "predictive_gate_audit_count",
        "predictive_gate_cost_promotion",
        "predictive_gate_inventory_count",
        "predictive_gate_observed_effect_error",
        "predictive_gate_pair_measured_effect",
        "predictive_gate_pair_predicted_effect",
        "predictive_gate_predicted_regression_count",
        "predictive_gate_max_effect_error",
        "predictive_gate_min_spearman",
        "predictive_gate_required_context_regimes",
        "predictive_gate_required_interventions",
        "predictive_gate_status",
        "ramulator_32b_cluster64_ratio",
        "ramulator_32b_sort_ratio",
        "ramulator_bf16_cluster64_ratio",
        "ramulator_bf16_sort_ratio",
        "ramulator_build_status",
        "ramulator_calibration_claim",
        "ramulator_case_count",
        "ramulator_cost_claim",
        "ramulator_cross_geometry_comparison",
        "ramulator_glm_performance_claim",
        "ramulator_native_status",
        "ramulator_tapeout_claim",
        "ramulator_within_geometry_only",
        "small_proxy_no_glm_transfer",
        "small_proxy_nosa_future",
        "small_proxy_qwen_local",
        "neon_all_correctness_checks_passed",
        "neon_all_timed_regions_allocation_free",
        "neon_all_work_counts_equal",
        "neon_blas_or_vllm_claim",
        "neon_cost_per_token_claim",
        "neon_energy_claim",
        "neon_explicit_simd_intrinsics_used",
        "neon_faster_than_floating_qdq",
        "neon_faster_than_scalar_packed",
        "neon_floating_qdq_speed_ratio",
        "neon_floating_qdq_summed_median_seconds",
        "neon_parameter_count",
        "neon_production_claim",
        "neon_provider_claim",
        "neon_quality_equivalence_claim",
        "neon_scalar_packed_speed_ratio",
        "neon_scalar_packed_summed_median_seconds",
        "neon_serving_claim",
        "neon_summed_median_seconds",
        "neon_tensor_count",
        "neon_tuned_kernel_claim",
    }
)

REQUIRED_NEW_ARITHMETIC_IDS = frozenset(
    {
        "agentic_mapping_exact_grid_count",
        "agentic_mapping_request_weighted_count",
        "competitive_glm_adjacent_entry_count",
        "predictive_gate_inventory_family_sum",
        "neon_floating_qdq_over_neon_ratio",
        "neon_measured_time_reduction",
        "neon_prediction_relative_effect_error",
        "neon_scalar_packed_over_neon_ratio",
        "ramulator_32b_sort_cycle_change",
        "ramulator_bf16_sort_cycle_change",
        "ramulator_geometry_case_count",
    }
)

REQUIRED_LEVER_CONTRACTS = {
    "generic_simulator_and_obvious_dsa_moat": {
        "decision": "kill",
        "source_ids": ["competitive_simulation_landscape"],
        "checked_facts.all_decision_gates_not_met": True,
        "claims.generic_simulator_moat_permitted": False,
        "claims.obvious_dsa_moat_permitted": False,
        "claims.commercial_moat_permitted": False,
    },
    "glm_agentic_mapping_deployment": {
        "decision": "measure",
        "source_ids": ["glm_agentic_mapping_screen"],
        "checked_facts.candidate_full_capacity_uncertain_request_count_by_concurrency": [
            64,
            64,
            64,
            64,
            64,
        ],
        "claims.deployment_validated_permitted": False,
        "claims.latency_or_throughput_permitted": False,
        "claims.quality_or_slo_permitted": False,
        "claims.cost_per_token_reduction_permitted": False,
    },
    "glm_synthetic_hbm3_locality_geometry": {
        "decision": "kill",
        "source_ids": ["ramulator2_hbm3_synthetic_irregular"],
        "checked_facts.cross_geometry_comparison_permitted": False,
        "claims.geometry_insensitive_locality_benefit_permitted": False,
        "claims.cross_geometry_performance_comparison_permitted": False,
        "claims.calibrated_simulation_permitted": False,
        "claims.glm_performance_permitted": False,
        "claims.cost_or_tapeout_permitted": False,
    },
    "simulator_predictive_validity": {
        "decision": "measure",
        "source_ids": ["simulator_predictive_validity_gate"],
        "checked_facts.status": "NOT_MET",
        "checked_facts.admitted_exact_scope_pair_count": 1,
        "checked_facts.maximum_observed_relative_effect_size_error": 0.44746583093174686,
        "checked_facts.all_directions_correct": True,
        "checked_facts.predicted_regression_count": 0,
        "claims.simulator_predictive_validity_permitted": False,
        "claims.calibrated_simulation_permitted": False,
        "claims.cost_promotion_permitted": False,
        "claims.provider_or_tapeout_claim_permitted": False,
    },
    "qwen_aarch64_neon_local_kernel_holdout": {
        "decision": "pursue",
        "source_ids": [
            "qwen_int4_aarch64_neon_holdout",
            "simulator_predictive_validity_gate",
        ],
        "checked_facts.tensor_count": 3,
        "checked_facts.parameter_count": 8388608,
        "checked_facts.scalar_packed_over_neon_speed_ratio": 4.457260035182961,
        "checked_facts.floating_qdq_over_neon_speed_ratio": 3.2843003319910156,
        "checked_facts.predicted_benefit_effect": 0.4285714285714285,
        "checked_facts.measured_benefit_effect": 0.7756469238710342,
        "checked_facts.relative_effect_size_error": 0.44746583093174686,
        "checked_facts.all_work_counts_equal": True,
        "checked_facts.all_correctness_checks_passed": True,
        "checked_facts.all_timed_regions_allocation_free": True,
        "claims.local_aarch64_neon_intrinsic_speedup_permitted": True,
        "claims.prospective_direction_match_permitted": True,
        "claims.predictive_magnitude_validation_permitted": False,
        "claims.tuned_kernel_claim_permitted": False,
        "claims.blas_or_vllm_comparison_permitted": False,
        "claims.quality_equivalence_claim_permitted": False,
        "claims.serving_claim_permitted": False,
        "claims.energy_claim_permitted": False,
        "claims.cost_per_token_reduction_permitted": False,
        "claims.provider_claim_permitted": False,
        "claims.production_claim_permitted": False,
        "claims.transfer_to_glm_permitted": False,
    },
    "small_model_proxy_scope": {
        "decision": "pursue",
        "source_ids": [
            "small_model_proxy_selection_memo",
            "competitive_simulation_landscape",
        ],
        "checked_facts.current_local_proxy": "Qwen/Qwen3-0.6B",
        "checked_facts.future_single_gpu_sparse_memory_proxy": "openbmb/NOSA-1B",
        "checked_facts.nosa_revision": "7bdc33fbc1bc80b76b29689ba35ff6a7991b7dee",
        "checked_facts.nosa_checkpoint_lfs_sha256": "831236605310bdfded1fc5959dfecd033b48a0aa3ebdd2aa28f19d0ecf5ce4aa",
        "claims.nosa_causal_cost_savings_permitted": False,
        "claims.small_model_to_glm_transfer_permitted": False,
        "claims.glm_cost_or_performance_claim_permitted": False,
    },
}

PERMITTED_TRUE_LEVER_CLAIMS = {
    "qwen_selective_int4_o_gate_up": frozenset(
        {
            "teacher_forced_quality_proxy_pass_permitted",
            "frozen_piqa_subset_point_gate_pass_permitted",
            "local_packed_correctness_permitted",
            "local_scalar_timing_observation_permitted",
        }
    ),
    "qwen_one_shot_kv_head_pair_mean": frozenset(
        {"teacher_forced_quality_frontier_permitted"}
    ),
    "qwen_trained_full_kv_head_recovery_rank8_qo": frozenset(),
    "qwen_vllm_cpu_repeatability_baseline": frozenset(
        {"host_contamination_observation_permitted"}
    ),
    "glm_prefill_decode_disaggregation": frozenset(
        {"deterministic_synthetic_control_permitted"}
    ),
    "glm_independent_attention_expert_parallel_mapping": frozenset(
        {
            "partial_residency_arithmetic_permitted",
            "modeled_network_arithmetic_permitted",
        }
    ),
    "glm_public_nvfp4_and_fp8_kv_baseline": frozenset(
        {"incumbent_control_requirement_permitted"}
    ),
    "qwen_glm_dense_gemm_hardware_oracles": frozenset(
        {
            "native_scalesim_cycle_and_access_observations_permitted",
            "timeloop_frontend_contract_permitted",
        }
    ),
    "glm_joint_cost_claim_composition": frozenset(
        {"fail_closed_non_composition_permitted"}
    ),
    "glm_current_custom_hardware_roofline_rank": frozenset(
        {"component_sensitivity_permitted"}
    ),
    "glm_four_b200_residency_discontinuity": frozenset(
        {"aggregate_capacity_arithmetic_permitted"}
    ),
    "glm_current_economic_viability_screen": frozenset(
        {"configured_sensitivity_arithmetic_permitted"}
    ),
    "current_custom_silicon_program": frozenset(
        {"fixture_component_diagnostic_permitted"}
    ),
    "business_differentiation_after_incumbent_dossier": frozenset(
        {"incumbent_mechanism_floor_permitted"}
    ),
    "generic_simulator_and_obvious_dsa_moat": frozenset(
        {"remaining_wedge_as_hypothesis_permitted"}
    ),
    "glm_agentic_mapping_deployment": frozenset(
        {"exact_capacity_arithmetic_permitted"}
    ),
    "glm_synthetic_hbm3_locality_geometry": frozenset(
        {
            "patched_native_oracle_operability_permitted",
            "within_geometry_sensitivity_permitted",
        }
    ),
    "simulator_predictive_validity": frozenset(
        {"artifact_bound_gate_contract_permitted"}
    ),
    "qwen_aarch64_neon_local_kernel_holdout": frozenset(
        {
            "local_aarch64_neon_intrinsic_speedup_permitted",
            "prospective_direction_match_permitted",
        }
    ),
    "small_model_proxy_scope": frozenset(
        {
            "qwen_current_local_proxy_scope_permitted",
            "nosa_future_cuda_proxy_scope_permitted",
        }
    ),
}

FORBIDDEN_TRUE_PATHS = (
    "claim_permissions.business_viability",
    "claim_permissions.custom_hardware_advantage",
    "claim_permissions.custom_hardware_buildability",
    "claim_permissions.custom_silicon_tapeout_go",
    "claim_permissions.calibrated_simulation",
    "claim_permissions.five_x_improvement",
    "claim_permissions.generic_end_to_end_simulator_moat",
    "claim_permissions.geometry_insensitive_locality_benefit",
    "claim_permissions.glm_agentic_mapping_deployment_validated",
    "claim_permissions.material_cost_per_token_improvement",
    "claim_permissions.measured_fully_loaded_cost_per_token_reduction",
    "claim_permissions.measured_packed_int4_kernel_speedup",
    "claim_permissions.obvious_glm_dsa_moat",
    "claim_permissions.provider_superiority",
    "claim_permissions.predictive_neon_magnitude_validated",
    "claim_permissions.simulator_predictive_validity",
    "claim_permissions.small_model_to_glm_transfer",
    "claim_permissions.task_or_agent_quality_noninferiority",
    "claim_permissions.ten_x_improvement",
    "overall_decision.current_evidence_supports_10x_cost_per_token_improvement",
    "overall_decision.current_evidence_supports_5x_cost_per_token_improvement",
    "overall_decision.current_evidence_supports_buildable_custom_hardware",
    "overall_decision.current_evidence_supports_calibrated_simulation",
    "overall_decision.current_evidence_supports_a_full_end_to_end_simulation_claim",
    "overall_decision.current_evidence_supports_any_measured_cost_per_token_reduction",
    "overall_decision.current_evidence_supports_material_cost_per_token_reduction",
    "overall_decision.current_evidence_supports_provider_superiority",
    "overall_decision.launch_provider_on_current_evidence",
    "overall_decision.underwrite_custom_silicon_on_current_evidence",
)

CONTENT_ID_SCOPES = (
    "content_identity_sha256",
    "content_id",
    "provenance.detailed_artifact.content_identity_sha256",
    "provenance.content_identity_sha256",
)


def _nested_value(document: dict[str, Any], scope: str) -> Any:
    value: Any = document
    for key in scope.split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
            continue
        if isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
            continue
        else:
            return None
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_content_identity(document: dict[str, Any]) -> str:
    stable = {
        key: value
        for key, value in document.items()
        if key != "content_identity_sha256"
    }
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _evaluate_arithmetic(expression: str) -> float:
    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        raise ValueError("unsupported arithmetic expression")

    return evaluate(ast.parse(expression, mode="eval"))


def _content_id(document: dict[str, Any], source: dict[str, Any]) -> Any:
    scope = source.get("internal_content_id_scope")
    if scope:
        return _nested_value(document, scope)
    expected = source.get("internal_content_id")
    for candidate in CONTENT_ID_SCOPES:
        value = _nested_value(document, candidate)
        if value == expected:
            return value
    return None


def validate_ledger(ledger_path: Path, repo_root: Path) -> list[str]:
    ledger = json.loads(ledger_path.read_text())
    root = repo_root.resolve()
    errors: list[str] = []
    if ledger.get("content_identity_sha256") != canonical_content_identity(ledger):
        errors.append("ledger content identity mismatch")
    sources = ledger.get("sources", [])
    source_ids = [source.get("source_id") for source in sources]
    duplicates = sorted(
        {source_id for source_id in source_ids if source_ids.count(source_id) > 1}
    )
    if duplicates:
        errors.append(f"duplicate source ids: {duplicates}")
    missing = sorted(REQUIRED_SOURCE_IDS.difference(source_ids))
    if missing:
        errors.append(f"missing required source ids: {missing}")

    internal_bound_count = 0
    source_documents: dict[str, Any] = {}
    for source in sources:
        source_id = source.get("source_id", "<missing>")
        relative = Path(source.get("path", ""))
        resolved = (root / relative).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            errors.append(f"{source_id}: path escapes repository")
            continue
        if not resolved.is_file():
            errors.append(f"{source_id}: source file missing")
            continue
        actual_sha256 = _sha256(resolved)
        if actual_sha256 != source.get("file_sha256"):
            errors.append(f"{source_id}: file sha256 mismatch")
        source_format = source.get("source_format", "json")
        if source_format == "json":
            try:
                document: Any = json.loads(resolved.read_text())
            except json.JSONDecodeError:
                errors.append(f"{source_id}: invalid JSON source")
                continue
        elif source_format == "markdown":
            document = resolved.read_text()
        else:
            errors.append(f"{source_id}: unsupported source format")
            continue
        source_documents[source_id] = document
        expected_content_id = source.get("internal_content_id")
        if expected_content_id is not None:
            if not isinstance(document, dict):
                errors.append(f"{source_id}: internal content id requires JSON source")
                continue
            internal_bound_count += 1
            if _content_id(document, source) != expected_content_id:
                errors.append(f"{source_id}: internal content id mismatch")

    fact_checks = ledger.get("evidence_fact_verification", [])
    fact_check_ids = [check.get("check_id") for check in fact_checks]
    duplicate_fact_checks = sorted(
        {check_id for check_id in fact_check_ids if fact_check_ids.count(check_id) > 1}
    )
    if duplicate_fact_checks:
        errors.append(f"duplicate evidence fact check ids: {duplicate_fact_checks}")
    missing_fact_checks = sorted(REQUIRED_NEW_FACT_IDS.difference(fact_check_ids))
    if missing_fact_checks:
        errors.append(f"missing required fact check ids: {missing_fact_checks}")
    for check in fact_checks:
        check_id = check.get("check_id", "<missing>")
        source_id = check.get("source_id")
        document = source_documents.get(source_id)
        if document is None:
            errors.append(f"{check_id}: evidence fact source unavailable")
            continue
        check_kind = check.get("check_kind", "json_value")
        if check_kind == "json_value" and isinstance(document, dict):
            actual = _nested_value(document, check.get("source_scope", ""))
            matches = actual == check.get("expected")
        elif check_kind == "json_length" and isinstance(document, dict):
            actual = _nested_value(document, check.get("source_scope", ""))
            matches = isinstance(actual, (dict, list, str)) and len(
                actual
            ) == check.get("expected")
        elif check_kind == "json_all_value" and isinstance(document, dict):
            actual = _nested_value(document, check.get("source_scope", ""))
            item_scope = check.get("item_scope")
            matches = (
                isinstance(actual, list)
                and bool(actual)
                and isinstance(item_scope, str)
                and all(
                    isinstance(item, dict)
                    and _nested_value(item, item_scope) == check.get("expected")
                    for item in actual
                )
            )
        elif check_kind == "text_contains" and isinstance(document, str):
            expected = check.get("expected")
            matches = isinstance(expected, str) and expected in document
        else:
            matches = False
        if not matches:
            errors.append(f"{check_id}: evidence fact mismatch")

    arithmetic = ledger.get("arithmetic_verification", {})
    arithmetic_checks = arithmetic.get("checks", [])
    arithmetic_ids = [check.get("check_id") for check in arithmetic_checks]
    duplicate_arithmetic = sorted(
        {check_id for check_id in arithmetic_ids if arithmetic_ids.count(check_id) > 1}
    )
    if duplicate_arithmetic:
        errors.append(f"duplicate arithmetic check ids: {duplicate_arithmetic}")
    missing_arithmetic = sorted(REQUIRED_NEW_ARITHMETIC_IDS.difference(arithmetic_ids))
    if missing_arithmetic:
        errors.append(f"missing required arithmetic check ids: {missing_arithmetic}")
    if arithmetic.get("verified") is not True:
        errors.append("arithmetic_verification.verified: must be true")
    for check in arithmetic_checks:
        check_id = check.get("check_id", "<missing>")
        try:
            actual = _evaluate_arithmetic(check.get("expression", ""))
            expected = float(check["result"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError, SyntaxError):
            errors.append(f"{check_id}: invalid arithmetic check")
            continue
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            errors.append(f"{check_id}: arithmetic mismatch")

    summary = ledger.get("integrity_summary", {})
    expected_summary = {
        "source_count": len(sources),
        "file_sha256_bound_source_count": len(sources),
        "internal_content_id_bound_source_count": internal_bound_count,
        "evidence_fact_check_count": len(fact_checks),
        "lever_decision_count": len(ledger.get("lever_decisions", [])),
        "arithmetic_check_count": len(arithmetic_checks),
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            errors.append(f"integrity_summary.{key}: expected {expected}")

    lever_ids = [lever.get("lever_id") for lever in ledger.get("lever_decisions", [])]
    duplicate_levers = sorted(
        {lever_id for lever_id in lever_ids if lever_ids.count(lever_id) > 1}
    )
    if duplicate_levers:
        errors.append(f"duplicate lever ids: {duplicate_levers}")
    missing_levers = sorted(REQUIRED_NEW_LEVER_IDS.difference(lever_ids))
    if missing_levers:
        errors.append(f"missing required lever ids: {missing_levers}")
    levers_by_id = {
        lever.get("lever_id"): lever for lever in ledger.get("lever_decisions", [])
    }
    for lever_id, contract in REQUIRED_LEVER_CONTRACTS.items():
        lever = levers_by_id.get(lever_id)
        if lever is None:
            continue
        for scope, expected in contract.items():
            if _nested_value(lever, scope) != expected:
                errors.append(f"{lever_id}.{scope}: required lever contract mismatch")
    known_sources = set(source_ids)
    for lever in ledger.get("lever_decisions", []):
        unknown = sorted(set(lever.get("source_ids", [])).difference(known_sources))
        if unknown:
            errors.append(f"{lever.get('lever_id')}: unknown source ids: {unknown}")
        lever_id = lever.get("lever_id")
        claims = lever.get("claims")
        allowed_true_claims = PERMITTED_TRUE_LEVER_CLAIMS.get(lever_id)
        if allowed_true_claims is None:
            errors.append(f"{lever_id}: missing lever claim schema")
            continue
        if not isinstance(claims, dict) or any(
            not isinstance(value, bool) for value in claims.values()
        ):
            errors.append(f"{lever_id}: lever claims must be booleans")
            continue
        true_claims = {key for key, value in claims.items() if value}
        unapproved = sorted(true_claims.difference(allowed_true_claims))
        if unapproved:
            errors.append(f"{lever_id}: unapproved true lever claims: {unapproved}")
        missing_true_claims = sorted(allowed_true_claims.difference(true_claims))
        if missing_true_claims:
            errors.append(
                f"{lever_id}: missing permitted true lever claims: {missing_true_claims}"
            )

    for scope in FORBIDDEN_TRUE_PATHS:
        if _nested_value(ledger, scope) is not False:
            errors.append(f"{scope}: must be false")
    if (
        ledger.get("overall_decision", {}).get(
            "measured_fully_loaded_cost_per_token_improvement_multiplier"
        )
        is not None
    ):
        errors.append("measured fully loaded cost multiplier must be null")
    return errors
