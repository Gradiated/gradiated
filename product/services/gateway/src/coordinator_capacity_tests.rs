use super::support::{headers, WORKSPACE_KEY};
use super::*;
use crate::{
    catalog::ProviderCompliance,
    test_support::{metadata, TestServingState},
    ModelCatalogResponse, ModelParameterDescriptor,
};

const MAPPING: &str = "author/model-a";

/// A model OpenRouter can serve, with `deployments` of our own.
fn mapped(deployments: usize) -> TestServingState {
    let mut state = TestServingState::ready();
    let model = state.model.as_mut().unwrap();
    model.deployments.truncate(deployments);
    model.openrouter_model_id = Some(MAPPING.to_owned());

    state
}

fn coordinator(state: TestServingState) -> RequestCoordinator {
    RequestCoordinator::new(Arc::new(state))
}

async fn qualify_with(
    coordinator: &RequestCoordinator,
    headers: &HeaderMap,
    body: &[u8],
    kind: RequestKind,
) -> Result<QualifiedRequest, GatewayError> {
    let classified = coordinator
        .classify(headers, body, metadata().received_at, Protocol::OpenAiChat)
        .await?;

    coordinator.qualify(metadata(), headers, classified.hosted, body, kind)
}

async fn qualify(state: TestServingState, body: &[u8]) -> Result<QualifiedRequest, GatewayError> {
    qualify_with(
        &coordinator(state),
        &headers(&WORKSPACE_KEY),
        body,
        RequestKind::Chat,
    )
    .await
}

const CHAT: &[u8] = br#"{"model":"model-a","messages":[{"role":"user","content":"hi"}]}"#;

#[tokio::test]
async fn a_mapped_model_needs_no_deployment_to_qualify() {
    let request = qualify(mapped(0), CHAT).await.unwrap();

    assert_eq!(request.local, None);
    assert_eq!(request.base, None);
    assert_eq!(request.external, Some(ExternalModel::openrouter(MAPPING)));
    assert_eq!(request.request.model, "model-a");
    assert_eq!(request.pricing.prompt(), 100);
}

#[tokio::test]
async fn a_mapped_model_with_deployments_keeps_them_first() {
    let request = qualify(mapped(1), CHAT).await.unwrap();

    assert!(request.local.is_some());
    assert_eq!(request.external, Some(ExternalModel::openrouter(MAPPING)));
}

#[tokio::test]
async fn catalog_membership_alone_does_not_make_a_model_servable_elsewhere() {
    let mut unmapped = mapped(0);
    unmapped.model.as_mut().unwrap().openrouter_model_id = None;
    assert_eq!(
        qualify(unmapped, CHAT).await.err(),
        Some(GatewayError::ServingStateUnavailable)
    );

    let request = qualify(
        {
            let mut state = mapped(1);
            state.model.as_mut().unwrap().openrouter_model_id = None;
            state
        },
        CHAT,
    )
    .await
    .unwrap();
    assert_eq!(request.external, None);
}

#[tokio::test]
async fn fallback_does_not_enable_an_unavailable_or_retired_model() {
    for status in [ModelStatus::Unavailable, ModelStatus::Retired] {
        let mut state = mapped(0);
        state.model.as_mut().unwrap().status = status;

        assert_eq!(
            qualify(state, CHAT).await.err(),
            Some(GatewayError::ModelUnavailable),
            "{status:?}"
        );
    }
}

#[tokio::test]
async fn fallback_does_not_bypass_balance_or_authentication() {
    let mut unfunded = mapped(0);
    unfunded.account.as_mut().unwrap().balance = 0;
    assert_eq!(
        qualify(unfunded, CHAT).await.err(),
        Some(GatewayError::InsufficientBalance)
    );

    assert_eq!(
        qualify_with(
            &coordinator(mapped(0)),
            &HeaderMap::new(),
            CHAT,
            RequestKind::Chat
        )
        .await
        .err(),
        Some(GatewayError::InvalidApiKey)
    );
}

fn from_openrouter(
    mut state: TestServingState,
    openrouter_channel: Option<bool>,
) -> TestServingState {
    state.account.as_mut().unwrap().organization_kind =
        crate::domain::OrganizationKind::DistributionChannel;
    state.credential.as_mut().unwrap().openrouter_channel = openrouter_channel;
    state
}

#[tokio::test]
async fn openrouter_traffic_is_never_sent_back_to_openrouter() {
    assert_eq!(
        qualify(from_openrouter(mapped(1), Some(true)), CHAT)
            .await
            .unwrap()
            .external,
        None
    );
    assert_eq!(
        qualify(from_openrouter(mapped(0), Some(true)), CHAT)
            .await
            .err(),
        Some(GatewayError::RuntimeUnavailable)
    );
}

#[tokio::test]
async fn another_distribution_channel_is_served_like_a_customer() {
    let request = qualify(from_openrouter(mapped(0), Some(false)), CHAT)
        .await
        .unwrap();

    assert_eq!(request.external, Some(ExternalModel::openrouter(MAPPING)));
}

#[tokio::test]
async fn a_credential_cached_before_the_channel_was_known_is_treated_as_openrouter() {
    let mut state = mapped(1);
    state.credential.as_mut().unwrap().openrouter_channel = None;

    assert_eq!(qualify(state, CHAT).await.unwrap().external, None);
}

#[tokio::test]
async fn a_request_pinned_to_a_deployment_keeps_it() {
    let state = mapped(1);
    let id = state.model.as_ref().unwrap().deployments[0].id.to_string();
    let pinned = headers(&[WORKSPACE_KEY[0], ("x-gradiated-deployment-id", id.as_str())]);

    let request = qualify_with(&coordinator(state), &pinned, CHAT, RequestKind::Chat)
        .await
        .unwrap();

    assert_eq!(request.external, None);
    assert_eq!(request.local_capacity().deployment.id.to_string(), id);
}

