use std::{net::IpAddr, net::SocketAddr, time::Duration};

use axum::http::Uri;
use serde::Deserialize;

use crate::{capture::CaptureSettings, identity::IdentitySettings};

#[derive(Clone, Debug)]
pub struct ProxyConfig {
    pub bind_address: SocketAddr,
    pub admin_address: SocketAddr,
    pub gateway_origin: String,
    pub anthropic_origin: String,
    pub openai_origin: String,
    pub relay_enabled: bool,
    pub database_url: String,
    pub database_ca_bundle_path: Option<String>,
    pub identity: IdentitySettings,
    pub catalog_refresh: Duration,
    pub limits: Limits,
    pub capture: Option<CaptureSettings>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Limits {
    pub max_request_bytes: usize,
    pub request_buffer_bytes: usize,
    pub max_in_flight: usize,
    pub body_read: Duration,
    pub gateway: Deadlines,
    pub provider: Deadlines,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct Deadlines {
    pub connect: Duration,
    pub headers: Duration,
    pub idle: Duration,
    pub total: Duration,
}

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error(transparent)]
    Environment(#[from] envy::Error),
    #[error("{0} must be a bare origin such as https://api.example.com")]
    NotBareOrigin(&'static str),
    #[error("{0} must use HTTPS unless it is a loopback address")]
    InsecureOrigin(&'static str),
    #[error("{0} must be greater than zero")]
    Zero(&'static str),
    #[error("{0} must not exceed {1}")]
    Exceeds(&'static str, &'static str),
    #[error("PROXY_COLLECTOR_URL and PROXY_COLLECTOR_TOKEN must be set together")]
    CollectorPair,
    #[error("PROXY_COLLECTOR_URL must be an HTTP or HTTPS URL")]
    CollectorUrl,
}

#[derive(Deserialize)]
struct Environment {
    #[serde(default = "default_bind_address")]
    proxy_bind_address: SocketAddr,
    #[serde(default = "default_admin_address")]
    proxy_admin_address: SocketAddr,
    proxy_gateway_origin: String,
    #[serde(default = "default_anthropic_origin")]
    proxy_anthropic_origin: String,
    #[serde(default = "default_openai_origin")]
    proxy_openai_origin: String,
    #[serde(default = "default_true")]
    proxy_relay_enabled: bool,

    database_url: String,
    database_ca_bundle_path: Option<String>,

    #[serde(default = "default_identity_fresh_seconds")]
    proxy_identity_fresh_seconds: u64,
    #[serde(default = "default_identity_stale_grace_seconds")]
    proxy_identity_stale_grace_seconds: u64,
    #[serde(default = "default_identity_capacity")]
    proxy_identity_capacity: usize,
    #[serde(default = "default_identity_max_concurrent_loads")]
    proxy_identity_max_concurrent_loads: usize,
    #[serde(default = "default_catalog_refresh_seconds")]
    proxy_catalog_refresh_seconds: u64,

    #[serde(default = "default_max_request_bytes")]
    proxy_max_request_bytes: usize,
    #[serde(default = "default_request_buffer_bytes")]
    proxy_request_buffer_bytes: usize,
    #[serde(default = "default_max_in_flight")]
    proxy_max_in_flight: usize,

    #[serde(default = "default_gateway_connect_seconds")]
    proxy_gateway_connect_seconds: u64,
    proxy_gateway_header_seconds: Option<u64>,
    #[serde(default = "default_provider_connect_seconds")]
    proxy_provider_connect_seconds: u64,
    proxy_provider_header_seconds: Option<u64>,
    proxy_idle_seconds: Option<u64>,
    #[serde(default = "default_total_seconds")]
    proxy_total_seconds: u64,
    #[serde(default = "default_body_read_seconds")]
    proxy_body_read_seconds: u64,

    proxy_collector_url: Option<String>,
    proxy_collector_token: Option<String>,
    #[serde(default = "default_capture_buffer_bytes")]
    proxy_capture_buffer_bytes: usize,
}

impl ProxyConfig {
    pub fn from_environment() -> Result<Self, ConfigError> {
        Self::from_variables(std::env::vars())
    }

    pub fn from_variables<I>(variables: I) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = (String, String)>,
    {
        let environment: Environment = envy::from_iter(variables)?;

        environment.try_into()
    }
}

impl TryFrom<Environment> for ProxyConfig {
    type Error = ConfigError;

    fn try_from(environment: Environment) -> Result<Self, Self::Error> {
        let gateway_header_seconds = environment
            .proxy_gateway_header_seconds
            .unwrap_or(environment.proxy_total_seconds);
        let provider_header_seconds = environment
            .proxy_provider_header_seconds
            .unwrap_or(environment.proxy_total_seconds);
        let idle_seconds = environment
            .proxy_idle_seconds
            .unwrap_or(environment.proxy_total_seconds);

        let gateway_origin = bare_origin(
            "PROXY_GATEWAY_ORIGIN",
            environment.proxy_gateway_origin,
            false,
        )?;
        let anthropic_origin = bare_origin(
            "PROXY_ANTHROPIC_ORIGIN",
            environment.proxy_anthropic_origin,
            true,
        )?;
        let openai_origin =
            bare_origin("PROXY_OPENAI_ORIGIN", environment.proxy_openai_origin, true)?;

        for (name, value) in [
            (
                "PROXY_IDENTITY_FRESH_SECONDS",
                environment.proxy_identity_fresh_seconds,
            ),
            (
                "PROXY_CATALOG_REFRESH_SECONDS",
                environment.proxy_catalog_refresh_seconds,
            ),
            (
                "PROXY_GATEWAY_CONNECT_SECONDS",
                environment.proxy_gateway_connect_seconds,
            ),
            ("PROXY_GATEWAY_HEADER_SECONDS", gateway_header_seconds),
            (
                "PROXY_PROVIDER_CONNECT_SECONDS",
                environment.proxy_provider_connect_seconds,
            ),
            ("PROXY_PROVIDER_HEADER_SECONDS", provider_header_seconds),
            ("PROXY_IDLE_SECONDS", idle_seconds),
            ("PROXY_TOTAL_SECONDS", environment.proxy_total_seconds),
            (
                "PROXY_BODY_READ_SECONDS",
                environment.proxy_body_read_seconds,
            ),
        ] {
            if value == 0 {
                return Err(ConfigError::Zero(name));
            }
        }

        for (name, value) in [
            (
                "PROXY_IDENTITY_CAPACITY",
                environment.proxy_identity_capacity,
            ),
            (
                "PROXY_IDENTITY_MAX_CONCURRENT_LOADS",
                environment.proxy_identity_max_concurrent_loads,
            ),
            (
                "PROXY_MAX_REQUEST_BYTES",
                environment.proxy_max_request_bytes,
            ),
            ("PROXY_MAX_IN_FLIGHT", environment.proxy_max_in_flight),
            (
                "PROXY_CAPTURE_BUFFER_BYTES",
                environment.proxy_capture_buffer_bytes,
            ),
        ] {
            if value == 0 {
                return Err(ConfigError::Zero(name));
            }
        }

        if environment.proxy_max_request_bytes > environment.proxy_request_buffer_bytes {
            return Err(ConfigError::Exceeds(
                "PROXY_MAX_REQUEST_BYTES",
                "PROXY_REQUEST_BUFFER_BYTES",
            ));
        }

        // The semaphores that enforce these buffers count bytes as permits.
        for (name, value) in [
            (
                "PROXY_REQUEST_BUFFER_BYTES",
                environment.proxy_request_buffer_bytes,
            ),
            (
                "PROXY_CAPTURE_BUFFER_BYTES",
                environment.proxy_capture_buffer_bytes,
            ),
        ] {
            if value > tokio::sync::Semaphore::MAX_PERMITS {
                return Err(ConfigError::Exceeds(name, "the semaphore permit limit"));
            }
        }

        let capture = match (
            environment.proxy_collector_url,
            environment.proxy_collector_token,
        ) {
            (None, None) => None,
            (Some(collector_url), Some(collector_token)) => {
                let scheme = collector_url
                    .parse::<Uri>()
                    .ok()
                    .and_then(|uri| uri.scheme_str().map(str::to_owned));
                if !matches!(scheme.as_deref(), Some("http" | "https")) {
                    return Err(ConfigError::CollectorUrl);
                }

                Some(CaptureSettings {
                    collector_url,
                    collector_token,
                    buffer_bytes: environment.proxy_capture_buffer_bytes,
                })
            }
            _ => return Err(ConfigError::CollectorPair),
        };

        for (name, value) in [
            ("PROXY_GATEWAY_HEADER_SECONDS", gateway_header_seconds),
            ("PROXY_PROVIDER_HEADER_SECONDS", provider_header_seconds),
            ("PROXY_IDLE_SECONDS", idle_seconds),
        ] {
            if value > environment.proxy_total_seconds {
                return Err(ConfigError::Exceeds(name, "PROXY_TOTAL_SECONDS"));
            }
        }

        let seconds = Duration::from_secs;
        let idle = seconds(idle_seconds);
        let total = seconds(environment.proxy_total_seconds);

        Ok(Self {
            bind_address: environment.proxy_bind_address,
            admin_address: environment.proxy_admin_address,
            gateway_origin,
            anthropic_origin,
            openai_origin,
            relay_enabled: environment.proxy_relay_enabled,
            database_url: environment.database_url,
            database_ca_bundle_path: environment.database_ca_bundle_path,
            identity: IdentitySettings {
                fresh_for: seconds(environment.proxy_identity_fresh_seconds),
                stale_grace: seconds(environment.proxy_identity_stale_grace_seconds),
                capacity: environment.proxy_identity_capacity,
                max_concurrent_loads: environment.proxy_identity_max_concurrent_loads,
            },
            catalog_refresh: seconds(environment.proxy_catalog_refresh_seconds),
            limits: Limits {
                max_request_bytes: environment.proxy_max_request_bytes,
                request_buffer_bytes: environment.proxy_request_buffer_bytes,
                max_in_flight: environment.proxy_max_in_flight,
                body_read: seconds(environment.proxy_body_read_seconds),
                gateway: Deadlines {
                    connect: seconds(environment.proxy_gateway_connect_seconds),
                    headers: seconds(gateway_header_seconds),
                    idle,
                    total,
                },
                provider: Deadlines {
                    connect: seconds(environment.proxy_provider_connect_seconds),
                    headers: seconds(provider_header_seconds),
                    idle,
                    total,
                },
            },
            capture,
        })
    }
}

fn bare_origin(name: &'static str, origin: String, provider: bool) -> Result<String, ConfigError> {
    let uri = origin
        .parse::<Uri>()
        .map_err(|_| ConfigError::NotBareOrigin(name))?;
    let authority = uri
        .authority()
        .filter(|authority| !authority.as_str().contains('@'))
        .ok_or(ConfigError::NotBareOrigin(name))?;
    let scheme = uri.scheme_str().ok_or(ConfigError::NotBareOrigin(name))?;

    if origin != format!("{scheme}://{authority}") {
        return Err(ConfigError::NotBareOrigin(name));
    }

    let loopback = authority.host() == "localhost"
        || authority
            .host()
            .trim_start_matches('[')
            .trim_end_matches(']')
            .parse::<IpAddr>()
            .is_ok_and(|ip| ip.is_loopback());

    match scheme {
        "https" => Ok(origin),
        "http" if !provider || loopback => Ok(origin),
        "http" => Err(ConfigError::InsecureOrigin(name)),
        _ => Err(ConfigError::NotBareOrigin(name)),
    }
}

fn default_bind_address() -> SocketAddr {
    SocketAddr::from(([0, 0, 0, 0], 3003))
}

fn default_admin_address() -> SocketAddr {
    SocketAddr::from(([0, 0, 0, 0], 9003))
}

fn default_anthropic_origin() -> String {
    "https://api.anthropic.com".to_owned()
}

fn default_openai_origin() -> String {
    "https://api.openai.com".to_owned()
}

fn default_true() -> bool {
    true
}

fn default_identity_fresh_seconds() -> u64 {
    15
}

fn default_identity_stale_grace_seconds() -> u64 {
    3_600
}

fn default_identity_capacity() -> usize {
    100_000
}

fn default_identity_max_concurrent_loads() -> usize {
    128
}

fn default_catalog_refresh_seconds() -> u64 {
    5
}

fn default_max_request_bytes() -> usize {
    32_000_000
}

fn default_request_buffer_bytes() -> usize {
    256 * 1024 * 1024
}

fn default_max_in_flight() -> usize {
    4_000
}

fn default_capture_buffer_bytes() -> usize {
    256 * 1024 * 1024
}

fn default_gateway_connect_seconds() -> u64 {
    2
}

fn default_provider_connect_seconds() -> u64 {
    10
}

fn default_body_read_seconds() -> u64 {
    60
}

/// The official SDKs time out after 600 seconds.
fn default_total_seconds() -> u64 {
    630
}

#[cfg(test)]
mod tests {
    use super::*;

    const REQUIRED: [(&str, &str); 2] = [
        ("PROXY_GATEWAY_ORIGIN", "http://gateway.gradiated.svc:3002"),
        ("DATABASE_URL", "postgres://127.0.0.1/gradiated"),
    ];

    fn config(overrides: &[(&str, &str)]) -> Result<ProxyConfig, ConfigError> {
        let mut variables: Vec<(String, String)> = REQUIRED
            .iter()
            .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()))
            .collect();
        variables.retain(|(name, _)| !overrides.iter().any(|(other, _)| other == name));
        variables.extend(
            overrides
                .iter()
                .map(|(name, value)| ((*name).to_owned(), (*value).to_owned())),
        );

        ProxyConfig::from_variables(variables)
    }

    #[test]
    fn defaults_follow_the_plan() {
        let config = config(&[]).unwrap();

        assert!(config.relay_enabled);
        assert_eq!(config.anthropic_origin, "https://api.anthropic.com");
        assert_eq!(config.openai_origin, "https://api.openai.com");
        assert_eq!(config.identity.fresh_for, Duration::from_secs(15));
        assert_eq!(config.identity.stale_grace, Duration::from_secs(3_600));
        assert_eq!(config.identity.max_concurrent_loads, 128);
        assert_eq!(config.limits.provider.total, Duration::from_secs(630));
        assert_eq!(config.limits.provider.headers, Duration::from_secs(630));
        assert_eq!(config.limits.provider.idle, Duration::from_secs(630));
        assert_eq!(config.limits.gateway.headers, Duration::from_secs(630));
        assert_eq!(config.limits.max_request_bytes, 32_000_000);
        assert_eq!(config.limits.body_read, Duration::from_secs(60));
        assert!(config.capture.is_none());
    }

    #[test]
    fn capture_needs_a_collector_url_and_token() {
        let url = ("PROXY_COLLECTOR_URL", "http://collector:3004/v1/contents");
        let token = ("PROXY_COLLECTOR_TOKEN", "secret");

        let capture = config(&[url, token]).unwrap().capture.unwrap();
        assert_eq!(capture.collector_url, url.1);
        assert_eq!(capture.buffer_bytes, 256 * 1024 * 1024);

        for overrides in [
            &[url][..],
            &[token][..],
            &[("PROXY_COLLECTOR_URL", "collector:3004"), token][..],
            &[url, token, ("PROXY_CAPTURE_BUFFER_BYTES", "0")][..],
        ] {
            assert!(config(overrides).is_err(), "{overrides:?}");
        }
    }

    #[test]
    fn origins_must_be_bare_and_providers_must_be_secure() {
        for (name, origin, accepted) in [
            ("PROXY_ANTHROPIC_ORIGIN", "https://api.anthropic.com", true),
            ("PROXY_ANTHROPIC_ORIGIN", "http://127.0.0.1:9", true),
            ("PROXY_OPENAI_ORIGIN", "http://localhost:9", true),
            ("PROXY_OPENAI_ORIGIN", "http://[::1]:9", true),
            ("PROXY_ANTHROPIC_ORIGIN", "http://api.anthropic.com", false),
            (
                "PROXY_ANTHROPIC_ORIGIN",
                "https://api.anthropic.com/",
                false,
            ),
            (
                "PROXY_ANTHROPIC_ORIGIN",
                "https://api.anthropic.com/v1",
                false,
            ),
            ("PROXY_OPENAI_ORIGIN", "https://user@api.openai.com", false),
            ("PROXY_OPENAI_ORIGIN", "ftp://api.openai.com", false),
            ("PROXY_OPENAI_ORIGIN", "api.openai.com", false),
            (
                "PROXY_GATEWAY_ORIGIN",
                "http://gateway.gradiated.svc:3002",
                true,
            ),
            ("PROXY_GATEWAY_ORIGIN", "http://gateway:3002/v1", false),
        ] {
            assert_eq!(
                config(&[(name, origin)]).is_ok(),
                accepted,
                "{name}={origin}"
            );
        }
    }

    #[test]
    fn inconsistent_limits_are_rejected() {
        for overrides in [
            &[("PROXY_TOTAL_SECONDS", "0")][..],
            &[("PROXY_MAX_IN_FLIGHT", "0")][..],
            &[("PROXY_IDENTITY_MAX_CONCURRENT_LOADS", "0")][..],
            &[
                ("PROXY_MAX_REQUEST_BYTES", "2048"),
                ("PROXY_REQUEST_BUFFER_BYTES", "1024"),
            ][..],
            &[("PROXY_TOTAL_SECONDS", "60"), ("PROXY_IDLE_SECONDS", "61")][..],
            &[
                ("PROXY_TOTAL_SECONDS", "300"),
                ("PROXY_PROVIDER_HEADER_SECONDS", "301"),
            ][..],
            &[("PROXY_RELAY_ENABLED", "maybe")][..],
            &[("PROXY_IDLE_SECONDS", "0")][..],
            &[("PROXY_BODY_READ_SECONDS", "0")][..],
        ] {
            assert!(config(overrides).is_err(), "{overrides:?}");
        }
    }

    #[test]
    fn the_gateway_origin_and_database_are_required() {
        for missing in ["PROXY_GATEWAY_ORIGIN", "DATABASE_URL"] {
            let variables = REQUIRED
                .iter()
                .filter(|(name, _)| *name != missing)
                .map(|(name, value)| ((*name).to_owned(), (*value).to_owned()));

            assert!(ProxyConfig::from_variables(variables).is_err(), "{missing}");
        }
    }
}
