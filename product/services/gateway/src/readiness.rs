use std::{
    sync::Mutex,
    time::{Duration, Instant},
};

use async_trait::async_trait;

use crate::{GatewayMetrics, ValkeyServingState};

const DEPENDENCY_TIMEOUT: Duration = Duration::from_secs(2);

#[async_trait]
pub trait ReadinessCheck: Send + Sync {
    async fn is_ready(&self) -> bool;
}

pub struct DependencyReadiness {
    serving_state: ValkeyServingState,
    metrics: GatewayMetrics,
    valkey_state: DependencyState,
    catalog_state: DependencyState,
}

impl DependencyReadiness {
    pub fn new(serving_state: ValkeyServingState, metrics: GatewayMetrics) -> Self {
        Self {
            serving_state,
            metrics,
            valkey_state: DependencyState::default(),
            catalog_state: DependencyState::default(),
        }
    }
}

#[async_trait]
impl ReadinessCheck for DependencyReadiness {
    async fn is_ready(&self) -> bool {
        let (ping, models) = tokio::join!(
            tokio::time::timeout(DEPENDENCY_TIMEOUT, self.serving_state.ping()),
            tokio::time::timeout(DEPENDENCY_TIMEOUT, self.serving_state.models()),
        );
        let valkey_reason = readiness_error(&ping);
        let catalog_reason = readiness_error(&models);
        self.metrics
            .set_dependency_ready("valkey", valkey_reason.is_none());
        self.metrics
            .set_dependency_ready("catalog", catalog_reason.is_none());
        self.valkey_state.record("valkey", valkey_reason);
        self.catalog_state.record("catalog", catalog_reason);
        valkey_reason.is_none() && catalog_reason.is_none()
    }
}

fn readiness_error<T>(
    result: &Result<
        Result<T, crate::serving_state::ServingStateError>,
        tokio::time::error::Elapsed,
    >,
) -> Option<&'static str> {
    match result {
        Ok(Ok(_)) => None,
        Ok(Err(error)) => Some(error.diagnostic_code()),
        Err(_) => Some("timeout"),
    }
}

#[derive(Default)]
struct DependencyState(Mutex<Option<(bool, Instant)>>);

impl DependencyState {
    fn record(&self, dependency: &'static str, reason: Option<&'static str>) {
        let now = Instant::now();
        let ready = reason.is_none();
        let mut state = self
            .0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        if state
            .as_ref()
            .is_some_and(|(previous, _)| *previous == ready)
        {
            return;
        }
        if !ready {
            crate::diagnostics::limited_warn!(
                dependency,
                phase = "readiness",
                error_code = reason,
                "gateway dependency became unavailable"
            );
        } else if let Some((false, since)) = *state {
            tracing::info!(
                dependency,
                phase = "readiness",
                outage_ms = now.duration_since(since).as_millis() as u64,
                "gateway dependency recovered"
            );
        }
        *state = Some((ready, now));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn logs_failure_and_recovery_but_not_repeated_probes() {
        let logs = crate::diagnostics::capture::Logs::default();
        let _guard = logs.start();
        let state = DependencyState::default();
        state.record("valkey", None);
        state.record("valkey", Some("timeout"));
        state.record("valkey", Some("timeout"));
        state.record("valkey", None);
        state.record("valkey", None);
        let events = logs.events();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0]["fields"]["error_code"], "timeout");
        assert_eq!(events[1]["level"], "INFO");
        assert!(events[1]["fields"]["outage_ms"].is_number());
    }
}
