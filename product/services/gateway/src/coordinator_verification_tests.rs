use super::support::{headers, CHAT_BODY, WORKSPACE_KEY};
use super::*;
use crate::test_support::{metadata, TestServingState, WORKSPACE_ID};
use crate::DeploymentStatus;

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
        "x-gradiated-deployment-id",
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
        request_headers.insert("x-gradiated-deployment-id", target.parse().unwrap());
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
    request_headers.append("x-gradiated-deployment-id", id.parse().unwrap());
    request_headers.append("x-gradiated-deployment-id", id.parse().unwrap());
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

#[tokio::test]
async fn deployment_id_targets_an_isolated_replica_as_normal_workspace_traffic() {
    for workspace in [None, Some(Uuid::nil())] {
        let mut state = TestServingState::ready();
        let deployment = &mut state.model.as_mut().unwrap().deployments[0];
        deployment.status = DeploymentStatus::Unavailable;
        let id = deployment.id;
        let state = Arc::new(state);
        let coordinator =
            RequestCoordinator::new(state.clone()).with_verification_workspace(workspace);
        let mut request_headers = headers(&WORKSPACE_KEY);
        request_headers.insert("x-gradiated-deployment-id", id.to_string().parse().unwrap());
        let mut internal_verification = true;
        let classified = coordinator
            .classify_with_traffic(
                &request_headers,
                CHAT_BODY,
                metadata().received_at,
                Protocol::OpenAiChat,
                &mut internal_verification,
            )
            .await
            .unwrap();
        assert!(!internal_verification);
        let request = coordinator
            .qualify(
                metadata(),
                &request_headers,
                classified.hosted,
                CHAT_BODY,
                RequestKind::Chat,
            )
            .unwrap();
        assert_eq!(request.deployment.id, id);
        assert_eq!(request.model_deployments.len(), 1);
        assert!(!request.is_verification);
        assert_eq!(
            state.model.as_ref().unwrap().deployments[0].status,
            DeploymentStatus::Unavailable
        );
    }
}

#[tokio::test]
async fn public_deployment_targets_reject_invalid_duplicate_and_retired_headers() {
    for values in [
        vec!["not-a-uuid"],
        vec!["00000000-0000-0000-0000-000000000000"; 2],
    ] {
        let coordinator = RequestCoordinator::new(Arc::new(TestServingState::ready()));
        let mut request_headers = headers(&WORKSPACE_KEY);
        for value in values {
            request_headers.append("x-gradiated-deployment-id", value.parse().unwrap());
        }
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
    for headers_to_send in [
        vec!["x-gradiated-verification-deployment"],
        vec![
            "x-gradiated-deployment-id",
            "x-gradiated-verification-deployment",
        ],
    ] {
        let state = TestServingState::ready();
        let id = state.model.as_ref().unwrap().deployments[0].id.to_string();
        let coordinator = RequestCoordinator::new(Arc::new(state))
            .with_verification_workspace(Some(WORKSPACE_ID));
        let mut request_headers = headers(&WORKSPACE_KEY);
        for header in headers_to_send {
            request_headers.insert(header, id.parse().unwrap());
        }
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
async fn public_deployment_target_cannot_select_missing_or_draining_replicas() {
    for draining in [false, true] {
        let mut state = TestServingState::ready();
        let id = if draining {
            state.model.as_mut().unwrap().deployments[0].status = DeploymentStatus::Draining;
            state.model.as_ref().unwrap().deployments[0].id
        } else {
            Uuid::nil()
        };
        let coordinator = RequestCoordinator::new(Arc::new(state));
        let mut request_headers = headers(&WORKSPACE_KEY);
        request_headers.insert("x-gradiated-deployment-id", id.to_string().parse().unwrap());
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
