use super::support::qualify_chat;
use super::*;
use crate::test_support::{TestServingState, WORKSPACE_ID};

fn state() -> TestServingState {
    let mut state = TestServingState::ready();
    let model = state.model.as_mut().unwrap();
    model.deployments[0].release.lora_enabled = Some(true);
    state.adapter = Some(crate::PrivateAdapter {
        workspace_id: WORKSPACE_ID,
        organization_slug: "acme".to_owned(),
        task_name: "task-a".to_owned(),
        version_id: Uuid::from_u128(77),
        name: "task-a-v1".to_owned(),
        status: "available".to_owned(),
        size_bytes: 10,
        base_model_id: model.id.clone(),
        base_model_revision: model.deployments[0].release.model_revision.clone(),
        sha256: "a".repeat(64),
        format: crate::AdapterFormat::PeftLora,
        num_tokens: None,
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
    let production = private_request(state.clone(), "acme/task-a").await.unwrap();
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
        ["acme/task-a/task-a-v1", "model-a", "acme/task-a", "model-a"]
    );
}

#[tokio::test]
async fn names_carry_the_organization_slug() {
    let state = Arc::new(state());
    let canonical = state.adapter.as_ref().unwrap().model_id();
    assert_eq!(canonical, "acme/task-a/task-a-v1");

    for model in ["ACME/task-a/task-a-v1", "acme/task-a"] {
        let request = private_request(state.clone(), model).await.unwrap();
        assert_eq!(request.request.model, canonical, "{model}");
    }
    for model in [
        "other/task-a/task-a-v1",
        "acme/task-a/v2",
        "acme/task-b",
        "task-a",
        "task-a-v1",
    ] {
        assert_eq!(
            private_request(state.clone(), model).await.err(),
            Some(GatewayError::ModelNotFound),
            "{model}"
        );
    }
}

#[tokio::test]
async fn an_alias_cannot_replace_an_adapters_pinned_base_model() {
    let mut state = state();
    let model = state.model.as_mut().unwrap();
    model.aliases = vec![model.id.clone()];
    model.id = "replacement-model".to_owned();

    assert_eq!(
        private_request(Arc::new(state), "acme/task-a").await.err(),
        Some(GatewayError::ModelUnavailable)
    );
}

#[tokio::test]
async fn rejects_other_workspaces_and_missing_versions() {
    let mut state = state();
    state.adapter.as_mut().unwrap().workspace_id = Uuid::from_u128(123);
    assert_eq!(
        private_request(Arc::new(state), "acme/task-a/task-a-v1")
            .await
            .err(),
        Some(GatewayError::ModelNotFound)
    );
    assert_eq!(
        private_request(Arc::new(TestServingState::ready()), "acme/task-a/task-a-v1")
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
        let result = private_request(Arc::new(state), "acme/task-a/task-a-v1").await;

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
                assert_eq!(request.request.model, "acme/task-a/task-a-v1");
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
    state.model.as_mut().unwrap().id = "acme/task-a".to_owned();
    assert_eq!(
        private_request(Arc::new(state), "acme/task-a").await.err(),
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

        let result = private_request(Arc::new(state), "acme/task-a/task-a-v1").await;
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

fn cartridge_state(enabled: Option<bool>) -> TestServingState {
    let mut state = state();
    let adapter = state.adapter.as_mut().unwrap();
    adapter.format = crate::AdapterFormat::Cartridge;
    adapter.num_tokens = Some(512);
    state.model.as_mut().unwrap().deployments[0]
        .release
        .cartridge_enabled = enabled;
    state
}

#[tokio::test]
async fn a_cartridge_routes_only_to_cartridge_enabled_deployments() {
    let request = private_request(Arc::new(cartridge_state(Some(true))), "acme/task-a")
        .await
        .unwrap();
    assert_eq!(
        request
            .local_capacity()
            .deployment
            .release
            .cartridge_enabled,
        Some(true)
    );
    assert_eq!(request.request.cartridge_tokens, 512);

    assert_eq!((&request.base, &request.external), (&None, &None));

    // Fails closed: no base-model or OpenRouter fallback, even for a mapped model.
    for enabled in [None, Some(false)] {
        let mut state = cartridge_state(enabled);
        state.model.as_mut().unwrap().openrouter_model_id = Some("vendor/model".to_owned());
        assert_eq!(
            private_request(Arc::new(state), "acme/task-a").await.err(),
            Some(GatewayError::ModelUnavailable),
            "{enabled:?}"
        );
    }
}

#[tokio::test]
async fn a_cartridge_takes_its_positions_out_of_the_context_limit() {
    let lora = private_request(Arc::new(state()), "acme/task-a")
        .await
        .unwrap();
    let cartridge = private_request(Arc::new(cartridge_state(Some(true))), "acme/task-a")
        .await
        .unwrap();

    assert_eq!(lora.request.cartridge_tokens, 0);
    assert_eq!(cartridge.max_context_tokens, lora.max_context_tokens - 512);
    assert_eq!(cartridge.max_prompt_tokens, lora.max_prompt_tokens - 512);
}

#[tokio::test]
async fn a_cartridge_without_its_length_is_invalid() {
    let mut state = cartridge_state(Some(true));
    state.adapter.as_mut().unwrap().num_tokens = None;
    assert!(private_request(Arc::new(state), "acme/task-a")
        .await
        .is_err());
}
