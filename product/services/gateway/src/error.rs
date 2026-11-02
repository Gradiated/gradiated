use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum GatewayError {
    InvalidRequest { param: Option<String> },
    UnsupportedParameter { param: Option<String> },
    ContextLengthExceeded { param: Option<String> },
    PayloadTooLarge,
    InvalidApiKey,
    ProviderKeyRequired,
    WorkspaceArchived,
    OrganizationSuspended,
    ProviderUnavailable,
    ProviderTimeout,
    ProxyOverloaded,
    InsufficientBalance,
    ConcurrencyExceeded,
    SettlementBacklog,
    CapacityExceeded,
    ModelNotFound,
    ModelUnavailable,
    ServingStateUnavailable,
    RuntimeUnavailable,
    FinalizationUnavailable,
}

impl GatewayError {
    pub fn invalid_request(param: Option<&str>) -> Self {
        Self::InvalidRequest {
            param: bounded_param(param),
        }
    }

    pub fn unsupported_parameter(param: &str) -> Self {
        Self::UnsupportedParameter {
            param: bounded_param(Some(param)),
        }
    }

    pub fn context_length_exceeded(param: &str) -> Self {
        Self::ContextLengthExceeded {
            param: bounded_param(Some(param)),
        }
    }

    pub fn status(&self) -> StatusCode {
        match self {
            Self::InvalidRequest { .. }
            | Self::UnsupportedParameter { .. }
            | Self::ContextLengthExceeded { .. } => StatusCode::BAD_REQUEST,
            Self::PayloadTooLarge => StatusCode::PAYLOAD_TOO_LARGE,
            Self::InvalidApiKey | Self::ProviderKeyRequired => StatusCode::UNAUTHORIZED,
            Self::WorkspaceArchived | Self::OrganizationSuspended => StatusCode::FORBIDDEN,
            Self::ProviderUnavailable => StatusCode::BAD_GATEWAY,
            Self::ProviderTimeout => StatusCode::GATEWAY_TIMEOUT,
            Self::ProxyOverloaded => StatusCode::SERVICE_UNAVAILABLE,
            Self::InsufficientBalance => StatusCode::PAYMENT_REQUIRED,
            Self::ConcurrencyExceeded | Self::SettlementBacklog | Self::CapacityExceeded => {
                StatusCode::TOO_MANY_REQUESTS
            }
            Self::ModelNotFound | Self::ModelUnavailable => StatusCode::NOT_FOUND,
            Self::ServingStateUnavailable
            | Self::RuntimeUnavailable
            | Self::FinalizationUnavailable => StatusCode::SERVICE_UNAVAILABLE,
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::InvalidRequest { .. } => "invalid_request",
            Self::UnsupportedParameter { .. } => "unsupported_parameter",
            Self::ContextLengthExceeded { .. } => "context_length_exceeded",
            Self::PayloadTooLarge => "payload_too_large",
            Self::InvalidApiKey => "invalid_api_key",
            Self::ProviderKeyRequired => "provider_key_required",
            Self::WorkspaceArchived => "workspace_archived",
            Self::OrganizationSuspended => "organization_suspended",
            Self::ProviderUnavailable => "provider_unavailable",
            Self::ProviderTimeout => "provider_timeout",
            Self::ProxyOverloaded => "proxy_overloaded",
            Self::InsufficientBalance => "insufficient_balance",
            Self::ConcurrencyExceeded => "concurrency_exceeded",
            Self::SettlementBacklog => "settlement_backlog",
            Self::CapacityExceeded => "capacity_exceeded",
            Self::ModelNotFound => "model_not_found",
            Self::ModelUnavailable => "model_unavailable",
            Self::ServingStateUnavailable => "serving_state_unavailable",
            Self::RuntimeUnavailable => "runtime_unavailable",
            Self::FinalizationUnavailable => "finalization_unavailable",
        }
    }

