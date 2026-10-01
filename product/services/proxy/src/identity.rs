use std::{
    collections::HashMap,
    sync::{Arc, Mutex, MutexGuard, PoisonError},
    time::{Duration, Instant},
};

use chrono::{DateTime, Utc};
use futures_util::{
    future::{BoxFuture, Shared},
    FutureExt,
};
use tokio::sync::Semaphore;
use uuid::Uuid;

use crate::{
    credentials::ApiKey,
    directory::{Directory, DirectoryUnavailable, IdentityRecord},
    metrics::{IdentityResult, Metrics},
};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Identity {
    pub api_key_id: Uuid,
    pub organization_id: Uuid,
    pub workspace_id: Uuid,
    pub trace_capture_enabled: bool,
    pub trace_retention_days: i16,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
pub enum Denial {
    #[error("invalid API key")]
    InvalidApiKey,
    #[error("workspace is archived")]
    WorkspaceArchived,
    #[error("organization is suspended")]
    OrganizationSuspended,
    #[error("identity is unavailable")]
    Unavailable,
}

#[derive(Clone, Copy, Debug)]
pub struct IdentitySettings {
    pub fresh_for: Duration,
    pub stale_grace: Duration,
    pub capacity: usize,
    pub max_concurrent_loads: usize,
}

type Digest = [u8; 32];
type Load = Shared<BoxFuture<'static, Result<Option<IdentityRecord>, DirectoryUnavailable>>>;

struct Entry {
    loaded_at: Instant,
    record: IdentityRecord,
}

#[derive(Clone)]
pub struct IdentityCache {
    directory: Arc<dyn Directory>,
    settings: IdentitySettings,
    entries: Arc<Mutex<HashMap<Digest, Entry>>>,
    loads: Arc<Mutex<HashMap<Digest, Load>>>,
    load_permits: Arc<Semaphore>,
    metrics: Metrics,
}

impl IdentityCache {
    pub fn new(
        directory: Arc<dyn Directory>,
        settings: IdentitySettings,
        metrics: Metrics,
    ) -> Self {
        Self {
            directory,
            settings,
            entries: Arc::default(),
            loads: Arc::default(),
            load_permits: Arc::new(Semaphore::new(settings.max_concurrent_loads)),
            metrics,
        }
    }

    pub async fn authorize(
        &self,
        key: &ApiKey<'_>,
        now: DateTime<Utc>,
    ) -> Result<Identity, Denial> {
        let digest = key.digest();

        if let Some(record) = self.cached(&digest, self.settings.fresh_for) {
            self.metrics.record_identity(IdentityResult::Fresh);
            return evaluate(record, now);
        }

        match self.load(digest).await {
            Ok(Some(record)) => {
                self.metrics.record_identity(IdentityResult::Loaded);
                evaluate(record, now)
            }
            Ok(None) => {
                self.metrics.record_identity(IdentityResult::NotFound);
                Err(Denial::InvalidApiKey)
            }
            Err(DirectoryUnavailable) => {
                let Some(record) = self.cached(&digest, self.settings.stale_grace) else {
                    self.metrics.record_identity(IdentityResult::Unavailable);
                    return Err(Denial::Unavailable);
                };

                self.metrics.record_identity(IdentityResult::Stale);
                evaluate(record, now)
            }
        }
    }

    fn cached(&self, digest: &Digest, max_age: Duration) -> Option<IdentityRecord> {
        locked(&self.entries)
            .get(digest)
            .filter(|entry| entry.loaded_at.elapsed() < max_age)
            .map(|entry| entry.record.clone())
    }

    async fn load(&self, digest: Digest) -> Result<Option<IdentityRecord>, DirectoryUnavailable> {
        let load = {
            let mut loads = locked(&self.loads);
            if let Some(record) = self.cached(&digest, self.settings.fresh_for) {
                return Ok(Some(record));
            }

            loads
                .entry(digest)
                .or_insert_with(|| {
                    let directory = self.directory.clone();
                    let permits = self.load_permits.clone();
                    let metrics = self.metrics.clone();
                    let cache = self.clone();

                    // Spawned so an abandoned load still finishes and releases its permit.
                    let task = tokio::spawn(async move {
                        let result = match permits.try_acquire_owned() {
                            Ok(_permit) => {
                                metrics.record_identity_query();
                                directory.identity(digest).await
                            }
                            Err(_) => Err(DirectoryUnavailable),
                        };

                        match &result {
                            Ok(Some(record)) => cache.store(digest, record.clone()),
                            Ok(None) => {
                                locked(&cache.entries).remove(&digest);
                            }
                            Err(_) => {}
                        }
                        locked(&cache.loads).remove(&digest);
                        result
                    });

                    async move { task.await.unwrap_or(Err(DirectoryUnavailable)) }
                        .boxed()
                        .shared()
                })
                .clone()
        };

        load.await
    }

    fn store(&self, digest: Digest, record: IdentityRecord) {
        let mut entries = locked(&self.entries);
        if entries.len() >= self.settings.capacity && !entries.contains_key(&digest) {
            entries.retain(|_, entry| entry.loaded_at.elapsed() < self.settings.stale_grace);
        }

        if entries.len() >= self.settings.capacity && !entries.contains_key(&digest) {
            let oldest = entries
                .iter()
                .min_by_key(|(_, entry)| entry.loaded_at)
                .map(|(digest, _)| *digest);
            if let Some(oldest) = oldest {
                entries.remove(&oldest);
            }
        }

        entries.insert(
            digest,
            Entry {
                loaded_at: Instant::now(),
                record,
            },
        );
    }
}

fn evaluate(record: IdentityRecord, now: DateTime<Utc>) -> Result<Identity, Denial> {
    if record.revoked_at.is_some() || record.expires_at.is_some_and(|expires| expires <= now) {
        return Err(Denial::InvalidApiKey);
    }

    if record.workspace_archived {
        return Err(Denial::WorkspaceArchived);
    }

    if !record.organization_active {
        return Err(Denial::OrganizationSuspended);
    }

    Ok(Identity {
        api_key_id: record.api_key_id,
        organization_id: record.organization_id,
        workspace_id: record.workspace_id,
        trace_capture_enabled: record.trace_capture_enabled,
        trace_retention_days: record.trace_retention_days,
    })
}

fn locked<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

    use async_trait::async_trait;
    use axum::http::HeaderMap;

    use super::*;
    use crate::credentials;

    #[derive(Default)]
    struct TestDirectory {
        record: Mutex<Option<IdentityRecord>>,
        down: AtomicBool,
        queries: AtomicUsize,
        delay: Option<Duration>,
    }

    #[async_trait]
    impl Directory for TestDirectory {
        async fn identity(
            &self,
            _digest: Digest,
        ) -> Result<Option<IdentityRecord>, DirectoryUnavailable> {
            self.queries.fetch_add(1, Ordering::SeqCst);
            if let Some(delay) = self.delay {
                tokio::time::sleep(delay).await;
            }

            if self.down.load(Ordering::SeqCst) {
                return Err(DirectoryUnavailable);
            }

            Ok(self.record.lock().unwrap().clone())
        }

        async fn hosted_models(&self) -> Result<Vec<String>, DirectoryUnavailable> {
            Ok(Vec::new())
        }
    }

    fn record() -> IdentityRecord {
        IdentityRecord {
            api_key_id: Uuid::from_u128(1),
            organization_id: Uuid::from_u128(2),
            workspace_id: Uuid::from_u128(3),
            expires_at: None,
            revoked_at: None,
            workspace_archived: false,
            organization_active: true,
            trace_capture_enabled: false,
            trace_retention_days: 30,
        }
    }

    fn settings(fresh_for: Duration, stale_grace: Duration) -> IdentitySettings {
        IdentitySettings {
            fresh_for,
            stale_grace,
            capacity: 2,
            max_concurrent_loads: 4,
        }
    }

    fn cache(directory: &Arc<TestDirectory>, settings: IdentitySettings) -> IdentityCache {
        IdentityCache::new(directory.clone(), settings, Metrics::default())
    }

    async fn authorize(cache: &IdentityCache, key: &str) -> Result<Identity, Denial> {
        let mut headers = HeaderMap::new();
        headers.insert("x-gradiated-api-key", key.parse().unwrap());
        let credentials = credentials::extract(&headers).unwrap();

        cache
            .authorize(credentials.api_key.as_ref().unwrap(), Utc::now())
            .await
    }

    fn with_record(record: IdentityRecord) -> Arc<TestDirectory> {
        let directory = TestDirectory::default();
        *directory.record.lock().unwrap() = Some(record);

        Arc::new(directory)
    }

    #[tokio::test]
    async fn a_fresh_entry_answers_without_a_query() {
        let directory = with_record(record());
        let cache = cache(
            &directory,
            settings(Duration::from_secs(60), Duration::from_secs(60)),
        );

        assert_eq!(
            authorize(&cache, "grad_a").await.unwrap().workspace_id,
            Uuid::from_u128(3)
        );
        authorize(&cache, "grad_a").await.unwrap();

        assert_eq!(directory.queries.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn a_request_that_missed_before_a_completed_load_reuses_its_result() {
        let directory = with_record(record());
        let cache = cache(
            &directory,
            settings(Duration::from_secs(60), Duration::from_secs(60)),
        );
        let mut headers = HeaderMap::new();
        headers.insert("x-gradiated-api-key", "grad_a".parse().unwrap());
        let credentials = credentials::extract(&headers).unwrap();
        let digest = credentials.api_key.as_ref().unwrap().digest();

        assert!(cache.cached(&digest, cache.settings.fresh_for).is_none());
        assert!(authorize(&cache, "grad_a").await.is_ok());

        // This request missed the cache before the other request's load completed.
        assert!(cache.load(digest).await.unwrap().is_some());
        assert_eq!(directory.queries.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn an_abandoned_load_still_releases_its_permit() {
        let mut slow = TestDirectory {
            delay: Some(Duration::from_millis(200)),
            ..TestDirectory::default()
        };
        *slow.record.get_mut().unwrap() = Some(record());
        let directory = Arc::new(slow);
        let mut one_load = settings(Duration::from_secs(60), Duration::from_secs(60));
        one_load.max_concurrent_loads = 1;
        let cache = cache(&directory, one_load);

        let abandoned = tokio::spawn({
            let cache = cache.clone();
            async move { authorize(&cache, "grad_abandoned").await }
        });
        tokio::time::sleep(Duration::from_millis(50)).await;
        abandoned.abort();

        tokio::time::sleep(Duration::from_millis(300)).await;
        assert!(authorize(&cache, "grad_abandoned").await.is_ok());
        assert_eq!(directory.queries.load(Ordering::SeqCst), 1);
        assert!(authorize(&cache, "grad_next").await.is_ok());
        assert!(locked(&cache.loads).is_empty());
    }

    #[tokio::test]
    async fn a_directory_outage_serves_a_known_key_within_the_grace() {
        let directory = with_record(record());
        let cache = cache(
            &directory,
            settings(Duration::ZERO, Duration::from_secs(60)),
        );
        authorize(&cache, "grad_a").await.unwrap();

        directory.down.store(true, Ordering::SeqCst);

        assert!(authorize(&cache, "grad_a").await.is_ok());
        assert_eq!(
            authorize(&cache, "grad_unknown").await,
            Err(Denial::Unavailable)
        );
    }

    #[tokio::test]
    async fn the_grace_is_bounded() {
        let directory = with_record(record());
        let cache = cache(&directory, settings(Duration::ZERO, Duration::ZERO));
        authorize(&cache, "grad_a").await.unwrap();

        directory.down.store(true, Ordering::SeqCst);

        assert_eq!(authorize(&cache, "grad_a").await, Err(Denial::Unavailable));
    }

    #[tokio::test]
    async fn a_deleted_key_stops_working_once_the_directory_says_so() {
        let directory = with_record(record());
        let cache = cache(
            &directory,
            settings(Duration::ZERO, Duration::from_secs(60)),
        );
        authorize(&cache, "grad_a").await.unwrap();

        *directory.record.lock().unwrap() = None;
        assert_eq!(
            authorize(&cache, "grad_a").await,
            Err(Denial::InvalidApiKey)
        );

        directory.down.store(true, Ordering::SeqCst);
        assert_eq!(authorize(&cache, "grad_a").await, Err(Denial::Unavailable));
    }

    #[tokio::test]
    async fn denials_follow_the_record() {
        let now = Utc::now();
        for (change, denial) in [
            (
                IdentityRecord {
                    revoked_at: Some(now),
                    ..record()
                },
                Denial::InvalidApiKey,
            ),
            (
                IdentityRecord {
                    expires_at: Some(now - chrono::Duration::seconds(1)),
                    ..record()
                },
                Denial::InvalidApiKey,
            ),
            (
                IdentityRecord {
                    workspace_archived: true,
                    ..record()
                },
                Denial::WorkspaceArchived,
            ),
            (
                IdentityRecord {
                    organization_active: false,
                    ..record()
                },
                Denial::OrganizationSuspended,
            ),
        ] {
            let directory = with_record(change);
            let cache = cache(
                &directory,
                settings(Duration::from_secs(60), Duration::from_secs(60)),
            );

            assert_eq!(authorize(&cache, "grad_a").await, Err(denial));
        }
    }

    #[tokio::test]
    async fn concurrent_requests_for_one_key_share_one_query() {
        let directory = Arc::new(TestDirectory {
            record: Mutex::new(Some(record())),
            delay: Some(Duration::from_millis(50)),
            ..TestDirectory::default()
        });
        let cache = cache(
            &directory,
            settings(Duration::from_secs(60), Duration::from_secs(60)),
        );

        let results = futures_util::future::join_all((0..20).map(|_| {
            let cache = cache.clone();
            async move { authorize(&cache, "grad_a").await }
        }))
        .await;

        assert!(results.iter().all(Result::is_ok));
        assert_eq!(directory.queries.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn the_load_budget_bounds_distinct_unknown_keys() {
        let directory = Arc::new(TestDirectory {
            delay: Some(Duration::from_millis(50)),
            ..TestDirectory::default()
        });
        let cache = cache(
            &directory,
            settings(Duration::from_secs(60), Duration::from_secs(60)),
        );

        let results = futures_util::future::join_all((0..10).map(|index| {
            let cache = cache.clone();
            async move { authorize(&cache, &format!("grad_{index}")).await }
        }))
        .await;

        assert_eq!(directory.queries.load(Ordering::SeqCst), 4);
        assert_eq!(
            results
                .iter()
                .filter(|result| **result == Err(Denial::Unavailable))
                .count(),
            6
        );
    }

    #[tokio::test]
    async fn capacity_evicts_the_oldest_entry() {
        let directory = with_record(record());
        let cache = cache(
            &directory,
            settings(Duration::from_secs(60), Duration::from_secs(60)),
        );

        for key in ["grad_a", "grad_b", "grad_c"] {
            authorize(&cache, key).await.unwrap();
        }
        assert_eq!(locked(&cache.entries).len(), 2);

        authorize(&cache, "grad_a").await.unwrap();
        assert_eq!(directory.queries.load(Ordering::SeqCst), 4);
    }
}
