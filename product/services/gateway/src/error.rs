use axum::{
    http::StatusCode,
    response::{sse::Event, IntoResponse, Response},
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
            Self::InvalidApiKey => StatusCode::UNAUTHORIZED,
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

    fn error_type(&self) -> &'static str {
        match self {
            Self::InvalidApiKey => "authentication_error",
            Self::ConcurrencyExceeded | Self::SettlementBacklog | Self::CapacityExceeded => {
                "rate_limit_error"
            }
            Self::ServingStateUnavailable
            | Self::RuntimeUnavailable
            | Self::FinalizationUnavailable => "api_error",
            _ => "invalid_request_error",
        }
    }

    fn message(&self) -> &'static str {
        match self {
            Self::InvalidRequest { .. } => "The request is invalid.",
            Self::UnsupportedParameter { .. } => {
                "The requested model does not support this parameter."
            }
            Self::ContextLengthExceeded { .. } => {
                "The requested token limit exceeds the model limit."
            }
            Self::PayloadTooLarge => "The request body exceeds 8 MB.",
            Self::InvalidApiKey => "The API key is invalid.",
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

    fn param(&self) -> Option<&str> {
        match self {
            Self::InvalidRequest { param }
            | Self::UnsupportedParameter { param }
            | Self::ContextLengthExceeded { param } => param.as_deref(),
            Self::PayloadTooLarge => None,
            Self::ModelNotFound | Self::ModelUnavailable => Some("model"),
            _ => None,
        }
    }

    pub(crate) fn sse_event(&self) -> Event {
        Event::default()
            .json_data(self.envelope())
            .expect("the bounded public error envelope always serializes")
    }

    fn envelope(&self) -> ErrorEnvelope<'_> {
        ErrorEnvelope {
            error: ErrorBody {
                message: self.message(),
                error_type: self.error_type(),
                param: self.param(),
                code: self.code(),
            },
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

fn bounded_param(param: Option<&str>) -> Option<String> {
    param
        .filter(|value| value.len() <= 100)
        .map(ToOwned::to_owned)
}

#[derive(Serialize)]
struct ErrorEnvelope<'a> {
    error: ErrorBody<'a>,
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
    use axum::{body::to_bytes, response::IntoResponse};

    use super::*;

    #[tokio::test]
    async fn public_error_envelope_is_bounded_and_stable() {
        let response = GatewayError::unsupported_parameter("temperature").into_response();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);

        let body = to_bytes(response.into_body(), 1_024).await.unwrap();
        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(value["error"]["code"], "unsupported_parameter");
        assert_eq!(value["error"]["param"], "temperature");
        assert_eq!(value["error"]["type"], "invalid_request_error");

        let unbounded = "x".repeat(101);
        assert_eq!(
            GatewayError::unsupported_parameter(&unbounded),
            GatewayError::UnsupportedParameter { param: None }
        );
    }
}
