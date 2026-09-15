use std::{sync::Arc, time::Duration};

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, State},
    http::{
        header::{AUTHORIZATION, CONTENT_TYPE},
        HeaderMap, HeaderName, HeaderValue, Method, StatusCode,
    },
    response::{
        sse::{KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use futures_util::StreamExt;
use serde::Serialize;
use serde_json::Value;
use tower_http::cors::{AllowOrigin, CorsLayer};
use uuid::Uuid;

use crate::{
    protocol::{responses_use_unsupported_state, Frame, Protocol, StreamItem},
    readiness::ReadinessCheck,
    CompletionResponse, CompletionService, GatewayError, GatewayMetrics, ModelCatalogResponse,
    RequestCoordinator, RequestMetadata,
};

const MAX_REQUEST_BYTES: usize = 32_000_000;
const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-generation-id");
const SERVICE_TIER_HEADER: HeaderName = HeaderName::from_static("x-gradiated-service-tier");
const STREAM_KEEP_ALIVE: Duration = Duration::from_secs(10);

pub fn browser_cors(origins: Vec<HeaderValue>) -> CorsLayer {
    CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([AUTHORIZATION, CONTENT_TYPE])
        .expose_headers([GENERATION_ID_HEADER, SERVICE_TIER_HEADER])
        .max_age(Duration::from_secs(3600))
}

#[derive(Clone)]
pub struct GatewayState {
    readiness: Arc<dyn ReadinessCheck>,
    completions: CompletionService,
    coordinator: RequestCoordinator,
    metrics: GatewayMetrics,
}

impl GatewayState {
    pub fn new(
        readiness: Arc<dyn ReadinessCheck>,
        completions: CompletionService,
        coordinator: RequestCoordinator,
    ) -> Self {
        let metrics = completions.metrics();
        Self {
            readiness,
            completions,
            coordinator,
            metrics,
        }
    }
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
}

fn inference_routes() -> Router<GatewayState> {
    Router::new()
        .route("/chat/completions", post(chat_completions))
        .route("/messages", post(messages))
        .route("/messages/count_tokens", post(messages_count_tokens))
        .route("/responses", post(responses))
        .route("/models", get(models))
}

pub fn router(state: GatewayState) -> Router {
    Router::new()
        .nest("/v1", inference_routes())
        .merge(inference_routes())
        .route("/health/live", get(live))
        .route("/health/ready", get(ready))
        .route("/metrics", get(metrics))
        .layer(DefaultBodyLimit::max(MAX_REQUEST_BYTES))
        .with_state(state)
}

fn generation_id_header(generation_id: Uuid) -> HeaderValue {
    HeaderValue::from_str(&generation_id.to_string())
        .expect("a UUID is always a valid HTTP header value")
}

fn finish(
    state: &GatewayState,
    route: &'static str,
    protocol: Protocol,
    generation_id: Uuid,
    result: Result<Response, GatewayError>,
) -> Response {
    if let Err(error) = &result {
        crate::diagnostics::limited_warn!(
            %generation_id,
            route,
            status = error.status().as_u16(),
            error_code = error.code(),
            parameter = error.param(),
            "inference request rejected before response"
        );
    }
    let error = result
        .as_ref()
        .err()
        .map(GatewayError::code)
        .unwrap_or("none");
    let mut response = result.unwrap_or_else(|error| protocol.error_response(error));
    state
        .metrics
        .record_http(route, response.status().as_u16(), error);
    response
        .headers_mut()
        .insert(GENERATION_ID_HEADER, generation_id_header(generation_id));
    response
}

fn request_metadata() -> RequestMetadata {
    RequestMetadata {
        generation_id: Uuid::now_v7(),
        received_at: Utc::now(),
    }
}

fn parse_body(body: &Bytes) -> Result<Value, GatewayError> {
    serde_json::from_slice(body).map_err(|_| GatewayError::invalid_request(None))
}

fn body_rejection(rejection: BytesRejection) -> GatewayError {
    if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE {
        GatewayError::PayloadTooLarge
    } else {
        GatewayError::invalid_request(None)
    }
}

fn translate_inbound(protocol: Protocol, body: &Bytes) -> Result<Bytes, GatewayError> {
    let request = parse_body(body)?;
    if protocol == Protocol::OpenAiResponses && responses_use_unsupported_state(&request) {
        return Err(GatewayError::invalid_request(Some("store")));
    }
    protocol.translate_request(&request).map(Bytes::from)
}

async fn complete_with_protocol(
    state: &GatewayState,
    protocol: Protocol,
    metadata: RequestMetadata,
    headers: &HeaderMap,
    body: Bytes,
) -> Result<Response, GatewayError> {
    match state.completions.complete(metadata, headers, body).await? {
        CompletionResponse::NonStreaming {
            result,
            service_tier,
        } => {
            let mut response =
                Json(protocol.translate_response(result.into_response())?).into_response();
            response.headers_mut().insert(
                SERVICE_TIER_HEADER,
                HeaderValue::from_static(service_tier.as_str()),
            );
            Ok(response)
        }
        CompletionResponse::Streaming {
            result,
            service_tier,
        } => {
            let mut response = sse_response(protocol, result.into_stream());
            response.headers_mut().insert(
                SERVICE_TIER_HEADER,
                HeaderValue::from_static(service_tier.as_str()),
            );
            Ok(response)
        }
    }
}

fn sse_response(
    protocol: Protocol,
    stream: impl futures_util::Stream<Item = StreamItem> + Send + 'static,
) -> Response {
    let renderer = Arc::new(std::sync::Mutex::new(protocol.stream_renderer()));
    let frames = stream.map(move |item| {
        let rendered = renderer
            .lock()
            .expect("the stream renderer is never poisoned while unwinding")
            .render(item);
        futures_util::stream::iter(
            frames_into_events(rendered)
                .into_iter()
                .map(Ok::<_, axum::Error>),
        )
    });
    let mut response = Sse::new(frames.flatten())
        .keep_alive(
            KeepAlive::new()
                .interval(STREAM_KEEP_ALIVE)
                .text("keep-alive"),
        )
        .into_response();
    response.headers_mut().insert(
        HeaderName::from_static("x-accel-buffering"),
        HeaderValue::from_static("no"),
    );
    response
}

fn frames_into_events(frames: Vec<Frame>) -> Vec<axum::response::sse::Event> {
    frames
        .into_iter()
        .map(|frame| {
            let mut event = axum::response::sse::Event::default();
            if let Some(name) = frame.event {
                event = event.event(name);
            }
            event.data(frame.data)
        })
        .collect()
}

async fn models(State(state): State<GatewayState>, headers: HeaderMap) -> Response {
    let result = state.coordinator.list_models(&headers, Utc::now()).await;
    let error = result
        .as_ref()
        .err()
        .map(GatewayError::code)
        .unwrap_or("none");
    let response = match result {
        Ok(models) => Json(ModelCatalogResponse::from_models(&models)).into_response(),
        Err(error) => error.into_response(),
    };
    state
        .metrics
        .record_http("models", response.status().as_u16(), error);
    response
}

async fn chat_completions(
    State(state): State<GatewayState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    let metadata = request_metadata();
    let generation_id = metadata.generation_id;
    let result = match body {
        Ok(body) => match translate_inbound(Protocol::OpenAiChat, &body) {
            Ok(translated) => {
                complete_with_protocol(&state, Protocol::OpenAiChat, metadata, &headers, translated)
                    .await
            }
            Err(error) => Err(error),
        },
        Err(rejection) => Err(body_rejection(rejection)),
    };
    finish(
        &state,
        "chat_completions",
        Protocol::OpenAiChat,
        generation_id,
        result,
    )
}

async fn messages(
    State(state): State<GatewayState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    let metadata = request_metadata();
    let generation_id = metadata.generation_id;
    let result = match body {
        Ok(body) => match translate_inbound(Protocol::AnthropicMessages, &body) {
            Ok(translated) => {
                complete_with_protocol(
                    &state,
                    Protocol::AnthropicMessages,
                    metadata,
                    &headers,
                    translated,
                )
                .await
            }
            Err(error) => Err(error),
        },
        Err(rejection) => Err(body_rejection(rejection)),
    };
    finish(
        &state,
        "messages",
        Protocol::AnthropicMessages,
        generation_id,
        result,
    )
}

async fn messages_count_tokens(
    State(state): State<GatewayState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    let metadata = request_metadata();
    let generation_id = metadata.generation_id;
    let result = async {
        let body = body.map_err(body_rejection)?;
        let request = parse_body(&body)?;
        let translated = Protocol::AnthropicMessages.translate_request(&request)?;
        let count = state
            .completions
            .count_tokens(&headers, &translated)
            .await?;
        Ok(Json(serde_json::json!({ "input_tokens": count })).into_response())
    }
    .await;
    finish(
        &state,
        "messages_count_tokens",
        Protocol::AnthropicMessages,
        generation_id,
        result,
    )
}

async fn responses(
    State(state): State<GatewayState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    let metadata = request_metadata();
    let generation_id = metadata.generation_id;
    let result = async {
        let body = body.map_err(body_rejection)?;
        let translated = translate_inbound(Protocol::OpenAiResponses, &body)?;
        complete_with_protocol(
            &state,
            Protocol::OpenAiResponses,
            metadata,
            &headers,
            translated,
        )
        .await
    }
    .await;
    finish(
        &state,
        "responses",
        Protocol::OpenAiResponses,
        generation_id,
        result,
    )
}

async fn live() -> Json<HealthResponse> {
    Json(HealthResponse { status: "live" })
}

async fn ready(State(state): State<GatewayState>) -> (StatusCode, Json<HealthResponse>) {
    let ready = !state.completions.is_draining() && state.readiness.is_ready().await;
    state.metrics.set_dependency_ready("gateway", ready);
    if !ready {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(HealthResponse {
                status: "not_ready",
            }),
        )
    } else {
        (StatusCode::OK, Json(HealthResponse { status: "ready" }))
    }
}

async fn metrics(State(state): State<GatewayState>) -> Response {
    (
        [(
            CONTENT_TYPE,
            "application/openmetrics-text; version=1.0.0; charset=utf-8",
        )],
        state.metrics.encode(),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use async_trait::async_trait;
    use axum::{
        body::{to_bytes, Body},
        http::{header::AUTHORIZATION, Request},
    };
    use tower::ServiceExt;

    use super::*;
    use crate::{
        domain::{GatewayAccount, GatewayCredential, GatewayWorkspace},
        serving_state::ServingStateError,
        AdmissionError, AdmissionLease, ChatCompletionRequest, FinalizationError,
        FinalizationOutcome, GatewayConfig, GatewayModel, GatewayModelDeployment, ModelRuntime,
        ModelTokenizer, RuntimeCompletion, RuntimeFailure, RuntimeFailureKind, ServingState,
    };

    struct FixedReadiness(bool);

    #[async_trait]
    impl ReadinessCheck for FixedReadiness {
        async fn is_ready(&self) -> bool {
            self.0
        }
    }

    struct MissingServingState {
        credential_lookups: Arc<AtomicUsize>,
    }

    #[async_trait]
    impl ServingState for MissingServingState {
        async fn credential(
            &self,
            _digest_hex: &str,
        ) -> Result<Option<GatewayCredential>, ServingStateError> {
            self.credential_lookups.fetch_add(1, Ordering::SeqCst);
            Ok(None)
        }

        async fn workspace(
            &self,
            _workspace_id: uuid::Uuid,
        ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
            Ok(None)
        }

        async fn account(
            &self,
            _organization_id: uuid::Uuid,
        ) -> Result<Option<GatewayAccount>, ServingStateError> {
            Ok(None)
        }

        async fn model(&self, _model_id: &str) -> Result<Option<GatewayModel>, ServingStateError> {
            Ok(None)
        }

        async fn models(&self) -> Result<Vec<GatewayModel>, ServingStateError> {
            Ok(Vec::new())
        }

        async fn admit(
            &self,
            _generation_id: uuid::Uuid,
            _organization_id: uuid::Uuid,
            _received_at: chrono::DateTime<chrono::Utc>,
            _admitted_at: chrono::DateTime<chrono::Utc>,
            _config: &GatewayConfig,
        ) -> Result<AdmissionLease, AdmissionError> {
            unreachable!("missing credentials cannot reach admission")
        }

        async fn finalize(
            &self,
            _generation_id: uuid::Uuid,
            _organization_id: uuid::Uuid,
            _properties: &crate::GenerationProperties,
        ) -> Result<FinalizationOutcome, FinalizationError> {
            unreachable!("missing credentials cannot reach finalization")
        }
    }

    struct UnusedRuntime;

    #[async_trait]
    impl ModelRuntime for UnusedRuntime {
        async fn complete(
            &self,
            _deployment: &GatewayModelDeployment,
            _request: ChatCompletionRequest,
            _effective_output_tokens: u64,
            _request_deadline: chrono::DateTime<chrono::Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))
        }
    }

    fn application(ready: bool, credential_lookups: Arc<AtomicUsize>) -> Router {
        let config = Arc::new(GatewayConfig {
            bind_address: "127.0.0.1:3002".parse().unwrap(),
            browser_origins: None,
            generation_timeout_seconds: 300,
            lease_finalization_margin_seconds: 60,
            expired_lease_cleanup_grace_seconds: 300,
            prepaid_organization_concurrency_cap: 50,
            balance_per_concurrency_slot_nano_usd: 1_000_000_000,
            settlement_backlog_limit: 100_000,
            valkey_url: "redis://127.0.0.1:6379".to_owned(),
            valkey_iam_cache_name: None,
            valkey_iam_region: None,
            valkey_iam_user: None,
            sglang_api_key: None,
        });
        let serving_state = Arc::new(MissingServingState { credential_lookups });
        let completions = CompletionService::new(
            serving_state.clone(),
            Arc::new(UnusedRuntime),
            ModelTokenizer::new().unwrap(),
            config,
        );
        let coordinator = RequestCoordinator::new(serving_state);
        router(GatewayState::new(
            Arc::new(FixedReadiness(ready)),
            completions,
            coordinator,
        ))
    }

    async fn post_json(application: Router, path: &str, body: &str) -> axum::http::Response<Body> {
        application
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(path)
                    .header("content-type", "application/json")
                    .header(AUTHORIZATION, "Bearer secret")
                    .body(Body::from(body.to_owned()))
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn error_code(response: axum::http::Response<Body>) -> String {
        let body = to_bytes(response.into_body(), 4_096).await.unwrap();
        let value: Value = serde_json::from_slice(&body).unwrap();
        value
            .pointer("/error/code")
            .or(value.pointer("/error/error/code"))
            .cloned()
            .unwrap_or(Value::Null)
            .as_str()
            .unwrap_or_default()
            .to_owned()
    }

    #[tokio::test]
    async fn live_and_ready_are_available_without_authentication() {
        let application = application(true, Arc::new(AtomicUsize::new(0)));

        for path in ["/health/live", "/health/ready"] {
            let response = application
                .clone()
                .oneshot(Request::builder().uri(path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
        }
    }

    #[tokio::test]
    async fn readiness_fails_closed_when_a_dependency_is_unhealthy() {
        let application = application(false, Arc::new(AtomicUsize::new(0)));

        let response = application
            .oneshot(
                Request::builder()
                    .uri("/health/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }

    #[tokio::test]
    async fn metrics_are_available_without_customer_authentication() {
        let response = application(true, Arc::new(AtomicUsize::new(0)))
            .oneshot(
                Request::builder()
                    .uri("/metrics")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), 100_000).await.unwrap();
        let body = std::str::from_utf8(&body).unwrap();
        assert!(body.ends_with("# EOF\n"));
    }

    #[tokio::test]
    async fn browser_cors_allows_only_a_configured_origin() {
        let app = application(true, Arc::new(AtomicUsize::new(0)))
            .layer(browser_cors(vec!["https://gradiated.com".parse().unwrap()]));
        let allowed = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("OPTIONS")
                    .uri("/v1/chat/completions")
                    .header("origin", "https://gradiated.com")
                    .header("access-control-request-method", "POST")
                    .header(
                        "access-control-request-headers",
                        "authorization,content-type",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            allowed.headers()["access-control-allow-origin"],
            "https://gradiated.com"
        );

        let exposed = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/chat/completions")
                    .header("origin", "https://gradiated.com")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        let exposed_headers = exposed.headers()["access-control-expose-headers"]
            .to_str()
            .unwrap();
        assert!(exposed_headers.contains("x-generation-id"));
        assert!(exposed_headers.contains("x-gradiated-service-tier"));

        let denied = app
            .oneshot(
                Request::builder()
                    .method("OPTIONS")
                    .uri("/v1/chat/completions")
                    .header("origin", "https://example.com")
                    .header("access-control-request-method", "POST")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert!(!denied.headers().contains_key("access-control-allow-origin"));
    }

    #[tokio::test]
    async fn inference_routes_answer_under_v1_and_bare_prefixes() {
        for path in [
            "/v1/chat/completions",
            "/chat/completions",
            "/v1/messages",
            "/messages",
            "/v1/responses",
            "/responses",
        ] {
            let response = post_json(
                application(true, Arc::new(AtomicUsize::new(0))),
                path,
                r#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
            )
            .await;
            assert_eq!(
                response.status(),
                StatusCode::UNAUTHORIZED,
                "unexpected status for {path}"
            );
            assert_eq!(error_code(response).await, "invalid_api_key");
        }
    }

    #[tokio::test]
    async fn chat_completions_returns_the_public_error_and_generation_id() {
        let response = application(true, Arc::new(AtomicUsize::new(0)))
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/chat/completions")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let generation_id = response.headers()[GENERATION_ID_HEADER].to_str().unwrap();
        assert_eq!(
            uuid::Uuid::parse_str(generation_id)
                .unwrap()
                .get_version_num(),
            7
        );
        assert_eq!(error_code(response).await, "invalid_api_key");
    }

    #[tokio::test]
    async fn anthropic_routes_render_anthropic_error_envelopes() {
        for path in ["/v1/messages", "/messages", "/v1/messages/count_tokens"] {
            let response = post_json(
                application(true, Arc::new(AtomicUsize::new(0))),
                path,
                r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
            )
            .await;
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "{path}");
            let body = to_bytes(response.into_body(), 4_096).await.unwrap();
            let value: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(value["type"], "error", "{path}");
            assert_eq!(value["error"]["code"], "invalid_api_key", "{path}");
        }
    }

    #[tokio::test]
    async fn x_api_key_authentication_reaches_the_credential_lookup() {
        let credential_lookups = Arc::new(AtomicUsize::new(0));
        let application = application(true, credential_lookups.clone());
        let response = application
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/messages")
                    .header("content-type", "application/json")
                    .header("x-api-key", "secret")
                    .header("anthropic-version", "2023-06-01")
                    .body(Body::from(
                        r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(credential_lookups.load(Ordering::SeqCst), 1);
        assert_eq!(error_code(response).await, "invalid_api_key");
    }

    #[tokio::test]
    async fn responses_stateful_fields_are_rejected() {
        let response = post_json(
            application(true, Arc::new(AtomicUsize::new(0))),
            "/v1/responses",
            r#"{"model":"model-a","input":"hi","store":true}"#,
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(error_code(response).await, "invalid_request");
    }

    #[tokio::test]
    async fn malformed_bodies_render_protocol_envelopes() {
        let response = post_json(
            application(true, Arc::new(AtomicUsize::new(0))),
            "/v1/chat/completions",
            "{oops",
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(error_code(response).await, "invalid_request");

        for path in ["/v1/messages", "/messages"] {
            let response = post_json(
                application(true, Arc::new(AtomicUsize::new(0))),
                path,
                "{oops",
            )
            .await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{path}");
            let body = to_bytes(response.into_body(), 4_096).await.unwrap();
            let value: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(value["type"], "error", "{path}");
            assert_eq!(value["error"]["code"], "invalid_request", "{path}");
        }

        for path in ["/v1/responses", "/responses"] {
            let response = post_json(
                application(true, Arc::new(AtomicUsize::new(0))),
                path,
                "{oops",
            )
            .await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{path}");
            let body = to_bytes(response.into_body(), 4_096).await.unwrap();
            let value: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(value["error"]["code"], "invalid_request", "{path}");
        }
    }

    #[tokio::test]
    async fn streaming_frames_use_the_protocol_event_names() {
        let chunk = StreamItem::Chunk(serde_json::json!({
            "id":"chatcmpl-1","object":"chat.completion.chunk","created":1,"model":"model-a",
            "choices":[{"index":0,"delta":{"role":"assistant","content":"hi"},"logprobs":null,"finish_reason":null}]
        }));

        let response = sse_response(
            Protocol::AnthropicMessages,
            futures_util::stream::iter(vec![chunk.clone(), StreamItem::Done]),
        );
        assert_eq!(response.headers()["x-accel-buffering"], "no");
        let body = to_bytes(response.into_body(), 16_384).await.unwrap();
        let body = String::from_utf8(body.to_vec()).unwrap();
        assert!(body.starts_with("event: message_start\n"));
        assert!(body.contains("event: content_block_delta\n"));
        assert!(body.ends_with("event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"));

        let response = sse_response(
            Protocol::OpenAiResponses,
            futures_util::stream::iter(vec![chunk.clone(), StreamItem::Done]),
        );
        let body = to_bytes(response.into_body(), 16_384).await.unwrap();
        let body = String::from_utf8(body.to_vec()).unwrap();
        assert!(body.starts_with("event: response.created\n"));
        assert!(body.contains("event: response.output_text.delta\n"));

        let response = sse_response(
            Protocol::OpenAiChat,
            futures_util::stream::iter(vec![chunk, StreamItem::Done]),
        );
        let body = to_bytes(response.into_body(), 16_384).await.unwrap();
        let body = String::from_utf8(body.to_vec()).unwrap();
        assert!(!body.contains("event:"));
        assert!(body.ends_with("data: [DONE]\n\n"));
    }

    #[tokio::test]
    async fn streaming_errors_render_the_protocol_envelope_inline() {
        let response = sse_response(
            Protocol::AnthropicMessages,
            futures_util::stream::iter(vec![StreamItem::Error(GatewayError::CapacityExceeded)]),
        );
        let body = to_bytes(response.into_body(), 4_096).await.unwrap();
        let body = String::from_utf8(body.to_vec()).unwrap();
        assert!(body.starts_with("event: error\ndata: "));
        let value: Value = serde_json::from_str(
            body.strip_prefix("event: error\ndata: ")
                .and_then(|rest| rest.strip_suffix("\n\n"))
                .unwrap(),
        )
        .unwrap();
        assert_eq!(value["error"]["code"], "capacity_exceeded");
        assert_eq!(value["error"]["type"], "rate_limit_error");
    }

    #[tokio::test]
    async fn oversized_body_is_rejected_before_serving_state() {
        let credential_lookups = Arc::new(AtomicUsize::new(0));
        let response = application(true, credential_lookups.clone())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/chat/completions")
                    .header(AUTHORIZATION, "Bearer secret")
                    .body(Body::from(vec![b'x'; MAX_REQUEST_BYTES + 1]))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert!(response.headers().contains_key(GENERATION_ID_HEADER));
        assert_eq!(credential_lookups.load(Ordering::SeqCst), 0);
        assert_eq!(error_code(response).await, "payload_too_large");
    }

    #[test]
    fn inbound_translation_happens_exactly_once_per_protocol() {
        let responses_body = Bytes::from_static(
            br#"{"model":"model-a","stream":false,"input":"Reply with exactly: PONG"}"#,
        );
        let translated: Value = serde_json::from_slice(
            &translate_inbound(Protocol::OpenAiResponses, &responses_body).unwrap(),
        )
        .unwrap();
        assert_eq!(
            translated["messages"][0]["content"],
            "Reply with exactly: PONG"
        );

        let chat_body = Bytes::from_static(
            br#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
        );
        let translated: Value =
            serde_json::from_slice(&translate_inbound(Protocol::OpenAiChat, &chat_body).unwrap())
                .unwrap();
        assert_eq!(translated["messages"][0]["content"], "hi");

        let messages_body = Bytes::from_static(
            br#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
        );
        let translated: Value = serde_json::from_slice(
            &translate_inbound(Protocol::AnthropicMessages, &messages_body).unwrap(),
        )
        .unwrap();
        assert_eq!(translated["messages"][0]["role"], "user");
        assert_eq!(translated["messages"][0]["content"], "hi");
    }
}
