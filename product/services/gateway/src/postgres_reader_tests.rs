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
    PostgresReader::connect(LOCAL_URL, None)
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
                "insert into organizations (id, kind, name, status)
                 values ('{organization_id}', 'customer', 'reader-test', 'active');
                 insert into billing_accounts (organization_id, mode, balance)
                 values ('{organization_id}', 'prepaid', 1000);
                 insert into workspaces (id, organization_id, name, is_default)
                 values ('{workspace_id}', '{organization_id}', 'Default', true);"
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
                "insert into models (id, name, status, properties)
                 values ($1, $2, 'available', $3::text::jsonb)",
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

    async fn remove(self, reader: &PostgresReader) {
        let client = reader.client().await.unwrap();

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
