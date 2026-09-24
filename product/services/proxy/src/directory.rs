use std::{net::IpAddr, str::FromStr, sync::Arc, time::Duration};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use deadpool_postgres::{Manager, ManagerConfig, Pool, RecyclingMethod, Runtime, Timeouts};
use rustls::ClientConfig;
use tokio_postgres::{
    config::{Host, SslMode},
    Config, NoTls,
};
use tokio_postgres_rustls::MakeRustlsConnect;
use uuid::Uuid;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IdentityRecord {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub expires_at: Option<DateTime<Utc>>,
    pub revoked_at: Option<DateTime<Utc>>,
    pub workspace_archived: bool,
    pub organization_active: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
#[error("the directory is unavailable")]
pub struct DirectoryUnavailable;

#[async_trait]
pub trait Directory: Send + Sync + 'static {
    async fn identity(
        &self,
        digest: [u8; 32],
    ) -> Result<Option<IdentityRecord>, DirectoryUnavailable>;

    async fn hosted_models(&self) -> Result<Vec<String>, DirectoryUnavailable>;
}

const IDENTITY_QUERY: &str = "\
select
    api_keys.id,
    api_keys.organization_id,
    api_keys.workspace_id,
    api_keys.expires_at,
    api_keys.revoked_at,
    workspaces.archived_at is not null,
    organizations.status = 'active'
from api_keys
join workspaces
  on workspaces.organization_id = api_keys.organization_id
 and workspaces.id = api_keys.workspace_id
join organizations on organizations.id = api_keys.organization_id
where api_keys.digest = $1";

const HOSTED_MODELS_QUERY: &str = "select id from models";

const POOL_SIZE: usize = 8;
const QUERY_TIMEOUT: Duration = Duration::from_secs(2);
const CONNECT_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Clone)]
pub struct PostgresDirectory {
    pool: Pool,
}

impl PostgresDirectory {
    pub fn connect(url: &str, ca_bundle_path: Option<&str>) -> Result<Self, DirectoryError> {
        let mut config = connection_config(url)?;
        config.connect_timeout(CONNECT_TIMEOUT);

        let manager_config = ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        };
        let manager = if config.get_ssl_mode() == SslMode::Disable {
            Manager::from_config(config, NoTls, manager_config)
        } else {
            let bundle = ca_bundle_path.ok_or_else(|| {
                DirectoryError::Tls(
                    "DATABASE_CA_BUNDLE_PATH is required for a remote database".into(),
                )
            })?;
            Manager::from_config(
                config,
                MakeRustlsConnect::new(tls_config(bundle)?),
                manager_config,
            )
        };

        let pool = Pool::builder(manager)
            .max_size(POOL_SIZE)
            .timeouts(Timeouts {
                wait: Some(QUERY_TIMEOUT),
                create: Some(CONNECT_TIMEOUT),
                recycle: Some(CONNECT_TIMEOUT),
            })
            .runtime(Runtime::Tokio1)
            .build()
            .map_err(|error| DirectoryError::Configuration(error.to_string()))?;

        Ok(Self { pool })
    }

    async fn query(
        &self,
        statement: &str,
        parameters: &[&(dyn tokio_postgres::types::ToSql + Sync)],
    ) -> Result<Vec<tokio_postgres::Row>, DirectoryUnavailable> {
        let query = async {
            let client = self.pool.get().await.map_err(|error| {
                tracing::debug!(%error, "database connection unavailable");
                DirectoryUnavailable
            })?;

            client.query(statement, parameters).await.map_err(|error| {
                tracing::debug!(%error, "database query failed");
                DirectoryUnavailable
            })
        };

        tokio::time::timeout(QUERY_TIMEOUT, query)
            .await
            .map_err(|_| DirectoryUnavailable)?
    }
}

#[async_trait]
impl Directory for PostgresDirectory {
    async fn identity(
        &self,
        digest: [u8; 32],
    ) -> Result<Option<IdentityRecord>, DirectoryUnavailable> {
        let rows = self.query(IDENTITY_QUERY, &[&digest.as_slice()]).await?;
        let Some(row) = rows.first() else {
            return Ok(None);
        };

        let record = (|| {
            Ok::<_, tokio_postgres::Error>(IdentityRecord {
                api_key_id: row.try_get(0)?,
                organization_id: row.try_get(1)?,
                workspace_id: row.try_get(2)?,
                expires_at: row.try_get(3)?,
                revoked_at: row.try_get(4)?,
                workspace_archived: row.try_get(5)?,
                organization_active: row.try_get(6)?,
            })
        })()
        .map_err(|error| {
            tracing::debug!(%error, "identity row unreadable");
            DirectoryUnavailable
        })?;

        Ok(Some(record))
    }

