use std::{env, fmt, net::SocketAddr, time::Duration};

use axum::http::Uri;
use serde::Deserialize;
use thiserror::Error;
use validator::Validate;

use crate::{catalog::ProviderCompliance, model::MAX_SAFE_INTEGER};

/// The official SDKs time out after 600 seconds; the drain windows in the
/// deployment are sized from this ceiling.
const MAX_REQUEST_SECONDS: u64 = 630;

#[cfg(test)]
const MINIMAL_ENVIRONMENT: [(&str, &str); 3] = [
    ("VALKEY_URL", "redis://127.0.0.1:6379"),
    ("DATABASE_URL", "postgres://127.0.0.1:5432/gradiated"),
    ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "100000"),
];

#[derive(Clone, Eq, PartialEq)]
pub struct GatewayConfig {
    pub bind_address: SocketAddr,
    browser_origins: Vec<String>,

    pub generation_timeout_seconds: u64,
    pub lease_finalization_margin_seconds: u64,
    pub expired_lease_cleanup_grace_seconds: u64,
    pub organization_concurrency_cap: u64,
    pub balance_per_concurrency_slot_nano_usd: u64,
    pub settlement_backlog_limit: u64,

    pub proxy_anthropic_origin: String,
    proxy_limits: ProxyLimits,
    compliance: ProviderCompliance,

    pub database_url: String,
    pub database_ca_bundle_path: Option<String>,
    record_cache_ttl: Duration,

    pub valkey_url: String,
    valkey_iam: Option<ValkeyIamConfig>,

    pub sglang_api_key: Option<String>,
}

impl GatewayConfig {
    #[cfg(test)]
    pub(crate) fn for_tests() -> Self {
        Self::from_variables(
            MINIMAL_ENVIRONMENT.map(|(name, value)| (name.to_owned(), value.to_owned())),
        )
        .expect("the test environment is valid")
    }

    pub fn from_environment() -> Result<Self, ConfigError> {
        Self::from_variables(env::vars())
    }

    fn from_variables<I>(variables: I) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = (String, String)>,
    {
        let environment: Environment = envy::from_iter(variables)?;
        environment.validate()?;

        Self::try_from(environment)
    }

    pub fn valkey_iam(&self) -> Option<ValkeyIamConfig> {
        self.valkey_iam.clone()
    }

    pub fn browser_origins(&self) -> Vec<&str> {
        self.browser_origins.iter().map(String::as_str).collect()
    }

    pub fn compliance(&self) -> ProviderCompliance {
        self.compliance
    }

    pub fn record_cache_ttl(&self) -> Duration {
        self.record_cache_ttl
    }

    pub fn proxy_limits(&self) -> ProxyLimits {
        self.proxy_limits
    }
}

/// Connection URLs can embed passwords, so they are redacted with the API key.
impl fmt::Debug for GatewayConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        const REDACTED: &str = "<redacted>";

        formatter
            .debug_struct("GatewayConfig")
            .field("bind_address", &self.bind_address)
            .field("browser_origins", &self.browser_origins)
            .field(
                "generation_timeout_seconds",
                &self.generation_timeout_seconds,
            )
            .field(
                "lease_finalization_margin_seconds",
                &self.lease_finalization_margin_seconds,
            )
            .field(
                "expired_lease_cleanup_grace_seconds",
                &self.expired_lease_cleanup_grace_seconds,
            )
            .field(
                "organization_concurrency_cap",
                &self.organization_concurrency_cap,
            )
            .field(
                "balance_per_concurrency_slot_nano_usd",
                &self.balance_per_concurrency_slot_nano_usd,
            )
            .field("settlement_backlog_limit", &self.settlement_backlog_limit)
            .field("proxy_anthropic_origin", &self.proxy_anthropic_origin)
            .field("proxy_limits", &self.proxy_limits)
            .field("compliance", &self.compliance)
            .field("database_url", &REDACTED)
            .field("database_ca_bundle_path", &self.database_ca_bundle_path)
            .field("record_cache_ttl", &self.record_cache_ttl)
            .field("valkey_url", &REDACTED)
            .field("valkey_iam", &self.valkey_iam)
            .field(
                "sglang_api_key",
                &self.sglang_api_key.as_ref().map(|_| REDACTED),
            )
            .finish()
    }
}

impl TryFrom<Environment> for GatewayConfig {
    type Error = ConfigError;

