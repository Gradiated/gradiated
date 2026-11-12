use std::time::Duration;

use axum::{
    body::Body,
    http::{header, StatusCode},
    response::Response,
    routing::post,
};
use futures_util::stream;
use serde_json::{json, Value};
use uuid::Uuid;

use super::support::{data, deadline, expect_chunk, MockRuntime, DONE};
use crate::{
    config::OpenRouterConfig,
    runtime::{
        ExternalCapacity, ExternalModel, ExternalRequest, OpenRouterClient, PriceCap,
        RuntimeEventStream, RuntimeStreamEvent,
    },
    InferenceRequest, NormalizedUsage, RuntimeFailureKind,
};

const PATH: &str = "/api/v1/chat/completions";
const UPSTREAM_MODEL: &str = "z-ai/glm-5.3-flash";
const PUBLIC_MODEL: &str = "z-ai/glm-5.3-flash";
const GENERATION_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000abc);
const WORKSPACE_ID: Uuid = Uuid::from_u128(0x0198c36f9b6a70008000000000000def);

async fn client(mock: &MockRuntime) -> OpenRouterClient {
    OpenRouterClient::connect(&OpenRouterConfig {
        api_key: Some("platform-key".to_owned()),
        base_url: format!("{}/api/v1", mock.url()),
    })
    .await
    .unwrap()
}

/// The credential loader reading a stand-in for Secrets Manager at `endpoint`.
fn loader(endpoint: String) -> gradiated_credentials::CredentialLoader {
    let config = aws_sdk_secretsmanager::Config::builder()
        .behavior_version_latest()
        .region(aws_sdk_secretsmanager::config::Region::new("us-east-1"))
        .credentials_provider(aws_credential_types::Credentials::new(
            "test", "test", None, None, "test",
        ))
        .retry_config(
            aws_sdk_secretsmanager::config::retry::RetryConfig::standard().with_max_attempts(1),
        )
        .endpoint_url(endpoint)
        .build();

    gradiated_credentials::CredentialLoader::new(aws_sdk_secretsmanager::Client::from_conf(config))
}

fn request(body: Value) -> ExternalRequest {
    let mut request = InferenceRequest::parse(&serde_json::to_vec(&body).unwrap()).unwrap();
    request.model = PUBLIC_MODEL.to_owned();
    request.session_id = Some("session-key".to_owned());

    ExternalRequest {
        generation_id: GENERATION_ID,
        workspace_id: WORKSPACE_ID,
        model: ExternalModel::openrouter(UPSTREAM_MODEL),
        request,
        output_tokens: 64,
        deadline: deadline(10),
        price_cap: PriceCap {
            prompt: 150,
            completion: 1_200,
        },
    }
}

fn chat() -> ExternalRequest {
    request(json!({
        "model": PUBLIC_MODEL,
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.5,
        "max_tokens": 64
    }))
}

fn streaming_chat() -> ExternalRequest {
    request(json!({
        "model": PUBLIC_MODEL,
        "messages": [{"role": "user", "content": "hello"}],
        "stream": true
    }))
}

/// A buffered response as OpenRouter returns it, measured on 2026-11-05.
fn completion() -> Value {
    json!({
        "id": "gen-1793892348-SPKKvoS2qRcEu5bzmqv4",
        "object": "chat.completion",
        "created": 1_793_892_348,
        "model": UPSTREAM_MODEL,
        "provider": "Modal",
        "system_fingerprint": null,
        "service_tier": null,
        "choices": [{
            "index": 0,
            "logprobs": null,
            "finish_reason": "stop",
            "native_finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "ok",
                "refusal": null,
                "reasoning": "short thought",
                "reasoning_details": [{"type": "reasoning.text", "text": "short thought", "format": "unknown", "index": 0}]
            }
        }],
        "usage": {
            "prompt_tokens": 19,
            "completion_tokens": 35,
            "total_tokens": 54,
            "cost": 2.035e-05,
            "is_byok": false,
            "prompt_tokens_details": {"cached_tokens": 4, "cache_write_tokens": 0, "audio_tokens": 0, "video_tokens": 0},
            "cost_details": {"upstream_inference_cost": 2.035e-05},
            "completion_tokens_details": {"reasoning_tokens": 33, "image_tokens": 0, "audio_tokens": 0}
        }
    })
}

