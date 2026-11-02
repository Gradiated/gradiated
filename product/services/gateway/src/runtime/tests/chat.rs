use axum::http::{header, StatusCode};
use serde_json::{json, Value};

use super::support::{
    chat_request, client, data, deadline, expect_chunk, streaming_request, MockRuntime, CHAT, DONE,
};
use crate::{
    runtime::{
        chat::{normalize_completion, ChatStreamNormalizer},
        client::ModelNames,
        ModelRuntime, RuntimeFailure, RuntimeFailureKind, RuntimeStreamEvent,
    },
    ServiceTier,
};

fn models(requested: &str, runtime: &str) -> ModelNames {
    ModelNames {
        requested: requested.to_owned(),
        runtime: runtime.to_owned(),
    }
}

fn completion() -> Value {
    json!({
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 1_777_000_000,
        "model": "model-a",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "hello",
                "reasoning_content": null,
                "tool_calls": null
            },
            "logprobs": null,
            "finish_reason": "stop",
            "matched_stop": 1
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "prompt_tokens_details": {"cached_tokens": 4},
            "reasoning_tokens": 2
        },
        "metadata": {"private_runtime_field": true}
    })
}

fn chunk(delta: Value, finish_reason: Option<&str>) -> Value {
    json!({
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "runtime-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}]
    })
}

fn terminal_usage() -> Value {
    json!({
        "id": "chatcmpl-stream",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "runtime-model",
        "choices": [],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}
    })
}

#[tokio::test]
async fn sends_one_qualified_request_and_normalizes_the_response() {
    let mut upstream = completion();
    upstream["model"] = json!("runtime-model");
    let runtime = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, upstream)
        .start()
        .await;
    let deployment = runtime.renamed_deployment();
    let mut request = chat_request();
    request.service_tier = ServiceTier::Fast;

    let completion = client()
        .complete(&deployment, request, 1_024, deadline(5))
        .await
        .unwrap();

    let requests = runtime.requests();
    assert_eq!(requests.len(), 1);
    assert_eq!(
        requests[0].headers[header::AUTHORIZATION],
        "Bearer runtime-secret"
    );
    assert!(!requests[0].headers.contains_key(header::CONTENT_LENGTH));
    assert_eq!(requests[0].body["model"], "runtime-model");
    assert_eq!(requests[0].body["messages"][0]["content"], "hello");
    assert_eq!(requests[0].body["temperature"], 0.25);
    assert_eq!(requests[0].body["tools"][0]["function"]["name"], "weather");
    assert_eq!(requests[0].body["max_completion_tokens"], 1_024);
    assert_eq!(requests[0].body["stream"], false);
    assert_eq!(requests[0].body["priority"], -10);

    assert_eq!(completion.finish_reason(), "stop");
    assert_eq!(completion.usage().input_tokens(), 10);
    assert_eq!(completion.usage().cached_input_tokens(), 4);
    assert_eq!(completion.usage().output_tokens(), 5);
    assert_eq!(completion.usage().reasoning_tokens(), 2);
    assert_eq!(completion.response()["usage"]["total_tokens"], 15);
    assert_eq!(completion.response()["model"], "model-a");
    assert!(completion.response().get("metadata").is_none());
    assert!(completion.response()["choices"][0]
        .get("matched_stop")
        .is_none());
}

#[tokio::test]
async fn rejects_an_untrustworthy_completion() {
    let mut mismatched_model = completion();
    mismatched_model["model"] = json!("other-model");
    let mut no_choices = completion();
    no_choices["choices"] = json!([]);
    let mut long_finish_reason = completion();
    long_finish_reason["choices"][0]["finish_reason"] = json!("x".repeat(101));
    let mut inconsistent_total = completion();
    inconsistent_total["usage"]["total_tokens"] = json!(16);

    for (case, body) in [
        ("runtime model mismatch", mismatched_model),
        ("empty choices", no_choices),
        ("finish reason over 100 characters", long_finish_reason),
        ("total tokens inconsistent", inconsistent_total),
    ] {
        let runtime = MockRuntime::builder()
            .json(CHAT, StatusCode::OK, body)
            .start()
            .await;

        let failure = client()
            .complete(&runtime.deployment(), chat_request(), 1_024, deadline(5))
            .await
            .unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
    }
}

