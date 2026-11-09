use std::{sync::Arc, time::Instant};

use axum::{
    http::{StatusCode, Uri},
    response::IntoResponse,
};
use chrono::{TimeDelta, Utc};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::{
    completion::dispatch::RuntimeCall, routing::fixtures::deployment, GatewayError,
    InferenceRequest, ModelDeploymentRelease, ModelTokenizer, NormalizedUsage, RuntimeFailureKind,
    SglangClient,
};

fn live_call() -> RuntimeCall {
    let primary_url = std::env::var("GRADIATED_QUEUE_TEST_PRIMARY_URL").unwrap();
    let fallback_url = std::env::var("GRADIATED_QUEUE_TEST_FALLBACK_URL").unwrap();
    assert_ne!(primary_url, fallback_url);

    for url in [&primary_url, &fallback_url] {
        let uri: Uri = url.parse().unwrap();
        assert_eq!(uri.scheme_str(), Some("http"));
        assert_eq!(uri.host(), Some("127.0.0.1"));
        assert!(uri.path().starts_with("/alloc/"));
    }

    let profile: Value = serde_json::from_slice(
        &std::fs::read(std::env::var("GRADIATED_QUEUE_TEST_PROFILE_FILE").unwrap()).unwrap(),
    )
    .unwrap();
    let release: ModelDeploymentRelease =
        serde_json::from_value(profile["release"].clone()).unwrap();
    let request = InferenceRequest::parse(
        &serde_json::to_vec(&json!({
            "model": profile["model_id"],
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 8,
            "temperature": 0,
        }))
        .unwrap(),
    )
    .unwrap();
    let runtime = Arc::new(
        SglangClient::with_tokenizer_and_tls(None, ModelTokenizer::new().unwrap(), None).unwrap(),
    );
    let mut primary = deployment(1);
    primary.service_url = primary_url;
    primary.release = release.clone();
    primary.fault_domain = "isolated-runpod-test".to_owned();
    let mut fallback = deployment(2);
    fallback.service_url = fallback_url;
    fallback.release = release;
    fallback.fault_domain = primary.fault_domain.clone();

    RuntimeCall::local(
        runtime,
        request,
        8,
        Utc::now() + TimeDelta::seconds(4),
        primary,
        vec![fallback],
    )
}

#[tokio::test]
#[ignore = "requires two isolated TP1 replicas; primary must reject new requests at capacity"]
async fn live_tp1_admission_rejection_fails_over_within_probe_deadline() {
    use crate::runtime::RuntimeStreamEvent;

    for streaming in [false, true] {
        let mut call = live_call();
        call.request.stream = streaming;
        let failure = if streaming {
            call.runtime
                .stream(call.deployment(), call.request.clone(), 8, call.deadline)
                .await
                .err()
                .expect("full primary accepted a stream")
        } else {
            call.runtime
                .complete(call.deployment(), call.request.clone(), 8, call.deadline)
                .await
                .unwrap_err()
        };
        assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
        assert_eq!(failure.usage(), NormalizedUsage::zero());
        let fallback_id = call.plan.fallbacks[0].id;
        let started = Instant::now();
        let output_tokens = if streaming {
            tokio::time::timeout(std::time::Duration::from_secs(4), async {
                let mut events = call
                    .stream()
                    .await
                    .unwrap_or_else(|_| panic!("live stream failover failed"));
                let mut output = 0;
                let mut done = false;
                while let Some(event) = events.next_event().await.unwrap() {
                    match event {
                        RuntimeStreamEvent::Chunk(chunk) => {
                            if let Some(usage) = chunk.usage() {
                                output = usage.output_tokens();
                            }
                        }
                        RuntimeStreamEvent::Done => {
                            done = true;
                            break;
                        }
                    }
                }
                assert!(done);
                output
            })
            .await
            .unwrap()
        } else {
            call.complete()
                .await
                .unwrap_or_else(|_| panic!("live TP1 failover failed"))
                .usage()
                .output_tokens()
        };
        assert_eq!(call.deployment().id, fallback_id);
        assert!(output_tokens > 0);
        assert!(started.elapsed().as_secs_f64() < 4.0);
        println!(
            "{}",
            json!({"streaming":streaming,"elapsed_ms": started.elapsed().as_millis(), "served_deployment": fallback_id})
        );
    }
}

