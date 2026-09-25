use std::{net::SocketAddr, path::PathBuf, time::Duration};

use serde::Deserialize;

use crate::spool::Limits;

#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error(transparent)]
    Environment(#[from] envy::Error),
    #[error("set exactly one of COLLECTOR_BUCKET and COLLECTOR_LOCAL_STORE_DIR")]
    Store,
    #[error("{0} must be greater than zero")]
    Zero(&'static str),
    #[error("COLLECTOR_TOKEN must be at least 32 characters")]
    Token,
}

#[derive(Clone, Debug)]
pub enum Store {
    S3 { bucket: String },
    Local { directory: PathBuf },
}

#[derive(Clone, Debug)]
pub struct CollectorConfig {
    pub bind_address: SocketAddr,
    pub admin_address: SocketAddr,
    pub data_dir: PathBuf,
    pub store: Store,
    pub replica: String,
    pub token: String,
    pub max_record_bytes: usize,
    pub max_concurrent_requests: usize,
    pub limits: Limits,
    pub drain: Duration,
}

#[derive(Deserialize)]
struct Environment {
    #[serde(default = "default_bind_address")]
    collector_bind_address: SocketAddr,
    #[serde(default = "default_admin_address")]
    collector_admin_address: SocketAddr,
    collector_data_dir: PathBuf,
    collector_bucket: Option<String>,
    collector_local_store_dir: Option<PathBuf>,
    collector_replica: Option<String>,
    hostname: Option<String>,
    collector_token: String,
    #[serde(default = "default_max_record_bytes")]
    collector_max_record_bytes: usize,
    #[serde(default = "default_max_concurrent_requests")]
    collector_max_concurrent_requests: usize,
    #[serde(default = "default_max_open_streams")]
    collector_max_open_streams: usize,
    #[serde(default = "default_max_pending_batches")]
    collector_max_pending_batches: usize,
    #[serde(default = "default_max_batch_bytes")]
    collector_max_batch_bytes: u64,
    #[serde(default = "default_max_batch_seconds")]
    collector_max_batch_seconds: u64,
    #[serde(default = "default_disk_cap_bytes")]
    collector_disk_cap_bytes: u64,
    #[serde(default = "default_drain_seconds")]
    collector_drain_seconds: u64,
}

impl CollectorConfig {
    pub fn from_environment() -> Result<Self, ConfigError> {
        Self::from_variables(std::env::vars())
    }

    pub fn from_variables<I>(variables: I) -> Result<Self, ConfigError>
    where
        I: IntoIterator<Item = (String, String)>,
    {
        let environment: Environment = envy::from_iter(variables)?;

        let store = match (
            environment.collector_bucket,
            environment.collector_local_store_dir,
        ) {
            (Some(bucket), None) if !bucket.is_empty() => Store::S3 { bucket },
            (None, Some(directory)) => Store::Local { directory },
            _ => return Err(ConfigError::Store),
        };

        for (name, value) in [
            (
                "COLLECTOR_MAX_RECORD_BYTES",
                environment.collector_max_record_bytes as u64,
            ),
            (
                "COLLECTOR_MAX_BATCH_BYTES",
                environment.collector_max_batch_bytes,
            ),
            (
                "COLLECTOR_MAX_BATCH_SECONDS",
                environment.collector_max_batch_seconds,
            ),
            (
                "COLLECTOR_DISK_CAP_BYTES",
                environment.collector_disk_cap_bytes,
            ),
            (
                "COLLECTOR_MAX_CONCURRENT_REQUESTS",
                environment.collector_max_concurrent_requests as u64,
            ),
            (
                "COLLECTOR_MAX_OPEN_STREAMS",
                environment.collector_max_open_streams as u64,
            ),
            (
                "COLLECTOR_MAX_PENDING_BATCHES",
                environment.collector_max_pending_batches as u64,
            ),
        ] {
            if value == 0 {
                return Err(ConfigError::Zero(name));
            }
        }

        if environment.collector_token.len() < 32 {
            return Err(ConfigError::Token);
        }

        Ok(Self {
            bind_address: environment.collector_bind_address,
            admin_address: environment.collector_admin_address,
            data_dir: environment.collector_data_dir,
            store,
            replica: environment
                .collector_replica
                .or(environment.hostname)
                .unwrap_or_else(|| "collector".to_owned()),
            token: environment.collector_token,
            max_record_bytes: environment.collector_max_record_bytes,
            max_concurrent_requests: environment.collector_max_concurrent_requests,
            limits: Limits {
                max_open_streams: environment.collector_max_open_streams,
                max_pending_batches: environment.collector_max_pending_batches,
                max_batch_bytes: environment.collector_max_batch_bytes,
                max_batch_age: Duration::from_secs(environment.collector_max_batch_seconds),
                disk_cap_bytes: environment.collector_disk_cap_bytes,
            },
            drain: Duration::from_secs(environment.collector_drain_seconds),
        })
    }
}

fn default_bind_address() -> SocketAddr {
    SocketAddr::from(([0, 0, 0, 0], 3004))
}

fn default_admin_address() -> SocketAddr {
    SocketAddr::from(([0, 0, 0, 0], 9004))
}

fn default_max_record_bytes() -> usize {
    32 * 1024 * 1024
}

fn default_max_concurrent_requests() -> usize {
    8
}

fn default_max_pending_batches() -> usize {
    1024
}

fn default_max_open_streams() -> usize {
    256
}

fn default_max_batch_bytes() -> u64 {
    16 * 1024 * 1024
}

fn default_max_batch_seconds() -> u64 {
    60
}

fn default_disk_cap_bytes() -> u64 {
    8 * 1024 * 1024 * 1024
}

fn default_drain_seconds() -> u64 {
    60
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config(overrides: &[(&str, &str)]) -> Result<CollectorConfig, ConfigError> {
        let mut variables = vec![
            (
                "COLLECTOR_DATA_DIR".to_owned(),
                "/var/lib/collector".to_owned(),
            ),
            (
                "COLLECTOR_BUCKET".to_owned(),
                "gradiated-prod-contents-us-east-1".to_owned(),
            ),
            ("COLLECTOR_TOKEN".to_owned(), "t".repeat(32)),
        ];
        for (name, value) in overrides {
            variables.retain(|(existing, _)| existing != name);
            if !value.is_empty() {
                variables.push(((*name).to_owned(), (*value).to_owned()));
            }
        }

        CollectorConfig::from_variables(variables)
    }

    #[test]
    fn defaults_follow_the_plan() {
        let config = config(&[]).unwrap();

        assert_eq!(config.limits.max_batch_bytes, 16 * 1024 * 1024);
        assert_eq!(config.limits.max_batch_age, Duration::from_secs(60));
        assert!(matches!(config.store, Store::S3 { .. }));
    }

    #[test]
    fn invalid_settings_are_refused() {
        for overrides in [
            &[("COLLECTOR_LOCAL_STORE_DIR", "/tmp/store")][..],
            &[("COLLECTOR_BUCKET", "")][..],
            &[("COLLECTOR_TOKEN", "short")][..],
            &[("COLLECTOR_MAX_BATCH_SECONDS", "0")][..],
            &[("COLLECTOR_DISK_CAP_BYTES", "0")][..],
            &[("COLLECTOR_MAX_OPEN_STREAMS", "0")][..],
            &[("COLLECTOR_MAX_CONCURRENT_REQUESTS", "0")][..],
        ] {
            assert!(config(overrides).is_err(), "{overrides:?}");
        }
    }
}
