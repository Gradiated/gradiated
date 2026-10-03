use axum::http::{HeaderMap, HeaderValue};

use super::support::{headers, qualify, qualify_chat, StateChange, CHAT_BODY, WORKSPACE_KEY};
use super::*;
use crate::test_support::{model, TestServingState, ORGANIZATION_ID};

const DECISION_BODY: &[u8] = br#"{"model":"MODEL-A","state":"charged twice","questions":{"billing":{"type":"noul","instructions":"Duplicate charge?"}}}"#;

fn system_one_state() -> TestServingState {
    let mut state = TestServingState::ready();
    state.model.as_mut().unwrap().deployments[0]
        .release
        .protocol = Some(crate::RuntimeProtocol::SystemOne);

    state
}

#[tokio::test]
async fn qualifies_the_complete_pre_admission_request() {
    let state = Arc::new(TestServingState::ready());
    let request = qualify_chat(
        state.clone(),
        br#"{
                "model":"model-a",
                "messages":[{"role":"user","content":"hello"}],
                "service_tier":"fast",
                "temperature":0.5,
                "response_format":"json"
            }"#,
    )
    .await
    .unwrap();

    assert_eq!(request.effective_output_tokens, 1_024);
    assert_eq!(request.max_prompt_tokens, 7_168);
    assert_eq!(request.max_context_tokens, 8_192);
    assert_eq!(request.identity.organization_id, ORGANIZATION_ID);
    assert_eq!(request.request.parameters["temperature"], 0.5);
    assert_eq!(request.pricing.prompt(), 150);
    assert_eq!(request.pricing.cached_prompt(), 75);
    assert_eq!(request.pricing.completion(), 300);
    assert!(request.served_release_digest.starts_with("sha256:"));
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account", "model"]
    );
}

