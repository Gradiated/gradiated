use std::fs;
use std::path::Path;

use foundry_core::glm_decode::{GlmDecodeLoweringReport, GlmDecodeLoweringRequest};
use foundry_core::glm_dsa::GlmDsaSweepReport;
use foundry_core::glm_moe_route::GlmMoeRouteReport;
use foundry_core::glm_parallel_mapping::{
    CapacityStatus, Dominance, GlmParallelMappingError, GlmParallelMappingReport,
    GlmParallelMappingRequest, ParallelPlanReport, ResidencyPoint, evaluate_glm_parallel_mapping,
};
use foundry_core::glm_storage::GlmStorageEnvelopeReport;

const BASELINE_CONTEXT: u64 = 16_384;
const CONTROL_CONTEXT: u64 = 90_000;
const FP8_SEMANTIC_KV_BYTES_PER_TOKEN: u64 = 44_928;

#[test]
fn ninety_k_control_preserves_the_exact_decode_work_unit() {
    let inputs = inputs();
    let report = evaluate(&inputs.request, &inputs).unwrap();
    let work = &report.result.network_workload;

    assert_eq!(inputs.lowering_request.workload.batch_size, 8);
    assert_eq!(
        inputs.lowering_request.workload.context_tokens_per_request,
        CONTROL_CONTEXT
    );
    assert_eq!(inputs.lowering_request.workload.candidate_tokens, 16);
    assert_eq!(
        inputs.lowering_request.cache.semantic_kv_read_bytes.lower,
        2_944_401_408
    );
    assert_eq!(
        inputs.lowering_request.cache.semantic_kv_read_bytes.upper,
        Some(129_392_640_000)
    );
    assert_eq!(
        inputs.lowering_request.attention_dsa.attention_flops.upper,
        Some(5_493_164_062_500)
    );
    assert_eq!(inputs.request.network_workload.integer_repetitions, 2);
    assert_eq!(work.batch_size_per_repetition, 8);
    assert_eq!(work.context_tokens_per_request, CONTROL_CONTEXT);
    assert_eq!(work.candidate_tokens_per_repetition, 16);
    assert_eq!(work.integer_repetitions, 2);
    assert_eq!(work.aggregate_batch_size, 16);
    assert_eq!(work.aggregate_candidate_tokens, 32);
    assert_eq!(
        report.result.residency_context_tokens_per_request,
        CONTROL_CONTEXT
    );
    assert_eq!(
        report.result.sources.storage_report_content_id,
        inputs.storage.content_id
    );
    assert_eq!(
        report.result.sources.route_report_content_id,
        inputs.route.content_id
    );
    assert_eq!(
        report.result.sources.dsa_report_content_id,
        inputs.dsa.content_id
    );
    assert_eq!(
        report.result.sources.lowering_report_content_id,
        inputs.lowering.content_id
    );
    assert_eq!(
        report.result.sources.lower_action_ledger_content_id,
        inputs.lowering.result.lower_bound_ledger_content_id
    );
    assert!(report.result.mechanism_evidence.iter().any(|evidence| {
        evidence.source_artifact_id
            == "experiments/glm-5.2/parallel-mapping-control-v1.json#205c1c7157d104179e066ecfde311107ca7f160f941a8a97e7058e8e1fd80729"
    }));
}

#[test]
fn exact_fp8_cache_scaling_changes_residency_but_not_decode_network_work() {
    let report = evaluated();
    let baseline: GlmParallelMappingReport =
        read("experiments/glm-5.2/parallel-mapping-control-v1.json");
    let bytes_per_request = FP8_SEMANTIC_KV_BYTES_PER_TOKEN * CONTROL_CONTEXT;
    let baseline_bytes_per_request = FP8_SEMANTIC_KV_BYTES_PER_TOKEN * BASELINE_CONTEXT;

    assert_eq!(
        report.result.semantic_cache.bytes_per_token,
        FP8_SEMANTIC_KV_BYTES_PER_TOKEN
    );
    assert_eq!(bytes_per_request, 4_043_520_000);
    assert_eq!(baseline_bytes_per_request, 736_100_352);
    assert_eq!(
        bytes_per_request - baseline_bytes_per_request,
        3_307_419_648
    );
    assert_eq!(CONTROL_CONTEXT * 1_000_000 / BASELINE_CONTEXT, 5_493_164);
    assert_eq!(
        plan(&report, "coupled-tp16").network,
        plan(&baseline, "coupled-tp16").network
    );
    assert_eq!(
        plan(&report, "decoupled-dp-attention-ep8").network,
        plan(&baseline, "decoupled-dp-attention-ep8").network
    );
}

#[test]
fn ninety_k_partial_crossover_is_separate_from_active_batch() {
    let report = evaluated();
    let crossover = &report.result.partial_crossover;

    assert_eq!(report.result.network_workload.aggregate_batch_size, 16);
    assert_eq!(crossover.cluster_total_regions[0].start_concurrency, 1);
    assert_eq!(crossover.cluster_total_regions[0].end_concurrency, 5);
    assert_eq!(
        crossover.cluster_total_regions[0].dominance,
        Dominance::BaselineLower
    );
    assert_eq!(crossover.cluster_total_regions[1].start_concurrency, 6);
    assert_eq!(crossover.cluster_total_regions[1].end_concurrency, 7);
    assert_eq!(
        crossover.cluster_total_regions[1].dominance,
        Dominance::BoundsOverlap
    );
    assert_eq!(crossover.cluster_total_regions[2].start_concurrency, 8);
    assert_eq!(
        crossover.cluster_total_regions[2].dominance,
        Dominance::CandidateLower
    );
    assert_eq!(crossover.max_device_regions[0].end_concurrency, 6);
    assert_eq!(crossover.max_device_regions[1].start_concurrency, 7);
    assert_eq!(crossover.max_device_regions[1].end_concurrency, 8);
    assert_eq!(crossover.max_device_regions[2].start_concurrency, 9);
}

