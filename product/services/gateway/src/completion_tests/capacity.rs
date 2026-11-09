use std::sync::Arc;

use futures_util::StreamExt;
use serde_json::json;

use super::{super::*, support::*};
use crate::{
    diagnostics::capture::Logs, routing::fixtures::healthy_status, AdmissionError, ExternalModel,
    GatewayModelDeployment, RuntimeFailure, RuntimeFailureKind, RuntimeStreamEvent,
};

fn openrouter_digest() -> String {
    ExternalModel::openrouter(OPENROUTER_MODEL).served_release_digest()
}

fn local_digest(harness: &Harness) -> String {
    harness.request.local_capacity().release_digest.clone()
}

/// `usage(20, 0, 7)` at the captured prices: 20 * 2 + 7 * 3.
const EXTERNAL_CHARGE: u64 = 61;

#[tokio::test]
async fn a_mapped_model_without_deployments_is_served_and_billed_at_catalog_prices() {
    let harness = Harness::new(mapped_request(0), []).openrouter([external_completion()]);

    let result = harness.complete().await.unwrap();

    assert_eq!(result.response["id"], "chatcmpl-external");
    assert_eq!(result.response["usage"]["cost"], json!(0.000000061));
    assert_eq!(
        harness.journal.steps(),
        vec![Step::Admit, Step::External, Step::Finalize]
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "succeeded");
    // OpenRouter reported charging five million nano-USD; the caller pays the catalog price.
    assert_eq!(finalized["usage"]["charge"], EXTERNAL_CHARGE);
    assert_eq!(finalized["model_id"], "model-a");
    assert_eq!(finalized["served_release_digest"], openrouter_digest());
    assert_eq!(
        harness.metric("upstream_cost_nano_usd_total", "deployment=\"openrouter\""),
        5_000_000
    );
    assert_eq!(
        harness.metric(
            "calculated_charge_nano_usd_total",
            "deployment=\"openrouter\""
        ),
        EXTERNAL_CHARGE
    );
    assert_eq!(
        harness.metric(
            "capacity_fallbacks_total",
            "capacity=\"openrouter\",reason=\"no_deployment\""
        ),
        1
    );

    let sent = harness.external.requests.lock().unwrap();
    assert_eq!(sent[0].model.id(), OPENROUTER_MODEL);
    assert_eq!(sent[0].request.model, "model-a");
    assert_eq!(sent[0].workspace_id, harness.request.identity.workspace_id);
    assert_eq!(
        sent[0].output_tokens,
        harness.request.effective_output_tokens
    );
}

#[tokio::test]
async fn healthy_local_capacity_serves_without_openrouter() {
    let harness = Harness::new(mapped_request(2), [completion()]).openrouter([]);

    harness.complete().await.unwrap();

    assert_eq!(harness.journal.dispatches().len(), 1);
    assert_eq!(harness.journal.external_dispatches(), 0);
    let finalized = harness.only_finalized();
    assert_eq!(finalized["served_release_digest"], local_digest(&harness));
    assert_eq!(finalized["usage"]["charge"], 31);
    assert_eq!(
        harness.metric("capacity_fallbacks_total", "model=\"model-a\""),
        0
    );
}

#[tokio::test]
async fn unhealthy_or_saturated_local_capacity_goes_straight_to_openrouter() {
    type Change = fn(&mut crate::DeploymentRuntimeStatus);
    let cases: [(&str, Change); 2] = [
        ("unavailable", |status| status.healthy = false),
        ("at_capacity", |status| status.accepting_requests = false),
    ];

    for (reason, change) in cases {
        let harness = Harness::new(mapped_request(2), [])
            .openrouter([external_completion()])
            .local_status(change);

        harness.complete().await.unwrap();

        assert!(harness.journal.dispatches().is_empty(), "{reason}");
        assert_eq!(harness.journal.external_dispatches(), 1, "{reason}");
        assert_eq!(
            harness.only_finalized()["served_release_digest"],
            openrouter_digest()
        );
        assert_eq!(
            harness.metric(
                "capacity_fallbacks_total",
                &format!("capacity=\"openrouter\",reason=\"{reason}\"")
            ),
            1,
            "{reason}"
        );
        assert_eq!(
            harness.metric("routing_capacity_rejections_total", "model=\"model-a\""),
            0,
            "{reason}: nothing was rejected"
        );
    }
}