fn frame(delta: Value, finish_reason: Option<&str>) -> Value {
    json!({
        "id": "gen-1793892348-jSUOmqsHXLHSKviqsWgn",
        "object": "chat.completion.chunk",
        "created": 1_793_892_348,
        "model": UPSTREAM_MODEL,
        "provider": "Modal",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason, "native_finish_reason": finish_reason}]
    })
}

/// OpenRouter's final frame repeats the finish reason beside its only usage report.
fn accounting_frame(finish_reason: &str, completion_tokens: u64, reasoning_tokens: u64) -> Value {
    let mut frame = frame(
        json!({"content": "", "role": "assistant"}),
        Some(finish_reason),
    );
    frame["service_tier"] = Value::Null;
    frame["usage"] = json!({
        "prompt_tokens": 19,
        "completion_tokens": completion_tokens,
        "total_tokens": 19 + completion_tokens,
        "cost": 0.00003485,
        "is_byok": false,
        "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
        "cost_details": {"upstream_inference_cost": 0.00003485},
        "completion_tokens_details": {"reasoning_tokens": reasoning_tokens}
    });
    frame
}

fn measured_stream() -> Vec<String> {
    vec![
        ": OPENROUTER PROCESSING\n\n".to_owned(),
        data(&frame(
            json!({"content": "", "role": "assistant", "reasoning": "The", "reasoning_details": [{"type": "reasoning.text", "text": "The"}]}),
            None,
        )),
        data(&frame(
            json!({"content": "ok", "role": "assistant", "reasoning": null}),
            None,
        )),
        data(&frame(
            json!({"content": "", "role": "assistant", "reasoning": null}),
            Some("length"),
        )),
        data(&accounting_frame("length", 64, 69)),
        DONE.to_owned(),
    ]
}

async fn mock_json(status: StatusCode, body: Value) -> MockRuntime {
    MockRuntime::builder()
        .json(PATH, status, body)
        .start()
        .await
}

async fn collect(mut events: Box<dyn RuntimeEventStream>) -> Vec<RuntimeStreamEvent> {
    let mut collected = Vec::new();
    while let Some(event) = events.next_event().await.unwrap() {
        collected.push(event);
    }

    collected
}

#[tokio::test]
async fn sends_the_mapped_model_with_privacy_routing_and_only_the_platform_key() {
    let mock = mock_json(StatusCode::OK, completion()).await;

    client(&mock).await.complete(chat()).await.unwrap();

    let recorded = mock.requests();
    assert_eq!(recorded.len(), 1);
    assert_eq!(recorded[0].path, PATH);
    assert_eq!(
        recorded[0].headers[header::AUTHORIZATION],
        "Bearer platform-key"
    );
    let body = &recorded[0].body;
    assert_eq!(body["model"], UPSTREAM_MODEL);
    assert_eq!(body["messages"][0]["content"], "hello");
    assert_eq!(body["stream"], false);
    assert_eq!(body["max_tokens"], 64);
    assert_eq!(body["temperature"], 0.5);
    assert_eq!(
        body["provider"],
        json!({
            "data_collection": "deny",
            "require_parameters": true,
            "zdr": true,
            "max_price": {"prompt": 0.15, "completion": 1.2}
        })
    );
    assert_eq!(
        body["plugins"],
        json!([{"id": "context-compression", "enabled": false}])
    );
    let user = body["user"].as_str().unwrap();
    let session = body["session_id"].as_str().unwrap();
    assert_eq!((user.len(), session.len()), (64, 64));
    assert!(!user.contains(&WORKSPACE_ID.to_string()));
    assert_ne!(session, "session-key");
    for runtime_field in ["priority", "stream_options", "service_tier"] {
        assert!(body.get(runtime_field).is_none(), "{runtime_field}");
    }
}

