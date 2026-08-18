use std::{env, net::SocketAddr};

use serde::Deserialize;
use thiserror::Error;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
pub struct GatewayConfig {
    #[serde(rename = "gateway_bind_address", default = "default_bind_address")]
    pub bind_address: SocketAddr,
    #[serde(
        rename = "gateway_generation_timeout_seconds",
        default = "default_generation_timeout_seconds"
    )]
    pub generation_timeout_seconds: u64,
    pub valkey_url: String,
    pub sglang_api_key: Option<String>,
}

impl GatewayConfig {
    pub fn from_environment() -> Result<Self, ConfigError> {
        Self::from_variables(env::vars())
    }

    fn from_variables<I>(variables: I) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = (String, String)>,
    {
        let mut config: Self = envy::from_iter(variables)?;
        if config.generation_timeout_seconds == 0 {
            return Err(ConfigError::ZeroGenerationTimeout);
        }
        config.sglang_api_key = config.sglang_api_key.filter(|value| !value.is_empty());
        Ok(config)
    }
}

fn default_bind_address() -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], 3002))
}

fn default_generation_timeout_seconds() -> u64 {
    300
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("gateway environment is invalid: {0}")]
    Environment(#[from] envy::Error),
    #[error("GATEWAY_GENERATION_TIMEOUT_SECONDS must be greater than zero")]
    ZeroGenerationTimeout,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn variables(values: &[(&str, &str)]) -> Vec<(String, String)> {
        values
            .iter()
            .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()))
            .collect()
    }

    #[test]
    fn environment_uses_typed_defaults() {
        let config =
            GatewayConfig::from_variables(variables(&[("VALKEY_URL", "redis://127.0.0.1:6379")]))
                .expect("minimal environment should parse");

        assert_eq!(config.bind_address, default_bind_address());
        assert_eq!(
            config.generation_timeout_seconds,
            default_generation_timeout_seconds()
        );
        assert_eq!(config.sglang_api_key, None);
    }

    #[test]
    fn environment_parses_existing_variable_names() {
        let config = GatewayConfig::from_variables(variables(&[
            ("GATEWAY_BIND_ADDRESS", "0.0.0.0:8080"),
            ("GATEWAY_GENERATION_TIMEOUT_SECONDS", "120"),
            ("VALKEY_URL", "rediss://valkey.internal:6379"),
            ("SGLANG_API_KEY", "runtime-secret"),
        ]))
        .expect("complete environment should parse");

        assert_eq!(config.bind_address, "0.0.0.0:8080".parse().unwrap());
        assert_eq!(config.generation_timeout_seconds, 120);
        assert_eq!(config.sglang_api_key.as_deref(), Some("runtime-secret"));
    }

    #[test]
    fn environment_rejects_missing_or_invalid_required_values() {
        assert!(GatewayConfig::from_variables(variables(&[])).is_err());
        assert!(GatewayConfig::from_variables(variables(&[
            ("VALKEY_URL", "redis://127.0.0.1:6379"),
            ("GATEWAY_GENERATION_TIMEOUT_SECONDS", "0"),
        ]))
        .is_err());
    }
}