#[tokio::test]
async fn saturation_still_signals_the_autoscaler_when_openrouter_serves() {
    let harness = Harness::new(mapped_request(1), [])
        .openrouter([external_completion()])
        .local_status(|status| status.accepting_requests = false);

    harness.complete().await.unwrap();

    assert!(harness.metric("capacity_rejection_timestamp_seconds", "model=\"model-a\"") > 0);
}

#[tokio::test]
async fn a_failed_local_attempt_falls_back_and_settles_once_for_what_served() {
    for kind in [
        RuntimeFailureKind::Unavailable,
        RuntimeFailureKind::CapacityExceeded,
        RuntimeFailureKind::ProtocolViolation,
        RuntimeFailureKind::Interrupted,
        RuntimeFailureKind::ResponseTooLarge,
        // An idle timeout leaves most of the shared deadline for another attempt.
        RuntimeFailureKind::TimedOut,
    ] {
        let harness =
            Harness::new(mapped_request(1), [failure(kind)]).openrouter([external_completion()]);

        let result = harness.complete().await.unwrap();

        assert_eq!(result.response["id"], "chatcmpl-external", "{kind:?}");
        assert_eq!(harness.journal.finalizations(), 1, "{kind:?}");
        let finalized = harness.only_finalized();
        assert_eq!(finalized["usage"]["charge"], EXTERNAL_CHARGE, "{kind:?}");
        assert_eq!(finalized["served_release_digest"], openrouter_digest());
    }
}

#[tokio::test]
async fn work_reported_by_an_abandoned_attempt_is_not_billed() {
    let failed = RuntimeFailure::with_usage(RuntimeFailureKind::Interrupted, usage(10, 0, 9));
    let harness =
        Harness::new(mapped_request(1), [Script::Fail(failed)]).openrouter([external_completion()]);

    harness.complete().await.unwrap();

    let finalized = harness.only_finalized();
    assert_eq!(finalized["usage"]["input_tokens"], 20);
    assert_eq!(finalized["usage"]["output_tokens"], 7);
    assert_eq!(finalized["usage"]["charge"], EXTERNAL_CHARGE);
}

#[tokio::test]
async fn the_local_replica_retry_comes_before_openrouter_and_attempts_stay_bounded() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(
        mapped_request(3),
        [
            failure(RuntimeFailureKind::CapacityExceeded),
            failure(RuntimeFailureKind::Unavailable),
        ],
    )
    .openrouter([external_completion()]);

    harness.complete().await.unwrap();

    assert_eq!(harness.journal.dispatches().len(), 2);
    assert_eq!(harness.journal.external_dispatches(), 1);
    let events = logs.events();
    let attempts = logged(&events, "dispatch");
    let next: Vec<_> = attempts
        .iter()
        .map(|attempt| attempt["fields"]["next_capacity"].clone())
        .collect();
    assert_eq!(next, [json!("local"), json!("openrouter")]);
    assert_eq!(
        harness.metric(
            "capacity_fallbacks_total",
            "capacity=\"openrouter\",reason=\"attempt_failed\""
        ),
        1
    );
}

#[tokio::test]
async fn when_openrouter_also_fails_the_caller_gets_our_own_failure_settled_once() {
    let harness = Harness::new(
        mapped_request(1),
        [failure(RuntimeFailureKind::CapacityExceeded)],
    )
    .openrouter([failure(RuntimeFailureKind::Unavailable)]);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::CapacityExceeded
    );

    assert_eq!(
        harness.journal.steps(),
        vec![
            Step::Admit,
            Step::Dispatch(harness.deployment_ids()[0]),
            Step::External,
            Step::Finalize
        ]
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["usage"]["charge"], 0);
    assert_eq!(finalized["outcome"]["error_code"], "capacity_exceeded");
    assert_eq!(finalized["served_release_digest"], openrouter_digest());
}