#[tokio::test]
async fn deepseek_fallback_covers_standard_provider_prices_for_buffered_and_streaming_requests() {
    for streaming in [false, true] {
        let mock = mock_json(StatusCode::OK, json!({})).await;
        let mut deepseek = if streaming { streaming_chat() } else { chat() };
        deepseek.model = ExternalModel::openrouter("deepseek/deepseek-v4.1-flash-1017");
        deepseek.price_cap = PriceCap {
            prompt: 6,
            completion: 200,
        };

        let client = client(&mock).await;
        if streaming {
            let _ = client.stream(deepseek).await;
        } else {
            let _ = client.complete(deepseek).await;
        }

        let recorded = mock.requests();
        assert_eq!(recorded.len(), 1);
        assert_eq!(
            recorded[0].body["provider"],
            json!({
                "data_collection": "deny",
                "require_parameters": true,
                "zdr": true,
                "max_price": {"prompt": 0.30, "completion": 1.20}
            })
        );
    }
}

#[tokio::test]
async fn kimi_may_pay_openrouter_up_to_a_fifth_more_than_we_charge() {
    let mock = mock_json(StatusCode::OK, json!({})).await;
    let mut kimi = chat();
    kimi.model = ExternalModel::openrouter("moonshotai/kimi-k3.1-pro");
    kimi.price_cap = PriceCap {
        prompt: 1_800,
        completion: 9_000,
    };

    let _ = client(&mock).await.complete(kimi).await;

    let recorded = mock.requests();
    let price = &recorded[0].body["provider"]["max_price"];
    assert!((price["prompt"].as_f64().unwrap() - 2.16).abs() < 1e-9);
    assert!((price["completion"].as_f64().unwrap() - 10.8).abs() < 1e-9);
}

#[tokio::test]
async fn a_buffered_response_carries_only_public_fields_and_our_identity() {
    let mock = mock_json(StatusCode::OK, completion()).await;

    let completion = client(&mock).await.complete(chat()).await.unwrap();

    let response = completion.response();
    assert_eq!(
        response,
        &json!({
            "id": format!("chatcmpl-{}", GENERATION_ID.simple()),
            "object": "chat.completion",
            "created": 1_793_892_348,
            "model": PUBLIC_MODEL,
            "choices": [{
                "index": 0,
                "logprobs": null,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "ok",
                    "refusal": null,
                    "reasoning_content": "short thought"
                }
            }],
            "usage": {
                "prompt_tokens": 19,
                "completion_tokens": 35,
                "total_tokens": 54,
                "prompt_tokens_details": {"cached_tokens": 4},
                "completion_tokens_details": {"reasoning_tokens": 33}
            }
        })
    );
    assert_eq!(completion.finish_reason(), "stop");
    assert_eq!(
        completion.usage(),
        NormalizedUsage::new(19, 4, 0, 35, 33).unwrap()
    );
    assert_eq!(completion.upstream_cost_nano_usd(), Some(20_350));
}

#[tokio::test]
async fn reasoning_reported_beyond_completion_tokens_is_capped_at_the_billed_total() {
    let mut body = completion();
    body["usage"]["completion_tokens_details"]["reasoning_tokens"] = json!(69);
    let mock = mock_json(StatusCode::OK, body).await;

    let completion = client(&mock).await.complete(chat()).await.unwrap();

    assert_eq!(completion.usage().output_tokens(), 35);
    assert_eq!(completion.usage().reasoning_tokens(), 35);
}

#[tokio::test]
async fn a_body_padded_with_whitespace_parses() {
    let body = completion().to_string();
    let mock = MockRuntime::builder()
        .route(
            PATH,
            post(move || async move {
                let padding = stream::iter(["\n\n".to_owned(), "         \n".to_owned()]);
                let rest = stream::once(async move {
                    tokio::time::sleep(Duration::from_millis(50)).await;
                    body
                });
                let chunks = futures_util::StreamExt::map(
                    futures_util::StreamExt::chain(padding, rest),
                    Ok::<_, std::io::Error>,
                );
                Response::builder()
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from_stream(chunks))
                    .unwrap()
            }),
        )
        .start()
        .await;

    let completion = client(&mock).await.complete(chat()).await.unwrap();

    assert_eq!(completion.finish_reason(), "stop");
}

