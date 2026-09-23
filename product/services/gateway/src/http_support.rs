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
    GatewayModelDeployment, InferenceRequest, ModelRuntime, ModelTokenizer, ProviderRelay,
    RequestCoordinator, RuntimeCompletion, RuntimeFailure,
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
