use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

use crate::{identity::Denial, upstream::UpstreamError};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Protocol {
    Anthropic,
    OpenAi,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProxyError {
    InvalidRequest,
    NotFound,
    PayloadTooLarge,
    RequestTimeout,
    InvalidApiKey,
    WorkspaceArchived,
    OrganizationSuspended,
    IdentityUnavailable,
    Overloaded,
    GatewayUnavailable,
    GatewayTimeout,
    ProviderUnavailable,
    ProviderTimeout,
}

impl ProxyError {
    pub fn status(self) -> StatusCode {
        match self {
            Self::InvalidRequest => StatusCode::BAD_REQUEST,
            Self::NotFound => StatusCode::NOT_FOUND,
            Self::PayloadTooLarge => StatusCode::PAYLOAD_TOO_LARGE,
            Self::RequestTimeout => StatusCode::REQUEST_TIMEOUT,
            Self::InvalidApiKey => StatusCode::UNAUTHORIZED,
            Self::WorkspaceArchived | Self::OrganizationSuspended => StatusCode::FORBIDDEN,
            Self::IdentityUnavailable | Self::Overloaded => StatusCode::SERVICE_UNAVAILABLE,
            Self::GatewayUnavailable | Self::ProviderUnavailable => StatusCode::BAD_GATEWAY,
            Self::GatewayTimeout | Self::ProviderTimeout => StatusCode::GATEWAY_TIMEOUT,
        }
    }

    pub fn code(self) -> &'static str {
        match self {
            Self::InvalidRequest => "invalid_request",
            Self::NotFound => "not_found",
            Self::PayloadTooLarge => "payload_too_large",
            Self::RequestTimeout => "request_timeout",
            Self::InvalidApiKey => "invalid_api_key",
            Self::WorkspaceArchived => "workspace_archived",
            Self::OrganizationSuspended => "organization_suspended",
            Self::IdentityUnavailable => "serving_state_unavailable",
            Self::Overloaded => "proxy_overloaded",
            Self::GatewayUnavailable => "gateway_unavailable",
            Self::GatewayTimeout => "gateway_timeout",
            Self::ProviderUnavailable => "provider_unavailable",
            Self::ProviderTimeout => "provider_timeout",
        }
    }

    fn error_type(self) -> &'static str {
        match self {
            Self::InvalidRequest
            | Self::NotFound
            | Self::PayloadTooLarge
            | Self::RequestTimeout => "invalid_request_error",
            Self::InvalidApiKey => "authentication_error",
            Self::WorkspaceArchived | Self::OrganizationSuspended => "permission_error",
            Self::IdentityUnavailable
            | Self::Overloaded
            | Self::GatewayUnavailable
            | Self::GatewayTimeout
            | Self::ProviderUnavailable
            | Self::ProviderTimeout => "api_error",
        }
    }

    fn message(self) -> &'static str {
        match self {
            Self::InvalidRequest => "The request is invalid.",
            Self::NotFound => "The requested path was not found.",
            Self::PayloadTooLarge => "The request body is too large.",
            Self::RequestTimeout => "The request body did not arrive in time.",
            Self::InvalidApiKey => "The API key is invalid.",
            Self::WorkspaceArchived => "The workspace is archived.",
            Self::OrganizationSuspended => "The organization is suspended.",
            Self::IdentityUnavailable => "Required serving state is unavailable.",
            Self::Overloaded => "The proxy is temporarily at capacity.",
            Self::GatewayUnavailable => "The inference gateway is unavailable.",
            Self::GatewayTimeout => "The inference gateway did not respond in time.",
            Self::ProviderUnavailable => "The provider connection failed.",
            Self::ProviderTimeout => "The provider request timed out.",
        }
    }

    pub fn render(self, protocol: Protocol) -> Response {
        let body = ErrorBody {
            message: self.message(),
            error_type: self.error_type(),
            param: None,
            code: self.code(),
        };

        match protocol {
            Protocol::OpenAi => {
                (self.status(), Json(OpenAiEnvelope { error: body })).into_response()
            }
            Protocol::Anthropic => (
                self.status(),
                Json(AnthropicEnvelope {
                    kind: "error",
                    error: body,
                }),
            )
                .into_response(),
        }
    }

    pub fn from_upstream(error: UpstreamError, gateway: bool) -> Self {
        match (error, gateway) {
            (UpstreamError::Overloaded, _) => Self::Overloaded,
            (UpstreamError::Loop, _) => Self::InvalidRequest,
            (UpstreamError::Unavailable, true) => Self::GatewayUnavailable,
            (UpstreamError::Timeout, true) => Self::GatewayTimeout,
            (UpstreamError::Unavailable, false) => Self::ProviderUnavailable,
            (UpstreamError::Timeout, false) => Self::ProviderTimeout,
        }
    }
}

impl From<Denial> for ProxyError {
    fn from(denial: Denial) -> Self {
        match denial {
            Denial::InvalidApiKey => Self::InvalidApiKey,
            Denial::WorkspaceArchived => Self::WorkspaceArchived,
            Denial::OrganizationSuspended => Self::OrganizationSuspended,
            Denial::Unavailable => Self::IdentityUnavailable,
        }
    }
}

#[derive(Serialize)]
struct ErrorBody {
    message: &'static str,
    #[serde(rename = "type")]
    error_type: &'static str,
    param: Option<&'static str>,
    code: &'static str,
}

#[derive(Serialize)]
struct OpenAiEnvelope {
    error: ErrorBody,
}

#[derive(Serialize)]
struct AnthropicEnvelope {
    #[serde(rename = "type")]
    kind: &'static str,
    error: ErrorBody,
}
