use std::{env, net::SocketAddr, time::Duration};

use serde::Deserialize;
use thiserror::Error;
use validator::Validate;

const MAX_LUA_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Validate)]
pub struct GatewayConfig {
    #[serde(rename = "gateway_browser_origins")]
    pub browser_origins: Option<String>,
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
        rename = "gateway_organization_concurrency_cap",
        default = "default_organization_concurrency_cap"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub organization_concurrency_cap: u64,
    #[serde(
        rename = "gateway_balance_per_concurrency_slot_nano_usd",
        default = "default_balance_per_concurrency_slot_nano_usd"
    )]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub balance_per_concurrency_slot_nano_usd: u64,
    #[serde(rename = "gateway_settlement_backlog_limit")]
    #[validate(range(min = 1, max = MAX_LUA_SAFE_INTEGER))]
    pub settlement_backlog_limit: u64,

    #[serde(default = "default_anthropic_origin")]
    pub proxy_anthropic_origin: String,
    #[serde(default = "default_proxy_connect_timeout_seconds")]
    #[validate(range(min = 1, max = 120))]
    pub proxy_connect_timeout_seconds: u64,
    #[serde(default = "default_proxy_response_header_timeout_seconds")]
    #[validate(range(min = 1, max = 900))]
    pub proxy_response_header_timeout_seconds: u64,
    #[serde(default = "default_proxy_idle_timeout_seconds")]
    #[validate(range(min = 1, max = 900))]
    pub proxy_idle_timeout_seconds: u64,
    /// The total deadline starts before body buffering, so it bounds the whole relay.
    #[serde(default = "default_proxy_total_timeout_seconds")]
    #[validate(range(min = 1, max = 3600))]
    pub proxy_total_timeout_seconds: u64,
    #[serde(default = "default_proxy_max_request_bytes")]
    #[validate(range(min = 1024, max = 33_554_432))]
    pub proxy_max_request_bytes: u64,
    #[serde(default = "default_proxy_request_buffer_bytes")]
    #[validate(range(min = 1_048_576, max = MAX_LUA_SAFE_INTEGER))]
    pub proxy_request_buffer_bytes: u64,
    #[serde(default = "default_proxy_max_in_flight")]
    #[validate(range(min = 1, max = 1_000_000))]
    pub proxy_max_in_flight: u64,

    /// Published on every model in the catalog as a compliance claim. They are not
    /// per-deployment facts, so a runtime that retains prompts makes `provider_zdr`
    /// untrue for its models and the claim has to be revisited.
    #[serde(default = "default_provider_zdr")]
    pub provider_zdr: bool,
    #[serde(default)]
    pub provider_hipaa: bool,

    /// The authoritative store for identity and the model catalog.
    pub database_url: String,
    /// Extra certificate authorities to trust for the database connection. Amazon
    /// RDS roots its chain in its own authority, which no host trust store holds,
    /// so a managed instance cannot be verified without this.
    pub database_ca_bundle_path: Option<String>,
    /// How long Valkey may serve a cached identity or catalog record. It bounds the
    /// delay before a revoked key, a suspended organization, an archived workspace
    /// or a catalog change takes effect.
    #[serde(
        rename = "gateway_record_cache_ttl_seconds",
        default = "default_record_cache_ttl_seconds"
    )]
    #[validate(range(min = 1, max = 300))]
    pub record_cache_ttl_seconds: u64,

    pub valkey_url: String,
    pub valkey_iam_cache_name: Option<String>,
    pub valkey_iam_region: Option<String>,
    pub valkey_iam_user: Option<String>,

    pub sglang_api_key: Option<String>,
}

