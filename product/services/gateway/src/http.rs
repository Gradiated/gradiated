use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, State},
    http::{HeaderMap, HeaderName, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use chrono::Utc;
use serde::Serialize;
use uuid::Uuid;

use crate::{readiness::ReadinessCheck, CompletionService, GatewayError, RequestMetadata};

const MAX_REQUEST_BYTES: usize = 8_000_000;
const GENERATION_ID_HEADER: HeaderName = HeaderName::from_static("x-generation-id");

#[derive(Clone)]
pub struct GatewayState {
    readiness: Arc<dyn ReadinessCheck>,
    completions: CompletionService,
}

impl GatewayState {
    pub fn new(readiness: Arc<dyn ReadinessCheck>, completions: CompletionService) -> Self {
        Self {
            readiness,
            completions,
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
        .route("/health/live", get(live))
        .route("/health/ready", get(ready))
        .layer(DefaultBodyLimit::max(MAX_REQUEST_BYTES))
        .with_state(state)
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
            .complete_non_streaming(metadata, &headers, body)
            .await
            .map(|result| Json(result.into_response()).into_response()),
        Err(rejection) if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => {
            Err(GatewayError::PayloadTooLarge)
        }
        Err(_) => Err(GatewayError::invalid_request(None)),
    };
    let mut response = result.unwrap_or_else(IntoResponse::into_response);
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
    if !state.readiness.is_ready().await {
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
        let config = Arc::new(GatewayConfig {
            bind_address: "127.0.0.1:3002".parse().unwrap(),
            generation_timeout_seconds: 300,
            lease_finalization_margin_seconds: 60,
            expired_lease_cleanup_grace_seconds: 300,
            prepaid_organization_concurrency_cap: 50,
            balance_per_concurrency_slot_nano_usd: 1_000_000_000,
            settlement_backlog_limit: 100_000,
            valkey_url: "redis://127.0.0.1:6379".to_owned(),
            sglang_api_key: None,
        });
        let serving_state = Arc::new(MissingServingState { credential_lookups });
        let completions = CompletionService::new(
            serving_state,
            Arc::new(UnusedRuntime),
            ModelTokenizer::new().unwrap(),
            config,
        );
        router(GatewayState::new(
            Arc::new(FixedReadiness(ready)),
            completions,
        ))
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
