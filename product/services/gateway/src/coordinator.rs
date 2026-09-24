use std::sync::Arc;

use axum::http::HeaderMap;
use chrono::{DateTime, Utc};
use serde_json::Value;
use uuid::Uuid;

use crate::{
    auth::{
        authenticate_credential, authorize_access, extract_api_key, AccessError,
        AuthenticatedIdentity,
    },
    generation::{CapturedPricing, CapturedPricingError},
    healthy_deployment_count,
    model::{ModelStatus, ServingDeployment, ServingDeploymentError, TextOutputModality},
    protocol::Protocol,
    request::parse_target,
    serving_state::{ServingState, ServingStateError},
    CatalogModel, GatewayError, GatewayModel, GatewayModelDeployment, InferenceRequest,
    RequestKind,
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
    pub model_deployments: Vec<GatewayModelDeployment>,
    pub served_release_digest: String,
    pub max_context_tokens: u64,
    pub max_prompt_tokens: u64,
    pub effective_output_tokens: u64,
    pub pricing: CapturedPricing,
    pub request: InferenceRequest,
}

pub struct ClassifiedRequest {
    pub hosted: HostedRequest,
    pub request: Value,
}

pub struct HostedRequest {
    identity: AuthenticatedIdentity,
    model: GatewayModel,
}

impl HostedRequest {
    fn qualify(
        self,
        metadata: RequestMetadata,
        headers: &HeaderMap,
        body: &[u8],
        kind: RequestKind,
    ) -> Result<QualifiedRequest, GatewayError> {
        let Self { identity, model } = self;

        let mut request = InferenceRequest::parse_kind(body, kind)?;
        request.model.clone_from(&model.id);
        if let Some(decision) = &mut request.decision {
            decision.model.clone_from(&model.id);
        }

        if request.session_id.is_none() {
            request.session_id = session_header(headers)?;
        }

        let ServingDeployment {
            deployment,
            release_digest,
        } = model
            .serving_deployment()
            .map_err(|error| inconsistent_state(error.diagnostic_code()))?;
        let deployment = deployment.clone();

        if request.decision.is_some() != deployment.release.is_system_one() {
            return Err(GatewayError::unsupported_parameter("model"));
        }

        let output = model.properties.text_output();
        if request.stream && !output.streaming {
            return Err(GatewayError::unsupported_parameter("stream"));
        }

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

        let effective_output_tokens = effective_output_tokens(&request, output)?;
        let input = model.properties.text_input();
        let pricing = CapturedPricing::for_service_tier(
            &input.pricing,
            &output.pricing,
            request.service_tier,
        )
        .map_err(|error| inconsistent_state(pricing_diagnostic_code(&error)))?;

        Ok(QualifiedRequest {
            metadata,
            identity,
            deployment,
            served_release_digest: release_digest,
            max_context_tokens: input.supported_inputs.max_context_length.value,
            max_prompt_tokens: input.supported_inputs.max_prompt_length.value,
            effective_output_tokens,
            pricing,
            request,
            model_deployments: model.deployments,
        })
    }
}

struct Authorization {
    identity: AuthenticatedIdentity,
    funds_hosted: bool,
}