#[tokio::test]
async fn upstream_statuses_map_to_our_failures_without_their_bodies() {
    for (status, kind) in [
        (400, RuntimeFailureKind::InvalidRequest),
        (422, RuntimeFailureKind::InvalidRequest),
        (401, RuntimeFailureKind::Unavailable),
        (402, RuntimeFailureKind::Unavailable),
        (403, RuntimeFailureKind::Unavailable),
        (404, RuntimeFailureKind::Unavailable),
        (408, RuntimeFailureKind::Unavailable),
        (429, RuntimeFailureKind::CapacityExceeded),
        (502, RuntimeFailureKind::Unavailable),
        (503, RuntimeFailureKind::CapacityExceeded),
        (529, RuntimeFailureKind::CapacityExceeded),
    ] {
        let body = json!({"error": {"code": status, "message": "PRIVATE_UPSTREAM_DETAIL", "metadata": {"provider_name": "Modal"}}});
        let mock = mock_json(StatusCode::from_u16(status).unwrap(), body).await;

        let failure = client(&mock).await.complete(chat()).await.unwrap_err();

        assert_eq!(failure.kind(), kind, "{status}");
        assert_eq!(failure.usage(), NormalizedUsage::zero());
        assert!(!format!("{failure:?}").contains("PRIVATE_UPSTREAM_DETAIL"));
    }
}

#[tokio::test]
async fn a_mapped_model_openrouter_does_not_list_is_our_failure_not_the_callers() {
    for stream in [false, true] {
        let message = format!("{UPSTREAM_MODEL} is not a valid model ID");
        let body = json!({"error": {"code": 400, "message": message}});
        let mock = mock_json(StatusCode::BAD_REQUEST, body).await;
        let client = client(&mock).await;

        let failure = if stream {
            client.stream(chat()).await.err().unwrap()
        } else {
            client.complete(chat()).await.unwrap_err()
        };

        assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable, "{stream}");
        assert_eq!(failure.usage(), NormalizedUsage::zero());
    }
}

#[tokio::test]
async fn an_error_after_committed_headers_is_a_failure() {
    let reported = json!({"error": {"code": 502, "message": "provider failed", "metadata": {"error_type": "provider_unavailable"}}});
    let mock = mock_json(StatusCode::OK, reported).await;
    let failure = client(&mock).await.complete(chat()).await.unwrap_err();
    assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);

    let mut errored = completion();
    errored["choices"][0]["finish_reason"] = json!("error");
    let mock = mock_json(StatusCode::OK, errored).await;
    let failure = client(&mock).await.complete(chat()).await.unwrap_err();
    assert_eq!(failure.kind(), RuntimeFailureKind::Interrupted);
    assert_eq!(failure.usage().output_tokens(), 35);
}

#[tokio::test]
async fn a_response_for_another_model_or_without_usage_is_rejected() {
    let mut other = completion();
    other["model"] = json!("z-ai/glm-5.3-flashx");
    let mut unmetered = completion();
    unmetered.as_object_mut().unwrap().remove("usage");
    let mut inconsistent = completion();
    inconsistent["usage"]["total_tokens"] = json!(1);

    for (name, body) in [
        ("other model", other),
        ("no usage", unmetered),
        ("inconsistent usage", inconsistent),
    ] {
        let mock = mock_json(StatusCode::OK, body).await;

        let failure = client(&mock).await.complete(chat()).await.unwrap_err();

        assert_eq!(
            failure.kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{name}"
        );
    }
}

#[tokio::test]
async fn an_expired_deadline_sends_nothing() {
    let mock = mock_json(StatusCode::OK, completion()).await;
    let mut request = chat();
    request.deadline = deadline(-1);

    let failure = client(&mock).await.complete(request).await.unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
    assert!(mock.requests().is_empty());
}

