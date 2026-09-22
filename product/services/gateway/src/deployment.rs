use axum::http::Uri;
use chrono::{DateTime, TimeDelta, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;
use validator::Validate;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize, Validate)]
#[serde(deny_unknown_fields)]
pub struct GatewayModelDeployment {
    pub id: Uuid,
    pub status: DeploymentStatus,
    #[serde(default = "legacy_provider")]
    #[validate(length(min = 1, max = 100))]
    pub provider: String,
    #[serde(default = "legacy_region")]
    #[validate(length(min = 1, max = 100))]
    pub region: String,
    #[serde(default = "legacy_fault_domain")]
    #[validate(length(min = 1, max = 300))]
    pub fault_domain: String,
    #[validate(url, length(max = 2048))]
    pub service_url: String,
    #[validate(nested)]
    pub release: ModelDeploymentRelease,
}

fn legacy_provider() -> String {
    "legacy".to_owned()
}

fn legacy_region() -> String {
    "unknown".to_owned()
}

fn legacy_fault_domain() -> String {
    "legacy:unknown".to_owned()
}

// The status document is a wire format between independently deployed
// processes. Unknown fields are ignored so a newer producer cannot break an
// older gateway replica during a rolling change.
#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize, Validate)]
pub struct DeploymentRuntimeStatus {
    #[validate(range(min = 1, max = 1))]
    pub schema_version: u16,
    pub deployment_id: Uuid,
    #[validate(length(min = 1, max = 300))]
    pub runtime_revision: String,
    pub received_at: DateTime<Utc>,
    pub healthy: bool,
    pub accepting_requests: bool,
    #[validate(length(min = 1, max = 100))]
    pub reason_code: Option<String>,
}

impl DeploymentRuntimeStatus {
    pub fn is_fresh_at(&self, now: DateTime<Utc>, maximum_age: TimeDelta) -> bool {
        self.received_at <= now + TimeDelta::seconds(5) && self.received_at >= now - maximum_age
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentStatus {
    Available,
    Unavailable,
    Draining,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize, Validate)]
#[serde(deny_unknown_fields)]
pub struct ModelDeploymentRelease {
    #[validate(range(min = 1, max = 1))]
    pub schema_version: u16,
    #[validate(length(min = 1, max = 300))]
    pub runtime_revision: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub protocol: Option<RuntimeProtocol>,
    #[validate(length(min = 1, max = 300))]
    pub model_path: String,
    #[validate(length(min = 1, max = 300))]
    pub model_revision: String,
    #[validate(length(min = 1, max = 300))]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub runtime_model_name: Option<String>,
    #[validate(length(min = 1, max = 300))]
    pub tokenizer_path: String,
    #[validate(length(min = 1, max = 300))]
    pub tokenizer_revision: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tokenizer_mode: Option<TokenizerMode>,
}

/// The wire protocol a deployment's runtime speaks. Absent means the OpenAI chat
/// protocol, which is what all ordinary LLM deployments serve; only a runtime that
/// genuinely speaks something else declares a value here.
#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeProtocol {
    SystemOne,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TokenizerMode {
    DeepseekV4,
    DeepseekV41,
}

impl ModelDeploymentRelease {
    /// Whether this release speaks the native, non-streaming decision protocol.
    pub fn is_system_one(&self) -> bool {
        self.protocol == Some(RuntimeProtocol::SystemOne)
    }

    /// Stable metric label separating ordinary LLM traffic from everything else.
    pub fn protocol_label(&self) -> &'static str {
        match self.protocol {
            None => "openai_chat",
            Some(RuntimeProtocol::SystemOne) => "system_one",
        }
    }
}

impl GatewayModelDeployment {
    pub fn validate(&self) -> Result<(), DeploymentError> {
        <Self as Validate>::validate(self)
            .map_err(|error| DeploymentError::Invalid(error.to_string()))?;
        self.validate_service_url()
    }

