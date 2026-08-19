use std::{convert::Infallible, sync::Arc, time::Duration};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use futures_util::stream;
use reqwest::{header, redirect::Policy, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use thiserror::Error;

use crate::{ChatCompletionRequest, GatewayError, GatewayModelDeployment, NormalizedUsage};

const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
const RESPONSE_IDLE_TIMEOUT: Duration = Duration::from_secs(30);
const MAX_RESPONSE_BYTES: usize = 8_000_000;
const MAX_RESPONSE_TEXT_CHARS: usize = 300;
const MAX_JSON_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[async_trait]
pub trait ModelRuntime: Send + Sync {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure>;
}

#[derive(Clone)]
pub struct SglangClient {
    client: reqwest::Client,
    api_key: Option<Arc<str>>,
}

impl SglangClient {
    pub fn new(api_key: Option<String>) -> Result<Self, RuntimeClientError> {
        let client = reqwest::Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .redirect(Policy::none())
            .build()?;

        Ok(Self {
            client,
            api_key: api_key.map(Arc::from),
        })
    }

    pub async fn check_all(
        &self,
        deployments: &[GatewayModelDeployment],
    ) -> Result<(), RuntimeHealthError> {
        for deployment in deployments {
            let health_url = endpoint(&deployment.service_url, "health");
            let mut request = self.client.get(health_url);
            if let Some(api_key) = &self.api_key {
                request = request.bearer_auth(api_key);
            }
            let response = request.send().await?;
            if !response.status().is_success() {
                return Err(RuntimeHealthError::UnhealthyStatus(response.status()));
            }
        }
        Ok(())
    }

    async fn execute_non_streaming(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        response_header_timeout: Duration,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        if request.stream || effective_output_tokens == 0 {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }

        let requested_model = request.model.clone();
        let body = serde_json::to_vec(&request.into_upstream_body(effective_output_tokens))
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        let mut upstream = self
            .client
            .post(endpoint(&deployment.service_url, "v1/chat/completions"))
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::ACCEPT, "application/json")
            .body(one_shot_body(body));
        if let Some(api_key) = &self.api_key {
            upstream = upstream.bearer_auth(api_key);
        }

        let response = tokio::time::timeout(response_header_timeout, upstream.send())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let status = response.status();
        if !status.is_success() {
            let kind = match status {
                StatusCode::BAD_REQUEST | StatusCode::UNPROCESSABLE_ENTITY => {
                    RuntimeFailureKind::InvalidRequest
                }
                StatusCode::TOO_MANY_REQUESTS => RuntimeFailureKind::CapacityExceeded,
                _ => RuntimeFailureKind::Unavailable,
            };
            let usage = match read_bounded_body(response).await {
                Ok(body) => optional_usage(&body).unwrap_or_else(NormalizedUsage::zero),
                Err(_) => NormalizedUsage::zero(),
            };
            return Err(RuntimeFailure { kind, usage });
        }

        let body = read_bounded_body(response).await?;
        normalize_completion(&body, &requested_model)
    }
}

#[async_trait]
impl ModelRuntime for SglangClient {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: ChatCompletionRequest,
        effective_output_tokens: u64,
        request_deadline: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        let remaining = request_deadline
            .signed_duration_since(Utc::now())
            .to_std()
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?;

        tokio::time::timeout(remaining, async {
            self.execute_non_streaming(deployment, request, effective_output_tokens, remaining)
                .await
        })
        .await
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
    }
}

fn one_shot_body(body: Vec<u8>) -> reqwest::Body {
    reqwest::Body::wrap_stream(stream::once(async move {
        Result::<Vec<u8>, Infallible>::Ok(body)
    }))
}

fn endpoint(service_url: &str, path: &str) -> String {
    format!("{}/{}", service_url.trim_end_matches('/'), path)
}

async fn read_bounded_body(mut response: reqwest::Response) -> Result<Vec<u8>, RuntimeFailure> {
    if response
        .content_length()
        .is_some_and(|length| length > MAX_RESPONSE_BYTES as u64)
    {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
    }

    let mut body = Vec::with_capacity(
        response
            .content_length()
            .unwrap_or(0)
            .min(MAX_RESPONSE_BYTES as u64) as usize,
    );
    loop {
        let chunk = tokio::time::timeout(RESPONSE_IDLE_TIMEOUT, response.chunk())
            .await
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::TimedOut))?
            .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::Unavailable))?;
        let Some(chunk) = chunk else {
            break;
        };
        if body
            .len()
            .checked_add(chunk.len())
            .is_none_or(|length| length > MAX_RESPONSE_BYTES)
        {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ResponseTooLarge));
        }
        body.extend_from_slice(&chunk);
    }
    Ok(body)
}

