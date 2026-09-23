use hf_chat_template::Error as ChatTemplateError;
use hf_hub::api::tokio::ApiError;
use thiserror::Error;

use crate::{
    GatewayError, InferenceRequest, ModelDeploymentRelease, OutputTokenLimit, QualifiedRequest,
};

mod compiled;
mod decoder;
mod deepseek;
mod deepseek_v4;
mod deepseek_v41;
mod registry;
mod renderer;
#[cfg(test)]
pub(crate) mod test_support;
#[cfg(test)]
mod tests;

pub(crate) use decoder::TokenDecoder;
pub use registry::ModelTokenizer;

#[derive(Clone, Debug, PartialEq)]
pub struct BoundedRequest {
    pub qualified: QualifiedRequest,
}

impl ModelTokenizer {
    pub async fn enforce(
        &self,
        mut qualified: QualifiedRequest,
    ) -> Result<BoundedRequest, GatewayError> {
        let input_ids = self.encode(&qualified).await?;
        let input_tokens =
            u64::try_from(input_ids.len()).map_err(|_| GatewayError::ServingStateUnavailable)?;
        qualified.request.encoded_input_ids = Some(input_ids);

        enforce_bounds(qualified, input_tokens)
    }

    pub async fn count(&self, qualified: &QualifiedRequest) -> Result<u64, GatewayError> {
        let input_ids = self.encode(qualified).await?;

        u64::try_from(input_ids.len()).map_err(|_| GatewayError::ServingStateUnavailable)
    }

    async fn encode(&self, qualified: &QualifiedRequest) -> Result<Vec<u32>, GatewayError> {
        let release = &qualified.deployment.release;
        let tokenizer = self
            .tokenizer(release)
            .await
            .map_err(|_| GatewayError::ServingStateUnavailable)?;

        // Rendering and tokenizing a long prompt is CPU work that must not hold an
        // async worker other requests are waiting on.
        let request = qualified.request.clone();
        let encoded = tokio::task::spawn_blocking(move || tokenizer.encode_input(&request)).await;

        match encoded {
            Ok(Ok(input_ids)) => Ok(input_ids),
            Ok(Err(error)) => {
                if let Some(error_code) = error.hidden_code() {
                    log_hidden_failure(release, error_code);
                }

                Err(map_request_error(error))
            }
            Err(_) => {
                log_hidden_failure(release, "task");
                Err(GatewayError::ServingStateUnavailable)
            }
        }
    }

    pub(crate) async fn decoder(
        &self,
        release: &ModelDeploymentRelease,
    ) -> Result<TokenDecoder, ModelTokenizerError> {
        Ok(TokenDecoder::new(self.tokenizer(release).await?))
    }
}

// The error text is not logged: a render error can echo template input.
fn log_hidden_failure(release: &ModelDeploymentRelease, error_code: &'static str) {
    crate::diagnostics::limited_error!(
        tokenizer_path = %release.tokenizer_path,
        tokenizer_revision = %release.tokenizer_revision,
        error_code,
        "prompt tokenization failed"
    );
}

fn map_request_error(error: TokenizerRequestError) -> GatewayError {
    match error {
        TokenizerRequestError::InvalidParameter(param) => {
            GatewayError::invalid_request(Some(param))
        }
        TokenizerRequestError::InvalidInput | TokenizerRequestError::Rejected => {
            GatewayError::invalid_request(Some("messages"))
        }
        TokenizerRequestError::Render | TokenizerRequestError::Encode => {
            GatewayError::ServingStateUnavailable
        }
    }
}

fn enforce_bounds(
    qualified: QualifiedRequest,
    input_tokens: u64,
) -> Result<BoundedRequest, GatewayError> {
    if input_tokens > qualified.max_prompt_tokens {
        return Err(GatewayError::context_length_exceeded("messages"));
    }

    let total_tokens = input_tokens
        .checked_add(qualified.effective_output_tokens)
        .ok_or(GatewayError::ServingStateUnavailable)?;
    if total_tokens > qualified.max_context_tokens {
        let parameter = qualified
            .request
            .output_token_limit()
            .map(OutputTokenLimit::parameter_name)
            .unwrap_or("messages");
        return Err(GatewayError::context_length_exceeded(parameter));
    }

    Ok(BoundedRequest { qualified })
}

#[derive(Debug, Error)]
pub enum ModelTokenizerError {
    #[error("Hugging Face artifact resolution failed: {0}")]
    Hub(#[from] ApiError),
    #[error("tokenizer artifact I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("tokenizer config is invalid: {0}")]
    Config(#[from] serde_json::Error),
    #[error("chat template is invalid: {0}")]
    Template(#[from] ChatTemplateError),
    #[error("tokenizer is invalid: {0}")]
    Tokenizer(String),
    #[error("tokenizer task failed: {0}")]
    Task(tokio::task::JoinError),
    #[error("tokenizer load timed out")]
    TimedOut,
    #[error("tokenizer load is backing off after a failure")]
    Backoff,
}

impl ModelTokenizerError {
    fn code(&self) -> &'static str {
        match self {
            Self::Hub(_) => "hub",
            Self::Io(_) => "io",
            Self::Config(_) => "config",
            Self::Template(_) => "template",
            Self::Tokenizer(_) => "tokenizer",
            Self::Task(_) => "task",
            Self::TimedOut => "timeout",
            Self::Backoff => "backoff",
        }
    }
}

#[derive(Debug, Error, Eq, PartialEq)]
enum TokenizerRequestError {
    #[error("invalid request parameter: {0}")]
    InvalidParameter(&'static str),
    #[error("request cannot be represented as chat-template input")]
    InvalidInput,
    #[error("chat template rejected the request")]
    Rejected,
    #[error("chat template rendering failed")]
    Render,
    #[error("tokenization failed")]
    Encode,
}

impl TokenizerRequestError {
    fn hidden_code(&self) -> Option<&'static str> {
        match self {
            Self::Render => Some("render"),
            Self::Encode => Some("encode"),
            Self::InvalidParameter(_) | Self::InvalidInput | Self::Rejected => None,
        }
    }
}