impl Authorization {
    fn into_hosted_identity(self) -> Result<AuthenticatedIdentity, GatewayError> {
        if !self.funds_hosted {
            return Err(GatewayError::InsufficientBalance);
        }

        Ok(self.identity)
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

    pub fn qualify(
        &self,
        metadata: RequestMetadata,
        headers: &HeaderMap,
        hosted: HostedRequest,
        body: &[u8],
        kind: RequestKind,
    ) -> Result<QualifiedRequest, GatewayError> {
        hosted.qualify(metadata, headers, body, kind)
    }

    pub async fn list_models(
        &self,
        headers: &HeaderMap,
        requested_at: DateTime<Utc>,
    ) -> Result<Vec<CatalogModel>, GatewayError> {
        self.authorize(headers, requested_at)
            .await?
            .into_hosted_identity()?;

        let models = self
            .serving_state
            .models()
            .await
            .map_err(state_unavailable("catalog_read"))?;

        let mut catalog = Vec::with_capacity(models.len());
        for model in models {
            let statuses = match listed_release_digest(&model) {
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

    pub async fn classify(
        &self,
        headers: &HeaderMap,
        body: &[u8],
        received_at: DateTime<Utc>,
        protocol: Protocol,
    ) -> Result<ClassifiedRequest, GatewayError> {
        // A malformed or unsupported request is a local error on every route, so it
        // is rejected before identity.
        if headers.contains_key(RUNTIME_PRIORITY_HEADER) {
            return Err(GatewayError::invalid_request(Some("priority")));
        }

        let target = parse_target(body)?;
        protocol.validate_request(&target.request)?;

        let authorization = self.authorize(headers, received_at).await?;

        let mut model_id = target.model;
        model_id.make_ascii_lowercase();
        let model = self
            .serving_state
            .model(&model_id)
            .await
            .map_err(state_unavailable("model_read"))?
            .ok_or(GatewayError::ModelNotFound)?;
        let identity = authorization.into_hosted_identity()?;

        if model.status != ModelStatus::Available {
            return Err(GatewayError::ModelUnavailable);
        }

        Ok(ClassifiedRequest {
            hosted: HostedRequest { identity, model },
            request: target.request,
        })
    }

    async fn authorize(
        &self,
        headers: &HeaderMap,
        received_at: DateTime<Utc>,
    ) -> Result<Authorization, GatewayError> {
        let digest = extract_api_key(headers)?.digest();
        let credential = self
            .serving_state
            .credential(&digest)
            .await
            .map_err(state_unavailable("credential_read"))?
            .ok_or(GatewayError::InvalidApiKey)?;
        let identity = authenticate_credential(credential, received_at)?;

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
            .ok_or_else(|| inconsistent_state("workspace_missing"))?;
        let account = self
            .serving_state
            .account(identity.organization_id)
            .await
            .map_err(state_unavailable("account_read"))?
            .ok_or_else(|| inconsistent_state("account_missing"))?;
        let identity =
            authorize_access(identity, &workspace, &account).map_err(|error| match error {
                AccessError::InconsistentServingState => inconsistent_state("tenant_mismatch"),
                error => error.into(),
            })?;

        Ok(Authorization {
            identity,
            funds_hosted: account.funds_hosted_requests(),
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

fn inconsistent_state(code: &'static str) -> GatewayError {
    warn_inconsistent_state(code);

    GatewayError::ServingStateUnavailable
}

fn pricing_diagnostic_code(error: &CapturedPricingError) -> &'static str {
    match error {
        CapturedPricingError::DuplicateComponent => "pricing_duplicate_component",
        CapturedPricingError::MissingRequiredComponent => "pricing_missing_component",
        CapturedPricingError::UnsafeInteger => "pricing_unsafe_integer",
    }
}

fn warn_inconsistent_state(code: &'static str) {
    crate::diagnostics::limited_warn!(error_code = code, "serving state is inconsistent");
}

/// A model without an available deployment is listed as not ready. An invalid
/// one is listed the same way, but it is a state error, so its cause is logged.
fn listed_release_digest(model: &GatewayModel) -> Option<String> {
    if model.status != ModelStatus::Available {
        return None;
    }

    match model.serving_deployment() {
        Ok(serving) => Some(serving.release_digest),
        Err(ServingDeploymentError::Missing) => None,
        Err(error) => {
            warn_inconsistent_state(error.diagnostic_code());
            None
        }
    }
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

fn effective_output_tokens(
    request: &InferenceRequest,
    output: &TextOutputModality,
) -> Result<u64, GatewayError> {
    if request.decision.is_some() {
        return Ok(0);
    }

    match request.output_token_limit() {
        Some(limit) if limit.value() > output.max_length.value => Err(
            GatewayError::context_length_exceeded(limit.parameter_name()),
        ),
        Some(limit) => Ok(limit.value()),
        None => Ok(output.default_length.value),
    }
}

#[cfg(test)]
#[path = "coordinator_test_support.rs"]
mod support;

#[cfg(test)]
#[path = "coordinator_qualify_tests.rs"]
mod qualify_tests;

#[cfg(test)]
#[path = "coordinator_listing_tests.rs"]
mod listing_tests;

#[cfg(test)]
#[path = "coordinator_auth_tests.rs"]
mod authorization_tests;

#[cfg(test)]
#[path = "coordinator_route_tests.rs"]
mod route_tests;
