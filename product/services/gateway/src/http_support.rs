use std::sync::Arc;

use async_trait::async_trait;
use axum::{
    body::{to_bytes, Body},
    http::{header::CONTENT_TYPE, Request},
    response::Response,
    Router,
};
use serde_json::Value;

use super::{router, GatewayState};
use crate::{
    readiness::ReadinessCheck, test_support::TestServingState, CompletionService, GatewayConfig,
    GatewayModelDeployment, InferenceRequest, ModelRuntime, ModelTokenizer, RequestCoordinator,
    RuntimeCompletion, RuntimeFailure,
};

struct FixedReadiness(bool);

#[async_trait]
impl ReadinessCheck for FixedReadiness {
    async fn is_ready(&self) -> bool {
        self.0
    }
}

struct UnusedRuntime;

#[async_trait]
impl ModelRuntime for UnusedRuntime {
    async fn complete(
        &self,
        _deployment: &GatewayModelDeployment,
        _request: InferenceRequest,
        _effective_output_tokens: u64,
        _request_deadline: chrono::DateTime<chrono::Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        Err(RuntimeFailure::protocol_violation())
    }
}

pub(super) fn router_for(ready: bool, serving_state: Arc<TestServingState>) -> Router {
    router_for_with_verification(ready, serving_state, None)
}

pub(super) fn router_for_with_verification(
    ready: bool,
    serving_state: Arc<TestServingState>,
    verification_workspace: Option<uuid::Uuid>,
) -> Router {
    let test_config = GatewayConfig::for_tests();
    let config = Arc::new(test_config.clone());
    let completions = CompletionService::new(
        serving_state.clone(),
        Arc::new(UnusedRuntime),
        ModelTokenizer::new().unwrap(),
        config,
    );
    let coordinator =
        RequestCoordinator::new(serving_state).with_verification_workspace(verification_workspace);

    router(GatewayState::new(
        Arc::new(FixedReadiness(ready)),
        completions,
        coordinator,
        test_config.compliance(),
    ))
}

pub(super) const EVAL_TOKEN: &str = "eval-service-token-0123456789abcdef";

/// grad's eval workers, whose requests wait up to `wait` for a pool at zero.
pub(super) fn router_for_eval(
    serving_state: Arc<TestServingState>,
    wait: std::time::Duration,
) -> Router {
    let test_config = GatewayConfig::for_tests();
    let completions = CompletionService::new(
        serving_state.clone(),
        Arc::new(UnusedRuntime),
        ModelTokenizer::new().unwrap(),
        Arc::new(test_config.clone()),
    );
    let coordinator = RequestCoordinator::new(serving_state)
        .with_eval_service_tokens(crate::auth::EvalServiceTokens::new([EVAL_TOKEN]))
        .with_eval_cold_start_wait(wait);

    router(GatewayState::new(
        Arc::new(FixedReadiness(true)),
        completions,
        coordinator,
        test_config.compliance(),
    ))
}

pub(super) fn json_request(
    path: &str,
    headers: &[(&str, &str)],
    body: impl Into<Body>,
) -> Request<Body> {
    let mut request = Request::builder()
        .method("POST")
        .uri(path)
        .header(CONTENT_TYPE, "application/json");
    for (name, value) in headers {
        request = request.header(*name, *value);
    }

    request.body(body.into()).unwrap()
}

pub(super) async fn json_body(response: Response) -> Value {
    let body = to_bytes(response.into_body(), 4_096).await.unwrap();

    serde_json::from_slice(&body).unwrap()
}
