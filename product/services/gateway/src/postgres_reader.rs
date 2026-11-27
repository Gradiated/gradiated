use std::{net::IpAddr, str::FromStr, sync::Arc, time::Duration};

use chrono::{DateTime, TimeDelta, Utc};
use deadpool_postgres::{Manager, ManagerConfig, Pool, RecyclingMethod, Runtime, Timeouts};
use rustls::ClientConfig;
use thiserror::Error;
use tokio_postgres::{
    config::{Host, SslMode},
    Config, NoTls, Row,
};
use tokio_postgres_rustls::MakeRustlsConnect;
use uuid::Uuid;

/// PostgreSQL is the source of truth and Valkey caches what this returns. The
/// role this connects with is read-only.
#[derive(Clone)]
pub struct PostgresReader {
    pool: Pool,
}

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

/// Orders as the ledger query does: by `created_at`, then by `id`.
#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct LedgerPosition {
    pub created_at: DateTime<Utc>,
    pub id: Uuid,
}

impl LedgerPosition {
    pub fn replay_cursor(self) -> Self {
        Self {
            created_at: self.created_at - LEDGER_REPLAY_WINDOW,
            id: Uuid::nil(),
        }
    }

    #[cfg(test)]
    pub fn after_balance_at(created_at: DateTime<Utc>) -> Self {
        Self {
            created_at,
            id: Uuid::max(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AccountRecord {
    pub organization_kind: String,
    pub organization_status: String,
    pub billing_mode: String,
    pub seed: BalanceSeed,
}

/// Seeds the operational balance exactly once; the gateway replays later ledger
/// entries on top of it.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct BalanceSeed {
    pub balance: i64,
    /// The latest ledger entry the balance includes, or the Unix epoch and the nil
    /// id when the ledger is empty.
    pub ledger_head: LedgerPosition,
    /// Entries the balance includes that a replay from the head fetches again.
    pub replay_window_entries: Vec<Uuid>,
}

// Every replica holds up to this many connections, so the gateway's share of RDS
// max_connections is POOL_SIZE times maxReplicaCount. Records are cached in Valkey,
// so PostgreSQL sees only cache misses.
const POOL_SIZE: usize = 6;
// Fail a request instead of queueing it forever when the pool is exhausted.
const POOL_TIMEOUT: Duration = Duration::from_secs(2);

/// Ledger writers stamp `created_at` on their own hosts, so under clock skew, or
/// within one millisecond where UUIDv7 ids order at random, an entry can commit
/// after one with a later (created_at, id). A replay therefore reaches back this
/// far behind its watermark, and the applied-transaction set drops what the
/// balance already holds. The window also covers the watermark, which Valkey keeps
/// in milliseconds while PostgreSQL keeps microseconds.
const LEDGER_REPLAY_WINDOW: TimeDelta = TimeDelta::seconds(30);

const CREDENTIAL_QUERY: &str = "\
select json_build_object(
    'api_key_id', id,
    'organization_id', organization_id,
    'workspace_id', workspace_id,
    'expires_at', expires_at,
    'revoked_at', revoked_at,
    'openrouter_channel', exists (
      select 1 from organizations
      where organizations.id = api_keys.organization_id
        and organizations.kind = 'distribution_channel'
        and organizations.name = 'OpenRouter'
    )
  )::text
from api_keys
where digest = $1";

/// `<slug>/<task>` names the task's production version and `<slug>/<task>/<version>`
/// one version. Only tasks that claimed their name as a model resolve.
const ADAPTER_QUERY: &str = "\
select case when task_versions.id is null then 'null' else json_build_object(
    'workspace_id', tasks.workspace_id,
    'organization_slug', organizations.slug,
    'task_name', tasks.name,
    'version_id', task_versions.id,
    'name', task_versions.name,
    'status', task_versions.status,
    'size_bytes', task_versions.adapter->'size_bytes',
    'base_model_id', task_versions.base_model_id,
    'base_model_revision', coalesce(task_versions.adapter->>'validated_base_model_revision', task_versions.adapter->>'base_model_revision', ''),
    'sha256', task_versions.adapter->>'sha256',
    'format', coalesce(task_versions.adapter->>'format', 'peft_lora'),
    'num_tokens', task_versions.adapter->'num_tokens',
    'source_kind', task_versions.adapter->'source'->>'kind',
    'eval_only', tasks.purpose = 'eval'
)::text end
from tasks
join workspaces on workspaces.id = tasks.workspace_id
join organizations on organizations.id = tasks.organization_id and organizations.slug = $2
left join task_versions on task_versions.task_id = tasks.id
    and task_versions.workspace_id = tasks.workspace_id
    and case when $4::text is null then task_versions.id = tasks.production_version_id
        else task_versions.name = $4 end
where tasks.workspace_id = $1 and tasks.name = $3
    and workspaces.archived_at is null and organizations.status = 'active'";

const WORKSPACE_QUERY: &str = "\
select json_build_object(
    'organization_id', organization_id,
    'workspace_id', id,
    'archived_at', archived_at
  )::text
