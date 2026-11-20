use chrono::{TimeDelta, TimeZone, Utc};
use redis::streams::StreamRangeReply;

use super::*;
use crate::{
    postgres_reader::BalanceSeed, CapturedPricing, GenerationIdentity, GenerationStatus,
    GenerationTiming, InputTokenPrice, NormalizedUsage, OutputTokenPrice, PricedUsage,
    TerminalOutcome, TokenUnit,
};

const KEY_TTL_MS: i64 = 300_000;

/// Valkey only: the PostgreSQL URL names no credentials and is never queried, because
/// CI runs these tests against a Compose stack without migrations.
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

struct Fixture {
    state: ValkeyServingState,
    keys: SettlementKeys,
    organization_id: Uuid,
    config: GatewayConfig,
    admitted_at: DateTime<Utc>,
}

impl Fixture {
    async fn new() -> Self {
        let organization_id = Uuid::now_v7();

        Self {
            state: local_cluster().await,
            keys: SettlementKeys::with_hash_tag(
                organization_id,
                &format!("generation-test-{}", Uuid::now_v7()),
            ),
            organization_id,
            config: GatewayConfig::for_tests(),
            admitted_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap(),
        }
    }

    async fn run<T: FromRedisValue>(&self, command: &mut redis::Cmd) -> T {
        self.state.query(command).await.unwrap()
    }

    async fn expire(&self, key: &str) {
        let _: i64 = self
            .run(redis::cmd("PEXPIRE").arg(key).arg(KEY_TTL_MS))
            .await;
    }

    async fn admit(&self, generation_id: Uuid) -> Result<AdmissionLease, AdmissionError> {
        self.state
            .admit_with_keys(
                generation_id,
                self.organization_id,
                self.admitted_at - TimeDelta::seconds(1),
                self.admitted_at,
                &self.config,
                &self.keys,
            )
            .await
    }

    async fn finalize(
        &self,
        generation_id: Uuid,
        properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        self.state
            .finalize_with_keys(generation_id, self.organization_id, properties, &self.keys)
            .await
    }

    async fn seed_account(&self, billing_mode: &str, balance: i64) {
        let _: () = self
            .run(
                redis::cmd("HSET")
                    .arg(&self.keys.account)
                    .arg("organization_id")
                    .arg(self.organization_id.to_string())
                    .arg("organization_kind")
                    .arg("customer")
                    .arg("organization_status")
                    .arg("active")
                    .arg("billing_mode")
                    .arg(billing_mode)
                    .arg("balance")
                    .arg(balance),
            )
            .await;
        self.expire(&self.keys.account).await;
    }

    async fn ensure_account(&self, record: &AccountRecord) -> Result<(), ServingStateError> {
        let result = self
            .state
            .ensure_account(&self.keys, self.organization_id, record)
            .await;
        self.expire(&self.keys.account).await;
        self.expire(&self.keys.applied_balance_transactions).await;

        result
    }

    async fn mark_refreshed(&self) -> Result<(), ServingStateError> {
        self.state.mark_account_refreshed(&self.keys).await
    }

    async fn apply(&self, transactions: &[BalanceTransaction]) -> Result<(), ServingStateError> {
        let result = self
            .state
            .apply_ledger_batch(&self.keys, transactions)
            .await;
        self.expire(&self.keys.applied_balance_transactions).await;

        result
    }

    async fn watermark(&self) -> Option<LedgerPosition> {
        let (seeded_at, seeded_id): (Option<String>, Option<String>) = self
            .run(
                redis::cmd("HMGET")
                    .arg(&self.keys.account)
                    .arg("balance_seeded_at")
                    .arg("balance_seeded_id"),
            )
            .await;

        ledger_position(seeded_at.as_deref(), seeded_id.as_deref())
    }

    async fn applied_count(&self) -> i64 {
        self.run(redis::cmd("SCARD").arg(&self.keys.applied_balance_transactions))
            .await
    }

    async fn account_fields(&self) -> HashMap<String, String> {
        self.run(redis::cmd("HGETALL").arg(&self.keys.account))
            .await
    }

    async fn set_account_field(&self, name: &str, value: impl redis::ToRedisArgs) {
        let _: () = self
            .run(
                redis::cmd("HSET")
                    .arg(&self.keys.account)
                    .arg(name)
                    .arg(value),
            )
            .await;
        self.expire(&self.keys.account).await;
    }

    async fn hold_lease(&self, generation_id: Uuid, expires_at_ms: i64) {
        let _: i64 = self
            .run(
                redis::cmd("ZADD")
                    .arg(&self.keys.inflight)
                    .arg(expires_at_ms)
                    .arg(generation_id.to_string()),
            )
            .await;
        self.expire(&self.keys.inflight).await;
    }

    async fn append_settlement_event(&self) {
        let _: String = self
            .run(
                redis::cmd("XADD")
                    .arg(&self.keys.settlement_stream)
                    .arg("*")
                    .arg("generation_id")
                    .arg(Uuid::now_v7().to_string()),
            )
            .await;
        self.expire(&self.keys.settlement_stream).await;
    }

    async fn clear_settlement_stream(&self) {
        let _: i64 = self
            .run(redis::cmd("DEL").arg(&self.keys.settlement_stream))
            .await;
    }

    async fn replace_settlement_stream_with_a_string(&self) {
        let _: () = self
            .run(
                redis::cmd("SET")
                    .arg(&self.keys.settlement_stream)
                    .arg("wrong-type")
                    .arg("PX")
                    .arg(KEY_TTL_MS),
            )
            .await;
    }

