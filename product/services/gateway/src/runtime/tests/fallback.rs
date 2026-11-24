use axum::http::{header, StatusCode};
use serde_json::{json, Value};
use uuid::Uuid;

use super::support::{credential_loader, data, deadline, expect_chunk, MockRuntime, CHAT, DONE};
use crate::{
    runtime::{
        ExternalCapacity, ExternalModel, ExternalRequest, FallbackRouter, FallbackRoutes, PriceCap,
        RuntimeStreamEvent,
    },
    InferenceRequest,
};

const MODEL: &str = "gradiated/model";
const BASETEN: &str = "baseten/model";
const MODAL: &str = "modal/model";

fn request(stream: bool) -> ExternalRequest {
    let mut request = InferenceRequest::parse(
        &serde_json::to_vec(&json!({
            "model": MODEL,
            "messages": [{ "role": "user", "content": "test" }],
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": false},
            "parallel_tool_calls": false,
        }))
        .unwrap(),
    )
    .unwrap();
    // Pick a session whose stable first choice is Baseten.
    request.session_id = Some("session-2".to_owned());

    ExternalRequest {
        generation_id: Uuid::from_u128(2),
        organization_id: Uuid::from_u128(3),
        workspace_id: Uuid::from_u128(4),
        model: ExternalModel::direct(MODEL),
        request,
        output_tokens: 64,
        deadline: deadline(10),
        price_cap: PriceCap {
            prompt: 1,
            completion: 2,
        },
    }
}

fn routes(baseten: &str, modal: &str) -> Value {
    json!({MODEL: [
        {"provider": "baseten", "base_url": format!("{baseten}/v1"), "model": BASETEN,
         "nano_usd_per_token": {"input": 500, "cached_input": 100, "output": 2000}},
        {"provider": "modal", "base_url": format!("{modal}/v1"), "model": MODAL,
         "nano_usd_per_token": {"input": 300, "cached_input": 70, "output": 1200, "cache_write": 20}}
    ]})
}

async fn secrets() -> MockRuntime {
    MockRuntime::builder()
        .route(
            "/",
            axum::routing::post(|bytes: axum::body::Bytes| async move {
                let request: Value = serde_json::from_slice(&bytes).unwrap();
                let key = match request.get("SecretId").and_then(Value::as_str) {
                    Some("gradiated/prod/providers/baseten") => "baseten-fixture-token",
                    Some("gradiated/prod/providers/modal") => "modal-fixture-token",
                    _ => return (StatusCode::FORBIDDEN, axum::Json(json!({}))),
                };
                let secret = json!({"activeSlot": "primary", "primaryApiKey": key});

                (
                    StatusCode::OK,
                    axum::Json(json!({"SecretString": secret.to_string()})),
                )
            }),
        )
        .start()
        .await
}

fn router(baseten: &MockRuntime, modal: &MockRuntime, secrets: &MockRuntime) -> FallbackRouter {
    let raw = routes(&baseten.url(), &modal.url()).to_string();
    let routes = FallbackRoutes::parse(Some(&raw)).unwrap();

    FallbackRouter::with_loader(&routes, credential_loader(secrets.url())).unwrap()
}

fn usage() -> Value {
    json!({"prompt_tokens": 15, "completion_tokens": 7, "total_tokens": 22,
        "prompt_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 1},
        "completion_tokens_details": {"reasoning_tokens": 6}})
}

fn completion(model: &str) -> Value {
    json!({"id": "chatcmpl-test", "object": "chat.completion", "created": 1, "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Answer"}, "finish_reason": "stop"}],
        "usage": usage()})
}

fn chunk(model: &str, choices: Value, tokens: Value) -> String {
    data(
        &json!({"id": "chatcmpl-test", "object": "chat.completion.chunk", "created": 1,
        "model": model, "choices": choices, "usage": tokens}),
    )
}

