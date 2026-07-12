use std::fs;
use std::path::Path;

use foundry_core::glm_decode::{GlmDecodeLoweringReport, GlmDecodeLoweringRequest};
use foundry_core::glm_dsa::GlmDsaSweepReport;
use foundry_core::glm_moe_route::GlmMoeRouteReport;
use foundry_core::glm_parallel_mapping::{
    CapacityStatus, ClaimBlocker, Dominance, GlmParallelMappingError, GlmParallelMappingReport,
    GlmParallelMappingRequest, NetworkActionKind, PartialResidencyScope,
    evaluate_glm_parallel_mapping,
};
use foundry_core::glm_storage::GlmStorageEnvelopeReport;

#[test]
fn exact_lowerer_repetitions_and_topology_network_reconcile() {
    let report = evaluated();
    let result = &report.result;

    assert_eq!(result.network_workload.batch_size_per_repetition, 8);
    assert_eq!(result.network_workload.context_tokens_per_request, 16_384);
    assert_eq!(result.network_workload.candidate_tokens_per_repetition, 16);
    assert_eq!(result.network_workload.integer_repetitions, 2);
    assert_eq!(result.network_workload.aggregate_batch_size, 16);
    assert_eq!(result.network_workload.aggregate_candidate_tokens, 32);

    let coupled = plan(result, "coupled-tp16");
    assert_eq!(
        coupled.network.total.network_hop_payload_bytes.lower,
        1_804_861_440
    );
    assert_eq!(
        coupled.network.total.network_hop_payload_bytes.upper,
        1_804_861_440
    );
    assert_eq!(
        coupled.network.total.network_hop_message_count.lower,
        146_880
    );
    assert_eq!(
        coupled.network.total.cross_domain_payload_bytes.lower,
        225_607_680
    );
    assert_eq!(
        coupled.network.total.cross_domain_message_count.lower,
        18_360
    );
    assert_eq!(
        action(coupled, NetworkActionKind::AttentionTensorParallel)
            .network_hop_payload_bytes
            .lower,
        920_125_440
    );
    assert_eq!(
        action(coupled, NetworkActionKind::MoeTensorParallel)
            .network_hop_payload_bytes
            .lower,
        884_736_000
    );

    let decoupled = plan(result, "decoupled-dp-attention-ep8");
    assert_eq!(
        decoupled.network.total.network_hop_payload_bytes.lower,
        255_197_184
    );
    assert_eq!(
        decoupled.network.total.network_hop_payload_bytes.upper,
        255_246_336
    );
    assert_eq!(decoupled.network.total.network_hop_message_count.lower, 130);
    assert_eq!(decoupled.network.total.network_hop_message_count.upper, 132);
    assert_eq!(decoupled.network.total.cross_domain_payload_bytes.lower, 0);
    assert_eq!(decoupled.network.total.cross_domain_payload_bytes.upper, 0);
    assert_eq!(
        result
            .network_comparison
            .candidate_minus_baseline_network_hop_payload_bytes
            .lower,
        -1_549_664_256
    );
    assert_eq!(
        result
            .network_comparison
            .candidate_minus_baseline_network_hop_payload_bytes
            .upper,
        -1_549_615_104
    );
    assert_eq!(
        result.network_comparison.network_hop_payload_dominance,
        Dominance::CandidateLower
    );
}

#[test]
fn partial_residency_is_named_and_shared_uncertainty_crosses_over() {
    let report = evaluated();
    let result = &report.result;
    let coupled = plan(result, "coupled-tp16");
    let decoupled = plan(result, "decoupled-dp-attention-ep8");
    let coupled_16 = point(coupled, 16);
    let decoupled_16 = point(decoupled, 16);

    assert_eq!(
        coupled_16.partial.scope,
        PartialResidencyScope::RoutedWeightsPlusSemanticCacheOnly
    );
    assert_eq!(
        coupled_16.partial.semantic_cache_bytes_on_max_device,
        11_777_605_632
    );
    assert_eq!(
        coupled_16.partial.total_bytes_on_max_device.lower,
        34_426_847_232
    );
    assert_eq!(
        coupled_16.partial.total_bytes_on_max_device.upper,
        40_827_281_024
    );
    assert_eq!(
        decoupled_16.partial.semantic_cache_bytes_on_max_device,
        736_100_352
    );
    assert_eq!(
        decoupled_16.partial.total_bytes_on_max_device.lower,
        46_034_583_552
    );
    assert_eq!(
        decoupled_16.partial.total_bytes_on_max_device.upper,
        58_835_451_136
    );

    assert_eq!(
        comparison(result, 32).cluster_total_partial_dominance,
        Dominance::BaselineLower
    );
    assert_eq!(
        comparison(result, 33).cluster_total_partial_dominance,
        Dominance::BoundsOverlap
    );
    assert_eq!(
        comparison(result, 42).cluster_total_partial_dominance,
        Dominance::BoundsOverlap
    );
    assert_eq!(
        comparison(result, 43).cluster_total_partial_dominance,
        Dominance::CandidateLower
    );
    assert_eq!(
        comparison(result, 33).max_device_partial_dominance,
        Dominance::BaselineLower
    );
    assert_eq!(
        comparison(result, 34).max_device_partial_dominance,
        Dominance::BoundsOverlap
    );
    assert_eq!(
        comparison(result, 43).max_device_partial_dominance,
        Dominance::CandidateLower
    );
    assert_eq!(
        result.partial_crossover.cluster_total_regions[0].start_concurrency,
        1
    );
    assert_eq!(
        result.partial_crossover.cluster_total_regions[0].end_concurrency,
        32
    );
    assert_eq!(
        result.partial_crossover.cluster_total_regions[1].start_concurrency,
        33
    );
    assert_eq!(
        result.partial_crossover.cluster_total_regions[1].end_concurrency,
        42
    );
    assert_eq!(
        result.partial_crossover.cluster_total_regions[2].start_concurrency,
        43
    );
}

