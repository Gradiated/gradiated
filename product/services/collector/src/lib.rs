mod batch;
mod config;
mod http;
mod metrics;
mod postgres;
mod record;
mod relay;
mod relay_stream;
mod spool;
mod tasks;
mod upload;

#[cfg(test)]
mod collector_tests;
#[cfg(test)]
mod relay_tests;
#[cfg(test)]
mod test_support;

use std::{io, sync::Arc, time::Duration};

use object_store::ObjectStore;
use tokio::{sync::mpsc::unbounded_channel, task::JoinHandle};

pub use config::{CollectorConfig, ConfigError, Store};
pub use http::{admin_router, public_router, AppState};
pub use metrics::Metrics;

use crate::{
    postgres::PostgresService,
    spool::{Backlog, Spool},
    tasks::TaskService,
    upload::Uploader,
};

pub struct Collector {
    pub state: AppState,
    expiry: JoinHandle<()>,
    uploader: JoinHandle<()>,
    task_worker: Option<JoinHandle<()>>,
}

impl Collector {
    pub fn start(config: &CollectorConfig, store: Arc<dyn ObjectStore>) -> io::Result<Self> {
        let backlog = Arc::new(Backlog::default());
        let metrics = Metrics::new(backlog.clone());
        let (sealed, pending) = unbounded_channel();
        let (spool, recovered) = Spool::recover(
            &config.data_dir,
            config.limits,
            backlog.clone(),
            sealed.clone(),
            metrics.clone(),
        )?;
        metrics.recovered(recovered.len());
        for path in recovered {
            sealed.send(path).expect("the uploader has not started");
        }
        drop(sealed);

        let postgres = config
            .database_url
            .as_deref()
            .map(|url| PostgresService::new(url, config.database_ca_bundle_path.as_deref()))
            .transpose()?;
        let tasks = postgres
            .map(|postgres| TaskService::new(&config.data_dir, postgres, metrics.clone()))
            .transpose()?;
        let task_worker = tasks
            .as_ref()
            .map(|tasks| tokio::spawn(tasks.clone().run()));

        let spool = Arc::new(spool);
        let uploader = tokio::spawn(
            Uploader::new(
                store,
                &config.replica,
                backlog,
                metrics.clone(),
                tasks.clone(),
            )
            .run(pending),
        );
        let expiry = tokio::spawn({
            let spool = spool.clone();
            let tick = config.limits.max_batch_age.min(Duration::from_secs(1));
            async move {
                let mut interval = tokio::time::interval(tick);
                loop {
                    interval.tick().await;
                    spool.seal_expired();
                }
            }
        });

        Ok(Self {
            state: AppState {
                spool,
                tasks,
                token: Arc::from(config.token.as_str()),
                metrics,
                max_record_bytes: config.max_record_bytes,
                max_concurrent_requests: config.max_concurrent_requests,
            },
            expiry,
            uploader,
            task_worker,
        })
    }

    pub async fn shutdown(self, drain: Duration) {
        self.expiry.abort();
        self.state.spool.close();

        let mut uploader = self.uploader;

        if tokio::time::timeout(drain, &mut uploader).await.is_err() {
            tracing::warn!("uploads did not finish before the drain deadline");
            uploader.abort();
            let _ = uploader.await;
        }

        if let Some(task_worker) = self.task_worker {
            task_worker.abort();
            let _ = task_worker.await;
        }
    }
}
