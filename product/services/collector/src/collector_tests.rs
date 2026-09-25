use std::{fs, sync::Arc, time::Duration};

use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use chrono::{TimeZone, Utc};
use futures_util::TryStreamExt;
use object_store::{path::Path as ObjectPath, ObjectStore, ObjectStoreExt};
use serde_json::Value;
use tower::ServiceExt;
use uuid::Uuid;

use crate::{
    batch::{self, Batch},
    public_router,
    record::GenerationContent,
    test_support::{
        generation_at, limits, record, start, start_in, start_with, with_fields, Running, TOKEN,
        WORKSPACE,
    },
};

async fn post(running: &Running, token: &str, body: Vec<u8>) -> StatusCode {
    let request = Request::post("/v1/contents")
        .header("authorization", format!("Bearer {token}"))
        .header("content-type", "application/json")
        .body(Body::from(body))
        .unwrap();

    public_router(running.collector.state.clone())
        .oneshot(request)
        .await
        .unwrap()
        .status()
}

async fn manifests(running: &Running, expected: usize) -> Vec<(String, Value)> {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);

    loop {
        let objects: Vec<_> = running.store.list(None).try_collect().await.unwrap();
        let mut found = Vec::new();
        for object in objects {
            let key = object.location.to_string();
            if let Some(base) = key.strip_suffix(".manifest.json") {
                let bytes = running
                    .store
                    .get(&object.location)
                    .await
                    .unwrap()
                    .bytes()
                    .await
                    .unwrap();
                found.push((base.to_owned(), serde_json::from_slice(&bytes).unwrap()));
            }
        }

        if found.len() >= expected || tokio::time::Instant::now() > deadline {
            found.sort_by(|left, right| left.0.cmp(&right.0));
            return found;
        }

        tokio::time::sleep(Duration::from_millis(20)).await;
    }
}

async fn read_generation(running: &Running, base: &str, row: &Value) -> Vec<u8> {
    let offset = row["offset"].as_u64().unwrap();
    let length = row["length"].as_u64().unwrap();
    let frame = running
        .store
        .get_range(
            &ObjectPath::from(format!("{base}.jsonl.zst")),
            offset..offset + length,
        )
        .await
        .unwrap();

    let record = batch::frames(&frame).next().unwrap().record;

    record
}

#[tokio::test]
async fn accepted_generations_are_stored_as_one_batch_with_a_manifest() {
    let running = start(limits());
    let time = Utc.with_ymd_and_hms(2026, 9, 24, 20, 15, 0).unwrap();
    let records: Vec<Vec<u8>> = (0..3)
        .map(|second| {
            record(
                generation_at(time + chrono::Duration::seconds(second)),
                "support-triage",
            )
        })
        .collect();

    for body in &records {
        assert_eq!(
            post(&running, TOKEN, body.clone()).await,
            StatusCode::ACCEPTED
        );
    }

    let manifests = manifests(&running, 1).await;
    assert_eq!(manifests.len(), 1);
    let (base, manifest) = &manifests[0];
    assert!(
        base.starts_with(&format!(
            "v1/ws={WORKSPACE}/task=support-triage/dt=2026-09-24/hr=20/collector-0-"
        )),
        "{base}"
    );
    assert_eq!(
        manifest["schema"],
        "gradiated.generation-content-manifest/1"
    );

    let rows = manifest["generations"].as_array().unwrap();
    assert_eq!(rows.len(), 3);
    for (row, body) in rows.iter().zip(&records) {
        assert_eq!(&read_generation(&running, base, row).await, body);
        assert_eq!(row["trace_id"], "trace-1");
        assert_eq!(row["model"], "z-ai/glm-5.3-flash");
    }
}

#[tokio::test]
async fn a_generation_lands_in_the_hour_of_its_identifier() {
    let running = start(limits());
    let late = Utc.with_ymd_and_hms(2026, 9, 24, 20, 59, 59).unwrap();
    let early = Utc.with_ymd_and_hms(2026, 9, 24, 21, 0, 0).unwrap();

    for time in [late, early] {
        assert_eq!(
            post(&running, TOKEN, record(generation_at(time), "t")).await,
            StatusCode::ACCEPTED
        );
    }

    let hours: Vec<bool> = manifests(&running, 2)
        .await
        .iter()
        .map(|(base, _)| base.contains("/hr=20/"))
        .collect();
    assert_eq!(hours, [true, false]);
}

