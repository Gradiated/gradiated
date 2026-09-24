use std::{
    fmt::Write,
    sync::{Arc, Mutex},
    time::Duration,
};

use prometheus_client::{
    encoding::{text::encode, EncodeLabelSet, EncodeLabelValue, LabelValueEncoder},
    metrics::{counter::Counter, family::Family, gauge::Gauge, histogram::Histogram},
    registry::Registry,
};

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub enum Destination {
    Gateway,
    Anthropic,
    OpenAi,
    Local,
}

impl EncodeLabelValue for Destination {
    fn encode(&self, encoder: &mut LabelValueEncoder) -> std::fmt::Result {
        encoder.write_str(match self {
            Self::Gateway => "gateway",
            Self::Anthropic => "anthropic",
            Self::OpenAi => "openai",
            Self::Local => "local",
        })
    }
}

#[derive(Clone, Copy, Debug, Hash, PartialEq, Eq)]
pub enum IdentityResult {
    Fresh,
    Loaded,
    Stale,
    NotFound,
    Unavailable,
}

impl EncodeLabelValue for IdentityResult {
    fn encode(&self, encoder: &mut LabelValueEncoder) -> std::fmt::Result {
        encoder.write_str(match self {
            Self::Fresh => "fresh",
            Self::Loaded => "loaded",
            Self::Stale => "stale",
            Self::NotFound => "not_found",
            Self::Unavailable => "unavailable",
        })
    }
}

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct RequestLabels {
    destination: Destination,
    status: u16,
}

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct DestinationLabels {
    destination: Destination,
}

#[derive(Clone, Debug, Hash, PartialEq, Eq, EncodeLabelSet)]
struct IdentityLabels {
    result: IdentityResult,
}

/// Labels are fixed enums and status codes. Keys, workspaces and model names
/// never become labels.
#[derive(Clone)]
pub struct Metrics {
    registry: Arc<Mutex<Registry>>,
    requests: Family<RequestLabels, Counter>,
    upstream_headers: Family<DestinationLabels, Histogram>,
    in_flight: Family<DestinationLabels, Gauge>,
    identity: Family<IdentityLabels, Counter>,
    identity_queries: Counter,
    catalog_age: Gauge<f64, std::sync::atomic::AtomicU64>,
    catalog_refresh_failures: Counter,
}

impl Default for Metrics {
    fn default() -> Self {
        let mut registry = Registry::with_prefix("gradiated_proxy");
        let requests = Family::<RequestLabels, Counter>::default();
        let upstream_headers = Family::<DestinationLabels, Histogram>::new_with_constructor(|| {
            Histogram::new([
                0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0,
            ])
        });
        let in_flight = Family::<DestinationLabels, Gauge>::default();
        let identity = Family::<IdentityLabels, Counter>::default();
        let identity_queries = Counter::default();
        let catalog_age = Gauge::<f64, std::sync::atomic::AtomicU64>::default();
        let catalog_refresh_failures = Counter::default();
        let service_info = Gauge::<i64>::default();
        service_info.set(1);

        registry.register(
            "service_info",
            "Constant 1 while the proxy process is running",
            service_info,
        );
        registry.register(
            "requests",
            "Completed response heads by destination and status",
            requests.clone(),
        );
        registry.register(
            "upstream_header_seconds",
            "Time from dispatch to upstream response headers",
            upstream_headers.clone(),
        );
        registry.register(
            "in_flight",
            "Requests whose response is still open",
            in_flight.clone(),
        );
        registry.register(
            "identity_lookups",
            "Gradiated key lookups by result",
            identity.clone(),
        );
        registry.register(
            "identity_queries",
            "Database queries for Gradiated keys, after concurrent lookups share one",
            identity_queries.clone(),
        );
        registry.register(
            "catalog_age_seconds",
            "Seconds since the hosted catalog last refreshed",
            catalog_age.clone(),
        );
        registry.register(
            "catalog_refresh_failures",
            "Hosted catalog refreshes that failed",
            catalog_refresh_failures.clone(),
        );

        Self {
            registry: Arc::new(Mutex::new(registry)),
            requests,
            upstream_headers,
            in_flight,
            identity,
            identity_queries,
            catalog_age,
            catalog_refresh_failures,
        }
    }
}

impl Metrics {
    pub fn record_response(&self, destination: Destination, status: u16) {
        self.requests
            .get_or_create(&RequestLabels {
                destination,
                status,
            })
            .inc();
    }

    pub fn record_upstream_headers(&self, destination: Destination, elapsed: Duration) {
        self.upstream_headers
            .get_or_create(&DestinationLabels { destination })
            .observe(elapsed.as_secs_f64());
    }

    pub fn in_flight(&self, destination: Destination) -> InFlight {
        let gauge = self
            .in_flight
            .get_or_create(&DestinationLabels { destination })
            .clone();
        gauge.inc();

        InFlight(gauge)
    }

    pub fn record_identity(&self, result: IdentityResult) {
        self.identity
            .get_or_create(&IdentityLabels { result })
            .inc();
    }

    pub fn record_identity_query(&self) {
        self.identity_queries.inc();
    }

    pub fn set_catalog_age(&self, age: Option<Duration>) {
        self.catalog_age
            .set(age.map_or(f64::INFINITY, |age| age.as_secs_f64()));
    }

    pub fn record_catalog_refresh_failure(&self) {
        self.catalog_refresh_failures.inc();
    }

    pub fn encode(&self) -> String {
        let mut output = String::new();
        let registry = self
            .registry
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        encode(&mut output, &registry).expect("writing to a String cannot fail");

        output
    }
}

/// Decrements the in-flight gauge when the response body finishes or is dropped.
pub struct InFlight(Gauge);

impl Drop for InFlight {
    fn drop(&mut self) {
        self.0.dec();
    }
}
