use std::collections::HashMap;

use async_trait::async_trait;
use redis::{cluster::ClusterClient, cluster_async::ClusterConnection, FromRedisValue, Script};
use thiserror::Error;
use uuid::Uuid;

use crate::{
    admission::{AdmissionAttempt, AdmissionError, AdmissionLease},
    domain::{GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace},
};

const ADMIT_GENERATION_V1: &str = include_str!("scripts/admit_generation_v1.lua");

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
}

#[derive(Clone)]
pub struct ValkeyServingState {
    connection: ClusterConnection,
    admission_script: Script,
}

impl ValkeyServingState {
    pub async fn connect(url: &str) -> Result<Self, ServingStateError> {
        let client = ClusterClient::new(vec![url])?;
        let connection = client.get_async_connection().await?;

        let state = Self {
            connection,
            admission_script: Script::new(ADMIT_GENERATION_V1),
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
        let value: Option<String> = self
            .query(redis::cmd("GET").arg(format!("credential:{digest_hex}")))
            .await?;
        value
            .map(|value| {
                serde_json::from_str(&value).map_err(|source| ServingStateError::MalformedRecord {
                    kind: "GatewayCredential",
                    source,
                })
            })
            .transpose()
    }

    pub async fn workspace(
        &self,
        workspace_id: Uuid,
    ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
        let value: Option<String> = self
            .query(redis::cmd("GET").arg(format!("workspace:{workspace_id}")))
            .await?;
        value
            .map(|value| {
                serde_json::from_str(&value).map_err(|source| ServingStateError::MalformedRecord {
                    kind: "GatewayWorkspace",
                    source,
                })
            })
            .transpose()
    }

    pub async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        let fields: HashMap<String, String> = self
            .query(redis::cmd("HGETALL").arg(format!("account:{{settlement-0}}:{organization_id}")))
            .await?;
        if fields.is_empty() {
            return Ok(None);
        }
        GatewayAccount::from_hash(fields)
            .map(Some)
            .map_err(|source| ServingStateError::MalformedAccount { source })
    }

    pub async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
        let value: Option<String> = self
            .query(redis::cmd("GET").arg(format!("model:{model_id}")))
            .await?;
        let model = value
            .map(|value| {
                serde_json::from_str::<GatewayModel>(&value).map_err(|source| {
                    ServingStateError::MalformedRecord {
                        kind: "GatewayModel",
                        source,
                    }
                })
            })
            .transpose()?;
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
        let mut model_ids: Vec<String> = self
            .query(redis::cmd("SMEMBERS").arg("gateway-model-ids"))
            .await?;
        model_ids.sort();

        let mut models = Vec::with_capacity(model_ids.len());
        for model_id in model_ids {
            models.push(
                self.model(&model_id)
                    .await?
                    .ok_or(ServingStateError::MissingIndexedModel)?,
            );
        }
        Ok(models)
    }

    pub async fn admit(
        &self,
        attempt: &AdmissionAttempt,
    ) -> Result<AdmissionLease, AdmissionError> {
        self.admit_with_keys(attempt, &AdmissionKeys::settlement(attempt.organization_id))
            .await
    }

    async fn admit_with_keys(
        &self,
        attempt: &AdmissionAttempt,
        keys: &AdmissionKeys,
    ) -> Result<AdmissionLease, AdmissionError> {
        let mut invocation = self.admission_script.prepare_invoke();
        invocation
            .key(&keys.account)
            .key(&keys.inflight)
            .key(&keys.settlement_stream);
        for argument in attempt.script_arguments() {
            invocation.arg(argument);
        }

        let result: i64 = invocation
            .invoke_async(&mut self.connection.clone())
            .await?;
        match result {
            1 => Ok(attempt.lease()),
            2 => Err(AdmissionError::InsufficientBalance),
            3 => Err(AdmissionError::SettlementBacklog),
            4 => Err(AdmissionError::ConcurrencyExceeded),
            5 => Err(AdmissionError::DuplicateGeneration),
            result => Err(AdmissionError::UnknownScriptResult(result)),
        }
    }

    async fn query<T>(&self, command: &mut redis::Cmd) -> redis::RedisResult<T>
    where
        T: FromRedisValue,
    {
        command.query_async(&mut self.connection.clone()).await
    }
}

#[derive(Clone, Debug)]
struct AdmissionKeys {
    account: String,
    inflight: String,
    settlement_stream: String,
}

impl AdmissionKeys {
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
    #[error("gateway-model-ids contains an ID without a corresponding model record")]
    MissingIndexedModel,
    #[error("GatewayModel ID does not match its Valkey key")]
    MismatchedModelId,
    #[error("GatewayModel properties are invalid: {0}")]
    InvalidModelProperties(#[from] crate::model::ModelPropertiesError),
}

#[cfg(test)]
mod tests {
    use chrono::{TimeDelta, TimeZone, Utc};