#[test]
fn rejects_missing_unparseable_and_impossible_engine_usage() {
    for usage in [
        Value::Null,
        json!("not usage"),
        json!({}),
        json!({"prompt_tokens":"10","completion_tokens":2,"total_tokens":12}),
        json!({"prompt_tokens":-1,"completion_tokens":2,"total_tokens":1}),
        json!({"prompt_tokens":1.5,"completion_tokens":2,"total_tokens":3.5}),
        json!({"prompt_tokens":10,"completion_tokens":2,"total_tokens":99}),
        json!({"prompt_tokens":10,"completion_tokens":2,"total_tokens":12,"prompt_tokens_details":{"cached_tokens":11}}),
        json!({"prompt_tokens":10,"completion_tokens":2,"total_tokens":12,"reasoning_tokens":3}),
        json!({"prompt_tokens":10,"completion_tokens":2,"total_tokens":12,"completion_tokens_details":{"reasoning_tokens":3}}),
    ] {
        let mut response = completion();
        response["usage"] = usage.clone();
        let completion_failure = normalize_completion(
            &serde_json::to_vec(&response).unwrap(),
            &models("model-a", "model-a"),
        )
        .unwrap_err();

        let terminal = json!({"id":"chatcmpl-1","object":"chat.completion.chunk",
            "created":1,"model":"model-a","choices":[],"usage":usage});
        let stream_failure = ChatStreamNormalizer::new(models("model-a", "model-a"))
            .normalize(&serde_json::to_vec(&terminal).unwrap())
            .unwrap_err();

        assert_eq!(
            completion_failure.kind(),
            RuntimeFailureKind::ProtocolViolation
        );
        assert_eq!(stream_failure.kind(), RuntimeFailureKind::ProtocolViolation);
    }

    let mut missing = completion();
    missing.as_object_mut().unwrap().remove("usage");
    assert_eq!(
        normalize_completion(
            &serde_json::to_vec(&missing).unwrap(),
            &models("model-a", "model-a")
        )
        .unwrap_err()
        .kind(),
        RuntimeFailureKind::ProtocolViolation
    );
}

