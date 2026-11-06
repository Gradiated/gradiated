use super::support::qualify_chat;
use super::*;
use crate::test_support::{TestServingState, WORKSPACE_ID};

fn state() -> TestServingState {
    let mut state = TestServingState::ready();
    let model = state.model.as_mut().unwrap();
    model.deployments[0].release.lora_enabled = Some(true);
    state.adapter = Some(crate::PrivateAdapter {
        workspace_id: WORKSPACE_ID,
        version_id: Uuid::from_u128(77),
        name: "task-a-v1".to_owned(),
        status: "available".to_owned(),
        size_bytes: 10,
        base_model_id: model.id.clone(),
        base_model_revision: model.deployments[0].release.model_revision.clone(),
        sha256: "a".repeat(64),
    });
    state
}

async fn private_request(
    state: Arc<TestServingState>,
    selector: &str,
) -> Result<QualifiedRequest, GatewayError> {
    let body = serde_json::to_vec(
        &serde_json::json!({"model": selector, "messages": [{"role": "user", "content": "hello"}]}),
    )
    .unwrap();
    qualify_chat(state, &body).await
}

#[tokio::test]
async fn production_and_exact_version_resolve_to_the_same_pinned_identity() {
    let state = Arc::new(state());
    let adapter = state.adapter.as_ref().unwrap();
    let exact = private_request(state.clone(), &adapter.model_id())
        .await
        .unwrap();
    let production = private_request(state.clone(), "task-a").await.unwrap();
    assert_eq!(production.request.model, adapter.model_id());
    assert_eq!(exact.adapter, production.adapter);
    assert_eq!(exact.pricing, production.pricing);
    assert_eq!(
        exact.local_capacity().deployment.release.lora_enabled,
        Some(true)
    );
    assert_ne!(
        adapter.served_digest(&exact.local_capacity().release_digest),
        exact.local_capacity().release_digest
    );
    assert_eq!(
        *state.requested_models.lock().unwrap(),
        ["task-a-v1", "model-a", "task-a", "model-a"]
    );
}

#[tokio::test]
async fn rejects_other_workspaces_and_missing_versions() {
    let mut state = state();
    state.adapter.as_mut().unwrap().workspace_id = Uuid::from_u128(123);
    assert_eq!(
        private_request(Arc::new(state), "task-a-v1").await.err(),
        Some(GatewayError::ModelNotFound)
    );
    assert_eq!(
        private_request(Arc::new(TestServingState::ready()), "task-a-v1")
            .await
            .err(),
        Some(GatewayError::ModelNotFound)
    );
}

#[tokio::test]
async fn an_adapter_without_qualified_deployments_degrades_to_its_base_model() {
    for mismatch in ["disabled", "revision", "native", "system_one"] {
        let mut state = state();
        let release = &mut state.model.as_mut().unwrap().deployments[0].release;
        match mismatch {
            "disabled" => release.lora_enabled = None,
            "revision" => release.model_revision = "different".to_owned(),
            "native" => release.runtime_revision = "native-test".to_owned(),
            _ => release.protocol = Some(crate::RuntimeProtocol::SystemOne),
        }
        let base_deployment = state.model.as_ref().unwrap().deployments[0].id;
        let result = private_request(Arc::new(state), "task-a-v1").await;

        match mismatch {
            // The base model serves the request through the chat protocol, without the adapter.
            "disabled" | "revision" => {
                let request = result.unwrap();
                assert_eq!(request.local, None, "{mismatch}");
                assert_eq!(
                    request.base.unwrap().deployment.id,
                    base_deployment,
                    "{mismatch}"
                );
                assert_eq!(request.request.model, "task-a-v1");
                assert!(request.adapter.is_some());
            }
            // A deployment that cannot serve chat is not base capacity either.
            _ => assert_eq!(
                result.err(),
                Some(GatewayError::ModelUnavailable),
                "{mismatch}"
            ),
        }
    }
}

#[tokio::test]
async fn rejects_private_names_that_collide_with_public_catalog_models() {
    let mut state = state();
    state.adapter.as_mut().unwrap().name = "model-a".to_owned();
    assert_eq!(
        private_request(Arc::new(state), "model-a").await.err(),
        Some(GatewayError::ServingStateUnavailable)
    );
}

#[tokio::test]
async fn serves_the_adapter_only_on_its_qualified_training_revision() {
    for training_revision in ["bf16-training", "unqualified"] {
        let mut state = state();
        state.adapter.as_mut().unwrap().base_model_revision = training_revision.to_owned();
        state.model.as_mut().unwrap().deployments[0]
            .release
            .lora_base_model_revision = Some("bf16-training".to_owned());

        let result = private_request(Arc::new(state), "task-a-v1").await;
        if training_revision == "bf16-training" {
            let request = result.unwrap();
            assert_eq!(
                request
                    .local_capacity()
                    .deployment
                    .release
                    .lora_base_model_revision
                    .as_deref(),
                Some("bf16-training")
            );
            assert_ne!(
                request.local_capacity().deployment.release.model_revision,
                "bf16-training"
            );
        } else {
            let request = result.unwrap();
            assert_eq!(request.local, None);
            assert!(request.base.is_some());
        }
    }
}
