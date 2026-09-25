use std::sync::Arc;

use axum::{
    body::Bytes,
    extract::{rejection::BytesRejection, DefaultBodyLimit, Request, State},
    http::{header::AUTHORIZATION, HeaderMap, StatusCode},
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
};

#[derive(Clone)]
pub struct AppState {
    pub spool: Arc<Spool>,
    pub token: Arc<str>,
    pub metrics: Metrics,
    pub max_record_bytes: usize,
    pub max_concurrent_requests: usize,
}

pub fn public_router(state: AppState) -> Router {
    Router::new()
        .route("/v1/contents", post(accept))
        .route_layer(middleware::from_fn_with_state(state.clone(), authorize))
        .layer(DefaultBodyLimit::max(state.max_record_bytes))
        .layer(ConcurrencyLimitLayer::new(state.max_concurrent_requests))
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

async fn accept(State(state): State<AppState>, body: Result<Bytes, BytesRejection>) -> Response {
    let body = match body {
        Ok(body) => body,
        Err(rejection) if rejection.status() == StatusCode::PAYLOAD_TOO_LARGE => {
            return refuse(&state, StatusCode::PAYLOAD_TOO_LARGE, "too_large")
        }
        Err(_) => return refuse(&state, StatusCode::BAD_REQUEST, "unreadable_body"),
    };

    let content = match GenerationContent::parse(&body) {
        Ok(content) => content,
        Err(error) => {
            state.metrics.rejected("invalid");
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({ "error": "invalid_record", "message": error.to_string() })),
            )
                .into_response();
        }
    };

    let Some(key) = content.stream_key() else {
        state.metrics.skipped();
        return StatusCode::NO_CONTENT.into_response();
    };
    let spool = state.spool.clone();
    let written = tokio::task::spawn_blocking(move || {
        let frame = batch::compress(&body).map_err(|error| WriteError::Io(error.to_string()))?;
        spool.append(&key, &frame)
    })
    .await;

    match written {
        Ok(Ok(())) => {
            state.metrics.accepted();
            StatusCode::ACCEPTED.into_response()
        }
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
