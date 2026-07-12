use std::fs;
use std::path::Path;

use foundry_core::glm_decode::GlmDecodeLoweringReport;
use foundry_core::glm_mapping_context_frontier::{
    FrontierCapacityRelation, FrontierScope, GlmMappingContextFrontierError,
    GlmMappingContextFrontierReport, GlmMappingContextFrontierRequest, PartialPolicy,
    evaluate_glm_mapping_context_frontier,
};
use foundry_core::glm_parallel_mapping::{Dominance, GlmParallelMappingReport};
use foundry_core::glm_storage::GlmStorageEnvelopeReport;
use serde::de::DeserializeOwned;

const CONTEXTS: [u64; 8] = [
    16_384, 32_768, 65_536, 90_000, 131_072, 262_144, 524_288, 1_048_576,
];

#[test]
fn sweeps_the_exact_context_by_concurrency_grid_as_residency_only() {
    let report = evaluated();

    assert_eq!(report.result.scope, FrontierScope::ResidencyOnly);
    assert!(
        report
            .result
            .partial_policy_contract
            .contains("never selects a deployable plan")
    );
    assert_eq!(report.result.frontiers.len(), CONTEXTS.len());
    assert_eq!(
        report
            .result
            .frontiers
            .iter()
            .map(|frontier| frontier.context_tokens_per_request)
            .collect::<Vec<_>>(),
        CONTEXTS
    );
    assert!(report.result.frontiers.iter().all(|frontier| {
        frontier.points.len() == 96
            && frontier.points.first().unwrap().concurrent_requests == 1
            && frontier.points.last().unwrap().concurrent_requests == 96
    }));
    assert_eq!(
        frontier(&report, 16_384).semantic_cache_bytes_per_request,
        736_100_352
    );
    assert_eq!(
        frontier(&report, 90_000).semantic_cache_bytes_per_request,
        4_043_520_000
    );
    assert_eq!(
        frontier(&report, 1_048_576).semantic_cache_bytes_per_request,
        47_110_422_528
    );
    assert_eq!(
        report.result.excluded_context_dependent_lowerer_work[0]
            .attention_flops
            .upper,
        Some(1_000_000_000_000)
    );
    assert_eq!(
        report.result.excluded_context_dependent_lowerer_work[1]
            .attention_flops
            .upper,
        Some(5_493_164_062_500)
    );
}

#[test]
fn policy_regions_are_strict_only_when_both_partial_metrics_agree() {
    let report = evaluated();
    let short = frontier(&report, 16_384);
    let long = frontier(&report, 90_000);

    assert_eq!(short.partial_policy_regions.len(), 3);
    assert_region(
        &short.partial_policy_regions[0],
        1,
        32,
        PartialPolicy::CoupledRobustLower,
    );
    assert_region(
        &short.partial_policy_regions[1],
        33,
        42,
        PartialPolicy::BoundsOverlapOrMetricDisagreement,
    );
    assert_region(
        &short.partial_policy_regions[2],
        43,
        96,
        PartialPolicy::DecoupledRobustLower,
    );
    assert_region(
        &long.partial_policy_regions[0],
        1,
        5,
        PartialPolicy::CoupledRobustLower,
    );
    assert_region(
        &long.partial_policy_regions[1],
        6,
        8,
        PartialPolicy::BoundsOverlapOrMetricDisagreement,
    );
    assert_region(
        &long.partial_policy_regions[2],
        9,
        96,
        PartialPolicy::DecoupledRobustLower,
    );
}

#[test]
fn anchor_witnesses_reproduce_exact_partial_deltas_and_full_capacity() {
    let report = evaluated();
    let short = witness(&report, 16_384);
    let long = witness(&report, 90_000);

    assert!(short.all_stored_points_reproduced_exactly);
    assert_eq!(short.reproduced_stored_point_count, 9);
    assert_eq!(
        short
            .witness_partial_comparison
            .candidate_minus_baseline_cluster_total_bytes
            .lower,
        185_723_781_120
    );
    assert_eq!(
        short
            .witness_partial_comparison
            .candidate_minus_baseline_cluster_total_bytes
            .upper,
        288_130_721_792
    );
    assert!(long.all_stored_points_reproduced_exactly);
    assert_eq!(long.reproduced_stored_point_count, 12);
    assert_eq!(
        long.witness_partial_comparison
            .cluster_total_partial_dominance,
        Dominance::CandidateLower
    );
    assert_eq!(
        long.witness_partial_comparison
            .candidate_minus_baseline_max_device_bytes
            .lower,
        -38_003_558_400
    );
    assert_eq!(
        long.baseline_witness.full.total_bytes_on_max_device.lower,
        108_957_894_701
    );
    assert_eq!(
        long.candidate_witness.full.total_bytes_on_max_device.upper,
        179_900_645_453
    );
}

