use chrono::{TimeDelta, TimeZone, Utc};
use redis::streams::StreamRangeReply;

use super::*;
use crate::{
    CapturedPricing, GenerationIdentity, GenerationStatus, GenerationTiming, InputTokenPrice,
    NormalizedUsage, OutputTokenPrice, PricedUsage, TerminalOutcome, TokenUnit,
};

fn config() -> GatewayConfig {
    GatewayConfig::for_tests()
}

/// These tests exercise the Valkey scripts. The record store is built but
/// never queried, because none of them read a cached record.
async fn local_cluster() -> ValkeyServingState {
    ValkeyServingState::connect(
        "redis://127.0.0.1:6379",
        PostgresReader::connect("postgres://127.0.0.1:5432/gradiated?sslmode=disable", None)
            .expect("a connection string without a server should build a pool"),
        Duration::from_secs(15),
    )
    .await
    .expect("local Valkey cluster should connect")
}

fn test_keys(organization_id: Uuid) -> SettlementKeys {
    SettlementKeys::with_hash_tag(
        organization_id,
        &format!("generation-test-{}", Uuid::now_v7()),
    )
}

fn generation_properties(organization_id: Uuid, charge: u64) -> GenerationProperties {
    let completed_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 1).unwrap();
    let identity = GenerationIdentity::new(
        None,
        organization_id,
        Uuid::now_v7(),
        Uuid::now_v7(),
        "model-a".to_owned(),
        format!("sha256:{}", "a".repeat(64)),
    )
    .unwrap();
    let prices = CapturedPricing::new(
        &[
            InputTokenPrice::Prompt {
                unit: TokenUnit::Token,
                cost: 0,
            },
            InputTokenPrice::CachedPrompt {
                unit: TokenUnit::Token,
                cost: 0,
            },
        ],
        &[OutputTokenPrice::Completion {
            unit: TokenUnit::Token,
            cost: charge,
        }],
    )
    .unwrap();
    let priced_usage =
        PricedUsage::calculate(&prices, NormalizedUsage::new(0, 0, 0, 1, 0).unwrap()).unwrap();
    let terminal = TerminalOutcome::new(
        GenerationStatus::Succeeded,
        Some("stop".to_owned()),
        None,
        true,
        None,
    )
    .unwrap();
    let timing = GenerationTiming::new(
        completed_at - TimeDelta::seconds(1),
        Some(completed_at - TimeDelta::milliseconds(900)),
        Some(completed_at - TimeDelta::milliseconds(500)),
        completed_at,
    )
    .unwrap();
    GenerationProperties::new(
        identity,
        crate::ServiceTier::Default,
        false,
        priced_usage,
        terminal,
        timing,
    )
}

async fn admit(
    state: &ValkeyServingState,
    keys: &SettlementKeys,
    generation_id: Uuid,
    organization_id: Uuid,
    admitted_at: chrono::DateTime<Utc>,
    config: &GatewayConfig,
) -> Result<AdmissionLease, AdmissionError> {
    state
        .admit_with_keys(
            generation_id,
            organization_id,
            admitted_at - TimeDelta::seconds(1),
            admitted_at,
            config,
            keys,
        )
        .await
}

async fn seed_account(
    state: &ValkeyServingState,
    keys: &SettlementKeys,
    organization_id: Uuid,
    billing_mode: &str,
    balance: i64,
) {
    let _: () = state
        .query(
            redis::cmd("HSET")
                .arg(&keys.account)
                .arg("organization_id")
                .arg(organization_id.to_string())
                .arg("organization_kind")
                .arg("customer")
                .arg("organization_status")
                .arg("active")
                .arg("billing_mode")
                .arg(billing_mode)
                .arg("balance")
                .arg(balance),
        )
        .await
        .unwrap();
}

async fn delete_test_keys(state: &ValkeyServingState, keys: &SettlementKeys) {
    let _: i64 = state
        .query(
            redis::cmd("DEL")
                .arg(&keys.account)
                .arg(&keys.inflight)
                .arg(&keys.settlement_stream),
        )
        .await
        .unwrap();
}