    fn try_from(environment: Environment) -> Result<Self, ConfigError> {
        require_bare_https_origin(&environment.proxy_anthropic_origin)?;

        let proxy_limits = environment.proxy_limits()?;
        let valkey_iam = environment.valkey_iam()?;
        let browser_origins = environment
            .browser_origins
            .as_deref()
            .into_iter()
            .flat_map(|value| value.split(','))
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(str::to_owned)
            .collect();

        Ok(Self {
            bind_address: environment.bind_address,
            browser_origins,
            generation_timeout_seconds: environment.generation_timeout_seconds,
            lease_finalization_margin_seconds: environment.lease_finalization_margin_seconds,
            expired_lease_cleanup_grace_seconds: environment.expired_lease_cleanup_grace_seconds,
            organization_concurrency_cap: environment.organization_concurrency_cap,
            balance_per_concurrency_slot_nano_usd: environment
                .balance_per_concurrency_slot_nano_usd,
            settlement_backlog_limit: environment.settlement_backlog_limit,
            proxy_anthropic_origin: environment.proxy_anthropic_origin,
            proxy_limits,
            compliance: ProviderCompliance {
                zdr: environment.provider_zdr,
                hipaa: environment.provider_hipaa,
            },
            database_url: environment.database_url,
            database_ca_bundle_path: environment.database_ca_bundle_path,
            record_cache_ttl: Duration::from_secs(environment.record_cache_ttl_seconds),
            valkey_url: environment.valkey_url,
            valkey_iam,
            sglang_api_key: environment.sglang_api_key.filter(|value| !value.is_empty()),
        })
    }
}

#[derive(Deserialize, Validate)]
struct Environment {
    #[serde(rename = "gateway_browser_origins")]
    browser_origins: Option<String>,
    #[serde(rename = "gateway_bind_address", default = "default_bind_address")]
    bind_address: SocketAddr,

    #[serde(
        rename = "gateway_generation_timeout_seconds",
        default = "default_generation_timeout_seconds"
    )]
    #[validate(range(min = 1, max = MAX_REQUEST_SECONDS))]
    generation_timeout_seconds: u64,
    #[serde(
        rename = "gateway_lease_finalization_margin_seconds",
        default = "default_lease_finalization_margin_seconds"
    )]
    #[validate(range(min = 1, max = 3_600))]
    lease_finalization_margin_seconds: u64,
    #[serde(
        rename = "gateway_expired_lease_cleanup_grace_seconds",
        default = "default_expired_lease_cleanup_grace_seconds"
    )]
    #[validate(range(min = 1, max = 86_400))]
    expired_lease_cleanup_grace_seconds: u64,
    #[serde(
        rename = "gateway_organization_concurrency_cap",
        default = "default_organization_concurrency_cap"
    )]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    organization_concurrency_cap: u64,
    #[serde(
        rename = "gateway_balance_per_concurrency_slot_nano_usd",
        default = "default_balance_per_concurrency_slot_nano_usd"
    )]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    balance_per_concurrency_slot_nano_usd: u64,
    #[serde(rename = "gateway_settlement_backlog_limit")]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    settlement_backlog_limit: u64,

    #[serde(default = "default_anthropic_origin")]
    proxy_anthropic_origin: String,
    #[serde(default = "default_proxy_connect_timeout_seconds")]
    #[validate(range(min = 1, max = 120))]
    proxy_connect_timeout_seconds: u64,
    #[serde(default = "default_proxy_response_header_timeout_seconds")]
    #[validate(range(min = 1, max = MAX_REQUEST_SECONDS))]
    proxy_response_header_timeout_seconds: u64,
    #[serde(default = "default_proxy_idle_timeout_seconds")]
    #[validate(range(min = 1, max = MAX_REQUEST_SECONDS))]
    proxy_idle_timeout_seconds: u64,
    /// The total deadline starts before body buffering, so it bounds the whole relay.
    #[serde(default = "default_proxy_total_timeout_seconds")]
    #[validate(range(min = 1, max = MAX_REQUEST_SECONDS))]
    proxy_total_timeout_seconds: u64,
    #[serde(default = "default_proxy_max_request_bytes")]
    #[validate(range(min = 1024, max = 33_554_432))]
    proxy_max_request_bytes: u64,
    #[serde(default = "default_proxy_request_buffer_bytes")]
    #[validate(range(min = 1_048_576, max = MAX_SAFE_INTEGER))]
    proxy_request_buffer_bytes: u64,
    #[serde(default = "default_proxy_max_in_flight")]
    #[validate(range(min = 1, max = 1_000_000))]
    proxy_max_in_flight: u64,

    /// A runtime that retains prompts makes `provider_zdr` untrue for every model.
    #[serde(default = "default_provider_zdr")]
    provider_zdr: bool,
    #[serde(default)]
    provider_hipaa: bool,

    database_url: String,
    /// Extra certificate authorities to trust for the database connection. Amazon
    /// RDS roots its chain in its own authority, which no host trust store holds,
    /// so a managed instance cannot be verified without this.
    database_ca_bundle_path: Option<String>,
    /// How long Valkey may serve a cached identity or catalog record. It bounds the
    /// delay before a revoked key, a suspended organization, an archived workspace
    /// or a catalog change takes effect.
    #[serde(
        rename = "gateway_record_cache_ttl_seconds",
        default = "default_record_cache_ttl_seconds"
    )]
    #[validate(range(min = 1, max = 300))]
    record_cache_ttl_seconds: u64,

    valkey_url: String,
    valkey_iam_cache_name: Option<String>,
    valkey_iam_region: Option<String>,
    valkey_iam_user: Option<String>,

    sglang_api_key: Option<String>,
}

