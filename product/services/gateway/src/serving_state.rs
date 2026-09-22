use std::{collections::HashMap, time::Duration};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use redis::{
    cluster::{ClusterClient, ClusterClientBuilder},
    cluster_async::ClusterConnection,
    FromRedisValue, Script,
};
use thiserror::Error;
use uuid::Uuid;

use crate::{
    admission::{cleanup_cutoff, AdmissionError, AdmissionLease},
    cache::LazyTtlCache,
    deployment::DeploymentRuntimeStatus,
    domain::{GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace},
    postgres_reader::{AccountRecord, PostgresError, PostgresReader},
    FinalizationError, FinalizationOutcome, GatewayConfig, GenerationProperties,
};
use crate::{valkey_auth::ValkeyIamCredentials, ValkeyIamConfig};

const ADMIT_GENERATION_V1: &str = include_str!("scripts/admit_generation_v1.lua");
const FINALIZE_GENERATION_V1: &str = include_str!("scripts/finalize_generation_v1.lua");
const ENSURE_ACCOUNT_V1: &str = include_str!("scripts/ensure_account_v1.lua");
const APPLY_BALANCE_TRANSACTIONS_V1: &str =
    include_str!("scripts/apply_balance_transactions_v1.lua");
/// One request never applies more than this many ledger entries; the next one
/// continues from the watermark this batch advanced.
const BALANCE_TRANSACTION_BATCH: i64 = 500;
/// The gateway's own fields in the account hash. They record what the seed
/// included and when metadata was last refreshed, and they are not part of the
/// account record, which rejects fields it does not declare.
const ACCOUNT_BOOKKEEPING: [&str; 2] = ["balance_seeded_at", "metadata_refreshed_at"];
/// Deployment statuses are pushed by the runtimes and expire on their own, so
/// this only stops one request from reading the same key repeatedly.
const STATUS_CACHE_TTL: Duration = Duration::from_secs(1);
/// Status keys come from requests, so the contract caps their count.
const STATUS_CACHE_CAPACITY: usize = 10_000;

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
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        let _ = release_digest;
        Err(ServingStateError::UnsupportedOperation)
    }
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
        let connection = client.get_async_connection().await?;

        let state = Self {
            connection,
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

    pub async fn credential(
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

    pub async fn workspace(
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

    /// Reads a record from the Valkey cache, then from PostgreSQL. A record that
    /// PostgreSQL does not have is never cached, so a key or model created a moment
    /// ago is visible at once and a projection gap cannot invent a missing record.
    async fn read_through<T, F, Fut>(
        &self,
        kind: &'static str,
        key: String,
        load: F,
    ) -> Result<Option<T>, ServingStateError>
    where
        T: serde::de::DeserializeOwned,
        F: FnOnce() -> Fut,
        Fut: std::future::Future<Output = Result<Option<String>, PostgresError>>,
    {
        let cached: Option<String> = self.query(redis::cmd("GET").arg(&key)).await?;
        if let Some(cached) = cached {
            return parse_record(kind, &cached).map(Some);
        }

        let Some(record) = load().await? else {
            return Ok(None);
        };
        let parsed = parse_record(kind, &record)?;
        // Caching after parsing keeps a record this gateway cannot read out of the
        // cache, where it would fail every later request for the same key.
        let _: () = self
            .query(
                redis::cmd("SET")
                    .arg(&key)
                    .arg(&record)
                    .arg("EX")
                    .arg(self.record_cache_ttl.as_secs().max(1)),
            )
            .await?;

        Ok(Some(parsed))
    }

    /// The account hash is operational state, not a cache: it holds the balance
    /// that settlement moves. It is seeded once from PostgreSQL and never expires;
    /// only its metadata is refreshed, and only when it has gone stale.
    pub async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        let key = format!("account:{{settlement-0}}:{organization_id}");
        let fields: HashMap<String, String> = self.query(redis::cmd("HGETALL").arg(&key)).await?;
        if !fields.is_empty() && self.account_metadata_is_current(&fields) {
            return account_from_hash(fields).map(Some);
        }

        let Some(record) = self.database.account(organization_id).await? else {
            return Ok(None);
        };
        self.ensure_account(&key, organization_id, &record).await?;
        self.apply_balance_transactions(&key, organization_id)
            .await?;

        let fields: HashMap<String, String> = self.query(redis::cmd("HGETALL").arg(&key)).await?;
        if fields.is_empty() {
            return Ok(None);
        }

        account_from_hash(fields).map(Some)
    }

    /// Moves ledger entries created after the seed into the operational balance.
    /// Nothing else applies them, so a customer's top-up lands on their next
    /// request, which is the only moment the balance has to be right.
    async fn apply_balance_transactions(
        &self,
        key: &str,
        organization_id: Uuid,
    ) -> Result<(), ServingStateError> {
        let watermark: Option<String> = self
            .query(redis::cmd("HGET").arg(key).arg("balance_seeded_at"))
            .await?;
        let watermark = watermark
            .and_then(|value| value.parse::<i64>().ok())
            .and_then(DateTime::from_timestamp_millis)
            .ok_or(ServingStateError::MissingBalanceWatermark)?;

        let transactions = self
            .database
            .balance_transactions_after(organization_id, watermark, BALANCE_TRANSACTION_BATCH)
            .await?;
        let Some(highest) = transactions.last().map(|entry| entry.created_at) else {
            return Ok(());
        };

        let mut script = self.apply_balance_script.prepare_invoke();
        script
            .key(key)
            .key(format!(
                "applied-balance-transactions:{{settlement-0}}:{organization_id}"
            ))
            .arg(highest.timestamp_millis());
        for transaction in &transactions {
            script
                .arg(transaction.id.to_string())
                .arg(transaction.amount);
        }
        let _: i64 = script.invoke_async(&mut self.connection.clone()).await?;

        Ok(())
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
        key: &str,
        organization_id: Uuid,
        record: &AccountRecord,
    ) -> Result<(), ServingStateError> {
        let _: i64 = self
            .ensure_account_script
            .key(key)
            .arg(organization_id.to_string())
            .arg(&record.organization_kind)
            .arg(&record.organization_status)
            .arg(&record.billing_mode)
            .arg(record.balance)
            .arg(record.balance_updated_at.timestamp_millis())
            .arg(Utc::now().timestamp_millis())
            .invoke_async(&mut self.connection.clone())
            .await?;

        Ok(())
    }

    pub async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
        let model: Option<GatewayModel> = self
            .read_through("GatewayModel", format!("model:{model_id}"), || {
                self.database.model_json(model_id)
            })
            .await?;
        if let Some(model) = &model {
            model
                .properties
                .validate_for_serving()
                .map_err(ServingStateError::InvalidModelProperties)?;
        }
        if model.as_ref().is_some_and(|model| model.id != model_id) {
            return Err(ServingStateError::MismatchedModelId);
        }
        Ok(model)
    }

    pub async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
        let model_ids = self.database.model_ids().await?;

        let mut models = Vec::with_capacity(model_ids.len());
        for model_id in model_ids {
            match self.model(&model_id).await {
                Ok(Some(model)) => models.push(model),
                Ok(None)
                | Err(ServingStateError::MalformedRecord { .. })
                | Err(ServingStateError::MismatchedModelId)
                | Err(ServingStateError::InvalidModelProperties(_)) => {}
                Err(error) => return Err(error),
            }
        }
        Ok(models)
    }

    pub async fn deployment_statuses(
        &self,
        release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        self.status_cache
            .get_or_load(release_digest.to_owned(), || async {
                let fields: HashMap<String, String> = self
                    .query(
                        redis::cmd("HGETALL")
                            .arg(format!("deployment-status:{{{release_digest}}}")),
                    )
                    .await?;
                Ok(parse_deployment_statuses(fields))
            })
            .await
    }

    pub async fn admit(
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
            &GenerationKeys::settlement(organization_id),
        )
        .await
    }

    async fn admit_with_keys(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
        keys: &GenerationKeys,
    ) -> Result<AdmissionLease, AdmissionError> {
        let lease = AdmissionLease::new(generation_id, received_at, admitted_at, config)?;
        let cleanup_cutoff = cleanup_cutoff(admitted_at, config)?;
        let mut invocation = self.admission_script.prepare_invoke();
        invocation
            .key(&keys.account)
            .key(&keys.inflight)
            .key(&keys.settlement_stream)
            .arg(generation_id.to_string())
            .arg(organization_id.to_string())
            .arg(admitted_at.timestamp_millis())
            .arg(lease.lease_expires_at().timestamp_millis())
            .arg(cleanup_cutoff.timestamp_millis())
            .arg(config.prepaid_organization_concurrency_cap)
            .arg(config.balance_per_concurrency_slot_nano_usd)
            .arg(config.settlement_backlog_limit);

        let result: i64 = invocation
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

    pub async fn finalize(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        self.finalize_with_keys(
            generation_id,
            organization_id,
            properties,
            &GenerationKeys::settlement(organization_id),
        )
        .await
    }

    async fn finalize_with_keys(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        properties: &GenerationProperties,
        keys: &GenerationKeys,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        if properties.organization_id() != organization_id {
            return Err(FinalizationError::OrganizationMismatch);
        }
        let charge = properties.charge();
        let properties = serde_json::to_string(properties)?;
        let result: i64 = self
            .finalization_script
            .prepare_invoke()
            .key(&keys.account)
            .key(&keys.inflight)
            .key(&keys.settlement_stream)
            .arg(generation_id.to_string())
            .arg(organization_id.to_string())
            .arg(charge)
            .arg(properties)
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

fn account_from_hash(
    mut fields: HashMap<String, String>,
) -> Result<GatewayAccount, ServingStateError> {
    for field in ACCOUNT_BOOKKEEPING {
        fields.remove(field);
    }

    GatewayAccount::from_hash(fields)
        .map_err(|source| ServingStateError::MalformedAccount { source })
}

fn parse_record<T>(kind: &'static str, value: &str) -> Result<T, ServingStateError>
where
    T: serde::de::DeserializeOwned,
{
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
        .map(|index| u8::from_str_radix(&value[index..index + 2], 16).ok())
        .collect()
}

/// One malformed status drops only its own deployment. A rejected document
/// must never fail every request for the model.
fn parse_deployment_statuses(fields: HashMap<String, String>) -> Vec<DeploymentRuntimeStatus> {
    let mut statuses = Vec::with_capacity(fields.len());
    for (deployment_id, value) in fields {
        let status: DeploymentRuntimeStatus = match serde_json::from_str(&value) {
            Ok(status) => status,
            Err(_) => {
                crate::diagnostics::limited_warn!(
                    deployment_id = %deployment_id,
                    phase = "deployment_status_read",
                    error_code = "malformed_record",
                    "dropping malformed deployment status"
                );
                continue;
            }
        };
        if status.deployment_id.to_string() != deployment_id {
            crate::diagnostics::limited_warn!(
                deployment_id = %deployment_id,
                phase = "deployment_status_read",
                error_code = "deployment_id_mismatch",
                "dropping mismatched deployment status"
            );
            continue;
        }
        statuses.push(status);
    }
    statuses
}

#[derive(Clone, Debug)]
struct GenerationKeys {
    account: String,
    inflight: String,
    settlement_stream: String,
}

impl GenerationKeys {
    fn settlement(organization_id: Uuid) -> Self {
        Self::with_hash_tag(organization_id, "settlement-0")
    }

    fn with_hash_tag(organization_id: Uuid, hash_tag: &str) -> Self {
        Self {
            account: format!("account:{{{hash_tag}}}:{organization_id}"),
            inflight: format!("inflight:{{{hash_tag}}}:{organization_id}"),
            settlement_stream: format!("generation-settled:{{{hash_tag}}}"),
        }
    }
}

#[async_trait]
impl ServingState for ValkeyServingState {
    async fn credential(
        &self,
        digest_hex: &str,
    ) -> Result<Option<GatewayCredential>, ServingStateError> {
        ValkeyServingState::credential(self, digest_hex).await
    }

    async fn workspace(
        &self,
        workspace_id: Uuid,
    ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
        ValkeyServingState::workspace(self, workspace_id).await
    }

    async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        ValkeyServingState::account(self, organization_id).await
    }

    async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
        ValkeyServingState::model(self, model_id).await
    }

    async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
        ValkeyServingState::models(self).await
    }

    async fn deployment_statuses(
        &self,
        release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        ValkeyServingState::deployment_statuses(self, release_digest).await
    }

    async fn admit(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        received_at: DateTime<Utc>,
        admitted_at: DateTime<Utc>,
        config: &GatewayConfig,
    ) -> Result<AdmissionLease, AdmissionError> {
        ValkeyServingState::admit(
            self,
            generation_id,
            organization_id,
            received_at,
            admitted_at,
            config,
        )
        .await
    }

    async fn finalize(
        &self,
        generation_id: Uuid,
        organization_id: Uuid,
        properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        ValkeyServingState::finalize(self, generation_id, organization_id, properties).await
    }
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
    #[error("deployment capacity script returned {0}")]
    UnknownDeploymentScriptResult(i64),
    #[error("serving state operation is not implemented")]
    UnsupportedOperation,
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
            Self::UnknownDeploymentScriptResult(_) => "unexpected_script_result",
            Self::UnsupportedOperation => "unsupported_operation",
            Self::InvalidModelProperties(_) => "invalid_model_properties",
            Self::Iam(_) => "iam",
            Self::MalformedDigest => "malformed_digest",
            Self::Postgres(_) => "postgres",
            Self::MissingBalanceWatermark => "missing_balance_watermark",
        }
    }
}

#[cfg(test)]
mod tests {
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

    fn test_keys(organization_id: Uuid) -> GenerationKeys {
        GenerationKeys::with_hash_tag(
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
        keys: &GenerationKeys,
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
        keys: &GenerationKeys,
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

    async fn delete_test_keys(state: &ValkeyServingState, keys: &GenerationKeys) {
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
}