#[tokio::test]
async fn a_parameter_openrouter_would_ignore_keeps_the_request_local() {
    let with_template = |deployments| {
        let mut state = mapped(deployments);
        state
            .model
            .as_mut()
            .unwrap()
            .properties
            .passthrough_parameters
            .insert(
                "chat_template_kwargs".to_owned(),
                ModelParameterDescriptor::Unknown,
            );
        state
    };
    let body = br#"{"model":"model-a","messages":[{}],"chat_template_kwargs":{"thinking":false}}"#;

    assert_eq!(
        qualify(with_template(1), body).await.unwrap().external,
        None
    );
    assert_eq!(
        qualify(with_template(0), body).await.err(),
        Some(GatewayError::RuntimeUnavailable)
    );
    let supported = br#"{"model":"model-a","messages":[{}],"temperature":0.2}"#;
    assert!(qualify(with_template(0), supported)
        .await
        .unwrap()
        .external
        .is_some());
}

#[tokio::test]
async fn a_newly_advertised_parameter_is_sent_to_openrouter() {
    let mut state = mapped(0);
    state
        .model
        .as_mut()
        .unwrap()
        .properties
        .passthrough_parameters
        .insert("verbosity".to_owned(), ModelParameterDescriptor::Unknown);
    let body = br#"{"model":"model-a","messages":[{}],"verbosity":"low"}"#;

    let request = qualify(state, body).await.unwrap();

    assert_eq!(request.external, Some(ExternalModel::openrouter(MAPPING)));
    assert!(request.request.parameters.contains_key("verbosity"));
}

#[tokio::test]
async fn a_mapping_to_another_variant_or_a_moving_alias_is_ignored() {
    for mapping in [
        "author/model-a:free",
        "author/model-a:nitro",
        "~author/model-latest",
        "Author/Model-A",
        "model-a",
        "",
    ] {
        let mut state = mapped(1);
        state.model.as_mut().unwrap().openrouter_model_id = Some(mapping.to_owned());

        assert_eq!(
            qualify(state, CHAT).await.unwrap().external,
            None,
            "{mapping}"
        );
    }
}

#[tokio::test]
async fn systemone_is_never_served_by_openrouter() {
    let mut state = mapped(1);
    state.model.as_mut().unwrap().deployments[0]
        .release
        .protocol = Some(crate::RuntimeProtocol::SystemOne);
    let mut decision = crate::systemone::fixtures::request_value();
    decision["model"] = serde_json::json!("model-a");
    let body = serde_json::to_vec(&decision).unwrap();
    let request = qualify_with(
        &coordinator(state),
        &headers(&WORKSPACE_KEY),
        &body,
        RequestKind::SystemOne,
    )
    .await
    .unwrap();
    assert_eq!(request.external, None);

    let result = qualify_with(
        &coordinator(mapped(0)),
        &headers(&WORKSPACE_KEY),
        &body,
        RequestKind::SystemOne,
    )
    .await;
    assert_eq!(
        result.err(),
        Some(GatewayError::unsupported_parameter("model"))
    );
}

async fn listing(state: TestServingState) -> serde_json::Value {
    let models = coordinator(state)
        .list_models(&headers(&WORKSPACE_KEY), metadata().received_at)
        .await
        .unwrap();
    let compliance = ProviderCompliance {
        zdr: true,
        hipaa: false,
    };

    serde_json::to_value(ModelCatalogResponse::from_models(&models, compliance)).unwrap()
}

fn released(mut state: TestServingState) -> TestServingState {
    state.model.as_mut().unwrap().properties.released_at = Some(metadata().received_at);
    state
}

#[tokio::test]
async fn a_mapped_model_lists_as_ready_without_a_residency_claim() {
    let listed = listing(released(mapped(0))).await;

    let model = &listed["data"][0];
    assert_eq!(model["id"], "model-a");
    assert_eq!(model["is_ready"], true);
    assert_eq!(model["datacenters"], serde_json::json!([]));
    assert!(model.get("deployment_region").is_none());
    assert!(!listed.to_string().contains("openrouter"));
    assert!(!listed.to_string().contains(MAPPING));
}

#[tokio::test]
async fn openrouter_sees_only_our_own_capacity() {
    let openrouter = |deployments| from_openrouter(released(mapped(deployments)), Some(true));

    assert_eq!(listing(openrouter(0)).await["data"], serde_json::json!([]));

    let mut unhealthy = openrouter(1);
    unhealthy.statuses = Some(Vec::new());
    assert_eq!(listing(unhealthy).await["data"][0]["is_ready"], false);

    let other_channel = from_openrouter(released(mapped(0)), Some(false));
    assert_eq!(listing(other_channel).await["data"][0]["is_ready"], true);
}

#[tokio::test]
async fn a_model_without_capacity_fails_before_its_protocol_is_checked() {
    let mut state = TestServingState::ready();
    let deployment = &mut state.model.as_mut().unwrap().deployments[0];
    deployment.release.protocol = Some(crate::RuntimeProtocol::SystemOne);
    deployment.status = crate::DeploymentStatus::Draining;
    let mut decision = crate::systemone::fixtures::request_value();
    decision["model"] = serde_json::json!("model-a");

    let result = qualify_with(
        &coordinator(state),
        &headers(&WORKSPACE_KEY),
        &serde_json::to_vec(&decision).unwrap(),
        RequestKind::SystemOne,
    )
    .await;

    assert_eq!(result.err(), Some(GatewayError::ServingStateUnavailable));
}