#[test]
fn full_capacity_includes_checkpoint_runtime_extra_cache_and_fragmentation() {
    let report = evaluated();
    let coupled = point(plan(&report, "coupled-tp16"), 16);
    let decoupled = point(plan(&report, "decoupled-dp-attention-ep8"), 16);

    assert_eq!(
        coupled.partial.semantic_cache_bytes_on_max_device,
        64_696_320_000
    );
    assert_eq!(coupled.full.fixed_runtime_bytes_on_device, 1_000_000_000);
    assert_eq!(
        coupled.full.total_bytes_on_max_device.lower,
        108_957_894_701
    );
    assert_eq!(
        coupled.full.total_bytes_on_max_device.upper,
        176_787_654_701
    );
    assert_eq!(coupled.full.capacity_status, CapacityStatus::Uncertain);
    assert_eq!(
        decoupled.partial.semantic_cache_bytes_on_max_device,
        4_043_520_000
    );
    assert_eq!(decoupled.full.fixed_runtime_bytes_on_device, 1_000_000_000);
    assert_eq!(
        decoupled.full.total_bytes_on_max_device.lower,
        65_253_802_541
    );
    assert_eq!(
        decoupled.full.total_bytes_on_max_device.upper,
        179_900_645_453
    );
    assert_eq!(decoupled.full.capacity_status, CapacityStatus::Uncertain);
    assert!(
        coupled.full.total_bytes_on_max_device.lower < coupled.full.usable_memory_bytes_per_device
    );
    assert!(
        coupled.full.total_bytes_on_max_device.upper > coupled.full.usable_memory_bytes_per_device
    );
    assert!(
        decoupled.full.total_bytes_on_max_device.lower
            < decoupled.full.usable_memory_bytes_per_device
    );
    assert!(
        decoupled.full.total_bytes_on_max_device.upper
            > decoupled.full.usable_memory_bytes_per_device
    );
    assert_eq!(
        point(plan(&report, "coupled-tp16"), 14)
            .full
            .capacity_status,
        CapacityStatus::Feasible
    );
    assert_eq!(
        point(plan(&report, "coupled-tp16"), 15)
            .full
            .capacity_status,
        CapacityStatus::Uncertain
    );
    assert_eq!(
        point(plan(&report, "coupled-tp16"), 27)
            .full
            .capacity_status,
        CapacityStatus::Uncertain
    );
    assert_eq!(
        point(plan(&report, "coupled-tp16"), 28)
            .full
            .capacity_status,
        CapacityStatus::Infeasible
    );
}

#[test]
fn control_fails_closed_for_performance_economics_quality_and_source_mixups() {
    let inputs = inputs();
    let report = evaluate(&inputs.request, &inputs).unwrap();
    let claims = &report.result.claims;

    assert!(!claims.end_to_end_latency_claim_permitted);
    assert!(!claims.throughput_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert!(!claims.quality_claim_permitted);

    let baseline_lowering_request: GlmDecodeLoweringRequest =
        read("configs/glm-5.2-nvfp4-whole-decode-lowering-v1.json");
    assert_eq!(
        evaluate_glm_parallel_mapping(
            &inputs.request,
            &inputs.storage,
            &inputs.route,
            &inputs.dsa,
            &baseline_lowering_request,
            &inputs.lowering,
        ),
        Err(GlmParallelMappingError::LoweringRequestDoesNotReproduceReport)
    );
}

#[test]
fn checked_ninety_k_artifacts_round_trip_exactly() {
    let inputs = inputs();
    let stored_lowering: GlmDecodeLoweringReport =
        read("experiments/glm-5.2/nvfp4-whole-decode-lowering-90k-control-v1.json");
    let stored_mapping: GlmParallelMappingReport =
        read("experiments/glm-5.2/parallel-mapping-90k-control-v1.json");

    assert_eq!(inputs.lowering, stored_lowering);
    assert!(stored_lowering.verify_content_id().unwrap());
    assert_eq!(evaluate(&inputs.request, &inputs).unwrap(), stored_mapping);
    assert!(stored_mapping.verify_content_id().unwrap());
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

fn plan<'a>(report: &'a GlmParallelMappingReport, id: &str) -> &'a ParallelPlanReport {
    report
        .result
        .plans
        .iter()
        .find(|plan| plan.plan_id == id)
        .unwrap()
}

fn point(plan: &ParallelPlanReport, concurrency: u32) -> &ResidencyPoint {
    plan.residency
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

fn inputs() -> Inputs {
    Inputs {
        request: read("configs/glm-5.2-parallel-mapping-90k-control-v1.json"),
        storage: read("experiments/glm-5.2/storage-envelope-v1.json"),
        route: read("experiments/glm-5.2/moe-route-skew-v1.json"),
        dsa: read("experiments/glm-5.2/dsa-indexshare-sweep-v1.json"),
        lowering_request: read("configs/glm-5.2-nvfp4-whole-decode-lowering-90k-control-v1.json"),
        lowering: read("experiments/glm-5.2/nvfp4-whole-decode-lowering-90k-control-v1.json"),
    }
}

fn read<T: serde::de::DeserializeOwned>(relative: &str) -> T {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    serde_json::from_slice(&fs::read(root.join(relative)).unwrap()).unwrap()
}