#[tokio::test]
async fn openrouter_finding_no_provider_answers_as_our_capacity_would_have() {
    let saturated = Harness::new(mapped_request(1), [])
        .openrouter([failure(RuntimeFailureKind::Unavailable)])
        .local_status(|status| status.accepting_requests = false);
    assert_eq!(
        saturated.complete().await.unwrap_err(),
        GatewayError::CapacityExceeded
    );

    let without_deployments = Harness::new(mapped_request(0), [])
        .openrouter([failure(RuntimeFailureKind::CapacityExceeded)]);
    assert_eq!(
        without_deployments.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    let streamed = Harness::new(mapped_request(1).streamed(), [])
        .openrouter([failure(RuntimeFailureKind::Unavailable)])
        .local_status(|status| status.accepting_requests = false);
    assert_eq!(
        streamed.stream().await.err(),
        Some(GatewayError::CapacityExceeded)
    );
}

#[tokio::test]
async fn an_openrouter_stream_failing_before_any_frame_answers_with_our_failure() {
    let harness = Harness::new(mapped_request(1).streamed(), [])
        .openrouter([Script::Stream(vec![Err(RuntimeFailure::new(
            RuntimeFailureKind::Interrupted,
        ))])])
        .local_status(|status| status.accepting_requests = false);

    let items = harness.stream().await.unwrap();

    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::CapacityExceeded))
    );
    assert_eq!(
        harness.only_finalized()["outcome"]["error_code"],
        "capacity_exceeded"
    );
}

#[tokio::test]
async fn an_openrouter_failure_never_returns_to_local_capacity() {
    let harness = Harness::new(mapped_request(2), [])
        .openrouter([failure(RuntimeFailureKind::Unavailable)])
        .local_status(|status| status.healthy = false);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    assert!(harness.journal.dispatches().is_empty());
    assert_eq!(harness.journal.external_dispatches(), 1);
    assert_eq!(harness.only_finalized()["status"], "failed");
}

#[tokio::test]
async fn an_invalid_request_or_an_exhausted_deadline_does_not_fall_back() {
    let harness = Harness::new(
        mapped_request(1),
        [failure(RuntimeFailureKind::InvalidRequest)],
    )
    .openrouter([]);
    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::invalid_request(None)
    );
    assert_eq!(harness.journal.external_dispatches(), 0);

    let harness =
        Harness::new(mapped_request(1), [failure(RuntimeFailureKind::TimedOut)]).openrouter([]);
    let mut config = GatewayConfig::for_tests();
    config.generation_timeout_seconds = 1;
    let harness = Harness {
        service: CompletionService {
            config: Arc::new(config),
            ..harness.service.clone()
        },
        ..harness
    };
    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );
    assert_eq!(harness.journal.external_dispatches(), 0);
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "server");
}

#[tokio::test]
async fn an_unmapped_model_keeps_its_local_failure() {
    let harness = Harness::new(
        qualified_request(1),
        [failure(RuntimeFailureKind::Unavailable)],
    )
    .openrouter([external_completion()]);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );
    assert_eq!(harness.journal.external_dispatches(), 0);

    let harness = Harness::new(qualified_request(1), [])
        .openrouter([external_completion()])
        .local_status(|status| status.accepting_requests = false);
    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::CapacityExceeded
    );
    assert_eq!(harness.journal.external_dispatches(), 0);
    assert_eq!(
        harness.metric("routing_capacity_rejections_total", "model=\"model-a\""),
        1
    );
}

#[tokio::test]
async fn a_service_without_an_openrouter_client_ignores_a_mapping() {
    let mut harness = Harness::new(mapped_request(0), []);
    harness.service.external = None;

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );
    assert!(harness.journal.steps().is_empty());
}

#[tokio::test]
async fn admission_still_decides_whether_openrouter_may_serve() {
    let harness = Harness::new(mapped_request(0), []).openrouter([]);
    *harness.state.admission_error.lock().unwrap() = Some(AdmissionError::ConcurrencyExceeded);

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::ConcurrencyExceeded
    );

    assert_eq!(harness.journal.steps(), vec![Step::Admit]);
    assert_eq!(
        harness.metric("capacity_fallbacks_total", "model=\"model-a\""),
        0
    );
}

