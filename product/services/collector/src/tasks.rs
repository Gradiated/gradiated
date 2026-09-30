use std::{
    collections::HashMap,
    fs, io,
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tokio::sync::Notify;
use uuid::Uuid;

use crate::{metrics::Metrics, postgres::PostgresService};

const CACHE_SIZE: usize = 10_000;
const CACHE_TTL: Duration = Duration::from_secs(3600);
const DATABASE_TIMEOUT: Duration = Duration::from_secs(2);
const RETRY: Duration = Duration::from_secs(60);
const INSERT_TASK: &str = "INSERT INTO tasks (id, workspace_id, name) \
    SELECT $1, id, $3 FROM workspaces WHERE id = $2 \
    ON CONFLICT (workspace_id, name) DO NOTHING";

#[derive(Clone, Serialize, Deserialize, Hash, PartialEq, Eq)]
struct Task {
    workspace_id: Uuid,
    name: String,
}

pub struct TaskService {
    directory: PathBuf,
    postgres: PostgresService,
    seen: Mutex<HashMap<Task, Instant>>,
    wake: Notify,
    metrics: Metrics,
}

impl TaskService {
    pub fn new(
        data_dir: &Path,
        postgres: PostgresService,
        metrics: Metrics,
    ) -> io::Result<Arc<Self>> {
        let directory = data_dir.join("task-registrations");
        fs::create_dir_all(&directory)?;

        Ok(Arc::new(Self {
            directory,
            postgres,
            seen: Mutex::new(HashMap::new()),
            wake: Notify::new(),
            metrics,
        }))
    }

    pub fn enqueue(&self, workspace_id: Uuid, name: &str) -> io::Result<()> {
        if name.is_empty() || matches!(name, "." | "..") {
            return Ok(());
        }

        let task = Task {
            workspace_id,
            name: name.to_owned(),
        };
        let mut seen = self.seen.lock().expect("task cache lock");
        if seen.get(&task).is_some_and(|at| at.elapsed() < CACHE_TTL) {
            return Ok(());
        }

        let path = self.path(&task);
        if !path.exists() {
            let temporary = self.directory.join(format!("{}.tmp", Uuid::now_v7()));
            let data = serde_json::to_vec(&task).expect("task serialises");
            fs::write(&temporary, data)?;
            fs::rename(temporary, path)?;
        }
        remember(&mut seen, task);
        self.wake.notify_one();

        Ok(())
    }

    fn path(&self, task: &Task) -> PathBuf {
        self.directory.join(format!(
            "{}-{:x}.json",
            task.workspace_id,
            Sha256::digest(task.name.as_bytes())
        ))
    }

    async fn reconcile(&self) -> io::Result<()> {
        let mut entries = tokio::fs::read_dir(&self.directory).await?;
        let mut processed = 0;
        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.extension().is_none_or(|extension| extension != "json") {
                continue;
            }

            let data = tokio::fs::read(&path).await?;
            let task: Task = serde_json::from_slice(&data).map_err(io::Error::other)?;
            let result = tokio::time::timeout(DATABASE_TIMEOUT, async {
                let client = self
                    .postgres
                    .client()
                    .await
                    .map_err(|_| io::Error::other("task database unavailable"))?;
                client
                    .execute(
                        INSERT_TASK,
                        &[&Uuid::now_v7(), &task.workspace_id, &task.name],
                    )
                    .await
                    .map_err(|_| io::Error::other("task registration failed"))?;
                Ok::<_, io::Error>(())
            })
            .await
            .map_err(|_| io::Error::other("task registration timed out"))?;
            result?;

            {
                let mut seen = self.seen.lock().expect("task cache lock");
                fs::remove_file(path)?;
                remember(&mut seen, task);
            }
            self.metrics.task_registered();
            processed += 1;
            if processed == 1000 {
                self.wake.notify_one();
                break;
            }
        }

        Ok(())
    }

    pub async fn run(self: Arc<Self>) {
        loop {
            if self.reconcile().await.is_err() {
                self.metrics.task_registration_failed();
                tracing::warn!("task registration unavailable; pending tasks remain on disk");
                tokio::time::sleep(RETRY).await;
                continue;
            }

            tokio::select! {
                _ = self.wake.notified() => {},
                _ = tokio::time::sleep(RETRY) => {},
            }
        }
    }
}

fn remember(seen: &mut HashMap<Task, Instant>, task: Task) {
    if seen.len() >= CACHE_SIZE && !seen.contains_key(&task) {
        seen.retain(|_, at| at.elapsed() < CACHE_TTL);
        if seen.len() >= CACHE_SIZE {
            if let Some(oldest) = seen
                .iter()
                .min_by_key(|(_, at)| **at)
                .map(|(task, _)| task.clone())
            {
                seen.remove(&oldest);
            }
        }
    }

    seen.insert(task, Instant::now());
}
