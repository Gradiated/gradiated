use std::{collections::VecDeque, time::Duration};

use async_trait::async_trait;
use serde_json::json;
use tokio::time::Instant;

use crate::runtime::{
    client::{read_bounded_body, read_completion_body},
    progress::ProgressStream,
    RuntimeEventStream, RuntimeFailure, RuntimeStreamChunk, RuntimeStreamEvent,
};

fn delayed_body(delays: Vec<u64>) -> reqwest::Response {
    use futures_util::{stream, StreamExt};

    let chunks = stream::iter(delays).then(|seconds| async move {
        tokio::time::sleep(Duration::from_secs(seconds)).await;
        Ok::<_, std::io::Error>(vec![b'x'])
    });

    reqwest::Response::from(
        axum::http::Response::builder()
            .status(200)
            .body(reqwest::Body::wrap_stream(chunks))
            .unwrap(),
    )
}

#[tokio::test(start_paused = true)]
async fn buffered_completions_allow_prefill_but_rejections_keep_the_short_idle_limit() {
    assert_eq!(
        read_completion_body(delayed_body(vec![275])).await.unwrap(),
        b"x"
    );
    assert_eq!(
        read_bounded_body(delayed_body(vec![31]))
            .await
            .unwrap_err()
            .diagnostic_code(),
        "idle_timeout"
    );
}

#[tokio::test(start_paused = true)]
async fn a_buffered_body_that_stalls_after_starting_still_times_out() {
    assert_eq!(
        read_completion_body(delayed_body(vec![275, 31]))
            .await
            .unwrap_err()
            .diagnostic_code(),
        "idle_timeout"
    );
}

struct DelayedEvents(VecDeque<(u64, RuntimeStreamEvent)>);

#[async_trait]
impl RuntimeEventStream for DelayedEvents {
    async fn next_event(&mut self) -> Result<Option<RuntimeStreamEvent>, RuntimeFailure> {
        let Some((seconds, event)) = self.0.pop_front() else {
            return std::future::pending().await;
        };

        tokio::time::sleep(Duration::from_secs(seconds)).await;
        Ok(Some(event))
    }
}

fn chunk(output: bool) -> RuntimeStreamEvent {
    RuntimeStreamEvent::Chunk(RuntimeStreamChunk::from_normalized_parts(
        json!({}),
        None,
        None,
        output,
        false,
    ))
}

fn events(rows: Vec<(u64, RuntimeStreamEvent)>, deadline: u64) -> ProgressStream {
    ProgressStream::new(
        Box::new(DelayedEvents(rows.into())),
        Instant::now() + Duration::from_secs(deadline),
    )
}

#[tokio::test(start_paused = true)]
async fn role_only_events_leave_time_for_long_prefill_then_generation_has_an_idle_limit() {
    let mut stream = events(
        vec![(0, chunk(false)), (275, chunk(true)), (31, chunk(true))],
        630,
    );
    assert_eq!(stream.next_event().await.unwrap(), Some(chunk(false)));
    assert_eq!(stream.next_event().await.unwrap(), Some(chunk(true)));
    assert_eq!(
        stream.next_event().await.unwrap_err().diagnostic_code(),
        "idle_timeout"
    );
    assert_eq!(stream.next_event().await.unwrap(), None);
}

#[tokio::test(start_paused = true)]
async fn the_request_deadline_bounds_prefill_even_with_role_only_heartbeats() {
    let mut stream = events(
        vec![(20, chunk(false)), (20, chunk(false)), (20, chunk(true))],
        50,
    );
    stream.next_event().await.unwrap();
    stream.next_event().await.unwrap();
    assert_eq!(
        stream.next_event().await.unwrap_err().diagnostic_code(),
        "deadline"
    );
}

#[tokio::test(start_paused = true)]
async fn consumer_backpressure_is_not_a_backend_idle_timeout() {
    let mut stream = events(vec![(0, chunk(true)), (0, chunk(true))], 630);
    stream.next_event().await.unwrap();
    tokio::time::advance(Duration::from_secs(60)).await;
    assert_eq!(stream.next_event().await.unwrap(), Some(chunk(true)));
}

#[tokio::test(start_paused = true)]
async fn even_ready_events_cannot_extend_an_expired_request_deadline() {
    let mut stream = events(vec![(0, chunk(true)), (0, chunk(true))], 50);
    stream.next_event().await.unwrap();
    tokio::time::advance(Duration::from_secs(60)).await;
    assert_eq!(
        stream.next_event().await.unwrap_err().diagnostic_code(),
        "deadline"
    );
}

#[tokio::test(start_paused = true)]
async fn generation_progress_does_not_extend_the_request_deadline() {
    let mut stream = events(
        vec![(0, chunk(true)), (20, chunk(true)), (20, chunk(true))],
        35,
    );
    stream.next_event().await.unwrap();
    stream.next_event().await.unwrap();
    assert_eq!(
        stream.next_event().await.unwrap_err().diagnostic_code(),
        "deadline"
    );
}