#[tokio::test]
async fn a_stream_is_normalized_to_one_finish_and_a_choiceless_usage_chunk() {
    let mock = MockRuntime::builder()
        .sse(PATH, &measured_stream())
        .start()
        .await;

    let events = collect(client(&mock).await.stream(streaming_chat()).await.unwrap()).await;

    assert_eq!(events.len(), 5, "{events:?}");
    assert_eq!(events[4], RuntimeStreamEvent::Done);
    let chunks: Vec<_> = events[..4]
        .iter()
        .cloned()
        .map(|event| expect_chunk(Some(event)))
        .collect();
    let identity = json!({
        "id": format!("chatcmpl-{}", GENERATION_ID.simple()),
        "object": "chat.completion.chunk",
        "created": 1_793_892_348,
        "model": PUBLIC_MODEL,
    });
    for chunk in &chunks {
        let response = chunk.clone().into_response();
        for field in ["id", "object", "created", "model"] {
            assert_eq!(response[field], identity[field], "{field}");
        }
        for hidden in ["provider", "service_tier", "system_fingerprint"] {
            assert!(response.get(hidden).is_none(), "{hidden}");
        }
    }

    let first = chunks[0].clone().into_response();
    assert_eq!(
        first["choices"][0]["delta"],
        json!({"role": "assistant", "content": "", "reasoning_content": "The"})
    );
    assert!(chunks[0].has_usable_output());
    assert_eq!(
        chunks[1].clone().into_response()["choices"][0]["delta"],
        json!({"content": "ok"})
    );
    assert_eq!(chunks[2].finish_reason(), Some("length"));
    assert!(!chunks[2].has_usable_output());

    let usage = &chunks[3];
    assert!(usage.is_terminal_usage());
    assert_eq!(
        usage.usage(),
        Some(NormalizedUsage::new(19, 0, 0, 64, 64).unwrap())
    );
    assert_eq!(usage.upstream_cost_nano_usd(), Some(34_850));
    let response = usage.clone().into_response();
    assert_eq!(response["choices"], json!([]));
    assert_eq!(response["usage"]["completion_tokens"], 64);
    assert!(response["usage"].get("cost").is_none());
    assert!(chunks[..3].iter().all(|chunk| chunk.usage().is_none()));
}

#[tokio::test]
async fn a_finish_reason_reported_only_in_the_usage_frame_is_kept() {
    let mock = MockRuntime::builder()
        .sse(
            PATH,
            &[
                data(&frame(json!({"content": "ok", "role": "assistant"}), None)),
                data(&accounting_frame("stop", 2, 0)),
                DONE.to_owned(),
            ],
        )
        .start()
        .await;

    let events = collect(client(&mock).await.stream(streaming_chat()).await.unwrap()).await;

    assert_eq!(events.len(), 4, "{events:?}");
    let finish = expect_chunk(Some(events[1].clone()));
    assert_eq!(finish.finish_reason(), Some("stop"));
    assert!(finish.usage().is_none());
    assert!(expect_chunk(Some(events[2].clone())).is_terminal_usage());
}

#[tokio::test]
async fn an_error_in_the_first_event_fails_the_open() {
    let mut error = frame(json!({"content": ""}), Some("error"));
    error["error"] = json!({"code": 429, "message": "rate limited", "metadata": {"error_type": "rate_limit_exceeded"}});
    let mock = MockRuntime::builder()
        .sse(PATH, &[data(&error)])
        .start()
        .await;

    let failure = client(&mock)
        .await
        .stream(streaming_chat())
        .await
        .err()
        .expect("the stream reports its upstream error");

    assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
}

#[tokio::test]
async fn an_error_after_output_ends_the_stream_as_a_failure() {
    let mut error = frame(json!({"content": ""}), Some("error"));
    error["error"] = json!({"code": 502, "message": "provider disconnected"});
    let mock = MockRuntime::builder()
        .sse(
            PATH,
            &[
                data(&frame(
                    json!({"content": "partial", "role": "assistant"}),
                    None,
                )),
                data(&error),
            ],
        )
        .start()
        .await;
    let mut events = client(&mock).await.stream(streaming_chat()).await.unwrap();

    let partial = expect_chunk(events.next_event().await.unwrap());
    let failure = events.next_event().await.unwrap_err();

    assert!(partial.has_usable_output());
    assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
}

