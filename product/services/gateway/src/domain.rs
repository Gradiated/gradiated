use std::collections::HashMap;

use chrono::{DateTime, Utc};
use serde::{de, de::value::MapDeserializer, Deserialize, Deserializer};
use thiserror::Error;
use uuid::Uuid;

use crate::deployment::{DeploymentStatus, GatewayModelDeployment};
use crate::model::GatewayModelProperties;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct GatewayCredential {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub expires_at: Option<DateTime<Utc>>,
    pub revoked_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct GatewayWorkspace {
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub archived_at: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct GatewayModel {
    pub id: String,
    pub name: String,
    pub status: ModelStatus,
    pub properties: GatewayModelProperties,
    pub deployments: Vec<GatewayModelDeployment>,
}

impl GatewayModel {
    pub fn first_available_deployment(
        &self,
    ) -> Result<Option<&GatewayModelDeployment>, ModelRouteError> {
        if self.status != ModelStatus::Available {
            return Ok(None);
        }
        let deployment = self
            .deployments
            .iter()
            .find(|deployment| deployment.status == DeploymentStatus::Available)
            .ok_or(ModelRouteError::Missing)?;
        deployment.validate().map_err(ModelRouteError::Invalid)?;
        Ok(Some(deployment))
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ModelStatus {
    Available,
    Unavailable,
    Retired,
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum ModelRouteError {
    #[error("available model has no available deployment")]
    Missing,
    #[error("available model deployment is invalid: {0}")]
    Invalid(crate::deployment::DeploymentError),
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum OrganizationKind {
    Customer,
    DistributionChannel,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum OrganizationStatus {
    Active,
    Suspended,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum BillingMode {
    Prepaid,
    Invoiced,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct GatewayAccount {
    pub organization_id: Uuid,
    pub organization_kind: OrganizationKind,
    pub organization_status: OrganizationStatus,
    pub billing_mode: BillingMode,
    #[serde(deserialize_with = "deserialize_i64_from_string")]
    pub balance: i64,
}

impl GatewayAccount {
    pub fn from_hash(fields: HashMap<String, String>) -> Result<Self, RecordError> {
        let values = MapDeserializer::<_, de::value::Error>::new(fields.into_iter());
        Self::deserialize(values).map_err(RecordError::from)
    }
}

fn deserialize_i64_from_string<'de, D>(deserializer: D) -> Result<i64, D::Error>
where
    D: Deserializer<'de>,
{
    String::deserialize(deserializer)?
        .parse()
        .map_err(de::Error::custom)
}

#[derive(Debug, Error)]
#[error("record does not match its schema: {0}")]
pub struct RecordError(#[from] de::value::Error);

#[cfg(test)]
mod tests {
    use super::*;
    use crate::deployment::ModelDeploymentRelease;

    fn valid_account() -> HashMap<String, String> {
        HashMap::from([
            (
                "organization_id".to_owned(),
                "0198c36f-9b6a-7000-8000-000000000001".to_owned(),
            ),
            ("organization_kind".to_owned(), "customer".to_owned()),
            ("organization_status".to_owned(), "active".to_owned()),
            ("billing_mode".to_owned(), "prepaid".to_owned()),
            ("balance".to_owned(), "1000000000".to_owned()),
        ])
    }

    fn deployment(id: u128, status: DeploymentStatus) -> GatewayModelDeployment {
        GatewayModelDeployment {
            id: Uuid::from_u128(id),
            status,
            provider: "local".to_owned(),
            region: "local".to_owned(),
            fault_domain: format!("local:{id}"),
            service_url: "http://127.0.0.1:30000".to_owned(),
            release: ModelDeploymentRelease {
                schema_version: 1,
                runtime_revision: "runtime".to_owned(),
                model_path: "model".to_owned(),
                model_revision: "model-revision".to_owned(),
                runtime_model_name: None,
                tokenizer_path: "tokenizer".to_owned(),
                tokenizer_revision: "tokenizer-revision".to_owned(),
                tokenizer_mode: None,
            },
        }
    }

    fn model(deployments: Vec<GatewayModelDeployment>) -> GatewayModel {
        GatewayModel {
            id: "model".to_owned(),
            name: "Model".to_owned(),
            status: ModelStatus::Available,
            properties: serde_json::from_value(serde_json::json!({
                "schema_version": 1,
                "description": "Model",
                "released_at": null,
                "hugging_face_id": null,
                "quantization": null,
                "tokenizer": null,
                "input_modalities": [{
                    "type": "text",
                    "supported_inputs": {
                        "max_context_length": {"value": 4096, "unit": "token"},
                        "max_prompt_length": {"value": 4096, "unit": "token"}
                    },
                    "pricing": [
                        {"type": "prompt", "unit": "token", "cost": 0},
                        {"type": "cached_prompt", "unit": "token", "cost": 0}
                    ]
                }],
                "output_modalities": [{
                    "type": "text",
                    "max_length": {"value": 1024, "unit": "token"},
                    "default_length": {"value": 1024, "unit": "token"},
                    "streaming": true,
                    "supported_parameters": {},
                    "pricing": [{"type": "completion", "unit": "token", "cost": 0}]
                }],
                "passthrough_parameters": {},
                "deprecation_date": null
            }))
            .unwrap(),
            deployments,
        }
    }

    #[test]
    fn account_hash_is_strict_and_preserves_integer_money() {
        let account = GatewayAccount::from_hash(valid_account()).expect("account should parse");
        assert_eq!(account.balance, 1_000_000_000);
        assert_eq!(account.billing_mode, BillingMode::Prepaid);
    }

    #[test]
    fn account_hash_rejects_unknown_fields() {
        let mut fields = valid_account();
        fields.insert("unexpected".to_owned(), "value".to_owned());
        assert!(GatewayAccount::from_hash(fields).is_err());
    }

    #[test]
    fn account_hash_rejects_missing_or_malformed_fields() {
        let mut missing = valid_account();
        missing.remove("billing_mode");
        assert!(GatewayAccount::from_hash(missing).is_err());

        let mut malformed = valid_account();
        malformed.insert("balance".to_owned(), "one dollar".to_owned());
        assert!(GatewayAccount::from_hash(malformed).is_err());
    }

    #[test]
    fn available_model_selects_the_first_available_deployment() {
        let first = deployment(1, DeploymentStatus::Available);
        let staged = deployment(2, DeploymentStatus::Unavailable);
        let second = deployment(3, DeploymentStatus::Available);
        let routed_model = model(vec![first.clone(), staged, second]);
        let route = routed_model
            .first_available_deployment()
            .expect("multiple available deployments are valid")
            .expect("available model should have a route");
        assert_eq!(route.id, first.id);

        assert_eq!(
            model(Vec::new()).first_available_deployment(),
            Err(ModelRouteError::Missing)
        );
    }
}