fn status_json(id: Uuid, extra: &str) -> String {
    format!(
        r#"{{"schema_version":1,"deployment_id":"{id}","runtime_revision":"r",
            "received_at":"2026-08-27T12:00:00Z","healthy":true,
            "accepting_requests":true,"reason_code":null{extra}}}"#
    )
}

#[test]
fn status_parsing_keeps_good_records_and_drops_bad_ones() {
    let good = Uuid::from_u128(1);
    let mismatched = Uuid::from_u128(2);
    let mut fields = HashMap::new();
    fields.insert(good.to_string(), status_json(good, ""));
    fields.insert(mismatched.to_string(), status_json(good, ""));
    fields.insert(Uuid::from_u128(3).to_string(), "not json".to_owned());
    fields.insert(
        Uuid::from_u128(4).to_string(),
        status_json(Uuid::from_u128(4), r#","retired_field":7"#),
    );

    let statuses = parse_deployment_statuses(fields);
    assert_eq!(
        statuses.len(),
        2,
        "only the good and forward-compatible records survive"
    );
    assert!(statuses.iter().any(|status| status.deployment_id == good));
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn local_cluster_enforces_settlement_hash_tag() {
    let state = local_cluster().await;

    let tagged: i64 = state
        .query(
            redis::cmd("EVAL")
                .arg("return 1")
                .arg(2)
                .arg("account:{settlement-0}:test")
                .arg("inflight:{settlement-0}:test"),
        )
        .await
        .expect("tagged keys should share a slot");
    assert_eq!(tagged, 1);

    let error = state
        .query::<i64>(
            redis::cmd("EVAL")
                .arg("return 1")
                .arg(2)
                .arg("account:test")
                .arg("inflight:test"),
        )
        .await
        .expect_err("untagged keys should cross slots");
    assert!(
        error.to_string().to_ascii_lowercase().contains("crossslot"),
        "unexpected cluster error: {error}"
    );
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn admission_applies_prepaid_limits_and_bypasses_them_for_invoiced_accounts() {
    let state = local_cluster().await;
    let organization_id = Uuid::now_v7();
    let keys = test_keys(organization_id);
    let config = config();
    let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
    seed_account(&state, &keys, organization_id, "prepaid", 1).await;

    let first_generation_id = Uuid::now_v7();
    admit(
        &state,
        &keys,
        first_generation_id,
        organization_id,
        admitted_at,
        &config,
    )
    .await
    .unwrap();
    let second_generation_id = Uuid::now_v7();
    assert!(matches!(
        admit(
            &state,
            &keys,
            second_generation_id,
            organization_id,
            admitted_at,
            &config,
        )
        .await,
        Err(AdmissionError::ConcurrencyExceeded)
    ));

    let _: () = state
        .query(redis::cmd("HSET").arg(&keys.account).arg("balance").arg(0))
        .await
        .unwrap();
    assert!(matches!(
        admit(
            &state,
            &keys,
            second_generation_id,
            organization_id,
            admitted_at,
            &config,
        )
        .await,
        Err(AdmissionError::InsufficientBalance)
    ));

    seed_account(&state, &keys, organization_id, "invoiced", -1).await;
    admit(
        &state,
        &keys,
        second_generation_id,
        organization_id,
        admitted_at,
        &config,
    )
    .await
    .unwrap();
    assert!(matches!(
        admit(
            &state,
            &keys,
            first_generation_id,
            organization_id,
            admitted_at,
            &config,
        )
        .await,
        Err(AdmissionError::DuplicateGeneration)
    ));
    let count: i64 = state
        .query(redis::cmd("ZCARD").arg(&keys.inflight))
        .await
        .unwrap();
    assert_eq!(count, 2);

    delete_test_keys(&state, &keys).await;
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn admission_stops_at_the_backlog_limit_and_cleans_only_old_leases() {
    let state = local_cluster().await;
    let organization_id = Uuid::now_v7();
    let keys = test_keys(organization_id);
    let mut config = config();
    config.settlement_backlog_limit = 1;
    let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
    seed_account(&state, &keys, organization_id, "prepaid", 5_000_000_000).await;
    let _: String = state
        .query(
            redis::cmd("XADD")
                .arg(&keys.settlement_stream)
                .arg("*")
                .arg("generation_id")
                .arg(Uuid::now_v7().to_string()),
        )
        .await
        .unwrap();

    let generation_id = Uuid::now_v7();
    assert!(matches!(
        admit(
            &state,
            &keys,
            generation_id,
            organization_id,
            admitted_at,
            &config,
        )
        .await,
        Err(AdmissionError::SettlementBacklog)
    ));
    let _: i64 = state
        .query(redis::cmd("DEL").arg(&keys.settlement_stream))
        .await
        .unwrap();

    let old_generation = Uuid::now_v7();
    let recent_generation = Uuid::now_v7();
    let cleanup_cutoff = admitted_at - TimeDelta::seconds(300);
    let _: i64 = state
        .query(
            redis::cmd("ZADD")
                .arg(&keys.inflight)
                .arg((cleanup_cutoff - TimeDelta::milliseconds(1)).timestamp_millis())
                .arg(old_generation.to_string())
                .arg((admitted_at - TimeDelta::milliseconds(1)).timestamp_millis())
                .arg(recent_generation.to_string()),
        )
        .await
        .unwrap();

    admit(
        &state,
        &keys,
        generation_id,
        organization_id,
        admitted_at,
        &config,
    )
    .await
    .unwrap();
    let generations: Vec<String> = state
        .query(redis::cmd("ZRANGE").arg(&keys.inflight).arg(0).arg(-1))
        .await
        .unwrap();
    assert!(!generations.contains(&old_generation.to_string()));
    assert!(generations.contains(&recent_generation.to_string()));
    assert!(generations.contains(&generation_id.to_string()));

    delete_test_keys(&state, &keys).await;
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn admission_fails_closed_before_writing_for_invalid_serving_state() {
    let state = local_cluster().await;
    let organization_id = Uuid::now_v7();
    let keys = test_keys(organization_id);
    let config = config();
    let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
    let generation_id = Uuid::now_v7();
    seed_account(&state, &keys, organization_id, "prepaid", 1_000_000_000).await;

    let _: () = state
        .query(
            redis::cmd("HSET")
                .arg(&keys.account)
                .arg("organization_status")
                .arg("suspended"),
        )
        .await
        .unwrap();
    assert!(matches!(
        admit(
            &state,
            &keys,
            generation_id,
            organization_id,
            admitted_at,
            &config,
        )
        .await,
        Err(AdmissionError::Redis(_))
    ));

    let _: () = state
        .query(
            redis::cmd("HSET")
                .arg(&keys.account)
                .arg("organization_status")
                .arg("active"),
        )
        .await
        .unwrap();
    let _: () = state
        .query(
            redis::cmd("SET")
                .arg(&keys.settlement_stream)
                .arg("wrong-type"),
        )
        .await
        .unwrap();
    assert!(matches!(
        admit(
            &state,
            &keys,
            generation_id,
            organization_id,
            admitted_at,
            &config,
        )
        .await,
        Err(AdmissionError::Redis(_))
    ));

    let lease_count: i64 = state
        .query(redis::cmd("ZCARD").arg(&keys.inflight))
        .await
        .unwrap();
    assert_eq!(lease_count, 0);
    delete_test_keys(&state, &keys).await;
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn concurrent_admission_never_exceeds_the_funded_limit() {
    let state = local_cluster().await;
    let organization_id = Uuid::now_v7();
    let keys = test_keys(organization_id);
    let config = config();
    let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
    seed_account(&state, &keys, organization_id, "prepaid", 2_000_000_000).await;

    let mut tasks = tokio::task::JoinSet::new();
    for _ in 0..10 {
        let state = state.clone();
        let keys = keys.clone();
        let config = config.clone();
        tasks.spawn(async move {
            admit(
                &state,
                &keys,
                Uuid::now_v7(),
                organization_id,
                admitted_at,
                &config,
            )
            .await
        });
    }

    let mut admitted = 0;
    let mut rejected = 0;
    while let Some(result) = tasks.join_next().await {
        match result.unwrap() {
            Ok(_) => admitted += 1,
            Err(AdmissionError::ConcurrencyExceeded) => rejected += 1,
            Err(error) => panic!("unexpected admission result: {error}"),
        }
    }
    assert_eq!(admitted, 2);
    assert_eq!(rejected, 8);
    let count: i64 = state
        .query(redis::cmd("ZCARD").arg(&keys.inflight))
        .await
        .unwrap();
    assert_eq!(count, 2);

    delete_test_keys(&state, &keys).await;
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn finalization_consumes_the_lease_debits_once_and_appends_one_event() {
    let state = local_cluster().await;
    let organization_id = Uuid::now_v7();
    let generation_id = Uuid::now_v7();
    let keys = test_keys(organization_id);
    let properties = generation_properties(organization_id, 250);
    seed_account(
        &state,
        &keys,
        organization_id,
        "prepaid",
        9_007_199_254_740_991,
    )
    .await;
    let _: i64 = state
        .query(
            redis::cmd("ZADD")
                .arg(&keys.inflight)
                .arg(Utc::now().timestamp_millis() + 60_000)
                .arg(generation_id.to_string()),
        )
        .await
        .unwrap();

    assert_eq!(
        state
            .finalize_with_keys(generation_id, organization_id, &properties, &keys)
            .await
            .unwrap(),
        FinalizationOutcome::Settled
    );
    assert_eq!(
        state
            .finalize_with_keys(generation_id, organization_id, &properties, &keys)
            .await
            .unwrap(),
        FinalizationOutcome::AlreadyAbsent
    );

    let balance: i64 = state
        .query(redis::cmd("HGET").arg(&keys.account).arg("balance"))
        .await
        .unwrap();
    assert_eq!(balance, 9_007_199_254_740_741);
    let lease_score: Option<i64> = state
        .query(
            redis::cmd("ZSCORE")
                .arg(&keys.inflight)
                .arg(generation_id.to_string()),
        )
        .await
        .unwrap();
    assert_eq!(lease_score, None);

    let stream: StreamRangeReply = state
        .query(
            redis::cmd("XRANGE")
                .arg(&keys.settlement_stream)
                .arg("-")
                .arg("+"),
        )
        .await
        .unwrap();
    assert_eq!(stream.ids.len(), 1);
    assert_eq!(stream.ids[0].len(), 2);
    assert_eq!(
        stream.ids[0].get::<String>("generation_id"),
        Some(generation_id.to_string())
    );
    assert_eq!(
        stream.ids[0].get::<String>("properties"),
        Some(serde_json::to_string(&properties).unwrap())
    );

    delete_test_keys(&state, &keys).await;
}

#[tokio::test]
#[ignore = "requires the local one-node Valkey cluster"]
async fn finalization_validates_all_state_before_consuming_the_lease() {
    let state = local_cluster().await;
    let organization_id = Uuid::now_v7();
    let generation_id = Uuid::now_v7();
    let keys = test_keys(organization_id);
    let properties = generation_properties(organization_id, 250);
    seed_account(&state, &keys, organization_id, "prepaid", 1_000).await;
    let _: i64 = state
        .query(
            redis::cmd("ZADD")
                .arg(&keys.inflight)
                .arg(Utc::now().timestamp_millis() + 60_000)
                .arg(generation_id.to_string()),
        )
        .await
        .unwrap();
    let _: () = state
        .query(
            redis::cmd("SET")
                .arg(&keys.settlement_stream)
                .arg("wrong-type"),
        )
        .await
        .unwrap();

    assert!(matches!(
        state
            .finalize_with_keys(generation_id, organization_id, &properties, &keys)
            .await,
        Err(FinalizationError::Redis(_))
    ));
    let balance: i64 = state
        .query(redis::cmd("HGET").arg(&keys.account).arg("balance"))
        .await
        .unwrap();
    assert_eq!(balance, 1_000);
    let lease_score: Option<i64> = state
        .query(
            redis::cmd("ZSCORE")
                .arg(&keys.inflight)
                .arg(generation_id.to_string()),
        )
        .await
        .unwrap();
    assert!(lease_score.is_some());

    delete_test_keys(&state, &keys).await;
}
