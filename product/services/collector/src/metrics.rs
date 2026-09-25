use std::sync::{atomic::Ordering, Arc};

use crate::spool::Backlog;

use prometheus_client::{
    encoding::{text::encode, EncodeLabelSet},
    metrics::{counter::Counter, family::Family, gauge::Gauge},
    registry::Registry,
};

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct ReasonLabels {
    reason: &'static str,
}

#[derive(Clone)]
pub struct Metrics {
    registry: Arc<Registry>,
    accepted: Counter,
    skipped: Counter,
    rejected: Family<ReasonLabels, Counter>,
    batches_uploaded: Counter,
    bytes_uploaded: Counter,
    upload_failures: Counter,
    batches_recovered: Counter,
    open_streams: Gauge,
    disk_bytes: Gauge,
    backlog: Arc<Backlog>,
}

impl Metrics {
    pub fn new(backlog: Arc<Backlog>) -> Self {
        let mut registry = Registry::with_prefix("gradiated_collector");
        let accepted = Counter::default();
        let skipped = Counter::default();
        let rejected = Family::<ReasonLabels, Counter>::default();
        let batches_uploaded = Counter::default();
        let bytes_uploaded = Counter::default();
        let upload_failures = Counter::default();
        let batches_recovered = Counter::default();
        let open_streams = Gauge::default();
        let disk_bytes = Gauge::default();
        let service_info = Gauge::<i64>::default();
        service_info.set(1);

        registry.register(
            "contents_accepted",
            "Generations written to a batch",
            accepted.clone(),
        );
        registry.register(
            "contents_skipped",
            "Generations without a task, which are not stored",
            skipped.clone(),
        );
        registry.register(
            "contents_rejected",
            "Generations refused, by reason",
            rejected.clone(),
        );
        registry.register(
            "batches_uploaded",
            "Batches stored with their manifest",
            batches_uploaded.clone(),
        );
        registry.register(
            "batch_bytes_uploaded",
            "Compressed bytes stored",
            bytes_uploaded.clone(),
        );
        registry.register(
            "upload_failures",
            "Failed batch uploads",
            upload_failures.clone(),
        );
        registry.register(
            "batches_recovered",
            "Batches found on disk at startup",
            batches_recovered.clone(),
        );
        registry.register(
            "open_streams",
            "Batches currently open",
            open_streams.clone(),
        );
        registry.register(
            "disk_bytes",
            "Batch bytes on local disk",
            disk_bytes.clone(),
        );
        registry.register(
            "service_info",
            "Always one while the collector runs",
            service_info,
        );

        Self {
            registry: Arc::new(registry),
            accepted,
            skipped,
            rejected,
            batches_uploaded,
            bytes_uploaded,
            upload_failures,
            batches_recovered,
            open_streams,
            disk_bytes,
            backlog,
        }
    }

    pub fn accepted(&self) {
        self.accepted.inc();
    }

    pub fn skipped(&self) {
        self.skipped.inc();
    }

    pub fn rejected(&self, reason: &'static str) {
        self.rejected.get_or_create(&ReasonLabels { reason }).inc();
    }

    pub fn batch_uploaded(&self, bytes: u64) {
        self.batches_uploaded.inc();
        self.bytes_uploaded.inc_by(bytes);
    }

    pub fn upload_failed(&self) {
        self.upload_failures.inc();
    }

    pub fn recovered(&self, batches: usize) {
        self.batches_recovered.inc_by(batches as u64);
    }

    pub fn set_open_streams(&self, count: usize) {
        self.open_streams.set(count as i64);
    }

    pub fn encode(&self) -> String {
        self.disk_bytes
            .set(self.backlog.bytes.load(Ordering::Acquire) as i64);

        let mut output = String::new();
        encode(&mut output, &self.registry).expect("encoding into a String cannot fail");

        output
    }
}