#[tokio::test]
async fn a_stream_without_usage_or_from_two_generations_is_rejected() {
    let mut spliced = frame(json!({"content": "b"}), None);
    spliced["id"] = json!("gen-other");

    for (name, frames) in [
        (
            "done before usage",
            vec![
                data(&frame(
                    json!({"content": "a", "role": "assistant"}),
                    Some("stop"),
                )),
                DONE.to_owned(),
            ],
        ),
        (
            "two generations",
            vec![
                data(&frame(json!({"content": "a", "role": "assistant"}), None)),
                data(&spliced),
            ],
        ),
        (
            "cut before done",
            vec![
                data(&frame(
                    json!({"content": "a", "role": "assistant"}),
                    Some("stop"),
                )),
                data(&accounting_frame("stop", 1, 0)),
            ],
        ),
    ] {
        let mock = MockRuntime::builder().sse(PATH, &frames).start().await;
        let mut events = client(&mock).await.stream(streaming_chat()).await.unwrap();

        let mut failure = None;
        while failure.is_none() {
            match events.next_event().await {
                Ok(Some(_)) => {}
                Ok(None) => panic!("{name}: the stream ended successfully"),
                Err(error) => failure = Some(error),
            }
        }

        assert_eq!(
            failure.unwrap().kind(),
            RuntimeFailureKind::ProtocolViolation,
            "{name}"
        );
    }
}

#[test]
fn each_mapping_has_a_stable_served_release_identity_of_its_own() {
    let glm = ExternalModel::openrouter(UPSTREAM_MODEL).served_release_digest();
    let deepseek =
        ExternalModel::openrouter("deepseek/deepseek-v4.1-flash-1017").served_release_digest();

    assert_eq!(
        glm,
        "sha256:".to_owned()
            + &format!(
                "{:x}",
                <sha2::Sha256 as sha2::Digest>::digest(
                    br#"{"capacity":"openrouter","model":"z-ai/glm-5.3-flash"}"#
                )
            )
    );
    assert_ne!(glm, deepseek);
    assert_eq!(glm.len(), 71);
}

#[tokio::test]
async fn a_rotating_key_sends_the_active_slot() {
    let secret = json!({
        "activeSlot": "secondary",
        "primaryApiKey": "primary-platform-key",
        "secondaryApiKey": "secondary-platform-key"
    });
    let secrets = MockRuntime::builder()
        .json(
            "/",
            StatusCode::OK,
            json!({"SecretString": secret.to_string()}),
        )
        .start()
        .await;
    let mock = mock_json(StatusCode::OK, completion()).await;
    let client =
        OpenRouterClient::with_loader(&format!("{}/api/v1", mock.url()), loader(secrets.url()))
            .unwrap();

    client.complete(chat()).await.unwrap();

    assert_eq!(
        mock.requests()[0].headers[header::AUTHORIZATION],
        "Bearer secondary-platform-key"
    );
    assert_eq!(
        secrets.requests()[0].body["SecretId"],
        "gradiated/prod/providers/openrouter"
    );
}

#[tokio::test]
async fn an_unreadable_credential_fails_the_attempt_without_a_request() {
    let secrets = MockRuntime::builder()
        .json(
            "/",
            StatusCode::BAD_REQUEST,
            json!({"__type": "AccessDeniedException", "Message": "PRIVATE_SECRET_DETAIL"}),
        )
        .start()
        .await;
    let mock = mock_json(StatusCode::OK, completion()).await;
    let client =
        OpenRouterClient::with_loader(&format!("{}/api/v1", mock.url()), loader(secrets.url()))
            .unwrap();

    let failure = client.complete(chat()).await.unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
    assert_eq!(failure.diagnostic_code(), "credential");
    assert!(!format!("{failure:?}").contains("PRIVATE_SECRET_DETAIL"));
    assert!(mock.requests().is_empty());
}
