use std::{collections::HashMap, future::Future, time::Duration};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use redis::{
    cluster::{ClusterClient, ClusterClientBuilder},
    cluster_async::ClusterConnection,
    FromRedisValue, Script,
};
use serde::de::DeserializeOwned;
use thiserror::Error;
use uuid::Uuid;

use crate::{
    admission::{cleanup_cutoff, AdmissionError, AdmissionLease},
    cache::{LazyTtlCache, SingleFlight},
    deployment::DeploymentRuntimeStatus,
    domain::{GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace},
    postgres_reader::{
        AccountRecord, BalanceTransaction, LedgerPosition, PostgresError, PostgresReader,
    },
    session_routing::{Placed, PlacementOutcome, PlacementRequest, RouteLease, SESSION_LIFETIME},
    valkey_auth::{ValkeyIamCredentials, ValkeyIamError},
    FinalizationError, FinalizationOutcome, GatewayConfig, GenerationProperties, ModelAccess,
    ValkeyIamConfig,
};

const ADMIT_GENERATION_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/admit_generation_v1.lua")
);
const FINALIZE_GENERATION_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/finalize_generation_v1.lua")
);
const ENSURE_ACCOUNT_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/ensure_account_v1.lua")
);
const APPLY_BALANCE_TRANSACTIONS_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/apply_balance_transactions_v1.lua")
);
const MARK_ACCOUNT_REFRESHED_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/mark_account_refreshed_v1.lua")
);
const PLACE_ROUTE_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/place_route_v1.lua")
);
const ADMIT_EVAL_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/admit_eval_v1.lua")
);
const CLAIM_ROUTE_V1: &str = concat!(
    include_str!("scripts/prelude.lua"),
    include_str!("scripts/claim_route_v1.lua")
);

/// Every settlement key shares this hash tag, so one script can touch them all.
const SETTLEMENT_HASH_TAG: &str = "settlement-0";
const BALANCE_TRANSACTION_BATCH: u16 = 500;
/// Deployment statuses are pushed by the runtimes and expire on their own, so
/// this only stops one request from reading the same key repeatedly.
const STATUS_CACHE_TTL: Duration = Duration::from_secs(1);
/// Far above the number of live releases; it bounds entries left by retired ones.
const STATUS_CACHE_CAPACITY: usize = 10_000;

/// The read-through key of a `GatewayModel`. Records under the earlier
/// `model:<id>` key predate `organization_id` and would read as public, so this
/// gateway never reads them; gateways still on that key keep their own entries.
pub(crate) fn model_cache_key(model_id: &str) -> String {
    format!("model:v2:{model_id}")
}

#[async_trait]
pub trait ServingState: Send + Sync {
    async fn credential(
        &self,
        digest_hex: &str,
    ) -> Result<Option<GatewayCredential>, ServingStateError>;

    async fn workspace(
        &self,
        workspace_id: Uuid,
    ) -> Result<Option<GatewayWorkspace>, ServingStateError>;

    async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError>;

    /// The model a request names, if this caller may see it. Another
    /// organization's own model is `None`, exactly like an unknown ID.
    async fn model_for(
        &self,
        access: ModelAccess,
        model_id: &str,
    ) -> Result<Option<GatewayModel>, ServingStateError>;

    /// Every servable model this caller may see.
    async fn models_visible_to(
        &self,
        access: ModelAccess,
    ) -> Result<Vec<GatewayModel>, ServingStateError>;

    async fn private_model_exists(
        &self,
        workspace_id: Uuid,
        name: &str,
    ) -> Result<bool, ServingStateError>;

    async fn private_adapter(
        &self,
        workspace_id: Uuid,
        name: &str,
    ) -> Result<Option<crate::PrivateAdapter>, ServingStateError>;

