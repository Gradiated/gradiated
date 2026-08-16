use foundry_core::qwen_int4_kernel::{
    PredictiveMeasurementScope, QwenInt4Aarch64NeonReport, QwenInt4Aarch64NeonRequest,
    QwenInt4KernelSmokeRequest, validate_qwen_int4_aarch64_neon_request_contract,
};
use std::path::{Path, PathBuf};

const ARTIFACT_PATH: &str = "experiments/qwen3-0.6b/int4-aarch64-neon-v1.json";
const ARTIFACT_BLAKE3: &str = "d4a705486775d3893c4dac97de4f45e0b95e1ae711bdbe1b1284462bf62cac2c";
const CONTENT_ID: &str = "5494727ab064f8c189f89e88794bbd7c9234baf23ab657c11bae62eaa6f35d40";
const CONFIG_PATH: &str = "configs/qwen3-0.6b-int4-aarch64-neon-v1.json";
const CONFIG_BLAKE3: &str = "8c9f38791aea1e54178371a6aa41c0da5dda4c39b2640c778bbb044bfbd4165d";
const CORE_SOURCE_PATH: &str = "crates/foundry-core/src/qwen_int4_kernel.rs";
const CORE_SOURCE_BLAKE3: &str = "a7ecfb1311b12694ae737f193e1b6d57226e0ed98de6bacca7d280052cee5bbf";
const PREDICTION_PATH: &str = "validation/predictions/qwen3-0.6b-int4-aarch64-neon-v1.json";

#[test]
fn checked_neon_artifact_has_exact_identity_and_source_bindings() {
    let (artifact_bytes, report) = load_report();
    assert_eq!(blake3_hex(&artifact_bytes), ARTIFACT_BLAKE3);
    assert_eq!(report.schema_version, 1);
    assert_eq!(report.content_id, CONTENT_ID);
    assert!(report.verify_content_id().expect("content ID must verify"));
    let identity_bytes = serde_json::to_vec(&(report.schema_version, &report.result))
        .expect("report identity tuple must serialize");
    assert_eq!(blake3_hex(&identity_bytes), CONTENT_ID);

    let config_bytes = read_workspace_file(CONFIG_PATH);
    assert_eq!(blake3_hex(&config_bytes), CONFIG_BLAKE3);
    let request: QwenInt4Aarch64NeonRequest =
        serde_json::from_slice(&config_bytes).expect("checked NEON request must parse");
    validate_qwen_int4_aarch64_neon_request_contract(&request)
        .expect("checked NEON request contract must verify");
    assert_eq!(report.result.study_id, request.study_id);
    assert_eq!(report.result.base_request_path, request.base_request_path);
    assert_eq!(
        report.result.base_request_blake3,
        request.expected_base_request_blake3
    );
    assert_eq!(report.result.tensor_source_pins, request.tensor_source_pins);
    assert_eq!(report.result.benchmark, request.benchmark);
    assert_eq!(report.result.correctness, request.correctness);
    assert_eq!(
        report.result.predictive_scope.workload_revision,
        CONFIG_BLAKE3
    );

    let base_request_bytes = read_workspace_file(
        request
            .base_request_path
            .to_str()
            .expect("base request path must be UTF-8"),
    );
    assert_eq!(
        blake3_hex(&base_request_bytes),
        request.expected_base_request_blake3
    );
    let base_request: QwenInt4KernelSmokeRequest =
        serde_json::from_slice(&base_request_bytes).expect("base request must parse");
    assert_eq!(report.result.base_study_id, base_request.study_id);
    assert_eq!(report.result.checkpoint, base_request.checkpoint);
    assert_eq!(
        report.result.quality_evidence,
        base_request.quality_evidence
    );
    assert_eq!(
        report.result.checkpoint.expected_sha256,
        request.expected_checkpoint_sha256
    );
    assert_eq!(
        report.result.quality_evidence.expected_sha256,
        request.expected_quality_evidence_sha256
    );
    let report_pins = report
        .result
        .tensor_source_pins
        .iter()
        .map(|pin| (&pin.name, &pin.expected_source_bytes_blake3))
        .collect::<Vec<_>>();
    let base_pins = base_request
        .tensors
        .iter()
        .map(|pin| (&pin.name, &pin.expected_source_bytes_blake3))
        .collect::<Vec<_>>();
    assert_eq!(report_pins, base_pins);

    let verification = &report.result.source_verification;
    assert!(verification.base_request_blake3_verified);
    assert!(verification.checkpoint_sha256_pin_matches_base_request);
    assert!(verification.quality_evidence_sha256_pin_matches_base_request);
    assert!(verification.tensor_source_pins_match_base_request);
    assert!(verification.checkpoint_file_size_verified);
    assert!(verification.measured_tensor_blake3_pins_verified);
    assert!(!verification.checkpoint_declared_sha256_recomputed);
    assert!(!verification.quality_evidence_declared_sha256_recomputed);

    let prediction: serde_json::Value =
        serde_json::from_slice(&read_workspace_file(PREDICTION_PATH))
            .expect("locked prediction must parse");
    let prediction_scope: PredictiveMeasurementScope =
        serde_json::from_value(prediction["predictive_scope"].clone())
            .expect("locked prediction scope must parse");
    assert_eq!(prediction_scope, report.result.predictive_scope);
    assert_eq!(
        prediction["locked_inputs"]["config"]["path"].as_str(),
        Some(CONFIG_PATH)
    );
    assert_eq!(
        prediction["locked_inputs"]["config"]["blake3"].as_str(),
        Some(CONFIG_BLAKE3)
    );
    assert_eq!(
        prediction["locked_inputs"]["core_source"]["path"].as_str(),
        Some(CORE_SOURCE_PATH)
    );
    assert_eq!(
        prediction["locked_inputs"]["core_source"]["blake3"].as_str(),
        Some(CORE_SOURCE_BLAKE3)
    );
    assert_eq!(
        blake3_hex(&read_workspace_file(CORE_SOURCE_PATH)),
        CORE_SOURCE_BLAKE3
    );
    assert_eq!(
        prediction["locked_inputs"]["base_request"]["path"].as_str(),
        request.base_request_path.to_str()
    );
    assert_eq!(
        prediction["locked_inputs"]["base_request"]["blake3"].as_str(),
        Some(request.expected_base_request_blake3.as_str())
    );
}

