use std::sync::Arc;

use axum::http::HeaderMap;
use chrono::{DateTime, Utc};
use serde_json::Value;
use uuid::Uuid;

use crate::{
    auth::{
        authenticate_credential, authorize_access, extract_credentials, AuthenticatedIdentity,
        Provider, ProviderCredential,
    },
    domain::{BillingMode, ModelStatus},
    generation::CapturedPricing,
    healthy_deployment_count,
    protocol::Protocol,
    relay::{parse_target, RelayRoute},
    serving_state::{ServingState, ServingStateError},
    CatalogModel, GatewayError, GatewayModel, GatewayModelDeployment, InferenceRequest,
};

/// A runtime scheduling hint that only internal callers may set.
const RUNTIME_PRIORITY_HEADER: &str = "x-vllm-priority";

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestMetadata {
    pub generation_id: Uuid,
    pub received_at: DateTime<Utc>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct QualifiedRequest {
    pub metadata: RequestMetadata,
    pub identity: AuthenticatedIdentity,
    pub deployment: GatewayModelDeployment,
    /// Every deployment of the model, from which routing picks the one to use.
    pub model_deployments: Vec<GatewayModelDeployment>,
    pub served_release_digest: String,
    pub max_context_tokens: u64,
    pub max_prompt_tokens: u64,
    pub effective_output_tokens: u64,
    pub pricing: CapturedPricing,
    pub request: InferenceRequest,
}

/// The selected execution path for one generation. Each arm carries everything
/// the path needs, so nothing downstream repeats authorization or model loading.
pub enum RequestRoute<'a> {
    Hosted {
        // Boxed so a hosted model projection does not enlarge every classification.
        hosted: Box<HostedRequest>,
        request: Value,
    },
    Relay {
        route: RelayRoute,
        identity: AuthenticatedIdentity,
        credential: ProviderCredential<'a>,
    },
}

/// An authorized identity and the validated model that will serve it.
pub struct HostedRequest {
    identity: AuthenticatedIdentity,
    model: GatewayModel,
}

pub struct AuthorizedRequest<'a> {
    identity: AuthenticatedIdentity,
    provider: Option<ProviderCredential<'a>>,
    billing_mode: BillingMode,
    balance: i64,
}

impl<'a> AuthorizedRequest<'a> {
    pub fn carries_provider_credential(&self) -> bool {
        self.provider.is_some()
    }

    pub fn into_hosted_identity(self) -> Result<AuthenticatedIdentity, GatewayError> {
        if self.billing_mode == BillingMode::Prepaid && self.balance <= 0 {
            return Err(GatewayError::InsufficientBalance);
        }

        Ok(self.identity)
    }

    pub fn into_provider_request(
        self,
        expected_provider: Provider,
    ) -> Result<(AuthenticatedIdentity, ProviderCredential<'a>), GatewayError> {
        let credential = self.provider.ok_or(GatewayError::ProviderKeyRequired)?;

        if credential.provider != expected_provider {
            return Err(GatewayError::InvalidApiKey);
        }

        Ok((self.identity, credential))
    }
}

#[derive(Clone)]
pub struct RequestCoordinator {
    serving_state: Arc<dyn ServingState>,
}

impl RequestCoordinator {
    pub fn new(serving_state: Arc<dyn ServingState>) -> Self {
        Self { serving_state }
    }

    /// Completes a hosted request that `classify` already authorized and resolved.
    /// It performs no state lookup of its own.
    pub fn qualify(
        &self,
        metadata: RequestMetadata,
        headers: &HeaderMap,
        hosted: HostedRequest,
        body: &[u8],
        kind: crate::RequestKind,
    ) -> Result<QualifiedRequest, GatewayError> {
        let mut request = InferenceRequest::parse_kind(body, kind)?;
        if request.session_id.is_none() {
            request.session_id = session_header(headers)?;
        }
        request.model.make_ascii_lowercase();
        if let Some(decision) = &mut request.decision {
            decision.model = request.model.clone();
        }
        if request.model != hosted.model.id {
            return Err(GatewayError::ServingStateUnavailable);
        }

        qualify_model_request(metadata, hosted.identity, request, hosted.model)
    }

