use std::{str::FromStr, sync::Arc};

use chrono::{DateTime, Utc};
use deadpool_postgres::{Manager, ManagerConfig, Pool, RecyclingMethod};
use rustls::ClientConfig;
use thiserror::Error;
use tokio_postgres::{Config, NoTls, Row};
use tokio_postgres_rustls::MakeRustlsConnect;
use uuid::Uuid;

/// Reads the authoritative identity and catalog records. PostgreSQL is the source
/// of truth and Valkey caches what this returns, never the other way round. Every
/// record comes back as the JSON the gateway already understands, so the value that
/// is cached and the value that is deserialized are the same bytes. This type only
/// ever selects; the role it connects with holds no write privilege.
#[derive(Clone)]
pub struct PostgresReader {
    pool: Pool,
}

/// One ledger entry that has not yet reached the operational balance.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BalanceTransaction {
    pub id: Uuid,
    pub amount: i64,
    pub created_at: DateTime<Utc>,
}

impl BalanceTransaction {
    pub fn position(&self) -> LedgerPosition {
        LedgerPosition {
            created_at: self.created_at,
            id: self.id,
        }
    }
}

/// A place in the ledger, ordered the way the query orders it.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LedgerPosition {
    pub created_at: DateTime<Utc>,
    pub id: Uuid,
}

impl LedgerPosition {
    /// The position a seeded balance starts from. The id is the highest possible
    /// one, so entries sharing the source balance's timestamp stay excluded, which
    /// is what the balance already included.
    pub fn after_balance_at(created_at: DateTime<Utc>) -> Self {
        Self {
            created_at,
            id: Uuid::max(),
        }
    }
}

/// Every field the account hash needs on first write. `balance` and
/// `balance_updated_at` seed the operational balance exactly once; the worker
/// replays later transactions on top of that seed.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AccountRecord {
    pub organization_kind: String,
    pub organization_status: String,
    pub billing_mode: String,
    pub balance: i64,
    pub balance_updated_at: DateTime<Utc>,
}

const CREDENTIAL_QUERY: &str = "\
select json_build_object(
    'api_key_id', id,
    'organization_id', organization_id,
    'workspace_id', workspace_id,
    'expires_at', expires_at,
    'revoked_at', revoked_at
  )::text
from api_keys
where digest = $1";

const WORKSPACE_QUERY: &str = "\
select json_build_object(
    'organization_id', organization_id,
    'workspace_id', id,
    'archived_at', archived_at
  )::text
from workspaces
where id = $1";

/// Deployments are ordered exactly as the projector ordered them, so routing sees
/// the same candidate order it always has.
const MODEL_QUERY: &str = "\
select json_build_object(
    'id', models.id,
    'name', models.name,
    'status', models.status,
    'properties', models.properties,
    'deployments', coalesce(
      (
        select json_agg(
            json_build_object(
              'id', model_deployments.id,
              'status', model_deployments.status,
              'provider', model_deployments.provider,
              'region', model_deployments.region,
              'fault_domain', model_deployments.fault_domain,
              'service_url', model_deployments.service_url,
              'release', model_deployments.release
            )
            order by model_deployments.created_at, model_deployments.id
          )
        from model_deployments
        where model_deployments.model_id = models.id
      ),
      '[]'::json
    )
  )::text
from models
where models.id = $1";

const MODEL_IDS_QUERY: &str = "select id from models order by id";

/// Settlement batches are the charges this gateway already applied to the
/// operational balance, so replaying them would double-count usage.
/// The cursor is the (created_at, id) pair, not the timestamp alone: entries can
/// share a timestamp, and a batch that ends between two of them must resume at the
/// next entry rather than skip the rest of that instant. The
/// (organization_id, created_at, id) index serves this directly.
const BALANCE_TRANSACTIONS_QUERY: &str = "\
select id, amount, created_at
from balance_transactions
where organization_id = $1
  and (created_at, id) > ($2, $3)
  and source_type <> 'generation_settlement_batch'
order by created_at, id
limit $4";

const ACCOUNT_QUERY: &str = "\
select
    organizations.kind,
    organizations.status,
    billing_accounts.mode,
    billing_accounts.balance,
    billing_accounts.updated_at
from organizations
join billing_accounts on billing_accounts.organization_id = organizations.id
where organizations.id = $1";

impl PostgresReader {
    /// Uses TLS unless the connection string opts out, which only a local
    /// PostgreSQL without TLS does.
    pub fn connect(url: &str, ca_bundle_path: Option<&str>) -> Result<Self, PostgresError> {
        let url = &translated_ssl_mode(url);
        let config = Config::from_str(url)?;
        let manager_config = ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        };
        let manager = if requires_tls(url) {
            let tls = MakeRustlsConnect::new(tls_config(ca_bundle_path)?);
            Manager::from_config(config, tls, manager_config)
        } else {
            Manager::from_config(config, NoTls, manager_config)
        };

