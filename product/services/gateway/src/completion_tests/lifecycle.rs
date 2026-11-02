use std::time::Duration;

use axum::http::HeaderMap;
use futures_util::{FutureExt, StreamExt};

use super::{super::*, support::*};
use crate::completion::tasks::GenerationTasks;

#[tokio::test]
async fn a_draining_service_rejects_new_generations() {
    let harness = Harness::new(qualified_request(1), []);
    harness.service.begin_draining();

    assert_eq!(
        harness.complete().await.unwrap_err(),
        GatewayError::RuntimeUnavailable
    );

    assert!(harness.journal.steps().is_empty());
}

#[tokio::test]
async fn draining_waits_for_a_request_that_entered_before_admission() {
    let (gate, handle) = gate();
    let harness = Arc::new(Harness::new(qualified_request(1), [completion()]));
    *harness.state.status_gate.lock().unwrap() = Some(gate);
    let running = tokio::spawn({
        let harness = harness.clone();
        async move { harness.complete().await }
    });
    handle.entered.await.unwrap();

    harness.service.begin_draining();
    let mut drain = Box::pin(harness.service.wait_for_drain());
    assert!((&mut drain).now_or_never().is_none());

    handle.release.send(()).unwrap();
    assert!(running.await.unwrap().is_ok());
    tokio::time::timeout(Duration::from_secs(5), drain)
        .await
        .expect("the admitted generation settles and the drain ends");

    assert_eq!(harness.only_finalized()["status"], "succeeded");
}

#[tokio::test]
async fn a_dropped_request_drops_runtime_work_and_finalizes_as_client_owned() {
    let (hang, mut signal) = hang();
    let harness = Harness::new(qualified_request(1), [Script::Hang(hang)]);
    let mut completion = Box::pin(harness.complete());

    tokio::select! {
        _ = &mut completion => panic!("the runtime never answers"),
        started = &mut signal.started => started.unwrap(),
    }
    drop(completion);
    harness.drained().await;

    assert!(signal.dropped());
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "client");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], false);
}

#[tokio::test]
async fn a_caller_gone_while_a_stream_opens_settles_as_a_client_cancellation() {
    let (hang, mut signal) = hang();
    let harness = Harness::new(streaming_request(1), [Script::Hang(hang)]);
    let mut opening = Box::pin(harness.open());

    tokio::select! {
        _ = &mut opening => panic!("the runtime never opens the stream"),
        started = &mut signal.started => started.unwrap(),
    }
    drop(opening);
    harness.drained().await;

    assert!(signal.dropped());
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "client");
}

#[tokio::test]
async fn draining_preserves_generation_until_forced_shutdown() {
    let (hang, mut signal) = hang();
    let harness = Arc::new(Harness::new(qualified_request(1), [Script::Hang(hang)]));
    let running = tokio::spawn({
        let harness = harness.clone();
        async move { harness.complete().await }
    });
    (&mut signal.started).await.unwrap();

    harness.service.begin_draining();
    for _ in 0..8 {
        tokio::task::yield_now().await;
    }
    assert!(!running.is_finished());
    assert!(!signal.dropped());
    assert!(harness.finalized().is_empty());

    harness.service.force_shutdown();
    assert_eq!(
        running.await.unwrap().unwrap_err(),
        GatewayError::RuntimeUnavailable
    );
    harness.drained().await;

    assert!(signal.dropped());
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "server");
}

#[tokio::test]
async fn force_shutdown_mid_stream_settles_as_a_server_cancellation() {
    let (hang, signal) = hang();
    let harness = Harness::new(
        streaming_request(1),
        [Script::StreamThenHang(
            vec![content("hi", Some(usage(10, 0, 1)))],
            hang,
        )],
    );
    let mut items = Box::pin(harness.open().await.unwrap().into_stream());

    assert!(matches!(items.next().await, Some(StreamItem::Chunk(_))));
    signal.started.await.unwrap();
    harness.service.force_shutdown();
    let rest = items.collect::<Vec<_>>().await;

    assert_eq!(
        rest,
        vec![StreamItem::Error(GatewayError::RuntimeUnavailable)]
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "server");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
}

#[tokio::test]
async fn a_dropped_streaming_body_finalizes_as_client_cancellation() {
    let (hang, signal) = hang();
    let harness = Harness::new(
        streaming_request(1),
        [Script::StreamThenHang(Vec::new(), hang)],
    );

    let streaming = harness.open().await.unwrap();
    drop(streaming);
    harness.drained().await;

    assert!(signal.dropped());
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "client");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], false);
}

#[tokio::test]
async fn a_body_dropped_mid_stream_settles_the_observed_usage() {
    let (hang, signal) = hang();
    let harness = Harness::new(
        streaming_request(1),
        [Script::StreamThenHang(
            vec![content("hi", Some(usage(10, 0, 1)))],
            hang,
        )],
    );
    let mut items = Box::pin(harness.open().await.unwrap().into_stream());

    assert!(matches!(items.next().await, Some(StreamItem::Chunk(_))));
    signal.started.await.unwrap();
    drop(items);
    harness.drained().await;

    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "client");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
    assert_eq!(finalized["usage"]["output_tokens"], 1);
    assert_eq!(finalized["usage"]["charge"], 10 * 2 + 3);
}

#[test]
fn a_task_dropped_before_its_first_poll_leaves_the_drain_idle() {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .build()
        .unwrap();
    let tasks = GenerationTasks::new();

    {
        let _context = runtime.enter();
        tasks.enter().unwrap().spawn(std::future::pending::<()>());
    }
    assert!(tasks.wait().now_or_never().is_none());
    drop(runtime);

    assert!(tasks.wait().now_or_never().is_some());
}

#[tokio::test]
async fn generation_tasks_keep_request_identity_after_the_handler_returns() {
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    let tasks = GenerationTasks::new();

    let mut handles = Vec::new();
    for id in [Uuid::from_u128(1), Uuid::from_u128(2)] {
        let span = crate::diagnostics::request_span(id, &HeaderMap::new());
        span.record("workspace_id", tracing::field::display(id));
        let active = tasks.enter().unwrap();
        handles.push(span.in_scope(|| {
            active.spawn(async move {
                tokio::task::yield_now().await;
                tracing::info!(event = "test_stream_terminal", "terminal");
            })
        }));
    }
    for handle in handles {
        handle.await.unwrap();
    }

    let events = logs.events();
    assert_eq!(events.len(), 2);
    for event in events {
        assert_eq!(
            event["span"]["workspace_id"],
            event["span"]["generation_id"]
        );
        assert!(event["span"]["workspace_id"].is_string());
    }
}
