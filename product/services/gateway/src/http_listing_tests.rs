use axum::{
    body::{to_bytes, Body},
    http::{Request, StatusCode},
};
use serde_json::Value;
use tower::ServiceExt;
use uuid::Uuid;

use super::*;
use crate::test_support::{TestServingState, ORGANIZATION_ID, WORKSPACE_ID};

async fn listed(owner: Option<Uuid>, verification: Option<Uuid>) -> Vec<String> {
    let mut state = TestServingState::ready();
    let model = state.model.as_mut().unwrap();
    model.organization_id = owner;
    // The provider document advertises only models with a release time.
    model.properties.released_at = Some(chrono::Utc::now());
    let application = support::router_for_with_verification(true, Arc::new(state), verification);

    let response = application
        .oneshot(
            Request::builder()
                .uri("/v1/models")
                .header("authorization", "Bearer grad_test")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body: Value =
        serde_json::from_slice(&to_bytes(response.into_body(), 1 << 20).await.unwrap()).unwrap();

    let ids = |list: &str, field: &str| -> Vec<String> {
        body[list]
            .as_array()
            .unwrap()
            .iter()
            .map(|model| model[field].as_str().unwrap().to_owned())
            .collect()
    };
    let data = ids("data", "id");
    // The TypeSafe model cards come from the same filtered list as `data`.
    assert_eq!(ids("models", "name"), data);
    data
}

/// The provider listing, also OpenRouter's, and its TypeSafe model cards show
/// another organization's own model to nobody, the verification workspace
/// included.
#[tokio::test]
async fn v1_models_omits_another_organizations_model() {
    let other = Uuid::from_u128(0xa1);

    assert_eq!(listed(None, None).await, ["model-a"]);
    assert_eq!(listed(Some(ORGANIZATION_ID), None).await, ["model-a"]);
    assert!(listed(Some(other), None).await.is_empty());
    assert!(listed(Some(other), Some(WORKSPACE_ID)).await.is_empty());
}