    pub(crate) fn error_type(&self) -> &'static str {
        match self {
            Self::InvalidApiKey | Self::ProviderKeyRequired => "authentication_error",
            Self::WorkspaceArchived | Self::OrganizationSuspended => "permission_error",
            Self::ConcurrencyExceeded | Self::SettlementBacklog | Self::CapacityExceeded => {
                "rate_limit_error"
            }
            Self::ProviderUnavailable
            | Self::ProviderTimeout
            | Self::ProxyOverloaded
            | Self::ServingStateUnavailable
            | Self::RuntimeUnavailable
            | Self::FinalizationUnavailable => "api_error",
            Self::InvalidRequest { .. }
            | Self::UnsupportedParameter { .. }
            | Self::ContextLengthExceeded { .. }
            | Self::PayloadTooLarge
            | Self::InsufficientBalance
            | Self::ModelNotFound
            | Self::ModelUnavailable => "invalid_request_error",
        }
    }

    pub(crate) fn message(&self) -> &'static str {
        match self {
            Self::InvalidRequest { .. } => "The request is invalid.",
            Self::UnsupportedParameter { .. } => {
                "The requested model does not support this parameter."
            }
            Self::ContextLengthExceeded { .. } => {
                "The requested token limit exceeds the model limit."
            }
            Self::PayloadTooLarge => "The request body is too large.",
            Self::InvalidApiKey => "The API key is invalid.",
            Self::ProviderKeyRequired => {
                "Supply the provider API key and a Gradiated workspace key."
            }
            Self::WorkspaceArchived => "The workspace is archived.",
            Self::OrganizationSuspended => "The organization is suspended.",
            Self::ProviderUnavailable => "The provider connection failed.",
            Self::ProviderTimeout => "The provider request timed out.",
            Self::ProxyOverloaded => "Provider relay is temporarily at capacity.",
            Self::InsufficientBalance => "The prepaid balance is insufficient.",
            Self::ConcurrencyExceeded => {
                "The organization has reached its funded concurrency limit."
            }
            Self::SettlementBacklog => "Generation settlement is temporarily backlogged.",
            Self::CapacityExceeded => "The model is temporarily at capacity.",
            Self::ModelNotFound => "The requested model was not found.",
            Self::ModelUnavailable => "The requested model is unavailable.",
            Self::ServingStateUnavailable => "Required serving state is unavailable.",
            Self::RuntimeUnavailable => "The model runtime is unavailable.",
            Self::FinalizationUnavailable => "Generation finalization is unavailable.",
        }
    }

    pub(crate) fn param(&self) -> Option<&str> {
        match self {
            Self::InvalidRequest { param }
            | Self::UnsupportedParameter { param }
            | Self::ContextLengthExceeded { param } => param.as_deref(),
            Self::ModelNotFound | Self::ModelUnavailable => Some("model"),
            Self::PayloadTooLarge
            | Self::InvalidApiKey
            | Self::ProviderKeyRequired
            | Self::WorkspaceArchived
            | Self::OrganizationSuspended
            | Self::ProviderUnavailable
            | Self::ProviderTimeout
            | Self::ProxyOverloaded
            | Self::InsufficientBalance
            | Self::ConcurrencyExceeded
            | Self::SettlementBacklog
            | Self::CapacityExceeded
            | Self::ServingStateUnavailable
            | Self::RuntimeUnavailable
            | Self::FinalizationUnavailable => None,
        }
    }

    pub(crate) fn envelope(&self) -> ErrorEnvelope<'_> {
        ErrorEnvelope { error: self.body() }
    }

    pub(crate) fn anthropic_envelope(&self) -> AnthropicErrorEnvelope<'_> {
        AnthropicErrorEnvelope {
            kind: "error",
            error: self.body(),
        }
    }

    pub(crate) fn responses_stream_error(&self) -> ResponsesStreamError<'_> {
        ResponsesStreamError {
            kind: "error",
            code: self.code(),
            message: self.message(),
            param: self.param(),
        }
    }

    fn body(&self) -> ErrorBody<'_> {
        ErrorBody {
            message: self.message(),
            error_type: self.error_type(),
            param: self.param(),
            code: self.code(),
        }
    }
}

impl IntoResponse for GatewayError {
    fn into_response(self) -> Response {
        let status = self.status();
        let response = self.envelope();
        (status, Json(response)).into_response()
    }
}

const MAX_PUBLIC_PARAM_BYTES: usize = 100;

fn bounded_param(param: Option<&str>) -> Option<String> {
    param
        .filter(|value| value.len() <= MAX_PUBLIC_PARAM_BYTES)
        .map(ToOwned::to_owned)
}

#[derive(Serialize)]
pub(crate) struct ErrorEnvelope<'a> {
    error: ErrorBody<'a>,
}

#[derive(Serialize)]
pub(crate) struct AnthropicErrorEnvelope<'a> {
    #[serde(rename = "type")]
    kind: &'static str,
    error: ErrorBody<'a>,
}

#[derive(Serialize)]
pub(crate) struct ResponsesStreamError<'a> {
    #[serde(rename = "type")]
    kind: &'static str,
    code: &'a str,
    message: &'a str,
    param: Option<&'a str>,
}

