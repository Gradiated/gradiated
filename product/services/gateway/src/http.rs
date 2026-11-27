use std::{
    sync::Arc,
    time::{Duration, Instant},
};

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, State},
    http::{
        header::{AUTHORIZATION, CONTENT_ENCODING, CONTENT_LENGTH, CONTENT_TYPE, RETRY_AFTER},
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
    coordinator::{Authorization, ClassifiedRequest},
    diagnostics::limited_warn,
    protocol::{Frame, Protocol, StreamItem},
    readiness::ReadinessCheck,
    CompletionResponse, CompletionService, GatewayError, GatewayMetrics, ModelCatalogResponse,
    QualifiedRequest, RequestCoordinator, RequestKind, RequestMetadata,
};

const MAX_REQUEST_BYTES: usize = 32_000_000;
/// Compressed bodies inflated at once: each holds at most a 32 MiB zstd window and 32 MB of output.
static DECOMPRESSION_SLOTS: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(4);
const ZSTD_WINDOW_LOG_MAX: u32 = 25;
/// How long a compressed body waits for a slot before a retryable overloaded error; ordinary bodies inflate in
/// well under a millisecond.
const DECOMPRESSION_WAIT: Duration = Duration::from_secs(2);
const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-generation-id");
/// The TypeSafe SDK reads `requestId` from this header.
const TYPESAFE_REQUEST_ID_HEADER: HeaderName = HeaderName::from_static("x-typesafe-request-id");
const SERVICE_TIER_HEADER: HeaderName = HeaderName::from_static("x-gradiated-service-tier");
const DEPLOYMENT_ID_HEADER: HeaderName = HeaderName::from_static("x-gradiated-deployment-id");
const STREAM_KEEP_ALIVE: Duration = Duration::from_secs(10);

