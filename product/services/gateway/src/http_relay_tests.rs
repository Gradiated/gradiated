use std::{
    net::SocketAddr,
    sync::{Arc, Mutex},
};

use axum::{
    body::{to_bytes, Body},
    extract::State,
    http::{HeaderMap, Request, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Router,
};
use tokio::net::TcpListener;
use tower::ServiceExt;

use super::tests::router_for;
use super::*;
use crate::test_support::TestServingState;

const CUSTOMER_KEY: &str = "sk-ant-customer";

#[derive(Clone)]
struct SeenRequest {
    headers: Arc<Mutex<Option<HeaderMap>>>,
    body: Arc<Mutex<Option<Vec<u8>>>>,
}

async fn provider_handler(
    State(seen): State<SeenRequest>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    *seen.headers.lock().unwrap() = Some(headers);
    *seen.body.lock().unwrap() = Some(body.to_vec());

    (
        StatusCode::OK,
        [("content-type", "application/json")],
        r#"{"id":"msg_1","model":"claude-sonnet-5","usage":{"input_tokens":3}}"#,
    )
        .into_response()
}

async fn application() -> (Router, SeenRequest, Arc<TestServingState>) {
    let seen = SeenRequest {
        headers: Arc::new(Mutex::new(None)),
        body: Arc::new(Mutex::new(None)),
    };
    let provider = Router::new()
        .route("/v1/messages", post(provider_handler))
        .with_state(seen.clone());
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, provider).await.unwrap();
    });

    // An active workspace with an empty prepaid balance and no hosted model, so
    // every name is unresolved and a relay must not be charged.
    let mut state = TestServingState::without_models();
    state.account.as_mut().unwrap().balance = 0;
    let state = Arc::new(state);

    let application = router_for(true, state.clone(), &format!("http://{address}"));

    (application, seen, state)
}

fn messages_request(path: &str, headers: &[(&'static str, &str)], body: &str) -> Request<Body> {
    let mut request = Request::builder()
        .method("POST")
        .uri(path)
        .header("content-type", "application/json")
        .header("anthropic-version", "2023-06-01");
    for (name, value) in headers {
        request = request.header(*name, *value);
    }

    request.body(Body::from(body.to_owned())).unwrap()
}

#[tokio::test]
async fn an_unresolved_model_relays_with_the_customer_key() {
    for path in ["/v1/messages", "/messages"] {
        let (application, seen, serving_state) = application().await;
        let response = application
            .oneshot(messages_request(
                path,
                &[
                    ("x-gradiated-api-key", "grad_test"),
                    ("x-api-key", CUSTOMER_KEY),
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
        assert_eq!(
            body.as_ref(),
            br#"{"id":"msg_1","model":"claude-sonnet-5","usage":{"input_tokens":3}}"#,
            "{path}"
        );

        let upstream = seen.headers.lock().unwrap().clone().unwrap();
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
            seen.body.lock().unwrap().clone().unwrap(),
            br#"{"model":"claude-sonnet-5","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}"#,
            "the provider receives the caller's bytes, not a translation"
        );
    }
}

#[tokio::test]
async fn an_unresolved_model_without_a_provider_key_returns_the_local_error() {
    let (application, seen, _) = application().await;
    let response = application
        .oneshot(messages_request(
            "/v1/messages",
            &[("x-gradiated-api-key", "grad_test")],
            r#"{"model":"claude-sonnet-5","max_tokens":16}"#,
        ))
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    let body = to_bytes(response.into_body(), 4_096).await.unwrap();
    let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(value["type"], "error");
    assert_eq!(value["error"]["code"], "model_not_found");
    assert!(
        seen.headers.lock().unwrap().is_none(),
        "no provider connection may open"
    );
}

#[tokio::test]
async fn a_relayed_request_never_forwards_the_gradiated_bearer_key() {
    let (application, seen, _) = application().await;
    let response = application
        .oneshot(messages_request(
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
    let upstream = seen.headers.lock().unwrap().clone().unwrap();
    assert_eq!(upstream.get("x-api-key").unwrap(), CUSTOMER_KEY);
    assert!(upstream.get("authorization").is_none());
}