#[test]
fn full_capacity_envelope_includes_correlated_checkpoint_and_common_bytes() {
    let report = evaluated();
    let result = &report.result;
    let coupled = point(plan(result, "coupled-tp16"), 16);
    let decoupled = point(plan(result, "decoupled-dp-attention-ep8"), 16);

    assert_eq!(
        coupled.full.checkpoint_weight_bytes_on_max_device.lower,
        29_049_675_392
    );
    assert_eq!(
        coupled.full.checkpoint_weight_bytes_on_max_device.upper,
        29_049_675_392
    );
    assert_eq!(coupled.full.fixed_runtime_bytes_on_device, 1_000_000_000);
    assert_eq!(
        coupled
            .full
            .extra_and_indexer_cache_bytes_on_max_device
            .lower,
        0
    );
    assert_eq!(
        coupled
            .full
            .extra_and_indexer_cache_bytes_on_max_device
            .upper,
        10_737_418_240
    );
    assert_eq!(coupled.full.total_bytes_on_max_device.lower, 48_101_373_178);
    assert_eq!(coupled.full.total_bytes_on_max_device.upper, 60_449_404_154);
    assert_eq!(coupled.full.capacity_status, CapacityStatus::Feasible);

    assert_eq!(
        decoupled.full.checkpoint_weight_bytes_on_max_device.lower,
        51_698_916_992
    );
    assert_eq!(
        decoupled.full.checkpoint_weight_bytes_on_max_device.upper,
        147_705_423_872
    );
    assert_eq!(
        decoupled.full.total_bytes_on_max_device.lower,
        61_450_269_946
    );
    assert_eq!(
        decoupled.full.total_bytes_on_max_device.upper,
        172_629_504_794
    );
    assert_eq!(decoupled.full.capacity_status, CapacityStatus::Uncertain);
    assert!(decoupled.full.total_bytes_on_max_device.upper > result.usable_memory_bytes_per_device);
}

#[test]
fn negative_controls_isolate_cache_route_and_domain_effects() {
    let report = evaluated();
    let result = &report.result;
    let decoupled = plan(result, "decoupled-dp-attention-ep8");
    let forced = plan(result, "control-decoupled-forced-mla-replication");
    let zero_remote = plan(result, "control-decoupled-zero-remote");
    let crossed = plan(result, "control-decoupled-cross-domain-ep8");

    assert!(
        point(forced, 16).partial.semantic_cache_bytes_on_max_device
            > point(decoupled, 16)
                .partial
                .semantic_cache_bytes_on_max_device
    );
    assert_eq!(point(zero_remote, 16).partial, point(decoupled, 16).partial);
    assert_eq!(zero_remote.network.total.network_hop_payload_bytes.lower, 0);
    assert_eq!(zero_remote.network.total.network_hop_payload_bytes.upper, 0);
    assert_eq!(
        crossed.network.total.network_hop_payload_bytes,
        decoupled.network.total.network_hop_payload_bytes
    );
    assert_eq!(crossed.network.total.cross_domain_payload_bytes.lower, 0);
    assert_eq!(
        crossed.network.total.cross_domain_payload_bytes.upper,
        crossed.network.total.network_hop_payload_bytes.upper
    );
}

