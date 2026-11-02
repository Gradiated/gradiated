use std::{sync::Arc, time::Duration};

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, State},
    http::{
        header::{AUTHORIZATION, CONTENT_TYPE},
        HeaderMap, HeaderName, HeaderValue, Method, StatusCode,
    },
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::{get, post, MethodRouter},
    Json, Router,
};
use chrono::Utc;
use futures_util::{Stream, StreamExt};
use serde::Serialize;
use tower_http::cors::{AllowOrigin, CorsLayer};
use tracing::Instrument;
use uuid::Uuid;

use crate::{
    catalog::ProviderCompliance,
    coordinator::ClassifiedRequest,
    diagnostics::limited_warn,
    protocol::{Frame, Protocol, StreamItem},
    readiness::ReadinessCheck,
    CompletionResponse, CompletionService, GatewayError, GatewayMetrics, ModelCatalogResponse,
    QualifiedRequest, RequestCoordinator, RequestKind, RequestMetadata,
};

const MAX_REQUEST_BYTES: usize = 32_000_000;
const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-generation-id");
const SERVICE_TIER_HEADER: HeaderName = HeaderName::from_static("x-gradiated-service-tier");
const DEPLOYMENT_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-deployment-id");
const STREAM_KEEP_ALIVE: Duration = Duration::from_secs(10);

pub fn browser_cors(origins: Vec<HeaderValue>) -> CorsLayer {
    CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([AUTHORIZATION, CONTENT_TYPE, DEPLOYMENT_ID_HEADER])
        .expose_headers([
            GENERATION_ID_HEADER,
            SERVICE_TIER_HEADER,
            DEPLOYMENT_ID_HEADER,
        ])
        .max_age(Duration::from_secs(3600))
}

#[derive(Clone)]
pub struct GatewayState {
    readiness: Arc<dyn ReadinessCheck>,
    compliance: ProviderCompliance,
    completions: CompletionService,
    coordinator: RequestCoordinator,
    metrics: GatewayMetrics,
}