#[tokio::test]
async fn accepts_the_configured_response_model_for_streams_and_completions() {
    const RESPONSE_MODEL: &str = "baseten/response-model";
    let baseten = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, completion(RESPONSE_MODEL))
        .start()
        .await;
    let streaming = MockRuntime::builder()
        .sse(
            CHAT,
            &[
                chunk(
                    RESPONSE_MODEL,
                    json!([{"index": 0, "delta": {"content": "Answer"}}]),
                    Value::Null,
                ),
                chunk(
                    RESPONSE_MODEL,
                    json!([{"index": 0, "delta": {}, "finish_reason": "stop"}]),
                    Value::Null,
                ),
                chunk(RESPONSE_MODEL, json!([]), usage()),
                DONE.to_owned(),
            ],
        )
        .start()
        .await;
    let modal = MockRuntime::builder()
        .json(CHAT, StatusCode::TOO_MANY_REQUESTS, json!({}))
        .start()
        .await;
    let secrets = secrets().await;

    let configured_router = |endpoint: &str| {
        let mut config = routes(endpoint, &modal.url());
        config[MODEL][0]["response_model"] = json!(RESPONSE_MODEL);
        let routes = FallbackRoutes::parse(Some(&config.to_string())).unwrap();
        FallbackRouter::with_loader(&routes, credential_loader(secrets.url())).unwrap()
    };

    let result = configured_router(&baseten.url())
        .complete(request(false))
        .await
        .unwrap();
    assert_eq!(result.response()["model"], MODEL);
    assert_eq!(baseten.requests()[0].body["model"], BASETEN);

    let mut stream = configured_router(&streaming.url())
        .stream(request(true))
        .await
        .unwrap();
    let content = expect_chunk(stream.next_event().await.unwrap()).into_response();
    assert_eq!(content["model"], MODEL);
    assert_eq!(content["choices"][0]["delta"]["content"], "Answer");
    assert_eq!(streaming.requests()[0].body["model"], BASETEN);
    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn retries_the_other_provider_and_keeps_the_successful_provider_for_the_session() {
    let baseten = MockRuntime::builder()
        .json(CHAT, StatusCode::TOO_MANY_REQUESTS, json!({}))
        .start()
        .await;
    let modal = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, completion(MODAL))
        .start()
        .await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let result = router.complete(request(false)).await.unwrap();
    assert_eq!(result.response()["model"], MODEL);
    assert_eq!(result.upstream_cost_nano_usd(), Some(10_620));
    router.complete(request(false)).await.unwrap();

    let baseten_requests = baseten.requests();
    assert_eq!(baseten_requests.len(), 1);
    assert_eq!(
        baseten_requests[0].headers[header::AUTHORIZATION],
        "Bearer baseten-fixture-token"
    );
    let requests = modal.requests();
    assert_eq!(requests.len(), 2);
    assert_eq!(
        requests[0].headers[header::AUTHORIZATION],
        "Bearer modal-fixture-token"
    );
    let affinity = &requests[0].headers["modal-routing-affinity-key"];
    assert_eq!(affinity.as_bytes().len(), 64);
    assert_eq!(*affinity, requests[1].headers["modal-routing-affinity-key"]);
    assert_eq!(requests[0].body["model"], MODAL);
    assert_eq!(
        requests[0].body["chat_template_kwargs"]["enable_thinking"],
        false
    );
    assert_eq!(requests[0].body["parallel_tool_calls"], false);
    assert!(requests[0].body.get("provider").is_none());
    assert!(requests[0].body.get("session_id").is_none());

    let ids: Vec<_> = secrets
        .requests()
        .into_iter()
        .map(|call| call.body["SecretId"].clone())
        .collect();
    assert_eq!(
        ids,
        [
            json!("gradiated/prod/providers/baseten"),
            json!("gradiated/prod/providers/modal")
        ]
    );
}