#[tokio::test]
#[ignore = "requires two isolated TP1 replicas, both rejecting requests at capacity"]
async fn live_tp1_both_at_capacity_return_429_after_two_attempts() {
    use super::support::{logged, qualified_request, Harness};
    use crate::diagnostics::capture::Logs;

    for streaming in [false, true] {
        let call = live_call();
        let mut request = qualified_request(2);
        request.local = Some(crate::coordinator::LocalCapacity {
            deployment: call.deployment().clone(),
            deployments: vec![call.deployment().clone(), call.plan.fallbacks[0].clone()],
            release_digest: call.deployment().served_release_digest().unwrap(),
        });
        request.request = call.request;
        request.request.stream = streaming;
        request.effective_output_tokens = 8;
        let mut harness = Harness::new(request, []);
        harness.service.runtime = call.runtime;
        let mut config = crate::GatewayConfig::for_tests();
        config.generation_timeout_seconds = 4;
        harness.service.config = Arc::new(config);
        let logs = Logs::default();
        let _guard = logs.start();
        let started = Instant::now();
        let error = if streaming {
            harness
                .open()
                .await
                .err()
                .expect("both full replicas accepted a stream")
        } else {
            harness.complete().await.unwrap_err()
        };
        assert_eq!(error, GatewayError::CapacityExceeded);
        assert_eq!(
            error.into_response().status(),
            StatusCode::TOO_MANY_REQUESTS
        );
        assert!(started.elapsed().as_secs_f64() < 4.0);
        let events = logs.events();
        let attempts = logged(&events, "dispatch");
        assert_eq!(attempts.len(), 2);
        assert_eq!(attempts[0]["fields"]["retry_selected"], true);
        assert_eq!(attempts[1]["fields"]["retry_selected"], false);
        let finalized = harness.only_finalized();
        assert_eq!(finalized["status"], "failed");
        assert_eq!(finalized["usage"]["charge"], 0);
        assert_eq!(finalized["outcome"]["error_code"], "capacity_exceeded");
        println!(
            "{}",
            json!({"streaming":streaming,"elapsed_ms":started.elapsed().as_millis(),"status":429,"attempts":attempts.len(),"charge":0})
        );
    }
}

#[tokio::test]
#[ignore = "requires an isolated TP1 replica and a fresh million-token synthetic chat fixture"]
async fn live_tp1_million_token_prefill_can_exceed_the_generation_idle_timeout() {
    use crate::runtime::RuntimeStreamEvent;

    let mut call = live_call();
    call.request = InferenceRequest::parse(
        &std::fs::read(std::env::var("GRADIATED_QUEUE_TEST_LONG_REQUEST_FILE").unwrap()).unwrap(),
    )
    .unwrap();
    assert!(call.request.stream);
    call.effective_output_tokens = 64;
    call.deadline = Utc::now() + TimeDelta::seconds(630);
    let started = Instant::now();
    let mut events = call
        .stream()
        .await
        .unwrap_or_else(|_| panic!("live long stream failed to open"));
    if std::env::var("GRADIATED_QUEUE_TEST_REQUIRE_FALLBACK").as_deref() == Ok("1") {
        assert_eq!(call.deployment().id, Uuid::from_u128(2));
    }
    let mut first_output = None;
    let mut usage = None;
    let mut done = false;

    while let Some(event) = events.next_event().await.unwrap() {
        match event {
            RuntimeStreamEvent::Chunk(chunk) => {
                if chunk.has_usable_output() {
                    first_output.get_or_insert_with(|| started.elapsed());
                }
                if let Some(observed) = chunk.usage() {
                    usage = Some(observed);
                }
            }
            RuntimeStreamEvent::Done => {
                done = true;
                break;
            }
        }
    }

    let usage = usage.unwrap();
    let first_output = first_output.unwrap().as_secs_f64();
    assert!(done);
    assert!(first_output > 30.0);
    assert!(first_output < 630.0);
    assert!(usage.input_tokens() >= 1_000_000);
    assert_eq!(usage.cached_input_tokens(), 0);
    assert!(usage.output_tokens() > 0);
    println!(
        "{}",
        json!({"ttft_s":first_output,"elapsed_s":started.elapsed().as_secs_f64(),"input_tokens":usage.input_tokens(),"cached_input_tokens":usage.cached_input_tokens(),"output_tokens":usage.output_tokens()})
    );
}
