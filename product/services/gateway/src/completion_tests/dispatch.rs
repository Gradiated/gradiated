use serde_json::json;

use super::{super::*, support::*};
use crate::{
    completion::dispatch::RuntimeCall, diagnostics::capture::Logs, routing::fixtures::deployment,
    serving_state::ServingStateError, AdmissionError, GatewayModelDeployment, NormalizedUsage,
    RuntimeFailure, RuntimeFailureKind,
};

#[tokio::test]
async fn admits_dispatches_and_settles_before_returning_the_response() {
    let harness = Harness::new(qualified_request(1), [completion()]);

    let result = harness.complete().await.unwrap();

    assert_eq!(result.response["id"], "chatcmpl-1");
    assert_eq!(
        harness.journal.steps(),
        vec![
            Step::Admit,
            Step::Dispatch(harness.deployment_ids()[0]),
            Step::Finalize
        ]
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "succeeded");
    assert_eq!(finalized["streamed"], false);
    assert_eq!(finalized["usage"]["charge"], 31);
    assert_eq!(finalized["usage"]["input_tokens"], 10);
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
    assert!(finalized["timing"]["first_token_at"].is_null());
}

#[tokio::test]
async fn chat_dispatch_does_not_depend_on_local_template_or_context_estimates() {
    let mut request = qualified_request(1);
    request
        .local_capacity_mut()
        .deployment
        .release
        .tokenizer_path = "missing/local-artifact".to_owned();
    request.max_prompt_tokens = 0;
    request.max_context_tokens = 1;
    request
        .request
        .parameters
        .insert("reasoning_effort".to_owned(), json!("deployment-specific"));
    let harness = Harness::new(request.clone(), [completion()]);

    let prepared = harness.service.bound(request.clone()).await.unwrap();

    assert_eq!(prepared.request, request.request);
    assert_eq!(prepared.request.encoded_input_ids, None);
    assert!(harness.complete().await.is_ok());
    assert_eq!(harness.journal.dispatches().len(), 1);
}

#[tokio::test]
async fn unavailable_runtime_retries_one_other_deployment_and_settles_once() {
    let harness = Harness::new(
        qualified_request(2),
        [failure(RuntimeFailureKind::Unavailable), completion()],
    );

    let result = harness.complete().await.unwrap();

    assert_eq!(result.response["id"], "chatcmpl-1");
    let dispatches = harness.journal.dispatches();
    assert_eq!(dispatches.len(), 2);
    assert_ne!(dispatches[0], dispatches[1]);
    assert!(dispatches
        .iter()
        .all(|id| harness.deployment_ids().contains(id)));
    assert_eq!(harness.journal.finalizations(), 1);
    assert_eq!(harness.only_finalized()["status"], "succeeded");
}

#[tokio::test]
async fn a_retried_generation_is_measured_on_the_deployment_that_served_it() {
    let harness = Harness::new(
        qualified_request(2),
        [failure(RuntimeFailureKind::Unavailable), completion()],
    );

    harness.complete().await.unwrap();

    let dispatches = harness.journal.dispatches();
    let primary = format!("deployment=\"{}\"", dispatches[0]);
    let fallback = format!("deployment=\"{}\"", dispatches[1]);
    assert_eq!(harness.metric("generations_total", &fallback), 1);
    assert_eq!(harness.metric("tokens_total", &fallback), 10 + 4 + 5);
    assert_eq!(harness.metric("generations_total", &primary), 0);
    assert_eq!(harness.metric("tokens_total", &primary), 0);
    assert_eq!(harness.metric("admissions_total", &primary), 1);
}

#[tokio::test]
async fn a_second_retryable_failure_is_final() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(
        qualified_request(3),
        [
            failure(RuntimeFailureKind::CapacityExceeded),
            failure(RuntimeFailureKind::Unavailable),
        ],
    );

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    let dispatches = harness.journal.dispatches();
    assert_eq!(dispatches.len(), 2);
    assert_ne!(dispatches[0], dispatches[1]);
    assert_eq!(harness.only_finalized()["status"], "failed");
    let events = logs.events();
    let attempts = logged(&events, "dispatch");
    assert_eq!(attempts.len(), 2);
    assert_eq!(attempts[0]["fields"]["attempt"], 1);
    assert_eq!(attempts[0]["fields"]["retry_selected"], true);
    assert_eq!(attempts[1]["fields"]["attempt"], 2);
    assert_eq!(attempts[1]["fields"]["retry_selected"], false);
}

