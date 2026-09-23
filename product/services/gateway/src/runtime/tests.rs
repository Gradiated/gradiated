use std::path::PathBuf;
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc, Mutex,
};

use axum::{
    body::{Body, Bytes},
    extract::State,
    http::{header::LOCATION, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Router,
};
use serde_json::json;
use tokio::task::JoinHandle;
use uuid::Uuid;

use super::{
    chat::{normalize_completion, normalize_stream_chunk},
    client::one_shot_body,
    *,
};
use crate::ModelTokenizer;
use crate::{DeploymentStatus, ModelDeploymentRelease};
use reqwest::header;
use std::time::Duration;

#[test]
fn runtime_tls_paths_are_optional_as_one_group() {
    assert_eq!(
        RuntimeTlsConfig::from_paths(None, None, None).unwrap(),
        None
    );

    let config = RuntimeTlsConfig::from_paths(
        Some(PathBuf::from("ca.crt")),
        Some(PathBuf::from("client.crt")),
        Some(PathBuf::from("client.key")),
    )
    .unwrap()
    .unwrap();
    assert_eq!(config.ca_certificate_path, PathBuf::from("ca.crt"));
    assert_eq!(config.client_certificate_path, PathBuf::from("client.crt"));
    assert_eq!(config.client_key_path, PathBuf::from("client.key"));
}

#[test]
fn runtime_tls_rejects_partial_path_groups() {
    for paths in [
        (Some(PathBuf::from("ca.crt")), None, None),
        (
            Some(PathBuf::from("ca.crt")),
            Some(PathBuf::from("client.crt")),
            None,
        ),
        (None, None, Some(PathBuf::from("client.key"))),
    ] {
        assert!(matches!(
            RuntimeTlsConfig::from_paths(paths.0, paths.1, paths.2),
            Err(RuntimeClientError::IncompleteTlsConfiguration)
        ));
    }
}

#[derive(Clone)]
struct RecordedRequest {
    headers: HeaderMap,
    body: Value,
}

#[derive(Clone)]
struct TestServerState {
    recorded: Arc<Mutex<Vec<RecordedRequest>>>,
    status: StatusCode,
    response: Value,
}

async fn respond(
    State(state): State<TestServerState>,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    state.recorded.lock().unwrap().push(RecordedRequest {
        headers,
        body: serde_json::from_slice(&body).unwrap(),
    });
    (state.status, axum::Json(state.response))
}

async fn server(
    status: StatusCode,
    response: Value,
) -> (String, Arc<Mutex<Vec<RecordedRequest>>>, JoinHandle<()>) {
    let recorded = Arc::new(Mutex::new(Vec::new()));
    let state = TestServerState {
        recorded: recorded.clone(),
        status,
        response,
    };
    let application = Router::new()
        .route("/v1/chat/completions", post(respond))
        .route("/v1/systemone", post(respond))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move {
        axum::serve(listener, application).await.unwrap();
    });
    (format!("http://{address}"), recorded, task)
}

fn deployment(service_url: String) -> GatewayModelDeployment {
    GatewayModelDeployment {
        id: Uuid::now_v7(),
        status: DeploymentStatus::Available,
        provider: "local".to_owned(),
        region: "local".to_owned(),
        fault_domain: "local:runtime-1".to_owned(),
        service_url,
        release: ModelDeploymentRelease {
            schema_version: 1,
            runtime_revision: "runtime".to_owned(),
            protocol: None,
            model_path: "model-a".to_owned(),
            model_revision: "model-revision".to_owned(),
            runtime_model_name: None,
            tokenizer_path: "model-a".to_owned(),
            tokenizer_revision: "tokenizer-revision".to_owned(),
            tokenizer_mode: None,
        },
    }
}

fn request() -> InferenceRequest {
    InferenceRequest::parse(
        br#"{
            "model":"model-a",
            "messages":[{"role":"user","content":"hello"}],
            "temperature":0.25,
            "tools":[{"type":"function","function":{"name":"weather"}}]
        }"#,
    )
    .unwrap()
}

