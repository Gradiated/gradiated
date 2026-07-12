use foundry_core::glm_dsa::{
    DsaClaimBlocker, DsaEvidence, DsaEvidenceKind, DsaHardwareProfile, DsaIndexKeyCacheStorage,
    GLM_DSA_SWEEP_REQUEST_SCHEMA_VERSION, GlmDsaSweepReport, GlmDsaSweepRequest,
    evaluate_glm_dsa_sweep,
};
use foundry_core::spec::{HybridMoeMlaDsaSpec, ModelArchitecture, glm_5_2_bf16_reference};
use std::fs;
use std::path::Path;

#[test]
fn glm_indexshare_and_sparse_attention_work_reconcile_exactly() {
    let report = evaluate_glm_dsa_sweep(&request(vec![4_096])).unwrap();
    let point = &report.result.points[0];

    assert_eq!(point.context_tokens_per_request, 4_096);
    assert_eq!(point.selected_tokens_per_request, 2_048);
    assert_eq!(point.decode_query_tokens, 2);
    assert_eq!(point.indexshare.full_indexer_layers, 21);
    assert_eq!(point.indexshare.shared_index_layers, 57);
    assert_eq!(point.indexshare.indexer_projection_flops, 787_239_936);
    assert_eq!(point.indexshare.index_score_scan_flops, 1_409_286_144);
    assert_eq!(point.indexshare.index_key_scan_bytes, 44_040_192);
    assert_eq!(point.indexshare.indexer_weight_bytes_per_step, 393_619_968);
    assert_eq!(point.indexshare.score_candidates, 172_032);
    assert_eq!(point.sparse_attention_flops, 44_493_176_832);
    assert_eq!(point.sparse_cache_read_bytes, 368_050_176);
    assert_eq!(point.dense_attention_flops, 88_986_353_664);
    assert_eq!(point.dense_cache_read_bytes, 736_100_352);
    assert_eq!(point.hbm_index_topk_write_bytes, 344_064);
    assert_eq!(point.hbm_index_attention_read_bytes, 1_277_952);
    assert_eq!(point.hbm_index_handoff_bytes, 1_622_016);
    assert_eq!(point.zero_hbm_handoff_upper_bound_hbm_bytes, 0);
    assert_eq!(
        report.result.full_indexer_layer_ids,
        full_indexer_layer_ids()
    );
    assert_eq!(
        report.result.index_key_cache_storage,
        index_key_cache_storage()
    );
    assert!(
        report
            .result
            .work_basis
            .contains("absorbed MLA core arithmetic")
    );
    assert!(
        report
            .result
            .work_basis
            .contains("21 top-k writes plus 78 attention reads")
    );
}

#[test]
fn indexshare_removes_fifty_seven_scans_and_weight_sets() {
    let report = evaluate_glm_dsa_sweep(&request(vec![4_096])).unwrap();
    let point = &report.result.points[0];

    assert_eq!(
        point
            .same_geometry_every_layer_indexing_counterfactual
            .full_indexer_layers,
        78
    );
    assert_eq!(
        point
            .same_geometry_every_layer_indexing_counterfactual
            .shared_index_layers,
        0
    );
    assert_eq!(
        point
            .same_geometry_every_layer_indexing_counterfactual
            .indexer_projection_flops,
        2_924_034_048
    );
    assert_eq!(
        point
            .same_geometry_every_layer_indexing_counterfactual
            .index_score_scan_flops,
        5_234_491_392
    );
    assert_eq!(
        point
            .same_geometry_every_layer_indexing_counterfactual
            .index_key_scan_bytes,
        163_577_856
    );
    assert_eq!(
        point
            .same_geometry_every_layer_indexing_counterfactual
            .indexer_weight_bytes_per_step,
        1_462_017_024
    );
    assert_close(point.indexshare_scan_reduction_fraction, 57.0 / 78.0);
}

#[test]
fn index_key_storage_is_independent_and_includes_metadata() {
    let mut request = request(vec![4_096]);
    request
        .index_key_cache_storage
        .value_storage_bits_per_element = 8;
    request.index_key_cache_storage.metadata_bytes_per_token = 4;

    let report = evaluate_glm_dsa_sweep(&request).unwrap();
    let point = &report.result.points[0];

    assert_eq!(point.index_key_bytes_per_full_indexer_token, 132);
    assert_eq!(point.indexshare.index_key_scan_bytes, 22_708_224);
    assert_eq!(
        report
            .result
            .index_key_cache_storage
            .value_storage_bits_per_element,
        8
    );
    assert_eq!(
        report
            .result
            .index_key_cache_storage
            .metadata_bytes_per_token,
        4
    );
}

