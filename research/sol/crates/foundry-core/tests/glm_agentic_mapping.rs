use std::fs;
use std::path::{Path, PathBuf};

use foundry_core::artifact::ArtifactId;
use foundry_core::glm_agentic_mapping::{
    GlmAgenticMappingInputs, GlmAgenticMappingRequest, GlmAgenticSourceFileHashes,
    evaluate_glm_agentic_mapping_screen,
};
use foundry_core::glm_decode::GlmDecodeLoweringReport;
use foundry_core::glm_mapping_context_frontier::GlmMappingContextFrontierRequest;
use foundry_core::glm_parallel_mapping::GlmParallelMappingReport;
use foundry_core::glm_storage::GlmStorageEnvelopeReport;
use foundry_core::public_agentic_proxy::PublicAgenticProxyReport;
use serde::de::DeserializeOwned;

#[test]
fn weights_every_exact_proxy_context_at_the_fixed_concurrencies() {
    let inputs = inputs();
    let first = evaluated(&inputs);
    let second = evaluated(&inputs);

    assert_eq!(first, second);
    assert!(first.verify_content_id().unwrap());
    assert!(first.result.source_file_hashes_verified);
    assert_eq!(
        first.result.unique_context_tokens,
        vec![
            5_000, 10_000, 16_000, 22_000, 27_000, 32_000, 45_000, 48_250, 131_000
        ]
    );
    assert_eq!(first.result.concurrency_points, vec![1, 8, 16, 32, 64]);
    assert_eq!(first.result.exact_contexts.len(), 9);
    assert!(
        first
            .result
            .exact_contexts
            .iter()
            .all(|context| context.points.len() == 5)
    );
    assert_eq!(first.result.request_weighted.len(), 5);
    for aggregate in &first.result.request_weighted {
        assert_eq!(aggregate.request_count, 64);
        assert_eq!(aggregate.partial_policy.total(), 64);
        assert_eq!(aggregate.baseline_full_capacity.total(), 64);
        assert_eq!(aggregate.candidate_full_capacity.total(), 64);
    }
    let partial_counts = first
        .result
        .request_weighted
        .iter()
        .map(|aggregate| {
            (
                aggregate.partial_policy.coupled_robust_lower,
                aggregate.partial_policy.overlap_or_metric_disagreement,
                aggregate.partial_policy.decoupled_robust_lower,
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(
        partial_counts,
        vec![(64, 0, 0), (63, 0, 1), (48, 0, 16), (24, 0, 40), (8, 8, 48)]
    );
    assert_eq!(
        first
            .result
            .request_weighted
            .iter()
            .map(|aggregate| aggregate.baseline_full_capacity.uncertain)
            .collect::<Vec<_>>(),
        vec![0, 0, 1, 15, 24]
    );
    assert!(
        first
            .result
            .request_weighted
            .iter()
            .all(|aggregate| aggregate.candidate_full_capacity.uncertain == 64)
    );
    assert!(
        first
            .result
            .retargeting_notice
            .contains("token geometry only")
    );
    assert!(!first.result.claims.quality_claim_permitted);
    assert!(!first.result.claims.latency_claim_permitted);
    assert!(!first.result.claims.throughput_claim_permitted);
    assert!(!first.result.claims.slo_claim_permitted);
    assert!(!first.result.claims.energy_claim_permitted);
    assert!(!first.result.claims.cost_claim_permitted);
    assert!(!first.result.claims.provider_claim_permitted);
    assert!(!first.result.claims.nvidia_performance_claim_permitted);
    assert!(!first.result.claims.full_deployment_claim_permitted);
}

#[test]
fn rejects_hash_mismatch_target_drift_and_unpinned_concurrency() {
    let inputs = inputs();
    let mut hashes = inputs.hashes.clone();
    hashes.proxy = "0".repeat(64);
    assert!(evaluate(&inputs, &inputs.request, &hashes).is_err());

    let mut target_drift = inputs.request.clone();
    target_drift.retargeting.target_model_id = "different/model".into();
    assert!(evaluate(&inputs, &target_drift, &inputs.hashes).is_err());

    let mut concurrency_drift = inputs.request.clone();
    concurrency_drift.concurrency_points = vec![1, 2, 8, 16, 32, 64];
    assert!(evaluate(&inputs, &concurrency_drift, &inputs.hashes).is_err());
}

#[test]
fn checked_artifact_replays_exactly() {
    let inputs = inputs();
    let stored: foundry_core::glm_agentic_mapping::GlmAgenticMappingReport =
        read(&workspace_root().join("experiments/glm-5.2/agentic-mapping-screen-v1.json"));

    assert_eq!(stored, evaluated(&inputs));
    assert!(stored.verify_content_id().unwrap());
}

struct Inputs {
    request: GlmAgenticMappingRequest,
    proxy: PublicAgenticProxyReport,
    frontier_request: GlmMappingContextFrontierRequest,
    storage: GlmStorageEnvelopeReport,
    mapping_16k: GlmParallelMappingReport,
    mapping_90k: GlmParallelMappingReport,
    lowering_16k: GlmDecodeLoweringReport,
    lowering_90k: GlmDecodeLoweringReport,
    hashes: GlmAgenticSourceFileHashes,
}

fn evaluated(inputs: &Inputs) -> foundry_core::glm_agentic_mapping::GlmAgenticMappingReport {
    evaluate(inputs, &inputs.request, &inputs.hashes).unwrap()
}

fn evaluate(
    inputs: &Inputs,
    request: &GlmAgenticMappingRequest,
    hashes: &GlmAgenticSourceFileHashes,
) -> Result<
    foundry_core::glm_agentic_mapping::GlmAgenticMappingReport,
    foundry_core::glm_agentic_mapping::GlmAgenticMappingError,
> {
    evaluate_glm_agentic_mapping_screen(
        request,
        &GlmAgenticMappingInputs {
            source_file_hashes: hashes,
            proxy: &inputs.proxy,
            frontier_request: &inputs.frontier_request,
            storage: &inputs.storage,
            mapping_16k: &inputs.mapping_16k,
            mapping_90k: &inputs.mapping_90k,
            lowering_16k: &inputs.lowering_16k,
            lowering_90k: &inputs.lowering_90k,
        },
    )
}

fn inputs() -> Inputs {
    let root = workspace_root();
    let request_path = root.join("configs/glm-5.2-agentic-mapping-screen-v1.json");
    let request: GlmAgenticMappingRequest = read(&request_path);
    let base = request_path.parent().unwrap();
    let proxy_path = base.join(&request.sources.proxy.path);
    let frontier_request_path = base.join(&request.sources.frontier_request.path);
    let storage_path = base.join(&request.sources.storage.path);
    let mapping_16k_path = base.join(&request.sources.mapping_16k.path);
    let mapping_90k_path = base.join(&request.sources.mapping_90k.path);
    let lowering_16k_path = base.join(&request.sources.lowering_16k.path);
    let lowering_90k_path = base.join(&request.sources.lowering_90k.path);
    Inputs {
        proxy: read(&proxy_path),
        frontier_request: read(&frontier_request_path),
        storage: read(&storage_path),
        mapping_16k: read(&mapping_16k_path),
        mapping_90k: read(&mapping_90k_path),
        lowering_16k: read(&lowering_16k_path),
        lowering_90k: read(&lowering_90k_path),
        hashes: GlmAgenticSourceFileHashes {
            proxy: file_hash(&proxy_path),
            frontier_request: file_hash(&frontier_request_path),
            storage: file_hash(&storage_path),
            mapping_16k: file_hash(&mapping_16k_path),
            mapping_90k: file_hash(&mapping_90k_path),
            lowering_16k: file_hash(&lowering_16k_path),
            lowering_90k: file_hash(&lowering_90k_path),
        },
        request,
    }
}

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap()
        .to_path_buf()
}

fn read<T: DeserializeOwned>(path: &Path) -> T {
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

fn file_hash(path: &Path) -> String {
    ArtifactId::from_bytes(&fs::read(path).unwrap())
        .as_str()
        .to_owned()
}