impl GatewayConfig {
    /// Shared fixture for tests that need a configuration value but do not
    /// exercise configuration itself.
    #[cfg(test)]
    pub(crate) fn for_tests() -> Self {
        Self {
            bind_address: "127.0.0.1:3002".parse().unwrap(),
            browser_origins: None,
            generation_timeout_seconds: default_generation_timeout_seconds(),
            lease_finalization_margin_seconds: default_lease_finalization_margin_seconds(),
            expired_lease_cleanup_grace_seconds: default_expired_lease_cleanup_grace_seconds(),
            organization_concurrency_cap: default_organization_concurrency_cap(),
            balance_per_concurrency_slot_nano_usd: default_balance_per_concurrency_slot_nano_usd(),
            settlement_backlog_limit: 100_000,
            provider_zdr: default_provider_zdr(),
            provider_hipaa: false,
            database_url: "postgres://127.0.0.1:5432/gradiated".to_owned(),
            database_ca_bundle_path: None,
            record_cache_ttl_seconds: default_record_cache_ttl_seconds(),
            proxy_anthropic_origin: default_anthropic_origin(),
            proxy_connect_timeout_seconds: default_proxy_connect_timeout_seconds(),
            proxy_response_header_timeout_seconds: default_proxy_response_header_timeout_seconds(),
            proxy_idle_timeout_seconds: default_proxy_idle_timeout_seconds(),
            proxy_total_timeout_seconds: default_proxy_total_timeout_seconds(),
            proxy_max_request_bytes: default_proxy_max_request_bytes(),
            proxy_request_buffer_bytes: default_proxy_request_buffer_bytes(),
            proxy_max_in_flight: default_proxy_max_in_flight(),
            valkey_url: "redis://127.0.0.1:6379".to_owned(),
            valkey_iam_cache_name: None,
            valkey_iam_region: None,
            valkey_iam_user: None,
            sglang_api_key: None,
        }
    }

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
        config.validate_proxy()?;

        config.browser_origins = config.browser_origins.filter(|value| !value.is_empty());
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

    pub fn browser_origins(&self) -> Vec<&str> {
        self.browser_origins
            .as_deref()
            .into_iter()
            .flat_map(|value| value.split(','))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .collect()
    }

    pub fn compliance(&self) -> crate::catalog::ProviderCompliance {
        crate::catalog::ProviderCompliance {
            zdr: self.provider_zdr,
            hipaa: self.provider_hipaa,
        }
    }

    pub fn record_cache_ttl(&self) -> Duration {
        Duration::from_secs(self.record_cache_ttl_seconds)
    }

    pub fn proxy_limits(&self) -> ProxyLimits {
        ProxyLimits {
            connect_timeout: Duration::from_secs(self.proxy_connect_timeout_seconds),
            response_header_timeout: Duration::from_secs(
                self.proxy_response_header_timeout_seconds,
            ),
            idle_timeout: Duration::from_secs(self.proxy_idle_timeout_seconds),
            total_timeout: Duration::from_secs(self.proxy_total_timeout_seconds),
            max_request_bytes: self.proxy_max_request_bytes,
            request_buffer_bytes: self.proxy_request_buffer_bytes,
            max_in_flight: self.proxy_max_in_flight,
        }
    }

