use std::{env, fmt, net::SocketAddr, time::Duration};

use axum::http::Uri;
use serde::Deserialize;
use thiserror::Error;
use validator::Validate;

use crate::{catalog::ProviderCompliance, model::MAX_SAFE_INTEGER};

/// The official SDKs time out after 600 seconds.
const MAX_REQUEST_SECONDS: u64 = 630;
const DEFAULT_OPENROUTER_BASE_URL: &str = "https://openrouter.ai/api/v1";

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
    pub eval_concurrency_cap: u64,
    pub eval_requests_per_minute: u64,
    pub eval_service_tokens: Vec<String>,
    pub eval_cold_start_wait_seconds: u64,
    pub balance_per_concurrency_slot_nano_usd: u64,
    pub settlement_backlog_limit: u64,

    compliance: ProviderCompliance,

    pub database_url: String,
    pub database_ca_bundle_path: Option<String>,
    record_cache_ttl: Duration,

    pub valkey_url: String,
    valkey_iam: Option<ValkeyIamConfig>,

    pub sglang_api_key: Option<String>,
    pub verification_workspace_id: Option<uuid::Uuid>,
    pub openrouter: OpenRouterConfig,
    pub fallback_routes: crate::runtime::FallbackRoutes,
}

/// Outbound OpenRouter configuration for the migration and loopback tests.
#[derive(Clone, Eq, PartialEq)]
pub struct OpenRouterConfig {
    pub api_key: Option<String>,
    pub base_url: String,
}

impl OpenRouterConfig {
    pub fn is_loopback_mock(&self) -> bool {
        self.api_key.is_some()
            && self
                .base_url
                .parse::<Uri>()
                .ok()
                .is_some_and(|uri| matches!(uri.host(), Some("127.0.0.1" | "localhost" | "[::1]")))
    }
}

impl fmt::Debug for OpenRouterConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("OpenRouterConfig")
            .field("api_key", &self.api_key.as_ref().map(|_| "<redacted>"))
            .field("base_url", &self.base_url)
            .finish()
    }
}

impl GatewayConfig {
    #[cfg(test)]
    pub(crate) fn for_tests() -> Self {
        Self::from_variables(
            MINIMAL_ENVIRONMENT.map(|(name, value)| (name.to_owned(), value.to_owned())),
        )
        .expect("the test environment is valid")
    }

    pub fn use_openrouter_fallback(&self) -> bool {
        self.openrouter.is_loopback_mock()
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
            .field("eval_concurrency_cap", &self.eval_concurrency_cap)
            .field("eval_service_tokens", &self.eval_service_tokens.len())
            .field(
                "eval_cold_start_wait_seconds",
                &self.eval_cold_start_wait_seconds,
            )
            .field("eval_requests_per_minute", &self.eval_requests_per_minute)
            .field(
                "balance_per_concurrency_slot_nano_usd",
                &self.balance_per_concurrency_slot_nano_usd,
            )
            .field("settlement_backlog_limit", &self.settlement_backlog_limit)
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
            .field("openrouter", &self.openrouter)
            .field("fallback_routes", &self.fallback_routes)
            .finish()
    }
}

impl TryFrom<Environment> for GatewayConfig {
    type Error = ConfigError;

    fn try_from(environment: Environment) -> Result<Self, ConfigError> {
        let valkey_iam = environment.valkey_iam()?;
        let openrouter = environment.openrouter()?;
        let fallback_routes = match environment.gateway_fallback_routes.as_deref() {
            Some(raw) => crate::runtime::FallbackRoutes::parse(Some(raw))
                .ok_or(ConfigError::FallbackRoutes)?,
            None => crate::runtime::FallbackRoutes::production(),
        };
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
            eval_concurrency_cap: environment.eval_concurrency_cap,
            eval_requests_per_minute: environment.eval_requests_per_minute,
            eval_service_tokens: environment.eval_service_tokens()?,
            eval_cold_start_wait_seconds: environment.eval_cold_start_wait_seconds,
            balance_per_concurrency_slot_nano_usd: environment
                .balance_per_concurrency_slot_nano_usd,
            settlement_backlog_limit: environment.settlement_backlog_limit,
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
            verification_workspace_id: environment.gateway_verification_workspace_id,
            openrouter,
            fallback_routes,
        })
    }
}