    pub async fn list_models(
        &self,
        headers: &HeaderMap,
        requested_at: DateTime<Utc>,
    ) -> Result<Vec<CatalogModel>, GatewayError> {
        self.authorize_request(headers, requested_at)
            .await?
            .into_hosted_identity()?;

        let models = self
            .serving_state
            .models()
            .await
            .map_err(state_unavailable("catalog_read"))?;
        let mut catalog = Vec::with_capacity(models.len());
        for model in models {
            let release_digest = model
                .first_available_deployment()
                .ok()
                .flatten()
                .and_then(|deployment| deployment.served_release_digest().ok());
            let statuses = match release_digest {
                Some(digest) => self
                    .serving_state
                    .deployment_statuses(&digest)
                    .await
                    .map_err(state_unavailable("deployment_status_read"))?,
                None => Vec::new(),
            };
            catalog.push(CatalogModel {
                healthy_deployments: healthy_deployment_count(
                    &model.deployments,
                    &statuses,
                    requested_at,
                ),
                model,
            });
        }

        Ok(catalog)
    }

    /// Decides between hosted serving and customer-key relay before any hosted
    /// admission or translation. Local names always resolve first, so an unknown
    /// task or private version never reaches a provider.
    pub async fn classify<'a>(
        &self,
        headers: &'a HeaderMap,
        body: &[u8],
        received_at: DateTime<Utc>,
        protocol: Protocol,
        relay: Option<RelayRoute>,
    ) -> Result<RequestRoute<'a>, GatewayError> {
        // A malformed or unsupported request is a local error on every route, so it
        // is rejected before identity, as the hosted translation rejected it before.
        if headers.contains_key(RUNTIME_PRIORITY_HEADER) {
            return Err(GatewayError::invalid_request(Some("priority")));
        }

        let target = parse_target(body)?;
        protocol.validate_request(&target.request)?;

        let authorized = self.authorize_request(headers, received_at).await?;

        // Hosted names match without regard to case; a relayed body keeps the
        // caller's own spelling because its bytes are never rewritten.
        let mut hosted_id = target.model;
        hosted_id.make_ascii_lowercase();
        let hosted = self
            .serving_state
            .model(&hosted_id)
            .await
            .map_err(state_unavailable("model_read"))?;

        if let Some(model) = hosted {
            return Ok(RequestRoute::Hosted {
                hosted: Box::new(HostedRequest {
                    identity: authorized.into_hosted_identity()?,
                    model: validate_hosted_model(model, &hosted_id)?,
                }),
                request: target.request,
            });
        }

        // The provider is authoritative for its own model names. Without a relay
        // route or its key there is nothing to ask, so the name stays a local error.
        let Some(route) = relay.filter(|_| authorized.carries_provider_credential()) else {
            return Err(GatewayError::ModelNotFound);
        };
        let (identity, credential) = authorized.into_provider_request(route.provider())?;

        Ok(RequestRoute::Relay {
            route,
            identity,
            credential,
        })
    }

    pub async fn authorize_request<'a>(
        &self,
        headers: &'a HeaderMap,
        received_at: DateTime<Utc>,
    ) -> Result<AuthorizedRequest<'a>, GatewayError> {
        let credentials = extract_credentials(headers).map_err(|_| GatewayError::InvalidApiKey)?;
        let digest = credentials.api_key_digest();
        let credential = self
            .serving_state
            .credential(&digest)
            .await
            .map_err(state_unavailable("credential_read"))?
            .ok_or(GatewayError::InvalidApiKey)?;
        let identity = authenticate_credential(credential, received_at)
            .map_err(|_| GatewayError::InvalidApiKey)?;

        tracing::Span::current()
            .record(
                "organization_id",
                tracing::field::display(identity.organization_id),
            )
            .record(
                "workspace_id",
                tracing::field::display(identity.workspace_id),
            )
            .record("api_key_id", tracing::field::display(identity.api_key_id));

        let workspace = self
            .serving_state
            .workspace(identity.workspace_id)
            .await
            .map_err(state_unavailable("workspace_read"))?
            .ok_or(GatewayError::ServingStateUnavailable)?;
        let account = self
            .serving_state
            .account(identity.organization_id)
            .await
            .map_err(state_unavailable("account_read"))?
            .ok_or(GatewayError::ServingStateUnavailable)?;
        let identity = authorize_access(identity, &workspace, &account)?;

        Ok(AuthorizedRequest {
            identity,
            provider: credentials.provider,
            billing_mode: account.billing_mode,
            balance: account.balance,
        })
    }
}

