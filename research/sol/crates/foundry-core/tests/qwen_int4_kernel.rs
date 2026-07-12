use foundry_core::qwen_int4_kernel::{
    PackedInt4Matrix, QwenInt4Aarch64NeonRequest, QwenInt4BatchFrontierReport,
    QwenInt4BatchFrontierRequest, QwenInt4KernelError, QwenInt4KernelSmokeReport,
    QwenInt4KernelSmokeRequest, ScaleStorage, floating_group8_qdq,
    floating_qdq_batch_matmul_feature_major, validate_qwen_int4_aarch64_neon_request_contract,
};
use std::path::Path;

#[test]
fn signed_group8_codes_and_bfloat16_scales_pack_exactly() {
    let weights = vec![
        -7.0, -6.0, -1.0, 0.0, 1.0, 2.0, 6.0, 7.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
    ];

    let packed = PackedInt4Matrix::pack_group8(&weights, 2, 8, ScaleStorage::Bfloat16)
        .expect("valid group-8 weights must pack");

    assert_eq!(packed.packed_codes(), &[0xa9, 0x0f, 0x21, 0x76, 0, 0, 0, 0]);
    assert_eq!(packed.scale_bits(), &[0x3f80, 0x3f80]);
    assert_eq!(packed.code_bytes(), 8);
    assert_eq!(packed.scale_bytes(), 4);
    assert_eq!(packed.packed_bytes(), 12);
    assert_eq!(packed.dequantize(), weights);
}

#[test]
fn packed_matvec_matches_independently_materialized_qdq_reference() {
    let weights = vec![
        -3.25, -2.5, -1.25, -0.25, 0.5, 1.5, 2.75, 3.5, 7.0, -6.0, 5.0, -4.0, 3.0, -2.0, 1.0, 0.0,
    ];
    let input = vec![0.25, -0.5, 0.75, -1.0, 1.25, -1.5, 1.75, -2.0];
    let packed = PackedInt4Matrix::pack_group8(&weights, 2, 8, ScaleStorage::Bfloat16)
        .expect("valid group-8 weights must pack");
    let reference_weights = floating_group8_qdq(&weights, 2, 8, ScaleStorage::Bfloat16)
        .expect("floating QDQ must accept the same shape");
    assert_eq!(packed.dequantize(), reference_weights);
    let expected = reference_weights
        .chunks_exact(8)
        .map(|row| {
            row.iter()
                .zip(&input)
                .map(|(weight, value)| weight * value)
                .sum()
        })
        .collect::<Vec<f32>>();

    let actual = packed
        .matvec(&input)
        .expect("matching input width must execute");

    assert_eq!(actual, expected);
    assert_eq!(packed.logical_bytes_read_per_output(), 6);
}

#[cfg(target_arch = "aarch64")]
#[test]
fn neon_packed_matvec_matches_scalar_packed_path() {
    let rows = 17;
    let columns = 72;
    let weights = (0..rows * columns)
        .map(|index| ((index * 37 % 101) as f32 - 50.0) / 11.0)
        .collect::<Vec<_>>();
    let input = (0..columns)
        .map(|index| ((index * 19 % 67) as f32 - 33.0) / 13.0)
        .collect::<Vec<_>>();
    let packed = PackedInt4Matrix::pack_group8(&weights, rows, columns, ScaleStorage::Bfloat16)
        .expect("valid group-8 weights must pack");

    let scalar = packed.matvec(&input).expect("scalar path must execute");
    let neon = packed
        .matvec_aarch64_neon(&input)
        .expect("NEON path must execute");
    let maximum_absolute_error = scalar
        .iter()
        .zip(&neon)
        .map(|(expected, actual)| (expected - actual).abs())
        .fold(0.0_f32, f32::max);

    assert!(maximum_absolute_error <= 0.0001, "{maximum_absolute_error}");
}

#[cfg(target_arch = "aarch64")]
#[test]
fn neon_packed_matvec_into_validates_reusable_buffers() {
    let packed = PackedInt4Matrix::pack_group8(&[1.0; 16], 2, 8, ScaleStorage::Bfloat16)
        .expect("valid group-8 weights must pack");
    let mut output = vec![0.0; 2];

    packed
        .matvec_aarch64_neon_into(&[1.0; 8], &mut output)
        .expect("matching buffers must execute");
    let scalar = packed.matvec(&[1.0; 8]).expect("scalar path must execute");
    assert_eq!(output, scalar);

    assert!(matches!(
        packed.matvec_aarch64_neon_into(&[1.0; 7], &mut output),
        Err(QwenInt4KernelError::InputWidthMismatch { .. })
    ));
    assert!(matches!(
        packed.matvec_aarch64_neon_into(&[1.0; 8], &mut [0.0]),
        Err(QwenInt4KernelError::OutputHeightMismatch { .. })
    ));
}