#[tokio::test]
async fn failures_that_may_have_done_work_or_have_no_fallback_do_not_retry() {
    let cases = [
        (
            "failure carries usage",
            RuntimeFailure::with_usage(RuntimeFailureKind::Unavailable, usage(10, 0, 0)),
            2,
        ),
        (
            "invalid request",
            RuntimeFailure::new(RuntimeFailureKind::InvalidRequest),
            2,
        ),
        (
            "timed out",
            RuntimeFailure::new(RuntimeFailureKind::TimedOut),
            2,
        ),
        (
            "no fallback",
            RuntimeFailure::new(RuntimeFailureKind::Unavailable),
            1,
        ),
    ];

    for (name, runtime_failure, deployments) in cases {
        let error = runtime_failure.gateway_error();
        let harness = Harness::new(
            qualified_request(deployments),
            [Script::Fail(runtime_failure)],
        );

        assert_eq!(harness.complete().await.unwrap_err(), error, "{name}");
        assert_eq!(harness.journal.dispatches().len(), 1, "{name}");
        assert_eq!(harness.journal.finalizations(), 1, "{name}");
    }
}

#[tokio::test]
async fn a_timed_out_runtime_settles_as_a_server_cancellation() {
    let harness = Harness::new(
        qualified_request(1),
        [failure(RuntimeFailureKind::TimedOut)],
    );

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "server");
    assert_eq!(finalized["outcome"]["error_code"], "runtime_unavailable");
}

struct Fallbacks {
    same_fault_domain: GatewayModelDeployment,
    same_provider: GatewayModelDeployment,
    other_provider: GatewayModelDeployment,
}

fn fallbacks() -> Fallbacks {
    Fallbacks {
        same_fault_domain: placed(2, "b", "x"),
        same_provider: placed(3, "a", "y"),
        other_provider: placed(4, "b", "y"),
    }
}

fn placed(id: u128, provider: &str, fault_domain: &str) -> GatewayModelDeployment {
    GatewayModelDeployment {
        provider: provider.to_owned(),
        fault_domain: fault_domain.to_owned(),
        ..deployment(id)
    }
}

fn runtime_call(fallbacks: &[&GatewayModelDeployment]) -> RuntimeCall {
    let request = qualified_request(1);

    RuntimeCall::local(
        Arc::new(ScriptedRuntime::new([], Journal::default())),
        request.request,
        request.effective_output_tokens,
        Utc::now(),
        placed(1, "a", "x"),
        fallbacks
            .iter()
            .map(|deployment| (*deployment).clone())
            .collect(),
    )
}

#[test]
fn a_full_runtime_falls_back_to_another_fault_domain_whatever_its_provider() {
    let Fallbacks {
        same_fault_domain,
        same_provider,
        other_provider,
    } = fallbacks();

    let mut call = runtime_call(&[&same_fault_domain, &same_provider, &other_provider]);

    assert!(call
        .fall_back(RuntimeFailureKind::CapacityExceeded, true)
        .is_some());
    assert_eq!(call.deployment(), &same_provider);
    assert_eq!(call.plan.fallbacks.len(), 2);
}

#[test]
fn an_unavailable_runtime_also_falls_back_to_another_provider() {
    let Fallbacks {
        same_fault_domain,
        same_provider,
        other_provider,
    } = fallbacks();

    let mut call = runtime_call(&[&same_fault_domain, &same_provider, &other_provider]);
    assert!(call
        .fall_back(RuntimeFailureKind::Unavailable, true)
        .is_some());
    assert_eq!(call.deployment(), &other_provider);

    let mut call = runtime_call(&[&same_fault_domain, &same_provider]);
    assert!(call
        .fall_back(RuntimeFailureKind::Unavailable, true)
        .is_some());
    assert_eq!(call.deployment(), &same_provider);
}

#[tokio::test]
async fn a_failed_deployment_status_read_dispatches_nothing() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(qualified_request(1), []);
    *harness.state.status_error.lock().unwrap() = Some(ServingStateError::UnexpectedPingResponse);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::ServingStateUnavailable
    );

    assert!(harness.journal.steps().is_empty());
    let events = logs.events();
    let failures = logged(&events, "deployment_status_read");
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["fields"]["error_code"], "unexpected_ping");
}

#[tokio::test]
async fn busy_deployments_reject_the_request_at_capacity() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(qualified_request(2), []);
    for status in harness.state.statuses.lock().unwrap().iter_mut() {
        status.accepting_requests = false;
    }

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::CapacityExceeded
    );

    assert_eq!(
        harness.metric("routing_capacity_rejections_total", "model="),
        1
    );

    assert!(harness.metric("capacity_rejection_timestamp_seconds", "model=") > 0);

    assert!(harness.journal.steps().is_empty());
    let events = logs.events();
    let failures = logged(&events, "routing");
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["fields"]["at_capacity"], 2);
}

