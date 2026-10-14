use std::time::Duration;

use super::{super::*, support::*};
use crate::{diagnostics::capture::Logs, RuntimeFailure, RuntimeFailureKind, RuntimeStreamEvent};

struct CounterCase {
    name: &'static str,
    first_input: u64,
    last_input: u64,
    last_output: u64,
    status: &'static str,
}

#[tokio::test]
async fn streaming_uses_runtime_counts_but_rejects_inconsistent_counters() {
    let cases = [
        CounterCase {
            name: "runtime reports consistent counts",
            first_input: 7,
            last_input: 7,
            last_output: 2,
            status: "succeeded",
        },
        CounterCase {
            name: "input count changes mid-stream",
            first_input: 7,
            last_input: 8,
            last_output: 2,
            status: "failed",
        },
        CounterCase {
            name: "output count decreases",
            first_input: 7,
            last_input: 7,
            last_output: 0,
            status: "failed",
        },
    ];

    for case in cases {
        let events = vec![
            content("hi", Some(usage(case.first_input, 0, 1))),
            finish("stop"),
            terminal_usage(usage(case.last_input, 0, case.last_output)),
            Ok(RuntimeStreamEvent::Done),
        ];
        let harness = Harness::new(streaming_request(1), [Script::Stream(events)]);

        harness.stream().await.unwrap();

        let finalized = harness.only_finalized();
        assert_eq!(finalized["status"], case.status, "{}", case.name);
        assert_eq!(
            finalized["usage"]["input_tokens"], case.first_input,
            "{}",
            case.name
        );
        if case.status == "succeeded" {
            assert_eq!(
                finalized["usage"]["output_tokens"], case.last_output,
                "{}",
                case.name
            );
            assert_eq!(
                finalized["usage"]["charge"],
                case.first_input * 2 + case.last_output * 3,
                "{}",
                case.name
            );
        }
    }
}

#[tokio::test]
async fn streaming_finalizes_before_done_and_exposes_only_terminal_usage() {
    let harness = Harness::new(streaming_request(1), [successful_stream()]);

    let mut renderer = crate::protocol::Protocol::OpenAiChat.stream_renderer();
    let frames = harness
        .stream()
        .await
        .unwrap()
        .into_iter()
        .flat_map(|item| renderer.render(item))
        .collect::<Vec<_>>();

    assert_eq!(
        frames.last().map(|frame| frame.data.as_str()),
        Some("[DONE]")
    );
    assert_eq!(
        frames
            .iter()
            .filter(|frame| frame.data.contains("\"usage\""))
            .count(),
        1
    );
    let finalized = harness.only_finalized();
    let usage_frame = frames
        .iter()
        .find(|frame| frame.data.contains("\"usage\""))
        .unwrap();
    let response: serde_json::Value = serde_json::from_str(&usage_frame.data).unwrap();
    assert_eq!(response["usage"]["cost"], serde_json::json!(0.000000026));
    assert_eq!(finalized["usage"]["charge"], 26);
    assert_eq!(finalized["status"], "succeeded");
    assert_eq!(finalized["streamed"], true);
    assert_eq!(finalized["usage"]["input_tokens"], 10);
    assert_eq!(finalized["usage"]["output_tokens"], 2);
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
    assert!(finalized["timing"]["first_token_at"].is_string());
}

#[tokio::test]
async fn a_stream_that_fails_to_open_retries_on_the_fallback() {
    let harness = Harness::new(
        streaming_request(2),
        [
            failure(RuntimeFailureKind::Unavailable),
            successful_stream(),
        ],
    );

    let items = harness.stream().await.unwrap();

    assert_eq!(items.last(), Some(&StreamItem::Done));
    assert_eq!(harness.journal.dispatches().len(), 2);
    assert_eq!(harness.only_finalized()["status"], "succeeded");
}

#[tokio::test]
async fn a_stream_that_fails_to_open_without_a_fallback_returns_the_settled_error() {
    let harness = Harness::new(
        streaming_request(1),
        [failure(RuntimeFailureKind::CapacityExceeded)],
    );

    assert_eq!(
        harness.open().await.err(),
        Some(GatewayError::CapacityExceeded)
    );

    assert_eq!(harness.journal.dispatches().len(), 1);
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["outcome"]["error_code"], "capacity_exceeded");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], false);
}

