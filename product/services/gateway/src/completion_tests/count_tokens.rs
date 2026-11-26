use async_trait::async_trait;
use axum::http::StatusCode;
use chrono::{DateTime, Utc};
use serde_json::json;

use super::{super::*, support::*};
use crate::{
    tokenizer::test_support::Hub, GatewayModelDeployment, PinnedTokenizer, RuntimeCompletion,
    RuntimeFailure,
};

struct NeverCalledRuntime;

#[async_trait]
impl ModelRuntime for NeverCalledRuntime {
    async fn complete(
        &self,
        _: &GatewayModelDeployment,
        _: InferenceRequest,
        _: u64,
        _: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        panic!("counting must not call the model runtime")
    }
}

#[tokio::test]
async fn kimi_counts_in_gateway_with_pinned_tokenizer_when_no_local_deployment_exists() {
    let hub = Hub::answering(StatusCode::NOT_FOUND).await;
    let revision = "d9e99b0792a5e93b78ea9bea62a68167e36ddd9e";
    hub.cache_kimi_release("moonshotai/Kimi-K3.1-Pro", revision);

    let mut request = qualified_request(1);
    request.local = None;
    request.external = Some(crate::ExternalModel::direct("moonshotai/kimi-k3.1-pro"));
    request.tokenizer = Some(PinnedTokenizer {
        path: "moonshotai/Kimi-K3.1-Pro".to_owned(),
        revision: revision.to_owned(),
    });
    request.request.model = "moonshotai/kimi-k3.1-pro".to_owned();
    request.request.messages = vec![
        json!({"role": "system", "content": "Be brief"}),
        json!({"role": "user", "content": "Hello"}),
    ];

    let mut harness = Harness::new(request, []);
    harness.service = CompletionService::new(
        harness.state.clone(),
        Arc::new(NeverCalledRuntime),
        hub.tokenizer.clone(),
        Arc::new(GatewayConfig::for_tests()),
    );

    let count = harness
        .service
        .count_tokens(&harness.request)
        .await
        .unwrap();
    assert!(count > 0);
    assert_eq!(hub.requests(), 0);
    assert!(harness.journal.steps().is_empty());
}

#[tokio::test]
async fn kimi_cyber_counts_in_gateway_even_without_healthy_replicas() {
    let hub = Hub::answering(StatusCode::NOT_FOUND).await;
    let revision = "0911ef0765f49d26dfa25bb0d071f29463f8000b";
    hub.cache_kimi_release("yetalabs/Kimi-K3.1-Pro-abliterated", revision);

    let mut request = qualified_request(1);
    let local = request.local.as_mut().unwrap();
    local.deployment.release.model_path = "yetalabs/Kimi-K3.1-Pro-abliterated".to_owned();
    local.deployment.release.tokenizer_path = "yetalabs/Kimi-K3.1-Pro-abliterated".to_owned();
    local.deployment.release.tokenizer_revision = revision.to_owned();
    local.deployments[0] = local.deployment.clone();
    local.release_digest = local.deployment.served_release_digest().unwrap();

    let mut harness = Harness::new(request, []).local_status(|status| {
        status.received_at = Utc::now() - chrono::TimeDelta::minutes(1);
    });
    harness.service = CompletionService::new(
        harness.state.clone(),
        Arc::new(NeverCalledRuntime),
        hub.tokenizer.clone(),
        Arc::new(GatewayConfig::for_tests()),
    );

    let count = harness
        .service
        .count_tokens(&harness.request)
        .await
        .unwrap();
    assert!(count > 0);
    assert_eq!(hub.requests(), 0);
    assert!(harness.journal.steps().is_empty());
}
