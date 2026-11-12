use axum::http::Uri;
use chrono::{DateTime, TimeDelta, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use thiserror::Error;
use uuid::Uuid;
use validator::{Validate, ValidationErrors};

const MAXIMUM_STATUS_CLOCK_SKEW: TimeDelta = TimeDelta::seconds(5);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize, Validate)]
pub struct GatewayModelDeployment {
    pub id: Uuid,
    pub status: DeploymentStatus,
    #[validate(length(min = 1, max = 100))]
    pub provider: String,
    #[validate(length(min = 1, max = 100))]
    pub region: String,
    #[validate(length(min = 1, max = 300))]
    pub fault_domain: String,
    #[validate(url, length(max = 2048))]
    pub service_url: String,
    #[validate(nested)]
    pub release: ModelDeploymentRelease,
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
    /// The runtime's concurrent request limit. Routing weights each candidate by
    /// it, and uses equal weights when any candidate leaves it out.
    #[validate(range(min = 1, max = 4096))]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub active_requests: Option<u32>,
    #[validate(length(min = 1, max = 100))]
    pub reason_code: Option<String>,
}

impl DeploymentRuntimeStatus {
    pub fn is_fresh_at(&self, now: DateTime<Utc>, maximum_age: TimeDelta) -> bool {
        self.received_at <= now + MAXIMUM_STATUS_CLOCK_SKEW && self.received_at >= now - maximum_age
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DeploymentStatus {
    Available,
    Unavailable,
    Draining,
}

// This one stays strict on purpose. Its serialisation is the deployment's identity:
// `served_release_digest` hashes it, and the runtimes write their heartbeats under
// that hash. Ignoring an unknown field would compute a different digest from the
// producer's and silently route heartbeats to a key nothing reads, so failing to
// parse is the safer failure.
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lora_enabled: Option<bool>,
    #[validate(length(min = 1, max = 300))]
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lora_base_model_revision: Option<String>,
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
    pub fn is_system_one(&self) -> bool {
        self.protocol == Some(RuntimeProtocol::SystemOne)
    }

    /// Whether the runtime receives token IDs rendered by this gateway instead of
    /// chat messages it renders itself.
    pub fn sends_token_ids(&self) -> bool {
        self.runtime_revision.starts_with("native-")
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
        <Self as Validate>::validate(self)?;

        self.validate_service_url()
    }

    fn validate_service_url(&self) -> Result<(), DeploymentError> {
        let service_uri = self
            .service_url
            .parse::<Uri>()
            .map_err(|_| DeploymentError::ServiceUrl)?;

        if !matches!(service_uri.scheme_str(), Some("http" | "https"))
            || service_uri.authority().is_none()
        {
            return Err(DeploymentError::ServiceUrl);
        }

        Ok(())
    }

    pub fn served_release_digest(&self) -> Result<String, serde_json::Error> {
        let encoded = serde_json::to_vec(&self.release)?;
        Ok(format!("sha256:{:x}", Sha256::digest(encoded)))
    }
}

#[derive(Debug, Error, PartialEq)]
pub enum DeploymentError {
    #[error("deployment does not match its schema: {0}")]
    Schema(#[from] ValidationErrors),
    #[error("service_url must be an absolute HTTP or HTTPS URL")]
    ServiceUrl,
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
    fn an_unknown_field_is_tolerated_on_the_deployment_and_refused_in_the_release() {
        let deployment = serde_json::from_str::<GatewayModelDeployment>(include_str!(
            "../test/fixtures/gateway-model-deployment.rejected.json"
        ))
        .expect("an unknown deployment field is ignored");
        assert_eq!(deployment.provider, "local");

        let mut value = serde_json::to_value(accepted_deployment()).unwrap();
        value["release"]["unexpected_release_option"] = serde_json::json!(true);
        let error = serde_json::from_value::<GatewayModelDeployment>(value)
            .expect_err("an unknown release field must be rejected");
        assert!(error.to_string().contains("unexpected_release_option"));
    }

    #[test]
    fn derived_validation_rejects_invalid_release_fields() {
        let mut deployment = accepted_deployment();
        deployment.release.runtime_revision.clear();

        let error = deployment
            .validate()
            .expect_err("empty release identifiers must be rejected");

        let DeploymentError::Schema(errors) = error else {
            panic!("an empty identifier is a schema error, not {error}");
        };
        assert!(errors.to_string().contains("runtime_revision"));
    }

    #[test]
    fn service_url_requires_http_or_https() {
        let mut deployment = accepted_deployment();
        deployment.service_url = "ftp://runtime.internal/model".to_owned();

        assert_eq!(deployment.validate(), Err(DeploymentError::ServiceUrl));
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
        assert_eq!(status.active_requests, None);

        let limited = |active_requests: u32| {
            serde_json::from_value::<DeploymentRuntimeStatus>(serde_json::json!({
                "schema_version": 1,
                "deployment_id": Uuid::nil(),
                "runtime_revision": "vllm-revision",
                "received_at": "2026-08-27T12:00:00Z",
                "healthy": true,
                "accepting_requests": true,
                "active_requests": active_requests,
                "reason_code": null
            }))
            .unwrap()
        };
        assert_eq!(limited(16).active_requests, Some(16));
        assert!(limited(16).validate().is_ok());
        assert!(limited(0).validate().is_err());
        assert!(limited(4_097).validate().is_err());

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

    #[test]
    fn a_status_is_fresh_within_its_age_and_the_clock_skew_bound() {
        let now = "2026-08-27T12:00:00Z".parse::<DateTime<Utc>>().unwrap();
        let maximum_age = TimeDelta::seconds(30);

        for (offset, fresh) in [(-30, true), (-31, false), (5, true), (6, false)] {
            let status = DeploymentRuntimeStatus {
                schema_version: 1,
                deployment_id: Uuid::nil(),
                runtime_revision: "vllm-revision".to_owned(),
                received_at: now + TimeDelta::seconds(offset),
                healthy: true,
                accepting_requests: true,
                active_requests: None,
                reason_code: None,
            };

            assert_eq!(status.is_fresh_at(now, maximum_age), fresh, "{offset}s");
        }
    }

    /// The heartbeat key is computed independently by the gateway and by the control
    /// plane, so every combination of the optional release fields is pinned here and
    /// asserted from both sides. Omitting one silently routes heartbeats to a key the
    /// gateway never reads.
    #[test]
    fn release_digests_match_the_shared_fixture() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../test/fixtures/release-digests.json"))
                .expect("the fixture parses");
        let cases = fixture["cases"].as_array().expect("cases is an array");
        assert_eq!(cases.len(), 25, "all pinned release cases are covered");

        for case in cases {
            let release: ModelDeploymentRelease =
                serde_json::from_value(case["release"].clone()).expect("the release parses");
            let deployment = GatewayModelDeployment {
                release,
                ..accepted_deployment()
            };

            assert_eq!(
                deployment.served_release_digest().expect("a digest"),
                case["digest"].as_str().expect("a digest string"),
                "{}",
                case["name"]
            );
        }
    }
}