#[tokio::test]
async fn a_full_batch_is_sealed_and_a_new_one_opens() {
    let mut small = limits();
    small.max_batch_bytes = 1;
    let running = start(small);
    let time = Utc.with_ymd_and_hms(2026, 9, 24, 20, 0, 0).unwrap();

    for second in 0..3 {
        let id = generation_at(time + chrono::Duration::seconds(second));
        assert_eq!(
            post(&running, TOKEN, record(id, "t")).await,
            StatusCode::ACCEPTED
        );
    }

    let manifests = manifests(&running, 3).await;
    assert_eq!(manifests.len(), 3);
    assert!(manifests.iter().all(|(_, manifest)| manifest["generations"]
        .as_array()
        .unwrap()
        .len()
        == 1));
}

#[tokio::test]
async fn batches_left_open_by_a_crash_are_uploaded_at_startup() {
    let data_dir = tempfile::tempdir().unwrap();
    let time = Utc.with_ymd_and_hms(2026, 9, 24, 20, 0, 0).unwrap();
    let written: Vec<Vec<u8>> = (0..2)
        .map(|second| record(generation_at(time + chrono::Duration::seconds(second)), "t"))
        .collect();
    let key = GenerationContent::parse(&written[0])
        .unwrap()
        .stream_key()
        .unwrap();
    let mut batch = Batch::create(data_dir.path(), &key).unwrap();
    for body in &written {
        batch.append(&batch::compress(body).unwrap()).unwrap();
    }
    batch
        .append(&batch::compress(&record(Uuid::now_v7(), "t")).unwrap()[..7])
        .unwrap();
    drop(batch);

    let running = start_in(data_dir, limits());

    let manifests = manifests(&running, 1).await;
    assert_eq!(manifests.len(), 1);
    let (base, manifest) = &manifests[0];
    let rows = manifest["generations"].as_array().unwrap();
    assert_eq!(rows.len(), 2, "the torn frame is dropped");
    for (row, body) in rows.iter().zip(&written) {
        assert_eq!(&read_generation(&running, base, row).await, body);
    }
    assert_eq!(fs::read_dir(running.data_dir.path()).unwrap().count(), 0);
}

#[tokio::test]
async fn a_full_disk_budget_refuses_new_generations() {
    let mut tiny = limits();
    tiny.disk_cap_bytes = 16;
    let running = start(tiny);

    assert_eq!(
        post(&running, TOKEN, record(Uuid::now_v7(), "t")).await,
        StatusCode::SERVICE_UNAVAILABLE
    );
}

#[tokio::test]
async fn unauthorized_malformed_and_oversized_bodies_are_refused() {
    let running = start(limits());

    assert_eq!(
        post(
            &running,
            "wrong-token-with-at-least-32-chars",
            record(Uuid::now_v7(), "t")
        )
        .await,
        StatusCode::UNAUTHORIZED
    );
    assert_eq!(
        post(&running, TOKEN, b"{}".to_vec()).await,
        StatusCode::BAD_REQUEST
    );
    assert_eq!(
        post(&running, TOKEN, vec![b' '; 2 * 1024 * 1024]).await,
        StatusCode::PAYLOAD_TOO_LARGE
    );
    assert!(running
        .store
        .list(None)
        .try_collect::<Vec<_>>()
        .await
        .unwrap()
        .is_empty());
}

#[tokio::test]
async fn shutdown_uploads_batches_that_are_still_open() {
    let mut patient = limits();
    patient.max_batch_age = Duration::from_secs(3600);
    let running = start(patient);
    assert_eq!(
        post(&running, TOKEN, record(Uuid::now_v7(), "t")).await,
        StatusCode::ACCEPTED
    );

    let Running {
        collector,
        store,
        data_dir,
    } = running;
    collector.shutdown(Duration::from_secs(5)).await;

    let objects: Vec<_> = store.list(None).try_collect().await.unwrap();
    assert_eq!(objects.len(), 2);
    assert_eq!(fs::read_dir(data_dir.path()).unwrap().count(), 0);
}