    /// Relay origins are fixed configuration, never derived from a request.
    fn validate_proxy(&self) -> Result<(), ConfigError> {
        let origin = self.proxy_anthropic_origin.as_str();
        let Some(authority) = origin.strip_prefix("https://") else {
            return Err(ConfigError::InsecureProviderOrigin);
        };

        if authority.is_empty() || authority.contains('/') || authority.contains('?') {
            return Err(ConfigError::ProviderOriginHasPath);
        }

        if self.proxy_request_buffer_bytes < self.proxy_max_request_bytes {
            return Err(ConfigError::ProxyBufferBelowRequestCap);
        }

        Ok(())
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

/// Relay limits from the gateway contract. A single request can always fit the
/// process buffer, so a well-formed request never fails on the byte budget alone.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ProxyLimits {
    pub connect_timeout: Duration,
    pub response_header_timeout: Duration,
    pub idle_timeout: Duration,
    pub total_timeout: Duration,
    pub max_request_bytes: u64,
    pub request_buffer_bytes: u64,
    pub max_in_flight: u64,
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

fn default_organization_concurrency_cap() -> u64 {
    50
}

fn default_balance_per_concurrency_slot_nano_usd() -> u64 {
    1_000_000_000
}

fn default_provider_zdr() -> bool {
    true
}

fn default_record_cache_ttl_seconds() -> u64 {
    15
}

fn default_anthropic_origin() -> String {
    "https://api.anthropic.com".to_owned()
}

fn default_proxy_connect_timeout_seconds() -> u64 {
    10
}

fn default_proxy_response_header_timeout_seconds() -> u64 {
    120
}

fn default_proxy_idle_timeout_seconds() -> u64 {
    120
}

fn default_proxy_total_timeout_seconds() -> u64 {
    900
}

fn default_proxy_max_request_bytes() -> u64 {
    8 * 1024 * 1024
}

fn default_proxy_request_buffer_bytes() -> u64 {
    64 * 1024 * 1024
}

fn default_proxy_max_in_flight() -> u64 {
    2_000
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
    #[error("PROXY_ANTHROPIC_ORIGIN must use https")]
    InsecureProviderOrigin,
    #[error("PROXY_ANTHROPIC_ORIGIN must be an origin without a path or query")]
    ProviderOriginHasPath,
    #[error("PROXY_REQUEST_BUFFER_BYTES must be at least PROXY_MAX_REQUEST_BYTES")]
    ProxyBufferBelowRequestCap,
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
            ("DATABASE_URL", "postgres://127.0.0.1:5432/gradiated"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "100000"),
        ]))
        .expect("minimal environment should parse");

        assert_eq!(
            config.record_cache_ttl_seconds,
            default_record_cache_ttl_seconds()
        );

        assert_eq!(config.bind_address, default_bind_address());
        assert!(config.browser_origins().is_empty());
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
        assert_eq!(config.organization_concurrency_cap, 50);
        assert_eq!(config.balance_per_concurrency_slot_nano_usd, 1_000_000_000);
        assert_eq!(config.settlement_backlog_limit, 100_000);
        assert_eq!(config.valkey_iam(), None);
        assert_eq!(config.sglang_api_key, None);
    }

    #[test]
    fn environment_parses_existing_variable_names() {
        let config = GatewayConfig::from_variables(variables(&[
            ("GATEWAY_BIND_ADDRESS", "0.0.0.0:8080"),
            (
                "GATEWAY_BROWSER_ORIGINS",
                "https://gradiated.com, https://www.gradiated.com",
            ),
            ("GATEWAY_GENERATION_TIMEOUT_SECONDS", "120"),
            ("GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS", "30"),
            ("GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS", "240"),
            ("GATEWAY_ORGANIZATION_CONCURRENCY_CAP", "25"),
            ("GATEWAY_BALANCE_PER_CONCURRENCY_SLOT_NANO_USD", "500000000"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "50000"),
            ("GATEWAY_RECORD_CACHE_TTL_SECONDS", "30"),
            ("DATABASE_URL", "postgres://control.internal:5432/gradiated"),
            ("VALKEY_URL", "rediss://valkey.internal:6379"),
            ("VALKEY_IAM_CACHE_NAME", "gradiated-prod"),
            ("VALKEY_IAM_REGION", "us-east-1"),
            ("VALKEY_IAM_USER", "gradiated-prod-gateway"),
            ("SGLANG_API_KEY", "runtime-secret"),
        ]))
        .expect("complete environment should parse");

        assert_eq!(config.bind_address, "0.0.0.0:8080".parse().unwrap());
        assert_eq!(
            config.browser_origins(),
            vec!["https://gradiated.com", "https://www.gradiated.com"]
        );
        assert_eq!(config.generation_timeout_seconds, 120);
        assert_eq!(config.lease_finalization_margin_seconds, 30);
        assert_eq!(config.expired_lease_cleanup_grace_seconds, 240);
        assert_eq!(config.organization_concurrency_cap, 25);
        assert_eq!(config.balance_per_concurrency_slot_nano_usd, 500_000_000);
        assert_eq!(config.settlement_backlog_limit, 50_000);
        assert_eq!(config.record_cache_ttl_seconds, 30);
        assert_eq!(
            config.database_url,
            "postgres://control.internal:5432/gradiated"
        );
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