#[tokio::test]
async fn retries_a_stream_after_role_only_output_and_records_final_usage() {
    let role = json!([{"index": 0, "delta": {"role": "assistant"}}]);
    let baseten = MockRuntime::builder()
        .sse(
            CHAT,
            &[
                chunk(BASETEN, role.clone(), Value::Null),
                data(&json!({"error": {"code": 503}})),
            ],
        )
        .start()
        .await;
    let modal = MockRuntime::builder()
        .sse(
            CHAT,
            &[
                chunk(MODAL, role, Value::Null),
                chunk(
                    MODAL,
                    json!([{"index": 0, "delta": {"content": "Answer"}}]),
                    Value::Null,
                ),
                chunk(
                    MODAL,
                    json!([{"index": 0, "delta": {}, "finish_reason": "stop"}]),
                    Value::Null,
                ),
                chunk(MODAL, json!([]), usage()),
                DONE.to_owned(),
            ],
        )
        .start()
        .await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let mut stream = router.stream(request(true)).await.unwrap();
    let role = expect_chunk(stream.next_event().await.unwrap()).into_response();
    assert_eq!(role["choices"][0]["delta"]["role"], "assistant");
    let content = expect_chunk(stream.next_event().await.unwrap()).into_response();
    assert_eq!(content["choices"][0]["delta"]["content"], "Answer");
    let finish = expect_chunk(stream.next_event().await.unwrap());
    assert_eq!(finish.finish_reason(), Some("stop"));
    let final_usage = expect_chunk(stream.next_event().await.unwrap());
    assert!(final_usage.is_terminal_usage());
    assert_eq!(final_usage.upstream_cost_nano_usd(), Some(10_620));
    assert!(matches!(
        stream.next_event().await.unwrap(),
        Some(RuntimeStreamEvent::Done)
    ));
    assert_eq!(baseten.requests().len(), 1);
    assert_eq!(
        modal.requests()[0].body["stream_options"]["include_usage"],
        true
    );
}

#[tokio::test]
async fn never_switches_providers_after_answer_output() {
    for delta in [
        json!({"content": "Partial"}),
        json!({"refusal": "Declined"}),
    ] {
        let content = chunk(BASETEN, json!([{"index": 0, "delta": delta}]), Value::Null);
        let baseten = MockRuntime::builder()
            .sse(CHAT, &[content, data(&json!({"error": {"code": 503}}))])
            .start()
            .await;
        let modal = MockRuntime::builder().start().await;
        let secrets = secrets().await;
        let router = router(&baseten, &modal, &secrets);

        let mut stream = router.stream(request(true)).await.unwrap();
        assert!(expect_chunk(stream.next_event().await.unwrap()).has_usable_output());
        assert!(stream.next_event().await.is_err());
        assert!(modal.requests().is_empty());
    }
}

#[test]
fn validates_direct_provider_endpoints() {
    let routes = routes(
        "https://inference.baseten.co",
        "https://example.us-west.modal.direct",
    );
    assert!(FallbackRoutes::parse(Some(&routes.to_string())).is_some());

    for (provider, url) in [
        (0, "https://openrouter.ai/v1"),
        (1, "https://modal.direct.example.com/v1"),
        (1, "https://.modal.direct/v1"),
        (0, "https://inference.baseten.co:8443/v1"),
        (1, "https://example.us-west.modal.direct:8443/v1"),
        (0, "https://token@inference.baseten.co/v1"),
        (1, "http://example.us-west.modal.direct/v1"),
    ] {
        let mut invalid = routes.clone();
        invalid[MODEL][provider]["base_url"] = json!(url);
        assert!(
            FallbackRoutes::parse(Some(&invalid.to_string())).is_none(),
            "{url}"
        );
    }
}

