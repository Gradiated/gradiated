use foundry_core::glm_storage::{EnvelopeEvidence, EnvelopeEvidenceKind, GlmStorageEnvelopeReport};
use foundry_core::residency_frontier::{
    FrontierCacheBound, FrontierClaimBlocker, GLM_RESIDENCY_FRONTIER_REQUEST_SCHEMA_VERSION,
    GlmResidencyFrontierError, GlmResidencyFrontierRequest, SemanticCacheFormatOverride,
    TargetCapacityTopology, evaluate_glm_residency_frontier,
};
use std::fs;
use std::path::Path;

#[test]
fn fp8_lower_frontier_reconciles_the_four_b200_capacity_miss() {
    let report = evaluate_glm_residency_frontier(&request(), &storage()).unwrap();
    let result = &report.result;
    let lower = frontier(result, FrontierCacheBound::Lower);

    assert!(report.verify_content_id().unwrap());
    assert_eq!(result.target_capacity_bytes, 656_000_000_000);
    assert_eq!(result.semantic_cache.source_bytes_per_token, 89_856);
    assert_eq!(result.semantic_cache.override_bytes_per_token, 44_928);
    assert_eq!(result.semantic_cache.reduction_bytes_per_token, 44_928);
    assert_eq!(result.semantic_cache.source_total_bytes, 188_441_690_112);
    assert_eq!(result.semantic_cache.override_total_bytes, 94_220_845_056);
    assert_eq!(result.semantic_cache.total_reduction_bytes, 94_220_845_056);
    assert_eq!(lower.override_unfragmented_resident_bytes, 575_015_651_328);
    assert_eq!(lower.override_fragmentation_overhead_bytes, 86_252_347_700);
    assert_eq!(lower.override_total_resident_bytes, 661_267_999_028);
    assert_eq!(lower.total_resident_reduction_required_bytes, 5_267_999_028);
    assert_eq!(lower.maximum_unfragmented_resident_bytes, 570_434_782_608);
    assert_eq!(lower.unfragmented_reduction_required_bytes, 4_580_868_720);
    assert_eq!(lower.maximum_fixed_runtime_bytes, Some(11_419_131_280));
    assert_eq!(
        lower.maximum_fixed_runtime_and_nonsemantic_cache_bytes,
        Some(11_419_131_280)
    );
    assert_eq!(lower.maximum_extra_cache_bytes_per_token, None);
    assert_eq!(
        lower.maximum_extra_cache_bytes_per_token_at_zero_fixed_runtime,
        Some(5_445)
    );
    assert_eq!(lower.maximum_reserved_token_slots, Some(1_995_191));
    assert_eq!(lower.maximum_reserved_tokens_per_sequence, Some(31_174));
    assert_eq!(lower.source_total_resident_bytes, 769_621_970_842);
    assert_eq!(
        lower.source_to_override_total_resident_reduction_bytes,
        108_353_971_814
    );
    assert!(!lower.aggregate_capacity_feasible);
}

#[test]
fn exact_sequence_and_fragmentation_boundaries_include_both_witnesses() {
    let report = evaluate_glm_residency_frontier(&request(), &storage()).unwrap();
    let lower = frontier(&report.result, FrontierCacheBound::Lower);

    assert_eq!(lower.sequence_boundary.maximum_feasible_sequences, Some(60));
    assert_eq!(
        lower.sequence_boundary.total_resident_bytes_at_maximum,
        Some(654_495_875_789)
    );
    assert_eq!(lower.sequence_boundary.first_infeasible_sequences, 61);
    assert_eq!(
        lower
            .sequence_boundary
            .total_resident_bytes_at_first_infeasible,
        656_188_906_599
    );
    assert_eq!(
        lower.fragmentation_boundary.maximum_feasible_basis_points,
        Some(1_408)
    );
    assert_eq!(
        lower.fragmentation_boundary.total_resident_bytes_at_maximum,
        Some(655_977_855_035)
    );
    assert_eq!(
        lower.fragmentation_boundary.first_infeasible_basis_points,
        1_409
    );
    assert_eq!(
        lower
            .fragmentation_boundary
            .total_resident_bytes_at_first_infeasible,
        656_035_356_601
    );
}

#[test]
fn upper_cache_frontier_remains_separate_and_more_constrained() {
    let report = evaluate_glm_residency_frontier(&request(), &storage()).unwrap();
    let upper = frontier(&report.result, FrontierCacheBound::Upper);

    assert_eq!(upper.extra_cache_bytes_per_token, 32_768);
    assert_eq!(upper.indexer_cache_bytes_per_token, 8_192);
    assert_eq!(upper.cache_bytes_per_reserved_token, 85_888);
    assert_eq!(upper.override_unfragmented_resident_bytes, 660_914_997_248);
    assert_eq!(upper.override_total_resident_bytes, 760_052_246_836);
    assert_eq!(
        upper.total_resident_reduction_required_bytes,
        104_052_246_836
    );
    assert_eq!(upper.maximum_reserved_token_slots, Some(1_043_684));
    assert_eq!(upper.sequence_boundary.maximum_feasible_sequences, Some(31));
    assert_eq!(upper.sequence_boundary.first_infeasible_sequences, 32);
    assert_eq!(upper.maximum_reserved_tokens_per_sequence, Some(16_307));
    assert_eq!(
        upper.fragmentation_boundary.maximum_feasible_basis_points,
        None
    );
    assert_eq!(
        upper.fragmentation_boundary.first_infeasible_basis_points,
        0
    );
    assert_eq!(upper.maximum_fixed_runtime_bytes, None);
    assert_eq!(upper.maximum_extra_cache_bytes_per_token, None);
}