#[test]
fn analytical_mapping_never_unlocks_latency_throughput_cost_or_quality() {
    let report = evaluated();
    let claims = &report.result.claims;

    assert!(claims.partial_residency_accounting_permitted);
    assert!(claims.modeled_capacity_arithmetic_permitted);
    assert!(!claims.end_to_end_latency_claim_permitted);
    assert!(!claims.throughput_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert!(!claims.quality_claim_permitted);
    assert!(
        claims
            .blockers
            .contains(&ClaimBlocker::RouteHistogramIsSynthetic)
    );
    assert!(
        claims
            .blockers
            .contains(&ClaimBlocker::CheckpointExpertLayoutIsOpaque)
    );
    assert!(
        claims
            .blockers
            .contains(&ClaimBlocker::CacheScaleAndMetadataAreExcluded)
    );
    assert!(
        claims
            .blockers
            .contains(&ClaimBlocker::CollectiveTimingIsNotCalibrated)
    );
    assert!(
        claims
            .blockers
            .contains(&ClaimBlocker::ServingAndContentionAreNotModeled)
    );
}

#[test]
fn all_source_identities_fail_closed() {
    let inputs = inputs();
    let mut wrong = inputs.request.clone();
    wrong.sources.lowering_report_content_id = "wrong".into();
    assert_eq!(
        evaluate(&wrong, &inputs),
        Err(GlmParallelMappingError::LoweringReportContentIdMismatch)
    );

    let mut tampered = inputs.storage.clone();
    tampered.result.semantic_mla_cache_bytes_per_token += 1;
    assert_eq!(
        evaluate_glm_parallel_mapping(
            &inputs.request,
            &tampered,
            &inputs.route,
            &inputs.dsa,
            &inputs.lowering_request,
            &inputs.lowering,
        ),
        Err(GlmParallelMappingError::InvalidStorageReportContentId)
    );
}

#[test]
fn checked_config_and_report_round_trip_exactly() {
    let inputs = inputs();
    let stored: GlmParallelMappingReport =
        read("experiments/glm-5.2/parallel-mapping-control-v1.json");
    let evaluated = evaluate(&inputs.request, &inputs).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
}

#[test]
fn request_schema_is_strict_and_repetition_partition_is_exact() {
    let inputs = inputs();
    let mut value = serde_json::to_value(&inputs.request).unwrap();
    value
        .as_object_mut()
        .unwrap()
        .insert("unknown".into(), true.into());
    assert!(serde_json::from_value::<GlmParallelMappingRequest>(value).is_err());

    let mut invalid = inputs.request.clone();
    invalid.network_workload.integer_repetitions = 1;
    assert_eq!(
        evaluate(&invalid, &inputs),
        Err(
            GlmParallelMappingError::WorkRepetitionsDoNotPartitionExpertGroups {
                plan_id: "decoupled-dp-attention-ep8".into(),
            }
        )
    );
}

fn plan<'a>(
    result: &'a foundry_core::glm_parallel_mapping::GlmParallelMappingResult,
    id: &str,
) -> &'a foundry_core::glm_parallel_mapping::ParallelPlanReport {
    result.plans.iter().find(|plan| plan.plan_id == id).unwrap()
}

fn point(
    plan: &foundry_core::glm_parallel_mapping::ParallelPlanReport,
    concurrency: u32,
) -> &foundry_core::glm_parallel_mapping::ResidencyPoint {
    plan.residency
        .iter()
        .find(|point| point.concurrent_requests == concurrency)
        .unwrap()
}

fn action(
    plan: &foundry_core::glm_parallel_mapping::ParallelPlanReport,
    kind: NetworkActionKind,
) -> &foundry_core::glm_parallel_mapping::NetworkActionReport {
    plan.network
        .actions
        .iter()
        .find(|action| action.kind == kind)
        .unwrap()
}

fn comparison(
    result: &foundry_core::glm_parallel_mapping::GlmParallelMappingResult,
    concurrency: u32,
) -> &foundry_core::glm_parallel_mapping::PartialResidencyComparison {
    result
        .partial_comparisons
        .iter()
        .find(|point| point.concurrent_requests == concurrency)
        .unwrap()
}

struct Inputs {
    request: GlmParallelMappingRequest,
    storage: GlmStorageEnvelopeReport,
    route: GlmMoeRouteReport,
    dsa: GlmDsaSweepReport,
    lowering_request: GlmDecodeLoweringRequest,
    lowering: GlmDecodeLoweringReport,
}

fn evaluated() -> GlmParallelMappingReport {
    let inputs = inputs();
    evaluate(&inputs.request, &inputs).unwrap()
}

fn evaluate(
    request: &GlmParallelMappingRequest,
    inputs: &Inputs,
) -> Result<GlmParallelMappingReport, GlmParallelMappingError> {
    evaluate_glm_parallel_mapping(
        request,
        &inputs.storage,
        &inputs.route,
        &inputs.dsa,
        &inputs.lowering_request,
        &inputs.lowering,
    )
}

fn inputs() -> Inputs {
    Inputs {
        request: read("configs/glm-5.2-parallel-mapping-control-v1.json"),
        storage: read("experiments/glm-5.2/storage-envelope-v1.json"),
        route: read("experiments/glm-5.2/moe-route-skew-v1.json"),
        dsa: read("experiments/glm-5.2/dsa-indexshare-sweep-v1.json"),
        lowering_request: read("configs/glm-5.2-nvfp4-whole-decode-lowering-v1.json"),
        lowering: read("experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json"),
    }
}

fn read<T: serde::de::DeserializeOwned>(relative: &str) -> T {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    serde_json::from_slice(&fs::read(root.join(relative)).unwrap()).unwrap()
}