#[tokio::test]
async fn a_failed_upload_is_retried_until_the_store_accepts_it() {
    use std::os::unix::fs::PermissionsExt;

    let data_dir = tempfile::tempdir().unwrap();
    let store_dir = tempfile::tempdir().unwrap();
    fs::set_permissions(store_dir.path(), fs::Permissions::from_mode(0o500)).unwrap();
    let store =
        Arc::new(object_store::local::LocalFileSystem::new_with_prefix(store_dir.path()).unwrap());
    let collector = start_with(&data_dir, limits(), store.clone());
    let router = public_router(collector.state.clone());
    let request = Request::post("/v1/contents")
        .header("authorization", format!("Bearer {TOKEN}"))
        .body(Body::from(record(Uuid::now_v7(), "t")))
        .unwrap();

    assert_eq!(
        router.oneshot(request).await.unwrap().status(),
        StatusCode::ACCEPTED
    );
    tokio::time::sleep(Duration::from_millis(500)).await;
    assert!(store
        .list(None)
        .try_collect::<Vec<_>>()
        .await
        .unwrap()
        .is_empty());
    assert_eq!(fs::read_dir(data_dir.path()).unwrap().count(), 1);

    fs::set_permissions(store_dir.path(), fs::Permissions::from_mode(0o700)).unwrap();
    let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
    while store
        .list(None)
        .try_collect::<Vec<_>>()
        .await
        .unwrap()
        .len()
        < 2
    {
        assert!(
            tokio::time::Instant::now() < deadline,
            "the upload was never retried"
        );
        tokio::time::sleep(Duration::from_millis(50)).await;
    }

    assert_eq!(fs::read_dir(data_dir.path()).unwrap().count(), 0);
    assert!(collector
        .state
        .metrics
        .encode()
        .contains("gradiated_collector_upload_failures_total"));
}

#[tokio::test]
async fn trainable_and_untrainable_generations_never_share_a_batch() {
    let running = start(limits());
    let hosted = record(Uuid::now_v7(), "t");
    let relayed = with_fields(
        &record(Uuid::now_v7(), "t"),
        serde_json::json!({ "source": "relay", "provider": "anthropic", "trainable": false }),
    );

    for body in [hosted, relayed] {
        assert_eq!(post(&running, TOKEN, body).await, StatusCode::ACCEPTED);
    }

    let mut kinds: Vec<Vec<bool>> = manifests(&running, 2)
        .await
        .iter()
        .map(|(_, manifest)| {
            manifest["generations"]
                .as_array()
                .unwrap()
                .iter()
                .map(|row| row["trainable"].as_bool().unwrap())
                .collect()
        })
        .collect();
    kinds.sort();
    assert_eq!(kinds, [vec![false], vec![true]]);
}

#[test]
fn objects_are_tagged_with_retention_and_trainability() {
    let key = GenerationContent::parse(&with_fields(
        &record(Uuid::now_v7(), "t"),
        serde_json::json!({ "retention_days": 180, "source": "relay", "trainable": false }),
    ))
    .unwrap()
    .stream_key();

    let tags = crate::upload::object_tags(&key.unwrap());

    assert_eq!(tags.encoded(), "retention=180d&trainable=false");
}

#[tokio::test]
async fn the_oldest_stream_is_sealed_when_too_many_are_open() {
    let mut few = limits();
    few.max_open_streams = 2;
    few.max_batch_age = Duration::from_secs(3600);
    let running = start(few);

    for task in ["first", "second", "third"] {
        assert_eq!(
            post(&running, TOKEN, record(Uuid::now_v7(), task)).await,
            StatusCode::ACCEPTED
        );
        tokio::time::sleep(Duration::from_millis(5)).await;
    }

    let manifests = manifests(&running, 1).await;
    assert_eq!(manifests.len(), 1);
    assert!(
        manifests[0].0.contains("/task=first/"),
        "{}",
        manifests[0].0
    );
}