#[test]
fn capacity_arithmetic_never_claims_topology_kernel_serving_or_cost_support() {
    let report = evaluate_glm_residency_frontier(&request(), &storage()).unwrap();
    let claims = &report.result.claims;

    assert!(claims.aggregate_capacity_arithmetic_permitted);
    assert!(!claims.executable_topology_permitted);
    assert!(!claims.model_format_kernel_support_permitted);
    assert!(!claims.end_to_end_serving_permitted);
    assert!(!claims.cost_per_token_permitted);
    assert_eq!(
        claims.blockers,
        vec![
            FrontierClaimBlocker::AggregateCapacityOnly,
            FrontierClaimBlocker::TargetExecutionTopologyNotValidated,
            FrontierClaimBlocker::ModelFormatKernelSupportNotValidated,
            FrontierClaimBlocker::RuntimeWorkspaceIsModeled,
            FrontierClaimBlocker::CacheLayoutMetadataIsBounded,
        ]
    );
}

#[test]
fn report_and_source_identity_fail_closed() {
    let storage = storage();
    let first = evaluate_glm_residency_frontier(&request(), &storage).unwrap();
    let second = evaluate_glm_residency_frontier(&request(), &storage).unwrap();
    assert_eq!(first.content_id, second.content_id);

    let mut wrong_pin = request();
    wrong_pin.storage_report_content_id = "wrong".into();
    assert_eq!(
        evaluate_glm_residency_frontier(&wrong_pin, &storage),
        Err(GlmResidencyFrontierError::StorageReportContentIdMismatch)
    );

    let mut tampered = storage;
    tampered.result.semantic_mla_cache_bytes_per_token += 1;
    assert_eq!(
        evaluate_glm_residency_frontier(&request(), &tampered),
        Err(GlmResidencyFrontierError::InvalidStorageReportContentId)
    );
}

#[test]
fn checked_config_and_report_round_trip_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request: GlmResidencyFrontierRequest = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-nvfp4-fp8-kv-four-b200-frontier-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: foundry_core::residency_frontier::GlmResidencyFrontierReport =
        serde_json::from_slice(
            &fs::read(root.join("experiments/glm-5.2/nvfp4-fp8-kv-four-b200-frontier-v1.json"))
                .unwrap(),
        )
        .unwrap();

    let evaluated = evaluate_glm_residency_frontier(&request, &storage()).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
}

#[test]
fn schema_is_strict_and_capacity_overflow_is_rejected() {
    let mut value = serde_json::to_value(request()).unwrap();
    value
        .as_object_mut()
        .unwrap()
        .insert("unknown".into(), true.into());
    assert!(serde_json::from_value::<GlmResidencyFrontierRequest>(value).is_err());

    let mut overflow = request();
    overflow.target_device_count = u32::MAX;
    assert_eq!(
        evaluate_glm_residency_frontier(&overflow, &storage()),
        Err(GlmResidencyFrontierError::ArithmeticOverflow)
    );
}

fn frontier(
    result: &foundry_core::residency_frontier::GlmResidencyFrontierResult,
    bound: FrontierCacheBound,
) -> &foundry_core::residency_frontier::ResidencyBoundFrontier {
    result
        .frontiers
        .iter()
        .find(|frontier| frontier.cache_bound == bound)
        .unwrap()
}

fn storage() -> GlmStorageEnvelopeReport {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/storage-envelope-v1.json")).unwrap(),
    )
    .unwrap()
}

fn request() -> GlmResidencyFrontierRequest {
    GlmResidencyFrontierRequest {
        schema_version: GLM_RESIDENCY_FRONTIER_REQUEST_SCHEMA_VERSION,
        study_id: "glm-5.2-nvfp4-fp8-kv-four-b200-frontier-v1".into(),
        storage_report_content_id:
            "3216cdd0e8c0988ccc7c779f9df9c7d0b8099f11375e7bdb441ab7463d9bc174".into(),
        variant_id: "glm-5.2-nvidia-nvfp4-expert-selective".into(),
        device_profile_id: "fireworks-b200-180gb-16x".into(),
        target_device_count: 4,
        semantic_cache: SemanticCacheFormatOverride {
            source_format_id: "bf16".into(),
            override_format_id: "fp8".into(),
            override_bytes_per_token: 44_928,
            evidence: EnvelopeEvidence {
                kind: EnvelopeEvidenceKind::PublishedSpecification,
                source_artifact_id: "https://recipes.vllm.ai/zai-org/GLM-5.2#fp8-kv-cache"
                    .into(),
            },
            basis: "78 layers times 576 semantic-plus-rotary values times one byte; excludes scales, alignment, block metadata, and indexer cache"
                .into(),
        },
        target: TargetCapacityTopology {
            topology_id: "four-b200-aggregate-capacity-only".into(),
            device_capacity_evidence: EnvelopeEvidence {
                kind: EnvelopeEvidenceKind::PublishedSpecification,
                source_artifact_id: "nvidia-b200-180gb-memory-specification".into(),
            },
            topology_evidence: EnvelopeEvidence {
                kind: EnvelopeEvidenceKind::ModeledAssumption,
                source_artifact_id: "modeled-assumption:four-b200-capacity-only-no-tp4-support"
                    .into(),
            },
            basis: "four devices contribute aggregate usable bytes only; no tensor-parallel, expert-parallel, kernel, allocation, or serving support is asserted"
                .into(),
        },
    }
}
