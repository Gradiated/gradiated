use async_trait::async_trait;
use chrono::{DateTime, Utc};
use serde_json::{json, Value};

use super::{super::*, support::*};
use crate::{GatewayModelDeployment, RuntimeCompletion, RuntimeFailure};

struct CountingRuntime {
    expected: Value,
    hang: bool,
}

#[async_trait]
impl ModelRuntime for CountingRuntime {
    async fn count_tokens(
        &self,
        deployment: &GatewayModelDeployment,
        request: Value,
    ) -> Result<u64, RuntimeFailure> {
        assert_eq!(deployment.release.model_path, "moonshotai/Kimi-K3.1-Pro");
        assert_eq!(request, self.expected);
        if self.hang {
            std::future::pending::<()>().await;
        }

        Ok(89)
    }

    async fn complete(
        &self,
        _: &GatewayModelDeployment,
        _: InferenceRequest,
        _: u64,
        _: DateTime<Utc>,
    ) -> Result<RuntimeCompletion, RuntimeFailure> {
        panic!("counting must not generate tokens")
    }
}

fn kimi(hang: bool) -> (Harness, Value) {
    let mut request = qualified_request(1);
    let local = request.local.as_mut().unwrap();
    local.deployment.release.model_path = "moonshotai/Kimi-K3.1-Pro".to_owned();
    local.deployments[0] = local.deployment.clone();
    local.release_digest = local.deployment.served_release_digest().unwrap();
    let mut harness = Harness::new(request, []);
    let body = json!({
        "model": "moonshotai/kimi-k3.1-pro",
        "system": "Be brief",
        "messages": [{"role": "user", "content": "Hello"}],
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "tools": [{"name": "weather", "input_schema": {"type": "object"}}]
    });
    harness.service.runtime = Arc::new(CountingRuntime {
        expected: body.clone(),
        hang,
    });

    (harness, body)
}

#[tokio::test]
async fn kimi_counts_with_its_runtime_without_loading_hf_json_or_admitting_a_generation() {
    let (harness, body) = kimi(false);

    assert_eq!(
        harness.service.count_tokens(&harness.request, &body).await,
        Ok(89)
    );
    assert!(harness.journal.steps().is_empty());
}

#[tokio::test(start_paused = true)]
async fn kimi_counting_has_a_bounded_deadline() {
    let (harness, body) = kimi(true);

    assert_eq!(
        harness.service.count_tokens(&harness.request, &body).await,
        Err(GatewayError::RuntimeUnavailable)
    );
    assert!(harness.journal.steps().is_empty());
}

#[tokio::test]
async fn kimi_counting_does_not_dispatch_to_an_unhealthy_replica() {
    let (harness, body) = kimi(false);
    let harness = harness
        .local_status(|status| status.received_at = Utc::now() - chrono::TimeDelta::minutes(1));

    assert_eq!(
        harness.service.count_tokens(&harness.request, &body).await,
        Err(GatewayError::RuntimeUnavailable)
    );
}
