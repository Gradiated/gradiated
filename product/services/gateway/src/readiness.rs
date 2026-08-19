use std::time::Duration;

use async_trait::async_trait;

use crate::{SglangClient, ValkeyServingState};

const DEPENDENCY_TIMEOUT: Duration = Duration::from_secs(2);

#[async_trait]
pub trait ReadinessCheck: Send + Sync {
    async fn is_ready(&self) -> bool;
}

pub struct DependencyReadiness {
    serving_state: ValkeyServingState,
    runtimes: SglangClient,
}

impl DependencyReadiness {
    pub fn new(serving_state: ValkeyServingState, runtimes: SglangClient) -> Self {
        Self {
            serving_state,
            runtimes,
        }
    }
}

#[async_trait]
impl ReadinessCheck for DependencyReadiness {
    async fn is_ready(&self) -> bool {
        let checks = async {
            let (ping, models) =
                tokio::join!(self.serving_state.ping(), self.serving_state.models());
            let Ok(models) = models else {
                return false;
            };
            if ping.is_err() || models.is_empty() {
                return false;
            }

            let mut deployments = Vec::new();
            for model in &models {
                match model.first_available_deployment() {
                    Ok(Some(deployment)) => deployments.push(deployment.clone()),
                    Ok(None) => {}
                    Err(_) => return false,
                }
            }
            self.runtimes.check_all(&deployments).await.is_ok()
        };

        matches!(
            tokio::time::timeout(DEPENDENCY_TIMEOUT, checks).await,
            Ok(true)
        )
    }
}
