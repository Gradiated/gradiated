use foundry_core::tiered_cache::{
    CacheAccess, CacheEvidence, CacheEvidenceKind, CacheFootprint, CacheLinkSpec, CacheTierSpec,
    GLM_TIERED_CACHE_REQUEST_SCHEMA_VERSION, GlmTieredCacheReport, GlmTieredCacheRequest,
    TieredCacheClaimBlocker, TieredCacheScenario, evaluate_glm_tiered_cache,
};
use std::fs;
use std::path::Path;

#[test]
fn exclusive_lru_promotes_lower_tier_hits_and_demotes_hot_evictions() {
    let report = evaluate_glm_tiered_cache(&request(vec![scenario(200, 300)])).unwrap();
    let result = &report.result.scenarios[0];

    assert_eq!(result.totals.requests, 6);
    assert_eq!(result.totals.hit_requests, 3);
    assert_eq!(result.totals.miss_requests, 3);
    assert_eq!(result.totals.hot_tier_hit_requests, 1);
    assert_eq!(result.totals.lower_tier_hit_requests, 2);
    assert_eq!(result.totals.hit_tokens, 30);
    assert_eq!(result.totals.miss_recompute_tokens, 30);
    assert_eq!(result.totals.promotion_bytes, 200);
    assert_eq!(result.totals.demotion_bytes, 300);
    assert_eq!(result.totals.link_transfer_bytes, 500);
    assert_eq!(result.links[0].promotion_bytes, 200);
    assert_eq!(result.links[0].demotion_bytes, 300);
    assert_eq!(result.tiers[0].evictions, 3);
    assert_eq!(result.tiers[0].final_used_bytes, 200);
    assert_eq!(result.tiers[1].final_used_bytes, 100);
    assert_eq!(result.accesses[2].hit_tier.as_deref(), Some("hbm"));
    assert_eq!(result.accesses[4].hit_tier.as_deref(), Some("host"));
    assert_eq!(result.accesses[4].promoted_to_tier.as_deref(), Some("hbm"));
}

#[test]
fn a_larger_hot_tier_avoids_all_link_traffic_for_the_same_trace() {
    let report = evaluate_glm_tiered_cache(&request(vec![scenario(300, 300)])).unwrap();
    let result = &report.result.scenarios[0];

    assert_eq!(result.totals.hit_requests, 3);
    assert_eq!(result.totals.hot_tier_hit_requests, 3);
    assert_eq!(result.totals.lower_tier_hit_requests, 0);
    assert_eq!(result.totals.link_transfer_bytes, 0);
    assert_eq!(result.tiers[0].evictions, 0);
    assert_eq!(result.tiers[1].final_used_bytes, 0);
}

#[test]
fn entries_that_fit_no_tier_are_dropped_and_recomputed_on_reuse() {
    let mut request = request(vec![scenario(50, 50)]);
    request.accesses = vec![access(1, "a"), access(2, "b"), access(3, "a")];
    let result = &evaluate_glm_tiered_cache(&request)
        .unwrap()
        .result
        .scenarios[0];

    assert_eq!(result.totals.hit_requests, 0);
    assert_eq!(result.totals.miss_requests, 3);
    assert_eq!(result.totals.dropped_entries, 3);
    assert_eq!(result.totals.miss_recompute_tokens, 30);
    assert!(result.tiers.iter().all(|tier| tier.final_used_bytes == 0));
}

#[test]
fn modeled_cache_movement_never_unlocks_end_to_end_claims() {
    let report = evaluate_glm_tiered_cache(&request(vec![scenario(200, 300)])).unwrap();
    let claims = &report.result.claims;

    assert!(!claims.end_to_end_latency_claim_permitted);
    assert!(!claims.cost_per_token_claim_permitted);
    assert!(
        claims
            .blockers
            .contains(&TieredCacheClaimBlocker::TraceIsNotMeasured)
    );
    assert!(
        claims
            .blockers
            .contains(&TieredCacheClaimBlocker::TierAndLinkTimingIsNotMeasured)
    );
    assert!(
        claims
            .blockers
            .contains(&TieredCacheClaimBlocker::RecomputeWorkIsNotCalibrated)
    );
    assert!(
        claims
            .blockers
            .contains(&TieredCacheClaimBlocker::ConcurrentContentionIsNotModeled)
    );
    assert!(
        claims
            .blockers
            .contains(&TieredCacheClaimBlocker::ServingIntegrationIsNotMeasured)
    );
}

