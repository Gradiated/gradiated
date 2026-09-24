use super::support::{
    classify_messages, headers, StateChange, CHAT_BODY, UNHOSTED_BODY, WORKSPACE_KEY,
};
use super::*;
use crate::test_support::TestServingState;

#[tokio::test]
async fn a_hosted_name_resolves_to_its_model() {
    let state = Arc::new(TestServingState::ready());
    let classified = classify_messages(state.clone(), &headers(&WORKSPACE_KEY), CHAT_BODY)
        .await
        .unwrap();

    assert_eq!(classified.request["model"], "model-a");
    assert_eq!(*state.requested_models.lock().unwrap(), ["model-a"]);
}

#[tokio::test]
async fn a_hosted_name_that_cannot_serve_is_unavailable() {
    let unservable: [(&str, StateChange); 2] = [
        ("unavailable", |state| {
            state.model.as_mut().unwrap().status = ModelStatus::Unavailable
        }),
        ("retired", |state| {
            state.model.as_mut().unwrap().status = ModelStatus::Retired
        }),
    ];
    let headers = headers(&WORKSPACE_KEY);

    for (name, change) in unservable {
        let mut state = TestServingState::ready();
        change(&mut state);
        let result = classify_messages(Arc::new(state), &headers, CHAT_BODY).await;

        assert_eq!(result.err(), Some(GatewayError::ModelUnavailable), "{name}");
    }
}

#[tokio::test]
async fn an_unhosted_name_is_a_local_error() {
    let result = classify_messages(
        Arc::new(TestServingState::without_models()),
        &headers(&WORKSPACE_KEY),
        UNHOSTED_BODY,
    )
    .await;

    assert_eq!(result.err(), Some(GatewayError::ModelNotFound));
}

#[tokio::test]
async fn a_provider_key_is_refused_before_any_lookup() {
    for provider in [
        ("x-api-key", "sk-ant-example"),
        ("authorization", "Bearer sk-proj-example"),
    ] {
        let state = Arc::new(TestServingState::ready());
        let headers = headers(&[("x-gradiated-api-key", "grad_test"), provider]);
        let result = classify_messages(state.clone(), &headers, CHAT_BODY).await;

        assert_eq!(
            result.err(),
            Some(GatewayError::InvalidApiKey),
            "{provider:?}"
        );
        assert!(state.calls.lock().unwrap().is_empty(), "{provider:?}");
    }
}