#[test]
fn aarch64_neon_request_pins_exact_execution_and_correctness_contract() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("core crate must be in the workspace");
    let request: QwenInt4Aarch64NeonRequest = serde_json::from_slice(
        &std::fs::read(root.join("configs/qwen3-0.6b-int4-aarch64-neon-v1.json"))
            .expect("NEON request must be readable"),
    )
    .expect("NEON request must parse");

    validate_qwen_int4_aarch64_neon_request_contract(&request)
        .expect("the checked request must satisfy the immutable contract");
    assert_eq!(request.benchmark.required_target_architecture, "aarch64");
    assert_eq!(request.benchmark.required_target_feature, "neon");
    assert!(request.benchmark.require_release_build);
    assert_eq!(request.benchmark.thread_count, 1);
    assert_eq!(request.benchmark.warmup_iterations, 5);
    assert_eq!(request.benchmark.measured_iterations, 31);
    assert!(request.benchmark.preallocated_output_buffers);
    assert!(request.benchmark.alternate_forward_reverse_order);
    assert_eq!(request.correctness.maximum_output_absolute_error, 1e-3);
    assert_eq!(request.correctness.maximum_output_rmse, 1e-4);
    assert_eq!(request.tensor_source_pins.len(), 3);
}

#[test]
fn aarch64_neon_request_rejects_post_result_contract_loosening() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("core crate must be in the workspace");
    let request: QwenInt4Aarch64NeonRequest = serde_json::from_slice(
        &std::fs::read(root.join("configs/qwen3-0.6b-int4-aarch64-neon-v1.json"))
            .expect("NEON request must be readable"),
    )
    .expect("NEON request must parse");

    let mut wrong_samples = request.clone();
    wrong_samples.benchmark.measured_iterations = 30;
    assert!(matches!(
        validate_qwen_int4_aarch64_neon_request_contract(&wrong_samples),
        Err(QwenInt4KernelError::InvalidField(
            "benchmark.measured_iterations"
        ))
    ));

    let mut changed_tensor = request.clone();
    changed_tensor.tensor_source_pins[0].expected_source_bytes_blake3 = "0".repeat(64);
    assert!(matches!(
        validate_qwen_int4_aarch64_neon_request_contract(&changed_tensor),
        Err(QwenInt4KernelError::InvalidField("tensor_source_pins"))
    ));

    let mut loosened = request;
    loosened.correctness.maximum_output_absolute_error = 1.1e-3;
    assert!(matches!(
        validate_qwen_int4_aarch64_neon_request_contract(&loosened),
        Err(QwenInt4KernelError::InvalidField(
            "correctness.maximum_output_absolute_error"
        ))
    ));
}

#[test]
fn group_size_shape_and_input_width_fail_closed() {
    let wrong_group = PackedInt4Matrix::pack_groupwise(&[1.0; 16], 2, 8, 4, ScaleStorage::Bfloat16)
        .expect_err("only the quality-checked group size may pack");
    assert!(matches!(
        wrong_group,
        QwenInt4KernelError::UnsupportedGroupSize(4)
    ));

    let wrong_shape = PackedInt4Matrix::pack_group8(&[1.0; 15], 2, 8, ScaleStorage::Bfloat16)
        .expect_err("weight count must match the matrix shape");
    assert!(matches!(
        wrong_shape,
        QwenInt4KernelError::WeightCountMismatch { .. }
    ));

    let packed = PackedInt4Matrix::pack_group8(&[1.0; 16], 2, 8, ScaleStorage::Bfloat16)
        .expect("valid weights must pack");
    assert!(matches!(
        packed.matvec(&[1.0; 7]),
        Err(QwenInt4KernelError::InputWidthMismatch { .. })
    ));
}

#[test]
fn packing_is_deterministic_and_identity_covers_scale_storage() {
    let weights = (0..32)
        .map(|index| (index as f32 - 16.0) / 7.0)
        .collect::<Vec<_>>();

    let first = PackedInt4Matrix::pack_group8(&weights, 4, 8, ScaleStorage::Bfloat16)
        .expect("valid weights must pack");
    let second = PackedInt4Matrix::pack_group8(&weights, 4, 8, ScaleStorage::Bfloat16)
        .expect("valid weights must pack");

    assert_eq!(first.checksum_blake3(), second.checksum_blake3());
    assert_eq!(first.packed_codes(), second.packed_codes());
    assert_eq!(first.scale_bits(), second.scale_bits());
}

#[test]
fn checked_request_and_measured_report_are_self_consistent() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("core crate must be in the workspace");
    let request: QwenInt4KernelSmokeRequest = serde_json::from_slice(
        &std::fs::read(root.join("configs/qwen3-0.6b-int4-packed-kernel-smoke-v1.json"))
            .expect("request must be readable"),
    )
    .expect("request must parse");
    let report: QwenInt4KernelSmokeReport = serde_json::from_slice(
        &std::fs::read(root.join("experiments/qwen3-0.6b/int4-packed-kernel-smoke-v1.json"))
            .expect("report must be readable"),
    )
    .expect("report must parse");

    assert!(report.verify_content_id().expect("identity must verify"));
    assert_eq!(report.result.study_id, request.study_id);
    assert_eq!(report.result.measurements.len(), 3);
    assert_eq!(report.result.aggregate.parameter_count, 8_388_608);
    assert_eq!(report.result.aggregate.total_packed_bytes, 6_291_456);
    assert!(report.result.aggregate.all_correctness_checks_passed);
    assert!(
        report
            .result
            .aggregate
            .raw_speed_ratio_reference_over_packed
            < 1.0
    );
    assert!(!report.result.claims.blas_or_vllm_comparison_permitted);
    assert!(!report.result.claims.cost_per_token_claim_permitted);
}