        Ok(Self {
            pool: Pool::builder(manager)
                .max_size(POOL_SIZE)
                .build()
                .map_err(|error| PostgresError::Pool(error.to_string()))?,
        })
    }

    pub async fn ping(&self) -> Result<(), PostgresError> {
        self.client().await?.query_one("select 1", &[]).await?;

        Ok(())
    }

    pub async fn credential_json(&self, digest: &[u8]) -> Result<Option<String>, PostgresError> {
        self.record(CREDENTIAL_QUERY, &[&digest]).await
    }

    pub async fn workspace_json(
        &self,
        workspace_id: Uuid,
    ) -> Result<Option<String>, PostgresError> {
        self.record(WORKSPACE_QUERY, &[&workspace_id]).await
    }

    pub async fn model_json(&self, model_id: &str) -> Result<Option<String>, PostgresError> {
        self.record(MODEL_QUERY, &[&model_id]).await
    }

    pub async fn model_ids(&self) -> Result<Vec<String>, PostgresError> {
        let rows = self.client().await?.query(MODEL_IDS_QUERY, &[]).await?;

        rows.iter().map(|row| Ok(row.try_get(0)?)).collect()
    }

    pub async fn account(
        &self,
        organization_id: Uuid,
    ) -> Result<Option<AccountRecord>, PostgresError> {
        let row = self
            .client()
            .await?
            .query_opt(ACCOUNT_QUERY, &[&organization_id])
            .await?;

        row.map(account_record).transpose()
    }

    /// Ledger entries after the position the account hash already includes.
    pub async fn balance_transactions_after(
        &self,
        organization_id: Uuid,
        watermark: LedgerPosition,
        limit: i64,
    ) -> Result<Vec<BalanceTransaction>, PostgresError> {
        let rows = self
            .client()
            .await?
            .query(
                BALANCE_TRANSACTIONS_QUERY,
                &[
                    &organization_id,
                    &watermark.created_at,
                    &watermark.id,
                    &limit,
                ],
            )
            .await?;

        rows.into_iter()
            .map(|row| {
                Ok(BalanceTransaction {
                    id: row.try_get(0)?,
                    amount: row.try_get(1)?,
                    created_at: row.try_get(2)?,
                })
            })
            .collect()
    }

    /// Lets the integration tests exercise the digest comparison with a digest the
    /// database actually holds.
    #[cfg(test)]
    pub(crate) async fn any_credential_digest(&self) -> Result<Option<Vec<u8>>, PostgresError> {
        let row = self
            .client()
            .await?
            .query_opt("select digest from api_keys limit 1", &[])
            .await?;

        row.map(|row| Ok(row.try_get(0)?)).transpose()
    }

    async fn record(
        &self,
        query: &str,
        parameters: &[&(dyn tokio_postgres::types::ToSql + Sync)],
    ) -> Result<Option<String>, PostgresError> {
        let row = self.client().await?.query_opt(query, parameters).await?;

        row.map(|row| Ok(row.try_get(0)?)).transpose()
    }

    async fn client(&self) -> Result<deadpool_postgres::Object, PostgresError> {
        self.pool
            .get()
            .await
            .map_err(|error| PostgresError::Pool(error.to_string()))
    }
}

fn account_record(row: Row) -> Result<AccountRecord, PostgresError> {
    Ok(AccountRecord {
        organization_kind: row.try_get(0)?,
        organization_status: row.try_get(1)?,
        billing_mode: row.try_get(2)?,
        balance: row.try_get(3)?,
        balance_updated_at: row.try_get(4)?,
    })
}

const POOL_SIZE: usize = 16;

/// `tokio-postgres` accepts only libpq's `disable`, `prefer` and `require`, while
/// this repository's connection strings ask for `verify-full`. That mode wants the
/// certificate chain and the hostname checked, and the Rustls configuration below
/// always checks both, so the mode is translated rather than weakened. Passing it
/// through unchanged makes the connection string fail to parse at startup.
fn translated_ssl_mode(url: &str) -> String {
    url.replace("sslmode=verify-full", "sslmode=require")
        .replace("sslmode=verify-ca", "sslmode=require")
}

fn requires_tls(url: &str) -> bool {
    !url.contains("sslmode=disable")
}

/// Names the provider rather than reading the process-level default, so this does
/// not depend on something else having installed one first. Rustls verifies the
/// chain against these roots and checks the hostname, which is what the connection
/// strings' `verify-full` asks for.
///
/// Amazon RDS presents a chain that roots in its own certificate authority, which
/// is not in a host's trust store, so `ca_bundle_path` supplies it. Without it a
/// managed instance cannot be verified at all, only trusted blindly.
fn tls_config(ca_bundle_path: Option<&str>) -> Result<ClientConfig, PostgresError> {
    let mut roots = rustls::RootCertStore::empty();
    for certificate in rustls_native_certs::load_native_certs().certs {
        roots
            .add(certificate)
            .map_err(|error| PostgresError::Tls(error.to_string()))?;
    }

    if let Some(path) = ca_bundle_path {
        let bundle =
            std::fs::read(path).map_err(|error| PostgresError::Tls(format!("{path}: {error}")))?;
        let mut added = 0;
        for certificate in rustls_pemfile::certs(&mut bundle.as_slice()) {
            roots
                .add(certificate.map_err(|error| PostgresError::Tls(error.to_string()))?)
                .map_err(|error| PostgresError::Tls(error.to_string()))?;
            added += 1;
        }
        if added == 0 {
            return Err(PostgresError::Tls(format!("{path} holds no certificate")));
        }
    }

    ClientConfig::builder_with_provider(Arc::new(rustls::crypto::aws_lc_rs::default_provider()))
        .with_safe_default_protocol_versions()
        .map_err(|error| PostgresError::Tls(error.to_string()))
        .map(|builder| builder.with_root_certificates(roots).with_no_client_auth())
}

#[derive(Debug, Error)]
pub enum PostgresError {
    #[error("PostgreSQL connection string is invalid: {0}")]
    Configuration(#[from] tokio_postgres::Error),
    #[error("PostgreSQL pool is unavailable: {0}")]
    Pool(String),
    #[error("PostgreSQL TLS configuration is invalid: {0}")]
    Tls(String),
}

#[cfg(test)]
#[path = "postgres_reader_tests.rs"]
mod tests;
