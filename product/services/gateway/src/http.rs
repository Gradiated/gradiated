use std::{sync::Arc, time::Duration};

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, State},
    http::{header::CONTENT_TYPE, HeaderMap, HeaderName, HeaderValue, StatusCode},
    response::{
        sse::{KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::Serialize;
use uuid::Uuid;

use crate::{
    readiness::ReadinessCheck, CompletionResponse, CompletionService, GatewayError, GatewayMetrics,
    ModelCatalogResponse, RequestCoordinator, RequestMetadata,
};

const MAX_REQUEST_BYTES: usize = 32_000_000;
const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-generation-id");
const STREAM_KEEP_ALIVE: Duration = Duration::from_secs(10);

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

pub fn router(state: GatewayState) -> Router {
    Router::new()
        .route("/v1/chat/completions", post(chat_completions))
        .route("/v1/models", get(models))
        .route("/health/live", get(live))
        .route("/health/ready", get(ready))
        .route("/metrics", get(metrics))
        .layer(DefaultBodyLimit::max(MAX_REQUEST_BYTES))
        .with_state(state)
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
    let metadata = RequestMetadata {
        generation_id: Uuid::now_v7(),
        received_at: Utc::now(),
    };
    let generation_id = metadata.generation_id;
    let result = match body {
        Ok(body) => state
            .completions
            .complete(metadata, &headers, body)
            .await
            .map(|result| match result {
                CompletionResponse::NonStreaming(result) => {
                    Json(result.into_response()).into_response()
                }
                CompletionResponse::Streaming(result) => {
                    let mut response = Sse::new(result.into_stream())
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
            }),
        Err(rejection) if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => {
            Err(GatewayError::PayloadTooLarge)
        }
        Err(_) => Err(GatewayError::invalid_request(None)),
    };
    let error = result
        .as_ref()
        .err()
        .map(GatewayError::code)
        .unwrap_or("none");
    let mut response = result.unwrap_or_else(IntoResponse::into_response);
    state
        .metrics
        .record_http("chat_completions", response.status().as_u16(), error);
    response.headers_mut().insert(
        GENERATION_ID_HEADER,
        HeaderValue::from_str(&generation_id.to_string())
            .expect("a UUID is always a valid HTTP header value"),
    );
    response
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
    use axum::{body::to_bytes, body::Body, http::header::AUTHORIZATION, http::Request};
    use chrono::DateTime;
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
            _workspace_id: Uuid,
        ) -> Result<Option<GatewayWorkspace>, ServingStateError> {
            Ok(None)
        }

        async fn account(
            &self,
            _organization_id: Uuid,
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
            _generation_id: Uuid,
            _organization_id: Uuid,
            _received_at: DateTime<Utc>,
            _admitted_at: DateTime<Utc>,
            _config: &GatewayConfig,
        ) -> Result<AdmissionLease, AdmissionError> {
            unreachable!("missing credentials cannot reach admission")
        }

        async fn finalize(
            &self,
            _generation_id: Uuid,
            _organization_id: Uuid,
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
            _request_deadline: DateTime<Utc>,
        ) -> Result<RuntimeCompletion, RuntimeFailure> {
            Err(RuntimeFailure::new(RuntimeFailureKind::ProtocolViolation))
        }
    }

    fn application(ready: bool, credential_lookups: Arc<AtomicUsize>) -> Router {
        application_with_completions(ready, credential_lookups).0
    }

    fn application_with_completions(
        ready: bool,
        credential_lookups: Arc<AtomicUsize>,
    ) -> (Router, CompletionService) {
        let config = Arc::new(GatewayConfig {
            bind_address: "127.0.0.1:3002".parse().unwrap(),
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
        (
            router(GatewayState::new(
                Arc::new(FixedReadiness(ready)),
                completions.clone(),
                coordinator,
            )),
            completions,
        )
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
    async fn readiness_fails_as_soon_as_draining_begins() {
        let (application, completions) =
            application_with_completions(true, Arc::new(AtomicUsize::new(0)));
        completions.begin_draining();

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
        assert!(response
            .headers()
            .get(CONTENT_TYPE)
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("application/openmetrics-text"));
        let body = to_bytes(response.into_body(), 100_000).await.unwrap();
        let body = std::str::from_utf8(&body).unwrap();
        assert!(body.ends_with("# EOF\n"));
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
        assert_eq!(Uuid::parse_str(generation_id).unwrap().get_version_num(), 7);
        let body = to_bytes(response.into_body(), 1_024).await.unwrap();
        let body: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(body["error"]["code"], "invalid_api_key");
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
        let body = to_bytes(response.into_body(), 1_024).await.unwrap();
        let body: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(body["error"]["code"], "payload_too_large");
    }
}