    async fn deployment_statuses(
        &self,
        release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError>;

    async fn admit(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
    ) -> Result<AdmissionLease, AdmissionError>;

    async fn finalize(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError>;

    async fn place_route(
        &self,
        request: &PlacementRequest<'_>,
    ) -> Result<Placed, ServingStateError>;

    async fn claim_route(&self, lease: &RouteLease) -> Result<(), ServingStateError>;

    async fn release_route(&self, lease: &RouteLease) -> Result<(), ServingStateError>;

    async fn admit_eval(
        &self,
        lease: &EvalLease,
        config: &GatewayConfig,
    ) -> Result<EvalAdmission, ServingStateError>;

    async fn release_eval(&self, lease: &EvalLease) -> Result<(), ServingStateError>;
}

/// One eval-lane generation's slot in its workspace's eval limits.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EvalLease {
    pub workspace_id: Uuid,
    pub generation_id: Uuid,
    pub now: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
}

impl EvalLease {
    fn inflight_key(&self) -> String {
        format!("eval-inflight:{{eval-{}}}", self.workspace_id)
    }

    fn minute_key(&self) -> String {
        format!(
            "eval-requests:{{eval-{}}}:{}",
            self.workspace_id,
            self.now.timestamp() / 60
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EvalAdmission {
    Admitted,
    ConcurrencyCapped,
    RateCapped,
}

#[derive(Clone)]
pub struct ValkeyServingState {
    connection: ClusterConnection,
    admission_script: Script,
    finalization_script: Script,
    ensure_account_script: Script,
    apply_balance_script: Script,
    mark_refreshed_script: Script,
    place_route_script: Script,
    claim_route_script: Script,
    eval_admission_script: Script,
    database: PostgresReader,
    record_cache_ttl: Duration,
    record_loads: SingleFlight<String>,
    status_cache: LazyTtlCache<String, Vec<DeploymentRuntimeStatus>>,
}

impl ValkeyServingState {
    /// The model record whoever asks. Private to this type: the request path
    /// reads models only through [`ServingState::model_for`] and
    /// [`ServingState::models_visible_to`], which take the caller's access.
    async fn unscoped_model(
        &self,
        model_id: &str,
    ) -> Result<Option<GatewayModel>, ServingStateError> {
        let model: Option<GatewayModel> = self
            .read_through("GatewayModel", model_cache_key(model_id), || {
                self.database.model_json(model_id)
            })
            .await?;
        let Some(model) = model else {
            return Ok(None);
        };

        model
            .properties
            .validate_for_serving()
            .map_err(ServingStateError::InvalidModelProperties)?;
        if model.id != model_id && !model.aliases.iter().any(|alias| alias == model_id) {
            return Err(ServingStateError::MismatchedModelId);
        }

        Ok(Some(model))
    }

    pub async fn connect(
        url: &str,
        database: PostgresReader,
        record_cache_ttl: Duration,
    ) -> Result<Self, ServingStateError> {
        let client = ClusterClient::new(vec![url])?;

        Self::connect_client(client, database, record_cache_ttl).await
    }

    pub async fn connect_with_iam(
        url: &str,
        config: ValkeyIamConfig,
        database: PostgresReader,
        record_cache_ttl: Duration,
    ) -> Result<Self, ServingStateError> {
        let credentials = ValkeyIamCredentials::start(config).await?;
        let client = ClusterClientBuilder::new(vec![url])
            .set_credentials_provider(credentials)
            .build()?;

        Self::connect_client(client, database, record_cache_ttl).await
    }

    async fn connect_client(
        client: ClusterClient,
        database: PostgresReader,
        record_cache_ttl: Duration,
    ) -> Result<Self, ServingStateError> {
        let state = Self {
            connection: client.get_async_connection().await?,
            admission_script: Script::new(ADMIT_GENERATION_V1),
            finalization_script: Script::new(FINALIZE_GENERATION_V1),
            ensure_account_script: Script::new(ENSURE_ACCOUNT_V1),
            apply_balance_script: Script::new(APPLY_BALANCE_TRANSACTIONS_V1),
            mark_refreshed_script: Script::new(MARK_ACCOUNT_REFRESHED_V1),
            place_route_script: Script::new(PLACE_ROUTE_V1),
            claim_route_script: Script::new(CLAIM_ROUTE_V1),
            eval_admission_script: Script::new(ADMIT_EVAL_V1),
            database,
            record_cache_ttl,
            record_loads: SingleFlight::default(),
            status_cache: LazyTtlCache::new(STATUS_CACHE_TTL, STATUS_CACHE_CAPACITY),
        };
        state.ping().await?;

        Ok(state)
    }

    pub async fn ping(&self) -> Result<(), ServingStateError> {
        let response: String = self.query(&mut redis::cmd("PING")).await?;
        if response != "PONG" {
            return Err(ServingStateError::UnexpectedPingResponse);
        }

        Ok(())
    }

    pub async fn ping_database(&self) -> Result<(), ServingStateError> {
        Ok(self.database.ping().await?)
    }

    /// Reads a record from the Valkey cache, then from PostgreSQL. A record that
    /// PostgreSQL does not have is never cached, so a key or model created a moment
    /// ago is visible at once. Every lookup of an unknown key therefore reaches
    /// PostgreSQL; caching absence would not bound a flood of distinct random keys,
    /// so that bound belongs in front of this layer.
    async fn read_through<T, F, Fut>(
        &self,
        kind: &'static str,
        key: String,
        load: F,
    ) -> Result<Option<T>, ServingStateError>
    where
        T: DeserializeOwned,
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<Option<String>, PostgresError>>,
    {
        if let Some(cached) = self.cached_record(kind, &key).await? {
            return Ok(Some(cached));
        }

        self.record_loads
            .run(key.clone(), || async {
                if let Some(cached) = self.cached_record(kind, &key).await? {
                    return Ok(Some(cached));
                }

                self.load_record(kind, &key, load).await
            })
            .await
    }

    async fn cached_record<T: DeserializeOwned>(
        &self,
        kind: &'static str,
        key: &str,
    ) -> Result<Option<T>, ServingStateError> {
        let cached: Option<String> = self.query(redis::cmd("GET").arg(key)).await?;

        cached.map(|cached| parse_record(kind, &cached)).transpose()
    }

    async fn load_record<T, F, Fut>(
        &self,
        kind: &'static str,
        key: &str,
        load: F,
    ) -> Result<Option<T>, ServingStateError>
    where
        T: DeserializeOwned,
        F: FnOnce() -> Fut,
        Fut: Future<Output = Result<Option<String>, PostgresError>>,
    {
        let Some(record) = load().await? else {
            return Ok(None);
        };

        // Caching after parsing keeps a record this gateway cannot read out of the
        // cache, where it would fail every later request for the same key.
        let parsed = parse_record(kind, &record)?;
        let ttl_seconds = self.record_cache_ttl.as_secs().max(1);
        let _: () = self
            .query(
                redis::cmd("SET")
                    .arg(key)
                    .arg(&record)
                    .arg("EX")
                    .arg(ttl_seconds),
            )
            .await?;

        Ok(Some(parsed))
    }

    async fn account_hash(&self, key: &str) -> Result<HashMap<String, String>, ServingStateError> {
        Ok(self.query(redis::cmd("HGETALL").arg(key)).await?)
    }

    async fn current_account(
        &self,
        keys: &SettlementKeys,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        let fields = self.account_hash(&keys.account).await?;
        if !self.account_metadata_is_current(&fields) {
            return Ok(None);
        }

        account_from_hash(fields).map(Some)
    }

    async fn refresh_account(
        &self,
        keys: &SettlementKeys,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        let Some(record) = self.database.account(organization_id).await? else {
            return Ok(None);
        };

        self.ensure_account(keys, organization_id, &record).await?;
        self.apply_balance_transactions(keys, organization_id)
            .await?;
        self.mark_account_refreshed(keys).await?;

        account_from_hash(self.account_hash(&keys.account).await?).map(Some)
    }

    fn account_metadata_is_current(&self, fields: &HashMap<String, String>) -> bool {
        let ttl = i64::try_from(self.record_cache_ttl.as_millis()).unwrap_or(i64::MAX);

        fields
            .get("metadata_refreshed_at")
            .and_then(|value| value.parse::<i64>().ok())
            .is_some_and(|refreshed_at| Utc::now().timestamp_millis() - refreshed_at < ttl)
    }

    async fn ensure_account(
        &self,
        keys: &SettlementKeys,
        organization_id: Uuid,
        record: &AccountRecord,
    ) -> Result<(), ServingStateError> {
        let seed = &record.seed;
        let replayed_ids: Vec<String> = seed
            .replay_window_entries
            .iter()
            .map(Uuid::to_string)
            .collect();

        let _: i64 = self
            .ensure_account_script
            .key(&keys.account)
            .key(&keys.applied_balance_transactions)
            .arg(organization_id.to_string())
            .arg(&record.organization_kind)
            .arg(&record.organization_status)
            .arg(&record.billing_mode)
            .arg(seed.balance)
            .arg(seed.ledger_head.created_at.timestamp_millis())
            .arg(seed.ledger_head.id.to_string())
            .arg(replayed_ids)
            .invoke_async(&mut self.connection.clone())
            .await?;

        Ok(())
    }

    async fn mark_account_refreshed(&self, keys: &SettlementKeys) -> Result<(), ServingStateError> {
        let _: i64 = self
            .mark_refreshed_script
            .key(&keys.account)
            .arg(Utc::now().timestamp_millis())
            .invoke_async(&mut self.connection.clone())
            .await?;

        Ok(())
    }

    /// Moves ledger entries created after the watermark into the operational
    /// balance. Nothing else applies them, and the metadata is marked fresh only
    /// after this succeeds, so an entry reaches the balance within one
    /// record-cache TTL.
    async fn apply_balance_transactions(
        &self,
        keys: &SettlementKeys,
        organization_id: Uuid,
    ) -> Result<(), ServingStateError> {
        let mut cursor = self.replay_cursor(keys).await?;

        loop {
            let transactions = self
                .database
                .balance_transactions_after(organization_id, cursor, BALANCE_TRANSACTION_BATCH)
                .await?;
            self.apply_ledger_batch(keys, &transactions).await?;

            match transactions.last() {
                Some(last) if transactions.len() == usize::from(BALANCE_TRANSACTION_BATCH) => {
                    cursor = last.position();
                }
                _ => return Ok(()),
            }
        }
    }

    async fn replay_cursor(
        &self,
        keys: &SettlementKeys,
    ) -> Result<LedgerPosition, ServingStateError> {
        let (seeded_at, seeded_id, floor_at): (Option<String>, Option<String>, Option<String>) =
            self.query(
                redis::cmd("HMGET")
                    .arg(&keys.account)
                    .arg("balance_seeded_at")
                    .arg("balance_seeded_id")
                    .arg("balance_replay_floor_at"),
            )
            .await?;

        replay_cursor(
            seeded_at.as_deref(),
            seeded_id.as_deref(),
            floor_at.as_deref(),
        )
        .ok_or(ServingStateError::InvalidBalanceWatermark)
    }

    async fn apply_ledger_batch(
        &self,
        keys: &SettlementKeys,
        transactions: &[BalanceTransaction],
    ) -> Result<(), ServingStateError> {
        let Some(highest) = transactions.last().map(BalanceTransaction::position) else {
            return Ok(());
        };

        let mut script = self.apply_balance_script.prepare_invoke();
        script
            .key(&keys.account)
            .key(&keys.applied_balance_transactions)
            .arg(highest.created_at.timestamp_millis())
            .arg(highest.id.to_string());
        for transaction in transactions {
            script
                .arg(transaction.id.to_string())
                .arg(transaction.amount);
        }

        let _: i64 = script.invoke_async(&mut self.connection.clone()).await?;

        Ok(())
    }

    async fn admit_with_keys(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
        keys: &SettlementKeys,
    ) -> Result<AdmissionLease, AdmissionError> {
        let lease = AdmissionLease::new(generation_id, received_at, admitted_at, config)?;
        let cleanup_cutoff = cleanup_cutoff(admitted_at, config)?;

        let result: i64 = self
            .admission_script
            .prepare_invoke()
            .key(&keys.account)
            .key(&keys.inflight)
            .key(&keys.settlement_stream)
            .arg(generation_id.to_string())
            .arg(organization_id.to_string())
            .arg(admitted_at.timestamp_millis())
            .arg(lease.lease_expires_at().timestamp_millis())
            .arg(cleanup_cutoff.timestamp_millis())
            .arg(config.organization_concurrency_cap)
            .arg(config.balance_per_concurrency_slot_nano_usd)
            .arg(config.settlement_backlog_limit)
            .invoke_async(&mut self.connection.clone())
            .await?;

        match result {
            1 => Ok(lease),
            2 => Err(AdmissionError::InsufficientBalance),
            3 => Err(AdmissionError::SettlementBacklog),
            4 => Err(AdmissionError::ConcurrencyExceeded),
            5 => Err(AdmissionError::DuplicateGeneration),
            result => Err(AdmissionError::UnknownScriptResult(result)),
        }
    }

    async fn finalize_with_keys(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        properties: &GenerationProperties,
        keys: &SettlementKeys,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        if properties.organization_id() != organization_id {
            return Err(FinalizationError::OrganizationMismatch);
        }

        let result: i64 = self
            .finalization_script
            .prepare_invoke()
            .key(&keys.account)
            .key(&keys.inflight)
            .key(&keys.settlement_stream)
            .arg(generation_id.to_string())
            .arg(organization_id.to_string())
            .arg(properties.charge())
            .arg(serde_json::to_string(properties)?)
            .invoke_async(&mut self.connection.clone())
            .await?;

        match result {
            1 => Ok(FinalizationOutcome::Settled),
            2 => Ok(FinalizationOutcome::AlreadyAbsent),
            result => Err(FinalizationError::UnknownScriptResult(result)),
        }
    }

    async fn query<T>(&self, command: &mut redis::Cmd) -> redis::RedisResult<T>
    where
        T: FromRedisValue,
    {
        command.query_async(&mut self.connection.clone()).await
    }
}

#[async_trait]
impl ServingState for ValkeyServingState {
    async fn credential(
        &self,
        digest_hex: &str,
    ) -> Result<Option<GatewayCredential>, ServingStateError> {
        let digest = hex_bytes(digest_hex).ok_or(ServingStateError::MalformedDigest)?;

        self.read_through(
            "GatewayCredential",
            format!("credential:{digest_hex}"),
            || self.database.credential_json(&digest),
        )
        .await
    }

    async fn workspace(
        &self,
        workspace_id: Uuid,
    ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
        self.read_through(
            "GatewayWorkspace",
            format!("workspace:{workspace_id}"),
            || self.database.workspace_json(workspace_id),
        )
        .await
    }

    /// The account hash is operational state, not a cache: it holds the balance
    /// that settlement moves. It is seeded once from PostgreSQL and never expires;
    /// only its metadata is refreshed, and only when it has gone stale.
    async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        let keys = SettlementKeys::new(organization_id);
        if let Some(account) = self.current_account(&keys).await? {
            return Ok(Some(account));
        }

        self.record_loads
            .run(keys.account.clone(), || async {
                if let Some(account) = self.current_account(&keys).await? {
                    return Ok(Some(account));
                }

                self.refresh_account(&keys, organization_id).await
            })
            .await
    }

    async fn model_for(
        &self,
        access: ModelAccess,
        model_id: &str,
    ) -> Result<Option<GatewayModel>, ServingStateError> {
        Ok(self
            .unscoped_model(model_id)
            .await?
            .filter(|model| access.permits(model)))
    }

    async fn private_model_exists(
        &self,
        workspace_id: Uuid,
        name: &str,
    ) -> Result<bool, ServingStateError> {
        Ok(self
            .database
            .private_adapter_json(workspace_id, name)
            .await?
            .is_some())
    }

    async fn private_adapter(
        &self,
        workspace_id: Uuid,
        name: &str,
    ) -> Result<Option<crate::PrivateAdapter>, ServingStateError> {
        let record = self
            .database
            .private_adapter_json(workspace_id, name)
            .await?;
        let adapter = record
            .map(|record| parse_record::<Option<crate::PrivateAdapter>>("PrivateAdapter", &record))
            .transpose()?
            .flatten();
        Ok(adapter.filter(|adapter| adapter.is_valid()))
    }

    /// Every model that can be served. A model whose record is unusable is left
    /// out rather than failing the whole listing.
    async fn models_visible_to(
        &self,
        access: ModelAccess,
    ) -> Result<Vec<GatewayModel>, ServingStateError> {
        let model_ids = self.database.model_ids().await?;

        let mut models = Vec::with_capacity(model_ids.len());
        for model_id in model_ids {
            match self.unscoped_model(&model_id).await {
                Ok(Some(model)) if model.id == model_id && access.permits(&model) => {
                    models.push(model)
                }
                Ok(_) => {}
                Err(error) if error.is_unusable_record() => {
                    crate::diagnostics::limited_warn!(%model_id, phase = "catalog_read",
                        error_code = error.diagnostic_code(), "leaving out an unusable model");
                }
                Err(error) => return Err(error),
            }
        }

        Ok(models)
    }

    async fn deployment_statuses(
        &self,
        release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        self.status_cache
            .get_or_load(release_digest.to_owned(), || async {
                let key = format!("deployment-status:{{{release_digest}}}");
                let fields: HashMap<String, String> =
                    self.query(redis::cmd("HGETALL").arg(key)).await?;

                Ok(parse_deployment_statuses(fields))
            })
            .await
    }

    async fn admit(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
    ) -> Result<AdmissionLease, AdmissionError> {
        let result = self
            .admit_with_keys(
                generation_id,
                organization_id,
                received_at,
                admitted_at,
                config,
                &SettlementKeys::new(organization_id),
            )
            .await;

        if let Err(error) = &result {
            if error.is_serving_state_failure() {
                crate::diagnostics::limited_warn!(%organization_id, phase = "admission",
                    error_code = error.diagnostic_code(), redis_code = error.redis_code(),
                    "admission failed");
            }
        }

        result
    }

    async fn finalize(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        self.finalize_with_keys(
            generation_id,
            organization_id,
            properties,
            &SettlementKeys::new(organization_id),
        )
        .await
    }
    async fn place_route(
        &self,
        request: &PlacementRequest<'_>,
    ) -> Result<Placed, ServingStateError> {
        let mut script = self.place_route_script.prepare_invoke();
        script.key(request.session_key());
        for key in request.lease_keys() {
            script.key(key);
        }
        script
            .arg(request.generation_id.to_string())
            .arg(request.now.timestamp_millis())
            .arg(request.lease_expires_at.timestamp_millis())
            .arg(SESSION_LIFETIME.as_millis() as u64);
        for deployment_id in request.candidates {
            script
                .arg(deployment_id.to_string())
                .arg(request.limit(*deployment_id));
        }

        let (index, outcome): (usize, i64) =
            script.invoke_async(&mut self.connection.clone()).await?;
        let deployment_id = index
            .checked_sub(1)
            .and_then(|index| request.candidates.get(index).copied());
        match (deployment_id, PlacementOutcome::from_script(outcome)) {
            (Some(deployment_id), Some(outcome)) => Ok(Placed {
                deployment_id,
                outcome,
            }),
            _ => Err(ServingStateError::UnexpectedPlacement),
        }
    }

    async fn claim_route(&self, lease: &RouteLease) -> Result<(), ServingStateError> {
        let _: i64 = self
            .claim_route_script
            .prepare_invoke()
            .key(lease.session_key())
            .key(lease.lease_key())
            .arg(lease.generation_id.to_string())
            .arg(lease.deployment_id.to_string())
            .arg(Utc::now().timestamp_millis())
            .arg(lease.expires_at.timestamp_millis())
            .arg(SESSION_LIFETIME.as_millis() as u64)
            .invoke_async(&mut self.connection.clone())
            .await?;

        Ok(())
    }

    async fn release_route(&self, lease: &RouteLease) -> Result<(), ServingStateError> {
        let _: i64 = self
            .query(
                redis::cmd("ZREM")
                    .arg(lease.lease_key())
                    .arg(lease.generation_id.to_string()),
            )
            .await?;

        Ok(())
    }

    async fn admit_eval(
        &self,
        lease: &EvalLease,
        config: &GatewayConfig,
    ) -> Result<EvalAdmission, ServingStateError> {
        let result: i64 = self
            .eval_admission_script
            .prepare_invoke()
            .key(lease.inflight_key())
            .key(lease.minute_key())
            .arg(lease.generation_id.to_string())
            .arg(lease.now.timestamp_millis())
            .arg(lease.expires_at.timestamp_millis())
            .arg(config.eval_concurrency_cap)
            .arg(config.eval_requests_per_minute)
            .invoke_async(&mut self.connection.clone())
            .await?;

        match result {
            1 => Ok(EvalAdmission::Admitted),
            2 => Ok(EvalAdmission::ConcurrencyCapped),
            _ => Ok(EvalAdmission::RateCapped),
        }
    }

    async fn release_eval(&self, lease: &EvalLease) -> Result<(), ServingStateError> {
        let _: i64 = self
            .query(
                redis::cmd("ZREM")
                    .arg(lease.inflight_key())
                    .arg(lease.generation_id.to_string()),
            )
            .await?;

        Ok(())
    }
}

#[derive(Clone)]
struct SettlementKeys {
    account: String,
    inflight: String,
    applied_balance_transactions: String,
    settlement_stream: String,
}

impl SettlementKeys {
    fn new(organization_id: Uuid) -> Self {
        Self::with_hash_tag(organization_id, SETTLEMENT_HASH_TAG)
    }

    fn with_hash_tag(organization_id: Uuid, hash_tag: &str) -> Self {
        Self {
            account: format!("account:{{{hash_tag}}}:{organization_id}"),
            inflight: format!("inflight:{{{hash_tag}}}:{organization_id}"),
            applied_balance_transactions: format!(
                "applied-balance-transactions:{{{hash_tag}}}:{organization_id}"
            ),
            settlement_stream: format!("generation-settled:{{{hash_tag}}}"),
        }
    }
}

fn ledger_position(seeded_at: Option<&str>, seeded_id: Option<&str>) -> Option<LedgerPosition> {
    Some(LedgerPosition {
        created_at: epoch_millis(seeded_at?)?,
        id: seeded_id?.parse().ok()?,
    })
}

/// A replay floor excludes its whole millisecond, which a seed that recorded no
/// replay window included entirely.
fn replay_cursor(
    seeded_at: Option<&str>,
    seeded_id: Option<&str>,
    floor_at: Option<&str>,
) -> Option<LedgerPosition> {
    let cursor = ledger_position(seeded_at, seeded_id)?.replay_cursor();
    let Some(floor_at) = floor_at else {
        return Some(cursor);
    };

    let floor = LedgerPosition {
        created_at: epoch_millis(floor_at)?,
        id: Uuid::max(),
    };

    Some(cursor.max(floor))
}

fn epoch_millis(value: &str) -> Option<DateTime<Utc>> {
    DateTime::from_timestamp_millis(value.parse().ok()?)
}

fn account_from_hash(fields: HashMap<String, String>) -> Result<GatewayAccount, ServingStateError> {
    GatewayAccount::from_hash(fields)
        .map_err(|source| ServingStateError::MalformedAccount { source })
}

fn parse_record<T: DeserializeOwned>(
    kind: &'static str,
    value: &str,
) -> Result<T, ServingStateError> {
    serde_json::from_str(value)
        .map_err(|source| ServingStateError::MalformedRecord { kind, source })
}

/// The digest reaches this layer as the hexadecimal text that keys the cache; the
/// column it matches in PostgreSQL is bytes.
fn hex_bytes(value: &str) -> Option<Vec<u8>> {
    if !value.len().is_multiple_of(2) {
        return None;
    }

    (0..value.len())
        .step_by(2)
        .map(|index| u8::from_str_radix(value.get(index..index + 2)?, 16).ok())
        .collect()
}

/// One malformed status drops only its own deployment. A rejected document
/// must never fail every request for the model.
fn parse_deployment_statuses(fields: HashMap<String, String>) -> Vec<DeploymentRuntimeStatus> {
    fields
        .into_iter()
        .filter_map(|(deployment_id, value)| {
            let error_code = match serde_json::from_str::<DeploymentRuntimeStatus>(&value) {
                Ok(status) if status.deployment_id.to_string() == deployment_id => {
                    return Some(status);
                }
                Ok(_) => "deployment_id_mismatch",
                Err(_) => "malformed_record",
            };

            crate::diagnostics::limited_warn!(%deployment_id, phase = "deployment_status_read",
                error_code, "dropping an unusable deployment status");
            None
        })
        .collect()
}

#[derive(Debug, Error)]
pub enum ServingStateError {
    #[error("Valkey operation failed: {0}")]
    Redis(#[from] redis::RedisError),
    #[error("Valkey returned an unexpected PING response")]
    UnexpectedPingResponse,
    #[error("{kind} serving record is malformed: {source}")]
    MalformedRecord {
        kind: &'static str,
        source: serde_json::Error,
    },
    #[error("GatewayAccount serving record is malformed: {source}")]
    MalformedAccount { source: crate::domain::RecordError },
    #[error("GatewayModel ID does not match its Valkey key")]
    MismatchedModelId,
    #[error("GatewayModel properties are invalid: {0}")]
    InvalidModelProperties(#[from] crate::model::ModelPropertiesError),
    #[error("Valkey IAM authentication failed: {0}")]
    Iam(#[from] ValkeyIamError),
    #[error("credential digest is not hexadecimal")]
    MalformedDigest,
    #[error("PostgreSQL read failed: {0}")]
    Postgres(#[from] PostgresError),
    #[error("gateway account balance watermark is missing or malformed")]
    InvalidBalanceWatermark,
    #[error("route placement returned an unknown candidate or outcome")]
    UnexpectedPlacement,
}

impl ServingStateError {
    /// A bounded classification; the underlying errors can contain private record data.
    pub(crate) fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::Redis(error) => match error.code() {
                Some(
                    "ENSURE_ACCOUNT_V1"
                    | "APPLY_BALANCE_TRANSACTIONS_V1"
                    | "MARK_ACCOUNT_REFRESHED_V1",
                ) => "account_script_rejected",
                Some("PLACE_ROUTE_V1" | "CLAIM_ROUTE_V1") => "route_script_rejected",
                _ => "redis",
            },
            Self::UnexpectedPingResponse => "unexpected_ping",
            Self::MalformedRecord { .. } => "malformed_record",
            Self::MalformedAccount { .. } => "malformed_account",
            Self::MismatchedModelId => "model_id_mismatch",
            Self::InvalidModelProperties(_) => "invalid_model_properties",
            Self::Iam(_) => "iam",
            Self::MalformedDigest => "malformed_digest",
            Self::Postgres(_) => "postgres",
            Self::InvalidBalanceWatermark => "invalid_balance_watermark",
            Self::UnexpectedPlacement => "unexpected_placement",
        }
    }

    /// The record exists but this gateway cannot serve it. Other records are
    /// unaffected, unlike a failed dependency.
    fn is_unusable_record(&self) -> bool {
        matches!(
            self,
            Self::MalformedRecord { .. }
                | Self::MismatchedModelId
                | Self::InvalidModelProperties(_)
        )
    }
}

#[cfg(test)]
#[path = "serving_state_tests.rs"]
mod tests;
