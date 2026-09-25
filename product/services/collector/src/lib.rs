mod batch;
mod config;
mod http;
mod metrics;
mod record;
mod relay;
mod relay_stream;
mod spool;
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
    spool::{Backlog, Spool},
    upload::Uploader,
};

pub struct Collector {
    pub state: AppState,
    expiry: JoinHandle<()>,
    uploader: JoinHandle<()>,
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

        let spool = Arc::new(spool);
        let uploader = tokio::spawn(
            Uploader::new(store, &config.replica, backlog, metrics.clone()).run(pending),
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
                token: Arc::from(config.token.as_str()),
                metrics,
                max_record_bytes: config.max_record_bytes,
                max_concurrent_requests: config.max_concurrent_requests,
            },
            expiry,
            uploader,
        })
    }

    pub async fn shutdown(self, drain: Duration) {
        self.expiry.abort();
        self.state.spool.close();

        if tokio::time::timeout(drain, self.uploader).await.is_err() {
            tracing::warn!("uploads did not finish before the drain deadline");
        }
    }
}
