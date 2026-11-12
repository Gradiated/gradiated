use axum::http::{header, StatusCode};
use serde_json::json;

use super::support::{client, MockRuntime};
use crate::ModelRuntime;

const COUNT: &str = "/v1/messages/count_tokens";

#[tokio::test]
async fn counting_preserves_anthropic_fields_and_uses_the_runtime_model_and_auth() {
    let runtime = MockRuntime::builder()
        .json(COUNT, StatusCode::OK, json!({"input_tokens": 89}))
        .start()
        .await;
    let body = json!({
        "model": "public/model",
        "system": "Be brief",
        "messages": [{"role": "user", "content": "Hello"}],
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "tools": [{"name": "weather", "input_schema": {"type": "object"}}]
    });

    assert_eq!(
        client()
            .count_tokens(&runtime.renamed_deployment(), body.clone())
            .await
            .unwrap(),
        89
    );
    let requests = runtime.requests();
    assert_eq!(requests.len(), 1);
    assert_eq!(requests[0].path, COUNT);
    assert_eq!(
        requests[0].headers[header::AUTHORIZATION],
        "Bearer runtime-secret"
    );
    let mut expected = body;
    expected["model"] = json!("runtime-model");
    assert_eq!(requests[0].body, expected);
}

#[tokio::test]
async fn counting_rejects_invalid_or_missing_counts_and_upstream_errors() {
    for (status, body) in [
        (StatusCode::OK, json!({})),
        (StatusCode::OK, json!({"input_tokens": -1})),
        (StatusCode::OK, json!({"input_tokens": 1.5})),
        (StatusCode::OK, json!({"input_tokens": "89"})),
        (
            StatusCode::OK,
            json!({"input_tokens": 9_007_199_254_740_992_u64}),
        ),
        (StatusCode::SERVICE_UNAVAILABLE, json!({"input_tokens": 89})),
    ] {
        let runtime = MockRuntime::builder()
            .json(COUNT, status, body)
            .start()
            .await;

        assert!(client()
            .count_tokens(&runtime.deployment(), json!({"messages": []}))
            .await
            .is_err());
    }
}
