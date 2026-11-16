use std::{sync::Arc, time::Duration};

use chrono::{DateTime, Utc};
use object_store::{memory::InMemory, ObjectStore};
use tempfile::TempDir;
use uuid::{NoContext, Timestamp, Uuid};

use crate::{config::Store, record::SCHEMA, spool::Limits, Collector, CollectorConfig};

pub const TOKEN: &str = "test-token-with-at-least-32-characters";
pub const WORKSPACE: &str = "0190a8f2-7c3e-7d4a-8b1c-000000000001";

pub fn generation_at(time: DateTime<Utc>) -> Uuid {
    Uuid::new_v7(Timestamp::from_unix(NoContext, time.timestamp() as u64, 0))
}

pub fn record(generation_id: Uuid, task: &str) -> Vec<u8> {
    serde_json::to_vec(&serde_json::json!({
        "schema": SCHEMA,
        "generation_id": generation_id,
        "workspace_id": WORKSPACE,
        "task": task,
        "trace_id": "trace-1",
        "session_id": null,
        "model": "z-ai/glm-5.3-flash",
        "provider": "gradiated",
        "source": "hosted",
        "trainable": true,
        "started_at": "2026-09-24T20:00:00Z",
        "completed_at": "2026-09-24T20:00:01Z",
        "usage": { "input": 10, "output": 2 },
        "retention_days": 30,
        "raw": { "request": { "messages": [] }, "response": {} }
    }))
    .unwrap()
}

pub fn with_fields(body: &[u8], fields: serde_json::Value) -> Vec<u8> {
    let mut record: serde_json::Value = serde_json::from_slice(body).unwrap();
    for (name, value) in fields.as_object().unwrap() {
        record[name] = value.clone();
    }

    serde_json::to_vec(&record).unwrap()
}

pub fn limits() -> Limits {
    Limits {
        max_open_streams: 64,
        max_pending_batches: 64,
        max_batch_bytes: 64 * 1024 * 1024,
        max_batch_age: Duration::from_millis(100),
        disk_cap_bytes: 64 * 1024 * 1024,
    }
}

pub struct Running {
    pub collector: Collector,
    pub store: Arc<InMemory>,
    pub data_dir: TempDir,
}

pub fn start(limits: Limits) -> Running {
    start_in(tempfile::tempdir().unwrap(), limits)
}

pub fn start_in(data_dir: TempDir, limits: Limits) -> Running {
    let store = Arc::new(InMemory::new());
    let collector = start_with(&data_dir, limits, store.clone());

    Running {
        collector,
        store,
        data_dir,
    }
}

pub fn start_with(data_dir: &TempDir, limits: Limits, store: Arc<dyn ObjectStore>) -> Collector {
    let config = CollectorConfig {
        database_url: None,
        database_ca_bundle_path: None,
        bind_address: "127.0.0.1:0".parse().unwrap(),
        admin_address: "127.0.0.1:0".parse().unwrap(),
        data_dir: data_dir.path().to_owned(),
        store: Store::Local {
            directory: data_dir.path().join("unused"),
        },
        replica: "collector-0".to_owned(),
        token: TOKEN.to_owned(),
        max_record_bytes: 1024 * 1024,
        max_buffered_bytes: 4 * 1024 * 1024,
        max_concurrent_requests: 4,
        limits,
        drain: Duration::from_secs(5),
    };

    Collector::start(&config, store).unwrap()
}
