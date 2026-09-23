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
    cache::LazyTtlCache,
    deployment::DeploymentRuntimeStatus,
    domain::{GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace},
    postgres_reader::{
        AccountRecord, BalanceTransaction, LedgerPosition, PostgresError, PostgresReader,
    },
    valkey_auth::ValkeyIamCredentials,
    FinalizationError, FinalizationOutcome, GatewayConfig, GenerationProperties, ValkeyIamConfig,
};

const ADMIT_GENERATION_V1: &str = include_str!("scripts/admit_generation_v1.lua");
const FINALIZE_GENERATION_V1: &str = include_str!("scripts/finalize_generation_v1.lua");
const ENSURE_ACCOUNT_V1: &str = include_str!("scripts/ensure_account_v1.lua");
const APPLY_BALANCE_TRANSACTIONS_V1: &str =
    include_str!("scripts/apply_balance_transactions_v1.lua");

/// Every settlement key shares this hash tag, so one script can touch them all.
const SETTLEMENT_HASH_TAG: &str = "settlement-0";
/// One request never applies more than this many ledger entries; the next one
/// continues from the watermark this batch advanced.
const BALANCE_TRANSACTION_BATCH: i64 = 500;
/// Deployment statuses are pushed by the runtimes and expire on their own, so
/// this only stops one request from reading the same key repeatedly.
const STATUS_CACHE_TTL: Duration = Duration::from_secs(1);
/// Status keys come from requests, so the contract caps their count.
const STATUS_CACHE_CAPACITY: usize = 10_000;

/// The state the gateway serves from: identity and catalog records, runtime
/// statuses, and the admission and settlement of generations.
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

    async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError>;

    async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError>;

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
}

#[derive(Clone)]
pub struct ValkeyServingState {
    connection: ClusterConnection,
    admission_script: Script,
    finalization_script: Script,
    ensure_account_script: Script,
    apply_balance_script: Script,
    database: PostgresReader,
    record_cache_ttl: Duration,
    status_cache: LazyTtlCache<String, Vec<DeploymentRuntimeStatus>>,
}

impl ValkeyServingState {
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
        let credentials = ValkeyIamCredentials::start(config)
            .await
            .map_err(|error| ServingStateError::Iam(error.to_string()))?;
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
            database,
            record_cache_ttl,
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
    /// ago is visible at once.
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
        let cached: Option<String> = self.query(redis::cmd("GET").arg(&key)).await?;
        if let Some(cached) = cached {
            return parse_record(kind, &cached).map(Some);
        }

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
                    .arg(&key)
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

    fn account_metadata_is_current(&self, fields: &HashMap<String, String>) -> bool {
        let ttl = self.record_cache_ttl.as_millis() as i64;

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
        let seeded_at = record.balance_updated_at;
        let _: i64 = self
            .ensure_account_script
            .key(&keys.account)
            .arg(organization_id.to_string())
            .arg(&record.organization_kind)
            .arg(&record.organization_status)
            .arg(&record.billing_mode)
            .arg(record.balance)
            .arg(seeded_at.timestamp_millis())
            .arg(LedgerPosition::after_balance_at(seeded_at).id.to_string())
            .arg(Utc::now().timestamp_millis())
            .invoke_async(&mut self.connection.clone())
            .await?;

        Ok(())
    }

