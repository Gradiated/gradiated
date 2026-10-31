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

    RuntimeCall {
        runtime,
        generation_id: Uuid::now_v7(),
        request,
        effective_output_tokens: 8,
        deadline: Utc::now() + TimeDelta::seconds(4),
        deployment: primary,
        fallbacks: vec![fallback],
    }
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
                .stream(&call.deployment, call.request.clone(), 8, call.deadline)
                .await
                .err()
                .expect("full primary accepted a stream")
        } else {
            call.runtime
                .complete(&call.deployment, call.request.clone(), 8, call.deadline)
                .await
                .unwrap_err()
        };
        assert_eq!(failure.kind(), RuntimeFailureKind::CapacityExceeded);
        assert_eq!(failure.usage(), NormalizedUsage::zero());
        let fallback_id = call.fallbacks[0].id;
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
        assert_eq!(call.deployment.id, fallback_id);
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
        request.deployment = call.deployment.clone();
        request.served_release_digest = request.deployment.served_release_digest().unwrap();
        request.model_deployments = vec![call.deployment.clone(), call.fallbacks[0].clone()];
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