#[derive(Serialize)]
struct ErrorBody<'a> {
    message: &'a str,
    #[serde(rename = "type")]
    error_type: &'a str,
    param: Option<&'a str>,
    code: &'a str,
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use serde_json::json;

    use super::*;

    #[test]
    fn every_variant_has_a_stable_public_classification() {
        let table = [
            (
                GatewayError::invalid_request(Some("messages")),
                StatusCode::BAD_REQUEST,
                "invalid_request",
                "invalid_request_error",
                Some("messages"),
            ),
            (
                GatewayError::unsupported_parameter("temperature"),
                StatusCode::BAD_REQUEST,
                "unsupported_parameter",
                "invalid_request_error",
                Some("temperature"),
            ),
            (
                GatewayError::context_length_exceeded("max_tokens"),
                StatusCode::BAD_REQUEST,
                "context_length_exceeded",
                "invalid_request_error",
                Some("max_tokens"),
            ),
            (
                GatewayError::PayloadTooLarge,
                StatusCode::PAYLOAD_TOO_LARGE,
                "payload_too_large",
                "invalid_request_error",
                None,
            ),
            (
                GatewayError::InvalidApiKey,
                StatusCode::UNAUTHORIZED,
                "invalid_api_key",
                "authentication_error",
                None,
            ),
            (
                GatewayError::ProviderKeyRequired,
                StatusCode::UNAUTHORIZED,
                "provider_key_required",
                "authentication_error",
                None,
            ),
            (
                GatewayError::WorkspaceArchived,
                StatusCode::FORBIDDEN,
                "workspace_archived",
                "permission_error",
                None,
            ),
            (
                GatewayError::OrganizationSuspended,
                StatusCode::FORBIDDEN,
                "organization_suspended",
                "permission_error",
                None,
            ),
            (
                GatewayError::ProviderUnavailable,
                StatusCode::BAD_GATEWAY,
                "provider_unavailable",
                "api_error",
                None,
            ),
            (
                GatewayError::ProviderTimeout,
                StatusCode::GATEWAY_TIMEOUT,
                "provider_timeout",
                "api_error",
                None,
            ),
            (
                GatewayError::ProxyOverloaded,
                StatusCode::SERVICE_UNAVAILABLE,
                "proxy_overloaded",
                "api_error",
                None,
            ),
            (
                GatewayError::InsufficientBalance,
                StatusCode::PAYMENT_REQUIRED,
                "insufficient_balance",
                "invalid_request_error",
                None,
            ),
            (
                GatewayError::ConcurrencyExceeded,
                StatusCode::TOO_MANY_REQUESTS,
                "concurrency_exceeded",
                "rate_limit_error",
                None,
            ),
            (
                GatewayError::SettlementBacklog,
                StatusCode::TOO_MANY_REQUESTS,
                "settlement_backlog",
                "rate_limit_error",
                None,
            ),
            (
                GatewayError::CapacityExceeded,
                StatusCode::TOO_MANY_REQUESTS,
                "capacity_exceeded",
                "rate_limit_error",
                None,
            ),
            (
                GatewayError::ModelNotFound,
                StatusCode::NOT_FOUND,
                "model_not_found",
                "invalid_request_error",
                Some("model"),
            ),
            (
                GatewayError::ModelUnavailable,
                StatusCode::NOT_FOUND,
                "model_unavailable",
                "invalid_request_error",
                Some("model"),
            ),
            (
                GatewayError::ServingStateUnavailable,
                StatusCode::SERVICE_UNAVAILABLE,
                "serving_state_unavailable",
                "api_error",
                None,
            ),
            (
                GatewayError::RuntimeUnavailable,
                StatusCode::SERVICE_UNAVAILABLE,
                "runtime_unavailable",
                "api_error",
                None,
            ),
            (
                GatewayError::FinalizationUnavailable,
                StatusCode::SERVICE_UNAVAILABLE,
                "finalization_unavailable",
                "api_error",
                None,
            ),
        ];

        let mut codes = HashSet::new();
        for (error, status, code, error_type, param) in table {
            assert_eq!(error.status(), status, "{code}");
            assert_eq!(error.code(), code);
            assert_eq!(error.error_type(), error_type, "{code}");
            assert_eq!(error.param(), param, "{code}");
            assert!(codes.insert(code), "{code} is not unique");
        }
    }

    #[test]
    fn a_public_param_is_bounded() {
        let longest = "x".repeat(MAX_PUBLIC_PARAM_BYTES);
        let oversized = "x".repeat(MAX_PUBLIC_PARAM_BYTES + 1);

        assert_eq!(
            GatewayError::unsupported_parameter(&longest).param(),
            Some(longest.as_str())
        );
        assert_eq!(
            GatewayError::unsupported_parameter(&oversized),
            GatewayError::UnsupportedParameter { param: None }
        );
    }

    #[test]
    fn the_openai_envelope_is_exact() {
        let error = GatewayError::unsupported_parameter("temperature");

        assert_eq!(
            serde_json::to_value(error.envelope()).unwrap(),
            json!({
                "error": {
                    "message": "The requested model does not support this parameter.",
                    "type": "invalid_request_error",
                    "param": "temperature",
                    "code": "unsupported_parameter"
                }
            })
        );
    }

    #[test]
    fn the_anthropic_envelope_is_exact() {
        let error = GatewayError::unsupported_parameter("temperature");

        assert_eq!(
            serde_json::to_value(error.anthropic_envelope()).unwrap(),
            json!({
                "type": "error",
                "error": {
                    "message": "The requested model does not support this parameter.",
                    "type": "invalid_request_error",
                    "param": "temperature",
                    "code": "unsupported_parameter"
                }
            })
        );
    }

    #[test]
    fn the_responses_stream_error_is_exact() {
        let error = GatewayError::unsupported_parameter("temperature");

        assert_eq!(
            serde_json::to_value(error.responses_stream_error()).unwrap(),
            json!({
                "type": "error",
                "code": "unsupported_parameter",
                "message": "The requested model does not support this parameter.",
                "param": "temperature"
            })
        );
    }
}
