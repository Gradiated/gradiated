use std::{sync::Arc, time::Duration};

use async_trait::async_trait;
use reqwest::{header, redirect::Policy, Response, StatusCode};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use super::{
    client::{
        one_shot_body, open_events, read_bounded_body, read_completion_body, record_rejection,
        remaining_until, send, within, CONNECT_TIMEOUT,
    },
    external_chat::{failure_for_code, normalize_completion, ChatStream, Names, UpstreamBilling},
    progress::ProgressStream,
    ExternalCapacity, ExternalModel, ExternalRequest, FailureCause, PriceCap, ProtocolViolation,
    RuntimeClientError, RuntimeCompletion, RuntimeEventStream, RuntimeFailure, RuntimeFailureKind,
};
use crate::{config::OpenRouterConfig, NormalizedUsage};
use gradiated_credentials::{CredentialLoader, Provider};

const REJECTION_READ: Duration = Duration::from_millis(250);
pub(super) const POSTHOG_ORGANIZATION_ID: Uuid =
    Uuid::from_u128(0x01a01fdd37b57305a913aa3dc782c81c);
const FALLBACK_PROVIDER_RESTRICTIONS: &[(Uuid, &[&str])] =
    &[(POSTHOG_ORGANIZATION_ID, &["baseten", "modal"])];

/// Advertised parameters OpenRouter does not understand. It ignores rather than
/// rejects them, so a request carrying one stays on our capacity.
const UNSUPPORTED_PARAMETERS: [&str; 1] = ["chat_template_kwargs"];

/// Advertised parameters a specific OpenRouter model does not list in its
/// `supported_parameters`. With `require_parameters` no provider would match, so a
/// request carrying one stays on our capacity.
const MODEL_UNSUPPORTED_PARAMETERS: [(&str, &[&str]); 1] =
    [("moonshotai/kimi-k3.1-pro", &["parallel_tool_calls"])];

// Baseten/Modal endpoint maxima on OpenRouter, checked 2026-11-17 (standard tier only).
const MODEL_MAX_PRICE: [(&str, PriceCap); 3] = [
    (
        "moonshotai/kimi-k3.1-pro",
        PriceCap {
            prompt: 2_000,
            completion: 10_000,
        },
    ),
    (
        "deepseek/deepseek-v4.1-flash-1017",
        PriceCap {
            prompt: 300,
            completion: 1_200,
        },
    ),
    (
        "z-ai/glm-5.3-flash",
        PriceCap {
            prompt: 150,
            completion: 500,
        },
    ),
];

fn max_price(model_id: &str, cap: PriceCap) -> PriceCap {
    MODEL_MAX_PRICE
        .iter()
        .find(|(model, _)| *model == model_id)
        .map_or(cap, |(_, price)| *price)
}

pub fn supports_parameter(model_id: &str, name: &str) -> bool {
    !UNSUPPORTED_PARAMETERS.contains(&name)
        && !MODEL_UNSUPPORTED_PARAMETERS
            .iter()
            .any(|(model, names)| *model == model_id && names.contains(&name))
}

#[derive(Clone)]
pub struct OpenRouterClient {
    client: reqwest::Client,
    api_key: ApiKey,
    endpoint: Arc<str>,
}

#[derive(Clone)]
enum ApiKey {
    Fixed(Arc<str>),
    Rotating(Arc<CredentialLoader>),
}

impl OpenRouterClient {
    pub async fn connect(config: &OpenRouterConfig) -> Result<Self, RuntimeClientError> {
        let api_key = match &config.api_key {
            Some(key) => ApiKey::Fixed(Arc::from(key.as_str())),
            None => {
                let aws = aws_config::defaults(aws_config::BehaviorVersion::latest())
                    .region(aws_config::Region::new("us-east-1"))
                    .load()
                    .await;
                ApiKey::Rotating(Arc::new(CredentialLoader::new(
                    aws_sdk_secretsmanager::Client::new(&aws),
                )))
            }
        };

        Self::with_key(&config.base_url, api_key)
    }

    #[cfg(test)]
    pub(crate) fn with_loader(
        base_url: &str,
        loader: CredentialLoader,
    ) -> Result<Self, RuntimeClientError> {
        Self::with_key(base_url, ApiKey::Rotating(Arc::new(loader)))
    }

    fn with_key(base_url: &str, api_key: ApiKey) -> Result<Self, RuntimeClientError> {
        let client = reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .redirect(Policy::none())
            .build()?;

        Ok(Self {
            client,
            api_key,
            endpoint: Arc::from(format!("{base_url}/chat/completions")),
        })
    }

    /// The loader returns no detail on failure, so none can reach a log.
    async fn api_key(&self) -> Result<Arc<str>, RuntimeFailure> {
        match &self.api_key {
            ApiKey::Fixed(key) => Ok(key.clone()),
            ApiKey::Rotating(loader) => loader
                .load(Provider::OpenRouter)
                .await
                .map(Arc::from)
                .map_err(|_| {
                    crate::diagnostics::limited_warn!(
                        error_code = "openrouter_credential_unavailable",
                        "OpenRouter credential could not be loaded"
                    );
                    RuntimeFailure::caused(
                        RuntimeFailureKind::Unavailable,
                        FailureCause::Credential,
                    )
                }),
        }
    }

