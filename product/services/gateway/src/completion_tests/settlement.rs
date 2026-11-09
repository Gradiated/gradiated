use serde_json::json;

use super::{super::*, support::*};
use crate::{
    completion::settlement::FINALIZATION_ATTEMPTS, diagnostics::capture::Logs,
    generation::fixtures::token_prices, RuntimeCompletion, RuntimeFailureKind,
};

#[tokio::test]
async fn decision_settlement_bills_input_and_cached_input_without_output() {
    let mut request = qualified_request(1);
    let local = request.local_capacity_mut();
    for deployment in &mut local.deployments {
        deployment.release.protocol = Some(crate::RuntimeProtocol::SystemOne);
    }
    local.release_digest = local.deployments[0].served_release_digest().unwrap();
    request.effective_output_tokens = 0;
    request.request = InferenceRequest::parse_kind(
        br#"{"model":"model-a","state":"x","questions":{"q":{"type":"noul","instructions":"yes?"}}}"#,
        crate::RequestKind::SystemOne,
    )
    .unwrap();
    let decision = Script::Complete(RuntimeCompletion::from_normalized_parts(
        json!({"model":"model-a","answers":{"q":{"type":"noul","noul":0.9}},
            "usage":{"input_tokens":10,"cached_input_tokens":4,"output_tokens":0}}),
        "stop".to_owned(),
        usage(10, 4, 0),
    ));
    let harness = Harness::new(request, [decision]);

    let response = harness.complete().await.unwrap().into_response();
    assert_eq!(
        response["usage"],
        json!({"input_tokens":10,"cached_input_tokens":4,"output_tokens":0})
    );

    let finalized = harness.only_finalized();
    assert_eq!(finalized["usage"]["input_tokens"], 10);
    assert_eq!(finalized["usage"]["cached_input_tokens"], 4);
    assert_eq!(finalized["usage"]["output_tokens"], 0);
    assert_eq!(finalized["usage"]["charge"], 16);
}

#[tokio::test]
async fn overload_is_finalized_before_the_public_error_is_returned() {
    let harness = Harness::new(
        qualified_request(1),
        [failure(RuntimeFailureKind::CapacityExceeded)],
    );

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::CapacityExceeded
    );

    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["usage"]["charge"], 0);
    assert_eq!(finalized["outcome"]["error_code"], "capacity_exceeded");
}

#[tokio::test]
async fn finalization_retries_before_returning_a_successful_response() {
    let harness = Harness::new(qualified_request(1), [completion()]).finalizing([
        FinalizationResult::Unconfirmed,
        FinalizationResult::Unconfirmed,
    ]);

    assert!(harness.complete().await.is_ok());

    assert_eq!(harness.journal.finalizations(), 3);
    assert_eq!(harness.finalized().len(), 1);
    assert_eq!(
        harness.metric("finalization_attempts_total", "result=\"error\""),
        2
    );
    assert_eq!(
        harness.metric("finalization_attempts_total", "result=\"settled\""),
        1
    );
    assert_eq!(harness.metric("finalization_retries_total", ""), 2);
    assert_eq!(harness.metric("finalization_failures_total", ""), 0);
}

#[tokio::test]
async fn unconfirmed_finalization_withholds_the_successful_response() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(qualified_request(1), [completion()])
        .finalizing([(); FINALIZATION_ATTEMPTS].map(|_| FinalizationResult::Unconfirmed));

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::FinalizationUnavailable
    );

    assert_eq!(harness.journal.finalizations(), FINALIZATION_ATTEMPTS);
    assert!(harness.finalized().is_empty());
    assert_eq!(
        harness.metric("finalization_attempts_total", "result=\"error\""),
        FINALIZATION_ATTEMPTS as u64
    );
    assert_eq!(
        harness.metric("finalization_retries_total", ""),
        FINALIZATION_ATTEMPTS as u64 - 1
    );
    assert_eq!(harness.metric("finalization_failures_total", ""), 1);
    let events = logs.events();
    let failures = logged(&events, "finalization");
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["level"], "ERROR");
    assert_eq!(failures[0]["fields"]["attempts"], FINALIZATION_ATTEMPTS);
    assert_eq!(
        failures[0]["fields"]["error_code"],
        "unexpected_script_result"
    );
    assert!(failures[0]["fields"]["generation_id"].is_string());
}

