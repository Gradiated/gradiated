use super::support::{headers, CHAT_BODY, WORKSPACE_KEY};
use super::*;
use crate::test_support::{metadata, TestServingState, WORKSPACE_ID};
use crate::DeploymentStatus;

#[tokio::test]
async fn only_the_configured_workspace_can_target_a_deployment() {
    for workspace in [None, Some(Uuid::nil())] {
        let state = TestServingState::ready();
        let id = state.model.as_ref().unwrap().deployments[0].id;
        let coordinator =
            RequestCoordinator::new(Arc::new(state)).with_verification_workspace(workspace);
        let mut request_headers = headers(&WORKSPACE_KEY);
        request_headers.insert(
            "x-gradiated-verification-deployment",
            id.to_string().parse().unwrap(),
        );
        assert!(coordinator
            .classify(
                &request_headers,
                CHAT_BODY,
                metadata().received_at,
                Protocol::OpenAiChat
            )
            .await
            .is_err());
    }
}

#[tokio::test]
async fn verification_targets_one_healthy_canary_without_customer_fallbacks() {
    let mut state = TestServingState::ready();
    let model = state.model.as_mut().unwrap();
    let mut canary = model.deployments[0].clone();
    canary.id = Uuid::from_u128(99);
    canary.status = DeploymentStatus::Unavailable;
    model.deployments.push(canary.clone());
    let coordinator =
        RequestCoordinator::new(Arc::new(state)).with_verification_workspace(Some(WORKSPACE_ID));
    let regular = headers(&WORKSPACE_KEY);
    let classified = coordinator
        .classify(
            &regular,
            CHAT_BODY,
            metadata().received_at,
            Protocol::OpenAiChat,
        )
        .await
        .unwrap();
    let customer = coordinator
        .qualify(
            metadata(),
            &regular,
            classified.hosted,
            CHAT_BODY,
            RequestKind::Chat,
        )
        .unwrap();
    assert_ne!(customer.deployment.id, canary.id);
    assert!(!customer.is_verification);

    let mut targeted = regular;
    targeted.insert(
        "x-gradiated-verification-deployment",
        canary.id.to_string().parse().unwrap(),
    );
    let classified = coordinator
        .classify(
            &targeted,
            CHAT_BODY,
            metadata().received_at,
            Protocol::OpenAiChat,
        )
        .await
        .unwrap();
    let verified = coordinator
        .qualify(
            metadata(),
            &targeted,
            classified.hosted,
            CHAT_BODY,
            RequestKind::Chat,
        )
        .unwrap();
    assert_eq!(verified.deployment.id, canary.id);
    assert!(verified.is_verification);
    assert_eq!(verified.model_deployments.len(), 1);
}

#[tokio::test]
async fn missing_draining_and_malformed_targets_fail_closed() {
    for target in [
        "invalid".to_owned(),
        Uuid::nil().to_string(),
        Uuid::from_u128(99).to_string(),
    ] {
        let mut state = TestServingState::ready();
        state.model.as_mut().unwrap().deployments[0].id = Uuid::from_u128(99);
        state.model.as_mut().unwrap().deployments[0].status = DeploymentStatus::Draining;
        let coordinator = RequestCoordinator::new(Arc::new(state))
            .with_verification_workspace(Some(WORKSPACE_ID));
        let mut request_headers = headers(&WORKSPACE_KEY);
        request_headers.insert(
            "x-gradiated-verification-deployment",
            target.parse().unwrap(),
        );
        assert!(coordinator
            .classify(
                &request_headers,
                CHAT_BODY,
                metadata().received_at,
                Protocol::OpenAiChat
            )
            .await
            .is_err());
    }
}

#[tokio::test]
async fn duplicate_targets_are_rejected_even_for_the_verification_workspace() {
    let state = TestServingState::ready();
    let id = state.model.as_ref().unwrap().deployments[0].id.to_string();
    let coordinator =
        RequestCoordinator::new(Arc::new(state)).with_verification_workspace(Some(WORKSPACE_ID));
    let mut request_headers = headers(&WORKSPACE_KEY);
    request_headers.append("x-gradiated-verification-deployment", id.parse().unwrap());
    request_headers.append("x-gradiated-verification-deployment", id.parse().unwrap());
    assert!(coordinator
        .classify(
            &request_headers,
            CHAT_BODY,
            metadata().received_at,
            Protocol::OpenAiChat
        )
        .await
        .is_err());
}
