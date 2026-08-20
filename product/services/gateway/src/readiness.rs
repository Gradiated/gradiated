use std::time::Duration;

use async_trait::async_trait;

use crate::{GatewayMetrics, SglangClient, ValkeyServingState};

const DEPENDENCY_TIMEOUT: Duration = Duration::from_secs(2);

#[async_trait]
pub trait ReadinessCheck: Send + Sync {
    async fn is_ready(&self) -> bool;
}

pub struct DependencyReadiness {
    serving_state: ValkeyServingState,
    runtimes: SglangClient,
    metrics: GatewayMetrics,
}

impl DependencyReadiness {
    pub fn new(
        serving_state: ValkeyServingState,
        runtimes: SglangClient,
        metrics: GatewayMetrics,
    ) -> Self {
        Self {
            serving_state,
            runtimes,
            metrics,
        }
    }
}

#[async_trait]
impl ReadinessCheck for DependencyReadiness {
    async fn is_ready(&self) -> bool {
        for dependency in ["valkey", "catalog", "sglang"] {
            self.metrics.set_dependency_ready(dependency, false);
        }
        let checks = async {
            let (ping, models) =
                tokio::join!(self.serving_state.ping(), self.serving_state.models());
            self.metrics.set_dependency_ready("valkey", ping.is_ok());
            let Ok(models) = models else {
                return false;
            };
            self.metrics.set_dependency_ready("catalog", true);
            if ping.is_err() {
                return false;
            }

            let mut deployments = Vec::new();
            for model in &models {
                match model.first_available_deployment() {
                    Ok(Some(deployment)) => deployments.push(deployment.clone()),
                    Ok(None) => {}
                    Err(_) => {
                        self.metrics.set_dependency_ready("catalog", false);
                        return false;
                    }
                }
            }
            let runtimes_ready = self.runtimes.check_all(&deployments).await.is_ok();
            self.metrics.set_dependency_ready("sglang", runtimes_ready);
            runtimes_ready
        };

        matches!(
            tokio::time::timeout(DEPENDENCY_TIMEOUT, checks).await,
            Ok(true)
        )
    }
}