#[tokio::test]
async fn parses_and_normalizes_sglang_streaming_events() {
    let mut first = chunk(json!({"reasoning": "hello"}), None);
    first["usage"] = json!({"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11});
    let runtime = MockRuntime::builder()
        .sse(
            CHAT,
            &[
                data(&first),
                data(&chunk(json!({}), Some("stop"))),
                data(&terminal_usage()),
                DONE.to_owned(),
            ],
        )
        .start()
        .await;
    let deployment = runtime.renamed_deployment();
    let mut request = streaming_request();
    request.service_tier = ServiceTier::Flex;

    let mut events = client()
        .stream(&deployment, request, 32, deadline(5))
        .await
        .unwrap();

    let first = expect_chunk(events.next_event().await.unwrap());
    assert!(first.has_usable_output());
    assert_eq!(first.usage().unwrap().output_tokens(), 1);
    let first = first.into_response();
    assert_eq!(first["model"], "model-a");
    assert!(first.get("usage").is_none());

    let finish = expect_chunk(events.next_event().await.unwrap());
    assert_eq!(finish.finish_reason(), Some("stop"));
    assert!(!finish.has_usable_output());

    let usage = expect_chunk(events.next_event().await.unwrap());
    assert!(usage.is_terminal_usage());
    assert_eq!(usage.into_response()["usage"]["total_tokens"], 11);

    assert_eq!(
        events.next_event().await.unwrap(),
        Some(RuntimeStreamEvent::Done)
    );
    assert_eq!(events.next_event().await.unwrap(), None);

    let requests = runtime.requests();
    assert_eq!(requests[0].body["model"], "runtime-model");
    assert_eq!(requests[0].body["stream"], true);
    assert_eq!(requests[0].body["priority"], 10);
    assert_eq!(requests[0].body["stream_options"]["include_usage"], true);
    assert_eq!(
        requests[0].body["stream_options"]["continuous_usage_stats"],
        true
    );
}

async fn drain_stream(frames: &[String]) -> Result<(), RuntimeFailure> {
    let runtime = MockRuntime::builder().sse(CHAT, frames).start().await;
    let deployment = runtime.renamed_deployment();

    let mut events = client()
        .stream(&deployment, streaming_request(), 32, deadline(5))
        .await?;
    while events.next_event().await?.is_some() {}

    Ok(())
}

#[tokio::test]
async fn rejects_sglang_queue_abort_before_opening_the_stream() {
    let runtime = MockRuntime::builder()
        .sse(
            CHAT,
            &[data(&json!({
                "error": {
                    "message": "private queue detail",
                    "type": "SERVICE_UNAVAILABLE",
                    "code": 503
                }
            }))],
        )
        .start()
        .await;
    let result = client()
        .stream(
            &runtime.renamed_deployment(),
            streaming_request(),
            32,
            deadline(5),
        )
        .await;
    let Err(failure) = result else {
        panic!("queue rejection must fail before returning a stream");
    };

    assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
    assert_eq!(failure.usage(), crate::NormalizedUsage::zero());
}

#[tokio::test]
async fn admission_peek_is_bounded_and_preserves_a_fragmented_first_event() {
    use futures_util::StreamExt;
    use std::{convert::Infallible, sync::Arc, time::Duration};

    let release = Arc::new(tokio::sync::Notify::new());
    let first = data(&chunk(json!({"content": "hello"}), None));
    let split = first.len() / 2;
    let prefix = first[..split].to_owned();
    let suffix = first[split..].to_owned()
        + &data(&chunk(json!({}), Some("stop")))
        + &data(&terminal_usage())
        + DONE;
    let server_release = release.clone();
    let runtime = MockRuntime::builder()
        .route(
            CHAT,
            axum::routing::post(move || {
                let prefix = prefix.clone();
                let suffix = suffix.clone();
                let release = server_release.clone();
                async move {
                    let chunks = futures_util::stream::once(async { Ok::<_, Infallible>(prefix) })
                        .chain(futures_util::stream::once(async move {
                            release.notified().await;
                            Ok::<_, Infallible>(suffix)
                        }));
                    (
                        [(header::CONTENT_TYPE, "text/event-stream")],
                        axum::body::Body::from_stream(chunks),
                    )
                }
            }),
        )
        .start()
        .await;
    let opened = tokio::time::timeout(
        Duration::from_secs(2),
        client().stream(
            &runtime.renamed_deployment(),
            streaming_request(),
            32,
            deadline(5),
        ),
    )
    .await;
    let mut stream = opened
        .expect("headers must not wait for the first complete event")
        .unwrap();
    release.notify_one();

    let first = expect_chunk(stream.next_event().await.unwrap()).into_response();
    assert_eq!(first["choices"][0]["delta"]["content"], "hello");
    while stream.next_event().await.unwrap().is_some() {}
}

#[tokio::test]
async fn retains_usage_on_a_first_frame_rejection_to_prevent_retry() {
    let runtime = MockRuntime::builder()
        .sse(
            CHAT,
            &[data(&json!({
                "error": {"type": "SERVICE_UNAVAILABLE", "code": 503},
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}
            }))],
        )
        .start()
        .await;
    let result = client()
        .stream(
            &runtime.renamed_deployment(),
            streaming_request(),
            32,
            deadline(5),
        )
        .await;
    let Err(failure) = result else {
        panic!("reported work must not be discarded");
    };

    assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
    assert_eq!(failure.usage().input_tokens(), 10);
    assert_eq!(failure.usage().output_tokens(), 1);
}

#[tokio::test]
async fn does_not_reclassify_a_queue_error_after_output_as_an_open_failure() {
    let runtime = MockRuntime::builder()
        .sse(
            CHAT,
            &[
                data(&chunk(json!({"reasoning_content": "working"}), None)),
                data(&json!({"error": {"type": "SERVICE_UNAVAILABLE", "code": 503}})),
            ],
        )
        .start()
        .await;
    let mut stream = client()
        .stream(
            &runtime.renamed_deployment(),
            streaming_request(),
            32,
            deadline(5),
        )
        .await
        .unwrap();

    assert!(expect_chunk(stream.next_event().await.unwrap()).has_usable_output());
    assert_eq!(
        stream.next_event().await.unwrap_err().kind(),
        RuntimeFailureKind::ProtocolViolation
    );
}

#[tokio::test]
async fn rejects_an_untrustworthy_stream() {
    let text = chunk(json!({"content": "hi"}), None);
    let mut other_id = text.clone();
    other_id["id"] = json!("chatcmpl-other");
    let mut other_created = text.clone();
    other_created["created"] = json!(2);
    let mut terminal_without_usage = terminal_usage();
    terminal_without_usage
        .as_object_mut()
        .unwrap()
        .remove("usage");
    let oversized = chunk(json!({"content": "x".repeat(1_000_001)}), None);

    for (case, frames) in [
        ("id changes", vec![data(&text), data(&other_id)]),
        ("created changes", vec![data(&text), data(&other_created)]),
        (
            "terminal chunk without usage",
            vec![data(&terminal_without_usage)],
        ),
        (
            "named event",
            vec![format!("event: token\n{}", data(&text))],
        ),
        ("event id", vec![format!("id: 1\n{}", data(&text))]),
        ("retry hint", vec![format!("retry: 10\n{}", data(&text))]),
        ("event data over 1 MB", vec![data(&oversized)]),
    ] {
        let mut frames = frames;
        frames.push(DONE.to_owned());

        let failure = drain_stream(&frames).await.unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
    }
}

#[tokio::test]
async fn rejects_a_successful_stream_that_is_not_server_sent_events() {
    let runtime = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, completion())
        .start()
        .await;

    let failure = client()
        .stream(&runtime.deployment(), streaming_request(), 32, deadline(5))
        .await
        .err()
        .unwrap();

    assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
}