    async fn send(
        &self,
        request: ExternalRequest,
        accept: &str,
    ) -> Result<Response, RuntimeFailure> {
        let api_key = self.api_key().await?;
        let model = request.model.clone();
        let body = self.body(request);
        crate::diagnostics::body::record_value("runtime_request", &body, None);
        let body = serde_json::to_vec(&body).map_err(|_| ProtocolViolation::Json)?;

        let upstream = self
            .client
            .post(&*self.endpoint)
            .bearer_auth(&api_key)
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, accept)
            .body(one_shot_body(body));
        let response = send(upstream).await?;
        let status = response.status();
        if status.is_success() {
            return Ok(response);
        }

        if status != StatusCode::BAD_REQUEST {
            let headers = response.headers().clone();
            let status = record_rejection(response).await.as_u16();
            return Err(
                failure_for_code(status, NormalizedUsage::zero()).with_retry_after(&headers)
            );
        }

        if !rejects_model(response, &model).await {
            return Err(failure_for_code(400, NormalizedUsage::zero()));
        }

        crate::diagnostics::limited_warn!(
            error_code = "openrouter_model_rejected",
            openrouter_model = model.id(),
            "OpenRouter does not recognise the mapped model"
        );
        Err(RuntimeFailure::caused(
            RuntimeFailureKind::Unavailable,
            FailureCause::Status(400),
        ))
    }

    fn body(&self, request: ExternalRequest) -> Value {
        let ExternalRequest {
            organization_id,
            workspace_id,
            model,
            request,
            output_tokens,
            price_cap,
            ..
        } = request;
        let session = request
            .session_id
            .as_deref()
            .map(|session| scoped_hash(workspace_id, session));

        let max_price = max_price(model.id(), price_cap);
        let mut body = request.into_external_body(output_tokens, model.id());
        // Every request routes only to zero-retention endpoints that collect no data
        // and charge no more than the caller pays us, or the model's accepted overpay.
        body.insert(
            "provider".to_owned(),
            json!({
                "data_collection": "deny",
                "require_parameters": true,
                "zdr": true,
                "max_price": {
                    "prompt": usd_per_million(max_price.prompt),
                    "completion": usd_per_million(max_price.completion),
                },
            }),
        );

        if let Some((_, providers)) = FALLBACK_PROVIDER_RESTRICTIONS
            .iter()
            .find(|(organization, _)| *organization == organization_id)
        {
            body["provider"]["only"] = json!(providers);
        }

        // Context compression is on by default for small-context endpoints and
        // would silently drop the middle of a prompt.
        body.insert(
            "plugins".to_owned(),
            json!([{"id": "context-compression", "enabled": false}]),
        );
        body.insert(
            "user".to_owned(),
            Value::String(scoped_hash(workspace_id, "")),
        );
        if let Some(session) = session {
            body.insert("session_id".to_owned(), Value::String(session));
        }

        Value::Object(body)
    }
}

fn usd_per_million(nano_usd_per_token: u64) -> f64 {
    nano_usd_per_token as f64 / 1_000.0
}

/// An opaque per-workspace value: OpenRouter isolates abuse controls by `user`
/// and keeps provider cache affinity by `session_id`, but neither needs our IDs.
fn scoped_hash(workspace_id: Uuid, value: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(workspace_id.as_bytes());
    hash.update(value.as_bytes());

    format!("{:x}", hash.finalize())
}

#[async_trait]
impl ExternalCapacity for OpenRouterClient {
    async fn complete(
        &self,
        request: ExternalRequest,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let remaining = remaining_until(request.deadline)?;
        let names = Names::new(&request, request.model.id(), UpstreamBilling::OpenRouter);

        within(remaining, async move {
            let response = self.send(request, "application/json").await?;
            let body = read_completion_body(response).await?;

            normalize_completion(&body, &names)
        })
        .await
    }

    async fn stream(
        &self,
        request: ExternalRequest,
    ) -> Result<Box<dyn RuntimeEventStream>, RuntimeFailure> {
        let remaining = remaining_until(request.deadline)?;
        let deadline = tokio::time::Instant::now() + remaining;
        let names = Names::new(&request, request.model.id(), UpstreamBilling::OpenRouter);

        let stream = within(remaining, async move {
            let response = self.send(request, "text/event-stream").await?;
            let mut stream = ChatStream::new(open_events(response)?, names);
            stream.peek(1).await?;

            Ok(stream)
        })
        .await?;

        Ok(Box::new(ProgressStream::new(Box::new(stream), deadline)))
    }
}

/// Our credential, credit and routing problems are ours, not the caller's, so
/// only a malformed request is reported as one.
/// OpenRouter answers 400 for a model it does not list, which is our mapping's fault.
async fn rejects_model(response: Response, model: &ExternalModel) -> bool {
    let Ok(Ok(body)) = tokio::time::timeout(REJECTION_READ, read_bounded_body(response)).await
    else {
        return false;
    };

    serde_json::from_slice::<Value>(&body)
        .ok()
        .and_then(|value| {
            Some(
                value
                    .pointer("/error/message")?
                    .as_str()?
                    .contains(model.id()),
            )
        })
        .unwrap_or(false)
}