#[tokio::test]
async fn a_batch_from_an_older_schema_still_uploads() {
    let data_dir = tempfile::tempdir().unwrap();
    let current = record(Uuid::now_v7(), "t");
    let older = with_fields(
        &current,
        serde_json::json!({ "schema": "gradiated.contents/1" }),
    );
    let key = GenerationContent::parse(&current)
        .unwrap()
        .stream_key()
        .unwrap();
    let mut batch = Batch::create(data_dir.path(), &key).unwrap();
    batch.append(&batch::compress(&older).unwrap()).unwrap();
    drop(batch);

    let running = start_in(data_dir, limits());

    let manifests = manifests(&running, 1).await;
    assert_eq!(manifests.len(), 1);
    assert_eq!(manifests[0].1["generations"].as_array().unwrap().len(), 1);
}

#[tokio::test]
async fn a_batch_that_cannot_be_uploaded_stops_counting_against_the_disk_cap() {
    let data_dir = tempfile::tempdir().unwrap();
    let stray = batch::compress(&record(Uuid::now_v7(), "t")).unwrap();
    fs::write(data_dir.path().join("not-a-batch.zst"), &stray).unwrap();
    fs::write(data_dir.path().join("empty.zst"), b"torn").unwrap();
    let mut small = limits();
    small.disk_cap_bytes = stray.len() as u64 * 3 / 2;
    let running = start_in(data_dir, small);

    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
    while post(&running, TOKEN, record(Uuid::now_v7(), "t")).await != StatusCode::ACCEPTED {
        assert!(
            tokio::time::Instant::now() < deadline,
            "the stray batch kept the disk full"
        );
        tokio::time::sleep(Duration::from_millis(20)).await;
    }
    assert!(running.data_dir.path().join("not-a-batch.zst").exists());
    assert!(!running.data_dir.path().join("empty.zst").exists());
}

#[tokio::test]
async fn a_generation_without_a_task_is_dropped_without_an_error() {
    let running = start(limits());
    let untasked = with_fields(
        &record(Uuid::now_v7(), "t"),
        serde_json::json!({ "task": null }),
    );

    assert_eq!(
        post(&running, TOKEN, untasked).await,
        StatusCode::NO_CONTENT
    );

    tokio::time::sleep(Duration::from_millis(300)).await;
    assert!(running
        .store
        .list(None)
        .try_collect::<Vec<_>>()
        .await
        .unwrap()
        .is_empty());
    assert!(running
        .collector
        .state
        .metrics
        .encode()
        .contains("gradiated_collector_contents_skipped_total 1"));
}

#[tokio::test]
async fn too_many_batches_waiting_to_upload_refuses_new_batches() {
    use std::os::unix::fs::PermissionsExt;

    let data_dir = tempfile::tempdir().unwrap();
    let store_dir = tempfile::tempdir().unwrap();
    fs::set_permissions(store_dir.path(), fs::Permissions::from_mode(0o500)).unwrap();
    let store =
        Arc::new(object_store::local::LocalFileSystem::new_with_prefix(store_dir.path()).unwrap());
    let mut one = limits();
    one.max_pending_batches = 1;
    let collector = start_with(&data_dir, one, store);
    let send = |task: &'static str| {
        let router = public_router(collector.state.clone());
        async move {
            let request = Request::post("/v1/contents")
                .header("authorization", format!("Bearer {TOKEN}"))
                .body(Body::from(record(Uuid::now_v7(), task)))
                .unwrap();
            router.oneshot(request).await.unwrap().status()
        }
    };

    assert_eq!(send("first").await, StatusCode::ACCEPTED);
    tokio::time::sleep(Duration::from_millis(400)).await;

    assert_eq!(send("second").await, StatusCode::SERVICE_UNAVAILABLE);
    fs::set_permissions(store_dir.path(), fs::Permissions::from_mode(0o700)).unwrap();
}

async fn post_ndjson(running: &Running, body: Vec<u8>) -> StatusCode {
    let request = Request::post("/v1/contents")
        .header("authorization", format!("Bearer {TOKEN}"))
        .header("content-type", "application/x-ndjson; charset=utf-8")
        .body(Body::from(body))
        .unwrap();

    public_router(running.collector.state.clone())
        .oneshot(request)
        .await
        .unwrap()
        .status()
}