#[derive(Deserialize, Validate)]
struct Environment {
    gateway_verification_workspace_id: Option<uuid::Uuid>,
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
        rename = "gateway_eval_concurrency_cap",
        default = "default_eval_concurrency_cap"
    )]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    eval_concurrency_cap: u64,
    #[serde(
        rename = "gateway_eval_requests_per_minute",
        default = "default_eval_requests_per_minute"
    )]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    eval_requests_per_minute: u64,
    /// Comma-separated: the current token and, while rotating, the previous one.
    #[serde(rename = "gateway_eval_service_tokens")]
    eval_service_tokens: Option<String>,
    /// A pool at zero takes about five to eight minutes to serve its first replica.
    #[serde(
        rename = "gateway_eval_cold_start_wait_seconds",
        default = "default_eval_cold_start_wait_seconds"
    )]
    #[validate(range(max = 1_800))]
    eval_cold_start_wait_seconds: u64,
    #[serde(
        rename = "gateway_balance_per_concurrency_slot_nano_usd",
        default = "default_balance_per_concurrency_slot_nano_usd"
    )]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    balance_per_concurrency_slot_nano_usd: u64,
    #[serde(rename = "gateway_settlement_backlog_limit")]
    #[validate(range(min = 1, max = MAX_SAFE_INTEGER))]
    settlement_backlog_limit: u64,

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

    gateway_fallback_routes: Option<String>,
    openrouter_api_key: Option<String>,
    openrouter_base_url: Option<String>,
}

impl Environment {
    fn eval_service_tokens(&self) -> Result<Vec<String>, ConfigError> {
        let Some(raw) = self
            .eval_service_tokens
            .as_deref()
            .filter(|raw| !raw.is_empty())
        else {
            return Ok(Vec::new());
        };
        let tokens: Vec<String> = raw.split(',').map(str::to_owned).collect();
        let valid = tokens.len() <= 2
            && tokens.iter().all(|token| {
                (32..=4096).contains(&token.len())
                    && token.bytes().all(|byte| byte.is_ascii_graphic())
            });

        valid
            .then_some(tokens)
            .ok_or(ConfigError::EvalServiceTokens)
    }

