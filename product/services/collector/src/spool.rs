use std::{
    collections::HashMap,
    fs, io,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, AtomicUsize, Ordering},
        Arc, Mutex, MutexGuard, PoisonError,
    },
    time::Duration,
};

use tokio::sync::mpsc::UnboundedSender;

use crate::{
    batch::{self, Batch},
    metrics::Metrics,
    record::StreamKey,
};

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub max_open_streams: usize,
    pub max_pending_batches: usize,
    pub max_batch_bytes: u64,
    pub max_batch_age: Duration,
    pub disk_cap_bytes: u64,
}

#[derive(Clone, Debug, thiserror::Error, PartialEq, Eq)]
pub enum WriteError {
    #[error("the collector's disk budget is full")]
    Full,
    #[error("the collector is shutting down")]
    Closed,
    #[error("the batch write failed: {0}")]
    Io(String),
}

#[derive(Default)]
pub struct Backlog {
    pub bytes: AtomicU64,
    pub batches: AtomicUsize,
}

impl Backlog {
    pub fn release(&self, bytes: u64) {
        let _ = self
            .bytes
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |used| {
                Some(used.saturating_sub(bytes))
            });
        let _ = self
            .batches
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |pending| {
                Some(pending.saturating_sub(1))
            });
    }
}

struct Open {
    streams: HashMap<StreamKey, Batch>,
    sealed: Option<UnboundedSender<PathBuf>>,
}

pub struct Spool {
    directory: PathBuf,
    limits: Limits,
    open: Mutex<Open>,
    backlog: Arc<Backlog>,
    metrics: Metrics,
}

impl Spool {
    pub fn recover(
        directory: &Path,
        limits: Limits,
        backlog: Arc<Backlog>,
        sealed: UnboundedSender<PathBuf>,
        metrics: Metrics,
    ) -> io::Result<(Self, Vec<PathBuf>)> {
        fs::create_dir_all(directory)?;

        let mut recovered = Vec::new();
        for entry in fs::read_dir(directory)? {
            let path = entry?.path();
            let complete = batch::truncate_torn_tail(&path)?;

            if complete == 0 {
                fs::remove_file(&path)?;
            } else {
                backlog.bytes.fetch_add(complete, Ordering::AcqRel);
                backlog.batches.fetch_add(1, Ordering::AcqRel);
                recovered.push(path);
            }
        }
        recovered.sort();

        let spool = Self {
            directory: directory.to_owned(),
            limits,
            open: Mutex::new(Open {
                streams: HashMap::new(),
                sealed: Some(sealed),
            }),
            backlog,
            metrics,
        };

        Ok((spool, recovered))
    }

    pub fn append(&self, key: &StreamKey, frame: &[u8]) -> Result<(), WriteError> {
        let length = frame.len() as u64;
        let mut open = self.lock();

        if open.sealed.is_none() {
            return Err(WriteError::Closed);
        }

        if self.backlog.bytes.load(Ordering::Acquire) + length > self.limits.disk_cap_bytes {
            return Err(WriteError::Full);
        }

        let full = open.streams.get(key).is_some_and(|batch| {
            batch.bytes > 0 && batch.bytes + length > self.limits.max_batch_bytes
        });
        if full {
            self.seal(&mut open, key.clone());
        }

        if !open.streams.contains_key(key) {
            if self.backlog.batches.load(Ordering::Acquire) >= self.limits.max_pending_batches {
                return Err(WriteError::Full);
            }

            if open.streams.len() >= self.limits.max_open_streams {
                let oldest = open
                    .streams
                    .iter()
                    .min_by_key(|(_, batch)| batch.opened)
                    .map(|(key, _)| key.clone());
                if let Some(oldest) = oldest {
                    self.seal(&mut open, oldest);
                }
            }

            let batch = Batch::create(&self.directory, key)
                .map_err(|error| WriteError::Io(error.to_string()))?;
            open.streams.insert(key.clone(), batch);
        }

        open.streams
            .get_mut(key)
            .expect("the batch was just opened")
            .append(frame)
            .map_err(|error| WriteError::Io(error.to_string()))?;
        self.backlog.bytes.fetch_add(length, Ordering::AcqRel);
        self.metrics.set_open_streams(open.streams.len());

        Ok(())
    }

    pub fn seal_expired(&self) {
        let mut open = self.lock();
        let expired: Vec<StreamKey> = open
            .streams
            .iter()
            .filter(|(_, batch)| batch.opened.elapsed() >= self.limits.max_batch_age)
            .map(|(key, _)| key.clone())
            .collect();

        for key in expired {
            self.seal(&mut open, key);
        }
    }

    pub fn close(&self) {
        let mut open = self.lock();
        let keys: Vec<StreamKey> = open.streams.keys().cloned().collect();

        for key in keys {
            self.seal(&mut open, key);
        }
        open.sealed = None;
    }

    fn seal(&self, open: &mut Open, key: StreamKey) {
        if let Some(batch) = open.streams.remove(&key) {
            if let Some(sealed) = &open.sealed {
                self.backlog.batches.fetch_add(1, Ordering::AcqRel);
                let _ = sealed.send(batch.path);
            }
        }

        self.metrics.set_open_streams(open.streams.len());
    }

    fn lock(&self) -> MutexGuard<'_, Open> {
        self.open.lock().unwrap_or_else(PoisonError::into_inner)
    }
}
