use std::sync::Arc;

use axum::{extract::DefaultBodyLimit, http::StatusCode, routing::get, Json, Router};
use serde::Serialize;

use crate::readiness::ReadinessCheck;

#[derive(Clone)]
pub struct GatewayState {
    readiness: Arc<dyn ReadinessCheck>,
}

impl GatewayState {
    pub fn new(readiness: Arc<dyn ReadinessCheck>) -> Self {
        Self { readiness }
    }
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
}

pub fn router(state: GatewayState) -> Router {
    Router::new()
        .route("/health/live", get(live))
        .route("/health/ready", get(ready))
        .layer(DefaultBodyLimit::max(8_000_000))
        .with_state(state)
}

async fn live() -> Json<HealthResponse> {
    Json(HealthResponse { status: "live" })
}

async fn ready(
    axum::extract::State(state): axum::extract::State<GatewayState>,
) -> (StatusCode, Json<HealthResponse>) {
    if !state.readiness.is_ready().await {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(HealthResponse {
                status: "not_ready",
            }),
        )
    } else {
        (StatusCode::OK, Json(HealthResponse { status: "ready" }))
    }
}

#[cfg(test)]
mod tests {
    use async_trait::async_trait;
    use axum::{body::Body, http::Request};
    use tower::ServiceExt;

    use super::*;

    struct FixedReadiness(bool);

    #[async_trait]
    impl ReadinessCheck for FixedReadiness {
        async fn is_ready(&self) -> bool {
            self.0
        }
    }

    #[tokio::test]
    async fn live_and_ready_are_available_without_authentication() {
        let application = router(GatewayState::new(Arc::new(FixedReadiness(true))));

        for path in ["/health/live", "/health/ready"] {
            let response = application
                .clone()
                .oneshot(Request::builder().uri(path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
        }
    }

    #[tokio::test]
    async fn readiness_fails_closed_when_a_dependency_is_unhealthy() {
        let application = router(GatewayState::new(Arc::new(FixedReadiness(false))));

        let response = application
            .oneshot(
                Request::builder()
                    .uri("/health/ready")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
}