#[test]
fn dsa_overhead_loses_below_selected_width_and_wins_at_long_context() {
    let report = evaluate_glm_dsa_sweep(&request(vec![1_024, 1_048_576])).unwrap();

    for timing in &report.result.points[0].hardware {
        assert!(
            timing.modeled_serial_component_indexshare_hbm_handoff_seconds
                > timing.modeled_serial_component_dense_attention_seconds
        );
        assert!(timing.component_time_ratio_dense_attention_over_indexshare_hbm_handoff < 1.0);
    }
    for timing in &report.result.points[1].hardware {
        assert!(
            timing.modeled_serial_component_indexshare_hbm_handoff_seconds
                < timing.modeled_serial_component_dense_attention_seconds
        );
        assert!(timing.component_time_ratio_dense_attention_over_indexshare_hbm_handoff > 1.0);
        assert!(
            timing
                .component_time_ratio_same_geometry_every_layer_indexing_over_indexshare_hbm_handoff
                > 1.0
        );
        assert!(
            timing.component_time_ratio_indexshare_hbm_handoff_over_zero_hbm_handoff_upper_bound
                > 1.0
        );
    }
}

#[test]
fn attention_slice_never_unlocks_end_to_end_or_cost_claims() {
    let report = evaluate_glm_dsa_sweep(&request(vec![32_768])).unwrap();
    let claims = &report.result.claims;

    assert!(!claims.end_to_end_latency_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert!(!claims.quality_claim_permitted);
    assert!(
        claims
            .blockers
            .contains(&DsaClaimBlocker::RemainingModelWorkNotModeled)
    );
    assert!(
        claims
            .blockers
            .contains(&DsaClaimBlocker::ServingAndContentionNotModeled)
    );
    assert!(
        claims
            .blockers
            .contains(&DsaClaimBlocker::HardwareTimingNotMeasured)
    );
    assert!(
        claims
            .blockers
            .contains(&DsaClaimBlocker::PeakSerialRooflineAndUtilizationNotCalibrated)
    );
    assert!(
        claims
            .blockers
            .contains(&DsaClaimBlocker::ResidencyAndDistributedMappingNotModeled)
    );
    assert!(
        claims
            .blockers
            .contains(&DsaClaimBlocker::SramCapacityBandwidthAndLatencyNotModeled)
    );
}

#[test]
fn invalid_models_contexts_profiles_and_unknown_fields_are_rejected() {
    let mut dense = request(vec![4_096]);
    dense.model.architecture = ModelArchitecture::DenseDecoder;
    assert!(evaluate_glm_dsa_sweep(&dense).is_err());

    let mut context = request(vec![4_096]);
    context.context_tokens_per_request = vec![0];
    assert!(evaluate_glm_dsa_sweep(&context).is_err());

    let mut duplicate = request(vec![4_096]);
    duplicate.hardware.push(duplicate.hardware[0].clone());
    assert!(evaluate_glm_dsa_sweep(&duplicate).is_err());

    let mut incompatible_dimensions = request(vec![4_096]);
    hybrid_mut(&mut incompatible_dimensions)
        .dsa_indexer
        .query_head_dimension = 64;
    assert!(evaluate_glm_dsa_sweep(&incompatible_dimensions).is_err());

    let mut unsupported_key_heads = request(vec![4_096]);
    hybrid_mut(&mut unsupported_key_heads)
        .dsa_indexer
        .key_head_count = 2;
    assert!(evaluate_glm_dsa_sweep(&unsupported_key_heads).is_err());

    let mut insufficient_index_width = request(vec![1_048_576]);
    insufficient_index_width.selected_index_bytes = 2;
    assert!(evaluate_glm_dsa_sweep(&insufficient_index_width).is_err());

    let mut sufficient_index_width = request(vec![1_048_576]);
    sufficient_index_width.selected_index_bytes = 3;
    assert!(evaluate_glm_dsa_sweep(&sufficient_index_width).is_ok());

    let mut missing_full_layer = request(vec![4_096]);
    missing_full_layer.full_indexer_layer_ids.pop();
    assert!(evaluate_glm_dsa_sweep(&missing_full_layer).is_err());

    let mut duplicate_full_layer = request(vec![4_096]);
    duplicate_full_layer.full_indexer_layer_ids[20] = 70;
    assert!(evaluate_glm_dsa_sweep(&duplicate_full_layer).is_err());

    let mut out_of_range_full_layer = request(vec![4_096]);
    out_of_range_full_layer.full_indexer_layer_ids[20] = 78;
    assert!(evaluate_glm_dsa_sweep(&out_of_range_full_layer).is_err());

    let mut wrong_sorted_full_layer_pattern = request(vec![4_096]);
    wrong_sorted_full_layer_pattern.full_indexer_layer_ids[3] = 5;
    assert!(evaluate_glm_dsa_sweep(&wrong_sorted_full_layer_pattern).is_err());

    let mut empty_storage_basis = request(vec![4_096]);
    empty_storage_basis.index_key_cache_storage.basis.clear();
    assert!(evaluate_glm_dsa_sweep(&empty_storage_basis).is_err());

    let mut zero_storage_bits = request(vec![4_096]);
    zero_storage_bits
        .index_key_cache_storage
        .value_storage_bits_per_element = 0;
    assert!(evaluate_glm_dsa_sweep(&zero_storage_bits).is_err());

    let mut value = serde_json::to_value(request(vec![4_096])).unwrap();
    value["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<GlmDsaSweepRequest>(value).is_err());
}

#[test]
fn report_identity_is_stable_and_detects_tampering() {
    let request = request(vec![4_096, 1_048_576]);
    let first = evaluate_glm_dsa_sweep(&request).unwrap();
    let second = evaluate_glm_dsa_sweep(&request).unwrap();

    assert_eq!(first.content_id, second.content_id);
    assert!(first.verify_content_id().unwrap());
    let mut tampered = first;
    tampered.result.points[0].sparse_cache_read_bytes += 1;
    assert!(!tampered.verify_content_id().unwrap());
}

#[test]
fn checked_in_dsa_sweep_round_trips_with_all_claims_locked() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request: GlmDsaSweepRequest =
        serde_json::from_slice(&fs::read(root.join("configs/glm-5.2-dsa-sweep-v1.json")).unwrap())
            .unwrap();
    let stored: GlmDsaSweepReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/dsa-indexshare-sweep-v1.json")).unwrap(),
    )
    .unwrap();
    let evaluated = evaluate_glm_dsa_sweep(&request).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(stored.result.points.len(), 6);
    assert_eq!(stored.result.full_indexer_layer_count, 21);
    assert_eq!(stored.result.shared_index_layer_count, 57);
    assert!(!stored.result.claims.end_to_end_latency_claim_permitted);
    assert!(!stored.result.claims.cost_per_token_claim_permitted);
}