fn normalize_completion(
    body: &[u8],
    requested_model: &str,
) -> Result<RuntimeCompletion, RuntimeFailure> {
    let response: UpstreamCompletion = serde_json::from_slice(body)
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
    if response.object != "chat.completion"
        || response.id.is_empty()
        || response.id.chars().count() > MAX_RESPONSE_TEXT_CHARS
        || response.model != requested_model
        || response.choices.is_empty()
        || response.choices.iter().any(UpstreamChoice::is_invalid)
    {
        return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
    }
    let usage = response.usage.normalize()?;
    let finish_reason = response.choices[0].finish_reason.clone();
    let response = NormalizedCompletionResponse {
        id: response.id,
        object: response.object,
        created: response.created,
        model: response.model,
        choices: response
            .choices
            .into_iter()
            .map(NormalizedChoice::from)
            .collect(),
        usage: PublicUsage::from(usage),
    };
    let response = serde_json::to_value(response)
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;

    Ok(RuntimeCompletion {
        response,
        finish_reason,
        usage,
    })
}

fn optional_usage(body: &[u8]) -> Option<NormalizedUsage> {
    #[derive(Deserialize)]
    struct UsageEnvelope {
        usage: Option<UpstreamUsage>,
    }

    serde_json::from_slice::<UsageEnvelope>(body)
        .ok()?
        .usage?
        .normalize()
        .ok()
}

#[derive(Debug, Deserialize)]
struct UpstreamCompletion {
    id: String,
    object: String,
    created: u64,
    model: String,
    choices: Vec<UpstreamChoice>,
    usage: UpstreamUsage,
}

#[derive(Debug, Deserialize)]
struct UpstreamChoice {
    index: u64,
    message: Map<String, Value>,
    #[serde(default)]
    logprobs: Option<Value>,
    finish_reason: String,
}

impl UpstreamChoice {
    fn is_invalid(&self) -> bool {
        self.index > MAX_JSON_SAFE_INTEGER
            || self.finish_reason.is_empty()
            || self.finish_reason.chars().count() > 100
    }
}

#[derive(Debug, Deserialize)]
struct UpstreamUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    #[serde(default)]
    prompt_tokens_details: Option<PromptTokenDetails>,
    #[serde(default)]
    reasoning_tokens: Option<u64>,
    #[serde(default)]
    cache_write_tokens: Option<u64>,
}

impl UpstreamUsage {
    fn normalize(self) -> Result<NormalizedUsage, RuntimeFailure> {
        let expected_total = self
            .prompt_tokens
            .checked_add(self.completion_tokens)
            .ok_or_else(|| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))?;
        if expected_total != self.total_tokens || self.total_tokens > MAX_JSON_SAFE_INTEGER {
            return Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation));
        }
        NormalizedUsage::new(
            self.prompt_tokens,
            self.prompt_tokens_details
                .map_or(0, |details| details.cached_tokens),
            self.cache_write_tokens.unwrap_or(0),
            self.completion_tokens,
            self.reasoning_tokens.unwrap_or(0),
        )
        .map_err(|_| RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))
    }
}

#[derive(Debug, Deserialize)]
struct PromptTokenDetails {
    #[serde(default)]
    cached_tokens: u64,
}

#[derive(Serialize)]
struct NormalizedCompletionResponse {
    id: String,
    object: String,
    created: u64,
    model: String,
    choices: Vec<NormalizedChoice>,
    usage: PublicUsage,
}

#[derive(Serialize)]
struct NormalizedChoice {
    index: u64,
    message: Map<String, Value>,
    logprobs: Option<Value>,
    finish_reason: String,
}

impl From<UpstreamChoice> for NormalizedChoice {
    fn from(choice: UpstreamChoice) -> Self {
        Self {
            index: choice.index,
            message: choice.message,
            logprobs: choice.logprobs,
            finish_reason: choice.finish_reason,
        }
    }
}

#[derive(Serialize)]
struct PublicUsage {
    prompt_tokens: u64,
    completion_tokens: u64,
    total_tokens: u64,
    prompt_tokens_details: PublicPromptTokenDetails,
    completion_tokens_details: PublicCompletionTokenDetails,
}

impl From<NormalizedUsage> for PublicUsage {
    fn from(usage: NormalizedUsage) -> Self {
        Self {
            prompt_tokens: usage.input_tokens(),
            completion_tokens: usage.output_tokens(),
            total_tokens: usage.input_tokens() + usage.output_tokens(),
            prompt_tokens_details: PublicPromptTokenDetails {
                cached_tokens: usage.cached_input_tokens(),
            },
            completion_tokens_details: PublicCompletionTokenDetails {
                reasoning_tokens: usage.reasoning_tokens(),
            },
        }
    }
}

#[derive(Serialize)]
struct PublicPromptTokenDetails {
    cached_tokens: u64,
}