#[test]
fn full_capacity_uncertainty_is_explicit_and_never_selects_a_plan() {
    let report = evaluated();
    let point = point(&report, 90_000, 16);

    assert_eq!(
        point.full_capacity_relation,
        FrontierCapacityRelation::NeitherPlanProvenFeasible
    );
    assert_eq!(
        point.baseline_full_capacity.capacity_status,
        foundry_core::glm_parallel_mapping::CapacityStatus::Uncertain
    );
    assert_eq!(
        point.candidate_full_capacity.capacity_status,
        foundry_core::glm_parallel_mapping::CapacityStatus::Uncertain
    );
    let long = frontier(&report, 90_000);
    assert_eq!(long.baseline_capacity_status_regions.len(), 3);
    assert_eq!(
        long.baseline_capacity_status_regions[0].start_concurrency,
        1
    );
    assert_eq!(long.baseline_capacity_status_regions[0].end_concurrency, 14);
    assert_eq!(
        long.baseline_capacity_status_regions[1].start_concurrency,
        15
    );
    assert_eq!(long.baseline_capacity_status_regions[1].end_concurrency, 27);
    assert_eq!(
        long.baseline_capacity_status_regions[2].start_concurrency,
        28
    );
    assert_eq!(long.baseline_capacity_status_regions[2].end_concurrency, 96);
    assert_eq!(long.candidate_capacity_status_regions.len(), 1);
    assert_eq!(
        long.candidate_capacity_status_regions[0].start_concurrency,
        1
    );
    assert_eq!(
        long.candidate_capacity_status_regions[0].end_concurrency,
        96
    );
    assert_eq!(
        long.candidate_capacity_status_regions[0].status,
        foundry_core::glm_parallel_mapping::CapacityStatus::Uncertain
    );
    let million = frontier(&report, 1_048_576);
    assert_eq!(
        million.points[0].full_capacity_relation,
        FrontierCapacityRelation::BaselineOnlyProvenFeasible
    );
    assert!(
        million.points[1..]
            .iter()
            .all(|point| point.full_capacity_relation
                == FrontierCapacityRelation::NeitherPlanProvenFeasible)
    );
}

#[test]
fn network_work_is_stated_once_and_never_interpolated() {
    let report = evaluated();
    let network = &report.result.context_invariant_network_control;

    assert!(network.exactly_equal_across_anchors);
    assert_eq!(network.anchor_context_tokens, vec![16_384, 90_000]);
    assert_eq!(
        network
            .comparison
            .candidate_minus_baseline_network_hop_payload_bytes
            .lower,
        -1_549_664_256
    );
    assert!(!report.result.claims.end_to_end_latency_claim_permitted);
    assert!(!report.result.claims.throughput_claim_permitted);
    assert!(!report.result.claims.cost_per_token_claim_permitted);
    assert!(!report.result.claims.quality_claim_permitted);
}

