use super::support::{
    classify_messages, headers, StateChange, CHAT_BODY, FRONTIER_BODY, PROVIDER_KEYS,
};
use super::*;
use crate::auth::Provider;
use crate::test_support::{metadata, TestServingState};

#[tokio::test]
async fn a_hosted_name_serves_locally_even_with_a_provider_key() {
    let state = Arc::new(TestServingState::ready());
    let headers = headers(&PROVIDER_KEYS);
    let classified = classify_messages(state.clone(), &headers, CHAT_BODY)
        .await
        .unwrap();

    let RequestRoute::Hosted { request, .. } = classified else {
        panic!("a hosted name must serve locally");
    };
    assert_eq!(request["model"], "model-a");
    assert_eq!(*state.requested_models.lock().unwrap(), ["model-a"]);
}

#[tokio::test]
async fn a_hosted_name_that_cannot_serve_never_relays() {
    let unservable: [(&str, StateChange); 2] = [
        ("unavailable", |state| {
            state.model.as_mut().unwrap().status = ModelStatus::Unavailable
        }),
        ("retired", |state| {
            state.model.as_mut().unwrap().status = ModelStatus::Retired
        }),
    ];
    let headers = headers(&PROVIDER_KEYS);

    for (name, change) in unservable {
        let mut state = TestServingState::ready();
        change(&mut state);
        let result = classify_messages(Arc::new(state), &headers, CHAT_BODY).await;

        assert_eq!(
            result.err(),
            Some(GatewayError::ModelUnavailable),
            "a {name} hosted name must not reach a provider"
        );
    }
}

#[tokio::test]
async fn an_unresolved_name_relays_with_the_matching_provider_key() {
    let state = Arc::new(TestServingState::without_models());
    let headers = headers(&PROVIDER_KEYS);
    let classified = classify_messages(state.clone(), &headers, FRONTIER_BODY)
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
    let headers = headers(&[("x-gradiated-api-key", "grad_test")]);
    let result = classify_messages(
        Arc::new(TestServingState::without_models()),
        &headers,
        FRONTIER_BODY,
    )
    .await;

    assert_eq!(result.err(), Some(GatewayError::ModelNotFound));
}

#[tokio::test]
async fn an_endpoint_without_a_relay_route_never_relays_an_unresolved_name() {
    let headers = headers(&PROVIDER_KEYS);
    let result = RequestCoordinator::new(Arc::new(TestServingState::without_models()))
        .classify(
            &headers,
            FRONTIER_BODY,
            metadata().received_at,
            Protocol::OpenAiChat,
            None,
        )
        .await;

    assert_eq!(result.err(), Some(GatewayError::ModelNotFound));
}

#[tokio::test]
async fn a_route_rejects_another_providers_key() {
    let headers = headers(&[
        ("x-gradiated-api-key", "grad_test"),
        ("authorization", "Bearer sk-openai-example"),
    ]);
    let result = classify_messages(
        Arc::new(TestServingState::without_models()),
        &headers,
        FRONTIER_BODY,
    )
    .await;

    assert_eq!(result.err(), Some(GatewayError::InvalidApiKey));
}

#[tokio::test]
async fn an_unusable_target_is_rejected_before_any_state_lookup() {
    let headers = headers(&PROVIDER_KEYS);

    for body in [
        &br#"{"messages":[{}]}"#[..],
        &br#"{"model":"","messages":[{}]}"#[..],
        &br#"{"model":"claude-sonnet-5","model":"model-a"}"#[..],
        &br#"{oops"#[..],
    ] {
        let state = Arc::new(TestServingState::without_models());
        let result = classify_messages(state.clone(), &headers, body).await;

        assert!(
            matches!(result, Err(GatewayError::InvalidRequest { .. })),
            "expected a local rejection for {}",
            String::from_utf8_lossy(body)
        );
        assert!(
            state.calls.lock().unwrap().is_empty(),
            "an unusable target must not reach the serving state"
        );
    }
}