from workspaces
where id = $1";

/// Routing tries deployments in this order.
const MODEL_QUERY: &str = "\
select json_build_object(
    'id', models.id,
    'aliases', models.aliases,
    'name', models.name,
    'status', models.status,
    'properties', models.properties,
    'openrouter_model_id', models.openrouter_model_id,
    'tokenizer', case when models.tokenizer_path is null or models.tokenizer_revision is null then null
      else json_build_object('path', models.tokenizer_path, 'revision', models.tokenizer_revision) end,
    'organization_id', models.organization_id,
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
           or (
             model_deployments.model_id = any(models.aliases)
             and (coalesce(model_deployments.release->>'protocol', '') = 'system_one')
               = (models.type = 'decision')
           )
      ),
      '[]'::json
    )
  )::text
from models
where $1 = any(models.aliases)
   or (models.id = $1 and (models.status <> 'retired' or not exists (
       select 1 from models aliased where $1 = any(aliased.aliases)
   )))";

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

/// One statement reads the balance and the ledger head, so both come from the
/// same snapshot. Every ledger writer updates the balance in the transaction that
/// inserts the entry.
const ACCOUNT_QUERY: &str = "\
select
    organizations.kind,
    organizations.status,
    billing_accounts.mode,
    billing_accounts.balance,
    coalesce(head.created_at, 'epoch'),
    coalesce(head.id, '00000000-0000-0000-0000-000000000000'),
    coalesce(
      (
        select array_agg(replayable.id)
        from balance_transactions replayable
        where replayable.organization_id = organizations.id
          and replayable.created_at
            >= date_trunc('milliseconds', head.created_at) - make_interval(secs => $2)
          and replayable.source_type <> 'generation_settlement_batch'
      ),
      '{}'
    )
from organizations
join billing_accounts on billing_accounts.organization_id = organizations.id
left join lateral (
    select created_at, id
    from balance_transactions
    where balance_transactions.organization_id = organizations.id
    order by created_at desc, id desc
    limit 1
  ) head on true
where organizations.id = $1";