/// Logs why a serving-state read failed. The public error carries no cause,
/// and the diagnostic code never contains record data.
fn state_unavailable(phase: &'static str) -> impl FnOnce(ServingStateError) -> GatewayError {
    move |error| {
        crate::diagnostics::limited_warn!(
            phase,
            error_code = error.diagnostic_code(),
            "serving state read failed"
        );
        GatewayError::ServingStateUnavailable
    }
}

/// A record that disagrees with its own key, or that cannot serve, is not a
/// missing model: it is inconsistent serving state.
fn validate_hosted_model(
    model: GatewayModel,
    requested_model: &str,
) -> Result<GatewayModel, GatewayError> {
    if model.id != requested_model {
        return Err(GatewayError::ServingStateUnavailable);
    }

    model
        .properties
        .validate_for_serving()
        .map_err(|_| GatewayError::ServingStateUnavailable)?;
    if model.status != ModelStatus::Available {
        return Err(GatewayError::ModelUnavailable);
    }

    Ok(model)
}

fn session_header(headers: &HeaderMap) -> Result<Option<String>, GatewayError> {
    for name in ["x-gradiated-session-id", "x-session-id"] {
        if let Some(value) = headers.get(name) {
            let value = value
                .to_str()
                .map_err(|_| GatewayError::invalid_request(Some("session_id")))?;
            if value.is_empty() || value.len() > 256 {
                return Err(GatewayError::invalid_request(Some("session_id")));
            }
            return Ok(Some(value.to_owned()));
        }
    }

    Ok(None)
}

fn qualify_model_request(
    metadata: RequestMetadata,
    identity: AuthenticatedIdentity,
    mut request: InferenceRequest,
    model: GatewayModel,
) -> Result<QualifiedRequest, GatewayError> {
    let deployment = model
        .first_available_deployment()
        .map_err(|_| GatewayError::ServingStateUnavailable)?
        .ok_or(GatewayError::ModelUnavailable)?
        .clone();
    let output = model.properties.text_output();

    if request.decision.is_some() != deployment.release.is_system_one() {
        return Err(GatewayError::unsupported_parameter("model"));
    }
    if request.stream && !output.streaming {
        return Err(GatewayError::unsupported_parameter("stream"));
    }

    // Parameters the model declares must hold accepted values. Parameters it does
    // not declare are removed before dispatch.
    for (name, value) in &request.parameters {
        if model
            .properties
            .parameter(name)
            .is_some_and(|descriptor| !descriptor.accepts(value))
        {
            return Err(GatewayError::invalid_request(Some(name)));
        }
    }
    request
        .parameters
        .retain(|name, _| model.properties.parameter(name).is_some());

    let effective_output_tokens = if request.decision.is_some() {
        0
    } else {
        match request.output_token_limit() {
            Some(limit) if limit.value() > output.max_length.value => {
                return Err(GatewayError::context_length_exceeded(
                    limit.parameter_name(),
                ))
            }
            Some(limit) => limit.value(),
            None => output.default_length.value,
        }
    };

    let served_release_digest = deployment
        .served_release_digest()
        .map_err(|_| GatewayError::ServingStateUnavailable)?;
    let input = model.properties.text_input();
    let pricing =
        CapturedPricing::for_service_tier(&input.pricing, &output.pricing, request.service_tier)
            .map_err(|_| GatewayError::ServingStateUnavailable)?;

    Ok(QualifiedRequest {
        metadata,
        identity,
        deployment,
        model_deployments: model.deployments,
        served_release_digest,
        max_context_tokens: input.supported_inputs.max_context_length.value,
        max_prompt_tokens: input.supported_inputs.max_prompt_length.value,
        effective_output_tokens,
        pricing,
        request,
    })
}