#[tokio::test]
async fn a_lease_lost_before_settlement_is_served_but_reported_unsettled() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(qualified_request(1), [completion()])
        .finalizing([FinalizationResult::AlreadyAbsent]);

    assert!(harness.complete().await.is_ok());

    assert_eq!(harness.journal.finalizations(), 1);
    assert_eq!(harness.metric("unsettled_generations_total", ""), 1);
    assert_eq!(
        harness.metric("finalization_attempts_total", "result=\"already_absent\""),
        1
    );
    let events = logs.events();
    let lost = events
        .iter()
        .filter(|event| event["level"] == "ERROR")
        .collect::<Vec<_>>();
    assert_eq!(lost.len(), 1);
    assert!(lost[0]["fields"]["message"]
        .as_str()
        .unwrap()
        .contains("lost its admission lease"));
}

#[tokio::test]
async fn an_absent_lease_after_an_unconfirmed_attempt_is_already_settled() {
    let harness = Harness::new(qualified_request(1), [completion()]).finalizing([
        FinalizationResult::Unconfirmed,
        FinalizationResult::AlreadyAbsent,
    ]);

    assert!(harness.complete().await.is_ok());

    assert_eq!(harness.journal.finalizations(), 2);
    assert_eq!(harness.metric("unsettled_generations_total", ""), 0);
    assert_eq!(harness.metric("finalization_failures_total", ""), 0);
}

#[tokio::test]
async fn an_overlong_finish_reason_settles_once_as_a_failure() {
    let logs = Logs::default();
    let _guard = logs.start();
    let completion = Script::Complete(RuntimeCompletion::from_normalized_parts(
        json!({"id": "chatcmpl-1"}),
        "x".repeat(101),
        usage(10, 4, 5),
    ));
    let harness = Harness::new(qualified_request(1), [completion]);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    assert_eq!(harness.journal.finalizations(), 1);
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["error_code"], "runtime_unavailable");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], false);
    assert_eq!(finalized["usage"]["charge"], 31);
    let events = logs.events();
    let rejected = logged(&events, "completion");
    assert_eq!(rejected.len(), 1);
    assert_eq!(rejected[0]["fields"]["error_code"], "invalid_finish_reason");
}

#[tokio::test]
async fn unpriceable_usage_settles_once_without_a_charge_and_is_logged() {
    let logs = Logs::default();
    let _guard = logs.start();
    let mut request = qualified_request(1);
    request.pricing = token_prices((1 << 53) - 1, 0, 0);
    let completion = Script::Complete(RuntimeCompletion::from_normalized_parts(
        json!({"id": "chatcmpl-1"}),
        "stop".to_owned(),
        usage(2, 0, 0),
    ));
    let harness = Harness::new(request, [completion]);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    assert_eq!(harness.journal.finalizations(), 1);
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["usage"]["charge"], 0);
    assert_eq!(finalized["outcome"]["usable_output_delivered"], false);
    let events = logs.events();
    let overflow = logged(&events, "settlement");
    assert_eq!(overflow.len(), 1);
    assert_eq!(overflow[0]["level"], "ERROR");
    assert_eq!(overflow[0]["fields"]["error_code"], "pricing_overflow");
    assert_eq!(overflow[0]["fields"]["input_tokens"], 2);
}

#[tokio::test]
async fn exhausted_stream_finalization_ends_with_an_error_frame() {
    let harness = Harness::new(streaming_request(1), [successful_stream()])
        .finalizing([(); FINALIZATION_ATTEMPTS].map(|_| FinalizationResult::Unconfirmed));

    let items = harness.stream().await.unwrap();

    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::FinalizationUnavailable))
    );
    assert!(!items.contains(&StreamItem::Done));
    assert!(items
        .iter()
        .all(|item| !matches!(item, StreamItem::Chunk(value) if value.get("usage").is_some())));
}

#[tokio::test]
async fn a_panicking_runtime_settles_once_as_a_logged_failure() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(qualified_request(1), [Script::Panic]);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["error_code"], "runtime_unavailable");
    assert_runtime_panic_logged(&logs.events(), harness.request.metadata.generation_id);
}

fn assert_runtime_panic_logged(events: &[Value], generation_id: Uuid) {
    let panics = logged(events, "runtime");
    assert_eq!(panics.len(), 1);
    assert_eq!(panics[0]["level"], "ERROR");
    assert_eq!(panics[0]["fields"]["error_code"], "runtime_panic");
    assert_eq!(
        panics[0]["fields"]["generation_id"],
        generation_id.to_string()
    );
}

#[tokio::test]
async fn a_runtime_that_panics_before_the_stream_opens_settles_once_as_a_failure() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(streaming_request(1), [Script::Panic]);

    assert_eq!(
        harness.open().await.err(),
        Some(GatewayError::RuntimeUnavailable)
    );

    harness.drained().await;
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], false);
    assert_runtime_panic_logged(&logs.events(), harness.request.metadata.generation_id);
}