#[tokio::test]
async fn an_overlong_streamed_finish_reason_ends_with_an_error_frame() {
    let harness = Harness::new(
        streaming_request(1),
        [Script::Stream(vec![
            content("hi", Some(usage(10, 0, 1))),
            finish(&"x".repeat(101)),
            terminal_usage(usage(10, 0, 2)),
            Ok(RuntimeStreamEvent::Done),
        ])],
    );

    let items = harness.stream().await.unwrap();

    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::RuntimeUnavailable))
    );
    assert_eq!(harness.only_finalized()["status"], "failed");
}

#[tokio::test]
async fn the_request_deadline_mid_stream_settles_as_a_server_cancellation() {
    let logs = Logs::default();
    let _guard = logs.start();
    let (hang, signal) = hang();
    let timeout = GatewayConfig::for_tests().generation_timeout_seconds;
    let mut request = streaming_request(1);
    request.metadata.received_at = Utc::now() - chrono::TimeDelta::seconds(timeout as i64)
        + chrono::TimeDelta::milliseconds(300);
    let harness = Harness::new(
        request,
        [Script::StreamThenHang(
            vec![content("hi", Some(usage(10, 0, 1)))],
            hang,
        )],
    );

    let items = tokio::time::timeout(Duration::from_secs(5), harness.stream())
        .await
        .expect("the deadline ends the stream")
        .unwrap();

    assert!(matches!(items[0], StreamItem::Chunk(_)));
    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::RuntimeUnavailable))
    );
    harness.drained().await;
    assert!(signal.dropped());
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "cancelled");
    assert_eq!(finalized["outcome"]["cancellation_owner"], "server");
    assert_eq!(finalized["outcome"]["usable_output_delivered"], true);
    let events = logs.events();
    assert_eq!(logged(&events, "stream")[0]["fields"]["reason"], "deadline");
}

#[tokio::test]
async fn a_mid_stream_failure_settles_the_usage_it_reports() {
    let harness = Harness::new(
        streaming_request(1),
        [Script::Stream(vec![
            content("hi", Some(usage(10, 0, 1))),
            Err(RuntimeFailure::with_usage(
                RuntimeFailureKind::Unavailable,
                usage(10, 0, 3),
            )),
        ])],
    );

    let items = harness.stream().await.unwrap();

    assert_eq!(
        items.last(),
        Some(&StreamItem::Error(GatewayError::RuntimeUnavailable))
    );
    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["usage"]["output_tokens"], 3);
    assert_eq!(finalized["usage"]["charge"], 10 * 2 + 3 * 3);
    assert_eq!(finalized["outcome"]["error_code"], "runtime_unavailable");
}

#[tokio::test]
async fn a_failure_reporting_less_usage_than_observed_is_ignored() {
    let harness = Harness::new(
        streaming_request(1),
        [Script::Stream(vec![
            content("hi", Some(usage(10, 0, 3))),
            Err(RuntimeFailure::with_usage(
                RuntimeFailureKind::Unavailable,
                usage(10, 0, 1),
            )),
        ])],
    );

    harness.stream().await.unwrap();

    let finalized = harness.only_finalized();
    assert_eq!(finalized["status"], "failed");
    assert_eq!(finalized["usage"]["output_tokens"], 3);
    assert_eq!(finalized["usage"]["charge"], 10 * 2 + 3 * 3);
}

#[tokio::test]
async fn logs_incomplete_stream_after_response_start_without_payload() {
    let logs = Logs::default();
    let _guard = logs.start();
    let harness = Harness::new(
        streaming_request(1),
        [Script::Stream(vec![
            content("private-output-canary", None),
            Ok(RuntimeStreamEvent::Done),
        ])],
    );

    harness.stream().await.unwrap();

    let events = logs.events();
    let failure = logged(&events, "stream")[0];
    assert_eq!(
        failure["fields"]["generation_id"],
        harness.request.metadata.generation_id.to_string()
    );
    assert_eq!(failure["fields"]["reason"], "incomplete_stream");
    assert_eq!(failure["fields"]["usable_output_delivered"], true);
    assert!(!serde_json::to_string(&events)
        .unwrap()
        .contains("private-output-canary"));
    assert_eq!(harness.only_finalized()["status"], "failed");
}
