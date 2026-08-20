use std::{env, net::SocketAddr};

use serde::Deserialize;
use thiserror::Error;
use validator::Validate;

const MAX_LUA_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Validate)]
pub struct GatewayConfig {
    #[serde(rename = "gateway_bind_address", default = "default_bind_address")]
    pub bind_address: SocketAddr,
    #[serde(
        rename = "gateway_generation_timeout_seconds",
        default = "default_generation_timeout_seconds"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub generation_timeout_seconds: u64,
    #[serde(
        rename = "gateway_lease_finalization_margin_seconds",
        default = "default_lease_finalization_margin_seconds"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub lease_finalization_margin_seconds: u64,
    #[serde(
        rename = "gateway_expired_lease_cleanup_grace_seconds",
        default = "default_expired_lease_cleanup_grace_seconds"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub expired_lease_cleanup_grace_seconds: u64,
    #[serde(
        rename = "gateway_prepaid_organization_concurrency_cap",
        default = "default_prepaid_organization_concurrency_cap"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub prepaid_organization_concurrency_cap: u64,
    #[serde(
        rename = "gateway_balance_per_concurrency_slot_nano_usd",
        default = "default_balance_per_concurrency_slot_nano_usd"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub balance_per_concurrency_slot_nano_usd: u64,
    #[serde(rename = "gateway_settlement_backlog_limit")]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub settlement_backlog_limit: u64,
    pub valkey_url: String,
    pub valkey_iam_cache_name: Option<String>,
    pub valkey_iam_region: Option<String>,
    pub valkey_iam_user: Option<String>,
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
        config.validate()?;
        config.validate_valkey_auth()?;
        config.sglang_api_key = config.sglang_api_key.filter(|value| !value.is_empty());
        Ok(config)
    }

    pub fn valkey_iam(&self) -> Option<ValkeyIamConfig> {
        match (
            &self.valkey_iam_cache_name,
            &self.valkey_iam_region,
            &self.valkey_iam_user,
        ) {
            (Some(cache_name), Some(region), Some(user)) => Some(ValkeyIamConfig {
                cache_name: cache_name.clone(),
                region: region.clone(),
                user: user.clone(),
            }),
            _ => None,
        }
    }

    fn validate_valkey_auth(&self) -> Result<(), ConfigError> {
        let values = [
            self.valkey_iam_cache_name.as_deref(),
            self.valkey_iam_region.as_deref(),
            self.valkey_iam_user.as_deref(),
        ];
        let configured = values.iter().filter(|value| value.is_some()).count();
        if configured != 0 && configured != values.len() {
            return Err(ConfigError::IncompleteValkeyIam);
        }
        if values.into_iter().flatten().any(str::is_empty) {
            return Err(ConfigError::EmptyValkeyIam);
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValkeyIamConfig {
    pub cache_name: String,
    pub region: String,
    pub user: String,
}

fn default_bind_address() -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], 3002))
}

fn default_generation_timeout_seconds() -> u64 {
    300
}

fn default_lease_finalization_margin_seconds() -> u64 {
    60
}

fn default_expired_lease_cleanup_grace_seconds() -> u64 {
    300
}

fn default_prepaid_organization_concurrency_cap() -> u64 {
    50
}

fn default_balance_per_concurrency_slot_nano_usd() -> u64 {
    1_000_000_000
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("gateway environment is invalid: {0}")]
    Environment(#[from] envy::Error),
    #[error("gateway configuration values are invalid: {0}")]
    Validation(#[from] validator::ValidationErrors),
    #[error(
        "VALKEY_IAM_CACHE_NAME, VALKEY_IAM_REGION and VALKEY_IAM_USER must be configured together"
    )]
    IncompleteValkeyIam,
    #[error("Valkey IAM configuration values must not be empty")]
    EmptyValkeyIam,
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
        let config = GatewayConfig::from_variables(variables(&[
            ("VALKEY_URL", "redis://127.0.0.1:6379"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "100000"),
        ]))
        .expect("minimal environment should parse");

        assert_eq!(config.bind_address, default_bind_address());
        assert_eq!(
            config.generation_timeout_seconds,
            default_generation_timeout_seconds()
        );
        assert_eq!(
            config.lease_finalization_margin_seconds,
            default_lease_finalization_margin_seconds()
        );
        assert_eq!(
            config.expired_lease_cleanup_grace_seconds,
            default_expired_lease_cleanup_grace_seconds()
        );
        assert_eq!(config.prepaid_organization_concurrency_cap, 50);
        assert_eq!(config.balance_per_concurrency_slot_nano_usd, 1_000_000_000);
        assert_eq!(config.settlement_backlog_limit, 100_000);
        assert_eq!(config.valkey_iam(), None);
        assert_eq!(config.sglang_api_key, None);
    }

    #[test]
    fn environment_parses_existing_variable_names() {
        let config = GatewayConfig::from_variables(variables(&[
            ("GATEWAY_BIND_ADDRESS", "0.0.0.0:8080"),
            ("GATEWAY_GENERATION_TIMEOUT_SECONDS", "120"),
            ("GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS", "30"),
            ("GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS", "240"),
            ("GATEWAY_PREPAID_ORGANIZATION_CONCURRENCY_CAP", "25"),
            ("GATEWAY_BALANCE_PER_CONCURRENCY_SLOT_NANO_USD", "500000000"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "50000"),
            ("VALKEY_URL", "rediss://valkey.internal:6379"),
            ("VALKEY_IAM_CACHE_NAME", "gradiated-prod"),
            ("VALKEY_IAM_REGION", "us-east-1"),
            ("VALKEY_IAM_USER", "gradiated-prod-gateway"),
            ("SGLANG_API_KEY", "runtime-secret"),
        ]))
        .expect("complete environment should parse");

        assert_eq!(config.bind_address, "0.0.0.0:8080".parse().unwrap());
        assert_eq!(config.generation_timeout_seconds, 120);
        assert_eq!(config.lease_finalization_margin_seconds, 30);
        assert_eq!(config.expired_lease_cleanup_grace_seconds, 240);
        assert_eq!(config.prepaid_organization_concurrency_cap, 25);
        assert_eq!(config.balance_per_concurrency_slot_nano_usd, 500_000_000);
        assert_eq!(config.settlement_backlog_limit, 50_000);
        assert_eq!(
            config.valkey_iam(),
            Some(ValkeyIamConfig {
                cache_name: "gradiated-prod".to_owned(),
                region: "us-east-1".to_owned(),
                user: "gradiated-prod-gateway".to_owned(),
            })
        );
        assert_eq!(config.sglang_api_key.as_deref(), Some("runtime-secret"));
    }

    #[test]
    fn environment_rejects_missing_or_invalid_required_values() {
        assert!(GatewayConfig::from_variables(variables(&[])).is_err());
        assert!(GatewayConfig::from_variables(variables(&[
            ("VALKEY_URL", "redis://127.0.0.1:6379"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "100000"),
            ("GATEWAY_GENERATION_TIMEOUT_SECONDS", "0"),
        ]))
        .is_err());
        assert!(GatewayConfig::from_variables(variables(&[
            ("VALKEY_URL", "redis://127.0.0.1:6379"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "0"),
        ]))
        .is_err());
        assert!(GatewayConfig::from_variables(variables(&[
            ("VALKEY_URL", "redis://127.0.0.1:6379"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "100000"),
            ("VALKEY_IAM_USER", "gradiated-prod-gateway"),
        ]))
        .is_err());
    }
}
