use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

use async_trait::async_trait;

use crate::{cache::locked, serving_state::ServingStateError, GatewayMetrics, ValkeyServingState};

const DEPENDENCY_TIMEOUT: Duration = Duration::from_secs(2);

#[async_trait]
pub trait ReadinessCheck: Send + Sync {
    async fn is_ready(&self) -> bool;
}

pub struct DependencyReadiness {
    serving_state: ValkeyServingState,
    metrics: GatewayMetrics,
    valkey: DependencyState,
    postgres: DependencyState,
}

impl DependencyReadiness {
    pub fn new(serving_state: ValkeyServingState, metrics: GatewayMetrics) -> Self {
        Self {
            serving_state,
            metrics,
            valkey: DependencyState::new("valkey"),
            postgres: DependencyState::new("postgres"),
        }
    }
}

#[async_trait]
impl ReadinessCheck for DependencyReadiness {
    async fn is_ready(&self) -> bool {
        let (valkey, postgres) = tokio::join!(
            tokio::time::timeout(DEPENDENCY_TIMEOUT, self.serving_state.ping()),
            tokio::time::timeout(DEPENDENCY_TIMEOUT, self.serving_state.ping_database()),
        );

        let valkey_ready = self.valkey.observe(&self.metrics, readiness_error(&valkey));
        let postgres_ready = self
            .postgres
            .observe(&self.metrics, readiness_error(&postgres));

        valkey_ready && postgres_ready
    }
}

fn readiness_error<T>(
    result: &Result<Result<T, ServingStateError>, tokio::time::error::Elapsed>,
) -> Option<&'static str> {
    match result {
        Ok(Ok(_)) => None,
        Ok(Err(error)) => Some(error.diagnostic_code()),
        Err(_) => Some("timeout"),
    }
}

struct DependencyState {
    dependency: &'static str,
    last: Mutex<Option<Observation>>,
}

#[derive(Clone, Copy)]
struct Observation {
    ready: bool,
    since: Instant,
}

impl DependencyState {
    fn new(dependency: &'static str) -> Self {
        Self {
            dependency,
            last: Mutex::new(None),
        }
    }

    fn observe(&self, metrics: &GatewayMetrics, reason: Option<&'static str>) -> bool {
        let ready = reason.is_none();
        metrics.set_dependency_ready(self.dependency, ready);

        let now = Instant::now();
        let mut last = locked(&self.last);
        let previous = *last;
        if previous.is_some_and(|previous| previous.ready == ready) {
            return ready;
        }

        let dependency = self.dependency;
        if !ready {
            crate::diagnostics::limited_warn!(
                dependency,
                phase = "readiness",
                error_code = reason,
                "gateway dependency became unavailable"
            );
        } else if let Some(outage) = previous {
            tracing::info!(
                dependency,
                phase = "readiness",
                outage_ms = now.duration_since(outage.since).as_millis() as u64,
                "gateway dependency recovered"
            );
        }
        *last = Some(Observation { ready, since: now });

        ready
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn publishes_every_probe_but_logs_only_transitions() {
        let logs = crate::diagnostics::capture::Logs::default();
        let _guard = logs.start();
        let metrics = GatewayMetrics::new();
        let state = DependencyState::new("valkey");
        let published = |ready: u8| {
            metrics.encode().contains(&format!(
                r#"gradiated_gateway_dependency_ready{{dependency="valkey"}} {ready}"#
            ))
        };

        assert!(state.observe(&metrics, None));
        assert!(!state.observe(&metrics, Some("timeout")));
        assert!(!state.observe(&metrics, Some("timeout")));
        assert!(published(0));
        assert!(state.observe(&metrics, None));
        assert!(state.observe(&metrics, None));
        assert!(published(1));

        let events = logs.events();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0]["fields"]["error_code"], "timeout");
        assert_eq!(events[1]["level"], "INFO");
        assert!(events[1]["fields"]["outage_ms"].is_number());
    }

    #[tokio::test]
    async fn readiness_error_names_a_timeout_and_a_failed_dependency() {
        let elapsed = tokio::time::timeout(
            Duration::ZERO,
            std::future::pending::<Result<(), ServingStateError>>(),
        )
        .await;
        let failed: Result<Result<(), _>, tokio::time::error::Elapsed> =
            Ok(Err(ServingStateError::UnexpectedPingResponse));
        let ready: Result<Result<(), ServingStateError>, tokio::time::error::Elapsed> = Ok(Ok(()));

        assert_eq!(readiness_error(&elapsed), Some("timeout"));
        assert_eq!(readiness_error(&failed), Some("unexpected_ping"));
        assert_eq!(readiness_error(&ready), None);
    }
}