#[tokio::test]
async fn a_cancelled_openrouter_request_settles_once_as_the_client_left() {
    let (hang, signal) = hang();
    let harness = Harness::new(mapped_request(0), []).openrouter([Script::Hang(hang)]);
    let service = harness.service.clone();
    let request = harness.request.clone();

    let pending = tokio::spawn(async move { service.complete(request).await });
    let HangSignal { started, dropped } = signal;
    started.await.unwrap();
    pending.abort();
    harness.drained().await;

    assert!(dropped.load(std::sync::atomic::Ordering::SeqCst));
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "client");
    assert_eq!(finalized["served_release_digest"], openrouter_digest());
}

fn external_stream() -> Script {
    Script::Stream(vec![
        content("from openrouter", None),
        finish("stop"),
        terminal_usage(usage(20, 0, 7)),
        Ok(RuntimeStreamEvent::Done),
    ])
}

fn chunk_text(item: &StreamItem) -> Option<String> {
    match item {
        StreamItem::Chunk(chunk) => chunk["choices"][0]["delta"]["content"]
            .as_str()
            .map(ToOwned::to_owned),
        _ => None,
    }
}

#[tokio::test]
async fn a_stream_that_fails_before_any_frame_is_served_by_openrouter() {
    for local in [
        failure(RuntimeFailureKind::Unavailable),
        Script::Stream(vec![Err(RuntimeFailure::new(
            RuntimeFailureKind::Unavailable,
        ))]),
        Script::Stream(vec![]),
    ] {
        let harness =
            Harness::new(mapped_request(1).streamed(), [local]).openrouter([external_stream()]);

        let items = harness.stream().await.unwrap();

        let text: Vec<_> = items.iter().filter_map(chunk_text).collect();
        assert_eq!(text, ["from openrouter"]);
        assert_eq!(items.last(), Some(&StreamItem::Done));
        let finalized = harness.only_finalized();
        assert_eq!(finalized["status"], "succeeded");
        assert_eq!(finalized["usage"]["charge"], EXTERNAL_CHARGE);
        assert_eq!(finalized["served_release_digest"], openrouter_digest());
    }
}

#[tokio::test]
async fn a_stream_that_delivered_output_is_never_spliced_with_another() {
    let local = Script::Stream(vec![
        content("local", Some(usage(10, 0, 1))),
        Err(RuntimeFailure::new(RuntimeFailureKind::Unavailable)),
    ]);
    let harness =
        Harness::new(mapped_request(1).streamed(), [local]).openrouter([external_stream()]);

    let items = harness.stream().await.unwrap();

    let text: Vec<_> = items.iter().filter_map(chunk_text).collect();
    assert_eq!(text, ["local"]);
    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::RuntimeUnavailable))
    );
    assert_eq!(harness.journal.external_dispatches(), 0);
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
    assert_eq!(finalized["served_release_digest"], local_digest(&harness));
}

#[tokio::test]
async fn an_openrouter_stream_failing_after_output_keeps_the_stream_failure() {
    let harness = Harness::new(mapped_request(1).streamed(), [])
        .openrouter([Script::Stream(vec![
            content("partial", None),
            Err(RuntimeFailure::new(RuntimeFailureKind::Interrupted)),
        ])])
        .local_status(|status| status.accepting_requests = false);

    let items = harness.stream().await.unwrap();

    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::RuntimeUnavailable))
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
}

#[tokio::test]
async fn a_caller_leaving_after_the_finish_is_billed_from_openrouter_final_usage() {
    let (hang, _signal) = hang();
    let harness =
        Harness::new(mapped_request(0).streamed(), []).openrouter([Script::StreamThenHang(
            vec![
                content("answer", None),
                finish("stop"),
                terminal_usage(usage(20, 0, 7)),
            ],
            hang,
        )]);

    let mut stream = Box::pin(harness.open().await.unwrap().into_stream());
    let first = stream.next().await;
    let finish = stream.next().await;
    assert_eq!(
        first.as_ref().and_then(chunk_text).as_deref(),
        Some("answer")
    );
    assert!(matches!(finish, Some(StreamItem::Chunk(_))));
    drop(stream);
    harness.drained().await;

    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "client");
    assert_eq!(finalized["usage"]["charge"], EXTERNAL_CHARGE);
}

