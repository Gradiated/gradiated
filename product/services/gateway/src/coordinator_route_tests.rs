use super::tests::{metadata, TestServingState};
use super::*;
use crate::protocol::Protocol;

const HOSTED_BODY: &[u8] = br#"{"model":"model-a","messages":[{}]}"#;
const FRONTIER_BODY: &[u8] = br#"{"model":"claude-sonnet-5","max_tokens":16}"#;

fn headers(values: &[(&'static str, &str)]) -> HeaderMap {
    let mut headers = HeaderMap::new();
    for (name, value) in values {
        headers.append(
            axum::http::HeaderName::from_static(name),
            value.parse().unwrap(),
        );
    }

    headers
}

#[tokio::test]
async fn a_hosted_name_serves_locally_even_with_a_provider_key() {
    let state = Arc::new(TestServingState::ready());
    let route = RelayRoute::AnthropicMessages;
    let headers = headers(&[
        ("x-gradiated-api-key", "grad_test"),
        ("x-api-key", "sk-ant-example"),
    ]);

    let classified = RequestCoordinator::new(state.clone())
        .classify(
            &headers,
            HOSTED_BODY,
            metadata().received_at,
            Protocol::AnthropicMessages,
            Some(route),
        )
        .await
        .unwrap();

    let RequestRoute::Hosted { request, .. } = classified else {
        panic!("a hosted name must serve locally");
    };
    assert_eq!(request["model"], "model-a");
    assert_eq!(*state.requested_models.lock().unwrap(), ["model-a"]);
}

#[tokio::test]
async fn an_unresolved_name_relays_with_the_matching_provider_key() {
    let state = Arc::new(TestServingState::without_models());
    let headers = headers(&[
        ("x-gradiated-api-key", "grad_test"),
        ("x-api-key", "sk-ant-example"),
    ]);

    let classified = RequestCoordinator::new(state.clone())
        .classify(
            &headers,
            FRONTIER_BODY,
            metadata().received_at,
            Protocol::AnthropicMessages,
            Some(RelayRoute::AnthropicMessages),
        )
        .await
        .unwrap();

    let RequestRoute::Relay {
        identity,
        credential,
        ..
    } = classified
    else {
        panic!("a provider key and an unresolved name must relay");
    };
    assert_eq!(
        identity.workspace_id,
        state.workspace.as_ref().unwrap().workspace_id
    );
    assert_eq!(credential.provider, Provider::Anthropic);
    assert_eq!(credential.secret, "sk-ant-example");
    assert_eq!(
        *state.requested_models.lock().unwrap(),
        ["claude-sonnet-5"],
        "local resolution runs before the provider is considered"
    );
}

#[tokio::test]
async fn an_unresolved_name_without_a_provider_key_stays_a_local_error() {
    let state = Arc::new(TestServingState::without_models());
    let headers = headers(&[("x-gradiated-api-key", "grad_test")]);

    let result = RequestCoordinator::new(state)
        .classify(
            &headers,
            FRONTIER_BODY,
            metadata().received_at,
            Protocol::AnthropicMessages,
            Some(RelayRoute::AnthropicMessages),
        )
        .await;

    assert_eq!(result.err(), Some(GatewayError::ModelNotFound));
}

#[tokio::test]
async fn a_route_rejects_another_providers_key() {
    let state = Arc::new(TestServingState::without_models());
    let headers = headers(&[
        ("x-gradiated-api-key", "grad_test"),
        ("authorization", "Bearer sk-openai-example"),
    ]);

    let result = RequestCoordinator::new(state)
        .classify(
            &headers,
            FRONTIER_BODY,
            metadata().received_at,
            Protocol::AnthropicMessages,
            Some(RelayRoute::AnthropicMessages),
        )
        .await;

    assert_eq!(result.err(), Some(GatewayError::InvalidApiKey));
}

#[tokio::test]
async fn an_unusable_target_is_rejected_before_any_state_lookup() {
    for body in [
        &br#"{"messages":[{}]}"#[..],
        &br#"{"model":"","messages":[{}]}"#[..],
        &br#"{"model":"claude-sonnet-5","model":"model-a"}"#[..],
        &br#"{oops"#[..],
    ] {
        let state = Arc::new(TestServingState::without_models());
        let headers = headers(&[
            ("x-gradiated-api-key", "grad_test"),
            ("x-api-key", "sk-ant-example"),
        ]);

        let result = RequestCoordinator::new(state.clone())
            .classify(
                &headers,
                body,
                metadata().received_at,
                Protocol::AnthropicMessages,
                Some(RelayRoute::AnthropicMessages),
            )
            .await;

        assert!(
            matches!(result, Err(GatewayError::InvalidRequest { .. })),
            "expected a local rejection for {}",
            String::from_utf8_lossy(body)
        );
        assert!(
            state.calls.lock().unwrap().is_empty(),
            "an unusable target must not reach Valkey"
        );
    }
}

#[tokio::test]
async fn an_invalid_workspace_key_is_rejected_before_the_catalog() {
    let mut state = TestServingState::without_models();
    state.credential = None;
    let state = Arc::new(state);
    let headers = headers(&[
        ("x-gradiated-api-key", "grad_test"),
        ("x-api-key", "sk-ant-example"),
    ]);

    let result = RequestCoordinator::new(state.clone())
        .classify(
            &headers,
            FRONTIER_BODY,
            metadata().received_at,
            Protocol::AnthropicMessages,
            Some(RelayRoute::AnthropicMessages),
        )
        .await;

    assert_eq!(result.err(), Some(GatewayError::InvalidApiKey));
    assert_eq!(*state.calls.lock().unwrap(), ["credential"]);
}