impl GatewayState {
    pub fn new(
        readiness: Arc<dyn ReadinessCheck>,
        completions: CompletionService,
        coordinator: RequestCoordinator,
        compliance: ProviderCompliance,
    ) -> Self {
        let metrics = completions.metrics();

        Self {
            readiness,
            compliance,
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

#[derive(Clone, Copy)]
enum Operation {
    Complete,
    CountTokens,
}

struct Endpoint {
    route: &'static str,
    protocol: Protocol,
    kind: RequestKind,
    operation: Operation,
}

const CHAT_COMPLETIONS: Endpoint = Endpoint {
    route: "chat_completions",
    protocol: Protocol::OpenAiChat,
    kind: RequestKind::Chat,
    operation: Operation::Complete,
};

const SYSTEMONE: Endpoint = Endpoint {
    route: "systemone",
    protocol: Protocol::OpenAiChat,
    kind: RequestKind::SystemOne,
    operation: Operation::Complete,
};

const MESSAGES: Endpoint = Endpoint {
    route: "messages",
    protocol: Protocol::AnthropicMessages,
    kind: RequestKind::Chat,
    operation: Operation::Complete,
};

const COUNT_TOKENS: Endpoint = Endpoint {
    route: "messages_count_tokens",
    protocol: Protocol::AnthropicMessages,
    kind: RequestKind::Chat,
    operation: Operation::CountTokens,
};

const RESPONSES: Endpoint = Endpoint {
    route: "responses",
    protocol: Protocol::OpenAiResponses,
    kind: RequestKind::Chat,
    operation: Operation::Complete,
};

fn inference_routes() -> Router<GatewayState> {
    Router::new()
        .route("/chat/completions", endpoint(&CHAT_COMPLETIONS))
        .route("/systemone", endpoint(&SYSTEMONE))
        .route("/messages", endpoint(&MESSAGES))
        .route("/messages/count_tokens", endpoint(&COUNT_TOKENS))
        .route("/responses", endpoint(&RESPONSES))
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

fn endpoint(endpoint: &'static Endpoint) -> MethodRouter<GatewayState> {
    post(
        move |State(state): State<GatewayState>,
              headers: HeaderMap,
              body: Result<Bytes, BytesRejection>| {
            inference(state, headers, body, endpoint)
        },
    )
}

fn request_metadata(headers: &HeaderMap) -> RequestMetadata {
    let generation_id = headers
        .get(&GENERATION_ID_HEADER)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| Uuid::parse_str(value).ok())
        .filter(|id| id.get_version_num() == 7)
        .unwrap_or_else(Uuid::now_v7);

    RequestMetadata {
        generation_id,
        received_at: Utc::now(),
    }
}

fn body_rejection(rejection: BytesRejection) -> GatewayError {
    if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE {
        return GatewayError::PayloadTooLarge;
    }

    limited_warn!(error_code = "body_read_failed", "request body rejected");

    GatewayError::invalid_request(None)
}

async fn inference(
    state: GatewayState,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
    endpoint: &Endpoint,
) -> Response {
    let metadata = request_metadata(&headers);
    let generation_id = metadata.generation_id;

    async {
        let mut is_verification = false;
        let result = serve(
            &state,
            endpoint,
            metadata,
            &headers,
            body,
            &mut is_verification,
        )
        .await;

        finish(&state, endpoint, generation_id, result, is_verification)
    }
    .instrument(crate::diagnostics::request_span(generation_id, &headers))
    .await
}

async fn serve(
    state: &GatewayState,
    endpoint: &Endpoint,
    metadata: RequestMetadata,
    headers: &HeaderMap,
    body: Result<Bytes, BytesRejection>,
    is_verification: &mut bool,
) -> Result<Response, GatewayError> {
    let body = body.map_err(body_rejection)?;

    let ClassifiedRequest { hosted, request } = state
        .coordinator
        .classify_with_traffic(
            headers,
            &body,
            metadata.received_at,
            endpoint.protocol,
            is_verification,
        )
        .await?;
    if matches!(endpoint.operation, Operation::CountTokens)
        && headers.contains_key(&DEPLOYMENT_ID_HEADER)
    {
        return Err(GatewayError::invalid_request(Some(
            "x-gradiated-deployment-id",
        )));
    }
    crate::session_telemetry::record_body(&request);
    let translated = endpoint.protocol.translate_request(&request)?;
    let qualified =
        state
            .coordinator
            .qualify(metadata, headers, hosted, &translated, endpoint.kind)?;

    let targeted = headers.contains_key(&DEPLOYMENT_ID_HEADER);
    let deployment_id = qualified.deployment.id;
    let mut response = match endpoint.operation {
        Operation::Complete => complete(state, endpoint.protocol, qualified).await,
        Operation::CountTokens => count_tokens(state, &qualified).await,
    }?;

    if targeted {
        response
            .headers_mut()
            .insert(DEPLOYMENT_ID_HEADER, generation_id_header(deployment_id));
    }

    Ok(response)
}

fn finish(
    state: &GatewayState,
    endpoint: &Endpoint,
    generation_id: Uuid,
    result: Result<Response, GatewayError>,
    is_verification: bool,
) -> Response {
    let mut response = record(
        state,
        endpoint.route,
        Some(generation_id),
        result,
        is_verification,
        |error| endpoint.protocol.error_response(error),
    );

    response
        .headers_mut()
        .insert(GENERATION_ID_HEADER, generation_id_header(generation_id));

    response
}

fn record(
    state: &GatewayState,
    route: &'static str,
    generation_id: Option<Uuid>,
    result: Result<Response, GatewayError>,
    is_verification: bool,
    render: impl FnOnce(GatewayError) -> Response,
) -> Response {
    let error_code = match &result {
        Ok(_) => "none",
        Err(error) => {
            limited_warn!(
                generation_id = generation_id.map(tracing::field::display),
                route,
                status = error.status().as_u16(),
                error_code = error.code(),
                parameter = error.param(),
                "request rejected"
            );
            error.code()
        }
    };

    let response = result.unwrap_or_else(render);
    state.metrics.record_http(
        route,
        response.status().as_u16(),
        error_code,
        is_verification,
    );

    response
}

fn generation_id_header(generation_id: Uuid) -> HeaderValue {
    HeaderValue::from_str(&generation_id.to_string())
        .expect("a UUID is always a valid HTTP header value")
}

async fn complete(
    state: &GatewayState,
    protocol: Protocol,
    qualified: QualifiedRequest,
) -> Result<Response, GatewayError> {
    let (mut response, service_tier) = match state.completions.complete(qualified).await? {
        CompletionResponse::NonStreaming {
            result,
            service_tier,
        } => {
            let body = protocol.translate_response(result.into_response())?;
            (Json(body).into_response(), service_tier)
        }
        CompletionResponse::Streaming {
            result,
            service_tier,
        } => (sse_response(protocol, result.into_stream()), service_tier),
    };

    response.headers_mut().insert(
        SERVICE_TIER_HEADER,
        HeaderValue::from_static(service_tier.as_str()),
    );

    Ok(response)
}

async fn count_tokens(
    state: &GatewayState,
    qualified: &QualifiedRequest,
) -> Result<Response, GatewayError> {
    let count = state.completions.count_tokens(qualified).await?;

    Ok(Json(serde_json::json!({ "input_tokens": count })).into_response())
}

fn sse_response(
    protocol: Protocol,
    stream: impl Stream<Item = StreamItem> + Send + 'static,
) -> Response {
    let mut renderer = protocol.stream_renderer();
    let events = stream.flat_map(move |item| {
        futures_util::stream::iter(
            renderer
                .render(item)
                .into_iter()
                .map(|frame| Ok::<_, axum::Error>(Event::from(frame))),
        )
    });

    let mut response = Sse::new(events)
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

impl From<Frame> for Event {
    fn from(frame: Frame) -> Self {
        let event = Event::default();
        let event = match frame.event {
            Some(name) => event.event(name),
            None => event,
        };

        event.data(frame.data)
    }
}

async fn models(State(state): State<GatewayState>, headers: HeaderMap) -> Response {
    let result = state
        .coordinator
        .list_models(&headers, Utc::now())
        .await
        .map(|models| {
            Json(ModelCatalogResponse::from_models(&models, state.compliance)).into_response()
        });

    record(
        &state,
        "models",
        None,
        result,
        false,
        IntoResponse::into_response,
    )
}

async fn live() -> Json<HealthResponse> {
    Json(HealthResponse { status: "live" })
}

async fn ready(State(state): State<GatewayState>) -> (StatusCode, Json<HealthResponse>) {
    let ready = !state.completions.is_draining() && state.readiness.is_ready().await;
    state.metrics.set_dependency_ready("gateway", ready);

    let (status_code, status) = if ready {
        (StatusCode::OK, "ready")
    } else {
        (StatusCode::SERVICE_UNAVAILABLE, "not_ready")
    };

    (status_code, Json(HealthResponse { status }))
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
    use axum::{
        body::{to_bytes, Body},
        http::Request,
    };
    use serde_json::Value;
    use tower::ServiceExt;

    use super::{
        support::{json_body, json_request, router_for},
        *,
    };
    use crate::test_support::TestServingState;

    fn observed_application() -> (Router, Arc<TestServingState>) {
        let state = Arc::new(TestServingState::unknown_credential());
        let application = router_for(true, state.clone());

        (application, state)
    }

    fn application() -> Router {
        observed_application().0
    }

    async fn post_json(application: Router, path: &str, body: &str) -> Response {
        application
            .oneshot(json_request(
                path,
                &[("authorization", "Bearer secret")],
                body.to_owned(),
            ))
            .await
            .unwrap()
    }

    async fn error_code(response: Response) -> Value {
        json_body(response).await["error"]["code"].clone()
    }

    #[tokio::test]
    async fn live_and_ready_are_available_without_authentication() {
        let application = application();

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
        let application = router_for(false, Arc::new(TestServingState::unknown_credential()));

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
    async fn authorised_verification_http_failures_keep_their_traffic_class() {
        for (verification, model_unavailable) in
            [(false, false), (true, false), (false, true), (true, true)]
        {
            let mut state = TestServingState::ready();
            state.admission_unavailable = true;
            let model = state.model.as_mut().unwrap();
            let target = model.deployments[0].id.to_string();
            if model_unavailable {
                model.status = crate::model::ModelStatus::Unavailable;
            }
            let app = super::support::router_for_with_verification(
                true,
                Arc::new(state),
                Some(crate::test_support::WORKSPACE_ID),
            );
            let mut headers = vec![("authorization", "Bearer grad_test")];
            if verification {
                headers.push(("x-gradiated-deployment-id", target.as_str()));
            }
            let response = app
                .clone()
                .oneshot(json_request(
                    "/v1/chat/completions",
                    &headers,
                    r#"{"model":"model-a","messages":[{"role":"user","content":"Hi"}]}"#,
                ))
                .await
                .unwrap();
            let expected = if model_unavailable {
                StatusCode::NOT_FOUND
            } else {
                StatusCode::SERVICE_UNAVAILABLE
            };
            assert_eq!(response.status(), expected);
            let response = app
                .oneshot(
                    Request::builder()
                        .uri("/metrics")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            let body = to_bytes(response.into_body(), 100_000).await.unwrap();
            let body = std::str::from_utf8(&body).unwrap();
            let row = body
                .lines()
                .find(|line| line.starts_with("gradiated_gateway_http_requests_total{"))
                .unwrap();
            let traffic = if verification {
                "verification"
            } else {
                "routed"
            };
            assert!(row.contains(&format!("traffic=\"{traffic}\"")), "{row}");
            assert!(
                row.contains(&format!("status=\"{}\"", expected.as_u16())),
                "{row}"
            );
        }
    }

    #[tokio::test]
    async fn token_count_cannot_acknowledge_a_replica_target() {
        for path in ["/v1/messages/count_tokens", "/messages/count_tokens"] {
            let state = TestServingState::ready();
            let id = state.model.as_ref().unwrap().deployments[0].id.to_string();
            let response = router_for(true, Arc::new(state))
                .oneshot(json_request(
                    path,
                    &[
                        ("authorization", "Bearer grad_test"),
                        ("x-gradiated-deployment-id", id.as_str()),
                    ],
                    r#"{"model":"model-a","messages":[{"role":"user","content":"Hi"}]}"#,
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
            assert!(!response.headers().contains_key(&DEPLOYMENT_ID_HEADER));
        }
    }

    #[tokio::test]
    async fn an_ordinary_targeted_request_cannot_hide_http_failures() {
        let mut state = TestServingState::ready();
        let model = state.model.as_mut().unwrap();
        let target = model.deployments[0].id.to_string();
        model.status = crate::model::ModelStatus::Unavailable;
        let app = router_for(true, Arc::new(state));
        let response = app
            .clone()
            .oneshot(json_request(
                "/v1/chat/completions",
                &[
                    ("authorization", "Bearer grad_test"),
                    ("x-gradiated-deployment-id", target.as_str()),
                ],
                r#"{"model":"model-a","messages":[{"role":"user","content":"Hi"}]}"#,
            ))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/metrics")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = to_bytes(response.into_body(), 100_000).await.unwrap();
        let body = std::str::from_utf8(&body).unwrap();
        let row = body
            .lines()
            .find(|line| line.starts_with("gradiated_gateway_http_requests_total{"))
            .unwrap();
        assert!(row.contains("traffic=\"routed\""), "{row}");
    }

    #[tokio::test]
    async fn metrics_are_available_without_customer_authentication() {
        let response = application()
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
        let app = application().layer(browser_cors(vec!["https://gradiated.com".parse().unwrap()]));
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
                        "authorization,content-type,x-gradiated-deployment-id",
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
        assert!(allowed.headers()["access-control-allow-headers"]
            .to_str()
            .unwrap()
            .contains("x-gradiated-deployment-id"));

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
        assert!(exposed_headers.contains("x-gradiated-generation-id"));
        assert!(exposed_headers.contains("x-gradiated-service-tier"));
        assert!(exposed_headers.contains("x-gradiated-deployment-id"));

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
                application(),
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
    async fn the_proxy_generation_id_is_used_when_it_is_a_uuid_v7() {
        let minted = uuid::Uuid::now_v7().to_string();
        let v4 = "123e4567-e89b-42d3-a456-426614174000";

        for (supplied, kept) in [(minted.as_str(), true), (v4, false), ("not-a-uuid", false)] {
            let response = application()
                .oneshot(json_request(
                    "/v1/chat/completions",
                    &[("x-gradiated-generation-id", supplied)],
                    r#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
                ))
                .await
                .unwrap();

            let returned = response.headers()[GENERATION_ID_HEADER].to_str().unwrap();
            assert_eq!(returned == supplied, kept, "{supplied}");
            assert_eq!(
                uuid::Uuid::parse_str(returned).unwrap().get_version_num(),
                7,
                "{supplied}"
            );
        }
    }

    #[tokio::test]
    async fn chat_completions_returns_the_public_error_and_generation_id() {
        let response = application()
            .oneshot(json_request(
                "/v1/chat/completions",
                &[],
                r#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#,
            ))
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
                application(),
                path,
                r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
            )
            .await;
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED, "{path}");
            let value = json_body(response).await;
            assert_eq!(value["type"], "error", "{path}");
            assert_eq!(value["error"]["code"], "invalid_api_key", "{path}");
        }
    }

    #[tokio::test]
    async fn x_api_key_authentication_reaches_the_credential_lookup() {
        let (application, serving_state) = observed_application();
        let response = application
            .oneshot(json_request(
                "/v1/messages",
                &[("x-api-key", "grad_test"), ("anthropic-version", "2023-06-01")],
                r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
            ))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(serving_state.lookups("credential"), 1);
        assert_eq!(error_code(response).await, "invalid_api_key");
    }

    #[tokio::test]
    async fn responses_stateful_fields_are_rejected() {
        for (body, field) in [
            (r#"{"model":"model-a","input":"hi","store":true}"#, "store"),
            (
                r#"{"model":"model-a","input":"hi","previous_response_id":"resp_1"}"#,
                "previous_response_id",
            ),
            (
                r#"{"model":"model-a","input":"hi","conversation":"c_1"}"#,
                "conversation",
            ),
            (
                r#"{"model":"model-a","input":"hi","conversation":{"id":"conv_1"}}"#,
                "conversation",
            ),
            (
                r#"{"model":"model-a","input":"hi","prompt":{"id":"pmpt_1"}}"#,
                "prompt",
            ),
            (
                r#"{"model":"model-a","input":"hi","background":true}"#,
                "background",
            ),
        ] {
            let response = post_json(application(), "/v1/responses", body).await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{field}");

            let value = json_body(response).await;
            assert_eq!(value["error"]["code"], "invalid_request", "{field}");
            assert_eq!(value["error"]["param"], field);
        }
    }

    #[tokio::test]
    async fn malformed_bodies_render_protocol_envelopes() {
        let response = post_json(application(), "/v1/chat/completions", "{oops").await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(error_code(response).await, "invalid_request");

        for path in ["/v1/messages", "/messages"] {
            let response = post_json(application(), path, "{oops").await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{path}");
            let value = json_body(response).await;
            assert_eq!(value["type"], "error", "{path}");
            assert_eq!(value["error"]["code"], "invalid_request", "{path}");
        }

        for path in ["/v1/responses", "/responses"] {
            let response = post_json(application(), path, "{oops").await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{path}");
            assert_eq!(error_code(response).await, "invalid_request", "{path}");
        }
    }

    #[tokio::test]
    async fn streaming_frames_use_the_sse_wire_format() {
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
        assert!(body.ends_with("event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"));

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
    async fn an_unreadable_body_is_an_invalid_request_before_serving_state() {
        let (application, serving_state) = observed_application();
        let failing = futures_util::stream::iter([Err::<Bytes, _>(std::io::Error::other(
            "client disconnected",
        ))]);

        let response = application
            .oneshot(json_request(
                "/v1/chat/completions",
                &[("authorization", "Bearer secret")],
                Body::from_stream(failing),
            ))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert!(response.headers().contains_key(GENERATION_ID_HEADER));
        assert_eq!(serving_state.lookups("credential"), 0);
        assert_eq!(error_code(response).await, "invalid_request");
    }

    #[tokio::test]
    async fn oversized_body_is_rejected_before_serving_state() {
        let (application, serving_state) = observed_application();
        let response = application
            .oneshot(json_request(
                "/v1/chat/completions",
                &[("authorization", "Bearer secret")],
                vec![b'x'; MAX_REQUEST_BYTES + 1],
            ))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert!(response.headers().contains_key(GENERATION_ID_HEADER));
        assert_eq!(serving_state.lookups("credential"), 0);
        assert_eq!(error_code(response).await, "payload_too_large");
    }

    #[tokio::test]
    async fn rejected_requests_keep_verified_ids_and_never_credentials() {
        let logs = crate::diagnostics::capture::Logs::default();
        let _guard = logs.start();
        let mut archived = TestServingState::ready();
        archived.workspace.as_mut().unwrap().archived_at = Some(Utc::now());

        for (state, authenticated) in [
            (archived, true),
            (TestServingState::unknown_credential(), false),
        ] {
            let app = router_for(true, Arc::new(state));
            let request = Request::builder()
                .method("POST")
                .uri("/v1/messages")
                .header("content-type", "application/json")
                .header("x-gradiated-api-key", "grad_DO_NOT_LOG_THIS")
                .body(Body::from(
                    r#"{"model":"model-a","max_tokens":16,"messages":[{"role":"user","content":"PRIVATE_PROMPT"}]}"#,
                ))
                .unwrap();
            let response = app.oneshot(request).await.unwrap();

            let events = logs.events();
            let event = events.last().unwrap();
            assert_eq!(
                event["span"]["generation_id"],
                response.headers()[GENERATION_ID_HEADER].to_str().unwrap()
            );
            for (key, id) in [
                ("organization_id", crate::test_support::ORGANIZATION_ID),
                ("workspace_id", crate::test_support::WORKSPACE_ID),
                ("api_key_id", crate::test_support::API_KEY_ID),
            ] {
                if authenticated {
                    assert_eq!(event["span"][key], id.to_string());
                } else {
                    assert!(event["span"].get(key).is_none());
                }
            }

            let logged = serde_json::to_string(&events).unwrap();
            assert!(!logged.contains("DO_NOT_LOG_THIS"));
            assert!(!logged.contains("PRIVATE_PROMPT"));
        }
    }
}

#[cfg(test)]
#[path = "http_support.rs"]
mod support;
