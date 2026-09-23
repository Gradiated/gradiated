use async_trait::async_trait;
use axum::http::{HeaderMap, HeaderName};

use super::*;
use crate::domain::{GatewayAccount, GatewayCredential, GatewayWorkspace};
use crate::test_support::{metadata, TestServingState};
use crate::{
    AdmissionError, AdmissionLease, DeploymentRuntimeStatus, FinalizationError,
    FinalizationOutcome, GatewayConfig, GenerationProperties,
};

pub(super) const WORKSPACE_KEY: [(&str, &str); 1] = [("authorization", "Bearer grad_test")];
pub(super) const PROVIDER_KEYS: [(&str, &str); 2] = [
    ("x-gradiated-api-key", "grad_test"),
    ("x-api-key", "sk-ant-example"),
];

pub(super) const CHAT_BODY: &[u8] = br#"{"model":"model-a","messages":[{}]}"#;
pub(super) const FRONTIER_BODY: &[u8] = br#"{"model":"claude-sonnet-5","max_tokens":16}"#;

pub(super) type StateChange = fn(&mut TestServingState);

pub(super) fn headers(values: &[(&'static str, &str)]) -> HeaderMap {
    let mut headers = HeaderMap::new();
    for (name, value) in values {
        headers.append(HeaderName::from_static(name), value.parse().unwrap());
    }

    headers
}

pub(super) async fn qualify(
    state: Arc<dyn ServingState>,
    headers: &HeaderMap,
    body: &[u8],
    kind: RequestKind,
) -> Result<QualifiedRequest, GatewayError> {
    let coordinator = RequestCoordinator::new(state);
    let classified = coordinator
        .classify(
            headers,
            body,
            metadata().received_at,
            Protocol::OpenAiChat,
            None,
        )
        .await?;
    let RequestRoute::Hosted { hosted, .. } = classified else {
        panic!("no relay route was offered");
    };

    coordinator.qualify(metadata(), headers, *hosted, body, kind)
}

pub(super) async fn qualify_chat(
    state: Arc<dyn ServingState>,
    body: &[u8],
) -> Result<QualifiedRequest, GatewayError> {
    qualify(state, &headers(&WORKSPACE_KEY), body, RequestKind::Chat).await
}

pub(super) async fn classify_messages<'a>(
    state: Arc<dyn ServingState>,
    headers: &'a HeaderMap,
    body: &[u8],
) -> Result<RequestRoute<'a>, GatewayError> {
    RequestCoordinator::new(state)
        .classify(
            headers,
            body,
            metadata().received_at,
            Protocol::AnthropicMessages,
            Some(RelayRoute::AnthropicMessages),
        )
        .await
}

pub(super) async fn list_models(
    state: Arc<dyn ServingState>,
) -> Result<Vec<CatalogModel>, GatewayError> {
    RequestCoordinator::new(state)
        .list_models(&headers(&WORKSPACE_KEY), metadata().received_at)
        .await
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(super) enum StateRead {
    Credential,
    Workspace,
    Account,
    Model,
    Models,
    DeploymentStatuses,
}

/// Delegates to `TestServingState`, which does not record status reads, so this
/// wrapper records them before failing the one read named by `fail`.
pub(super) struct FailingState {
    pub(super) inner: TestServingState,
    fail: StateRead,
}

impl FailingState {
    pub(super) fn new(inner: TestServingState, fail: StateRead) -> Self {
        Self { inner, fail }
    }

    fn read(&self, read: StateRead) -> Result<(), ServingStateError> {
        if self.fail == read {
            return Err(ServingStateError::MalformedDigest);
        }

        Ok(())
    }
}

#[async_trait]
impl ServingState for FailingState {
    async fn credential(
        &self,
        digest_hex: &str,
    ) -> Result<Option<GatewayCredential>, ServingStateError> {
        self.read(StateRead::Credential)?;
        self.inner.credential(digest_hex).await
    }

    async fn workspace(
        &self,
        workspace_id: Uuid,
    ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
        self.read(StateRead::Workspace)?;
        self.inner.workspace(workspace_id).await
    }

    async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<GatewayAccount>, ServingStateError> {
        self.read(StateRead::Account)?;
        self.inner.account(organization_id).await
    }

    async fn model(&self, model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
        self.read(StateRead::Model)?;
        self.inner.model(model_id).await
    }

    async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
        self.read(StateRead::Models)?;
        self.inner.models().await
    }

    async fn deployment_statuses(
        &self,
        release_digest: &str,
    ) -> Result<Vec<DeploymentRuntimeStatus>, ServingStateError> {
        self.inner.calls.lock().unwrap().push("deployment_statuses");
        self.read(StateRead::DeploymentStatuses)?;
        self.inner.deployment_statuses(release_digest).await
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
