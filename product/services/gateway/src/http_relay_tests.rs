use std::sync::Arc;

use axum::{body::to_bytes, http::StatusCode, Router};
use tower::ServiceExt;

use super::support::{json_body, json_request, router_for};
use crate::{
    relay::support::{start_provider, TestProvider, TestReply, CUSTOMER_KEY, JSON_REPLY},
    test_support::TestServingState,
};

async fn application() -> (Router, TestProvider, Arc<TestServingState>) {
    let (address, provider) = start_provider(TestReply::Json).await;

    // An active workspace with an empty prepaid balance and no hosted model, so
    // every name is unresolved and a relay must not be charged.
    let mut state = TestServingState::without_models();
    state.account.as_mut().unwrap().balance = 0;
    let state = Arc::new(state);

    let application = router_for(true, state.clone(), &format!("http://{address}"));

    (application, provider, state)
}

#[tokio::test]
async fn an_unresolved_model_relays_with_the_customer_key() {
    for path in ["/v1/messages", "/messages"] {
        let (application, seen, serving_state) = application().await;
        let response = application
            .oneshot(json_request(
                path,
                &[
                    ("x-gradiated-api-key", "grad_test"),
                    ("x-api-key", CUSTOMER_KEY),
                    ("anthropic-version", "2023-06-01"),
                ],
                r#"{"model":"claude-sonnet-5","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
            ))
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK, "{path}");
        assert!(
            response.headers().get("x-generation-id").is_some(),
            "{path}"
        );
        assert_eq!(
            response.headers().get("content-type").unwrap(),
            "application/json",
            "{path}"
        );
        let body = to_bytes(response.into_body(), 4_096).await.unwrap();
        assert_eq!(body.as_ref(), JSON_REPLY.as_bytes(), "{path}");

        let upstream = seen.headers().unwrap();
        assert_eq!(upstream.get("x-api-key").unwrap(), CUSTOMER_KEY, "{path}");
        assert_eq!(
            upstream.get("anthropic-version").unwrap(),
            "2023-06-01",
            "{path}"
        );
        assert!(upstream.get("x-gradiated-api-key").is_none(), "{path}");
        assert_eq!(
            serving_state.lookups("credential"),
            1,
            "one request authorizes once"
        );
        assert_eq!(
            serving_state.lookups("model"),
            1,
            "one request resolves the catalog once"
        );
        assert_eq!(
            seen.body().unwrap(),
            br#"{"model":"claude-sonnet-5","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
            "the provider receives the caller's bytes, not a translation"
        );
    }
}

#[tokio::test]
async fn an_unresolved_model_without_a_provider_key_returns_the_local_error() {
    let (application, seen, _) = application().await;
    let response = application
        .oneshot(json_request(
            "/v1/messages",
            &[("x-gradiated-api-key", "grad_test")],
            r#"{"model":"claude-sonnet-5","max_tokens":16}"#,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let value = json_body(response).await;
    assert_eq!(value["type"], "error");
    assert_eq!(value["error"]["code"], "model_not_found");
    assert!(seen.headers().is_none(), "no provider connection may open");
}

#[tokio::test]
async fn a_relayed_request_never_forwards_the_gradiated_bearer_key() {
    let (application, seen, _) = application().await;
    let response = application
        .oneshot(json_request(
            "/v1/messages",
            &[
                ("authorization", "Bearer grad_test"),
                ("x-api-key", CUSTOMER_KEY),
            ],
            r#"{"model":"claude-sonnet-5","max_tokens":16}"#,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let upstream = seen.headers().unwrap();
    assert_eq!(upstream.get("x-api-key").unwrap(), CUSTOMER_KEY);
    assert!(upstream.get("authorization").is_none());
}

#[tokio::test]
async fn an_inbound_hop_header_is_refused_without_contacting_the_provider() {
    let (application, provider, _) = application().await;
    let response = application
        .oneshot(json_request(
            "/v1/messages",
            &[
                ("x-gradiated-api-key", "grad_test"),
                ("x-api-key", CUSTOMER_KEY),
                ("x-gradiated-hop", "1"),
            ],
            r#"{"model":"claude-sonnet-5","max_tokens":16}"#,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let value = json_body(response).await;
    assert_eq!(value["type"], "error");
    assert_eq!(value["error"]["code"], "invalid_request");
    assert!(provider.headers().is_none());
}

#[tokio::test]
async fn count_tokens_never_relays_an_unresolved_model() {
    let (application, provider, _) = application().await;
    let response = application
        .oneshot(json_request(
            "/v1/messages/count_tokens",
            &[
                ("x-gradiated-api-key", "grad_test"),
                ("x-api-key", CUSTOMER_KEY),
            ],
            r#"{"model":"claude-sonnet-5","messages":[{"role":"user","content":"hi"}]}"#,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let value = json_body(response).await;
    assert_eq!(value["type"], "error");
    assert_eq!(value["error"]["code"], "model_not_found");
    assert!(provider.headers().is_none());
}