    fn openrouter(&self) -> Result<OpenRouterConfig, ConfigError> {
        let base_url = self
            .openrouter_base_url
            .as_deref()
            .filter(|url| !url.is_empty())
            .unwrap_or(DEFAULT_OPENROUTER_BASE_URL)
            .trim_end_matches('/')
            .to_owned();
        if !secure_or_loopback(&base_url) {
            return Err(ConfigError::OpenRouterBaseUrl);
        }

        Ok(OpenRouterConfig {
            api_key: self
                .openrouter_api_key
                .clone()
                .filter(|key| !key.is_empty()),
            base_url,
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

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ValkeyIamConfig {
    pub cache_name: String,
    pub region: String,
    pub user: String,
}

/// Plain HTTP is accepted only for a loopback test double.
fn secure_or_loopback(url: &str) -> bool {
    let Ok(uri) = url.parse::<Uri>() else {
        return false;
    };

    match (uri.scheme_str(), uri.host()) {
        (Some("https"), Some(_)) => true,
        (Some("http"), Some(host)) => matches!(host, "127.0.0.1" | "localhost" | "[::1]"),
        _ => false,
    }
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
    500
}

fn default_eval_concurrency_cap() -> u64 {
    20
}

fn default_eval_requests_per_minute() -> u64 {
    600
}

fn default_eval_cold_start_wait_seconds() -> u64 {
    600
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
    #[error("OPENROUTER_BASE_URL must be an HTTPS URL, or HTTP on a loopback host")]
    OpenRouterBaseUrl,
    #[error("GATEWAY_FALLBACK_ROUTES must contain valid Baseten or Modal routes")]
    FallbackRoutes,
    #[error(
        "GATEWAY_EVAL_SERVICE_TOKENS takes one or two tokens of 32 to 4096 printable characters"
    )]
    EvalServiceTokens,
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
    fn verification_requires_an_explicit_valid_workspace() {
        assert_eq!(minimal_with(&[]).unwrap().verification_workspace_id, None);
        let workspace = "00000000-0000-4000-8000-000000000001";
        assert_eq!(
            minimal_with(&[("GATEWAY_VERIFICATION_WORKSPACE_ID", workspace)])
                .unwrap()
                .verification_workspace_id,
            Some(uuid::Uuid::parse_str(workspace).unwrap())
        );
        assert!(minimal_with(&[("GATEWAY_VERIFICATION_WORKSPACE_ID", "invalid")]).is_err());
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
        assert_eq!(config.organization_concurrency_cap, 500);
        assert_eq!(
            (
                config.eval_concurrency_cap,
                config.eval_requests_per_minute,
                config.eval_cold_start_wait_seconds
            ),
            (20, 600, 600)
        );
        assert_eq!(config.balance_per_concurrency_slot_nano_usd, 1_000_000_000);
        assert_eq!(config.settlement_backlog_limit, 100_000);
        assert_eq!(config.valkey_iam(), None);
        assert_eq!(config.sglang_api_key, None);
        assert_eq!(config.database_ca_bundle_path, None);
        assert!(config.compliance().zdr);
        assert!(!config.compliance().hipaa);
    }

    #[test]
    fn the_openrouter_key_comes_from_the_environment_or_else_the_provider_secret() {
        let production = minimal_with(&[]).unwrap().openrouter;
        assert_eq!(production.api_key, None);
        assert_eq!(production.base_url, DEFAULT_OPENROUTER_BASE_URL);
        assert_eq!(
            minimal_with(&[("OPENROUTER_API_KEY", "")])
                .unwrap()
                .openrouter
                .api_key,
            None
        );

        let local = minimal_with(&[
            ("OPENROUTER_API_KEY", "platform-key"),
            ("OPENROUTER_BASE_URL", "http://127.0.0.1:4100/api/v1/"),
        ])
        .unwrap();
        assert_eq!(
            local.openrouter,
            OpenRouterConfig {
                api_key: Some("platform-key".to_owned()),
                base_url: "http://127.0.0.1:4100/api/v1".to_owned(),
            }
        );
        assert_eq!(local.sglang_api_key, None);
    }

    #[test]
    fn production_fallback_routes_are_loaded_by_default() {
        let config = minimal_with(&[]).unwrap();
        assert!(!config.use_openrouter_fallback());
        assert!(!config.fallback_routes.is_empty());
        assert!(config.fallback_routes.contains("moonshotai/kimi-k3.1-pro"));
        assert!(config
            .fallback_routes
            .contains("deepseek/deepseek-v4.1-flash-1017"));
        assert!(config.fallback_routes.contains("z-ai/glm-5.3-flash"));
        assert!(config.fallback_routes.contains("z-ai/glm-5.3"));
    }

    #[test]
    fn openrouter_capacity_rejects_an_insecure_url() {
        for url in [
            "http://openrouter.ai/api/v1",
            "ftp://127.0.0.1/api",
            "not a url",
        ] {
            assert!(
                matches!(
                    minimal_with(&[
                        ("OPENROUTER_API_KEY", "platform-key"),
                        ("OPENROUTER_BASE_URL", url),
                    ]),
                    Err(ConfigError::OpenRouterBaseUrl)
                ),
                "{url}"
            );
        }
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
            ("OPENROUTER_API_KEY", "platform-secret"),
        ])
        .expect("the environment parses");
        let debug = format!("{config:?}");

        for secret in [
            "db-secret",
            "valkey-secret",
            "runtime-secret",
            "platform-secret",
        ] {
            assert!(!debug.contains(secret), "{secret} leaked into {debug}");
        }
    }

    #[test]
    fn the_generation_deadline_cannot_exceed_the_sdk_timeout_and_margin() {
        let key = "GATEWAY_GENERATION_TIMEOUT_SECONDS";

        assert!(minimal_with(&[(key, "630")]).is_ok());
        assert!(minimal_with(&[(key, "631")]).is_err());
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
        ];

        for (overrides, expected) in cases {
            let error = minimal_with(overrides).expect_err("the override is invalid");

            assert!(expected(&error), "{overrides:?} gave {error:?}");
        }
    }

    #[test]
    fn eval_service_tokens_take_one_or_two_long_tokens() {
        let long = "a".repeat(32);
        let rotating = format!("{long},{}", "b".repeat(40));
        assert_eq!(
            minimal_with(&[("GATEWAY_EVAL_SERVICE_TOKENS", &rotating)])
                .unwrap()
                .eval_service_tokens
                .len(),
            2
        );
        assert!(minimal_with(&[]).unwrap().eval_service_tokens.is_empty());
        for invalid in [
            "short",
            &format!("{long},{long},{long}"),
            &format!("{long} "),
        ] {
            assert!(matches!(
                minimal_with(&[("GATEWAY_EVAL_SERVICE_TOKENS", invalid)]),
                Err(ConfigError::EvalServiceTokens)
            ));
        }
    }
}
