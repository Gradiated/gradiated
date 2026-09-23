use std::{
    net::SocketAddr,
    sync::{Arc, Mutex},
    time::Duration,
};

use axum::{
    body::{Body, Bytes},
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Router,
};
use futures_util::StreamExt;
use tokio::net::TcpListener;

pub(crate) const CUSTOMER_KEY: &str = "sk-ant-customer";

pub(crate) const JSON_REPLY: &str =
    r#"{"id":"msg_1","model":"claude-sonnet-5","usage":{"input_tokens":3}}"#;

#[derive(Clone, Copy)]
pub(crate) enum TestReply {
    Json,
    Stream,
    RateLimited,
    Redirect,
    Delayed(Duration),
    StallAfterFirstChunk,
}

#[derive(Clone)]
pub(crate) struct TestProvider {
    headers: Arc<Mutex<Option<HeaderMap>>>,
    body: Arc<Mutex<Option<Vec<u8>>>>,
    reply: TestReply,
}

impl TestProvider {
    pub(crate) fn headers(&self) -> Option<HeaderMap> {
        self.headers.lock().unwrap().clone()
    }

    pub(crate) fn body(&self) -> Option<Vec<u8>> {
        self.body.lock().unwrap().clone()
    }
}

async fn provider_handler(
    State(provider): State<TestProvider>,
    headers: HeaderMap,
    body: Bytes,
) -> Response {
    *provider.headers.lock().unwrap() = Some(headers);
    *provider.body.lock().unwrap() = Some(body.to_vec());

    match provider.reply {
        TestReply::Json => (
            StatusCode::OK,
            [("content-type", "application/json"), ("set-cookie", "a=1")],
            JSON_REPLY,
        )
            .into_response(),
        TestReply::Stream => {
            let frames = futures_util::stream::iter(vec![
                Ok::<_, std::io::Error>(Bytes::from_static(b"event: message_start\n\n")),
                Ok(Bytes::from_static(b"event: message_stop\n\n")),
            ]);
            (
                StatusCode::OK,
                [("content-type", "text/event-stream")],
                Body::from_stream(frames),
            )
                .into_response()
        }
        TestReply::RateLimited => (
            StatusCode::TOO_MANY_REQUESTS,
            [("content-type", "application/json"), ("retry-after", "7")],
            r#"{"type":"error","error":{"type":"rate_limit_error"}}"#,
        )
            .into_response(),
        TestReply::Redirect => (
            StatusCode::TEMPORARY_REDIRECT,
            [("location", "https://example.invalid/v1/messages")],
            "",
        )
            .into_response(),
        TestReply::Delayed(delay) => {
            tokio::time::sleep(delay).await;
            (StatusCode::OK, JSON_REPLY).into_response()
        }
        TestReply::StallAfterFirstChunk => {
            let frames = futures_util::stream::iter([Ok::<_, std::io::Error>(Bytes::from_static(
                b"event: message_start\n\n",
            ))])
            .chain(futures_util::stream::pending());
            (
                StatusCode::OK,
                [("content-type", "text/event-stream")],
                Body::from_stream(frames),
            )
                .into_response()
        }
    }
}

pub(crate) async fn start_provider(reply: TestReply) -> (SocketAddr, TestProvider) {
    let provider = TestProvider {
        headers: Arc::new(Mutex::new(None)),
        body: Arc::new(Mutex::new(None)),
        reply,
    };
    let router = Router::new()
        .route("/v1/messages", post(provider_handler))
        .with_state(provider.clone());
    let listener = TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], 0)))
        .await
        .unwrap();
    let address = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, router).await.unwrap();
    });

    (address, provider)
}
