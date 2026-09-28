use std::sync::Mutex;

use async_trait::async_trait;
use chrono::{DateTime, TimeZone, Utc};
use uuid::Uuid;

use crate::{
    domain::{
        BillingMode, GatewayAccount, GatewayCredential, GatewayModel, GatewayWorkspace,
        OrganizationKind, OrganizationStatus,
    },
    serving_state::{ServingState, ServingStateError},
    AdmissionError, AdmissionLease, DeploymentRuntimeStatus, FinalizationError,
    FinalizationOutcome, GatewayConfig, GenerationProperties, RequestMetadata,
};

pub(crate) const API_KEY_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000001);
pub(crate) const ORGANIZATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000002);
pub(crate) const WORKSPACE_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000003);
pub(crate) const GENERATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000004);

pub(crate) struct TestServingState {
    pub(crate) credential: Option<GatewayCredential>,
    pub(crate) workspace: Option<GatewayWorkspace>,
    pub(crate) account: Option<GatewayAccount>,
    pub(crate) model: Option<GatewayModel>,
    pub(crate) statuses: Option<Vec<DeploymentRuntimeStatus>>,
    pub(crate) calls: Mutex<Vec<&'static str>>,
    pub(crate) requested_models: Mutex<Vec<String>>,
    pub(crate) requested_digests: Mutex<Vec<String>>,
}

impl TestServingState {
    pub(crate) fn ready() -> Self {
        Self {
            credential: Some(GatewayCredential {
                api_key_id: API_KEY_ID,
                organization_id: ORGANIZATION_ID,
                workspace_id: WORKSPACE_ID,
                expires_at: None,
                revoked_at: None,
            }),
            workspace: Some(GatewayWorkspace {
                organization_id: ORGANIZATION_ID,
                workspace_id: WORKSPACE_ID,
                archived_at: None,
            }),
            account: Some(GatewayAccount {
                organization_id: ORGANIZATION_ID,
                organization_kind: OrganizationKind::Customer,
                organization_status: OrganizationStatus::Active,
                billing_mode: BillingMode::Prepaid,
                balance: 1,
            }),
            model: Some(model(true)),
            statuses: None,
            calls: Mutex::new(Vec::new()),
            requested_models: Mutex::new(Vec::new()),
            requested_digests: Mutex::new(Vec::new()),
        }
    }

    pub(crate) fn without_models() -> Self {
        let mut state = Self::ready();
        state.model = None;

        state
    }

    pub(crate) fn unknown_credential() -> Self {
        let mut state = Self::ready();
        state.credential = None;

        state
    }

    pub(crate) fn lookups(&self, name: &str) -> usize {
        self.calls
            .lock()
            .unwrap()
            .iter()
            .filter(|call| **call == name)
            .count()
    }

    fn record(&self, call: &'static str) {
        self.calls.lock().unwrap().push(call);
    }
}

#[async_trait]
impl ServingState for TestServingState {
    async fn credential(
        &self,
        digest_hex: &str,
    ) -> Result<Option<GatewayCredential>, ServingStateError> {
        self.record("credential");
        self.requested_digests
            .lock()
            .unwrap()
            .push(digest_hex.to_owned());
        Ok(self.credential.clone())
    }

    async fn workspace(
        &self,
        _workspace_id: Uuid,
    ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
        self.record("workspace");
        Ok(self.workspace.clone())
    }

    async fn account(
        &self,
        _organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        self.record("account");
        Ok(self.account.clone())
    }

    async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
        self.record("model");
        self.requested_models
            .lock()
            .unwrap()
            .push(model_id.to_owned());
        Ok(self.model.clone())
    }

    async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
        self.record("models");
        Ok(self.model.clone().into_iter().collect())
    }

    async fn deployment_statuses(
        &self,
        _release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        if let Some(statuses) = &self.statuses {
            return Ok(statuses.clone());
        }

        Ok(self
            .model
            .as_ref()
            .and_then(|model| model.deployments.first())
            .map(|deployment| DeploymentRuntimeStatus {
                schema_version: 1,
                deployment_id: deployment.id,
                runtime_revision: deployment.release.runtime_revision.clone(),
                received_at: metadata().received_at,
                healthy: true,
                accepting_requests: true,
                reason_code: None,
            })
            .into_iter()
            .collect())
    }

    async fn admit(
        &self,
        _generation_id: Uuid,
        _organization_id: Uuid,
        _received_at: DateTime<Utc>,
        _admitted_at: DateTime<Utc>,
        _config: &GatewayConfig,
    ) -> Result<AdmissionLease, AdmissionError> {
        unreachable!("serving-state fixtures never admit")
    }

    async fn finalize(
        &self,
        _generation_id: Uuid,
        _organization_id: Uuid,
        _properties: &GenerationProperties,
    ) -> Result<FinalizationOutcome, FinalizationError> {
        unreachable!("serving-state fixtures never finalize")
    }
}

pub(crate) fn model(streaming: bool) -> GatewayModel {
    serde_json::from_value(model_record(streaming)).unwrap()
}

pub(crate) fn model_record(streaming: bool) -> serde_json::Value {
    serde_json::json!({
        "id": "model-a",
        "name": "Model A",
        "status": "available",
        "properties": {
            "schema_version": 1,
            "description": "Model A",
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
                "streaming": streaming,
                "supported_parameters": {
                    "temperature": {"type": "range", "min": 0, "max": 2}
                },
                "pricing": [
                    {"type": "completion", "unit": "token", "cost": 200}
                ]
            }],
            "passthrough_parameters": {
                "response_format": {"type": "enum", "values": ["text", "json"]}
            },
            "deprecation_date": null
        },
        "deployments": [{
            "id": "0198c36f-9b6a-7000-8000-000000000005",
            "status": "available",
            "provider": "local",
            "region": "local",
            "fault_domain": "local:runtime-1",
            "service_url": "http://127.0.0.1:30000",
            "release": {
                "schema_version": 1,
                "runtime_revision": "runtime",
                "model_path": "model",
                "model_revision": "model-revision",
                "tokenizer_path": "tokenizer",
                "tokenizer_revision": "tokenizer-revision"
            }
        }]
    })
}

pub(crate) fn metadata() -> RequestMetadata {
    RequestMetadata {
        generation_id: GENERATION_ID,
        received_at: Utc.with_ymd_and_hms(2026, 8, 19, 12, 0, 0).unwrap(),
    }
}