    async fn cache_record(&self, key: &str, value: &str) {
        let _: () = self
            .run(
                redis::cmd("SET")
                    .arg(key)
                    .arg(value)
                    .arg("PX")
                    .arg(KEY_TTL_MS),
            )
            .await;
    }

    async fn cached_record(&self, key: &str) -> Option<String> {
        self.run(redis::cmd("GET").arg(key)).await
    }

    async fn delete_record(&self, key: &str) {
        let _: i64 = self.run(redis::cmd("DEL").arg(key)).await;
    }

    async fn lease_count(&self) -> i64 {
        self.run(redis::cmd("ZCARD").arg(&self.keys.inflight)).await
    }

    async fn leases(&self) -> Vec<String> {
        self.run(redis::cmd("ZRANGE").arg(&self.keys.inflight).arg(0).arg(-1))
            .await
    }

    async fn lease_score(&self, generation_id: Uuid) -> Option<i64> {
        self.run(
            redis::cmd("ZSCORE")
                .arg(&self.keys.inflight)
                .arg(generation_id.to_string()),
        )
        .await
    }

    async fn balance(&self) -> i64 {
        self.run(redis::cmd("HGET").arg(&self.keys.account).arg("balance"))
            .await
    }

    async fn settlement_events(&self) -> StreamRangeReply {
        self.run(
            redis::cmd("XRANGE")
                .arg(&self.keys.settlement_stream)
                .arg("-")
                .arg("+"),
        )
        .await
    }

    async fn cleanup(&self) {
        let _: i64 = self
            .run(
                redis::cmd("DEL")
                    .arg(&self.keys.account)
                    .arg(&self.keys.inflight)
                    .arg(&self.keys.applied_balance_transactions)
                    .arg(&self.keys.settlement_stream),
            )
            .await;
    }

    fn generation_properties(&self, charge: u64) -> GenerationProperties {
        let completed_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 1).unwrap();
        let identity = GenerationIdentity::new(
            None,
            self.organization_id,
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
}

mod records {
    use super::*;

