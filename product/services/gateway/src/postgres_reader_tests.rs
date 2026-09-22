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
        .balance_transactions_after(Uuid::nil(), Utc.timestamp_opt(0, 0).unwrap(), 10)
        .await
        .unwrap()
        .is_empty());
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn a_model_deserializes_into_the_type_the_gateway_serves() {
    let reader = local_reader();
    let model_ids = reader.model_ids().await.expect("models should list");
    let model_id = model_ids
        .first()
        .expect("the local catalog should hold at least one model");

    let record = reader
        .model_json(model_id)
        .await
        .unwrap()
        .expect("the listed model should be readable");
    let model: GatewayModel =
        serde_json::from_str(&record).expect("the query should build the served shape");

    assert_eq!(&model.id, model_id);
    model
        .properties
        .validate_for_serving()
        .expect("a catalog model should be servable");
}

#[tokio::test]
#[ignore = "requires the local Compose PostgreSQL with migrations applied"]
async fn a_credential_and_its_workspace_deserialize_together() {
    let reader = local_reader();
    let Some(digest) = reader.any_credential_digest().await.unwrap() else {
        panic!("the local database should hold at least one API key");
    };

    let record = reader
        .credential_json(&digest)
        .await
        .unwrap()
        .expect("the digest should match its own row");
    let credential: GatewayCredential =
        serde_json::from_str(&record).expect("the query should build the served shape");

    let record = reader
        .workspace_json(credential.workspace_id)
        .await
        .unwrap()
        .expect("a key's workspace should exist");
    let workspace: GatewayWorkspace =
        serde_json::from_str(&record).expect("the query should build the served shape");

    assert_eq!(workspace.workspace_id, credential.workspace_id);
    assert_eq!(workspace.organization_id, credential.organization_id);

    let account = reader
        .account(credential.organization_id)
        .await
        .unwrap()
        .expect("a key's organization should have a billing account");
    assert!(!account.organization_status.is_empty());
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
