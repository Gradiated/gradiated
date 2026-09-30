use std::{fs, io, net::IpAddr, str::FromStr, sync::Arc, time::Duration};

use deadpool_postgres::{
    Manager, ManagerConfig, Object, Pool, PoolError, RecyclingMethod, Runtime, Timeouts,
};
use tokio_postgres::{config::Host, Config, NoTls};
use tokio_postgres_rustls::MakeRustlsConnect;

#[derive(Clone)]
pub struct PostgresService {
    pool: Pool,
}

const DATABASE_TIMEOUT: Duration = Duration::from_secs(2);

impl PostgresService {
    pub fn new(url: &str, ca_bundle: Option<&str>) -> io::Result<Self> {
        // The driver has no verify-* modes; rustls verifies remote certificates and hostnames.
        let url = url
            .replace("sslmode=verify-full", "sslmode=require")
            .replace("sslmode=verify-ca", "sslmode=require");
        let mut config = Config::from_str(&url)
            .map_err(|_| io::Error::other("invalid PostgreSQL configuration"))?;
        let local = config.get_hosts().iter().all(|host| match host {
            Host::Tcp(name) => {
                name == "localhost" || name.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
            }
            Host::Unix(_) => true,
        });
        config.connect_timeout(DATABASE_TIMEOUT);
        config.ssl_mode(if local {
            tokio_postgres::config::SslMode::Disable
        } else {
            tokio_postgres::config::SslMode::Require
        });

        let manager_config = ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        };
        let manager = if local {
            Manager::from_config(config, NoTls, manager_config)
        } else {
            let bundle = fs::read(ca_bundle.ok_or_else(|| {
                io::Error::other("DATABASE_CA_BUNDLE_PATH is required for a remote database")
            })?)?;
            let mut roots = rustls::RootCertStore::empty();
            let (added, _) = roots
                .add_parsable_certificates(rustls_pemfile::certs(&mut bundle.as_slice()).flatten());
            if added == 0 {
                return Err(io::Error::other("database CA bundle has no certificates"));
            }

            let tls = rustls::ClientConfig::builder_with_provider(Arc::new(
                rustls::crypto::aws_lc_rs::default_provider(),
            ))
            .with_safe_default_protocol_versions()
            .map_err(io::Error::other)?
            .with_root_certificates(roots)
            .with_no_client_auth();
            Manager::from_config(config, MakeRustlsConnect::new(tls), manager_config)
        };

        Pool::builder(manager)
            .max_size(1)
            .runtime(Runtime::Tokio1)
            .timeouts(Timeouts {
                wait: Some(DATABASE_TIMEOUT),
                create: Some(DATABASE_TIMEOUT),
                recycle: Some(DATABASE_TIMEOUT),
            })
            .build()
            .map(|pool| Self { pool })
            .map_err(io::Error::other)
    }

    pub async fn client(&self) -> Result<Object, PoolError> {
        self.pool.get().await
    }
}
