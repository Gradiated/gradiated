use super::support::{headers, list_models, qualify_chat, CHAT_BODY, WORKSPACE_KEY};
use super::*;
use crate::test_support::{metadata, TestServingState, ORGANIZATION_ID, WORKSPACE_ID};

const OTHER_ORGANIZATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a700080000000000000a1);
const OTHER_WORKSPACE_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a700080000000000000a2);

fn owned_by(organization_id: Uuid) -> TestServingState {
    let mut state = TestServingState::ready();
    state.model.as_mut().unwrap().organization_id = Some(organization_id);
    state
}

async fn classify_with(
    state: TestServingState,
    verification_workspace: Option<Uuid>,
) -> Result<ClassifiedRequest, GatewayError> {
    RequestCoordinator::new(Arc::new(state))
        .with_verification_workspace(verification_workspace)
        .classify(
            &headers(&WORKSPACE_KEY),
            CHAT_BODY,
            metadata().received_at,
            Protocol::OpenAiChat,
        )
        .await
}

#[tokio::test]
async fn the_owner_calls_its_own_model() {
    let request = qualify_chat(Arc::new(owned_by(ORGANIZATION_ID)), CHAT_BODY)
        .await
        .unwrap();

    assert_eq!(request.identity.organization_id, ORGANIZATION_ID);
    assert!(request.local.is_some());
}

#[tokio::test]
async fn another_organizations_model_fails_exactly_like_an_unknown_model() {
    let mut unknown = TestServingState::ready();
    unknown.model = None;
    let unknown = qualify_chat(Arc::new(unknown), CHAT_BODY).await.err();

    let owned = qualify_chat(Arc::new(owned_by(OTHER_ORGANIZATION_ID)), CHAT_BODY)
        .await
        .err();

    assert_eq!(owned, Some(GatewayError::ModelNotFound));
    assert_eq!(owned, unknown);
}

#[tokio::test]
async fn the_verification_workspace_calls_any_organizations_model() {
    let classified = classify_with(owned_by(OTHER_ORGANIZATION_ID), Some(WORKSPACE_ID))
        .await
        .unwrap();

    assert_eq!(classified.hosted.model.id, "model-a");
}

#[tokio::test]
async fn only_the_configured_verification_workspace_is_exempt() {
    for verification_workspace in [None, Some(OTHER_WORKSPACE_ID)] {
        let result = classify_with(owned_by(OTHER_ORGANIZATION_ID), verification_workspace).await;

        assert_eq!(
            result.err(),
            Some(GatewayError::ModelNotFound),
            "{verification_workspace:?}"
        );
    }
}

#[tokio::test]
async fn listing_shows_public_and_own_models_but_never_another_organizations() {
    for (owner, listed) in [
        (None, true),
        (Some(ORGANIZATION_ID), true),
        (Some(OTHER_ORGANIZATION_ID), false),
    ] {
        let mut state = TestServingState::ready();
        state.model.as_mut().unwrap().organization_id = owner;
        let models = list_models(Arc::new(state)).await.unwrap();

        assert_eq!(models.len(), usize::from(listed), "{owner:?}");
    }
}

#[tokio::test]
async fn the_verification_workspace_does_not_list_other_organizations_models() {
    let models = RequestCoordinator::new(Arc::new(owned_by(OTHER_ORGANIZATION_ID)))
        .with_verification_workspace(Some(WORKSPACE_ID))
        .list_models(&headers(&WORKSPACE_KEY), metadata().received_at)
        .await
        .unwrap();

    assert!(models.is_empty());
}

/// The catalog retires an owned model whose name a private model already has;
/// the private model then resolves instead of both being ambiguous.
#[tokio::test]
async fn a_retired_hosted_model_yields_its_name_to_a_private_model() {
    for (status, lookups) in [
        (ModelStatus::Available, &["acme/task-a"][..]),
        (ModelStatus::Retired, &["acme/task-a", "model-a"][..]),
    ] {
        let mut state = owned_by(ORGANIZATION_ID);
        let model = state.model.as_mut().unwrap();
        model.status = status;
        model.aliases = vec!["acme/task-a".to_owned()];
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
        });
        let state = Arc::new(state);

        let result =
            qualify_chat(state.clone(), br#"{"model":"acme/task-a","messages":[{}]}"#).await;

        assert!(result.is_err(), "{status:?}");
        assert_eq!(
            *state.requested_models.lock().unwrap(),
            lookups,
            "{status:?}"
        );
    }
}