#[tokio::test]
async fn ndjson_stores_valid_lines_around_invalid_lines_and_skips_no_task() {
    let running = start(limits());
    let hosted = record(Uuid::now_v7(), "hosted-test");
    let relay = crate::relay_tests::relay(
        "{\"usage\":{\"input_tokens\":7,\"output_tokens\":2},\"output\":[]}",
        "openai",
        "/v1/responses",
        "application/json",
    );
    let mut body = hosted.clone();
    body.extend_from_slice(b"\nnot json\n\n");
    body.extend_from_slice(&with_fields(&hosted, serde_json::json!({"task":null})));
    body.push(b'\n');
    body.extend_from_slice(&serde_json::to_vec(&relay).unwrap());
    assert_eq!(post_ndjson(&running, body).await, StatusCode::ACCEPTED);

    let manifests = manifests(&running, 2).await;
    assert_eq!(manifests.len(), 2);
    for (base, manifest) in manifests {
        let rows = manifest["generations"].as_array().unwrap();
        assert_eq!(rows.len(), 1);
        let bytes = read_generation(&running, &base, &rows[0]).await;
        let content: Value = serde_json::from_slice(&bytes).unwrap();
        if content["source"] == "relay" {
            assert_eq!(content["trainable"], false);
            assert_eq!(rows[0]["status"], 200);
            assert_eq!(rows[0]["outcome"], "complete");
            assert_eq!(rows[0]["protocol"], "openai.responses");
            assert_eq!(rows[0]["streamed"], false);
            assert_eq!(content["raw"]["response"]["output"], serde_json::json!([]));
            assert_eq!(content["usage"]["input"], 7);
            assert_eq!(content["generation_id"], relay["generation_id"]);
        } else {
            assert_eq!(bytes, hosted);
        }
    }
    let metrics = running.collector.state.metrics.encode();
    assert!(metrics.contains("gradiated_collector_contents_accepted_total 2"));
    assert!(metrics.contains("gradiated_collector_contents_skipped_total 1"));
    assert!(metrics.contains("gradiated_collector_contents_rejected_total{reason=\"invalid\"} 1"));
}

#[tokio::test]
async fn invalid_ndjson_does_not_fail_the_batch_but_spool_refusal_does() {
    let mut tiny = limits();
    tiny.disk_cap_bytes = 1;
    let running = start(tiny);
    assert_eq!(
        post_ndjson(&running, b"bad\n{}\n".to_vec()).await,
        StatusCode::ACCEPTED
    );
    assert_eq!(
        post_ndjson(&running, record(Uuid::now_v7(), "t")).await,
        StatusCode::SERVICE_UNAVAILABLE
    );
}

#[tokio::test]
async fn a_batch_refusal_keeps_earlier_accepted_lines() {
    let body = record(Uuid::now_v7(), "partial-batch");
    let mut bounded = limits();
    bounded.disk_cap_bytes = batch::compress(&body).unwrap().len() as u64;
    bounded.max_batch_age = Duration::from_secs(3600);
    let running = start(bounded);
    let batch = [body.as_slice(), b"\n", body.as_slice()].concat();

    assert_eq!(
        post_ndjson(&running, batch).await,
        StatusCode::SERVICE_UNAVAILABLE
    );
    assert!(running
        .collector
        .state
        .metrics
        .encode()
        .contains("gradiated_collector_contents_accepted_total 1"));
    let Running {
        collector,
        store,
        data_dir,
    } = running;
    collector.shutdown(Duration::from_secs(5)).await;
    let objects: Vec<_> = store.list(None).try_collect().await.unwrap();
    assert_eq!(objects.len(), 2);
    let manifest = objects
        .iter()
        .find(|object| object.location.to_string().ends_with(".manifest.json"))
        .unwrap();
    let value: Value = serde_json::from_slice(
        &store
            .get(&manifest.location)
            .await
            .unwrap()
            .bytes()
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(value["generations"].as_array().unwrap().len(), 1);
    assert_eq!(fs::read_dir(data_dir.path()).unwrap().count(), 0);
}