fn streaming_request() -> InferenceRequest {
    InferenceRequest::parse(
        br#"{
            "model":"model-a",
            "messages":[{"role":"user","content":"hello"}],
            "stream":true
        }"#,
    )
    .unwrap()
}

fn successful_response() -> Value {
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

#[tokio::test]
async fn decision_transport_preserves_schema_and_authoritative_usage() {
    let response = json!({"model":"runtime-model", "answers":{"q":{"type":"noul","noul":0.9}},
        "usage":{"input_tokens":100,"cached_input_tokens":80,"output_tokens":0}});
    let (url, recorded, task) = server(StatusCode::OK, response).await;
    let mut deployment = deployment(url);
    deployment.release.protocol = Some(crate::RuntimeProtocol::SystemOne);
    deployment.release.runtime_model_name = Some("runtime-model".to_owned());
    let request = InferenceRequest::parse_kind(
        br#"{"model":"model-a","state":{"ticket":"charged twice"},"questions":{"q":{"type":"noul","instructions":"Duplicate?"}}}"#,
        crate::RequestKind::SystemOne,
    ).unwrap();
    let completion = SglangClient::new(Some("runtime-secret".to_owned()))
        .unwrap()
        .complete(
            &deployment,
            request,
            0,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap();
    assert_eq!(
        completion.usage(),
        NormalizedUsage::new(100, 80, 0, 0, 0).unwrap()
    );
    assert_eq!(completion.into_response()["model"], "model-a");
    let requests = recorded.lock().unwrap();
    assert_eq!(requests[0].body["model"], "runtime-model");
    assert_eq!(requests[0].body["state"]["ticket"], "charged twice");
    assert_eq!(requests[0].body["priority"], 0);
    assert!(requests[0].body.get("messages").is_none());
    assert!(requests[0].body.get("max_completion_tokens").is_none());
    assert_eq!(
        requests[0].headers["authorization"],
        "Bearer runtime-secret"
    );
    task.abort();
}

#[tokio::test]
async fn sends_one_qualified_request_and_normalizes_the_response() {
    let mut upstream_response = successful_response();
    upstream_response["model"] = json!("runtime-model");
    let (service_url, recorded, task) = server(StatusCode::OK, upstream_response).await;
    let runtime = SglangClient::new(Some("runtime-secret".to_owned())).unwrap();
    let mut deployment = deployment(service_url);
    deployment.release.runtime_model_name = Some("runtime-model".to_owned());

    let mut request = request();
    request.service_tier = crate::ServiceTier::Fast;
    let completion = runtime
        .complete(
            &deployment,
            request,
            1_024,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap();

    let requests = recorded.lock().unwrap();
    assert_eq!(requests.len(), 1);
    assert_eq!(
        requests[0].headers[header::AUTHORIZATION],
        "Bearer runtime-secret"
    );
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
    task.abort();
}

#[tokio::test]
async fn parses_and_normalizes_sglang_streaming_events() {
    let recorded = Arc::new(Mutex::new(Vec::new()));
    let captured = recorded.clone();
    let application = Router::new().route(
        "/v1/chat/completions",
        post(move |headers: HeaderMap, body: Bytes| {
            let captured = captured.clone();
            async move {
                captured.lock().unwrap().push(RecordedRequest {
                    headers,
                    body: serde_json::from_slice(&body).unwrap(),
                });
                Response::builder()
                    .header("content-type", "text/event-stream")
                    .body(Body::from(concat!(
                        "data: {\"id\":\"chatcmpl-stream\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"runtime-model\",\"choices\":[{\"index\":0,\"delta\":{\"reasoning\":\"hello\"},\"finish_reason\":null}],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":1,\"total_tokens\":11}}\n\n",
                        "data: {\"id\":\"chatcmpl-stream\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"runtime-model\",\"choices\":[{\"index\":0,\"delta\":{},\"finish_reason\":\"stop\"}]}\n\n",
                        "data: {\"id\":\"chatcmpl-stream\",\"object\":\"chat.completion.chunk\",\"created\":1,\"model\":\"runtime-model\",\"choices\":[],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":1,\"total_tokens\":11}}\n\n",
                        "data: [DONE]\n\n"
                    )))
                    .unwrap()
            }
        }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move {
        axum::serve(listener, application).await.unwrap();
    });
    let runtime = SglangClient::new(None).unwrap();
    let mut deployment = deployment(format!("http://{address}"));
    deployment.release.runtime_model_name = Some("runtime-model".to_owned());
    let mut request = streaming_request();
    request.service_tier = crate::ServiceTier::Flex;
    let mut response = runtime
        .stream(
            &deployment,
            request,
            32,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap();

    let first = response.next_event().await.unwrap().unwrap();
    let RuntimeStreamEvent::Chunk(first) = first else {
        panic!("first event must be a chunk");
    };
    assert!(first.has_usable_output());
    assert_eq!(first.clone().into_response()["model"], "model-a");
    assert_eq!(first.usage().unwrap().output_tokens(), 1);
    assert!(first.clone().into_response().get("usage").is_none());

    let finish = response.next_event().await.unwrap().unwrap();
    let RuntimeStreamEvent::Chunk(finish) = finish else {
        panic!("second event must be a chunk");
    };
    assert_eq!(finish.finish_reason(), Some("stop"));

    let usage = response.next_event().await.unwrap().unwrap();
    let RuntimeStreamEvent::Chunk(usage) = usage else {
        panic!("third event must be a chunk");
    };
    assert!(usage.is_terminal_usage());
    assert_eq!(usage.into_response()["usage"]["total_tokens"], 11);
    assert_eq!(
        response.next_event().await.unwrap(),
        Some(RuntimeStreamEvent::Done)
    );

    let requests = recorded.lock().unwrap();
    assert_eq!(requests[0].body["model"], "runtime-model");
    assert_eq!(requests[0].body["stream"], true);
    assert_eq!(requests[0].body["priority"], 10);
    assert_eq!(requests[0].body["stream_options"]["include_usage"], true);
    assert_eq!(
        requests[0].body["stream_options"]["continuous_usage_stats"],
        true
    );
    task.abort();
}

#[tokio::test]
#[ignore = "downloads the pinned production Gemma tokenizer from Hugging Face"]
async fn parses_native_token_streams_with_authoritative_usage() {
    let recorded = Arc::new(Mutex::new(Vec::new()));
    let captured = recorded.clone();
    let application = Router::new().route(
        "/v1/token-completions",
        post(move |headers: HeaderMap, body: Bytes| {
            let captured = captured.clone();
            async move {
                captured.lock().unwrap().push(RecordedRequest {
                    headers,
                    body: serde_json::from_slice(&body).unwrap(),
                });
                Response::builder()
                    .header("content-type", "text/event-stream")
                    .body(Body::from(concat!(
                        "data: {\"token_id\":2021,\"usage\":{\"input_tokens\":3,\"cached_input_tokens\":2,\"output_tokens\":1}}\n\n",
                        "data: {\"token_id\":1586,\"usage\":{\"input_tokens\":3,\"cached_input_tokens\":2,\"output_tokens\":2}}\n\n",
                        "data: {\"finish_reason\":\"length\",\"usage\":{\"input_tokens\":3,\"cached_input_tokens\":2,\"output_tokens\":2}}\n\n",
                        "data: [DONE]\n\n"
                    )))
                    .unwrap()
            }
        }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move {
        axum::serve(listener, application).await.unwrap();
    });
    let tokenizer = ModelTokenizer::new().unwrap();
    let runtime = SglangClient::with_tokenizer(None, tokenizer).unwrap();
    let mut deployment = deployment(format!("http://{address}"));
    deployment.release.runtime_revision = "native-gemma4-h200-v2".to_owned();
    deployment.release.model_path = "google/gemma-4-31B-it".to_owned();
    deployment.release.model_revision = "b9ea41a2887d8607f594846523f94c6cc75ac8a4".to_owned();
    deployment.release.tokenizer_path = "google/gemma-4-31B-it".to_owned();
    deployment.release.tokenizer_revision = "b9ea41a2887d8607f594846523f94c6cc75ac8a4".to_owned();
    let mut request = streaming_request();
    request.encoded_input_ids = Some(vec![2, 3, 4]);
    let mut response = runtime
        .stream(
            &deployment,
            request,
            8,
            Utc::now() + chrono::TimeDelta::seconds(30),
        )
        .await
        .unwrap();

    let mut usable_chunks = 0;
    let mut finish = None;
    let mut terminal_usage = None;
    while let RuntimeStreamEvent::Chunk(chunk) = response.next_event().await.unwrap().unwrap() {
        if chunk.has_usable_output() {
            usable_chunks += 1;
            assert!(chunk.usage().is_some());
        }
        if let Some(reason) = chunk.finish_reason() {
            finish = Some(reason.to_owned());
        }
        if chunk.is_terminal_usage() {
            terminal_usage = chunk.usage();
        }
    }
    assert!(usable_chunks > 0);
    assert_eq!(finish.as_deref(), Some("length"));
    assert_eq!(terminal_usage.unwrap().input_tokens(), 3);
    assert_eq!(terminal_usage.unwrap().cached_input_tokens(), 2);
    assert_eq!(terminal_usage.unwrap().output_tokens(), 2);
    let requests = recorded.lock().unwrap();
    assert_eq!(requests[0].body["input_ids"], json!([2, 3, 4]));
    assert_eq!(requests[0].body["stream"], true);
    assert_eq!(requests[0].body["priority"], 0);
    task.abort();
}

#[tokio::test]
async fn transport_diagnostic_drops_private_url_and_correlates_attempt() {
    let error = reqwest::Client::new()
        .get("http://private-runtime.invalid/secret-path")
        .timeout(Duration::ZERO)
        .send()
        .await
        .unwrap_err();
    let failure = RuntimeFailure::from_transport(error);
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    let generation_id = Uuid::from_u128(123);
    failure.log_attempt(
        generation_id,
        "hosted-model",
        Uuid::from_u128(456),
        1,
        20,
        true,
    );
    let events = logs.events();
    assert_eq!(events.len(), 1);
    assert_eq!(
        events[0]["fields"]["generation_id"],
        generation_id.to_string()
    );
    assert_eq!(events[0]["fields"]["retry_selected"], true);
    assert!(events[0]["fields"]["transport"].is_string());
    assert!(!serde_json::to_string(&events)
        .unwrap()
        .contains("private-runtime"));
    assert!(!format!("{failure:?}").contains("secret-path"));
}

#[tokio::test]
async fn maps_overload_without_retrying_and_retains_valid_error_usage() {
    let response = json!({
        "error": {"message": "queue full"},
        "usage": {
            "prompt_tokens": 2,
            "completion_tokens": 1,
            "total_tokens": 3,
            "reasoning_tokens": 0
        }
    });
    let (service_url, recorded, task) = server(StatusCode::TOO_MANY_REQUESTS, response).await;
    let runtime = SglangClient::new(None).unwrap();

    let failure = runtime
        .complete(
            &deployment(service_url),
            request(),
            1_024,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap_err();

    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    failure.log_attempt(
        Uuid::from_u128(123),
        "hosted-model",
        Uuid::from_u128(456),
        1,
        20,
        false,
    );
    let events = logs.events();
    assert_eq!(events[0]["fields"]["upstream_status"], 429);
    assert!(!serde_json::to_string(&events)
        .unwrap()
        .contains("queue full"));
    assert_eq!(failure.upstream_status, Some(429));
    assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
    assert_eq!(failure.gateway_error(), GatewayError::CapacityExceeded);
    assert_eq!(failure.usage().input_tokens(), 2);
    assert_eq!(recorded.lock().unwrap().len(), 1);
    task.abort();
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
    ] {
        let mut response = successful_response();
        response["usage"] = usage.clone();
        assert_eq!(
            normalize_completion(
                &serde_json::to_vec(&response).unwrap(),
                "model-a",
                "model-a"
            )
            .unwrap_err()
            .kind(),
            RuntimeFailureKind::ProtocolViolation
        );
        let terminal = json!({"id":"chatcmpl-1","object":"chat.completion.chunk",
            "created":1,"model":"model-a","choices":[],"usage":usage});
        assert_eq!(
            normalize_stream_chunk(
                &serde_json::to_vec(&terminal).unwrap(),
                "model-a",
                "model-a",
                &mut None,
                &mut None
            )
            .unwrap_err()
            .kind(),
            RuntimeFailureKind::ProtocolViolation
        );
    }
    let mut missing = successful_response();
    missing.as_object_mut().unwrap().remove("usage");
    assert_eq!(
        normalize_completion(&serde_json::to_vec(&missing).unwrap(), "model-a", "model-a")
            .unwrap_err()
            .kind(),
        RuntimeFailureKind::ProtocolViolation
    );
}

#[tokio::test]
async fn maps_engine_queue_rejection_to_capacity() {
    // vLLM rejects with 503 when max_num_queued_reqs or max_num_queued_tokens
    // is reached. That is admission backpressure and must stay retryable.
    let response = json!({
        "error": {
            "message": "The engine is currently busy and cannot accept new requests."
        }
    });
    let (service_url, _, task) = server(StatusCode::SERVICE_UNAVAILABLE, response).await;
    let runtime = SglangClient::new(None).unwrap();

    let failure = runtime
        .complete(
            &deployment(service_url),
            request(),
            1_024,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap_err();

    assert_eq!(failure.upstream_status, Some(503));
    assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
    assert_eq!(failure.gateway_error(), GatewayError::CapacityExceeded);
    task.abort();
}

#[test]
fn classifies_admission_statuses_and_real_outages() {
    assert_eq!(
        failure_kind_for_status(StatusCode::SERVICE_UNAVAILABLE),
        RuntimeFailureKind::CapacityExceeded
    );
    assert_eq!(
        failure_kind_for_status(StatusCode::TOO_MANY_REQUESTS),
        RuntimeFailureKind::CapacityExceeded
    );
    assert_eq!(
        failure_kind_for_status(StatusCode::BAD_GATEWAY),
        RuntimeFailureKind::Unavailable
    );
    assert_eq!(
        failure_kind_for_status(StatusCode::BAD_REQUEST),
        RuntimeFailureKind::InvalidRequest
    );
}

#[tokio::test]
async fn rejects_inconsistent_authoritative_usage() {
    let mut response = successful_response();
    response["usage"]["total_tokens"] = json!(16);
    let (service_url, _, task) = server(StatusCode::OK, response).await;
    let runtime = SglangClient::new(None).unwrap();

    let failure = runtime
        .complete(
            &deployment(service_url),
            request(),
            1_024,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::ProtocolViolation);
    task.abort();
}

#[tokio::test]
async fn native_requests_are_length_delimited_for_the_cpp_runtime() {
    let recorded = Arc::new(Mutex::new(Vec::new()));
    let captured = recorded.clone();
    let application = Router::new().route(
        "/v1/token-completions",
        post(move |headers: HeaderMap, body: Bytes| {
            let captured = captured.clone();
            async move {
                captured.lock().unwrap().push(RecordedRequest {
                    headers,
                    body: serde_json::from_slice(&body).unwrap(),
                });
                (
                    StatusCode::BAD_REQUEST,
                    axum::Json(json!({"error": "invalid_request"})),
                )
            }
        }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move {
        axum::serve(listener, application).await.unwrap();
    });
    let runtime = SglangClient::with_tokenizer(None, ModelTokenizer::new().unwrap()).unwrap();
    let mut deployment = deployment(format!("http://{address}"));
    deployment.release.runtime_revision = "native-gemma4-h200-v2".to_owned();

    let mut non_streaming =
        InferenceRequest::parse(br#"{"model":"model-a","messages":[{}],"temperature":0}"#).unwrap();
    non_streaming.encoded_input_ids = Some(vec![2, 3, 4]);
    let failure = runtime
        .complete(
            &deployment,
            non_streaming,
            8,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap_err();
    assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);

    let mut streaming = streaming_request();
    streaming.encoded_input_ids = Some(vec![2, 3, 4]);
    let failure = runtime
        .stream(
            &deployment,
            streaming,
            8,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .err()
        .expect("native request should preserve the upstream rejection");
    assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);

    let requests = recorded.lock().unwrap();
    assert_eq!(requests.len(), 2);
    for request in requests.iter() {
        assert!(request.headers.contains_key(header::CONTENT_LENGTH));
        assert!(!request.headers.contains_key(header::TRANSFER_ENCODING));
        assert_eq!(request.body["input_ids"], json!([2, 3, 4]));
    }
    task.abort();
}

#[tokio::test]
async fn native_runtime_rejects_unimplemented_stochastic_sampling() {
    let runtime = SglangClient::new(None).unwrap();
    let mut deployment = deployment("http://127.0.0.1:1".to_owned());
    deployment.release.runtime_revision = "native-gemma4-h200-v2".to_owned();
    let failure = runtime
        .complete(
            &deployment,
            request(),
            32,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap_err();
    assert_eq!(failure.kind(), RuntimeFailureKind::InvalidRequest);
}

#[tokio::test]
async fn refuses_non_streaming_execution_after_the_deadline() {
    let runtime = SglangClient::new(None).unwrap();

    let failure = runtime
        .complete(
            &deployment("http://127.0.0.1:1".to_owned()),
            request(),
            1_024,
            Utc::now() - chrono::TimeDelta::seconds(1),
        )
        .await
        .unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::TimedOut);
}

#[test]
fn request_body_is_not_replayable() {
    assert!(one_shot_body(b"private prompt".to_vec())
        .as_bytes()
        .is_none());
}

#[tokio::test]
async fn does_not_follow_a_runtime_redirect() {
    let initial_requests = Arc::new(AtomicUsize::new(0));
    let redirected_requests = Arc::new(AtomicUsize::new(0));
    let initial_counter = initial_requests.clone();
    let redirected_counter = redirected_requests.clone();
    let application = Router::new()
        .route(
            "/v1/chat/completions",
            post(move || {
                let counter = initial_counter.clone();
                async move {
                    counter.fetch_add(1, Ordering::SeqCst);
                    (StatusCode::TEMPORARY_REDIRECT, [(LOCATION, "/redirected")])
                }
            }),
        )
        .route(
            "/redirected",
            post(move || {
                let counter = redirected_counter.clone();
                async move {
                    counter.fetch_add(1, Ordering::SeqCst);
                    axum::Json(successful_response())
                }
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move {
        axum::serve(listener, application).await.unwrap();
    });
    let runtime = SglangClient::new(None).unwrap();

    let failure = runtime
        .complete(
            &deployment(format!("http://{address}")),
            request(),
            1_024,
            Utc::now() + chrono::TimeDelta::seconds(5),
        )
        .await
        .unwrap_err();

    assert_eq!(failure.kind(), RuntimeFailureKind::Unavailable);
    assert_eq!(initial_requests.load(Ordering::SeqCst), 1);
    assert_eq!(redirected_requests.load(Ordering::SeqCst), 0);
    task.abort();
}