    use super::*;
    use crate::{admission::AdmissionAttempt, GatewayConfig};

    fn config() -> GatewayConfig {
        GatewayConfig {
            bind_address: "127.0.0.1:3002".parse().unwrap(),
            generation_timeout_seconds: 300,
            lease_finalization_margin_seconds: 60,
            expired_lease_cleanup_grace_seconds: 300,
            prepaid_organization_concurrency_cap: 50,
            balance_per_concurrency_slot_nano_usd: 1_000_000_000,
            settlement_backlog_limit: 100_000,
            valkey_url: "redis://127.0.0.1:6379".to_owned(),
            sglang_api_key: None,
        }
    }

    fn test_keys(organization_id: Uuid) -> AdmissionKeys {
        AdmissionKeys::with_hash_tag(
            organization_id,
            &format!("admission-test-{}", Uuid::now_v7()),
        )
    }

    fn attempt(
        generation_id: Uuid,
        organization_id: Uuid,
        admitted_at: chrono::DateTime<Utc>,
        config: &GatewayConfig,
    ) -> AdmissionAttempt {
        AdmissionAttempt::new(
            generation_id,
            organization_id,
            admitted_at - TimeDelta::seconds(1),
            admitted_at,
            config,
        )
        .unwrap()
    }

    async fn seed_account(
        state: &ValkeyServingState,
        keys: &AdmissionKeys,
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

    async fn delete_test_keys(state: &ValkeyServingState, keys: &AdmissionKeys) {
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

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn local_cluster_enforces_settlement_hash_tag() {
        let state = ValkeyServingState::connect("redis://127.0.0.1:6379")
            .await
            .expect("local Valkey cluster should connect");

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
        let state = ValkeyServingState::connect("redis://127.0.0.1:6379")
            .await
            .unwrap();
        let organization_id = Uuid::now_v7();
        let keys = test_keys(organization_id);
        let config = config();
        let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        seed_account(&state, &keys, organization_id, "prepaid", 1).await;

        let first = attempt(Uuid::now_v7(), organization_id, admitted_at, &config);
        state.admit_with_keys(&first, &keys).await.unwrap();
        let second = attempt(Uuid::now_v7(), organization_id, admitted_at, &config);
        assert!(matches!(
            state.admit_with_keys(&second, &keys).await,
            Err(AdmissionError::ConcurrencyExceeded)
        ));

        let _: () = state
            .query(redis::cmd("HSET").arg(&keys.account).arg("balance").arg(0))
            .await
            .unwrap();
        assert!(matches!(
            state.admit_with_keys(&second, &keys).await,
            Err(AdmissionError::InsufficientBalance)
        ));

        seed_account(&state, &keys, organization_id, "invoiced", -1).await;
        state.admit_with_keys(&second, &keys).await.unwrap();
        assert!(matches!(
            state.admit_with_keys(&first, &keys).await,
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
        let state = ValkeyServingState::connect("redis://127.0.0.1:6379")
            .await
            .unwrap();
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

        let current = attempt(Uuid::now_v7(), organization_id, admitted_at, &config);
        assert!(matches!(
            state.admit_with_keys(&current, &keys).await,
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

        state.admit_with_keys(&current, &keys).await.unwrap();
        let generations: Vec<String> = state
            .query(redis::cmd("ZRANGE").arg(&keys.inflight).arg(0).arg(-1))
            .await
            .unwrap();
        assert!(!generations.contains(&old_generation.to_string()));
        assert!(generations.contains(&recent_generation.to_string()));
        assert!(generations.contains(&current.generation_id.to_string()));

        delete_test_keys(&state, &keys).await;
    }

    #[tokio::test]
    #[ignore = "requires the local one-node Valkey cluster"]
    async fn admission_fails_closed_before_writing_for_invalid_serving_state() {
        let state = ValkeyServingState::connect("redis://127.0.0.1:6379")
            .await
            .unwrap();
        let organization_id = Uuid::now_v7();
        let keys = test_keys(organization_id);
        let config = config();
        let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        let current = attempt(Uuid::now_v7(), organization_id, admitted_at, &config);
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
            state.admit_with_keys(&current, &keys).await,
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
            state.admit_with_keys(&current, &keys).await,
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
        let state = ValkeyServingState::connect("redis://127.0.0.1:6379")
            .await
            .unwrap();
        let organization_id = Uuid::now_v7();
        let keys = test_keys(organization_id);
        let config = config();
        let admitted_at = Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap();
        seed_account(&state, &keys, organization_id, "prepaid", 2_000_000_000).await;

        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..10 {
            let state = state.clone();
            let keys = keys.clone();
            let attempt = attempt(Uuid::now_v7(), organization_id, admitted_at, &config);
            tasks.spawn(async move { state.admit_with_keys(&attempt, &keys).await });
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
}