impl Environment {
    fn proxy_limits(&self) -> Result<ProxyLimits, ConfigError> {
        if self.proxy_request_buffer_bytes < self.proxy_max_request_bytes {
            return Err(ConfigError::ProxyBufferBelowRequestCap);
        }

        Ok(ProxyLimits {
            connect_timeout: Duration::from_secs(self.proxy_connect_timeout_seconds),
            response_header_timeout: Duration::from_secs(
                self.proxy_response_header_timeout_seconds,
            ),
            idle_timeout: Duration::from_secs(self.proxy_idle_timeout_seconds),
            total_timeout: Duration::from_secs(self.proxy_total_timeout_seconds),
            max_request_bytes: self.proxy_max_request_bytes,
            request_buffer_bytes: self.proxy_request_buffer_bytes,
            max_in_flight: self.proxy_max_in_flight,
        })
    }

    fn valkey_iam(&self) -> Result<Option<ValkeyIamConfig>, ConfigError> {
        let (cache_name, region, user) = match (
            &self.valkey_iam_cache_name,
            &self.valkey_iam_region,
            &self.valkey_iam_user,
        ) {
            (None, None, None) => return Ok(None),
            (Some(cache_name), Some(region), Some(user)) => (cache_name, region, user),
            _ => return Err(ConfigError::IncompleteValkeyIam),
        };

        if [cache_name, region, user]
            .iter()
            .any(|value| value.is_empty())
        {
            return Err(ConfigError::EmptyValkeyIam);
        }

        Ok(Some(ValkeyIamConfig {
            cache_name: cache_name.clone(),
            region: region.clone(),
            user: user.clone(),
        }))
    }
}

fn require_bare_https_origin(origin: &str) -> Result<(), ConfigError> {
    let uri = origin
        .parse::<Uri>()
        .map_err(|_| ConfigError::ProviderOriginNotBare)?;

    if uri.scheme_str() != Some("https") {
        return Err(ConfigError::InsecureProviderOrigin);
    }

    let Some(authority) = uri
        .authority()
        .filter(|authority| !authority.as_str().contains('@'))
    else {
        return Err(ConfigError::ProviderOriginNotBare);
    };

    if origin != format!("https://{authority}") {
        return Err(ConfigError::ProviderOriginNotBare);
    }

    Ok(())
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
    MAX_REQUEST_SECONDS
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
    MAX_REQUEST_SECONDS
}

fn default_proxy_idle_timeout_seconds() -> u64 {
    MAX_REQUEST_SECONDS
}