#[test]
fn invalid_tiers_links_trace_and_key_sizes_are_rejected() {
    let mut duplicate_tier = request(vec![scenario(200, 300)]);
    duplicate_tier.scenarios[0].tiers[1].tier_id = "hbm".into();
    assert!(evaluate_glm_tiered_cache(&duplicate_tier).is_err());

    let mut wrong_link = request(vec![scenario(200, 300)]);
    wrong_link.scenarios[0].links[0].lower_tier_id = "missing".into();
    assert!(evaluate_glm_tiered_cache(&wrong_link).is_err());

    let mut noncanonical = request(vec![scenario(200, 300)]);
    noncanonical.accesses.swap(0, 1);
    assert!(evaluate_glm_tiered_cache(&noncanonical).is_err());

    let mut inconsistent_key = request(vec![scenario(200, 300)]);
    inconsistent_key.accesses[2].prefix_tokens = 11;
    assert!(evaluate_glm_tiered_cache(&inconsistent_key).is_err());
}

#[test]
fn report_identity_is_stable_and_detects_tampering() {
    let request = request(vec![scenario(200, 300)]);
    let first = evaluate_glm_tiered_cache(&request).unwrap();
    let second = evaluate_glm_tiered_cache(&request).unwrap();

    assert_eq!(first.content_id, second.content_id);
    assert!(first.verify_content_id().unwrap());
    let mut tampered = first;
    tampered.result.scenarios[0].totals.hit_tokens += 1;
    assert!(!tampered.verify_content_id().unwrap());
}

#[test]
fn checked_in_glm_tiered_cache_study_round_trips_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request: GlmTieredCacheRequest = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-tiered-prefix-cache-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: GlmTieredCacheReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/tiered-prefix-cache-v1.json")).unwrap(),
    )
    .unwrap();
    let evaluated = evaluate_glm_tiered_cache(&request).unwrap();

    assert_eq!(evaluated, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(stored.result.total_bytes_per_token, 98_048);
    assert_eq!(stored.result.scenarios[0].totals.hit_requests, 2);
    assert_eq!(stored.result.scenarios[1].totals.hit_requests, 10);
    assert!(!stored.result.claims.cost_per_token_claim_permitted);
}

fn request(scenarios: Vec<TieredCacheScenario>) -> GlmTieredCacheRequest {
    GlmTieredCacheRequest {
        schema_version: GLM_TIERED_CACHE_REQUEST_SCHEMA_VERSION,
        study_id: "tiered-cache-test".into(),
        model_id: "zai-org/GLM-5.2".into(),
        model_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
        footprint: CacheFootprint {
            mla_bytes_per_token: 8,
            indexer_bytes_per_token: 2,
            extra_bytes_per_token: 0,
            evidence: evidence(CacheEvidenceKind::PublishedSpecification, "footprint"),
        },
        trace_evidence: evidence(CacheEvidenceKind::SyntheticTrace, "trace"),
        accesses: vec![
            access(1, "a"),
            access(2, "b"),
            access(3, "a"),
            access(4, "c"),
            access(5, "b"),
            access(6, "a"),
        ],
        scenarios,
    }
}

fn scenario(hot_capacity: u64, cold_capacity: u64) -> TieredCacheScenario {
    TieredCacheScenario {
        scenario_id: format!("hbm-{hot_capacity}-host-{cold_capacity}"),
        policy: "exclusive_lru_promote_on_hit".into(),
        tiers: vec![
            tier("hbm", hot_capacity, 1_000, 1_000, 1.0),
            tier("host", cold_capacity, 500, 500, 2.0),
        ],
        links: vec![CacheLinkSpec {
            upper_tier_id: "hbm".into(),
            lower_tier_id: "host".into(),
            bandwidth_bytes_per_second: 100,
            fixed_latency_microseconds: 3.0,
            evidence: evidence(CacheEvidenceKind::ModeledAssumption, "link"),
        }],
    }
}

fn tier(
    id: &str,
    capacity_bytes: u64,
    read_bandwidth: u64,
    write_bandwidth: u64,
    fixed_latency_microseconds: f64,
) -> CacheTierSpec {
    CacheTierSpec {
        tier_id: id.into(),
        capacity_bytes,
        read_bandwidth_bytes_per_second: read_bandwidth,
        write_bandwidth_bytes_per_second: write_bandwidth,
        fixed_access_latency_microseconds: fixed_latency_microseconds,
        evidence: evidence(CacheEvidenceKind::ModeledAssumption, id),
    }
}

fn access(request_id: u64, key: &str) -> CacheAccess {
    CacheAccess {
        request_id,
        arrival_timestamp_microseconds: request_id,
        prefix_key: key.into(),
        prefix_tokens: 10,
    }
}

fn evidence(kind: CacheEvidenceKind, source: &str) -> CacheEvidence {
    CacheEvidence {
        kind,
        source_artifact_id: source.into(),
    }
}