    /// Moves ledger entries created after the seed into the operational balance.
    /// Nothing else applies them, so a customer's top-up lands on their next
    /// request, which is the only moment the balance has to be right.
    async fn apply_balance_transactions(
        &self,
        keys: &SettlementKeys,
        organization_id: Uuid,
    ) -> Result<(), ServingStateError> {
        let (seeded_at, seeded_id): (Option<String>, Option<String>) = self
            .query(
                redis::cmd("HMGET")
                    .arg(&keys.account)
                    .arg("balance_seeded_at")
                    .arg("balance_seeded_id"),
            )
            .await?;
        let watermark = ledger_position(seeded_at.as_deref(), seeded_id.as_deref())
            .ok_or(ServingStateError::MissingBalanceWatermark)?;

        let transactions = self
            .database
            .balance_transactions_after(organization_id, watermark, BALANCE_TRANSACTION_BATCH)
            .await?;

        // The cursor is the last entry applied, not the last timestamp seen, so a
        // batch that ends between two entries sharing a timestamp resumes correctly.
        let Some(highest) = transactions.last().map(BalanceTransaction::position) else {
            return Ok(());
        };

        let mut script = self.apply_balance_script.prepare_invoke();
        script
            .key(&keys.account)
            .key(&keys.applied_balance_transactions)
            .arg(highest.created_at.timestamp_millis())
            .arg(highest.id.to_string());
        for transaction in &transactions {
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
        let fields = self.account_hash(&keys.account).await?;
        if !fields.is_empty() && self.account_metadata_is_current(&fields) {
            return account_from_hash(fields).map(Some);
        }

        let Some(record) = self.database.account(organization_id).await? else {
            return Ok(None);
        };

        self.ensure_account(&keys, organization_id, &record).await?;
        self.apply_balance_transactions(&keys, organization_id)
            .await?;

        let fields = self.account_hash(&keys.account).await?;
        if fields.is_empty() {
            return Ok(None);
        }

        account_from_hash(fields).map(Some)
    }

    async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
        let model: Option<GatewayModel> = self
            .read_through("GatewayModel", format!("model:{model_id}"), || {
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
        if model.id != model_id {
            return Err(ServingStateError::MismatchedModelId);
        }

        Ok(Some(model))
    }

    /// Every model that can be served. A model whose record is unusable is left
    /// out rather than failing the whole listing.
    async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
        let model_ids = self.database.model_ids().await?;

        let mut models = Vec::with_capacity(model_ids.len());
        for model_id in model_ids {
            match self.model(&model_id).await {
                Ok(Some(model)) => models.push(model),
                Ok(None) => {}
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
        self.admit_with_keys(
            generation_id,
            organization_id,
            received_at,
            admitted_at,
            config,
            &SettlementKeys::new(organization_id),
        )
        .await
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
}

/// The Valkey keys that admission and settlement touch for one organization.
#[derive(Clone, Debug)]
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

/// The ledger position the account hash already includes. A hash seeded before
/// entry IDs were recorded includes every entry at its timestamp.
fn ledger_position(seeded_at: Option<&str>, seeded_id: Option<&str>) -> Option<LedgerPosition> {
    let created_at = DateTime::from_timestamp_millis(seeded_at?.parse().ok()?)?;
    let id = seeded_id
        .and_then(|value| value.parse().ok())
        .unwrap_or_else(Uuid::max);

    Some(LedgerPosition { created_at, id })
}

/// The hash also carries the gateway's own bookkeeping, which `GatewayAccount`
/// ignores because it does not declare those fields.
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
    Iam(String),
    #[error("credential digest is not hexadecimal")]
    MalformedDigest,
    #[error("PostgreSQL read failed: {0}")]
    Postgres(#[from] PostgresError),
    #[error("gateway account has no balance watermark")]
    MissingBalanceWatermark,
}

impl ServingStateError {
    /// A bounded classification; the underlying errors can contain private record data.
    pub(crate) fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::Redis(_) => "redis",
            Self::UnexpectedPingResponse => "unexpected_ping",
            Self::MalformedRecord { .. } => "malformed_record",
            Self::MalformedAccount { .. } => "malformed_account",
            Self::MismatchedModelId => "model_id_mismatch",
            Self::InvalidModelProperties(_) => "invalid_model_properties",
            Self::Iam(_) => "iam",
            Self::MalformedDigest => "malformed_digest",
            Self::Postgres(_) => "postgres",
            Self::MissingBalanceWatermark => "missing_balance_watermark",
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