    async fn hosted_models(&self) -> Result<Vec<String>, DirectoryUnavailable> {
        self.query(HOSTED_MODELS_QUERY, &[])
            .await?
            .iter()
            .map(|row| row.try_get(0).map_err(|_| DirectoryUnavailable))
            .collect()
    }
}

#[derive(Debug, thiserror::Error)]
pub enum DirectoryError {
    #[error("PostgreSQL configuration is invalid: {0}")]
    Configuration(String),
    #[error("PostgreSQL TLS configuration is invalid: {0}")]
    Tls(String),
}

/// `tokio-postgres` cannot parse the `verify-*` modes; `tls_config` always verifies.
fn connection_config(url: &str) -> Result<Config, DirectoryError> {
    let url = url
        .replace("sslmode=verify-full", "sslmode=require")
        .replace("sslmode=verify-ca", "sslmode=require");
    let mut config =
        Config::from_str(&url).map_err(|error| DirectoryError::Configuration(error.to_string()))?;

    let local = config.get_hosts().iter().all(is_loopback);
    config.ssl_mode(if local {
        SslMode::Disable
    } else {
        SslMode::Require
    });

    Ok(config)
}

fn is_loopback(host: &Host) -> bool {
    match host {
        Host::Tcp(name) => {
            name == "localhost" || name.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
        }
        Host::Unix(_) => true,
    }
}

/// Amazon RDS roots its chain in its own authority, so the database is verified
/// against that bundle alone.
fn tls_config(ca_bundle_path: &str) -> Result<ClientConfig, DirectoryError> {
    let bundle = std::fs::read(ca_bundle_path)
        .map_err(|error| DirectoryError::Tls(format!("{ca_bundle_path}: {error}")))?;
    let mut roots = rustls::RootCertStore::empty();
    let (added, _) =
        roots.add_parsable_certificates(rustls_pemfile::certs(&mut bundle.as_slice()).flatten());

    if added == 0 {
        return Err(DirectoryError::Tls(format!(
            "{ca_bundle_path} holds no certificate"
        )));
    }

    ClientConfig::builder_with_provider(Arc::new(rustls::crypto::aws_lc_rs::default_provider()))
        .with_safe_default_protocol_versions()
        .map_err(|error| DirectoryError::Tls(error.to_string()))
        .map(|builder| builder.with_root_certificates(roots).with_no_client_auth())
}

#[cfg(test)]
mod tests {
    use super::*;

    const RDS_BUNDLE: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/rds-ca-bundle.pem");

    #[test]
    fn only_a_local_database_goes_without_tls() {
        for (url, mode) in [
            ("postgres://u:p@db.example/gradiated", SslMode::Require),
            (
                "postgres://u:p@db.example/gradiated?sslmode=disable",
                SslMode::Require,
            ),
            (
                "postgres://u:p@db.example/gradiated?sslmode=prefer",
                SslMode::Require,
            ),
            (
                "postgres://u:p@db.example/gradiated?sslmode=verify-full",
                SslMode::Require,
            ),
            (
                "postgres://u:p@db.example/gradiated?sslmode=verify-ca",
                SslMode::Require,
            ),
            ("postgres://u:p@127.0.0.1/gradiated", SslMode::Disable),
            (
                "postgres://u:p@[::1]/gradiated?sslmode=require",
                SslMode::Disable,
            ),
            (
                "postgres://u:p@localhost/gradiated?sslmode=disable",
                SslMode::Disable,
            ),
        ] {
            assert_eq!(
                connection_config(url).unwrap().get_ssl_mode(),
                mode,
                "{url}"
            );
        }
    }

    #[test]
    fn the_rds_bundle_verifies_the_database() {
        assert!(tls_config(RDS_BUNDLE).is_ok());
    }

    #[test]
    fn an_unusable_bundle_is_refused() {
        let empty =
            std::env::temp_dir().join(format!("proxy-empty-bundle-{}.pem", std::process::id()));
        std::fs::write(&empty, "not a certificate").unwrap();

        for path in ["/nonexistent/bundle.pem", empty.to_str().unwrap()] {
            assert!(
                matches!(tls_config(path), Err(DirectoryError::Tls(_))),
                "{path}"
            );
        }

        std::fs::remove_file(empty).unwrap();
    }

    #[tokio::test]
    async fn a_remote_database_requires_the_bundle() {
        let missing = PostgresDirectory::connect("postgres://u:p@db.example/gradiated", None);

        assert!(matches!(missing, Err(DirectoryError::Tls(_))));
        assert!(PostgresDirectory::connect(
            "postgres://u:p@db.example/gradiated",
            Some(RDS_BUNDLE)
        )
        .is_ok());
    }
}