#[cfg(test)]
mod tests {
    use axum::http::{header::AUTHORIZATION, HeaderValue};

    use super::*;
    use crate::domain::OrganizationStatus;
    use crate::test_support::ORGANIZATION_ID;
    pub(super) use crate::test_support::{metadata, model, TestServingState};

    /// Runs the production pipeline: classify, then qualify what it resolved.
    pub(super) async fn qualify(
        coordinator: &RequestCoordinator,
        headers: &HeaderMap,
        body: &[u8],
    ) -> Result<QualifiedRequest, GatewayError> {
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

        coordinator.qualify(metadata(), headers, *hosted, body, crate::RequestKind::Chat)
    }

    /// As `qualify`, for a body the native decision protocol owns.
    pub(super) async fn qualify_decision(
        coordinator: &RequestCoordinator,
        headers: &HeaderMap,
        body: &[u8],
    ) -> Result<QualifiedRequest, GatewayError> {
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

        coordinator.qualify(
            metadata(),
            headers,
            *hosted,
            body,
            crate::RequestKind::SystemOne,
        )
    }

    fn headers() -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(AUTHORIZATION, HeaderValue::from_static("Bearer grad_test"));
        headers
    }

    #[tokio::test]
    async fn qualifies_the_complete_pre_admission_request() {
        let state = Arc::new(TestServingState::ready());
        let coordinator = RequestCoordinator::new(state.clone());
        let request = qualify(
            &coordinator,
            &headers(),
            br#"{
                    "model":"model-a",
                    "messages":[{"role":"user","content":"hello"}],
                    "service_tier":"fast",
                    "temperature":0.5,
                    "response_format":"json"
                }"#,
        )
        .await
        .unwrap();

        assert_eq!(request.effective_output_tokens, 1_024);
        assert_eq!(request.max_prompt_tokens, 7_168);
        assert_eq!(request.max_context_tokens, 8_192);
        assert_eq!(request.identity.organization_id, ORGANIZATION_ID);
        assert_eq!(request.request.parameters["temperature"], 0.5);
        assert_eq!(request.pricing.prompt(), 150);
        assert_eq!(request.pricing.cached_prompt(), 75);
        assert_eq!(request.pricing.completion(), 300);
        assert!(request.served_release_digest.starts_with("sha256:"));
        assert_eq!(
            *state.calls.lock().unwrap(),
            ["credential", "workspace", "account", "model"]
        );
    }

    #[tokio::test]
    async fn canonicalizes_model_ids_before_lookup_and_dispatch() {
        let state = Arc::new(TestServingState::ready());
        let request = qualify(
            &RequestCoordinator::new(state.clone()),
            &headers(),
            br#"{"model":"MODEL-A","messages":[{}]}"#,
        )
        .await
        .unwrap();

        assert_eq!(request.request.model, "model-a");
        let upstream_body = request
            .request
            .into_upstream_body_for_model(request.effective_output_tokens, None);
        assert_eq!(upstream_body["model"], "model-a");
        assert_eq!(*state.requested_models.lock().unwrap(), ["model-a"]);
    }

    #[tokio::test]
    async fn system_one_uses_existing_auth_and_rejects_cross_protocol_models() {
        let body = br#"{"model":"MODEL-A","state":"charged twice","questions":{"billing":{"type":"noul","instructions":"Duplicate charge?"}}}"#;
        let mut state = TestServingState::ready();
        state.model.as_mut().unwrap().deployments[0]
            .release
            .protocol = Some(crate::RuntimeProtocol::SystemOne);
        let state = Arc::new(state);
        let coordinator = RequestCoordinator::new(state.clone());

        let qualified = qualify_decision(&coordinator, &headers(), body)
            .await
            .unwrap();
        assert_eq!(qualified.effective_output_tokens, 0);
        assert_eq!(qualified.request.model, "model-a");
        assert_eq!(qualified.request.decision.unwrap().model, "model-a");
        // Identity is resolved by the same pipeline every other protocol uses.
        assert_eq!(
            *state.calls.lock().unwrap(),
            ["credential", "workspace", "account", "model"]
        );

        // Neither protocol may be served by the other's deployment.
        assert!(qualify(
            &coordinator,
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#
        )
        .await
        .is_err());
        let chat = RequestCoordinator::new(Arc::new(TestServingState::ready()));
        assert!(qualify_decision(&chat, &headers(), body).await.is_err());

        assert_eq!(
            qualify_decision(&coordinator, &HeaderMap::new(), body)
                .await
                .unwrap_err(),
            GatewayError::InvalidApiKey
        );
    }

    #[tokio::test]
    async fn model_listing_reuses_the_complete_access_pipeline_without_admission() {
        let state = Arc::new(TestServingState::ready());
        let models = RequestCoordinator::new(state.clone())
            .list_models(&headers(), metadata().received_at)
            .await
            .unwrap();

        assert_eq!(models.len(), 1);
        assert_eq!(models[0].model.id, "model-a");
        assert_eq!(
            *state.calls.lock().unwrap(),
            ["credential", "workspace", "account", "models"]
        );
    }

    #[tokio::test]
    async fn stops_at_the_first_failed_access_stage() {
        let mut missing_credential = TestServingState::ready();
        missing_credential.credential = None;
        let missing_credential = Arc::new(missing_credential);
        let result = qualify(
            &RequestCoordinator::new(missing_credential.clone()),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::InvalidApiKey));
        assert_eq!(*missing_credential.calls.lock().unwrap(), ["credential"]);

        let mut empty_balance = TestServingState::ready();
        empty_balance.account.as_mut().unwrap().balance = 0;
        let empty_balance = Arc::new(empty_balance);
        let result = qualify(
            &RequestCoordinator::new(empty_balance.clone()),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::InsufficientBalance));
        assert_eq!(
            *empty_balance.calls.lock().unwrap(),
            ["credential", "workspace", "account", "model"],
            "the model decides whether a request is hosted, so it resolves before              the hosted balance gate"
        );
    }

    #[tokio::test]
    async fn invoiced_accounts_are_not_gated_by_their_balance() {
        let mut state = TestServingState::ready();
        let account = state.account.as_mut().unwrap();
        account.billing_mode = BillingMode::Invoiced;
        account.balance = -10_000;

        let request = qualify(
            &RequestCoordinator::new(Arc::new(state)),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await
        .unwrap();
        assert_eq!(request.effective_output_tokens, 1_024);
    }

    #[tokio::test]
    async fn fails_closed_for_inconsistent_or_inactive_access_state() {
        let mut archived = TestServingState::ready();
        archived.workspace.as_mut().unwrap().archived_at = Some(metadata().received_at);
        let archived = Arc::new(archived);
        let result = qualify(
            &RequestCoordinator::new(archived.clone()),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        // A permanent denial is not a dependency failure, so it is not retryable.
        assert_eq!(result, Err(GatewayError::WorkspaceArchived));
        assert_eq!(
            *archived.calls.lock().unwrap(),
            ["credential", "workspace", "account"]
        );

        let mut suspended = TestServingState::ready();
        suspended.account.as_mut().unwrap().organization_status = OrganizationStatus::Suspended;
        let result = qualify(
            &RequestCoordinator::new(Arc::new(suspended)),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::OrganizationSuspended));

        let mut mismatched = TestServingState::ready();
        mismatched.workspace.as_mut().unwrap().organization_id = Uuid::from_u128(99);
        let result = qualify(
            &RequestCoordinator::new(Arc::new(mismatched)),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::ServingStateUnavailable));
    }

    #[tokio::test]
    async fn request_and_model_failures_remain_pre_admission() {
        let priority_override = Arc::new(TestServingState::ready());
        let mut override_headers = headers();
        override_headers.insert("x-vllm-priority", HeaderValue::from_static("-100"));
        let result = qualify(
            &RequestCoordinator::new(priority_override.clone()),
            &override_headers,
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::invalid_request(Some("priority"))));
        assert!(
            priority_override.calls.lock().unwrap().is_empty(),
            "a header the caller must not send is refused before any state lookup"
        );

        let malformed = Arc::new(TestServingState::ready());
        let result = qualify(
            &RequestCoordinator::new(malformed.clone()),
            &headers(),
            br#"{"model":"model-a"}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::invalid_request(None)));
        assert_eq!(
            *malformed.calls.lock().unwrap(),
            ["credential", "workspace", "account", "model"],
            "classification needs only the target, so the rest of the request shape \
             is checked after the model resolves"
        );

        let mut missing = TestServingState::ready();
        missing.model = None;
        let result = qualify(
            &RequestCoordinator::new(Arc::new(missing)),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::ModelNotFound));

        let mut unavailable = TestServingState::ready();
        unavailable.model.as_mut().unwrap().status = ModelStatus::Unavailable;
        let result = qualify(
            &RequestCoordinator::new(Arc::new(unavailable)),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::ModelUnavailable));

        let mut missing_route = TestServingState::ready();
        missing_route.model.as_mut().unwrap().deployments.clear();
        let result = qualify(
            &RequestCoordinator::new(Arc::new(missing_route)),
            &headers(),
            br#"{"model":"model-a","messages":[{}]}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::ServingStateUnavailable));
    }

    #[tokio::test]
    async fn ignores_unadvertised_model_parameters() {
        let request = qualify(
            &RequestCoordinator::new(Arc::new(TestServingState::ready())),
            &headers(),
            br#"{
                    "model":"model-a",
                    "messages":[{}],
                    "seed":7,
                    "tools":[{"type":"function"}]
                }"#,
        )
        .await
        .unwrap();

        assert!(!request.request.parameters.contains_key("seed"));
        assert!(!request.request.parameters.contains_key("tools"));
    }

    #[tokio::test]
    async fn rejects_invalid_supported_model_parameters() {
        for (body, expected) in [
            (
                br#"{"model":"model-a","messages":[{}],"temperature":3}"#.as_slice(),
                GatewayError::invalid_request(Some("temperature")),
            ),
            (
                br#"{"model":"model-a","messages":[{}],"max_tokens":4097}"#.as_slice(),
                GatewayError::context_length_exceeded("max_tokens"),
            ),
        ] {
            let result = qualify(
                &RequestCoordinator::new(Arc::new(TestServingState::ready())),
                &headers(),
                body,
            )
            .await;
            assert_eq!(result, Err(expected));
        }

        let mut state = TestServingState::ready();
        state.model = Some(model(false));
        let result = qualify(
            &RequestCoordinator::new(Arc::new(state)),
            &headers(),
            br#"{"model":"model-a","messages":[{}],"stream":true}"#,
        )
        .await;
        assert_eq!(result, Err(GatewayError::unsupported_parameter("stream")));
    }
}

#[cfg(test)]
#[path = "coordinator_auth_tests.rs"]
mod authorization_tests;

#[cfg(test)]
#[path = "coordinator_route_tests.rs"]
mod route_tests;
