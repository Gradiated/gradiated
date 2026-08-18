use std::sync::Arc;

use thiserror::Error;

use crate::GatewayModelDeployment;

#[derive(Clone)]
pub struct SglangHealthClient {
    client: reqwest::Client,
    api_key: Option<Arc<str>>,
}

impl SglangHealthClient {
    pub fn new(api_key: Option<String>) -> Result<Self, RuntimeHealthError> {
        let client = reqwest::Client::builder().build()?;

        Ok(Self {
            client,
            api_key: api_key.map(Arc::from),
        })
    }

    pub async fn check_all(
        &self,
        deployments: &[GatewayModelDeployment],
    ) -> Result<(), RuntimeHealthError> {
        for deployment in deployments {
            let health_url = format!("{}/health", deployment.service_url.trim_end_matches('/'));
            let mut request = self.client.get(health_url);
            if let Some(api_key) = &self.api_key {
                request = request.bearer_auth(api_key);
            }
            let response = request.send().await?;
            if !response.status().is_success() {
                return Err(RuntimeHealthError::UnhealthyStatus(response.status()));
            }
        }
        Ok(())
    }
}

#[derive(Debug, Error)]
pub enum RuntimeHealthError {
    #[error("SGLang health request failed: {0}")]
    Request(#[from] reqwest::Error),
    #[error("SGLang health endpoint returned {0}")]
    UnhealthyStatus(reqwest::StatusCode),
}
