use std::{
    sync::{Arc, Mutex},
    time::Duration,
};

use axum::{
    body::Body,
    extract::{Request, State},
    http::{header, HeaderMap, StatusCode},
    middleware::{self, Next},
    response::Response,
    routing::{post, MethodRouter},
    Router,
};
use chrono::{DateTime, TimeDelta, Utc};
use futures_util::{stream, StreamExt};
use serde_json::Value;
use tokio::task::JoinHandle;

use crate::{
    routing,
    runtime::{RuntimeStreamChunk, RuntimeStreamEvent},
    GatewayModelDeployment, InferenceRequest, ModelTokenizer, RuntimeProtocol, SglangClient,
};

pub(super) const CHAT: &str = "/v1/chat/completions";
pub(super) const SYSTEMONE: &str = "/v1/systemone";
pub(super) const DONE: &str = "data: [DONE]\n\n";

type Recorded = Arc<Mutex<Vec<RecordedRequest>>>;

#[derive(Clone, Debug)]
pub(super) struct RecordedRequest {
    pub(super) path: String,
    pub(super) headers: HeaderMap,
    pub(super) body: Value,
}

pub(super) struct MockRuntime {
    url: String,
    recorded: Recorded,
    task: JoinHandle<()>,
}

pub(super) struct MockRuntimeBuilder {
    router: Router,
}

impl MockRuntime {
    pub(super) fn builder() -> MockRuntimeBuilder {
        MockRuntimeBuilder {
            router: Router::new(),
        }
    }

    pub(super) fn url(&self) -> String {
        self.url.clone()
    }

    pub(super) fn deployment(&self) -> GatewayModelDeployment {
        deployment(self.url())
    }

    pub(super) fn renamed_deployment(&self) -> GatewayModelDeployment {
        let mut deployment = self.deployment();
        deployment.release.runtime_model_name = Some("runtime-model".to_owned());

        deployment
    }

    pub(super) fn system_one_deployment(&self) -> GatewayModelDeployment {
        let mut deployment = self.deployment();
        deployment.release.protocol = Some(RuntimeProtocol::SystemOne);

        deployment
    }

    pub(super) fn requests(&self) -> Vec<RecordedRequest> {
        self.recorded.lock().unwrap().clone()
    }
}

impl Drop for MockRuntime {
    fn drop(&mut self) {
        self.task.abort();
    }
}

impl MockRuntimeBuilder {
    pub(super) fn json(self, path: &str, status: StatusCode, body: Value) -> Self {
        self.route(
            path,
            post(move || async move { (status, axum::Json(body)) }),
        )
    }

    pub(super) fn sse(self, path: &str, frames: &[String]) -> Self {
        let body = frames.concat();

        self.route(
            path,
            post(move || async move { ([(header::CONTENT_TYPE, "text/event-stream")], body) }),
        )
    }

    /// Declares a longer body than it sends, then drops the connection.
    pub(super) fn truncated(
        self,
        path: &str,
        status: StatusCode,
        content_type: &'static str,
        sent: String,
    ) -> Self {
        self.route(
            path,
            post(move || async move { truncated_body(status, content_type, sent) }),
        )
    }

    pub(super) fn redirect(self, path: &str, to: &'static str) -> Self {
        self.route(
            path,
            post(move || async move { (StatusCode::TEMPORARY_REDIRECT, [(header::LOCATION, to)]) }),
        )
    }

    pub(super) fn route(self, path: &str, handler: MethodRouter) -> Self {
        Self {
            router: self.router.route(path, handler),
        }
    }

    pub(super) async fn start(self) -> MockRuntime {
        let recorded = Recorded::default();
        let application = self
            .router
            .layer(middleware::from_fn_with_state(recorded.clone(), record));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, application).await.unwrap();
        });

        MockRuntime {
            url,
            recorded,
            task,
        }
    }
}

async fn record(State(recorded): State<Recorded>, request: Request, next: Next) -> Response {
    let (parts, body) = request.into_parts();
    let bytes = axum::body::to_bytes(body, usize::MAX).await.unwrap();
    recorded.lock().unwrap().push(RecordedRequest {
        path: parts.uri.path().to_owned(),
        headers: parts.headers.clone(),
        body: serde_json::from_slice(&bytes).unwrap_or(Value::Null),
    });

    next.run(Request::from_parts(parts, Body::from(bytes)))
        .await
}

fn truncated_body(status: StatusCode, content_type: &'static str, sent: String) -> Response {
    let declared = sent.len() + 1_000;
    let sent = stream::iter([Ok(sent.into_bytes())]);
    let cut = stream::once(async {
        tokio::time::sleep(Duration::from_millis(50)).await;
        Err(std::io::Error::other("connection cut"))
    });

    Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, content_type)
        .header(header::CONTENT_LENGTH, declared)
        .body(Body::from_stream(sent.chain(cut)))
        .unwrap()
}

pub(super) fn expect_chunk(event: Option<RuntimeStreamEvent>) -> RuntimeStreamChunk {
    match event {
        Some(RuntimeStreamEvent::Chunk(chunk)) => chunk,
        other => panic!("expected a chunk, got {other:?}"),
    }
}

pub(super) fn data(payload: &Value) -> String {
    format!("data: {payload}\n\n")
}

pub(super) fn client() -> SglangClient {
    client_with_tokenizer(ModelTokenizer::new().unwrap())
}

pub(super) fn client_with_tokenizer(tokenizer: ModelTokenizer) -> SglangClient {
    SglangClient::with_tokenizer_and_tls(Some("runtime-secret".to_owned()), tokenizer, None)
        .unwrap()
}

pub(super) fn deployment(service_url: String) -> GatewayModelDeployment {
    GatewayModelDeployment {
        service_url,
        ..routing::fixtures::deployment(0)
    }
}

pub(super) fn chat_request() -> InferenceRequest {
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

pub(super) fn streaming_request() -> InferenceRequest {
    InferenceRequest::parse(
        br#"{
            "model":"model-a",
            "messages":[{"role":"user","content":"hello"}],
            "stream":true
        }"#,
    )
    .unwrap()
}

pub(super) fn decision_request() -> InferenceRequest {
    let body = serde_json::to_vec(&crate::systemone::fixtures::request_value()).unwrap();

    InferenceRequest::parse_kind(&body, crate::RequestKind::SystemOne).unwrap()
}

pub(super) fn deadline(seconds: i64) -> DateTime<Utc> {
    Utc::now() + TimeDelta::seconds(seconds)
}

/// The credential loader reading a stand-in for Secrets Manager at `endpoint`.
pub(super) fn credential_loader(endpoint: String) -> gradiated_credentials::CredentialLoader {
    let config = aws_sdk_secretsmanager::Config::builder()
        .behavior_version_latest()
        .region(aws_sdk_secretsmanager::config::Region::new("us-east-1"))
        .credentials_provider(aws_credential_types::Credentials::new(
            "test", "test", None, None, "test",
        ))
        .retry_config(
            aws_sdk_secretsmanager::config::retry::RetryConfig::standard().with_max_attempts(1),
        )
        .endpoint_url(endpoint)
        .build();

    gradiated_credentials::CredentialLoader::new(aws_sdk_secretsmanager::Client::from_conf(config))
}
