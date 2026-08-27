use std::time::Duration;

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
}

impl DependencyReadiness {
    pub fn new(serving_state: ValkeyServingState, metrics: GatewayMetrics) -> Self {
        Self {
            serving_state,
            metrics,
        }
    }
}

#[async_trait]
impl ReadinessCheck for DependencyReadiness {
    async fn is_ready(&self) -> bool {
        for dependency in ["valkey", "catalog"] {
            self.metrics.set_dependency_ready(dependency, false);
        }
        let checks = async {
            let (ping, models) =
                tokio::join!(self.serving_state.ping(), self.serving_state.models());
            self.metrics.set_dependency_ready("valkey", ping.is_ok());
            if models.is_err() {
                return false;
            }
            self.metrics.set_dependency_ready("catalog", true);
            if ping.is_err() {
                return false;
            }
            true
        };

        matches!(
            tokio::time::timeout(DEPENDENCY_TIMEOUT, checks).await,
            Ok(true)
        )
    }
}