    fn status_json(id: Uuid, extra: &str) -> String {
        format!(
            r#"{{"schema_version":1,"deployment_id":"{id}","runtime_revision":"r",
                "received_at":"2026-08-27T12:00:00Z","healthy":true,
                "accepting_requests":true,"reason_code":null{extra}}}"#
        )
    }

    fn model_json(id: &str, description: &str) -> String {
        serde_json::json!({
            "id": id,
            "name": "Model A",
            "status": "available",
            "properties": {
                "schema_version": 1,
                "description": description,
                "released_at": null,
                "hugging_face_id": null,
                "quantization": null,
                "tokenizer": null,
                "input_modalities": [{
                    "type": "text",
                    "supported_inputs": {
                        "max_context_length": {"value": 8192, "unit": "token"},
                        "max_prompt_length": {"value": 7168, "unit": "token"}
                    },
                    "pricing": [
                        {"type": "prompt", "unit": "token", "cost": 100},
                        {"type": "cached_prompt", "unit": "token", "cost": 50}
                    ]
                }],
                "output_modalities": [{
                    "type": "text",
                    "max_length": {"value": 4096, "unit": "token"},
                    "default_length": {"value": 1024, "unit": "token"},
                    "streaming": true,
                    "supported_parameters": {},
                    "pricing": [{"type": "completion", "unit": "token", "cost": 200}]
                }],
                "passthrough_parameters": {},
                "deprecation_date": null
            },
            "deployments": []
        })
        .to_string()
    }

    fn unique_model_id() -> String {
        format!("serving-state-test-{}", Uuid::now_v7())
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

    #[test]
    fn a_lowercase_sha256_digest_decodes_to_32_bytes() {
        let digest = "0123456789abcdef".repeat(4);

        let bytes = hex_bytes(&digest).unwrap();

        assert_eq!(bytes.len(), 32);
        assert_eq!(
            &bytes[..8],
            &[0x01, 0x23, 0x45, 0x67, 0x89, 0xab, 0xcd, 0xef]
        );
    }

    #[test]
    fn hex_decoding_rejects_odd_length_non_hex_and_multibyte_text() {
        assert_eq!(hex_bytes("abc"), None);
        assert_eq!(hex_bytes("0g"), None);
        assert_eq!(hex_bytes("aéb"), None, "a split character must not panic");
        assert_eq!(hex_bytes("éé"), None);
    }

    #[test]
    fn only_record_errors_leave_out_a_single_record() {
        let malformed = ServingStateError::MalformedRecord {
            kind: "GatewayModel",
            source: serde_json::from_str::<serde_json::Value>("{").unwrap_err(),
        };
        let invalid = ServingStateError::InvalidModelProperties(
            crate::model::ModelPropertiesError::DuplicatePrice,
        );
        let redis = ServingStateError::Redis(redis::RedisError::from((
            redis::ErrorKind::Io,
            "connection refused",
        )));
        let postgres =
            ServingStateError::Postgres(PostgresError::Pool(deadpool_postgres::PoolError::Closed));

        assert!(malformed.is_unusable_record());
        assert!(invalid.is_unusable_record());
        assert!(ServingStateError::MismatchedModelId.is_unusable_record());
        assert!(!redis.is_unusable_record());
        assert!(!postgres.is_unusable_record());
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_malformed_cached_credential_fails_and_stays_cached() {
        let fixture = Fixture::new().await;
        let digest = format!("{}{}", Uuid::now_v7().simple(), Uuid::now_v7().simple());
        let key = format!("credential:{digest}");
        fixture.cache_record(&key, "not json").await;

        let result = fixture.state.credential(&digest).await;

        assert!(matches!(
            result,
            Err(ServingStateError::MalformedRecord {
                kind: "GatewayCredential",
                ..
            })
        ));
        assert_eq!(
            fixture.cached_record(&key).await.as_deref(),
            Some("not json")
        );

        fixture.delete_record(&key).await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_cached_model_under_another_id_is_rejected() {
        let fixture = Fixture::new().await;
        let model_id = unique_model_id();
        let key = model_cache_key(&model_id);
        fixture
            .cache_record(&key, &model_json("model-a", "Model A"))
            .await;

        let result = fixture.state.unscoped_model(&model_id).await;

        assert!(matches!(result, Err(ServingStateError::MismatchedModelId)));

        fixture.delete_record(&key).await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_cached_model_with_invalid_properties_is_rejected() {
        let fixture = Fixture::new().await;
        let model_id = unique_model_id();
        let key = model_cache_key(&model_id);
        fixture
            .cache_record(&key, &model_json(&model_id, &"x".repeat(2_001)))
            .await;

        let result = fixture.state.unscoped_model(&model_id).await;

        assert!(matches!(
            result,
            Err(ServingStateError::InvalidModelProperties(_))
        ));

        fixture.delete_record(&key).await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_valid_cached_model_is_served_without_postgres() {
        let fixture = Fixture::new().await;
        let model_id = unique_model_id();
        let key = model_cache_key(&model_id);
        fixture
            .cache_record(&key, &model_json(&model_id, "Model A"))
            .await;

        let model = fixture
            .state
            .unscoped_model(&model_id)
            .await
            .unwrap()
            .unwrap();

        assert_eq!(model.id, model_id);
        assert_eq!(model.organization_id, None);

        fixture.delete_record(&key).await;
    }

    fn owned_model_json(id: &str, organization_id: Uuid) -> String {
        let mut record: serde_json::Value =
            serde_json::from_str(&model_json(id, "Model A")).unwrap();
        record["organization_id"] = serde_json::Value::String(organization_id.to_string());
        record.to_string()
    }

    #[test]
    fn a_record_without_an_owner_is_public_and_an_owned_one_keeps_its_owner() {
        let owner = Uuid::from_u128(7);
        let public: GatewayModel = parse_record("GatewayModel", &model_json("a", "A")).unwrap();
        let owned: GatewayModel =
            parse_record("GatewayModel", &owned_model_json("a", owner)).unwrap();
        let null_owner = model_json("a", "A").replacen('{', r#"{"organization_id":null,"#, 1);
        let null_owner: GatewayModel = parse_record("GatewayModel", &null_owner).unwrap();

        assert_eq!(public.organization_id, None);
        assert_eq!(null_owner.organization_id, None);
        assert_eq!(owned.organization_id, Some(owner));
        let identity = |organization_id, workspace_id| crate::auth::AuthenticatedIdentity {
            api_key_id: Uuid::from_u128(1),
            organization_id,
            workspace_id,
        };
        let member = identity(owner, Uuid::from_u128(9));
        let outsider = identity(Uuid::from_u128(8), Uuid::from_u128(10));
        assert!(ModelAccess::caller(&member).permits(&owned));
        assert!(ModelAccess::caller(&outsider).permits(&public));
        assert!(!ModelAccess::caller(&outsider).permits(&owned));
        assert!(!ModelAccess::calling(&outsider, Some(Uuid::from_u128(9))).permits(&owned));
        assert!(ModelAccess::calling(&outsider, Some(Uuid::from_u128(10))).permits(&owned));
    }

    #[test]
    fn model_records_are_cached_apart_from_records_without_owners() {
        assert_eq!(model_cache_key("acme/jeeves"), "model:v2:acme/jeeves");
        assert_ne!(model_cache_key("acme/jeeves"), "model:acme/jeeves");
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_cached_owned_model_keeps_its_owner() {
        let fixture = Fixture::new().await;
        let model_id = unique_model_id();
        let key = model_cache_key(&model_id);
        let owner = Uuid::now_v7();
        fixture
            .cache_record(&key, &owned_model_json(&model_id, owner))
            .await;

        let model = fixture
            .state
            .unscoped_model(&model_id)
            .await
            .unwrap()
            .unwrap();
        let identity = |organization_id| crate::auth::AuthenticatedIdentity {
            api_key_id: Uuid::now_v7(),
            organization_id,
            workspace_id: Uuid::now_v7(),
        };

        assert_eq!(model.organization_id, Some(owner));
        let for_owner = fixture
            .state
            .model_for(ModelAccess::caller(&identity(owner)), &model_id)
            .await
            .unwrap();
        let for_other = fixture
            .state
            .model_for(ModelAccess::caller(&identity(Uuid::now_v7())), &model_id)
            .await
            .unwrap();
        assert_eq!(for_owner.map(|model| model.id), Some(model_id.clone()));
        assert_eq!(for_other, None);

        fixture.delete_record(&key).await;
    }

    /// An entry written before `organization_id` existed could be an owned model
    /// read as public, so it must never be served; the read falls to PostgreSQL,
    /// which these tests do not run.
    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_record_under_the_key_before_owners_is_never_read() {
        let fixture = Fixture::new().await;
        let model_id = unique_model_id();
        let legacy = format!("model:{model_id}");
        fixture
            .cache_record(&legacy, &model_json(&model_id, "Model A"))
            .await;

        let result = fixture.state.unscoped_model(&model_id).await;

        assert!(!matches!(result, Ok(Some(_))));

        fixture.delete_record(&legacy).await;
    }
}

mod errors {
    use super::*;

    #[tokio::test]
    async fn an_unreachable_database_is_a_pool_error_with_the_postgres_code() {
        let reader =
            PostgresReader::connect("postgres://127.0.0.1:1/gradiated?sslmode=disable", None)
                .unwrap();

        let error = ServingStateError::from(reader.ping().await.unwrap_err());

        assert!(matches!(
            error,
            ServingStateError::Postgres(PostgresError::Pool(_))
        ));
        assert_eq!(error.diagnostic_code(), "postgres");
    }

    #[test]
    fn iam_and_transport_failures_keep_their_own_codes() {
        let iam = ServingStateError::from(ValkeyIamError::MissingAwsCredentialsProvider);
        let redis = ServingStateError::from(redis::RedisError::from((
            redis::ErrorKind::Io,
            "connection refused",
        )));

        assert_eq!(iam.diagnostic_code(), "iam");
        assert_eq!(redis.diagnostic_code(), "redis");
    }
}

mod account {
    use super::*;

    fn account_record(balance: i64) -> AccountRecord {
        AccountRecord {
            organization_kind: "customer".to_owned(),
            organization_status: "active".to_owned(),
            billing_mode: "prepaid".to_owned(),
            seed: BalanceSeed {
                balance,
                ledger_head: LedgerPosition {
                    created_at: Utc.with_ymd_and_hms(2026, 8, 19, 11, 0, 0).unwrap(),
                    id: Uuid::from_u128(7),
                },
                replay_window_entries: Vec::new(),
            },
        }
    }

    #[test]
    fn a_watermark_needs_a_valid_timestamp_and_id() {
        let id = Uuid::now_v7().to_string();

        assert_eq!(ledger_position(None, Some(&id)), None);
        assert_eq!(ledger_position(Some("soon"), Some(&id)), None);
        assert_eq!(
            ledger_position(Some(&i64::MAX.to_string()), Some(&id)),
            None
        );
        assert_eq!(ledger_position(Some("1"), None), None);
        assert_eq!(ledger_position(Some("1"), Some("not-a-uuid")), None);
    }

    #[test]
    fn a_valid_watermark_round_trips() {
        let position = transaction(1, 1_755_604_800_123, Uuid::now_v7()).position();

        let parsed = ledger_position(
            Some(&position.created_at.timestamp_millis().to_string()),
            Some(&position.id.to_string()),
        );

        assert_eq!(parsed, Some(position));
    }

    #[test]
    fn a_replay_starts_a_window_behind_the_watermark_but_never_below_its_floor() {
        let id = Uuid::now_v7().to_string();
        let at = 1_790_000_060_000_i64;
        let window_start = LedgerPosition {
            created_at: DateTime::from_timestamp_millis(at - 30_000).unwrap(),
            id: Uuid::nil(),
        };
        let cursor = |floor_at: Option<i64>| {
            let floor_at = floor_at.map(|floor_at| floor_at.to_string());
            replay_cursor(Some(&at.to_string()), Some(&id), floor_at.as_deref())
        };

        assert_eq!(cursor(None), Some(window_start));
        assert_eq!(cursor(Some(at - 60_000)), Some(window_start));
        assert_eq!(
            cursor(Some(at - 10_000)),
            Some(LedgerPosition {
                created_at: DateTime::from_timestamp_millis(at - 10_000).unwrap(),
                id: Uuid::max(),
            })
        );
        assert_eq!(
            replay_cursor(Some(&at.to_string()), Some(&id), Some("soon")),
            None
        );
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_new_account_is_seeded_with_its_watermark_and_stale_until_marked_refreshed() {
        let fixture = Fixture::new().await;
        let record = account_record(1_000);

        fixture.ensure_account(&record).await.unwrap();

        let fields = fixture.account_fields().await;
        assert_eq!(fields["balance"], "1000");
        assert_eq!(fixture.watermark().await, Some(record.seed.ledger_head));
        assert!(!fields.contains_key("balance_replay_floor_at"));
        assert!(!fixture.state.account_metadata_is_current(&fields));

        fixture.mark_refreshed().await.unwrap();

        let fields = fixture.account_fields().await;
        let refreshed_at: i64 = fields["metadata_refreshed_at"].parse().unwrap();
        assert!((Utc::now().timestamp_millis() - refreshed_at).abs() < 5_000);
        assert!(fixture.state.account_metadata_is_current(&fields));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn an_existing_account_keeps_its_balance_and_updates_its_metadata() {
        let fixture = Fixture::new().await;
        fixture
            .ensure_account(&account_record(1_000))
            .await
            .unwrap();
        fixture.set_account_field("metadata_refreshed_at", 0).await;
        let mut refreshed = account_record(5);
        refreshed.organization_status = "suspended".to_owned();

        fixture.ensure_account(&refreshed).await.unwrap();

        let fields = fixture.account_fields().await;
        assert_eq!(fields["balance"], "1000");
        assert_eq!(fields["organization_status"], "suspended");
        assert!(!fixture.state.account_metadata_is_current(&fields));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_rejected_ledger_batch_leaves_the_metadata_stale() {
        let fixture = Fixture::new().await;
        fixture
            .ensure_account(&account_record(1_000))
            .await
            .unwrap();

        let unsafe_amount = transaction(9_007_199_254_740_992, seeded_at() + 1, Uuid::now_v7());
        assert!(fixture.apply(&[unsafe_amount]).await.is_err());

        let fields = fixture.account_fields().await;
        assert!(!fixture.state.account_metadata_is_current(&fields));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn marking_a_missing_account_refreshed_creates_nothing() {
        let fixture = Fixture::new().await;

        let error = fixture.mark_refreshed().await.unwrap_err();

        assert_eq!(error.diagnostic_code(), "account_script_rejected");
        assert!(fixture.account_fields().await.is_empty());
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_watermark_without_an_id_is_repaired_without_moving_its_timestamp() {
        let fixture = Fixture::new().await;
        fixture.seed_account("prepaid", 7).await;
        fixture.set_account_field("balance_seeded_at", 123).await;

        fixture
            .ensure_account(&account_record(1_000))
            .await
            .unwrap();

        let fields = fixture.account_fields().await;
        assert_eq!(fields["balance"], "7");
        assert_eq!(fields["balance_seeded_at"], "123");
        assert_eq!(fields["balance_seeded_id"], Uuid::max().to_string());
        assert_eq!(fields["balance_replay_floor_at"], "123");

        fixture.cleanup().await;
    }

    fn transaction(amount: i64, created_at_ms: i64, id: Uuid) -> BalanceTransaction {
        BalanceTransaction {
            id,
            amount,
            created_at: DateTime::from_timestamp_millis(created_at_ms).unwrap(),
        }
    }

    fn seeded_at() -> i64 {
        account_record(0)
            .seed
            .ledger_head
            .created_at
            .timestamp_millis()
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_replay_applies_a_late_commit_but_not_an_entry_the_seed_included() {
        let fixture = Fixture::new().await;
        let included = transaction(500, seeded_at() - 10_000, Uuid::now_v7());
        let mut record = account_record(1_500);
        record.seed.replay_window_entries = vec![included.id];
        fixture.ensure_account(&record).await.unwrap();
        let committed_after_the_seed = transaction(-200, seeded_at() - 5_000, Uuid::now_v7());

        fixture
            .apply(&[included, committed_after_the_seed])
            .await
            .unwrap();

        assert_eq!(fixture.balance().await, 1_300);
        assert_eq!(fixture.applied_count().await, 2);
        assert_eq!(fixture.watermark().await, Some(record.seed.ledger_head));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_ledger_batch_applied_twice_changes_the_balance_once() {
        let fixture = Fixture::new().await;
        fixture
            .ensure_account(&account_record(1_000))
            .await
            .unwrap();
        let batch = [
            transaction(500, seeded_at() + 1, Uuid::now_v7()),
            transaction(-200, seeded_at() + 2, Uuid::now_v7()),
        ];

        fixture.apply(&batch).await.unwrap();
        fixture.apply(&batch).await.unwrap();

        assert_eq!(fixture.balance().await, 1_300);
        assert_eq!(fixture.applied_count().await, 2);
        assert_eq!(fixture.watermark().await, Some(batch[1].position()));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn an_entry_below_the_watermark_is_applied_without_rewinding_it() {
        let fixture = Fixture::new().await;
        fixture.ensure_account(&account_record(0)).await.unwrap();
        let newer = transaction(10, seeded_at() + 20, Uuid::now_v7());
        let older = transaction(5, seeded_at() + 10, Uuid::now_v7());

        fixture.apply(std::slice::from_ref(&newer)).await.unwrap();
        fixture.apply(&[older]).await.unwrap();

        assert_eq!(fixture.balance().await, 15);
        assert_eq!(fixture.watermark().await, Some(newer.position()));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn at_an_equal_timestamp_the_watermark_advances_only_for_a_higher_id() {
        let fixture = Fixture::new().await;
        fixture.ensure_account(&account_record(0)).await.unwrap();
        let at = seeded_at() + 1;
        let middle = transaction(1, at, Uuid::from_u128(2));

        fixture.apply(std::slice::from_ref(&middle)).await.unwrap();
        fixture
            .apply(&[transaction(1, at, Uuid::from_u128(1))])
            .await
            .unwrap();
        assert_eq!(fixture.watermark().await, Some(middle.position()));

        let highest = transaction(1, at, Uuid::from_u128(3));
        fixture.apply(std::slice::from_ref(&highest)).await.unwrap();
        assert_eq!(fixture.watermark().await, Some(highest.position()));
        assert_eq!(fixture.balance().await, 3);

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_batch_with_an_unsafe_amount_writes_nothing() {
        let fixture = Fixture::new().await;
        fixture
            .ensure_account(&account_record(1_000))
            .await
            .unwrap();
        let before = fixture.watermark().await;
        let batch = [
            transaction(1, seeded_at() + 1, Uuid::now_v7()),
            transaction(2, seeded_at() + 2, Uuid::now_v7()),
            transaction(9_007_199_254_740_992, seeded_at() + 3, Uuid::now_v7()),
        ];

        let error = fixture.apply(&batch).await.unwrap_err();

        assert_eq!(error.diagnostic_code(), "account_script_rejected");
        assert_eq!(fixture.balance().await, 1_000);
        assert_eq!(fixture.applied_count().await, 0);
        assert_eq!(fixture.watermark().await, before);

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_batch_that_would_overflow_the_balance_writes_nothing() {
        let fixture = Fixture::new().await;
        fixture
            .ensure_account(&account_record(9_007_199_254_740_990))
            .await
            .unwrap();
        let before = fixture.watermark().await;
        let batch = [
            transaction(1, seeded_at() + 1, Uuid::now_v7()),
            transaction(1, seeded_at() + 2, Uuid::now_v7()),
        ];

        assert!(fixture.apply(&batch).await.is_err());

        assert_eq!(fixture.balance().await, 9_007_199_254_740_990);
        assert_eq!(fixture.applied_count().await, 0);
        assert_eq!(fixture.watermark().await, before);

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn ensure_rejects_malformed_arguments_before_writing() {
        let fixture = Fixture::new().await;
        let ensure = |organization_id: &str, extra: &[&str]| {
            let mut invocation = fixture
                .state
                .ensure_account_script
                .key(&fixture.keys.account);
            invocation.key(&fixture.keys.applied_balance_transactions);
            invocation
                .arg(organization_id)
                .arg("customer")
                .arg("active")
                .arg("prepaid")
                .arg(1_000)
                .arg(0)
                .arg(Uuid::max().to_string())
                .arg(extra);
            let mut connection = fixture.state.connection.clone();

            async move { invocation.invoke_async::<i64>(&mut connection).await }
        };

        let organization_id = fixture.organization_id.to_string();
        let replayed_id = Uuid::now_v7().to_string();
        for result in [
            ensure(&organization_id, &[&replayed_id, "not-a-uuid"]).await,
            ensure("not-a-uuid", &[&replayed_id]).await,
        ] {
            let error = ServingStateError::from(result.unwrap_err());
            assert_eq!(
                error.diagnostic_code(),
                "account_script_rejected",
                "{error}"
            );
        }

        assert!(fixture.account_fields().await.is_empty());
    }
}

mod admission {
    use super::*;

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
        let mut fixture = Fixture::new().await;
        fixture.config.organization_concurrency_cap = 1;
        fixture.seed_account("prepaid", 1).await;
        let first_generation_id = Uuid::now_v7();
        let second_generation_id = Uuid::now_v7();

        fixture.admit(first_generation_id).await.unwrap();
        assert!(matches!(
            fixture.admit(second_generation_id).await,
            Err(AdmissionError::ConcurrencyExceeded)
        ));

        fixture.set_account_field("balance", 0).await;
        assert!(matches!(
            fixture.admit(second_generation_id).await,
            Err(AdmissionError::InsufficientBalance)
        ));

        fixture.seed_account("invoiced", -1).await;
        fixture.config.organization_concurrency_cap = 50;
        fixture.admit(second_generation_id).await.unwrap();
        assert!(matches!(
            fixture.admit(first_generation_id).await,
            Err(AdmissionError::DuplicateGeneration)
        ));
        assert_eq!(fixture.lease_count().await, 2);

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn admission_stops_at_the_backlog_limit_and_cleans_only_old_leases() {
        let mut fixture = Fixture::new().await;
        fixture.config.settlement_backlog_limit = 1;
        fixture.seed_account("prepaid", 5_000_000_000).await;
        fixture.append_settlement_event().await;
        let generation_id = Uuid::now_v7();

        assert!(matches!(
            fixture.admit(generation_id).await,
            Err(AdmissionError::SettlementBacklog)
        ));

        fixture.clear_settlement_stream().await;
        let old_generation = Uuid::now_v7();
        let recent_generation = Uuid::now_v7();
        let cleanup_cutoff = fixture.admitted_at - TimeDelta::seconds(300);
        fixture
            .hold_lease(
                old_generation,
                (cleanup_cutoff - TimeDelta::milliseconds(1)).timestamp_millis(),
            )
            .await;
        fixture
            .hold_lease(
                recent_generation,
                (fixture.admitted_at - TimeDelta::milliseconds(1)).timestamp_millis(),
            )
            .await;

        fixture.admit(generation_id).await.unwrap();

        let leases = fixture.leases().await;
        assert!(!leases.contains(&old_generation.to_string()));
        assert!(leases.contains(&recent_generation.to_string()));
        assert!(leases.contains(&generation_id.to_string()));

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn admission_fails_closed_before_writing_for_invalid_serving_state() {
        let fixture = Fixture::new().await;
        let generation_id = Uuid::now_v7();
        fixture.seed_account("prepaid", 1_000_000_000).await;

        fixture
            .set_account_field("organization_status", "suspended")
            .await;
        assert!(matches!(
            fixture.admit(generation_id).await,
            Err(AdmissionError::Redis(_))
        ));

        fixture
            .set_account_field("organization_status", "active")
            .await;
        fixture.replace_settlement_stream_with_a_string().await;
        assert!(matches!(
            fixture.admit(generation_id).await,
            Err(AdmissionError::Redis(_))
        ));

        assert_eq!(fixture.lease_count().await, 0);

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_rejected_admission_script_is_logged_with_its_redis_code() {
        let logs = crate::diagnostics::capture::Logs::default();
        let _guard = logs.start();
        let mut fixture = Fixture::new().await;
        fixture.keys = SettlementKeys::new(fixture.organization_id);
        fixture.seed_account("prepaid", 1_000).await;
        fixture
            .set_account_field("organization_status", "suspended")
            .await;

        let result = fixture
            .state
            .admit(
                Uuid::now_v7(),
                fixture.organization_id,
                fixture.admitted_at - TimeDelta::seconds(1),
                fixture.admitted_at,
                &fixture.config,
            )
            .await;
        fixture.delete_record(&fixture.keys.account).await;

        assert!(matches!(result, Err(AdmissionError::Redis(_))));
        let events = logs.events();
        let event = events
            .iter()
            .find(|event| event["fields"]["phase"] == "admission")
            .expect("the failed admission is logged");
        assert_eq!(event["fields"]["error_code"], "valkey_error");
        assert_eq!(event["fields"]["redis_code"], "ADMIT_GENERATION_V1");
        assert_eq!(
            event["fields"]["organization_id"],
            fixture.organization_id.to_string()
        );
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn concurrent_admission_never_exceeds_the_prepaid_floor() {
        let fixture = std::sync::Arc::new(Fixture::new().await);
        fixture.seed_account("prepaid", 2_000_000_000).await;

        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..30 {
            let fixture = fixture.clone();
            tasks.spawn(async move { fixture.admit(Uuid::now_v7()).await });
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
        assert_eq!(admitted, 20);
        assert_eq!(rejected, 10);
        assert_eq!(fixture.lease_count().await, 20);

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn prepaid_concurrency_has_a_floor_but_respects_balance_and_the_cap() {
        for (balance, cap, expected) in [
            (1, 50, 20),
            (4_000_000_000, 50, 20),
            (20_000_000_000, 50, 20),
            (20_000_000_001, 50, 21),
            (60_000_000_000, 50, 50),
            (60_000_000_000, 500, 60),
            (600_000_000_000, 500, 500),
            (1, 10, 10),
        ] {
            let mut fixture = Fixture::new().await;
            fixture.config.organization_concurrency_cap = cap;
            fixture.seed_account("prepaid", balance).await;

            for _ in 0..expected {
                fixture.admit(Uuid::now_v7()).await.unwrap();
            }
            assert!(matches!(
                fixture.admit(Uuid::now_v7()).await,
                Err(AdmissionError::ConcurrencyExceeded)
            ));
            assert_eq!(fixture.lease_count().await, expected);

            for empty_balance in [0, -1] {
                fixture.set_account_field("balance", empty_balance).await;
                assert!(matches!(
                    fixture.admit(Uuid::now_v7()).await,
                    Err(AdmissionError::InsufficientBalance)
                ));
            }

            fixture.cleanup().await;
        }
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn invoiced_concurrency_uses_the_default_cap_without_balance_scaling() {
        let fixture = Fixture::new().await;
        fixture.seed_account("invoiced", -1).await;

        for _ in 0..500 {
            fixture.admit(Uuid::now_v7()).await.unwrap();
        }
        assert!(matches!(
            fixture.admit(Uuid::now_v7()).await,
            Err(AdmissionError::ConcurrencyExceeded)
        ));
        assert_eq!(fixture.lease_count().await, 500);

        fixture.cleanup().await;
    }
}

mod finalization {
    use super::*;

    fn live_lease_expiry() -> i64 {
        Utc::now().timestamp_millis() + 60_000
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn finalization_consumes_the_lease_debits_once_and_appends_one_event() {
        let fixture = Fixture::new().await;
        let generation_id = Uuid::now_v7();
        let properties = fixture.generation_properties(250);
        fixture.seed_account("prepaid", 9_007_199_254_740_991).await;
        fixture.hold_lease(generation_id, live_lease_expiry()).await;

        assert_eq!(
            fixture.finalize(generation_id, &properties).await.unwrap(),
            FinalizationOutcome::Settled
        );
        assert_eq!(
            fixture.finalize(generation_id, &properties).await.unwrap(),
            FinalizationOutcome::AlreadyAbsent
        );

        assert_eq!(fixture.balance().await, 9_007_199_254_740_741);
        assert_eq!(fixture.lease_score(generation_id).await, None);

        let stream = fixture.settlement_events().await;
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

        fixture.cleanup().await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn finalization_validates_all_state_before_consuming_the_lease() {
        let fixture = Fixture::new().await;
        let generation_id = Uuid::now_v7();
        let properties = fixture.generation_properties(250);
        fixture.seed_account("prepaid", 1_000).await;
        fixture.hold_lease(generation_id, live_lease_expiry()).await;
        fixture.replace_settlement_stream_with_a_string().await;

        assert!(matches!(
            fixture.finalize(generation_id, &properties).await,
            Err(FinalizationError::Redis(_))
        ));

        assert_eq!(fixture.balance().await, 1_000);
        assert!(fixture.lease_score(generation_id).await.is_some());

        fixture.cleanup().await;
    }
}

mod routes {
    use std::collections::HashMap;

    use super::*;
    use crate::{
        routing::RoutePlacement,
        session_routing::{Placed, PlacementOutcome, PlacementRequest, RouteLease},
    };

    struct Routes {
        state: ValkeyServingState,
        placement: RoutePlacement,
        deployments: [Uuid; 3],
        now: DateTime<Utc>,
    }

    impl Routes {
        async fn new(limits: [Option<u32>; 3]) -> Self {
            let deployments = [Uuid::now_v7(), Uuid::now_v7(), Uuid::now_v7()];

            Self {
                state: local_cluster().await,
                placement: RoutePlacement {
                    release_digest: format!("route-test-{}", Uuid::now_v7()),
                    route_key: *Uuid::now_v7().as_bytes().repeat(2).first_chunk().unwrap(),
                    limits: deployments
                        .into_iter()
                        .zip(limits)
                        .collect::<HashMap<_, _>>(),
                },
                deployments,
                now: Utc::now(),
            }
        }

        fn for_session(&self, session: u8) -> Self {
            let mut placement = self.placement.clone();
            placement.route_key[0] = session;

            Self {
                state: self.state.clone(),
                placement,
                deployments: self.deployments,
                now: self.now,
            }
        }

        async fn place(&self, candidates: &[Uuid]) -> (Placed, Uuid) {
            let generation_id = Uuid::now_v7();
            let placed = self
                .state
                .place_route(&PlacementRequest {
                    placement: &self.placement,
                    candidates,
                    generation_id,
                    now: self.now,
                    lease_expires_at: self.now + TimeDelta::minutes(10),
                })
                .await
                .unwrap();

            (placed, generation_id)
        }

        fn lease(&self, deployment_id: Uuid, generation_id: Uuid) -> RouteLease {
            RouteLease {
                release_digest: self.placement.release_digest.clone(),
                route_key: self.placement.route_key,
                deployment_id,
                generation_id,
                expires_at: self.now + TimeDelta::minutes(10),
            }
        }

        async fn leases(&self, deployment_id: Uuid) -> i64 {
            self.state
                .query(redis::cmd("ZCARD").arg(self.lease(deployment_id, Uuid::nil()).lease_key()))
                .await
                .unwrap()
        }
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_session_keeps_its_replica_while_it_has_a_free_slot() {
        let routes = Routes::new([Some(2), Some(2), Some(2)]).await;
        let [first, second, third] = routes.deployments;

        let (placed, _) = routes.place(&[first, second, third]).await;
        assert_eq!(placed.outcome, PlacementOutcome::Placed);
        assert_eq!(placed.deployment_id, first);

        // The candidate order changes, as it does when another replica joins.
        let (kept, _) = routes.place(&[third, second, first]).await;
        assert_eq!(kept.deployment_id, first);
        assert_eq!(kept.outcome, PlacementOutcome::Kept);
        assert_eq!(routes.leases(first).await, 2);

        let (spilled, _) = routes.place(&[first, second, third]).await;
        assert_eq!(spilled.outcome, PlacementOutcome::Spilled);
        assert_eq!(spilled.deployment_id, second);

        let (stays, _) = routes.place(&[first, second, third]).await;
        assert_eq!(stays.deployment_id, second);
        assert_eq!(stays.outcome, PlacementOutcome::Kept);
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn new_sessions_go_where_the_smallest_share_of_slots_is_in_use() {
        let routes = Routes::new([Some(12), Some(12), Some(6)]).await;
        let [large, other, small] = routes.deployments;

        // Idle replicas tie, so the first candidate in rendezvous order wins.
        for session in 1..=3 {
            routes
                .for_session(session)
                .place(&[large, other, small])
                .await;
        }
        assert_eq!(routes.leases(large).await, 1);
        assert_eq!(routes.leases(other).await, 1);
        assert_eq!(routes.leases(small).await, 1);

        // One lease fills 1/6 of the small replica but only 1/12 of a large one.
        let (placed, _) = routes.for_session(4).place(&[small, large, other]).await;
        assert_eq!(placed.deployment_id, large);
        assert_eq!(placed.outcome, PlacementOutcome::Placed);
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn a_session_whose_replica_is_gone_moves_and_unknown_limits_compare_leases() {
        let routes = Routes::new([None, None, None]).await;
        let [first, second, third] = routes.deployments;

        routes.place(&[first, second, third]).await;
        routes.for_session(9).place(&[second, third]).await;

        let (moved, _) = routes.place(&[second, third]).await;
        assert_eq!(moved.outcome, PlacementOutcome::Moved);
        assert_eq!(moved.deployment_id, third);
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn releases_expiry_and_claims_keep_counts_true() {
        let routes = Routes::new([Some(2), Some(2), Some(2)]).await;
        let [first, second, _] = routes.deployments;

        let (placed, generation_id) = routes.place(&[first, second]).await;
        assert_eq!(placed.deployment_id, first);
        routes
            .state
            .release_route(&routes.lease(first, generation_id))
            .await
            .unwrap();
        assert_eq!(routes.leases(first).await, 0);

        let (_, claimed) = routes.place(&[first, second]).await;
        routes
            .state
            .claim_route(&routes.lease(second, claimed))
            .await
            .unwrap();
        routes
            .state
            .release_route(&routes.lease(first, claimed))
            .await
            .unwrap();
        let (followed, _) = routes.place(&[first, second]).await;
        assert_eq!(followed.deployment_id, second);
        assert_eq!(followed.outcome, PlacementOutcome::Kept);
        assert_eq!(
            (routes.leases(first).await, routes.leases(second).await),
            (0, 2)
        );

        // Expired leases no longer count against the replica.
        let later = Routes {
            now: routes.now + TimeDelta::minutes(11),
            ..routes.for_session(routes.placement.route_key[0])
        };
        let (kept, _) = later.place(&[first, second]).await;
        assert_eq!(kept.deployment_id, second);
        assert_eq!(later.leases(second).await, 1);
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn placement_rejects_mismatched_arguments() {
        let routes = Routes::new([Some(1), Some(1), Some(1)]).await;
        let mut script = routes.state.place_route_script.prepare_invoke();
        script
            .key("route-session:{x}:a")
            .arg(Uuid::now_v7().to_string());

        let result: redis::RedisResult<i64> = script
            .invoke_async(&mut routes.state.connection.clone())
            .await;

        assert_eq!(result.unwrap_err().code(), Some("PLACE_ROUTE_V1"));
    }
}