impl PostgresReader {
    pub fn connect(url: &str, ca_bundle_path: Option<&str>) -> Result<Self, PostgresError> {
        let config = connection_config(url)?;
        let manager_config = ManagerConfig {
            recycling_method: RecyclingMethod::Fast,
        };
        let manager = if config.get_ssl_mode() == SslMode::Disable {
            Manager::from_config(config, NoTls, manager_config)
        } else {
            let tls = MakeRustlsConnect::new(tls_config(ca_bundle_path)?);
            Manager::from_config(config, tls, manager_config)
        };

        Ok(Self {
            pool: Pool::builder(manager)
                .max_size(POOL_SIZE)
                .timeouts(Timeouts {
                    wait: Some(POOL_TIMEOUT),
                    create: Some(POOL_TIMEOUT),
                    recycle: Some(POOL_TIMEOUT),
                })
                .runtime(Runtime::Tokio1)
                .build()
                .map_err(PostgresError::PoolBuild)?,
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

    pub async fn private_adapter_json(
        &self,
        workspace_id: Uuid,
        model: &str,
    ) -> Result<Option<String>, PostgresError> {
        let mut segments = model.splitn(3, '/');
        let (Some(slug), Some(task)) = (segments.next(), segments.next()) else {
            return Ok(None);
        };
        let slug = slug.to_ascii_lowercase();
        let version = segments.next();

        self.record(ADAPTER_QUERY, &[&workspace_id, &slug, &task, &version])
            .await
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
            .query_opt(
                ACCOUNT_QUERY,
                &[&organization_id, &LEDGER_REPLAY_WINDOW.as_seconds_f64()],
            )
            .await?;

        row.map(account_record).transpose()
    }

    pub async fn balance_transactions_after(
        &self,
        organization_id: Uuid,
        cursor: LedgerPosition,
        limit: u16,
    ) -> Result<Vec<BalanceTransaction>, PostgresError> {
        let rows = self
            .client()
            .await?
            .query(
                BALANCE_TRANSACTIONS_QUERY,
                &[
                    &organization_id,
                    &cursor.created_at,
                    &cursor.id,
                    &i64::from(limit),
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

    async fn record(
        &self,
        query: &str,
        parameters: &[&(dyn tokio_postgres::types::ToSql + Sync)],
    ) -> Result<Option<String>, PostgresError> {
        let row = self.client().await?.query_opt(query, parameters).await?;

        row.map(|row| Ok(row.try_get(0)?)).transpose()
    }

    async fn client(&self) -> Result<deadpool_postgres::Object, PostgresError> {
        Ok(self.pool.get().await?)
    }
}

fn account_record(row: Row) -> Result<AccountRecord, PostgresError> {
    Ok(AccountRecord {
        organization_kind: row.try_get(0)?,
        organization_status: row.try_get(1)?,
        billing_mode: row.try_get(2)?,
        seed: BalanceSeed {
            balance: row.try_get(3)?,
            ledger_head: LedgerPosition {
                created_at: row.try_get(4)?,
                id: row.try_get(5)?,
            },
            replay_window_entries: row.try_get(6)?,
        },
    })
}

/// `tokio-postgres` accepts only libpq's `disable`, `prefer` and `require`, while
/// this repository's connection strings ask for `verify-full`. That mode wants the
/// certificate chain and the hostname checked, and the Rustls configuration below
/// always checks both, so the mode is translated rather than weakened.
///
/// `prefer`, which is also the default, continues in plaintext when the server
/// declines TLS. That is acceptable only on this machine, where the local
/// PostgreSQL has no TLS, so a remote server must use it.
fn connection_config(url: &str) -> Result<Config, PostgresError> {
    let url = url
        .replace("sslmode=verify-full", "sslmode=require")
        .replace("sslmode=verify-ca", "sslmode=require");
    let mut config = Config::from_str(&url).map_err(PostgresError::Configuration)?;

    if config.get_ssl_mode() == SslMode::Prefer && !config.get_hosts().iter().all(is_loopback) {
        config.ssl_mode(SslMode::Require);
    }

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
    Configuration(#[source] tokio_postgres::Error),
    #[error("PostgreSQL query failed: {0}")]
    Query(#[from] tokio_postgres::Error),
    #[error("PostgreSQL pool could not be built: {0}")]
    PoolBuild(#[source] deadpool_postgres::BuildError),
    #[error("PostgreSQL connection is unavailable: {0}")]
    Pool(#[from] deadpool_postgres::PoolError),
    #[error("PostgreSQL TLS configuration is invalid: {0}")]
    Tls(String),
}

#[cfg(test)]
#[path = "postgres_reader_tests.rs"]
mod tests;

#[cfg(test)]
mod connection_tests {
    use std::path::PathBuf;

    use super::*;

    const RDS_CA_BUNDLE: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/rds-ca-bundle.pem");

    struct Bundle(PathBuf);

    impl Bundle {
        fn holding(contents: &str) -> Self {
            let path = std::env::temp_dir().join(format!("gateway-ca-{}.pem", Uuid::now_v7()));
            std::fs::write(&path, contents).unwrap();

            Self(path)
        }

        fn path(&self) -> &str {
            self.0.to_str().unwrap()
        }
    }

    impl Drop for Bundle {
        fn drop(&mut self) {
            let _ = std::fs::remove_file(&self.0);
        }
    }

    #[test]
    fn a_remote_server_must_use_tls() {
        for (url, mode) in [
            ("postgres://u:p@db.example/gradiated", SslMode::Require),
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
            ("postgres://u:p@127.0.0.1/gradiated", SslMode::Prefer),
            ("postgres://u:p@localhost/gradiated", SslMode::Prefer),
            (
                "postgres://u:p@127.0.0.1/gradiated?sslmode=disable",
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
    fn an_unparseable_connection_string_is_a_configuration_error() {
        let result = PostgresReader::connect("postgres://127.0.0.1/gradiated?sslmode=bogus", None);

        assert!(matches!(result, Err(PostgresError::Configuration(_))));
    }

    #[test]
    fn the_rds_bundle_builds_a_tls_configuration() {
        assert!(tls_config(Some(RDS_CA_BUNDLE)).is_ok());
    }

    #[test]
    fn an_unreadable_bundle_is_a_tls_error() {
        let result = tls_config(Some("/nonexistent/rds-ca-bundle.pem"));

        assert!(matches!(result, Err(PostgresError::Tls(_))));
    }

    #[test]
    fn a_bundle_without_a_certificate_is_a_tls_error() {
        let bundle = Bundle::holding("");

        let result = tls_config(Some(bundle.path()));

        assert!(
            matches!(&result, Err(PostgresError::Tls(message)) if message.ends_with("holds no certificate"))
        );
    }

    #[test]
    fn an_invalid_certificate_entry_is_a_tls_error() {
        let bundle =
            Bundle::holding("-----BEGIN CERTIFICATE-----\n!!!\n-----END CERTIFICATE-----\n");

        let result = tls_config(Some(bundle.path()));

        assert!(matches!(result, Err(PostgresError::Tls(_))));
    }
}

#[cfg(test)]
mod account_seed_tests {
    use chrono::TimeZone;

    use super::*;

    const LOCAL_URL: &str =
        "postgres://gradiated:gradiated@127.0.0.1:5432/gradiated?sslmode=disable";

    struct Tenant {
        client: tokio_postgres::Client,
        organization_id: Uuid,
    }

    impl Tenant {
        async fn with_balance(balance: i64) -> Self {
            let (client, connection) = tokio_postgres::connect(LOCAL_URL, NoTls).await.unwrap();
            tokio::spawn(connection);
            let organization_id = Uuid::now_v7();

            client
                .execute(
                    "insert into organizations (id, kind, name, status)
                     values ($1, 'customer', $2, 'active')",
                    &[&organization_id, &format!("seed-{organization_id}")],
                )
                .await
                .unwrap();
            client
                .execute(
                    "insert into billing_accounts (organization_id, mode, balance)
                     values ($1, 'prepaid', $2)",
                    &[&organization_id, &balance],
                )
                .await
                .unwrap();

            Self {
                client,
                organization_id,
            }
        }

        async fn record_entry(&self, source_type: &str, created_at: &str) -> LedgerPosition {
            let id = Uuid::now_v7();
            let row = self
                .client
                .query_one(
                    "insert into balance_transactions
                       (id, organization_id, type, amount, balance_after, source_type,
                        source_id, created_at)
                     values ($1, $2, 'adjustment', 1, 1, $3, $4, $5::text::timestamptz)
                     returning created_at",
                    &[
                        &id,
                        &self.organization_id,
                        &source_type,
                        &id.to_string(),
                        &created_at,
                    ],
                )
                .await
                .unwrap();

            LedgerPosition {
                created_at: row.get(0),
                id,
            }
        }

        fn reader() -> PostgresReader {
            PostgresReader::connect(LOCAL_URL, None).unwrap()
        }

        async fn delete(self) {
            self.client
                .execute(
                    "delete from organizations where id = $1",
                    &[&self.organization_id],
                )
                .await
                .unwrap();
        }

        async fn read_and_delete(self) -> AccountRecord {
            let record = Self::reader().account(self.organization_id).await;
            self.delete().await;

            record.unwrap().unwrap()
        }
    }

    #[tokio::test]
    #[ignore = "requires the local Compose PostgreSQL with migrations applied"]
    async fn paging_by_position_visits_entries_that_share_a_timestamp_once() {
        let tenant = Tenant::with_balance(0).await;
        let mut recorded = Vec::new();
        for _ in 0..5 {
            recorded.push(
                tenant
                    .record_entry("operator", "2026-09-23 12:00:00.000000+00")
                    .await,
            );
        }
        recorded.sort();

        let reader = Tenant::reader();
        let mut cursor = LedgerPosition {
            created_at: Utc.timestamp_opt(0, 0).unwrap(),
            id: Uuid::nil(),
        };
        let mut visited = Vec::new();
        loop {
            let page = reader
                .balance_transactions_after(tenant.organization_id, cursor, 2)
                .await
                .unwrap();
            let Some(last) = page.last() else {
                break;
            };

            cursor = last.position();
            visited.extend(page.iter().map(BalanceTransaction::position));
        }
        tenant.delete().await;

        assert_eq!(visited, recorded);
    }

    #[tokio::test]
    #[ignore = "requires the local Compose PostgreSQL with migrations applied"]
    async fn the_seed_names_the_ledger_head_and_the_entries_in_its_replay_window() {
        let tenant = Tenant::with_balance(3).await;
        tenant
            .record_entry("operator", "2026-09-23 11:59:30.122999+00")
            .await;
        let within_window = tenant
            .record_entry("operator", "2026-09-23 11:59:30.123000+00")
            .await;
        let same_millisecond = tenant
            .record_entry("operator", "2026-09-23 12:00:00.123456+00")
            .await;
        let head = tenant
            .record_entry(
                "generation_settlement_batch",
                "2026-09-23 12:00:00.123789+00",
            )
            .await;

        let seed = tenant.read_and_delete().await.seed;

        assert_eq!(seed.balance, 3);
        assert_eq!(seed.ledger_head, head);
        let mut replayed = seed.replay_window_entries;
        replayed.sort();
        assert_eq!(replayed, vec![within_window.id, same_millisecond.id]);
    }

    #[tokio::test]
    #[ignore = "requires the local Compose PostgreSQL with migrations applied"]
    async fn an_empty_ledger_seeds_from_the_epoch() {
        let tenant = Tenant::with_balance(0).await;

        let seed = tenant.read_and_delete().await.seed;

        assert_eq!(
            seed.ledger_head,
            LedgerPosition {
                created_at: Utc.timestamp_opt(0, 0).unwrap(),
                id: Uuid::nil(),
            }
        );
        assert!(seed.replay_window_entries.is_empty());
    }
}