#[test]
fn batch_one_weight_stationary_path_equals_scalar_matvec() {
    let weights = (0..16)
        .map(|index| (index as f32 - 8.0) / 3.0)
        .collect::<Vec<_>>();
    let input = (0..8)
        .map(|index| (index as f32 - 4.0) / 5.0)
        .collect::<Vec<_>>();
    let packed = PackedInt4Matrix::pack_group8(&weights, 2, 8, ScaleStorage::Bfloat16)
        .expect("valid weights must pack");

    let scalar = packed.matvec(&input).expect("scalar path must execute");
    let batch = packed
        .batch_matmul_feature_major(&input, 1, 64)
        .expect("batch-one path must execute");

    assert_eq!(batch, scalar);
}

#[test]
fn tiled_batch_path_matches_independent_floating_qdq_reference() {
    let weights = (0..16)
        .map(|index| ((index * 17 % 23) as f32 - 11.0) / 7.0)
        .collect::<Vec<_>>();
    let batch_size = 4;
    let input = (0..8 * batch_size)
        .map(|index| ((index * 13 % 19) as f32 - 9.0) / 8.0)
        .collect::<Vec<_>>();
    let packed = PackedInt4Matrix::pack_group8(&weights, 2, 8, ScaleStorage::Bfloat16)
        .expect("valid weights must pack");
    let reference_weights = floating_group8_qdq(&weights, 2, 8, ScaleStorage::Bfloat16)
        .expect("floating QDQ must execute");

    let actual = packed
        .batch_matmul_feature_major(&input, batch_size, 3)
        .expect("packed batch path must execute");
    let expected =
        floating_qdq_batch_matmul_feature_major(&reference_weights, 2, 8, &input, batch_size, 3)
            .expect("reference batch path must execute");

    assert_eq!(actual, expected);
}

#[test]
fn batch_layout_and_tile_fail_closed() {
    let packed = PackedInt4Matrix::pack_group8(&[1.0; 16], 2, 8, ScaleStorage::Bfloat16)
        .expect("valid weights must pack");

    assert!(matches!(
        packed.batch_matmul_feature_major(&[1.0; 31], 4, 4),
        Err(QwenInt4KernelError::BatchInputCountMismatch { .. })
    ));
    assert!(matches!(
        packed.batch_matmul_feature_major(&[], 0, 4),
        Err(QwenInt4KernelError::InvalidBatchSize)
    ));
    assert!(matches!(
        packed.batch_matmul_feature_major(&[1.0; 32], 4, 0),
        Err(QwenInt4KernelError::InvalidBatchTileSize)
    ));
}

#[test]
fn checked_batch_frontier_has_equal_work_exact_outputs_and_no_crossover() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("core crate must be in the workspace");
    let request: QwenInt4BatchFrontierRequest = serde_json::from_slice(
        &std::fs::read(root.join("configs/qwen3-0.6b-int4-packed-batch-frontier-v1.json"))
            .expect("frontier request must be readable"),
    )
    .expect("frontier request must parse");
    let report: QwenInt4BatchFrontierReport = serde_json::from_slice(
        &std::fs::read(root.join("experiments/qwen3-0.6b/int4-packed-batch-frontier-v1.json"))
            .expect("frontier report must be readable"),
    )
    .expect("frontier report must parse");

    assert!(report.verify_content_id().expect("identity must verify"));
    assert_eq!(report.result.study_id, request.study_id);
    assert_eq!(report.result.batch_sizes, vec![1, 4, 16, 64]);
    assert_eq!(report.result.measurements.len(), 3);
    assert_eq!(report.result.aggregate_points.len(), 4);
    for point in &report.result.aggregate_points {
        assert_eq!(
            point.multiply_accumulate_terms,
            8_388_608 * point.batch_size as u64
        );
        assert!(point.all_work_counts_equal);
        assert!(point.all_correctness_checks_passed);
        assert!(!point.packed_faster);
    }
    for measurement in &report.result.measurements {
        assert!(measurement.dequantized_weight_correctness.passed);
        for point in &measurement.points {
            assert!(point.work.exact_work_count_equal);
            assert!(point.work.accumulation_order_equal);
            assert!(point.correctness.checksum_match);
            assert_eq!(point.correctness.maximum_absolute_error, 0.0);
            assert_eq!(point.correctness.rmse, 0.0);
        }
    }
    assert!(report.result.crossover.strict_no_crossover_in_sweep);
    assert!(
        report
            .result
            .batch_one_scalar_reconciliation
            .direction_consistent
    );
    assert!(
        report
            .result
            .batch_one_scalar_reconciliation
            .both_observe_packed_slower
    );
    assert!(!report.result.claims.tuned_kernel_claim_permitted);
    assert!(!report.result.claims.cost_per_token_claim_permitted);
}
