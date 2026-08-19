use std::collections::HashMap;

use async_trait::async_trait;
use redis::{cluster::ClusterClient, cluster_async::ClusterConnection, FromRedisValue};
use thiserror::Error;
use uuid::Uuid;

use crate::domain::{GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace};

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
}

impl ValkeyServingState {
    pub async fn connect(url: &str) -> Result<Self, ServingStateError> {
        let client = ClusterClient::new(vec![url])?;
        let connection = client.get_async_connection().await?;

        let state = Self { connection };
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
    use super::*;

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
}