#[tokio::test]
async fn adapter_capacity_pressure_is_counted_against_its_base_model() {
    let mut request = qualified_request(2);
    request.request.model = "private-adapter".to_owned();
    request.adapter = Some(crate::PrivateAdapter {
        workspace_id: request.identity.workspace_id,
        organization_slug: "acme".to_owned(),
        task_name: "task-a".to_owned(),
        version_id: uuid::Uuid::nil(),
        name: "private-adapter".to_owned(),
        status: "available".to_owned(),
        size_bytes: 1,
        base_model_id: "base-model".to_owned(),
        base_model_revision: "revision".to_owned(),
        sha256: "a".repeat(64),
    });
    let harness = Harness::new(request, []);
    for status in harness.state.statuses.lock().unwrap().iter_mut() {
        status.accepting_requests = false;
    }

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::CapacityExceeded
    );
    assert_eq!(
        harness.metric("routing_capacity_rejections_total", "model=\"base-model\""),
        1
    );
    assert_eq!(
        harness.metric(
            "routing_capacity_rejections_total",
            "model=\"private-adapter\""
        ),
        0
    );
}

#[tokio::test]
async fn unhealthy_deployments_leave_the_runtime_unavailable_without_admission() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(qualified_request(2), []);
    {
        let mut statuses = harness.state.statuses.lock().unwrap();
        statuses[0].healthy = false;
        statuses[1].received_at -= chrono::TimeDelta::hours(1);
    }

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    assert!(harness.journal.steps().is_empty());
    let events = logs.events();
    let failures = logged(&events, "routing");
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["fields"]["unhealthy"], 1);
    assert_eq!(failures[0]["fields"]["stale_status"], 1);
}

#[tokio::test]
async fn an_admission_rejection_dispatches_nothing_and_is_counted() {
    let harness = Harness::new(qualified_request(1), []);
    *harness.state.admission_error.lock().unwrap() = Some(AdmissionError::ConcurrencyExceeded);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::ConcurrencyExceeded
    );

    assert_eq!(harness.journal.steps(), vec![Step::Admit]);
    assert_eq!(
        harness.metric(
            "admission_rejections_total",
            "reason=\"concurrency_exceeded\""
        ),
        1
    );
}

#[tokio::test]
async fn a_rejected_generation_identity_is_logged_before_admission() {
    let logs = Logs::default();
    let _guard = logs.start();
    let mut request = qualified_request(1);
    request.request.model = "m".repeat(301);
    let harness = Harness::new(request, []);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::ServingStateUnavailable
    );

    assert!(harness.journal.steps().is_empty());
    let events = logs.events();
    let failures = logged(&events, "generation_identity");
    assert_eq!(failures.len(), 1);
    assert_eq!(failures[0]["fields"]["error_code"], "invalid_model_id");
}

#[tokio::test]
async fn identical_sessionless_requests_keep_prefix_affinity() {
    let request = qualified_request(8);
    let harness = Harness::new(request.clone(), []);
    let mut primaries = std::collections::HashSet::new();
    for generation in 1..=256 {
        let mut current = request.clone();
        current.metadata.generation_id = Uuid::from_u128(generation);
        primaries.insert(
            harness
                .service
                .route(&current, current.local_capacity())
                .await
                .unwrap()
                .ok()
                .unwrap()
                .primary
                .id,
        );
    }
    assert_eq!(primaries.len(), 1);
}

#[tokio::test]
async fn an_explicit_session_keeps_its_replica_across_requests() {
    let mut request = qualified_request(8);
    request.request.session_id = Some("chat-session".to_owned());
    let harness = Harness::new(request.clone(), []);
    let mut primaries = std::collections::HashSet::new();
    for generation in 1..=256 {
        let mut current = request.clone();
        current.metadata.generation_id = Uuid::from_u128(generation);
        primaries.insert(
            harness
                .service
                .route(&current, current.local_capacity())
                .await
                .unwrap()
                .ok()
                .unwrap()
                .primary
                .id,
        );
    }
    assert_eq!(primaries.len(), 1);
}

#[tokio::test]
async fn capacity_failures_keep_their_authorised_traffic_class_through_settlement() {
    for is_verification in [false, true] {
        let mut request = qualified_request(1);
        request.is_verification = is_verification;
        let harness = Harness::new(request, [failure(RuntimeFailureKind::CapacityExceeded)]);

        assert_eq!(
            harness.complete().await.unwrap_err(),
            GatewayError::CapacityExceeded
        );
        let traffic = if is_verification {
            "verification"
        } else {
            "routed"
        };
        assert_eq!(
            harness.metric("generations_total", &format!("traffic=\"{traffic}\"")),
            1
        );
        let finalized = harness.only_finalized();
        assert_eq!(finalized["status"], "failed");
        assert_eq!(finalized["usage"]["charge"], 0);
    }
}

#[tokio::test]
async fn optional_energy_does_not_change_capacity_retry_behavior() {
    let refusal = Script::Fail(RuntimeFailure::with_usage(
        RuntimeFailureKind::Unavailable,
        NormalizedUsage::zero().with_estimated_joules(Some(1.0)),
    ));
    let harness = Harness::new(qualified_request(2), [refusal, completion()]);

    harness.complete().await.unwrap();

    assert_eq!(harness.journal.dispatches().len(), 2);
    assert_eq!(harness.only_finalized()["usage"]["charge"], 31);
}