#[tokio::test]
async fn canonicalizes_model_ids_before_lookup_and_dispatch() {
    let state = Arc::new(TestServingState::ready());
    let request = qualify_chat(state.clone(), br#"{"model":"MODEL-A","messages":[{}]}"#)
        .await
        .unwrap();

    assert_eq!(request.request.model, "model-a");
    let upstream_body = request
        .request
        .into_upstream_body_for_model(request.effective_output_tokens, None);
    assert_eq!(upstream_body["model"], "model-a");
    assert_eq!(*state.requested_models.lock().unwrap(), ["model-a"]);
}

#[tokio::test]
async fn a_decision_request_qualifies_through_the_shared_access_pipeline() {
    let state = Arc::new(system_one_state());
    let qualified = qualify(
        state.clone(),
        &headers(&WORKSPACE_KEY),
        DECISION_BODY,
        RequestKind::SystemOne,
    )
    .await
    .unwrap();

    assert_eq!(qualified.effective_output_tokens, 0);
    assert_eq!(qualified.request.model, "model-a");
    assert_eq!(qualified.request.decision.unwrap().model, "model-a");
    assert_eq!(
        *state.calls.lock().unwrap(),
        ["credential", "workspace", "account", "model"]
    );
}

#[tokio::test]
async fn each_protocol_is_refused_on_the_other_protocols_deployment() {
    let chat_on_decision = qualify_chat(Arc::new(system_one_state()), CHAT_BODY).await;
    assert_eq!(
        chat_on_decision.err(),
        Some(GatewayError::unsupported_parameter("model"))
    );

    let decision_on_chat = qualify(
        Arc::new(TestServingState::ready()),
        &headers(&WORKSPACE_KEY),
        DECISION_BODY,
        RequestKind::SystemOne,
    )
    .await;
    assert_eq!(
        decision_on_chat.err(),
        Some(GatewayError::unsupported_parameter("model"))
    );
}

#[tokio::test]
async fn a_decision_request_without_credentials_is_refused() {
    let state = Arc::new(system_one_state());
    let result = qualify(
        state.clone(),
        &HeaderMap::new(),
        DECISION_BODY,
        RequestKind::SystemOne,
    )
    .await;

    assert_eq!(result.err(), Some(GatewayError::InvalidApiKey));
    assert!(state.calls.lock().unwrap().is_empty());
}

#[tokio::test]
async fn a_body_session_id_wins_over_the_headers() {
    let mut headers = headers(&WORKSPACE_KEY);
    headers.insert("x-gradiated-session-id", HeaderValue::from_static("header"));
    let request = qualify(
        Arc::new(TestServingState::ready()),
        &headers,
        br#"{"model":"model-a","messages":[{}],"session_id":"body"}"#,
        RequestKind::Chat,
    )
    .await
    .unwrap();

    assert_eq!(request.request.session_id.as_deref(), Some("body"));
}

#[tokio::test]
async fn only_the_gradiated_session_header_is_read() {
    let mut headers = headers(&WORKSPACE_KEY);
    headers.insert("x-session-id", HeaderValue::from_static("generic"));
    let request = qualify(
        Arc::new(TestServingState::ready()),
        &headers,
        CHAT_BODY,
        RequestKind::Chat,
    )
    .await
    .unwrap();

    assert_eq!(request.request.session_id, None);
}

#[tokio::test]
async fn a_session_header_must_be_visible_ascii_of_at_most_256_bytes() {
    let longest = "s".repeat(256);
    let accepted = HeaderValue::from_str(&longest).unwrap();
    let mut headers = headers(&WORKSPACE_KEY);
    headers.insert("x-gradiated-session-id", accepted);
    let request = qualify(
        Arc::new(TestServingState::ready()),
        &headers,
        CHAT_BODY,
        RequestKind::Chat,
    )
    .await
    .unwrap();
    assert_eq!(request.request.session_id, Some(longest));

    for rejected in [
        HeaderValue::from_bytes(b"caf\xc3\xa9").unwrap(),
        HeaderValue::from_static(""),
        HeaderValue::from_str(&"s".repeat(257)).unwrap(),
    ] {
        let mut headers = headers.clone();
        headers.insert("x-gradiated-session-id", rejected.clone());
        let result = qualify(
            Arc::new(TestServingState::ready()),
            &headers,
            CHAT_BODY,
            RequestKind::Chat,
        )
        .await;

        assert_eq!(
            result.err(),
            Some(GatewayError::invalid_request(Some("session_id"))),
            "{rejected:?}"
        );
    }
}

#[tokio::test]
async fn request_and_model_failures_remain_pre_admission() {
    let priority_override = Arc::new(TestServingState::ready());
    let mut override_headers = headers(&WORKSPACE_KEY);
    override_headers.insert("x-vllm-priority", HeaderValue::from_static("-100"));
    let result = qualify(
        priority_override.clone(),
        &override_headers,
        CHAT_BODY,
        RequestKind::Chat,
    )
    .await;
    assert_eq!(result, Err(GatewayError::invalid_request(Some("priority"))));
    assert!(
        priority_override.calls.lock().unwrap().is_empty(),
        "a header the caller must not send is refused before any state lookup"
    );

    let malformed = Arc::new(TestServingState::ready());
    let result = qualify_chat(malformed.clone(), br#"{"model":"model-a"}"#).await;
    assert_eq!(result, Err(GatewayError::invalid_request(None)));
    assert_eq!(
        *malformed.calls.lock().unwrap(),
        ["credential", "workspace", "account", "model"],
        "classification needs only the target, so the rest of the request shape \
         is checked after the model resolves"
    );

    let model_failures: [(&str, StateChange, GatewayError); 5] = [
        (
            "missing",
            |state| state.model = None,
            GatewayError::ModelNotFound,
        ),
        (
            "unavailable",
            |state| state.model.as_mut().unwrap().status = ModelStatus::Unavailable,
            GatewayError::ModelUnavailable,
        ),
        (
            "without deployments",
            |state| state.model.as_mut().unwrap().deployments.clear(),
            GatewayError::ServingStateUnavailable,
        ),
        (
            "with an invalid serving deployment",
            |state| {
                state.model.as_mut().unwrap().deployments[0].service_url =
                    "ftp://runtime.internal".to_owned()
            },
            GatewayError::ServingStateUnavailable,
        ),
        (
            "with an unsafe price",
            |state| {
                state.model.as_mut().unwrap().properties.input_modalities[0].pricing[0] =
                    crate::InputTokenPrice::Prompt {
                        unit: crate::TokenUnit::Token,
                        cost: crate::model::MAX_SAFE_INTEGER + 1,
                    }
            },
            GatewayError::ServingStateUnavailable,
        ),
    ];
    for (name, break_state, expected) in model_failures {
        let mut state = TestServingState::ready();
        break_state(&mut state);
        let result = qualify_chat(Arc::new(state), CHAT_BODY).await;

        assert_eq!(result.err(), Some(expected), "{name}");
    }
}

#[tokio::test]
async fn ignores_unadvertised_model_parameters() {
    let request = qualify_chat(
        Arc::new(TestServingState::ready()),
        br#"{
                "model":"model-a",
                "messages":[{}],
                "seed":7,
                "tools":[{"type":"function"}]
            }"#,
    )
    .await
    .unwrap();

    assert!(!request.request.parameters.contains_key("seed"));
    assert!(!request.request.parameters.contains_key("tools"));
}

#[tokio::test]
async fn rejects_invalid_supported_model_parameters() {
    for (body, expected) in [
        (
            br#"{"model":"model-a","messages":[{}],"temperature":3}"#.as_slice(),
            GatewayError::invalid_request(Some("temperature")),
        ),
        (
            br#"{"model":"model-a","messages":[{}],"max_tokens":4097}"#.as_slice(),
            GatewayError::context_length_exceeded("max_tokens"),
        ),
        (
            br#"{"model":"model-a","messages":[{}],"max_completion_tokens":4097}"#.as_slice(),
            GatewayError::context_length_exceeded("max_completion_tokens"),
        ),
    ] {
        let result = qualify_chat(Arc::new(TestServingState::ready()), body).await;

        assert_eq!(result.err(), Some(expected));
    }

    let mut state = TestServingState::ready();
    state.model = Some(model(false));
    let result = qualify_chat(
        Arc::new(state),
        br#"{"model":"model-a","messages":[{}],"stream":true}"#,
    )
    .await;
    assert_eq!(
        result.err(),
        Some(GatewayError::unsupported_parameter("stream"))
    );
}

#[tokio::test]
async fn an_output_limit_equal_to_the_model_maximum_is_accepted() {
    let request = qualify_chat(
        Arc::new(TestServingState::ready()),
        br#"{"model":"model-a","messages":[{}],"max_completion_tokens":4096}"#,
    )
    .await
    .unwrap();

    assert_eq!(request.effective_output_tokens, 4_096);
}

#[tokio::test]
async fn a_rollout_keeps_a_healthy_release_until_its_replacement_is_ready() {
    use crate::test_support::metadata;
    use crate::{DeploymentRuntimeStatus, DeploymentStatus};

    for (old_ready, new_ready, new_accepting, expected_revision) in [
        (true, false, false, "old"),
        (true, true, true, "either"),
        (true, true, false, "old"),
        (false, true, true, "new"),
    ] {
        let mut state = TestServingState::ready();
        let model = state.model.as_mut().unwrap();
        model.deployments[0].release.runtime_revision = "old".to_owned();
        let mut next = model.deployments[0].clone();
        next.id = Uuid::from_u128(98765);
        next.release.runtime_revision = "new".to_owned();
        next.status = DeploymentStatus::Available;
        model.deployments.push(next);
        state.statuses = Some(
            model
                .deployments
                .iter()
                .zip([old_ready, new_ready])
                .map(|(deployment, ready)| DeploymentRuntimeStatus {
                    schema_version: 1,
                    deployment_id: deployment.id,
                    runtime_revision: deployment.release.runtime_revision.clone(),
                    received_at: metadata().received_at,
                    healthy: ready,
                    accepting_requests: ready
                        && (deployment.release.runtime_revision == "old" || new_accepting),
                    reason_code: None,
                })
                .collect(),
        );

        let qualified = qualify_chat(Arc::new(state), CHAT_BODY).await.unwrap();
        if expected_revision != "either" {
            assert_eq!(
                qualified.deployment.release.runtime_revision,
                expected_revision
            );
        }
        assert_eq!(
            qualified.served_release_digest,
            qualified.deployment.served_release_digest().unwrap()
        );
        assert_eq!(qualified.request.model, "model-a");
    }
}

#[tokio::test]
async fn a_partial_replacement_does_not_reduce_the_serving_pool() {
    use crate::test_support::metadata;
    use crate::DeploymentRuntimeStatus;

    for (new_ready, old_accepting, new_accepting) in [
        (1, 2, 1),
        (1, 1, 1),
        (2, 2, 2),
        (2, 2, 1),
        (2, 2, 0),
        (1, 0, 1),
    ] {
        let mut state = TestServingState::ready();
        let model = state.model.as_mut().unwrap();
        let template = model.deployments[0].clone();
        model.deployments = (0..4)
            .map(|index| {
                let mut deployment = template.clone();
                deployment.id = Uuid::from_u128(100 + index);
                deployment.release.runtime_revision =
                    if index < 2 { "old" } else { "new" }.to_owned();
                deployment
            })
            .collect();
        state.statuses = Some(
            model
                .deployments
                .iter()
                .enumerate()
                .map(|(index, deployment)| {
                    let old = index < 2;
                    DeploymentRuntimeStatus {
                        schema_version: 1,
                        deployment_id: deployment.id,
                        runtime_revision: deployment.release.runtime_revision.clone(),
                        received_at: metadata().received_at,
                        healthy: old || index - 2 < new_ready,
                        accepting_requests: if old {
                            index < old_accepting
                        } else {
                            index - 2 < new_accepting
                        },
                        reason_code: None,
                    }
                })
                .collect(),
        );
        let model = state.model.clone().unwrap();
        let coordinator = RequestCoordinator::new(Arc::new(state));
        let expected: HashSet<_> = (0..old_accepting)
            .chain(2..2 + new_accepting.min(new_ready))
            .map(|index| Uuid::from_u128(100 + index as u128))
            .collect();
        let mut selected_ids = HashSet::new();
        for selection in 0..128 {
            let selected = coordinator
                .prefer_ready_release(
                    model.clone(),
                    metadata().received_at,
                    Some(selection as u128),
                )
                .await
                .unwrap();
            selected_ids.insert(selected.serving_deployment().unwrap().deployment.id);
        }
        assert_eq!(selected_ids, expected);
    }
}

#[tokio::test]
async fn rollout_sessions_keep_their_revision_when_another_replica_stops_accepting() {
    use crate::test_support::metadata;
    use crate::DeploymentRuntimeStatus;

    let mut state = TestServingState::ready();
    let model = state.model.as_mut().unwrap();
    let template = model.deployments[0].clone();
    model.deployments = (0..3)
        .map(|index| {
            let mut deployment = template.clone();
            deployment.id = Uuid::from_u128(100 + index);
            deployment.release.runtime_revision = if index < 2 { "old" } else { "new" }.to_owned();
            deployment
        })
        .collect();
    state.statuses = Some(
        model
            .deployments
            .iter()
            .map(|deployment| DeploymentRuntimeStatus {
                schema_version: 1,
                deployment_id: deployment.id,
                runtime_revision: deployment.release.runtime_revision.clone(),
                received_at: metadata().received_at,
                healthy: true,
                accepting_requests: true,
                reason_code: None,
            })
            .collect(),
    );
    let model = state.model.clone().unwrap();
    let coordinator = RequestCoordinator::new(Arc::new(state));
    let mut changed = TestServingState::ready();
    changed.model = Some(model.clone());
    changed.statuses = Some(
        model
            .deployments
            .iter()
            .map(|deployment| DeploymentRuntimeStatus {
                schema_version: 1,
                deployment_id: deployment.id,
                runtime_revision: deployment.release.runtime_revision.clone(),
                received_at: metadata().received_at,
                healthy: true,
                accepting_requests: deployment.id != Uuid::from_u128(100),
                reason_code: None,
            })
            .collect(),
    );
    let changed = RequestCoordinator::new(Arc::new(changed));
    for seed in 0..128 {
        let before = coordinator
            .prefer_ready_release(model.clone(), metadata().received_at, Some(seed))
            .await
            .unwrap();
        let before = before.serving_deployment().unwrap().deployment;
        let after = changed
            .prefer_ready_release(model.clone(), metadata().received_at, Some(seed))
            .await
            .unwrap();
        let after = after.serving_deployment().unwrap().deployment;
        if before.id != Uuid::from_u128(100) {
            assert_eq!(before.id, after.id);
            assert_eq!(
                before.release.runtime_revision,
                after.release.runtime_revision
            );
        }
    }
}
