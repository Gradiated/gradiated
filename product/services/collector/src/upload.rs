use std::{
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use object_store::{path::Path as ObjectPath, ObjectStore, PutOptions, PutPayload, TagSet};
use serde::Serialize;
use tokio::{
    sync::{mpsc::UnboundedReceiver, Semaphore},
    task::JoinSet,
};
use uuid::Uuid;

use crate::{
    batch,
    metrics::Metrics,
    record::{GenerationContent, StreamKey},
    spool::Backlog,
};

const CONCURRENT_UPLOADS: usize = 4;
const FIRST_RETRY: Duration = Duration::from_secs(1);
const LAST_RETRY: Duration = Duration::from_secs(60);
pub const MANIFEST_SCHEMA: &str = "gradiated.generation-content-manifest/1";

#[derive(Debug, thiserror::Error)]
pub enum UploadError {
    #[error("unrecognised batch name")]
    Name,
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Store(#[from] object_store::Error),
    #[error("a frame is not a generation content record: {0}")]
    Record(String),
}

#[derive(Debug, Serialize, PartialEq)]
pub struct Manifest {
    pub schema: &'static str,
    pub generations: Vec<ManifestRow>,
}

#[derive(Debug, Serialize, PartialEq)]
pub struct ManifestRow {
    #[serde(flatten)]
    pub content: GenerationContent,
    pub offset: u64,
    pub length: u64,
}

pub struct Uploader {
    store: Arc<dyn ObjectStore>,
    replica: Arc<str>,
    backlog: Arc<Backlog>,
    metrics: Metrics,
}

impl Uploader {
    pub fn new(
        store: Arc<dyn ObjectStore>,
        replica: &str,
        backlog: Arc<Backlog>,
        metrics: Metrics,
    ) -> Arc<Self> {
        Arc::new(Self {
            store,
            replica: Arc::from(replica),
            backlog,
            metrics,
        })
    }

    pub async fn run(self: Arc<Self>, mut sealed: UnboundedReceiver<PathBuf>) {
        let permits = Arc::new(Semaphore::new(CONCURRENT_UPLOADS));
        let mut uploads = JoinSet::new();

        while let Some(path) = sealed.recv().await {
            let permit = permits
                .clone()
                .acquire_owned()
                .await
                .expect("the semaphore is never closed");
            let uploader = self.clone();

            uploads.spawn(async move {
                uploader.upload_until_stored(&path).await;
                drop(permit);
            });
            while uploads.try_join_next().is_some() {}
        }

        while uploads.join_next().await.is_some() {}
    }

    async fn upload_until_stored(&self, path: &Path) {
        let mut delay = FIRST_RETRY;

        loop {
            match self.upload(path).await {
                Ok(()) => return,
                Err(UploadError::Name | UploadError::Record(_)) => {
                    tracing::error!(path = %path.display(), "batch cannot be uploaded; it stays on disk");
                    self.metrics.upload_failed();
                    if let Ok(metadata) = tokio::fs::metadata(path).await {
                        self.backlog.release(metadata.len());
                    }
                    return;
                }
                Err(error) => {
                    tracing::warn!(%error, path = %path.display(), "batch upload failed; retrying");
                    self.metrics.upload_failed();
                    tokio::time::sleep(delay).await;
                    delay = (delay * 2).min(LAST_RETRY);
                }
            }
        }
    }

    async fn upload(&self, path: &Path) -> Result<(), UploadError> {
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or(UploadError::Name)?;
        let (key, batch_id) = batch::parse_file_name(name).ok_or(UploadError::Name)?;
        let data = tokio::fs::read(path).await?;
        let length = data.len() as u64;

        let (data, manifest) = tokio::task::spawn_blocking(move || {
            let manifest = manifest(&data);
            (data, manifest)
        })
        .await
        .expect("manifest building does not panic");
        let manifest = manifest?;

        if !manifest.generations.is_empty() {
            let base = object_base(&key, &self.replica, batch_id);
            let manifest = serde_json::to_vec(&manifest).expect("a manifest serialises");

            for (suffix, payload) in [("jsonl.zst", data), ("manifest.json", manifest)] {
                let options = PutOptions {
                    tags: object_tags(&key),
                    ..PutOptions::default()
                };

                self.store
                    .put_opts(
                        &ObjectPath::from(format!("{base}.{suffix}")),
                        PutPayload::from(payload),
                        options,
                    )
                    .await?;
            }
            self.metrics.batch_uploaded(length);
        }

        tokio::fs::remove_file(path).await?;
        self.backlog.release(length);

        Ok(())
    }
}

pub fn manifest(data: &[u8]) -> Result<Manifest, UploadError> {
    let generations = batch::frames(data)
        .map(|frame| {
            let content = GenerationContent::read(&frame.record)
                .map_err(|error| UploadError::Record(error.to_string()))?;

            Ok(ManifestRow {
                content,
                offset: frame.offset,
                length: frame.length,
            })
        })
        .collect::<Result<_, UploadError>>()?;

    Ok(Manifest {
        schema: MANIFEST_SCHEMA,
        generations,
    })
}

pub fn object_tags(key: &StreamKey) -> TagSet {
    let mut tags = TagSet::default();
    tags.push("retention", &format!("{}d", key.retention_days));
    tags.push("trainable", &key.trainable.to_string());

    tags
}

pub fn object_base(key: &StreamKey, replica: &str, batch_id: Uuid) -> String {
    format!(
        "v1/ws={}/task={}/dt={}/hr={}/{replica}-{batch_id}",
        key.workspace_id,
        key.task_key,
        key.hour.format("%Y-%m-%d"),
        key.hour.format("%H"),
    )
}