fn default_proxy_total_timeout_seconds() -> u64 {
    MAX_REQUEST_SECONDS
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
    #[error("PROXY_ANTHROPIC_ORIGIN must be https://host[:port] with no userinfo, path, query or fragment")]
    ProviderOriginNotBare,
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

    fn minimal_with(overrides: &[(&str, &str)]) -> Result<GatewayConfig, ConfigError> {
        let mut values = variables(&MINIMAL_ENVIRONMENT);
        values.retain(|(name, _)| !overrides.iter().any(|(changed, _)| name == changed));
        values.extend(variables(overrides));

        GatewayConfig::from_variables(values)
    }

    #[test]
    fn environment_uses_typed_defaults() {
        let config = minimal_with(&[]).expect("minimal environment should parse");

        assert_eq!(
            config.record_cache_ttl(),
            Duration::from_secs(default_record_cache_ttl_seconds())
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
        assert_eq!(config.database_ca_bundle_path, None);
        assert_eq!(config.proxy_anthropic_origin, "https://api.anthropic.com");
        assert_eq!(
            config.proxy_limits(),
            ProxyLimits {
                connect_timeout: Duration::from_secs(10),
                response_header_timeout: Duration::from_secs(630),
                idle_timeout: Duration::from_secs(630),
                total_timeout: Duration::from_secs(630),
                max_request_bytes: 8 * 1024 * 1024,
                request_buffer_bytes: 64 * 1024 * 1024,
                max_in_flight: 2_000,
            }
        );
        assert!(config.compliance().zdr);
        assert!(!config.compliance().hipaa);
    }

    #[test]
    fn environment_parses_existing_variable_names() {
        let config = GatewayConfig::from_variables(variables(&[
            ("GATEWAY_BIND_ADDRESS", "0.0.0.0:8080"),
            (
                "GATEWAY_BROWSER_ORIGINS",
                "https://gradiated.com, https://www.gradiated.com,",
            ),
            ("GATEWAY_GENERATION_TIMEOUT_SECONDS", "120"),
            ("GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS", "30"),
            ("GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS", "240"),
            ("GATEWAY_ORGANIZATION_CONCURRENCY_CAP", "25"),
            ("GATEWAY_BALANCE_PER_CONCURRENCY_SLOT_NANO_USD", "500000000"),
            ("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "50000"),
            ("GATEWAY_RECORD_CACHE_TTL_SECONDS", "30"),
            ("DATABASE_URL", "postgres://control.internal:5432/gradiated"),
            ("DATABASE_CA_BUNDLE_PATH", "/etc/ssl/rds-global-bundle.pem"),
            ("VALKEY_URL", "rediss://valkey.internal:6379"),
            ("VALKEY_IAM_CACHE_NAME", "gradiated-prod"),
            ("VALKEY_IAM_REGION", "us-east-1"),
            ("VALKEY_IAM_USER", "gradiated-prod-gateway"),
            ("SGLANG_API_KEY", "runtime-secret"),
            ("PROVIDER_ZDR", "false"),
            ("PROVIDER_HIPAA", "true"),
            ("PROXY_ANTHROPIC_ORIGIN", "https://anthropic.internal:8443"),
            ("PROXY_CONNECT_TIMEOUT_SECONDS", "5"),
            ("PROXY_RESPONSE_HEADER_TIMEOUT_SECONDS", "60"),
            ("PROXY_IDLE_TIMEOUT_SECONDS", "90"),
            ("PROXY_TOTAL_TIMEOUT_SECONDS", "240"),
            ("PROXY_MAX_REQUEST_BYTES", "2048"),
            ("PROXY_REQUEST_BUFFER_BYTES", "2097152"),
            ("PROXY_MAX_IN_FLIGHT", "10"),
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
        assert_eq!(config.record_cache_ttl(), Duration::from_secs(30));
        assert_eq!(
            config.database_url,
            "postgres://control.internal:5432/gradiated"
        );
        assert_eq!(
            config.database_ca_bundle_path.as_deref(),
            Some("/etc/ssl/rds-global-bundle.pem")
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
        assert!(!config.compliance().zdr);
        assert!(config.compliance().hipaa);
        assert_eq!(
            config.proxy_anthropic_origin,
            "https://anthropic.internal:8443"
        );
        assert_eq!(
            config.proxy_limits(),
            ProxyLimits {
                connect_timeout: Duration::from_secs(5),
                response_header_timeout: Duration::from_secs(60),
                idle_timeout: Duration::from_secs(90),
                total_timeout: Duration::from_secs(240),
                max_request_bytes: 2_048,
                request_buffer_bytes: 2_097_152,
                max_in_flight: 10,
            }
        );
    }

    #[test]
    fn debug_output_redacts_credentials() {
        let config = minimal_with(&[
            (
                "DATABASE_URL",
                "postgres://gateway:db-secret@db.internal/gradiated",
            ),
            (
                "VALKEY_URL",
                "rediss://default:valkey-secret@valkey.internal:6379",
            ),
            ("SGLANG_API_KEY", "runtime-secret"),
        ])
        .expect("the environment parses");
        let debug = format!("{config:?}");

        for secret in ["db-secret", "valkey-secret", "runtime-secret"] {
            assert!(!debug.contains(secret), "{secret} leaked into {debug}");
        }
    }

    #[test]
    fn request_deadlines_cannot_exceed_the_sdk_timeout_and_margin() {
        for key in [
            "GATEWAY_GENERATION_TIMEOUT_SECONDS",
            "PROXY_TOTAL_TIMEOUT_SECONDS",
        ] {
            assert!(minimal_with(&[(key, "630")]).is_ok());
            assert!(minimal_with(&[(key, "631")]).is_err());
        }
    }

    #[test]
    fn an_empty_runtime_key_means_none() {
        let config = minimal_with(&[("SGLANG_API_KEY", "")]).expect("an empty key parses");

        assert_eq!(config.sglang_api_key, None);
    }

    #[test]
    fn a_missing_required_variable_is_an_environment_error() {
        for (missing, _) in MINIMAL_ENVIRONMENT {
            let values = MINIMAL_ENVIRONMENT
                .into_iter()
                .filter(|(name, _)| *name != missing);

            assert!(
                matches!(
                    GatewayConfig::from_variables(variables(&values.collect::<Vec<_>>())),
                    Err(ConfigError::Environment(_))
                ),
                "{missing}"
            );
        }
    }

    #[test]
    fn each_invalid_value_is_rejected_by_its_own_rule() {
        type Expected = fn(&ConfigError) -> bool;
        let validation: Expected = |error| matches!(error, ConfigError::Validation(_));
        let incomplete_iam: Expected = |error| matches!(error, ConfigError::IncompleteValkeyIam);
        let empty_iam: Expected = |error| matches!(error, ConfigError::EmptyValkeyIam);
        let insecure: Expected = |error| matches!(error, ConfigError::InsecureProviderOrigin);
        let not_bare: Expected = |error| matches!(error, ConfigError::ProviderOriginNotBare);
        let small_buffer: Expected =
            |error| matches!(error, ConfigError::ProxyBufferBelowRequestCap);

        let cases: &[(&[(&str, &str)], Expected)] = &[
            (&[("GATEWAY_GENERATION_TIMEOUT_SECONDS", "0")], validation),
            (
                &[("GATEWAY_GENERATION_TIMEOUT_SECONDS", "3601")],
                validation,
            ),
            (
                &[("GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS", "0")],
                validation,
            ),
            (
                &[("GATEWAY_LEASE_FINALIZATION_MARGIN_SECONDS", "3601")],
                validation,
            ),
            (
                &[("GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS", "0")],
                validation,
            ),
            (
                &[("GATEWAY_EXPIRED_LEASE_CLEANUP_GRACE_SECONDS", "86401")],
                validation,
            ),
            (&[("GATEWAY_SETTLEMENT_BACKLOG_LIMIT", "0")], validation),
            (&[("GATEWAY_RECORD_CACHE_TTL_SECONDS", "0")], validation),
            (&[("GATEWAY_RECORD_CACHE_TTL_SECONDS", "301")], validation),
            (&[("PROXY_MAX_REQUEST_BYTES", "1023")], validation),
            (
                &[("VALKEY_IAM_USER", "gradiated-prod-gateway")],
                incomplete_iam,
            ),
            (
                &[("VALKEY_IAM_CACHE_NAME", "gradiated-prod")],
                incomplete_iam,
            ),
            (&[("VALKEY_IAM_REGION", "us-east-1")], incomplete_iam),
            (
                &[
                    ("VALKEY_IAM_CACHE_NAME", "gradiated-prod"),
                    ("VALKEY_IAM_REGION", ""),
                    ("VALKEY_IAM_USER", "gradiated-prod-gateway"),
                ],
                empty_iam,
            ),
            (
                &[("PROXY_ANTHROPIC_ORIGIN", "http://api.anthropic.com")],
                insecure,
            ),
            (
                &[("PROXY_ANTHROPIC_ORIGIN", "https://api.anthropic.com/v1")],
                not_bare,
            ),
            (
                &[("PROXY_ANTHROPIC_ORIGIN", "https://api.anthropic.com?x=1")],
                not_bare,
            ),
            (
                &[("PROXY_ANTHROPIC_ORIGIN", "https://api.anthropic.com/")],
                not_bare,
            ),
            (&[("PROXY_ANTHROPIC_ORIGIN", "https://")], not_bare),
            (
                &[("PROXY_ANTHROPIC_ORIGIN", "https://user@api.anthropic.com")],
                not_bare,
            ),
            (
                &[("PROXY_ANTHROPIC_ORIGIN", "https://api.anthropic.com#f")],
                not_bare,
            ),
            (
                &[
                    ("PROXY_MAX_REQUEST_BYTES", "4194304"),
                    ("PROXY_REQUEST_BUFFER_BYTES", "2097152"),
                ],
                small_buffer,
            ),
        ];

        for (overrides, expected) in cases {
            let error = minimal_with(overrides).expect_err("the override is invalid");

            assert!(expected(&error), "{overrides:?} gave {error:?}");
        }
    }
}
