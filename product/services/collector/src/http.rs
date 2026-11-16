use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, Request, State},
    http::{
        header::{AUTHORIZATION, CONTENT_LENGTH, CONTENT_TYPE},
        HeaderMap, StatusCode,
    },
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde_json::json;
use tower::limit::ConcurrencyLimitLayer;

use crate::{
    batch,
    metrics::Metrics,
    record::GenerationContent,
    spool::{Spool, WriteError},
    tasks::TaskService,
};

#[derive(Clone)]
pub struct AppState {
    pub spool: Arc<Spool>,
    pub(crate) tasks: Option<Arc<TaskService>>,
    pub token: Arc<str>,
    pub metrics: Metrics,
    pub max_record_bytes: usize,
    /// Bytes of request bodies held at once, across every request.
    pub buffer: Arc<tokio::sync::Semaphore>,
    pub max_concurrent_requests: usize,
}

pub fn public_router(state: AppState) -> Router {
    Router::new()
        .route("/v1/contents", post(accept))
        .route_layer(middleware::from_fn_with_state(state.clone(), reserve))
        .route_layer(middleware::from_fn_with_state(state.clone(), authorize))
        .layer(DefaultBodyLimit::max(state.max_record_bytes))
        .layer(ConcurrencyLimitLayer::new(state.max_concurrent_requests))
        // Outside the concurrency limit, so requests waiting for a slot count as demand.
        .layer(middleware::from_fn_with_state(state.clone(), count))
        .with_state(state)
}

pub fn admin_router(state: AppState) -> Router {
    Router::new()
        .route("/health/live", get(|| async { StatusCode::OK }))
        .route("/health/ready", get(|| async { StatusCode::OK }))
        .route("/metrics", get(metrics))
        .with_state(state)
}

async fn metrics(State(state): State<AppState>) -> String {
    state.metrics.encode()
}

async fn authorize(State(state): State<AppState>, request: Request, next: Next) -> Response {
    if authorized(request.headers(), &state.token) {
        next.run(request).await
    } else {
        refuse(&state, StatusCode::UNAUTHORIZED, "unauthorized")
    }
}

async fn count(State(state): State<AppState>, request: Request, next: Next) -> Response {
    let _in_flight = state.metrics.request_started();

    next.run(request).await
}

/// Holds the body's bytes from the memory budget until the response is sent. A
/// sender that does not fit gets 503 at once and retries on another replica.
async fn reserve(State(state): State<AppState>, request: Request, next: Next) -> Response {
    let declared = request
        .headers()
        .get(CONTENT_LENGTH)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.parse::<usize>().ok());
    // A body that can never fit is refused for good, not as a retryable 503.
    if declared.is_some_and(|bytes| bytes > state.max_record_bytes) {
        return refuse(&state, StatusCode::PAYLOAD_TOO_LARGE, "too_large");
    }
    let bytes = declared
        .unwrap_or(state.max_record_bytes)
        .clamp(1, state.max_record_bytes);
    let Ok(_held) = u32::try_from(bytes)
        .ok()
        .and_then(|bytes| state.buffer.clone().try_acquire_many_owned(bytes).ok())
        .ok_or(())
    else {
        return refuse(&state, StatusCode::SERVICE_UNAVAILABLE, "busy");
    };

    next.run(request).await
}

async fn accept(
    State(state): State<AppState>,
    headers: HeaderMap,
    body: Result<Bytes, BytesRejection>,
) -> Response {
    let body = match body {
        Ok(body) => body,
        Err(rejection) if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => {
            return refuse(&state, StatusCode::PAYLOAD_TOO_LARGE, "too_large")
        }
        Err(_) => return refuse(&state, StatusCode::BAD_REQUEST, "unreadable_body"),
    };

    let ndjson = headers
        .get(CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| {
            value
                .split(';')
                .next()
                .unwrap_or("")
                .trim()
                .eq_ignore_ascii_case("application/x-ndjson")
        });
    if !ndjson {
        if let Err(error) = GenerationContent::parse(&body) {
            state.metrics.rejected("invalid");
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({ "error": "invalid_record", "message": error.to_string() })),
            )
                .into_response();
        }
    }

    let worker_state = state.clone();
    let result = tokio::task::spawn_blocking(move || {
        if ndjson {
            for line in body
                .split(|byte| *byte == b'\n')
                .filter(|line| !line.iter().all(u8::is_ascii_whitespace))
            {
                let normalized = match crate::relay::normalize(line) {
                    Ok(record) => record,
                    Err(_) => {
                        worker_state.metrics.rejected("invalid");
                        continue;
                    }
                };
                if normalized.len() > worker_state.max_record_bytes {
                    worker_state.metrics.rejected("too_large");
                    continue;
                }
                write(&worker_state, &normalized)?;
            }
            Ok(StatusCode::ACCEPTED)
        } else {
            write(&worker_state, &body)
        }
    })
    .await;

    match result {
        Ok(Ok(status)) => status.into_response(),
        Ok(Err(WriteError::Full)) => refuse(&state, StatusCode::SERVICE_UNAVAILABLE, "disk_full"),
        Ok(Err(WriteError::Closed)) => {
            refuse(&state, StatusCode::SERVICE_UNAVAILABLE, "shutting_down")
        }
        Ok(Err(WriteError::Io(error))) => {
            tracing::error!(%error, "batch write failed");
            refuse(&state, StatusCode::SERVICE_UNAVAILABLE, "write_failed")
        }
        Err(_) => refuse(&state, StatusCode::INTERNAL_SERVER_ERROR, "write_panicked"),
    }
}

fn write(state: &AppState, body: &[u8]) -> Result<StatusCode, WriteError> {
    let content = GenerationContent::parse(body).expect("record was validated before writing");
    let Some(key) = content.stream_key() else {
        state.metrics.skipped();
        return Ok(StatusCode::NO_CONTENT);
    };
    let frame = batch::compress(body).map_err(|error| WriteError::Io(error.to_string()))?;
    state.spool.append(&key, &frame, content.manifest_bytes())?;
    if let Some(task_service) = &state.tasks {
        if task_service
            .enqueue(
                content.workspace_id,
                content.task.as_deref().expect("task has a stream"),
            )
            .is_err()
        {
            state.metrics.task_registration_failed();
            tracing::warn!("task registration could not be queued; the uploader will retry");
        }
    }
    state.metrics.accepted();

    Ok(StatusCode::ACCEPTED)
}

fn refuse(state: &AppState, status: StatusCode, reason: &'static str) -> Response {
    state.metrics.rejected(reason);

    (status, Json(json!({ "error": reason }))).into_response()
}

fn authorized(headers: &HeaderMap, token: &str) -> bool {
    let Some(presented) = headers
        .get(AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
    else {
        return false;
    };

    presented.len() == token.len()
        && presented
            .bytes()
            .zip(token.bytes())
            .fold(0, |difference, (left, right)| difference | (left ^ right))
            == 0
}