fn request(context_tokens_per_request: Vec<u64>) -> GlmDsaSweepRequest {
    GlmDsaSweepRequest {
        schema_version: GLM_DSA_SWEEP_REQUEST_SCHEMA_VERSION,
        study_id: "glm-5.2-dsa-test".into(),
        model: glm_5_2_bf16_reference(),
        batch_size: 2,
        context_tokens_per_request,
        selected_index_bytes: 4,
        full_indexer_layer_ids: full_indexer_layer_ids(),
        index_key_cache_storage: index_key_cache_storage(),
        hardware: vec![
            profile(
                "h200-like-modeled",
                3_360_000_000_000.0,
                500_000_000_000_000.0,
                500_000_000_000_000.0,
                50_000_000_000.0,
            ),
            profile(
                "dsa-custom-upper-bound",
                12_000_000_000_000.0,
                2_000_000_000_000_000.0,
                2_000_000_000_000_000.0,
                500_000_000_000.0,
            ),
        ],
    }
}

fn full_indexer_layer_ids() -> Vec<u32> {
    vec![
        0, 1, 2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42, 46, 50, 54, 58, 62, 66, 70, 74,
    ]
}

fn index_key_cache_storage() -> DsaIndexKeyCacheStorage {
    DsaIndexKeyCacheStorage {
        value_storage_bits_per_element: 16,
        metadata_bytes_per_token: 0,
        basis: "Explicit BF16 index-key scenario; not a provider runtime baseline".into(),
        evidence: DsaEvidence {
            kind: DsaEvidenceKind::ModeledAssumption,
            source_artifact_id: "modeled:glm-5.2-bf16-index-key-cache".into(),
        },
    }
}

fn hybrid_mut(request: &mut GlmDsaSweepRequest) -> &mut HybridMoeMlaDsaSpec {
    match &mut request.model.architecture {
        ModelArchitecture::HybridMoeMlaDsa(hybrid) => hybrid,
        ModelArchitecture::DenseDecoder => panic!("hybrid model required"),
    }
}

fn profile(
    profile_id: &str,
    hbm_bytes_per_second: f64,
    indexer_flops_per_second: f64,
    attention_flops_per_second: f64,
    topk_score_candidates_per_second: f64,
) -> DsaHardwareProfile {
    DsaHardwareProfile {
        profile_id: profile_id.into(),
        scope_basis: "Single timing component; no model residency or deployment mapping".into(),
        hbm_bytes_per_second,
        indexer_flops_per_second,
        attention_flops_per_second,
        topk_score_candidates_per_second,
        evidence: DsaEvidence {
            kind: DsaEvidenceKind::ModeledAssumption,
            source_artifact_id: format!("modeled:{profile_id}"),
        },
    }
}

fn assert_close(actual: f64, expected: f64) {
    assert!((actual - expected).abs() < 1e-12, "{actual} != {expected}");
}