#[test]
fn source_identity_and_shared_geometry_controls_fail_closed() {
    let inputs = inputs();
    let mut request = inputs.request.clone();
    request.sources.controls[0].mapping_report_content_id = "wrong".into();
    assert_eq!(
        evaluate(&request, &inputs),
        Err(
            GlmMappingContextFrontierError::MappingReportContentIdMismatch {
                context_tokens_per_request: 16_384,
            }
        )
    );

    let mut lowering = inputs.lowering_90k.clone();
    lowering.result.checkpoint.checkpoint.checkpoint_revision = "wrong".into();
    assert_eq!(
        evaluate_glm_mapping_context_frontier(
            &inputs.request,
            &inputs.storage,
            &inputs.mapping_16k,
            &inputs.mapping_90k,
            &inputs.lowering_16k,
            &lowering,
        ),
        Err(
            GlmMappingContextFrontierError::InvalidLoweringReportContentId {
                context_tokens_per_request: 90_000,
            }
        )
    );

    let mut storage_request = inputs.request.clone();
    storage_request.sources.storage_report_content_id = "wrong".into();
    assert_eq!(
        evaluate(&storage_request, &inputs),
        Err(GlmMappingContextFrontierError::StorageReportContentIdMismatch)
    );

    let mut ledger_request = inputs.request.clone();
    ledger_request.sources.controls[1].lower_action_ledger_content_id = "wrong".into();
    assert_eq!(
        evaluate(&ledger_request, &inputs),
        Err(
            GlmMappingContextFrontierError::LowerActionLedgerContentIdMismatch {
                context_tokens_per_request: 90_000,
            }
        )
    );
}

#[test]
fn checked_artifact_round_trips_exactly() {
    let stored: GlmMappingContextFrontierReport =
        read("experiments/glm-5.2/parallel-mapping-context-frontier-v1.json");
    assert_eq!(evaluated(), stored);
    assert!(stored.verify_content_id().unwrap());
}

fn evaluated() -> GlmMappingContextFrontierReport {
    let inputs = inputs();
    evaluate(&inputs.request, &inputs).unwrap()
}

fn evaluate(
    request: &GlmMappingContextFrontierRequest,
    inputs: &Inputs,
) -> Result<GlmMappingContextFrontierReport, GlmMappingContextFrontierError> {
    evaluate_glm_mapping_context_frontier(
        request,
        &inputs.storage,
        &inputs.mapping_16k,
        &inputs.mapping_90k,
        &inputs.lowering_16k,
        &inputs.lowering_90k,
    )
}

struct Inputs {
    request: GlmMappingContextFrontierRequest,
    storage: GlmStorageEnvelopeReport,
    mapping_16k: GlmParallelMappingReport,
    mapping_90k: GlmParallelMappingReport,
    lowering_16k: GlmDecodeLoweringReport,
    lowering_90k: GlmDecodeLoweringReport,
}

fn inputs() -> Inputs {
    Inputs {
        request: read("configs/glm-5.2-parallel-mapping-context-frontier-v1.json"),
        storage: read("experiments/glm-5.2/storage-envelope-v1.json"),
        mapping_16k: read("experiments/glm-5.2/parallel-mapping-control-v1.json"),
        mapping_90k: read("experiments/glm-5.2/parallel-mapping-90k-control-v1.json"),
        lowering_16k: read("experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json"),
        lowering_90k: read("experiments/glm-5.2/nvfp4-whole-decode-lowering-90k-control-v1.json"),
    }
}

fn frontier(
    report: &GlmMappingContextFrontierReport,
    context: u64,
) -> &foundry_core::glm_mapping_context_frontier::ContextPolicyFrontier {
    report
        .result
        .frontiers
        .iter()
        .find(|frontier| frontier.context_tokens_per_request == context)
        .unwrap()
}

fn point(
    report: &GlmMappingContextFrontierReport,
    context: u64,
    concurrency: u32,
) -> &foundry_core::glm_mapping_context_frontier::ContextConcurrencyPoint {
    frontier(report, context)
        .points
        .iter()
        .find(|point| point.concurrent_requests == concurrency)
        .unwrap()
}

fn witness(
    report: &GlmMappingContextFrontierReport,
    context: u64,
) -> &foundry_core::glm_mapping_context_frontier::AnchorRegressionWitness {
    report
        .result
        .anchor_regression_witnesses
        .iter()
        .find(|witness| witness.context_tokens_per_request == context)
        .unwrap()
}

fn assert_region(
    region: &foundry_core::glm_mapping_context_frontier::PartialPolicyRegion,
    start: u32,
    end: u32,
    policy: PartialPolicy,
) {
    assert_eq!(region.start_concurrency, start);
    assert_eq!(region.end_concurrency, end);
    assert_eq!(region.policy, policy);
}

fn read<T: DeserializeOwned>(path: &str) -> T {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    serde_json::from_slice(&fs::read(root.join(path)).unwrap()).unwrap()
}