    fn validate_service_url(&self) -> Result<(), DeploymentError> {
        let service_uri = self
            .service_url
            .parse::<Uri>()
            .map_err(|_| DeploymentError::Invalid("service_url is invalid".to_owned()))?;
        if !matches!(service_uri.scheme_str(), Some("http" | "https"))
            || service_uri.authority().is_none()
        {
            return Err(DeploymentError::Invalid(
                "service_url must be an absolute HTTP or HTTPS URL".to_owned(),
            ));
        }
        Ok(())
    }

    pub fn served_release_digest(&self) -> Result<String, serde_json::Error> {
        let encoded = serde_json::to_vec(&self.release)?;
        Ok(format!("sha256:{:x}", Sha256::digest(encoded)))
    }
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum DeploymentError {
    #[error("{0}")]
    Invalid(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    fn accepted_deployment() -> GatewayModelDeployment {
        serde_json::from_str(include_str!(
            "../test/fixtures/gateway-model-deployment.accepted.json"
        ))
        .expect("fixture should deserialize")
    }

    #[test]
    fn accepted_fixture_is_strict_and_has_a_stable_release_digest() {
        let deployment = accepted_deployment();

        deployment.validate().expect("fixture should validate");
        let digest = deployment
            .served_release_digest()
            .expect("release should serialize");
        assert_eq!(
            digest,
            "sha256:e4a74e6c4981b6176e08acc9fa391ca5fe5562485b5df96fdf088c48ae406eda"
        );
    }

    #[test]
    fn unknown_deployment_fields_are_rejected() {
        let error = serde_json::from_str::<GatewayModelDeployment>(include_str!(
            "../test/fixtures/gateway-model-deployment.rejected.json"
        ))
        .expect_err("unknown field must be rejected");

        assert!(error.to_string().contains("unexpected_private_option"));
    }

    #[test]
    fn legacy_projection_uses_safe_routing_defaults() {
        let mut value = serde_json::to_value(accepted_deployment()).unwrap();
        let object = value.as_object_mut().unwrap();
        object.remove("provider");
        object.remove("region");
        object.remove("fault_domain");

        let deployment: GatewayModelDeployment = serde_json::from_value(value).unwrap();

        deployment.validate().unwrap();
        assert_eq!(deployment.provider, "legacy");
        assert_eq!(deployment.region, "unknown");
        assert_eq!(deployment.fault_domain, "legacy:unknown");
    }

    #[test]
    fn derived_validation_rejects_invalid_release_fields() {
        let mut deployment = accepted_deployment();
        deployment.release.runtime_revision.clear();

        let error = deployment
            .validate()
            .expect_err("empty release identifiers must be rejected");
        assert!(error.to_string().contains("runtime_revision"));
    }

    #[test]
    fn service_url_requires_http_or_https() {
        let mut deployment = accepted_deployment();
        deployment.service_url = "ftp://runtime.internal/model".to_owned();

        assert_eq!(
            deployment.validate(),
            Err(DeploymentError::Invalid(
                "service_url must be an absolute HTTP or HTTPS URL".to_owned()
            ))
        );
    }

    #[test]
    fn status_ignores_unknown_fields_and_requires_known_ones() {
        let status: DeploymentRuntimeStatus = serde_json::from_value(serde_json::json!({
            "schema_version": 1,
            "deployment_id": Uuid::nil(),
            "runtime_revision": "vllm-revision",
            "received_at": "2026-08-27T12:00:00Z",
            "healthy": true,
            "accepting_requests": true,
            "reason_code": null,
            "maximum_concurrency": 4
        }))
        .expect("a retired field must not break a running producer");
        assert_eq!(status.runtime_revision, "vllm-revision");

        let missing = serde_json::from_value::<DeploymentRuntimeStatus>(serde_json::json!({
            "schema_version": 1,
            "deployment_id": Uuid::nil(),
            "runtime_revision": "vllm-revision",
            "received_at": "2026-08-27T12:00:00Z",
            "healthy": true
        }));
        assert!(
            missing.is_err(),
            "a missing required field must be rejected"
        );
    }
}