pub fn browser_cors(origins: Vec<HeaderValue>) -> CorsLayer {
    CorsLayer::new()
        .allow_origin(AllowOrigin::list(origins))
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([
            AUTHORIZATION,
            CONTENT_TYPE,
            CONTENT_ENCODING,
            DEPLOYMENT_ID_HEADER,
        ])
        .expose_headers([
            GENERATION_ID_HEADER,
            TYPESAFE_REQUEST_ID_HEADER,
            SERVICE_TIER_HEADER,
            DEPLOYMENT_ID_HEADER,
            RETRY_AFTER,
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

#[derive(Clone, Copy)]
enum Codec {
    Zstd,
    Gzip,
}

/// Inflates a zstd or gzip body (the TypeSafe SDK compresses bodies of 1 KiB or more) once the credential is known;
/// any other encoding is an invalid request.
async fn decoded(
    state: &GatewayState,
    headers: &HeaderMap,
    body: Bytes,
    received_at: chrono::DateTime<Utc>,
) -> Result<(HeaderMap, Bytes, Option<Authorization>), GatewayError> {
    let unsupported = || GatewayError::invalid_request(Some("content-encoding"));
    let mut values = headers.get_all(CONTENT_ENCODING).iter();
    let (Some(value), None) = (values.next(), values.next()) else {
        return Err(unsupported());
    };
    let codec = match value
        .to_str()
        .map(|v| v.trim().to_ascii_lowercase())
        .as_deref()
    {
        Ok("identity") => None,
        Ok("zstd") => Some(Codec::Zstd),
        Ok("gzip" | "x-gzip") => Some(Codec::Gzip),
        _ => return Err(unsupported()),
    };
    let mut headers = headers.clone();
    headers.remove(CONTENT_ENCODING);
    headers.remove(CONTENT_LENGTH);
    let Some(codec) = codec else {
        return Ok((headers, body, None));
    };
    let authorization = state
        .coordinator
        .authenticate(&headers, received_at)
        .await?;
    let body = inflate_in_slot(&DECOMPRESSION_SLOTS, codec, body).await?;

    Ok((headers, body, Some(authorization)))
}

/// Inflates on a blocking thread holding one of `slots`; the permit moves into the task, so a cancelled request
/// keeps its slot until inflation ends.
async fn inflate_in_slot(
    slots: &'static tokio::sync::Semaphore,
    codec: Codec,
    body: Bytes,
) -> Result<Bytes, GatewayError> {
    // A bounded wait: a caller cannot queue compressed bodies indefinitely ahead of admission.
    let slot = tokio::time::timeout(DECOMPRESSION_WAIT, slots.acquire())
        .await
        .map_err(|_| GatewayError::ProxyOverloaded)?
        .map_err(|_| GatewayError::ProxyOverloaded)?;
    tokio::task::spawn_blocking(move || {
        let _slot = slot;
        inflate(codec, &body)
    })
    .await
    .map_err(|_| GatewayError::invalid_request(None))?
}

fn inflate(codec: Codec, body: &[u8]) -> Result<Bytes, GatewayError> {
    use std::io::Read;

    let invalid = |_| {
        limited_warn!(
            error_code = "body_decode_failed",
            "compressed request body rejected"
        );
        GatewayError::invalid_request(None)
    };
    let reader: Box<dyn Read + '_> = match codec {
        Codec::Zstd => {
            let mut decoder = zstd::stream::read::Decoder::new(body).map_err(invalid)?;
            // The decoder otherwise accepts a 128 MiB history window from a tiny frame; 32 MiB matches the body limit.
            decoder
                .window_log_max(ZSTD_WINDOW_LOG_MAX)
                .map_err(invalid)?;
            Box::new(decoder)
        }
        Codec::Gzip => Box::new(flate2::read::MultiGzDecoder::new(body)),
    };
    let mut out = Vec::new();
    reader
        .take(MAX_REQUEST_BYTES as u64 + 1)
        .read_to_end(&mut out)
        .map_err(invalid)?;
    if out.len() > MAX_REQUEST_BYTES {
        return Err(GatewayError::PayloadTooLarge);
    }

    Ok(out.into())
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
    let decoded_headers;
    let (headers, body, authorization) = if headers.contains_key(CONTENT_ENCODING) {
        let (decoded, body, authorization) =
            decoded(state, headers, body, metadata.received_at).await?;
        decoded_headers = decoded;
        (&decoded_headers, body, authorization)
    } else {
        (headers, body, None)
    };

    // An eval request that finds its pool at zero wakes it and waits for the
    // replica; each attempt starts its generation deadline afresh. Waiters are
    // bounded per process, so the rest answer at once and grad retries them.
    let waiting_until = Instant::now() + state.coordinator.eval_cold_start_wait();
    let mut metadata = metadata;
    let mut authorization = authorization;
    let mut waiter = None;
    loop {
        match attempt(
            state,
            endpoint,
            metadata.clone(),
            headers,
            &body,
            is_verification,
            authorization.take(),
        )
        .await
        {
            Err(GatewayError::CapacityUnavailable { wake }) => {
                if let Some(model) = &wake {
                    state.metrics.routing_capacity_rejected(model, false);
                }
                if Instant::now() >= waiting_until {
                    return Err(GatewayError::CapacityUnavailable { wake });
                }
                if waiter.is_none() {
                    waiter = state.coordinator.eval_waiter(body.len());
                    if waiter.is_none() {
                        return Err(GatewayError::CapacityUnavailable { wake });
                    }
                }
                tokio::time::sleep(
                    EVAL_COLD_START_POLL
                        .min(waiting_until.saturating_duration_since(Instant::now())),
                )
                .await;
                metadata.received_at = Utc::now();
            }
            result => return result,
        }
    }
}

/// How often a waiting eval request looks for its pool's first replica.
const EVAL_COLD_START_POLL: Duration = Duration::from_secs(10);

async fn attempt(
    state: &GatewayState,
    endpoint: &Endpoint,
    metadata: RequestMetadata,
    headers: &HeaderMap,
    body: &Bytes,
    is_verification: &mut bool,
    authorization: Option<crate::coordinator::Authorization>,
) -> Result<Response, GatewayError> {
    let classified = state
        .coordinator
        .classify_authorized(
            headers,
            body,
            metadata.received_at,
            endpoint.protocol,
            is_verification,
            authorization,
        )
        .await;
    crate::diagnostics::body::record("client_request", body, None);
    let ClassifiedRequest { hosted, request } = classified?;
    if matches!(endpoint.operation, Operation::CountTokens)
        && headers.contains_key(&DEPLOYMENT_ID_HEADER)
    {
        return Err(GatewayError::invalid_request(Some(
            "x-gradiated-deployment-id",
        )));
    }
    if body.len() > 1_048_576 {
        crate::diagnostics::body::record_value("client_request", &request, None);
    }
    crate::session_telemetry::record_body(&request);
    let translated = endpoint.protocol.translate_request(&request)?;
    let qualified =
        state
            .coordinator
            .qualify(metadata, headers, hosted, &translated, endpoint.kind)?;

    let pinned = headers
        .contains_key(&DEPLOYMENT_ID_HEADER)
        .then(|| qualified.local.as_ref().map(|local| local.deployment.id))
        .flatten();
    let mut response = match endpoint.operation {
        Operation::Complete => complete(state, endpoint.protocol, qualified).await,
        Operation::CountTokens => count_tokens(state, &qualified).await,
    }?;

    if let Some(deployment_id) = pinned {
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

    let id = generation_id_header(generation_id);
    let headers = response.headers_mut();
    headers.insert(TYPESAFE_REQUEST_ID_HEADER, id.clone());
    headers.insert(GENERATION_ID_HEADER, id);

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
            crate::diagnostics::body::record_value(
                "client_error",
                &serde_json::json!({
                    "error": {"code": error.code(), "type": error.error_type(), "param": error.param(), "message": error.message()}
                }),
                Some(error.status().as_u16()),
            );
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
            crate::diagnostics::body::record_value("client_response", &body, Some(200));
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

    let body = serde_json::json!({ "input_tokens": count });
    crate::diagnostics::body::record_value("client_response", &body, Some(200));
    Ok(Json(body).into_response())
}

fn sse_response(
    protocol: Protocol,
    stream: impl Stream<Item = StreamItem> + Send + 'static,
) -> Response {
    let mut renderer = protocol.stream_renderer();
    let mut diagnostic_frames = 0;
    let diagnostic_span = tracing::Span::current();
    let events = stream.flat_map(move |item| {
        let _entered = diagnostic_span.enter();
        let terminal = match &item {
            StreamItem::Error(_) | StreamItem::Done => true,
            StreamItem::Chunk(value) => {
                value.get("usage").is_some_and(|v| !v.is_null())
                    && value
                        .get("choices")
                        .and_then(serde_json::Value::as_array)
                        .is_some_and(Vec::is_empty)
            }
        };
        let frames = renderer.render(item);
        if diagnostic_frames == 0 || terminal {
            for frame in &frames {
                if diagnostic_frames == 8 {
                    break;
                }

                crate::diagnostics::body::record(
                    "client_response_frame",
                    frame.data.as_bytes(),
                    Some(200),
                );
                diagnostic_frames += 1;
            }
        }
        futures_util::stream::iter(
            frames
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
                        "authorization,content-type,content-encoding,x-gradiated-deployment-id",
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
        assert!(allowed.headers()["access-control-allow-headers"]
            .to_str()
            .unwrap()
            .contains("content-encoding"));

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
        assert!(exposed_headers.contains("x-typesafe-request-id"));
        assert!(exposed_headers.contains("retry-after"));

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
        assert_eq!(
            response.headers()[TYPESAFE_REQUEST_ID_HEADER],
            response.headers()[GENERATION_ID_HEADER]
        );
        assert!(!response.headers().contains_key(RETRY_AFTER));
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
            futures_util::stream::iter(vec![StreamItem::Error(GatewayError::capacity_exceeded())]),
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

    async fn post_encoded(application: Router, encoding: &str, body: Vec<u8>) -> Response {
        application
            .oneshot(json_request(
                "/v1/systemone",
                &[
                    ("authorization", "Bearer grad_test"),
                    ("content-encoding", encoding),
                ],
                body,
            ))
            .await
            .unwrap()
    }

    const SYSTEMONE_BODY: &str = r#"{"model":"gradiated/linden-1","state":"Charged twice.","questions":{"q":{"type":"noul","instructions":"Is it urgent?"}}}"#;

    fn authenticated_application() -> (Router, Arc<TestServingState>) {
        let state = Arc::new(TestServingState::ready());
        let application = router_for(true, state.clone());

        (application, state)
    }

    #[tokio::test]
    async fn zstd_and_gzip_bodies_are_decompressed_after_authentication() {
        use std::io::Write;

        let zstd = zstd::encode_all(SYSTEMONE_BODY.as_bytes(), 3).unwrap();
        let mut gzip = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        gzip.write_all(SYSTEMONE_BODY.as_bytes()).unwrap();
        let gzip = gzip.finish().unwrap();

        for (encoding, body) in [("zstd", zstd), ("gzip", gzip)] {
            let (application, serving_state) = authenticated_application();
            let _ = post_encoded(application, encoding, body).await;

            // The decoded JSON is classified with the authorization made before inflating it.
            assert_eq!(serving_state.lookups("credential"), 1, "{encoding}");
            assert_eq!(serving_state.lookups("model"), 1, "{encoding}");
            assert_eq!(
                serving_state.requested_models.lock().unwrap().as_slice(),
                ["gradiated/linden-1"],
                "{encoding}"
            );
        }
    }

    #[tokio::test]
    async fn a_compressed_body_from_an_unknown_caller_is_not_inflated() {
        let (application, serving_state) = observed_application();
        let bomb = zstd::encode_all(vec![b' '; MAX_REQUEST_BYTES + 1].as_slice(), 19).unwrap();

        let response = post_encoded(application, "zstd", bomb).await;

        // Inflating would answer 413; the credential is refused first.
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(serving_state.lookups("credential"), 1);
        assert_eq!(serving_state.lookups("model"), 0);
    }

    #[tokio::test]
    async fn an_unsupported_encoding_is_an_invalid_request_in_the_error_envelope() {
        for encoding in ["br", "zstd, gzip"] {
            let (application, serving_state) = observed_application();
            let response = post_encoded(application, encoding, SYSTEMONE_BODY.into()).await;

            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{encoding}");
            assert!(response.headers().contains_key(GENERATION_ID_HEADER));
            assert_eq!(serving_state.lookups("credential"), 0, "{encoding}");
            assert_eq!(error_code(response).await, "invalid_request");
        }
    }

    #[tokio::test]
    async fn a_zstd_frame_with_a_window_above_32_mib_is_refused() {
        use std::io::Write;

        let mut encoder = zstd::stream::write::Encoder::new(Vec::new(), 3).unwrap();
        encoder.include_contentsize(false).unwrap();
        encoder.window_log(27).unwrap();
        encoder.write_all(SYSTEMONE_BODY.as_bytes()).unwrap();
        let frame = encoder.finish().unwrap();
        assert_eq!(
            zstd::decode_all(frame.as_slice()).unwrap(),
            SYSTEMONE_BODY.as_bytes()
        );

        let (application, serving_state) = authenticated_application();
        let response = post_encoded(application, "zstd", frame).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(serving_state.lookups("model"), 0);
    }

    #[tokio::test]
    async fn a_cancelled_inflation_keeps_its_slot_until_it_ends() {
        static SLOTS: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(1);
        let bomb = zstd::encode_all(vec![b' '; MAX_REQUEST_BYTES].as_slice(), 19).unwrap();
        let inflation = tokio::spawn(inflate_in_slot(&SLOTS, Codec::Zstd, bomb.into()));
        while SLOTS.available_permits() == 1 {
            tokio::task::yield_now().await;
        }
        inflation.abort();
        assert!(inflation.await.unwrap_err().is_cancelled());
        // The blocking task still runs and still holds the slot after its request is gone.
        assert_eq!(SLOTS.available_permits(), 0);
        let _released = tokio::time::timeout(Duration::from_secs(30), SLOTS.acquire())
            .await
            .expect("the slot is released when inflation ends")
            .unwrap();
    }

    #[tokio::test(start_paused = true)]
    async fn a_compressed_body_waits_a_bounded_time_for_a_slot() {
        static SLOTS: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(1);
        let _held = SLOTS.acquire().await.unwrap();
        let body = zstd::encode_all(SYSTEMONE_BODY.as_bytes(), 3).unwrap();

        let refused = inflate_in_slot(&SLOTS, Codec::Zstd, body.into()).await;

        assert!(matches!(refused, Err(GatewayError::ProxyOverloaded)));
    }

    #[tokio::test]
    async fn a_corrupt_compressed_body_is_an_invalid_request() {
        let (application, serving_state) = authenticated_application();
        let response = post_encoded(application, "zstd", b"not zstd".to_vec()).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(serving_state.lookups("model"), 0);
        assert_eq!(error_code(response).await, "invalid_request");
    }

    #[tokio::test]
    async fn a_compressed_body_cannot_expand_past_the_body_limit() {
        let (application, serving_state) = authenticated_application();
        let bomb = zstd::encode_all(vec![b' '; MAX_REQUEST_BYTES + 1].as_slice(), 19).unwrap();
        assert!(bomb.len() < 64 * 1024);

        let response = post_encoded(application, "zstd", bomb).await;

        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        assert_eq!(serving_state.lookups("model"), 0);
        assert_eq!(error_code(response).await, "payload_too_large");
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

    fn cold_eval_state() -> TestServingState {
        let mut state = TestServingState::ready();
        let model = state.model.as_ref().unwrap().clone();
        state.adapter = Some(crate::PrivateAdapter {
            workspace_id: crate::test_support::WORKSPACE_ID,
            organization_slug: "acme".to_owned(),
            task_name: "grad-eval".to_owned(),
            version_id: Uuid::from_u128(78),
            name: "fast-diff-merge.2026-11-26-1".to_owned(),
            status: "available".to_owned(),
            size_bytes: 10,
            base_model_id: model.id.clone(),
            base_model_revision: model.deployments[0].release.model_revision.clone(),
            sha256: "a".repeat(64),
            format: crate::AdapterFormat::PeftLora,
            num_tokens: None,
            source_kind: Some("grad".to_owned()),
            eval_only: true,
        });
        // The pool is at zero: its one replica, which serves adapters, is still starting.
        let deployment = &mut state.model.as_mut().unwrap().deployments[0];
        deployment.release.lora_enabled = Some(true);
        deployment.status = crate::DeploymentStatus::Unavailable;
        state
    }

    async fn metrics_text(application: Router) -> String {
        let metrics = application
            .oneshot(
                Request::builder()
                    .uri("/metrics")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        String::from_utf8(
            axum::body::to_bytes(metrics.into_body(), 1 << 20)
                .await
                .unwrap()
                .to_vec(),
        )
        .unwrap()
    }

    fn wakes(text: &str, model: &str) -> bool {
        text.lines().any(|line| {
            line.contains("routing_capacity_rejections_total")
                && line.contains(&format!("model=\"{model}\""))
        })
    }

    #[tokio::test]
    async fn an_eval_never_asks_for_a_replica_beside_a_ready_one() {
        // A ready replica that cannot load the adapter is no cold start: the
        // eval fails at once and the pool is not scaled.
        let mut state = cold_eval_state();
        let deployment = &mut state.model.as_mut().unwrap().deployments[0];
        deployment.status = crate::DeploymentStatus::Available;
        deployment.release.lora_enabled = None;
        let model = state.model.as_ref().unwrap().id.clone();
        let application =
            super::support::router_for_eval(Arc::new(state), std::time::Duration::from_secs(60));

        let started = Instant::now();
        let response = eval_completion(application.clone()).await;

        assert!(started.elapsed() < std::time::Duration::from_secs(5));
        assert_eq!(error_code(response).await, "model_unavailable");
        assert!(!wakes(&metrics_text(application).await, &model));
    }

    #[tokio::test]
    async fn an_eval_waits_for_an_unroutable_ready_replica_without_waking_the_pool() {
        let mut state = cold_eval_state();
        state.model.as_mut().unwrap().deployments[0].status = crate::DeploymentStatus::Available;
        // The replica is listed ready, but reports no healthy status.
        state.statuses = Some(Vec::new());
        let model = state.model.as_ref().unwrap().id.clone();
        let application =
            super::support::router_for_eval(Arc::new(state), std::time::Duration::from_millis(300));

        let response = eval_completion(application.clone()).await;

        assert_eq!(error_code(response).await, "capacity_unavailable");
        assert!(!wakes(&metrics_text(application).await, &model));
    }

    async fn eval_completion(application: Router) -> Response {
        let workspace = crate::test_support::WORKSPACE_ID.to_string();
        let bearer = format!("Bearer {}", super::support::EVAL_TOKEN);
        application
            .oneshot(json_request(
                "/v1/chat/completions",
                &[
                    ("authorization", bearer.as_str()),
                    ("x-gradiated-source", "eval"),
                    ("x-gradiated-workspace", workspace.as_str()),
                ],
                r#"{"model":"acme/grad-eval/fast-diff-merge.2026-11-26-1","messages":[{"role":"user","content":"hi"}]}"#,
            ))
            .await
            .unwrap()
    }

    #[tokio::test]
    async fn an_eval_on_a_pool_at_zero_wakes_it_then_gives_up_with_capacity_unavailable() {
        let state = Arc::new(cold_eval_state());
        let model = state.model.as_ref().unwrap().id.clone();
        let application =
            super::support::router_for_eval(state, std::time::Duration::from_millis(300));

        let started = Instant::now();
        let response = eval_completion(application.clone()).await;

        assert!(started.elapsed() >= std::time::Duration::from_millis(300));
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(response.headers()["retry-after"], "30");
        assert_eq!(error_code(response).await, "capacity_unavailable");

        // The wake signal names the pool's own model, which asks for one replica.
        let text = metrics_text(application).await;
        assert!(wakes(&text, &model), "{text}");
    }

    #[tokio::test]
    async fn an_eval_service_token_bills_customer_workspaces_only() {
        let mut state = cold_eval_state();
        state.account.as_mut().unwrap().organization_kind =
            crate::domain::OrganizationKind::DistributionChannel;
        let application =
            super::support::router_for_eval(Arc::new(state), std::time::Duration::ZERO);

        let response = eval_completion(application).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(error_code(response).await, "invalid_request");
    }

    #[test]
    fn eval_requests_waiting_for_a_cold_pool_are_bounded_per_process() {
        let coordinator = crate::RequestCoordinator::new(Arc::new(TestServingState::ready()));

        let small: Vec<_> = (0..64)
            .map(|_| coordinator.eval_waiter(100).expect("room to wait"))
            .collect();
        assert!(coordinator.eval_waiter(100).is_none());
        drop(small);

        // A large body takes a larger share: two of the largest fit.
        let large: Vec<_> = (0..2)
            .map(|_| coordinator.eval_waiter(32_000_000).expect("room to wait"))
            .collect();
        assert!(coordinator.eval_waiter(32_000_000).is_none());
        assert!(coordinator.eval_waiter(100).is_some());
        drop(large);
    }

    #[tokio::test]
    async fn without_a_wait_an_eval_on_a_pool_at_zero_fails_at_once() {
        let application =
            super::support::router_for_eval(Arc::new(cold_eval_state()), std::time::Duration::ZERO);

        let response = eval_completion(application.clone()).await;

        assert_eq!(error_code(response).await, "capacity_unavailable");
        // Even without waiting, the pool is asked for its first replica.
        let model = cold_eval_state().model.unwrap().id;
        assert!(wakes(&metrics_text(application).await, &model));
    }
}

#[cfg(test)]
#[path = "http_support.rs"]
mod support;

#[cfg(test)]
#[path = "http_diagnostics_tests.rs"]
mod diagnostics_tests;

#[cfg(test)]
#[path = "http_listing_tests.rs"]
mod listing_tests;
