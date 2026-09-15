use thiserror::Error;

use crate::GatewayError;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum FinalizationOutcome {
    Settled,
    AlreadyAbsent,
}

#[derive(Debug, Error)]
pub enum FinalizationError {
    #[error("generation properties organization does not match finalization")]
    OrganizationMismatch,
    #[error("generation properties could not be serialized: {0}")]
    Serialization(#[from] serde_json::Error),
    #[error("the finalization script returned an unknown result: {0}")]
    UnknownScriptResult(i64),
    #[error("Valkey finalization failed: {0}")]
    Redis(#[from] redis::RedisError),
}

impl From<FinalizationError> for GatewayError {
    fn from(_: FinalizationError) -> Self {
        Self::FinalizationUnavailable
    }
}

impl FinalizationError {
    pub(crate) fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::OrganizationMismatch => "organization_mismatch",
            Self::Serialization(_) => "serialization",
            Self::UnknownScriptResult(_) => "unexpected_script_result",
            Self::Redis(_) => "redis",
        }
    }
}