#[tokio::test]
async fn a_caller_leaving_mid_answer_is_not_held_waiting_for_usage() {
    let (hang, signal) = hang();
    let harness = Harness::new(mapped_request(0).streamed(), [])
        .openrouter([Script::StreamThenHang(vec![content("partial", None)], hang)]);

    let mut stream = Box::pin(harness.open().await.unwrap().into_stream());
    assert!(stream.next().await.is_some());
    drop(stream);
    let left = std::time::Instant::now();
    harness.drained().await;

    assert!(left.elapsed() < std::time::Duration::from_secs(1));
    assert!(signal.dropped());
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["usage"]["charge"], 0);
}

#[tokio::test]
async fn the_wait_for_final_usage_is_bounded() {
    let harness = Harness::new(mapped_request(0).streamed(), []).openrouter([
        Script::StreamThenStall(vec![content("answer", None), finish("stop")]),
    ]);

    let mut stream = Box::pin(harness.open().await.unwrap().into_stream());
    assert!(stream.next().await.is_some());
    assert!(stream.next().await.is_some());
    drop(stream);
    let left = std::time::Instant::now();
    harness.drained().await;

    let waited = left.elapsed();
    assert!(
        waited >= std::time::Duration::from_millis(1_900),
        "{waited:?}"
    );
    assert!(waited < std::time::Duration::from_secs(4), "{waited:?}");
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["usage"]["charge"], 0);
}

fn adapter() -> crate::PrivateAdapter {
    crate::PrivateAdapter {
        workspace_id: Uuid::now_v7(),
        version_id: Uuid::from_u128(77),
        name: "task-a-v1".to_owned(),
        status: "available".to_owned(),
        size_bytes: 10,
        base_model_id: "model-a".to_owned(),
        base_model_revision: "model-revision".to_owned(),
        sha256: "a".repeat(64),
    }
}

/// An adapter request whose adapter deployments are 1..=adapters and whose base
/// deployments are 101..=100 + bases, each with its own release.
fn adapter_request(adapters: u128, bases: u128, mapped: bool) -> QualifiedRequest {
    let mut request = qualified_request(1);
    let adapter = adapter();
    request.request.model = adapter.model_id();
    request.request.runtime_model_name = Some(adapter.runtime_name());
    request.adapter = Some(adapter);

    let capacity = |ids: Vec<u128>, lora: bool| {
        let deployments: Vec<GatewayModelDeployment> = ids
            .into_iter()
            .map(|id| {
                let mut deployment = crate::routing::fixtures::deployment(id);
                deployment.release.lora_enabled = lora.then_some(true);
                deployment
            })
            .collect();
        deployments
            .first()
            .cloned()
            .map(|deployment| LocalCapacity {
                release_digest: deployment.served_release_digest().unwrap(),
                deployment,
                deployments,
            })
    };
    request.local = capacity((1..=adapters).collect(), true);
    request.base = capacity((101..=100 + bases).collect(), false);
    if mapped {
        request.external = Some(ExternalModel::openrouter(OPENROUTER_MODEL));
    }

    request
}

fn serve_all(harness: &Harness) {
    let mut statuses = harness.state.statuses.lock().unwrap();
    statuses.clear();
    for capacity in [&harness.request.local, &harness.request.base]
        .into_iter()
        .flatten()
    {
        for deployment in &capacity.deployments {
            statuses.push(healthy_status(deployment, chrono::Utc::now()));
        }
    }
}

struct RuntimeNames(std::sync::Mutex<Vec<Option<String>>>);

#[tokio::test]
async fn an_adapter_is_served_with_its_adapter_when_it_can_be() {
    let harness = Harness::new(adapter_request(1, 1, true), [completion()]).openrouter([]);
    serve_all(&harness);

    harness.complete().await.unwrap();

    assert_eq!(harness.journal.dispatches(), [Uuid::from_u128(1)]);
    let finalized = harness.only_finalized();
    let request = &harness.request;
    assert_eq!(
        finalized["served_release_digest"],
        request
            .adapter
            .as_ref()
            .unwrap()
            .served_digest(&request.local_capacity().release_digest)
    );
    assert_eq!(finalized["model_id"], "task-a-v1");
}