#[derive(Serialize)]
struct PublicCompletionTokenDetails {
    reasoning_tokens: u64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RuntimeCompletion {
    response: Value,
    finish_reason: String,
    usage: NormalizedUsage,
}

impl RuntimeCompletion {
    #[cfg(test)]
    pub(crate) fn from_normalized_parts(
        response: Value,
        finish_reason: String,
        usage: NormalizedUsage,
    ) -> Self {
        Self {
            response,
            finish_reason,
            usage,
        }
    }

    pub fn response(&self) -> &Value {
        &self.response
    }

    pub fn into_response(self) -> Value {
        self.response
    }

    pub fn finish_reason(&self) -> &str {
        &self.finish_reason
    }

    pub fn usage(&self) -> NormalizedUsage {
        self.usage
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeFailureKind {
    InvalidRequest,
    CapacityExceeded,
    Unavailable,
    TimedOut,
    ResponseTooLarge,
    ProtocolViolation,
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
#[error("model runtime failed: {kind:?}")]
pub struct RuntimeFailure {
    kind: RuntimeFailureKind,
    usage: NormalizedUsage,
}

impl RuntimeFailure {
    pub fn new(kind: RuntimeFailureKind) -> Self {
        Self {
            kind,
            usage: NormalizedUsage::zero(),
        }
    }

    pub(crate) fn with_usage(kind: RuntimeFailureKind, usage: NormalizedUsage) -> Self {
        Self { kind, usage }
    }

    pub fn kind(&self) -> RuntimeFailureKind {
        self.kind
    }

    pub fn usage(&self) -> NormalizedUsage {
        self.usage
    }

    pub fn gateway_error(&self) -> GatewayError {
        match self.kind {
            RuntimeFailureKind::InvalidRequest => GatewayError::invalid_request(None),
            RuntimeFailureKind::CapacityExceeded => GatewayError::CapacityExceeded,
            RuntimeFailureKind::Unavailable
            | RuntimeFailureKind::TimedOut
            | RuntimeFailureKind::ResponseTooLarge
            | RuntimeFailureKind::ProtocolViolation => GatewayError::RuntimeUnavailable,
        }
    }
}

#[derive(Debug, Error)]
pub enum RuntimeClientError {
    #[error("SGLang HTTP client could not be built: {0}")]
    Request(#[from] reqwest::Error),
}

#[derive(Debug, Error)]
pub enum RuntimeHealthError {
    #[error("SGLang health request failed: {0}")]
    Request(#[from] reqwest::Error),
    #[error("SGLang health endpoint returned {0}")]
    UnhealthyStatus(reqwest::StatusCode),
}

#[cfg(test)]
mod tests {
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    };

    use axum::{
        body::Bytes,
        extract::State,
        http::{header::LOCATION, HeaderMap, StatusCode},
        response::IntoResponse,
        routing::post,
        Router,
    };
    use serde_json::json;
    use tokio::task::JoinHandle;
    use uuid::Uuid;

    use super::*;
    use crate::{DeploymentStatus, ModelDeploymentRelease};

    #[derive(Clone)]
    struct RecordedRequest {
        headers: HeaderMap,
        body: Value,
    }

    #[derive(Clone)]
    struct TestServerState {
        recorded: Arc<Mutex<Vec<RecordedRequest>>>,
        status: StatusCode,
        response: Value,
    }

    async fn respond(
        State(state): State<TestServerState>,
        headers: HeaderMap,
        body: Bytes,
    ) -> impl IntoResponse {
        state.recorded.lock().unwrap().push(RecordedRequest {
            headers,
            body: serde_json::from_slice(&body).unwrap(),
        });
        (state.status, axum::Json(state.response))
    }

    async fn server(
        status: StatusCode,
        response: Value,
    ) -> (String, Arc<Mutex<Vec<RecordedRequest>>>, JoinHandle<()>) {
        let recorded = Arc::new(Mutex::new(Vec::new()));
        let state = TestServerState {
            recorded: recorded.clone(),
            status,
            response,
        };
        let application = Router::new()
            .route("/v1/chat/completions", post(respond))
            .with_state(state);
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        (format!("http://{address}"), recorded, task)
    }

    fn deployment(service_url: String) -> GatewayModelDeployment {
        GatewayModelDeployment {
            id: Uuid::now_v7(),
            status: DeploymentStatus::Available,
            service_url,
            release: ModelDeploymentRelease {
                schema_version: 1,
                runtime_revision: "runtime".to_owned(),
                model_path: "model-a".to_owned(),
                model_revision: "model-revision".to_owned(),
                tokenizer_path: "model-a".to_owned(),
                tokenizer_revision: "tokenizer-revision".to_owned(),
            },
        }
    }

    fn request() -> ChatCompletionRequest {
        ChatCompletionRequest::parse(
            br#"{
                "model":"model-a",
                "messages":[{"role":"user","content":"hello"}],
                "temperature":0.25,
                "tools":[{"type":"function","function":{"name":"weather"}}]
            }"#,
        )
        .unwrap()
    }

    fn successful_response() -> Value {
        json!({
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1_777_000_000,
            "model": "model-a",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "hello",
                    "reasoning_content": null,
                    "tool_calls": null
                },
                "logprobs": null,
                "finish_reason": "stop",
                "matched_stop": 1
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "prompt_tokens_details": {"cached_tokens": 4},
                "reasoning_tokens": 2
            },
            "metadata": {"private_runtime_field": true}
        })
    }

    #[tokio::test]
    async fn sends_one_qualified_request_and_normalizes_the_response() {
        let (service_url, recorded, task) = server(StatusCode::OK, successful_response()).await;
        let runtime = SglangClient::new(Some("runtime-secret".to_owned())).unwrap();

        let completion = runtime
            .complete(
                &deployment(service_url),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap();

        let requests = recorded.lock().unwrap();
        assert_eq!(requests.len(), 1);
        assert_eq!(
            requests[0].headers[header::AUTHORIZATION],
            "Bearer runtime-secret"
        );
        assert_eq!(requests[0].body["model"], "model-a");
        assert_eq!(requests[0].body["messages"][0]["content"], "hello");
        assert_eq!(requests[0].body["temperature"], 0.25);
        assert_eq!(requests[0].body["tools"][0]["function"]["name"], "weather");
        assert_eq!(requests[0].body["max_completion_tokens"], 1_024);
        assert_eq!(requests[0].body["stream"], false);

        assert_eq!(completion.finish_reason(), "stop");
        assert_eq!(completion.usage().input_tokens(), 10);
        assert_eq!(completion.usage().cached_input_tokens(), 4);
        assert_eq!(completion.usage().output_tokens(), 5);
        assert_eq!(completion.usage().reasoning_tokens(), 2);
        assert_eq!(completion.response()["usage"]["total_tokens"], 15);
        assert!(completion.response().get("metadata").is_none());
        assert!(completion.response()["choices"][0]
            .get("matched_stop")
            .is_none());
        task.abort();
    }

    #[tokio::test]
    async fn maps_overload_without_retrying_and_retains_valid_error_usage() {
        let response = json!({
            "error": {"message": "queue full"},
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
                "reasoning_tokens": 0
            }
        });
        let (service_url, recorded, task) = server(StatusCode::TOO_MANY_REQUESTS, response).await;
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment(service_url),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
        assert_eq!(failure.gateway_error(), GatewayError::CapacityExceeded);
        assert_eq!(failure.usage().input_tokens(), 2);
        assert_eq!(recorded.lock().unwrap().len(), 1);
        task.abort();
    }

    #[tokio::test]
    async fn rejects_inconsistent_authoritative_usage() {
        let mut response = successful_response();
        response["usage"]["total_tokens"] = json!(16);
        let (service_url, _, task) = server(StatusCode::OK, response).await;
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment(service_url),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
        task.abort();
    }

    #[tokio::test]
    async fn refuses_non_streaming_execution_after_the_deadline() {
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment("http://127.0.0.1:1".to_owned()),
                request(),
                1_024,
                Utc::now() - chrono::TimeDelta::seconds(1),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
    }

    #[test]
    fn request_body_is_not_replayable() {
        assert!(one_shot_body(b"private prompt".to_vec())
            .as_bytes()
            .is_none());
    }

    #[tokio::test]
    async fn does_not_follow_a_runtime_redirect() {
        let initial_requests = Arc::new(AtomicUsize::new(0));
        let redirected_requests = Arc::new(AtomicUsize::new(0));
        let initial_counter = initial_requests.clone();
        let redirected_counter = redirected_requests.clone();
        let application = Router::new()
            .route(
                "/v1/chat/completions",
                post(move || {
                    let counter = initial_counter.clone();
                    async move {
                        counter.fetch_add(1, Ordering::SeqCst);
                        (StatusCode::TEMPORARY_REDIRECT, [(LOCATION, "/redirected")])
                    }
                }),
            )
            .route(
                "/redirected",
                post(move || {
                    let counter = redirected_counter.clone();
                    async move {
                        counter.fetch_add(1, Ordering::SeqCst);
                        axum::Json(successful_response())
                    }
                }),
            );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });
        let runtime = SglangClient::new(None).unwrap();

        let failure = runtime
            .complete(
                &deployment(format!("http://{address}")),
                request(),
                1_024,
                Utc::now() + chrono::TimeDelta::seconds(5),
            )
            .await
            .unwrap_err();

        assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
        assert_eq!(initial_requests.load(Ordering::SeqCst), 1);
        assert_eq!(redirected_requests.load(Ordering::SeqCst), 0);
        task.abort();
    }
}
