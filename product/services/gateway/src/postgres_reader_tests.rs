//! Exercises the real queries against the local PostgreSQL.
//!
//! These tests need the Docker Compose PostgreSQL from `product/docker-compose.yml`
//! with migrations applied, so they are ignored by default. They exist because a
//! column name, a JSON shape or the digest comparison can only be wrong at
//! runtime, and every request depends on them.

use chrono::TimeZone;
use uuid::Uuid;

use super::*;
use crate::domain::{GatewayCredential, GatewayModel, GatewayWorkspace};

const LOCAL_URL: &str = "postgres://gradiated:gradiated@127.0.0.1:5432/gradiated?sslmode=disable";

fn local_reader() -> PostgresReader {
    PostgresReader::connect(
        &std::env::var("GATEWAY_TEST_DATABASE_URL").unwrap_or_else(|_| LOCAL_URL.to_owned()),
        None,
    )
    .expect("the local connection string should build a pool")
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn every_query_runs_against_the_local_schema() {
    let reader = local_reader();
    reader.ping().await.expect("local PostgreSQL should answer");

    // An absent record must be absent rather than an error: these exercise each
    // query's parameter binding, including the digest compared as bytes.
    assert_eq!(reader.credential_json(&[0u8; 32]).await.unwrap(), None);
    assert_eq!(reader.workspace_json(Uuid::nil()).await.unwrap(), None);
    assert_eq!(reader.model_json("absent/model").await.unwrap(), None);
    reader.model_ids().await.unwrap();
    assert_eq!(
        reader
            .private_adapter_json(Uuid::nil(), "absent/version")
            .await
            .unwrap(),
        None
    );
    assert_eq!(reader.account(Uuid::nil()).await.unwrap(), None);
    assert!(reader
        .balance_transactions_after(
            Uuid::nil(),
            LedgerPosition::after_balance_at(Utc.timestamp_opt(0, 0).unwrap()),
            10,
        )
        .await
        .unwrap()
        .is_empty());
}

struct Tenant {
    organization_id: Uuid,
    workspace_id: Uuid,
    digest: Vec<u8>,
    model_id: String,
}

impl Tenant {
    async fn insert(reader: &PostgresReader) -> Self {
        let organization_id = Uuid::now_v7();
        let workspace_id = Uuid::now_v7();
        let digest = [*organization_id.as_bytes(), *workspace_id.as_bytes()].concat();
        let model = crate::test_support::model(true);
        let record = crate::test_support::model_record(true);
        let model_id = format!("reader-test/{organization_id}");
        let deployment = &model.deployments[0];
        let client = reader.client().await.unwrap();

        client
            .batch_execute(&format!(
                "insert into organizations (id, kind, name, status, slug)
                 values ('{organization_id}', 'customer', 'reader-test', 'active', 'reader-{}');
                 insert into billing_accounts (organization_id, mode, balance)
                 values ('{organization_id}', 'prepaid', 1000);
                 insert into workspaces (id, organization_id, name, is_default)
                 values ('{workspace_id}', '{organization_id}', 'Default', true);",
                organization_id.simple()
            ))
            .await
            .unwrap();
        client
            .execute(
                "insert into api_keys (id, organization_id, workspace_id, name, digest)
                 values ($1, $2, $3, 'reader-test', $4)",
                &[&Uuid::now_v7(), &organization_id, &workspace_id, &digest],
            )
            .await
            .unwrap();
        client
            .execute(
                "insert into models (id, name, status, properties, openrouter_model_id)
                 values ($1, $2, 'available', $3::text::jsonb, 'author/reader-test')",
                &[&model_id, &model.name, &record["properties"].to_string()],
            )
            .await
            .unwrap();
        client
            .execute(
                "insert into model_deployments
                   (id, model_id, status, provider, region, fault_domain, service_url, release)
                 values ($1, $2, 'available', $3, $4, $5, $6, $7::text::jsonb)",
                &[
                    &Uuid::now_v7(),
                    &model_id,
                    &deployment.provider,
                    &deployment.region,
                    &deployment.fault_domain,
                    &deployment.service_url,
                    &serde_json::to_string(&deployment.release).unwrap(),
                ],
            )
            .await
            .unwrap();

        Self {
            organization_id,
            workspace_id,
            digest,
            model_id,
        }
    }

    fn name(&self, task_and_version: &str) -> String {
        format!(
            "reader-{}/{task_and_version}",
            self.organization_id.simple()
        )
    }

    async fn adapter(
        &self,
        reader: &PostgresReader,
        task_name: &str,
        version_name: &str,
    ) -> (Uuid, Uuid) {
        let client = reader.client().await.unwrap();
        let task = Uuid::now_v7();
        let run = Uuid::now_v7();
        let version = Uuid::now_v7();
        client
            .execute(
                "insert into tasks (id, organization_id, workspace_id, name, base_model_id) values ($1, $2, $3, $4, $5)",
                &[&task, &self.organization_id, &self.workspace_id, &task_name, &self.model_id],
            )
            .await
            .unwrap();
        client.execute("insert into training_runs (id, task_id, trigger, stage, base_model_id, input_cutoff, finished_at) values ($1, $2, 'manual', 'succeeded', $3, now(), now())", &[&run, &task, &self.model_id]).await.unwrap();
        let artifact = serde_json::json!({"format": "peft_lora", "artifact_uri": "s3://synthetic/adapter.tar.gz", "sha256": "a".repeat(64), "size_bytes": 1024, "rank": 2, "base_model_revision": "frozen-revision"}).to_string();
        client.execute("insert into task_versions (id, workspace_id, task_id, training_run_id, name, base_model_id, status, adapter) values ($1, $2, $3, $4, $5, $6, 'available', $7::text::jsonb)", &[&version, &self.workspace_id, &task, &run, &version_name, &self.model_id, &artifact]).await.unwrap();
        (task, version)
    }

    async fn remove(self, reader: &PostgresReader) {
        let client = reader.client().await.unwrap();

        client
            .execute(
                "delete from tasks where workspace_id = $1",
                &[&self.workspace_id],
            )
            .await
            .unwrap();
        client
            .execute(
                "delete from model_deployments where model_id = $1",
                &[&self.model_id],
            )
            .await
            .unwrap();
        client
            .execute("delete from models where id = $1", &[&self.model_id])
            .await
            .unwrap();
        client
            .batch_execute(&format!(
                "delete from api_keys where organization_id = '{0}';
                 delete from workspaces where organization_id = '{0}';
                 delete from billing_accounts where organization_id = '{0}';
                 delete from organizations where id = '{0}';",
                self.organization_id
            ))
            .await
            .unwrap();
    }
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn a_model_deserializes_into_the_type_the_gateway_serves() {
    let reader = local_reader();
    let tenant = Tenant::insert(&reader).await;

    assert!(reader.model_ids().await.unwrap().contains(&tenant.model_id));
    let record = reader
        .model_json(&tenant.model_id)
        .await
        .unwrap()
        .expect("the inserted model should be readable");
    let model: GatewayModel =
        serde_json::from_str(&record).expect("the query should build the served shape");

    assert_eq!(model.id, tenant.model_id);
    assert_eq!(model.deployments.len(), 1);
    assert_eq!(model.openrouter_model(), Some("author/reader-test"));
    model
        .properties
        .validate_for_serving()
        .expect("a catalog model should be servable");

    tenant.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn a_credential_and_its_workspace_deserialize_together() {
    let reader = local_reader();
    let tenant = Tenant::insert(&reader).await;

    let record = reader
        .credential_json(&tenant.digest)
        .await
        .unwrap()
        .expect("the digest should match its own row");
    let credential: GatewayCredential =
        serde_json::from_str(&record).expect("the query should build the served shape");
    assert_eq!(credential.workspace_id, tenant.workspace_id);
    assert_eq!(credential.organization_id, tenant.organization_id);
    assert_eq!(credential.openrouter_channel, Some(false));

    let organization = tenant.organization_id.to_string();
    let rename = |kind: &str, name: &str| {
        format!(
            "update organizations set kind = '{kind}', name = '{name}' where id = '{organization}'"
        )
    };
    for (kind, name, expected) in [
        ("distribution_channel", "OpenRouter", true),
        ("distribution_channel", "Another channel", false),
        ("customer", "OpenRouter", false),
    ] {
        reader
            .client()
            .await
            .unwrap()
            .batch_execute(&rename(kind, name))
            .await
            .unwrap();
        let record = reader
            .credential_json(&tenant.digest)
            .await
            .unwrap()
            .unwrap();
        let credential: GatewayCredential = serde_json::from_str(&record).unwrap();
        assert_eq!(
            credential.openrouter_channel,
            Some(expected),
            "{kind} {name}"
        );
    }

    let record = reader
        .workspace_json(credential.workspace_id)
        .await
        .unwrap()
        .expect("a key's workspace should exist");
    let workspace: GatewayWorkspace =
        serde_json::from_str(&record).expect("the query should build the served shape");
    assert_eq!(workspace.workspace_id, tenant.workspace_id);
    assert_eq!(workspace.organization_id, tenant.organization_id);

    let account = reader
        .account(tenant.organization_id)
        .await
        .unwrap()
        .expect("a key's organization should have a billing account");
    assert_eq!(account.organization_status, "active");

    tenant.remove(&reader).await;
}

/// The repository's connection strings use libpq's `verify-full`, which
/// `tokio-postgres` does not accept. Startup must not depend on noticing that.
#[test]
fn a_verify_full_connection_string_is_accepted() {
    for url in [
        "postgresql://u:p@host.example:5432/gradiated?sslmode=verify-full",
        "postgresql://u:p@host.example:5432/gradiated?sslmode=verify-ca",
        "postgresql://u:p@host.example:5432/gradiated?sslmode=require",
        "postgres://u:p@127.0.0.1:5432/gradiated?sslmode=disable",
    ] {
        assert!(
            PostgresReader::connect(url, None).is_ok(),
            "{url} should build a pool"
        );
    }
}

async fn insert_ledger_entry(
    client: &tokio_postgres::Client,
    organization: Uuid,
    id: Uuid,
    at: DateTime<Utc>,
    source_type: &str,
) {
    client
        .execute(
            "insert into balance_transactions
             (id, organization_id, type, amount, balance_after, source_type, source_id, created_at)
             values ($1, $2, 'credit', 20, 1020, $3, $4, $5)",
            &[&id, &organization, &source_type, &id.to_string(), &at],
        )
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn ledger_pages_keep_equal_timestamps_and_exclude_other_tenants_and_settlements() {
    let reader = local_reader();
    let tenant = Tenant::insert(&reader).await;
    let other = Tenant::insert(&reader).await;
    let at = Utc.timestamp_opt(1_786_800_000, 123_456_000).unwrap();
    let mut ids = [Uuid::now_v7(), Uuid::now_v7(), Uuid::now_v7()];
    ids.sort();
    let client = reader.client().await.unwrap();

    for id in ids.into_iter().rev() {
        insert_ledger_entry(&client, tenant.organization_id, id, at, "operator").await;
    }
    insert_ledger_entry(
        &client,
        other.organization_id,
        Uuid::now_v7(),
        at,
        "operator",
    )
    .await;
    insert_ledger_entry(
        &client,
        tenant.organization_id,
        Uuid::now_v7(),
        at,
        "generation_settlement_batch",
    )
    .await;

    let first = reader
        .balance_transactions_after(
            tenant.organization_id,
            LedgerPosition {
                created_at: at,
                id: Uuid::nil(),
            },
            2,
        )
        .await
        .unwrap();
    assert_eq!(
        first.iter().map(|entry| entry.id).collect::<Vec<_>>(),
        ids[..2]
    );
    assert!(first
        .iter()
        .all(|entry| entry.amount == 20 && entry.created_at == at));

    let second = reader
        .balance_transactions_after(tenant.organization_id, first[1].position(), 2)
        .await
        .unwrap();
    assert_eq!(
        second.iter().map(|entry| entry.id).collect::<Vec<_>>(),
        ids[2..]
    );
    assert!(reader
        .balance_transactions_after(tenant.organization_id, second[0].position(), 2,)
        .await
        .unwrap()
        .is_empty());

    drop(client);
    tenant.remove(&reader).await;
    other.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn account_seed_includes_only_replayable_entries_in_its_window() {
    let reader = local_reader();
    let tenant = Tenant::insert(&reader).await;
    let empty = reader
        .account(tenant.organization_id)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(empty.seed.balance, 1000);
    assert_eq!(
        empty.seed.ledger_head,
        LedgerPosition {
            created_at: DateTime::UNIX_EPOCH,
            id: Uuid::nil()
        }
    );
    assert!(empty.seed.replay_window_entries.is_empty());

    let at = Utc.timestamp_opt(1_786_800_000, 123_456_000).unwrap();
    let included = Uuid::now_v7();
    let head = Uuid::now_v7();
    let client = reader.client().await.unwrap();
    insert_ledger_entry(
        &client,
        tenant.organization_id,
        Uuid::now_v7(),
        at - TimeDelta::seconds(31),
        "operator",
    )
    .await;
    insert_ledger_entry(
        &client,
        tenant.organization_id,
        included,
        at - TimeDelta::seconds(29),
        "operator",
    )
    .await;
    insert_ledger_entry(
        &client,
        tenant.organization_id,
        head,
        at,
        "generation_settlement_batch",
    )
    .await;
    client
        .execute(
            "update billing_accounts set balance = 1060 where organization_id = $1",
            &[&tenant.organization_id],
        )
        .await
        .unwrap();

    let account = reader
        .account(tenant.organization_id)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(account.seed.balance, 1060);
    assert_eq!(
        account.seed.ledger_head,
        LedgerPosition {
            created_at: at,
            id: head
        }
    );
    assert_eq!(account.seed.replay_window_entries, vec![included]);
    assert_eq!(account.organization_kind, "customer");
    assert_eq!(account.billing_mode, "prepaid");

    drop(client);
    tenant.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn account_reads_never_expose_a_partially_committed_billing_transaction() {
    let reader = local_reader();
    let tenant = Tenant::insert(&reader).await;
    let mut client = reader.client().await.unwrap();
    let transaction = client.transaction().await.unwrap();
    let id = Uuid::now_v7();
    let at = Utc::now();
    transaction
        .execute(
            "insert into balance_transactions
         (id, organization_id, type, amount, balance_after, source_type, source_id, created_at)
         values ($1, $2, 'credit', 20, 1020, 'operator', $3, $4)",
            &[&id, &tenant.organization_id, &id.to_string(), &at],
        )
        .await
        .unwrap();
    transaction
        .execute(
            "update billing_accounts set balance = 1020 where organization_id = $1",
            &[&tenant.organization_id],
        )
        .await
        .unwrap();

    let before = reader
        .account(tenant.organization_id)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(before.seed.balance, 1000);
    assert_eq!(before.seed.ledger_head.id, Uuid::nil());
    transaction.commit().await.unwrap();

    let after = reader
        .account(tenant.organization_id)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(after.seed.balance, 1020);
    assert_eq!(after.seed.ledger_head.id, id);
    assert_eq!(after.seed.replay_window_entries, vec![id]);

    drop(client);
    tenant.remove(&reader).await;
}

async fn production(reader: &PostgresReader, task: Uuid, version: Option<Uuid>) {
    reader
        .client()
        .await
        .unwrap()
        .execute(
            "update tasks set production_version_id = $2 where id = $1",
            &[&task, &version],
        )
        .await
        .unwrap();
}

#[tokio::test]
#[ignore = "requires migrated PostgreSQL; GATEWAY_TEST_DATABASE_URL selects a disposable database"]
async fn adapter_query_reads_exact_versions_and_production_with_workspace_isolation() {
    let reader = local_reader();
    let owner = Tenant::insert(&reader).await;
    let other = Tenant::insert(&reader).await;
    let (task, version) = owner.adapter(&reader, "support", "triage-日本語-v1").await;
    let (_, other_version) = other.adapter(&reader, "support", "triage-日本語-v1").await;
    production(&reader, task, Some(version)).await;

    let exact = reader
        .private_adapter_json(owner.workspace_id, &owner.name("support/triage-日本語-v1"))
        .await
        .unwrap()
        .unwrap();
    let adapter: crate::PrivateAdapter = serde_json::from_str(&exact).unwrap();
    assert!(adapter.is_valid());
    assert_eq!(adapter.workspace_id, owner.workspace_id);
    assert_eq!(adapter.version_id, version);
    assert_eq!(adapter.base_model_id, owner.model_id);
    assert_eq!(adapter.base_model_revision, "frozen-revision");
    assert_eq!(adapter.size_bytes, 1024);
    assert_eq!(adapter.sha256, "a".repeat(64));
    assert_eq!(
        reader
            .private_adapter_json(owner.workspace_id, &owner.name("support"))
            .await
            .unwrap(),
        Some(exact)
    );
    let other_record = reader
        .private_adapter_json(other.workspace_id, &other.name("support/triage-日本語-v1"))
        .await
        .unwrap()
        .unwrap();
    let other_adapter: crate::PrivateAdapter = serde_json::from_str(&other_record).unwrap();
    assert_eq!(other_adapter.version_id, other_version);
    assert_eq!(
        reader
            .private_adapter_json(Uuid::nil(), &owner.name("support/triage-日本語-v1"))
            .await
            .unwrap(),
        None
    );
    assert_eq!(
        reader
            .private_adapter_json(owner.workspace_id, &owner.name("missing"))
            .await
            .unwrap(),
        None
    );

    owner.remove(&reader).await;
    other.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires migrated PostgreSQL; GATEWAY_TEST_DATABASE_URL selects a disposable database"]
async fn adapter_query_resolves_names_under_the_workspace_organization_slug() {
    let reader = local_reader();
    let owner = Tenant::insert(&reader).await;
    let other = Tenant::insert(&reader).await;
    let (task, version) = owner.adapter(&reader, "triage", "v1").await;
    production(&reader, task, Some(version)).await;
    other.adapter(&reader, "triage", "v1").await;
    let slug = format!("reader-{}", owner.organization_id.simple());
    let moved = format!("moved-{}", owner.organization_id.simple());
    let resolve = |model: String| {
        let reader = &reader;
        async move {
            reader
                .private_adapter_json(owner.workspace_id, &model)
                .await
                .unwrap()
                .and_then(|record| {
                    serde_json::from_str::<Option<crate::PrivateAdapter>>(&record).unwrap()
                })
        }
    };

    for model in [
        format!("{slug}/triage/v1"),
        format!("{}/triage", slug.to_uppercase()),
    ] {
        let adapter = resolve(model.clone()).await.expect(&model);
        assert_eq!(adapter.version_id, version, "{model}");
        assert_eq!(adapter.model_id(), format!("{slug}/triage/v1"));
        assert_eq!(
            adapter.runtime_name(),
            format!("{}/triage/v1", owner.workspace_id)
        );
    }
    let other_slug = format!("reader-{}", other.organization_id.simple());
    for model in [
        format!("{other_slug}/triage/v1"),
        format!("{slug}/triage/v2"),
        format!("{slug}/other"),
        "v1".to_owned(),
        "triage".to_owned(),
    ] {
        assert_eq!(resolve(model.clone()).await, None, "{model}");
    }

    reader
        .client()
        .await
        .unwrap()
        .execute(
            "update organizations set slug = $2 where id = $1",
            &[&owner.organization_id, &moved],
        )
        .await
        .unwrap();
    let adapter = resolve(format!("{moved}/triage/v1")).await.unwrap();
    assert_eq!(adapter.model_id(), format!("{moved}/triage/v1"));
    assert_eq!(resolve(format!("{slug}/triage/v1")).await, None);

    owner.remove(&reader).await;
    other.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires migrated PostgreSQL; GATEWAY_TEST_DATABASE_URL selects a disposable database"]
async fn adapter_query_requires_the_organization_slug() {
    let reader = local_reader();
    let owner = Tenant::insert(&reader).await;
    let (task, version) = owner.adapter(&reader, "task", "version").await;
    production(&reader, task, Some(version)).await;
    for name in ["task", "version", "task/version"] {
        assert_eq!(
            reader
                .private_adapter_json(owner.workspace_id, name)
                .await
                .unwrap(),
            None,
            "{name}"
        );
    }
    owner.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires migrated PostgreSQL; GATEWAY_TEST_DATABASE_URL selects a disposable database"]
async fn adapter_query_requires_a_claimed_model_name() {
    let reader = local_reader();
    let owner = Tenant::insert(&reader).await;
    let (task, _) = owner.adapter(&reader, "task", "version").await;
    let client = reader.client().await.unwrap();
    client
        .execute(
            "update tasks set organization_id = null where id = $1",
            &[&task],
        )
        .await
        .unwrap();
    assert_eq!(
        reader
            .private_adapter_json(owner.workspace_id, &owner.name("task/version"))
            .await
            .unwrap(),
        None
    );
    owner.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires migrated PostgreSQL; GATEWAY_TEST_DATABASE_URL selects a disposable database"]
async fn adapter_query_distinguishes_missing_pointers_and_projects_legacy_metadata() {
    let reader = local_reader();
    let owner = Tenant::insert(&reader).await;
    let (task, version) = owner.adapter(&reader, "task", "version").await;
    assert_eq!(
        reader
            .private_adapter_json(owner.workspace_id, &owner.name("task"))
            .await
            .unwrap(),
        Some("null".to_owned())
    );
    let (other_task, other_version) = owner.adapter(&reader, "other-task", "other-version").await;
    production(&reader, task, Some(other_version)).await;
    assert_eq!(
        reader
            .private_adapter_json(owner.workspace_id, &owner.name("task"))
            .await
            .unwrap(),
        Some("null".to_owned())
    );
    production(&reader, other_task, None).await;
    reader.client().await.unwrap().execute("update task_versions set adapter = adapter - 'base_model_revision', status = 'unavailable' where id = $1", &[&version]).await.unwrap();
    let record = reader
        .private_adapter_json(owner.workspace_id, &owner.name("task/version"))
        .await
        .unwrap()
        .unwrap();
    let adapter: crate::PrivateAdapter = serde_json::from_str(&record).unwrap();
    assert_eq!(adapter.base_model_revision, "");
    assert_eq!(adapter.status, "unavailable");
    assert!(!adapter.is_valid());
    owner.remove(&reader).await;
}

#[tokio::test]
#[ignore = "requires migrated PostgreSQL; GATEWAY_TEST_DATABASE_URL selects a disposable database"]
async fn adapter_query_excludes_archived_workspaces_and_suspended_organizations() {
    let reader = local_reader();
    let owner = Tenant::insert(&reader).await;
    let (task, version) = owner.adapter(&reader, "task", "version").await;
    production(&reader, task, Some(version)).await;
    let client = reader.client().await.unwrap();
    client
        .execute(
            "update workspaces set is_default = false, archived_at = now() where id = $1",
            &[&owner.workspace_id],
        )
        .await
        .unwrap();
    for name in [owner.name("task"), owner.name("task/version")] {
        assert_eq!(
            reader
                .private_adapter_json(owner.workspace_id, &name)
                .await
                .unwrap(),
            None
        );
    }
    client
        .execute(
            "update workspaces set archived_at = null where id = $1",
            &[&owner.workspace_id],
        )
        .await
        .unwrap();
    client
        .execute(
            "update organizations set status = 'suspended' where id = $1",
            &[&owner.organization_id],
        )
        .await
        .unwrap();
    for name in [owner.name("task"), owner.name("task/version")] {
        assert_eq!(
            reader
                .private_adapter_json(owner.workspace_id, &name)
                .await
                .unwrap(),
            None
        );
    }
    drop(client);
    owner.remove(&reader).await;
}
