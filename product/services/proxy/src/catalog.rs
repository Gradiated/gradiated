use std::{
    collections::HashSet,
    sync::{Arc, RwLock},
    time::{Duration, Instant},
};

use crate::{directory::Directory, metrics::Metrics};

struct Snapshot {
    models: HashSet<String>,
    refreshed_at: Instant,
}

/// The set of hosted model IDs. A failed refresh keeps the last good set, so a
/// database outage never changes where requests go.
#[derive(Clone)]
pub struct HostedCatalog {
    snapshot: Arc<RwLock<Option<Arc<Snapshot>>>>,
    directory: Arc<dyn Directory>,
    metrics: Metrics,
}

impl HostedCatalog {
    pub fn new(directory: Arc<dyn Directory>, metrics: Metrics) -> Self {
        Self {
            snapshot: Arc::default(),
            directory,
            metrics,
        }
    }

    pub fn is_loaded(&self) -> bool {
        self.current().is_some()
    }

    /// Matches the gateway, which looks hosted models up by their lowercase name.
    pub fn is_hosted(&self, model: &str) -> bool {
        self.current()
            .is_some_and(|snapshot| snapshot.models.contains(&model.to_ascii_lowercase()))
    }

    pub fn age(&self) -> Option<Duration> {
        self.current()
            .map(|snapshot| snapshot.refreshed_at.elapsed())
    }

    /// The snapshot is as old as the moment its query started, not when it finished,
    /// so a slow query never makes the catalog look fresher than its data.
    pub async fn refresh(&self) -> bool {
        let started = Instant::now();
        let Ok(models) = self.directory.hosted_models().await else {
            self.metrics.record_catalog_refresh_failure();
            tracing::warn!(
                error_code = "catalog_refresh",
                "hosted catalog refresh failed"
            );
            return false;
        };

        let snapshot = Snapshot {
            models: models.into_iter().collect(),
            refreshed_at: started,
        };
        *self
            .snapshot
            .write()
            .unwrap_or_else(|poisoned| poisoned.into_inner()) = Some(Arc::new(snapshot));

        true
    }

    pub async fn run(self, interval: Duration) {
        let mut ticker = tokio::time::interval(interval);
        ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

        loop {
            ticker.tick().await;
            self.refresh().await;
        }
    }

    fn current(&self) -> Option<Arc<Snapshot>> {
        self.snapshot
            .read()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .clone()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use async_trait::async_trait;

    use super::*;
    use crate::directory::{DirectoryUnavailable, IdentityRecord};

    struct TestDirectory(Mutex<Result<Vec<String>, DirectoryUnavailable>>);

    #[async_trait]
    impl Directory for TestDirectory {
        async fn identity(
            &self,
            _digest: [u8; 32],
        ) -> Result<Option<IdentityRecord>, DirectoryUnavailable> {
            Ok(None)
        }

        async fn hosted_models(&self) -> Result<Vec<String>, DirectoryUnavailable> {
            self.0.lock().unwrap().clone()
        }
    }

    fn catalog(
        models: Result<Vec<String>, DirectoryUnavailable>,
    ) -> (HostedCatalog, Arc<TestDirectory>) {
        let directory = Arc::new(TestDirectory(Mutex::new(models)));

        (
            HostedCatalog::new(directory.clone(), Metrics::default()),
            directory,
        )
    }

    #[tokio::test]
    async fn nothing_is_hosted_before_the_first_load() {
        let (catalog, _) = catalog(Err(DirectoryUnavailable));

        assert!(!catalog.refresh().await);
        assert!(!catalog.is_loaded());
        assert!(!catalog.is_hosted("model-a"));
        assert_eq!(catalog.age(), None);
    }

    #[tokio::test]
    async fn names_match_case_insensitively_against_lowercase_ids() {
        let (catalog, _) = catalog(Ok(vec!["model-a".to_owned(), "Mixed-Case".to_owned()]));
        assert!(catalog.refresh().await);

        for (model, hosted) in [
            ("model-a", true),
            ("MODEL-A", true),
            ("model-b", false),
            // The gateway lowercases the request, so a stored uppercase ID can never match.
            ("Mixed-Case", false),
        ] {
            assert_eq!(catalog.is_hosted(model), hosted, "{model}");
        }
    }

    #[tokio::test]
    async fn a_failed_refresh_keeps_the_last_good_set() {
        let (catalog, directory) = catalog(Ok(vec!["model-a".to_owned()]));
        assert!(catalog.refresh().await);

        *directory.0.lock().unwrap() = Err(DirectoryUnavailable);
        assert!(!catalog.refresh().await);
        assert!(catalog.is_hosted("model-a"));

        *directory.0.lock().unwrap() = Ok(vec!["model-b".to_owned()]);
        assert!(catalog.refresh().await);
        assert!(!catalog.is_hosted("model-a"));
        assert!(catalog.is_hosted("model-b"));
    }

    struct SlowDirectory(Duration);

    #[async_trait]
    impl Directory for SlowDirectory {
        async fn identity(
            &self,
            _digest: [u8; 32],
        ) -> Result<Option<IdentityRecord>, DirectoryUnavailable> {
            Ok(None)
        }

        async fn hosted_models(&self) -> Result<Vec<String>, DirectoryUnavailable> {
            tokio::time::sleep(self.0).await;
            Ok(vec!["model-a".to_owned()])
        }
    }

    #[tokio::test]
    async fn the_age_counts_from_when_the_query_started() {
        let query_time = Duration::from_millis(100);
        let catalog = HostedCatalog::new(Arc::new(SlowDirectory(query_time)), Metrics::default());

        assert!(catalog.refresh().await);

        assert!(catalog.age().unwrap() >= query_time);
    }
}