#[tokio::test]
async fn a_runtime_that_panics_mid_stream_settles_the_delivered_usage() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(
        streaming_request(1),
        [Script::StreamThenPanic(vec![content(
            "hi",
            Some(usage(10, 0, 1)),
        )])],
    );

    let items = harness.stream().await.unwrap();

    assert_eq!(items.len(), 2);
    assert!(matches!(items[0], StreamItem::Chunk(_)));
    assert_eq!(
        items[1],
        StreamItem::Error(GatewayError::RuntimeUnavailable)
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
    assert_eq!(finalized["usage"]["output_tokens"], 1);
    assert!(finalized["usage"]["charge"].as_u64().unwrap() > 0);
    let events = logs.events();
    assert_runtime_panic_logged(&events, harness.request.metadata.generation_id);
    assert!(logged(&events, "stream").is_empty());
}

#[tokio::test]
async fn a_settlement_panic_is_logged_with_its_generation_and_unavailable() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness =
        Harness::new(qualified_request(1), [completion()]).finalizing([FinalizationResult::Panic]);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::FinalizationUnavailable
    );

    assert_generation_task_failure_logged(&logs.events(), harness.request.metadata.generation_id);
}

#[tokio::test]
async fn a_streamed_settlement_panic_ends_with_an_error_frame() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(streaming_request(1), [successful_stream()])
        .finalizing([FinalizationResult::Panic]);

    let items = harness.stream().await.unwrap();

    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::FinalizationUnavailable))
    );
    harness.drained().await;
    assert_generation_task_failure_logged(&logs.events(), harness.request.metadata.generation_id);
}

fn assert_generation_task_failure_logged(events: &[Value], generation_id: Uuid) {
    let failures = logged(events, "generation_task");
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["level"], "ERROR");
    assert_eq!(failures[0]["fields"]["panicked"], true);
    assert_eq!(
        failures[0]["fields"]["generation_id"],
        generation_id.to_string()
    );
}

#[tokio::test]
async fn buffered_cost_matches_settlement_with_cache_writes_reasoning_and_tier_pricing() {
    use crate::{CapturedPricing, InputTokenPrice, OutputTokenPrice, ServiceTier, TokenUnit};

    let mut request = qualified_request(1);
    request.request.service_tier = ServiceTier::Fast;
    request.pricing = CapturedPricing::for_service_tier(
        &[
            InputTokenPrice::Prompt {
                unit: TokenUnit::Token,
                cost: 10,
            },
            InputTokenPrice::CachedPrompt {
                unit: TokenUnit::Token,
                cost: 2,
            },
            InputTokenPrice::CacheWrite {
                unit: TokenUnit::Token,
                cost: 5,
            },
        ],
        &[
            OutputTokenPrice::Completion {
                unit: TokenUnit::Token,
                cost: 20,
            },
            OutputTokenPrice::InternalReasoning {
                unit: TokenUnit::Token,
                cost: 30,
            },
        ],
        ServiceTier::Fast,
    )
    .unwrap();
    let script = Script::Complete(RuntimeCompletion::from_normalized_parts(
        json!({"usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 999}}),
        "stop".to_owned(),
        crate::NormalizedUsage::new(10, 4, 2, 5, 3).unwrap(),
    ));
    let harness = Harness::new(request, [script]);

    let response = harness.complete().await.unwrap().into_response();
    let finalized = harness.only_finalized();
    let charge = finalized["usage"]["charge"].as_u64().unwrap();
    assert!(charge > 0);
    assert_eq!(
        response["usage"]["cost"].as_f64().unwrap(),
        charge as f64 / 1_000_000_000.0
    );
    assert_eq!(response["usage"]["prompt_tokens"], 10);
    assert_eq!(response["usage"]["completion_tokens"], 5);
}

#[tokio::test]
async fn lost_lease_returns_zero_cost_and_retry_absence_returns_the_settled_cost() {
    for (outcomes, expected) in [
        (vec![FinalizationResult::AlreadyAbsent], 0.0),
        (
            vec![
                FinalizationResult::Unconfirmed,
                FinalizationResult::AlreadyAbsent,
            ],
            0.000000031,
        ),
    ] {
        let script = Script::Complete(RuntimeCompletion::from_normalized_parts(
            json!({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}),
            "stop".to_owned(),
            usage(10, 4, 5),
        ));
        let harness = Harness::new(qualified_request(1), [script]).finalizing(outcomes);

        let response = harness.complete().await.unwrap().into_response();
        assert_eq!(response["usage"]["cost"], json!(expected));
    }
}
