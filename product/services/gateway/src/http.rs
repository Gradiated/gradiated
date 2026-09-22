use std::{sync::Arc, time::Duration};

use axum::{
    body::{Body, Bytes},
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
use tower_http::cors::{AllowOrigin, CorsLayer};
use uuid::Uuid;

use crate::{
    auth::ProviderCredential,
    coordinator::RequestRoute,
    protocol::{Frame, Protocol, StreamItem},
    readiness::ReadinessCheck,
    relay::{upstream_headers, ProviderRelay, RelayRoute},
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
    relay: ProviderRelay,
    metrics: GatewayMetrics,
}

impl GatewayState {
    pub fn new(
        readiness: Arc<dyn ReadinessCheck>,
        completions: CompletionService,
        coordinator: RequestCoordinator,
        relay: ProviderRelay,
    ) -> Self {
        let metrics = completions.metrics();
        Self {
            readiness,
            completions,
            coordinator,
            relay,
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

fn error_code(result: &Result<Response, GatewayError>) -> &'static str {
    result
        .as_ref()
        .err()
        .map(GatewayError::code)
        .unwrap_or("none")
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
    let error = error_code(&result);
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

fn body_rejection(rejection: BytesRejection) -> GatewayError {
    if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE {
        GatewayError::PayloadTooLarge
    } else {
        GatewayError::invalid_request(None)
    }
}

async fn inference(
    state: GatewayState,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
    route: &'static str,
    protocol: Protocol,
    relay: Option<RelayRoute>,
) -> Response {
    let metadata = request_metadata();
    let generation_id = metadata.generation_id;
    let result = async {
        let body = body.map_err(body_rejection)?;

        serve(&state, protocol, relay, metadata, &headers, body).await
    }
    .await;

    finish(&state, route, protocol, generation_id, result)
}

/// Classifies the request once, then either relays it or serves it here. Identity,
/// the model projection and the caller's body are each resolved a single time.
async fn serve(
    state: &GatewayState,
    protocol: Protocol,
    relay: Option<RelayRoute>,
    metadata: RequestMetadata,
    headers: &HeaderMap,
    body: Bytes,
) -> Result<Response, GatewayError> {
    let classified = state
        .coordinator
        .classify(headers, &body, metadata.received_at, protocol, relay)
        .await?;

    match classified {
        RequestRoute::Relay {
            route, credential, ..
        } => {
            relay_response(
                state,
                metadata.generation_id,
                route,
                headers,
                &credential,
                body,
            )
            .await
        }
        RequestRoute::Hosted { hosted, request } => {
            let translated = protocol.translate_request(&request).map(Bytes::from)?;
            let qualified = state
                .coordinator
                .qualify(metadata, headers, *hosted, &translated)?;

            complete_with_protocol(state, protocol, qualified).await
        }
    }
}

async fn complete_with_protocol(
    state: &GatewayState,
    protocol: Protocol,
    qualified: crate::QualifiedRequest,
) -> Result<Response, GatewayError> {
    match state.completions.complete(qualified).await? {
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

/// Returns the provider's status, headers and bytes. Nothing here inspects or
/// rewrites the provider's payload.
async fn relay_response(
    state: &GatewayState,
    generation_id: Uuid,
    route: RelayRoute,
    headers: &HeaderMap,
    credential: &ProviderCredential<'_>,
    body: Bytes,
) -> Result<Response, GatewayError> {
    let upstream = upstream_headers(headers, route, credential)?;
    let relayed = state.relay.send(route, upstream, body).await?;

    let mut response = Response::new(Body::from_stream(relayed.body));
    *response.status_mut() = relayed.status;
    *response.headers_mut() = relayed.headers;
    response
        .headers_mut()
        .insert(GENERATION_ID_HEADER, generation_id_header(generation_id));

    Ok(response)
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
    let result = state
        .coordinator
        .list_models(&headers, Utc::now())
        .await
        .map(|models| Json(ModelCatalogResponse::from_models(&models)).into_response());
    let error = error_code(&result);
    let response = result.unwrap_or_else(IntoResponse::into_response);
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
    inference(
        state,
        headers,
        body,
        "chat_completions",
        Protocol::OpenAiChat,
        None,
    )
    .await
}

async fn messages(
    State(state): State<GatewayState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    inference(
        state,
        headers,
        body,
        "messages",
        Protocol::AnthropicMessages,
        Some(RelayRoute::AnthropicMessages),
    )
    .await
}

async fn responses(
    State(state): State<GatewayState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    inference(
        state,
        headers,
        body,
        "responses",
        Protocol::OpenAiResponses,
        None,
    )
    .await
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
        let classified = state
            .coordinator
            .classify(
                &headers,
                &body,
                metadata.received_at,
                Protocol::AnthropicMessages,
                // Counting tokens has no relay path in this build, so an unresolved
                // name stays a local error even when a provider key is present.
                None,
            )
            .await?;
        let RequestRoute::Hosted { hosted, request } = classified else {
            return Err(GatewayError::ModelNotFound);
        };

        let translated = Protocol::AnthropicMessages.translate_request(&request)?;
        let qualified = state
            .coordinator
            .qualify(metadata, &headers, *hosted, &translated)?;
        let count = state.completions.count_tokens(&qualified).await?;

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
    use async_trait::async_trait;
    use axum::{
        body::{to_bytes, Body},
        http::{header::AUTHORIZATION, Request},
    };
    use serde_json::Value;
    use tower::ServiceExt;

    use super::*;
    use crate::{
        test_support::TestServingState, ChatCompletionRequest, GatewayConfig,
        GatewayModelDeployment, ModelRuntime, ModelTokenizer, RuntimeCompletion, RuntimeFailure,
        RuntimeFailureKind,
    };

    pub(super) struct FixedReadiness(pub(super) bool);

    #[async_trait]
    impl ReadinessCheck for FixedReadiness {
        async fn is_ready(&self) -> bool {
            self.0
        }
    }

    pub(super) struct UnusedRuntime;

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

    fn application(ready: bool) -> Router {
        let state = Arc::new(TestServingState::unknown_credential());

        router_for(
            ready,
            state,
            &GatewayConfig::for_tests().proxy_anthropic_origin,
        )
    }

    /// Builds the real router over a fixture, with the relay pointed wherever the
    /// caller needs it.
    pub(super) fn router_for(
        ready: bool,
        serving_state: Arc<TestServingState>,
        proxy_origin: &str,
    ) -> Router {
        let test_config = GatewayConfig::for_tests();
        let config = Arc::new(test_config.clone());
        let completions = CompletionService::new(
            serving_state.clone(),
            Arc::new(UnusedRuntime),
            ModelTokenizer::new().unwrap(),
            config,
        );
        let coordinator = RequestCoordinator::new(serving_state);
        let relay = ProviderRelay::new(proxy_origin, test_config.proxy_limits()).unwrap();
        router(GatewayState::new(
            Arc::new(FixedReadiness(ready)),
            completions,
            coordinator,
            relay,
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
        let application = application(true);

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
        let application = application(false);

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
        let response = application(true)
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
        let app =
            application(true).layer(browser_cors(vec!["https://gradiated.com".parse().unwrap()]));
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
                application(true),
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
        let response = application(true)
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
                application(true),
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
        let serving_state = Arc::new(TestServingState::unknown_credential());
        let response = router_for(
            true,
            serving_state.clone(),
            &GatewayConfig::for_tests().proxy_anthropic_origin,
        )
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/messages")
                    .header("content-type", "application/json")
                    .header("x-api-key", "grad_test")
                    .header("anthropic-version", "2023-06-01")
                    .body(Body::from(
                        r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(serving_state.lookups("credential"), 1);
        assert_eq!(error_code(response).await, "invalid_api_key");
    }

    #[tokio::test]
    async fn responses_stateful_fields_are_rejected() {
        let response = post_json(
            application(true),
            "/v1/responses",
            r#"{"model":"model-a","input":"hi","store":true}"#,
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(error_code(response).await, "invalid_request");
    }

    #[tokio::test]
    async fn malformed_bodies_render_protocol_envelopes() {
        let response = post_json(application(true), "/v1/chat/completions", "{oops").await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(error_code(response).await, "invalid_request");

        for path in ["/v1/messages", "/messages"] {
            let response = post_json(application(true), path, "{oops").await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{path}");
            let body = to_bytes(response.into_body(), 4_096).await.unwrap();
            let value: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(value["type"], "error", "{path}");
            assert_eq!(value["error"]["code"], "invalid_request", "{path}");
        }

        for path in ["/v1/responses", "/responses"] {
            let response = post_json(application(true), path, "{oops").await;
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
        let serving_state = Arc::new(TestServingState::unknown_credential());
        let response = router_for(
            true,
            serving_state.clone(),
            &GatewayConfig::for_tests().proxy_anthropic_origin,
        )
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
        assert_eq!(serving_state.lookups("credential"), 0);
        assert_eq!(error_code(response).await, "payload_too_large");
    }

    #[tokio::test]
    async fn a_closed_workspace_or_organization_is_refused_without_retry() {
        for (failure, code) in [
            ("archived", "workspace_archived"),
            ("suspended", "organization_suspended"),
        ] {
            let mut state = TestServingState::ready();
            match failure {
                "archived" => {
                    state.workspace.as_mut().unwrap().archived_at = Some(chrono::Utc::now())
                }
                _ => {
                    state.account.as_mut().unwrap().organization_status =
                        crate::domain::OrganizationStatus::Suspended
                }
            }
            let application = router_for(
                true,
                Arc::new(state),
                &GatewayConfig::for_tests().proxy_anthropic_origin,
            );

            let response = application
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri("/v1/messages")
                        .header("content-type", "application/json")
                        .header("x-gradiated-api-key", "grad_test")
                        .header("anthropic-version", "2023-06-01")
                        .body(Body::from(
                            r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();

            assert_eq!(response.status(), StatusCode::FORBIDDEN, "{failure}");
            assert_eq!(error_code(response).await, code, "{failure}");
        }
    }

    /// The pipeline translates the request that classification already parsed.
    fn translate(protocol: Protocol, body: &[u8]) -> Value {
        let request: Value = serde_json::from_slice(body).unwrap();
        serde_json::from_slice(&protocol.translate_request(&request).unwrap()).unwrap()
    }

    #[test]
    fn inbound_translation_happens_exactly_once_per_protocol() {
        let translated = translate(
            Protocol::OpenAiResponses,
            br#"{"model":"model-a","stream":false,"input":"Reply with exactly: PONG"}"#,
        );
        assert_eq!(
            translated["messages"][0]["content"],
            "Reply with exactly: PONG"
        );

        let translated = translate(
            Protocol::OpenAiChat,
            br#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
        );
        assert_eq!(translated["messages"][0]["content"], "hi");

        let translated = translate(
            Protocol::AnthropicMessages,
            br#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
        );
        assert_eq!(translated["messages"][0]["role"], "user");
        assert_eq!(translated["messages"][0]["content"], "hi");
    }
}

#[cfg(test)]
#[path = "http_relay_tests.rs"]
mod relay_route_tests;