#[test]
fn rejects_duplicate_models_and_provider_entries() {
    let routes = routes(
        "https://inference.baseten.co",
        "https://test.us-west.modal.direct",
    );
    let entries = &routes[MODEL];
    let duplicate_keys = format!(r#"{{"{MODEL}": [], "{MODEL}": {entries}}}"#);
    assert!(FallbackRoutes::parse(Some(&duplicate_keys)).is_none());

    let duplicate_provider = json!({MODEL: [entries[0], entries[0]]});
    assert!(FallbackRoutes::parse(Some(&duplicate_provider.to_string())).is_none());

    let wrong_case = json!({"Gradiated/Model": entries});
    assert!(FallbackRoutes::parse(Some(&wrong_case.to_string())).is_none());
}

#[tokio::test]
async fn exhausted_fallbacks_try_each_provider_once() {
    let baseten = MockRuntime::builder()
        .json(CHAT, StatusCode::TOO_MANY_REQUESTS, json!({}))
        .start()
        .await;
    let modal = MockRuntime::builder()
        .json(CHAT, StatusCode::SERVICE_UNAVAILABLE, json!({}))
        .start()
        .await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let failure = router.complete(request(false)).await.unwrap_err();

    assert_eq!(failure.kind(), crate::RuntimeFailureKind::CapacityExceeded);
    assert_eq!(baseten.requests().len(), 1);
    assert_eq!(modal.requests().len(), 1);
}

#[tokio::test]
async fn does_not_start_a_retry_with_less_than_one_second_remaining() {
    let baseten = MockRuntime::builder()
        .json(CHAT, StatusCode::TOO_MANY_REQUESTS, json!({}))
        .start()
        .await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);
    let mut call = request(false);
    call.deadline = chrono::Utc::now() + chrono::TimeDelta::milliseconds(900);

    let failure = router.complete(call).await.unwrap_err();

    assert_eq!(failure.kind(), crate::RuntimeFailureKind::CapacityExceeded);
    assert_eq!(baseten.requests().len(), 1);
    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn a_slow_first_answer_opens_the_stream_and_preserves_prefetched_frames() {
    use std::{convert::Infallible, sync::Arc, time::Duration};

    use axum::{body::Body, routing::post};
    use futures_util::{stream, StreamExt};

    let answered = Arc::new(tokio::sync::Notify::new());
    let first = chunk(
        BASETEN,
        json!([{"index": 0, "delta": {"content": "Answer"}}]),
        Value::Null,
    );
    let split = first.len() / 2;
    let prefix = chunk(
        BASETEN,
        json!([{"index": 0, "delta": {"role": "assistant"}}]),
        Value::Null,
    ) + &first[..split];
    let suffix = first[split..].to_owned()
        + &chunk(
            BASETEN,
            json!([{"index": 0, "finish_reason": "stop"}]),
            Value::Null,
        )
        + &chunk(BASETEN, json!([]), usage())
        + DONE;
    let baseten = MockRuntime::builder()
        .route(
            CHAT,
            post({
                let answered = answered.clone();
                move || async move {
                    let body = stream::iter([Ok::<_, Infallible>(prefix)]).chain(stream::once(
                        async move {
                            answered.notified().await;
                            Ok::<_, Infallible>(suffix)
                        },
                    ));
                    (
                        [(header::CONTENT_TYPE, "text/event-stream")],
                        Body::from_stream(body),
                    )
                }
            }),
        )
        .start()
        .await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let mut stream = tokio::time::timeout(Duration::from_secs(3), router.stream(request(true)))
        .await
        .expect("opening should not wait for the first token")
        .unwrap();
    let role = expect_chunk(stream.next_event().await.unwrap()).into_response();
    assert_eq!(role["choices"][0]["delta"]["role"], "assistant");
    answered.notify_one();

    let content = expect_chunk(stream.next_event().await.unwrap()).into_response();
    assert_eq!(content["choices"][0]["delta"]["content"], "Answer");
    assert_eq!(
        expect_chunk(stream.next_event().await.unwrap()).finish_reason(),
        Some("stop")
    );
    assert!(expect_chunk(stream.next_event().await.unwrap()).is_terminal_usage());
    assert!(matches!(
        stream.next_event().await.unwrap(),
        Some(RuntimeStreamEvent::Done)
    ));
    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn a_failed_completion_reporting_usage_does_not_run_twice() {
    let baseten = MockRuntime::builder()
        .json(
            CHAT,
            StatusCode::OK,
            json!({"error": {"code": 503}, "usage": usage()}),
        )
        .start()
        .await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let failure = router.complete(request(false)).await.unwrap_err();

    assert_eq!(failure.kind(), crate::RuntimeFailureKind::CapacityExceeded);
    assert_eq!(failure.usage().output_tokens(), 7);
    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn a_malformed_completion_with_verified_usage_does_not_retry() {
    let mut malformed = completion(BASETEN);
    malformed["choices"][0]["finish_reason"] = Value::Null;
    let baseten = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, malformed)
        .start()
        .await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let failure = router.complete(request(false)).await.unwrap_err();

    assert_eq!(failure.kind(), crate::RuntimeFailureKind::ProtocolViolation);
    assert_eq!(failure.usage().output_tokens(), 7);
    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn a_malformed_stream_frame_with_verified_usage_does_not_retry() {
    let frame = chunk(BASETEN, json!([{"index": 0, "finish_reason": ""}]), usage());
    let baseten = MockRuntime::builder().sse(CHAT, &[frame]).start().await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let Err(failure) = router.stream(request(true)).await else {
        panic!("stream with a malformed finish reason opened");
    };

    assert_eq!(failure.kind(), crate::RuntimeFailureKind::ProtocolViolation);
    assert_eq!(failure.usage().output_tokens(), 7);
    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn provider_redirects_are_not_followed() {
    use axum::routing::post;

    let redirected = MockRuntime::builder().start().await;
    let target = format!("{}{CHAT}", redirected.url());
    let baseten =
        MockRuntime::builder()
            .route(
                CHAT,
                post(move || async move {
                    (StatusCode::TEMPORARY_REDIRECT, [(header::LOCATION, target)])
                }),
            )
            .start()
            .await;
    let modal = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, completion(MODAL))
        .start()
        .await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    router.complete(request(false)).await.unwrap();

    assert!(redirected.requests().is_empty());
    assert_eq!(modal.requests().len(), 1);
}

#[tokio::test]
async fn reported_cost_is_preferred_when_valid_and_ignored_when_malformed() {
    use axum::routing::post;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };

    let call = Arc::new(AtomicUsize::new(0));
    let baseten = MockRuntime::builder()
        .route(
            CHAT,
            post(move || {
                let call = call.clone();
                async move {
                    let mut response = completion(BASETEN);
                    response["usage"]["cost"] = match call.fetch_add(1, Ordering::Relaxed) {
                        0 => json!(0.000_003),
                        1 => json!("unknown"),
                        _ => json!(-0.000_000_000_1),
                    };

                    axum::Json(response)
                }
            }),
        )
        .start()
        .await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    for cost in [3_000, 17_500, 17_500] {
        let completion = router.complete(request(false)).await.unwrap();
        assert_eq!(completion.upstream_cost_nano_usd(), Some(cost));
    }

    assert!(modal.requests().is_empty());
}

#[tokio::test]
async fn retries_the_other_provider_when_the_first_rejects_a_request_with_400() {
    let baseten = MockRuntime::builder()
        .json(
            CHAT,
            StatusCode::BAD_REQUEST,
            json!({"error": {"message": "unsupported parameter"}}),
        )
        .start()
        .await;
    let modal = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, completion(MODAL))
        .start()
        .await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let result = router.complete(request(false)).await.unwrap();

    assert_eq!(result.response()["model"], MODEL);
    assert_eq!(baseten.requests().len(), 1);
    assert_eq!(modal.requests().len(), 1);
}

#[tokio::test]
async fn streaming_strips_continuous_usage_stats_and_forces_include_usage() {
    let baseten = MockRuntime::builder()
        .sse(
            CHAT,
            &[
                chunk(
                    BASETEN,
                    json!([{"index": 0, "delta": {"role": "assistant", "content": "Answer"}, "finish_reason": "stop"}]),
                    Value::Null,
                ),
                chunk(BASETEN, json!([]), usage()),
                DONE.to_owned(),
            ],
        )
        .start()
        .await;
    let modal = MockRuntime::builder().start().await;
    let secrets = secrets().await;
    let router = router(&baseten, &modal, &secrets);

    let mut call = request(true);
    call.request.parameters.insert(
        "stream_options".to_owned(),
        json!({"include_usage": false, "continuous_usage_stats": true}),
    );

    let mut stream = router.stream(call).await.unwrap();
    while stream.next_event().await.unwrap().is_some() {}

    let options = &baseten.requests()[0].body["stream_options"];
    assert_eq!(options["include_usage"], true);
    assert!(options.get("continuous_usage_stats").is_none());
    assert!(modal.requests().is_empty());
}