#[tokio::test]
async fn rejects_frames_out_of_order() {
    let text = data(&chunk(json!({"content": "hi"}), None));
    let usage = data(&terminal_usage());

    for (case, frames) in [
        (
            "end of stream before done",
            vec![text.clone(), usage.clone()],
        ),
        ("end of stream before usage", vec![text.clone()]),
        (
            "done before the terminal usage",
            vec![text.clone(), DONE.to_owned()],
        ),
        (
            "content after the terminal usage",
            vec![usage.clone(), text.clone(), DONE.to_owned()],
        ),
        (
            "second terminal usage",
            vec![usage.clone(), usage, DONE.to_owned()],
        ),
    ] {
        let failure = drain_stream(&frames).await.unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{case}"
        );
        assert_eq!(failure.diagnostic_code(), "frame_order", "{case}");
    }
}

#[test]
fn normalized_wire_json_is_stable() {
    let mut stream_chunk = chunk(json!({"content": "hi"}), None);
    stream_chunk["choices"][0]["matched_stop"] = json!(null);

    let chunk = ChatStreamNormalizer::new(models("model-a", "runtime-model"))
        .normalize(&serde_json::to_vec(&stream_chunk).unwrap())
        .unwrap();
    let completion = normalize_completion(
        &serde_json::to_vec(&completion()).unwrap(),
        &models("model-a", "model-a"),
    )
    .unwrap();

    assert_eq!(
        chunk.into_response().to_string(),
        r#"{"id":"chatcmpl-stream","object":"chat.completion.chunk","created":1,"model":"model-a","choices":[{"index":0,"delta":{"content":"hi"},"logprobs":null,"finish_reason":null}]}"#
    );
    assert_eq!(
        completion.into_response().to_string(),
        r#"{"id":"chatcmpl-1","object":"chat.completion","created":1777000000,"model":"model-a","choices":[{"index":0,"message":{"role":"assistant","content":"hello","reasoning_content":null,"tool_calls":null},"logprobs":null,"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15,"prompt_tokens_details":{"cached_tokens":4},"completion_tokens_details":{"reasoning_tokens":2}}}"#
    );
}