#[test]
fn checked_neon_artifact_has_exact_predictive_scope_and_claim_boundary() {
    let (_, report) = load_report();
    assert_eq!(
        report.result.predictive_scope,
        PredictiveMeasurementScope {
            model_id: "Qwen/Qwen3-0.6B".into(),
            model_revision: "c1899de289a04d12100db370d81485cdf75e47ca".into(),
            workload_id: "qwen3-0.6b-layer0-o-gate-up-packed-matvec".into(),
            workload_revision: "8c9f38791aea1e54178371a6aa41c0da5dda4c39b2640c778bbb044bfbd4165d"
                .into(),
            context_regime: "decode-batch1-three-layer0-tensors".into(),
            hardware_id: "Apple M4 Pro".into(),
            hardware_revision: "Mac16,7-Apple-M4-Pro-14c-48GB".into(),
            software_id: "foundry-qwen-int4-aarch64-neon".into(),
            software_revision: "qwen-int4-aarch64-neon-v1".into(),
            intervention_id: "aarch64-neon-group8-packed-matvec".into(),
            intervention_revision: "v1".into(),
            metric_id: "summed_three_tensor_median_seconds".into(),
            metric_unit: "seconds".into(),
            higher_is_better: false,
        }
    );

    let claims = &report.result.claims;
    assert!(claims.local_aarch64_neon_intrinsic_correctness_permitted);
    assert!(claims.local_aarch64_neon_timing_observation_permitted);
    assert!(claims.local_scalar_packed_comparison_permitted);
    assert!(claims.local_f32_qdq_scalar_comparison_permitted);
    assert!(!claims.tuned_kernel_claim_permitted);
    assert!(!claims.blas_or_vllm_comparison_permitted);
    assert!(!claims.gpu_claim_permitted);
    assert!(!claims.quality_equivalence_claim_permitted);
    assert!(!claims.serving_claim_permitted);
    assert!(!claims.energy_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert!(!claims.provider_claim_permitted);
    assert!(!claims.production_claim_permitted);
    assert_eq!(report.result.host.architecture, "aarch64");
    assert_eq!(report.result.host.benchmark_thread_count, 1);
    assert_eq!(report.result.host.rust_profile, "release");
    assert!(report.result.compiler.release_profile);
    assert!(report.result.compiler.explicit_simd_intrinsics_used);
    assert!(!report.result.compiler.auto_vectorization_inspected);
    assert_eq!(report.result.limitations.len(), 8);
}

#[test]
fn checked_neon_artifact_aggregate_recomputes_from_correct_measurements() {
    let (_, report) = load_report();
    let measurements = &report.result.measurements;
    let aggregate = &report.result.aggregate;
    assert_eq!(measurements.len(), 3);
    assert_eq!(aggregate.tensor_count, measurements.len());

    let parameter_count = measurements
        .iter()
        .map(|measurement| measurement.parameter_count)
        .sum::<u64>();
    let summed_neon_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.aarch64_neon.median_seconds)
        .sum::<f64>();
    let summed_scalar_packed_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.scalar_packed.median_seconds)
        .sum::<f64>();
    let summed_floating_qdq_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.floating_qdq_scalar_reference.median_seconds)
        .sum::<f64>();
    assert_eq!(aggregate.parameter_count, parameter_count);
    assert_eq!(aggregate.parameter_count, 8_388_608);
    assert_eq!(
        aggregate.summed_neon_median_seconds,
        summed_neon_median_seconds
    );
    assert_eq!(
        aggregate.summed_neon_median_seconds,
        0.001_063_582_999_999_999_9
    );
    assert_eq!(
        aggregate.summed_scalar_packed_median_seconds,
        summed_scalar_packed_median_seconds
    );
    assert_eq!(
        aggregate.summed_scalar_packed_median_seconds,
        0.004_740_665_999_999_999
    );
    assert_eq!(
        aggregate.summed_floating_qdq_median_seconds,
        summed_floating_qdq_median_seconds
    );
    assert_eq!(aggregate.summed_floating_qdq_median_seconds, 0.003_493_126);
    assert_eq!(
        aggregate.scalar_packed_over_neon_speed_ratio,
        summed_scalar_packed_median_seconds / summed_neon_median_seconds
    );
    assert_eq!(
        aggregate.floating_qdq_over_neon_speed_ratio,
        summed_floating_qdq_median_seconds / summed_neon_median_seconds
    );
    assert!(aggregate.neon_faster_than_scalar_packed);
    assert!(aggregate.neon_faster_than_floating_qdq);
    assert!(aggregate.all_work_counts_equal);
    assert!(aggregate.all_correctness_checks_passed);
    assert!(aggregate.all_timed_regions_allocation_free);

    for measurement in measurements {
        assert_eq!(measurement.aarch64_neon.iterations, 31);
        assert_eq!(measurement.scalar_packed.iterations, 31);
        assert_eq!(measurement.floating_qdq_scalar_reference.iterations, 31);
        assert!(measurement.dequantized_weight_correctness.passed);
        assert!(measurement.neon_vs_scalar_packed_correctness.passed);
        assert!(measurement.neon_vs_floating_qdq_correctness.passed);
        assert!(
            measurement
                .neon_vs_scalar_packed_correctness
                .maximum_absolute_error
                <= 1e-3
        );
        assert!(measurement.neon_vs_scalar_packed_correctness.rmse <= 1e-4);
        assert!(
            measurement
                .neon_vs_floating_qdq_correctness
                .maximum_absolute_error
                <= 1e-3
        );
        assert!(measurement.neon_vs_floating_qdq_correctness.rmse <= 1e-4);
        assert_eq!(
            measurement.work.multiply_accumulate_terms_each,
            measurement.parameter_count
        );
        assert_eq!(
            measurement.work.nominal_arithmetic_operations_each,
            measurement.parameter_count * 2
        );
        assert!(measurement.work.exact_term_count_equal);
        assert!(!measurement.work.accumulation_order_equal);
        assert_eq!(measurement.memory.preallocated_output_buffer_count, 3);
        assert_eq!(measurement.memory.timed_region_allocation_bytes, 0);
        assert_eq!(measurement.alternating_order.forward_warmup_count, 3);
        assert_eq!(measurement.alternating_order.reverse_warmup_count, 2);
        assert_eq!(measurement.alternating_order.forward_measured_count, 16);
        assert_eq!(measurement.alternating_order.reverse_measured_count, 15);
        assert_eq!(
            measurement.scalar_packed_over_neon_speed_ratio,
            measurement.scalar_packed.median_seconds / measurement.aarch64_neon.median_seconds
        );
        assert_eq!(
            measurement.floating_qdq_over_neon_speed_ratio,
            measurement.floating_qdq_scalar_reference.median_seconds
                / measurement.aarch64_neon.median_seconds
        );
    }
}

fn load_report() -> (Vec<u8>, QwenInt4Aarch64NeonReport) {
    let bytes = read_workspace_file(ARTIFACT_PATH);
    let report = serde_json::from_slice(&bytes).expect("checked NEON artifact must parse");
    (bytes, report)
}

fn read_workspace_file(relative: &str) -> Vec<u8> {
    std::fs::read(workspace_root().join(relative)).expect("checked workspace file must be readable")
}

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("core crate must be in the workspace")
        .to_path_buf()
}

fn blake3_hex(bytes: &[u8]) -> String {
    blake3::hash(bytes).to_hex().to_string()
}