#[tokio::test]
async fn an_adapter_without_capacity_degrades_to_its_base_model() {
    for adapters in [0, 1] {
        let harness = Harness::new(adapter_request(adapters, 1, false), [completion()]);
        serve_all(&harness);
        if adapters == 1 {
            harness.state.statuses.lock().unwrap()[0].healthy = false;
        }

        harness.complete().await.unwrap();

        assert_eq!(
            harness.journal.dispatches(),
            [Uuid::from_u128(101)],
            "{adapters}"
        );
        let finalized = harness.only_finalized();
        assert_eq!(finalized["model_id"], "task-a-v1");
        assert_eq!(finalized["usage"]["charge"], 31);
        assert_eq!(
            finalized["served_release_digest"],
            harness.request.base.as_ref().unwrap().release_digest,
            "the base model served without the adapter"
        );
        assert_eq!(
            harness.metric("capacity_fallbacks_total", "capacity=\"local\",reason=\""),
            1
        );
    }
}

#[tokio::test]
async fn a_failed_adapter_attempt_moves_to_base_capacity_then_openrouter() {
    let harness = Harness::new(
        adapter_request(1, 1, true),
        [
            failure(RuntimeFailureKind::Unavailable),
            failure(RuntimeFailureKind::Unavailable),
        ],
    )
    .openrouter([external_completion()]);
    serve_all(&harness);

    harness.complete().await.unwrap();

    assert_eq!(
        harness.journal.steps(),
        vec![
            Step::Admit,
            Step::Dispatch(Uuid::from_u128(1)),
            Step::Dispatch(Uuid::from_u128(101)),
            Step::External,
            Step::Finalize
        ]
    );
    let sent = harness.external.requests.lock().unwrap();
    assert_eq!(sent[0].request.model, "task-a-v1");
    assert_eq!(
        harness.only_finalized()["served_release_digest"],
        openrouter_digest()
    );
}

#[tokio::test]
async fn a_degraded_base_attempt_drops_the_adapter_runtime_name() {
    let journal = Journal::default();
    let names = Arc::new(RuntimeNames(std::sync::Mutex::new(Vec::new())));
    let mut harness = Harness::new(adapter_request(0, 1, false), []);
    serve_all(&harness);
    harness.service.runtime = Arc::new(NamingRuntime {
        names: names.clone(),
        inner: ScriptedRuntime::new([completion()], journal),
    });

    harness.complete().await.unwrap();

    assert_eq!(*names.0.lock().unwrap(), [None]);
}

struct NamingRuntime {
    names: Arc<RuntimeNames>,
    inner: ScriptedRuntime,
}

#[async_trait::async_trait]
impl ModelRuntime for NamingRuntime {
    async fn complete(
        &self,
        deployment: &GatewayModelDeployment,
        request: InferenceRequest,
        effective_output_tokens: u64,
        request_deadline: chrono::DateTime<chrono::Utc>,
    ) -> Result<crate::RuntimeCompletion, RuntimeFailure> {
        self.names
            .0
            .lock()
            .unwrap()
            .push(request.runtime_model_name.clone());
        self.inner
            .complete(
                deployment,
                request,
                effective_output_tokens,
                request_deadline,
            )
            .await
    }
}

#[tokio::test]
async fn an_adapter_with_no_capacity_anywhere_keeps_its_existing_error() {
    let harness = Harness::new(adapter_request(1, 1, false), []);
    serve_all(&harness);
    for status in harness.state.statuses.lock().unwrap().iter_mut() {
        status.healthy = false;
    }

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );
    assert!(harness.journal.steps().is_empty());

    let harness = Harness::new(adapter_request(0, 0, false), []);
    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::ModelUnavailable
    );
}

#[tokio::test]
async fn an_adapter_whose_base_is_mapped_degrades_to_openrouter() {
    let harness = Harness::new(adapter_request(0, 0, true), []).openrouter([external_completion()]);

    harness.complete().await.unwrap();

    let finalized = harness.only_finalized();
    assert_eq!(finalized["model_id"], "task-a-v1");
    assert_eq!(finalized["served_release_digest"], openrouter_digest());
    assert_eq!(finalized["usage"]["charge"], EXTERNAL_CHARGE);
}