fn private_model_request(stream: bool) -> crate::InferenceRequest {
    let mut request = if stream {
        streaming_request()
    } else {
        chat_request()
    };
    request.model = "task-a-v1".to_owned();
    request.runtime_model_name = Some("workspace/immutable-version".to_owned());
    request
}

#[tokio::test]
async fn sends_one_normal_completion_request_for_a_private_model() {
    let request = private_model_request(false);
    let mut response = completion();
    response["model"] = request.runtime_model_name.clone().unwrap().into();
    let runtime = MockRuntime::builder()
        .json(CHAT, StatusCode::OK, response)
        .start()
        .await;
    for _ in 0..2 {
        let result = client()
            .complete(
                &runtime.renamed_deployment(),
                request.clone(),
                16,
                deadline(5),
            )
            .await
            .unwrap();
        assert_eq!(result.into_response()["model"], request.model);
    }
    let requests = runtime.requests();
    assert_eq!(requests.len(), 2);
    for sent in requests {
        assert_eq!(sent.path, CHAT);
        assert_eq!(
            sent.body["model"],
            request.runtime_model_name.as_ref().unwrap().as_str()
        );
    }
}

#[tokio::test]
async fn host_resolution_failure_has_zero_usage() {
    let runtime = MockRuntime::builder()
        .json(
            CHAT,
            StatusCode::INTERNAL_SERVER_ERROR,
            json!({"error": "resolution_failed"}),
        )
        .start()
        .await;
    let error = client()
        .complete(
            &runtime.deployment(),
            private_model_request(false),
            16,
            deadline(5),
        )
        .await
        .unwrap_err();
    assert_eq!(error.kind(), RuntimeFailureKind::Unavailable);
    assert_eq!(error.usage(), crate::NormalizedUsage::zero());
    assert_eq!(runtime.requests().len(), 1);
    assert_eq!(runtime.requests()[0].path, CHAT);
}

#[tokio::test]
async fn sends_one_normal_streaming_request_for_a_private_model() {
    let request = private_model_request(true);
    let mut event = chunk(json!({"content": "hello"}), Some("stop"));
    event["model"] = request.runtime_model_name.clone().unwrap().into();
    event["usage"] = json!({"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11});
    let runtime = MockRuntime::builder()
        .sse(CHAT, &[data(&event), DONE.to_owned()])
        .start()
        .await;
    let mut stream = client()
        .stream(&runtime.deployment(), request.clone(), 16, deadline(5))
        .await
        .unwrap();
    match stream.next_event().await.unwrap().unwrap() {
        RuntimeStreamEvent::Chunk(chunk) => {
            assert_eq!(chunk.into_response()["model"], request.model)
        }
        _ => panic!("expected chunk"),
    }
    assert_eq!(runtime.requests().len(), 1);
    assert_eq!(runtime.requests()[0].path, CHAT);
    assert_eq!(
        runtime.requests()[0].body["model"],
        request.runtime_model_name.as_ref().unwrap().as_str()
    );
}
