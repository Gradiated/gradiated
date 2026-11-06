use std::sync::Arc;

use chrono::{DateTime, Utc};
use prometheus_client::{
    encoding::{text::encode, EncodeLabelSet},
    metrics::{counter::Counter, family::Family, gauge::Gauge, histogram::Histogram},
    registry::{Metric, Registry},
};
use uuid::Uuid;

use crate::{
    AdmissionError, CancellationOwner, GenerationStatus, GenerationTiming, NormalizedUsage,
    ServiceTier, TerminalOutcome,
};

type CounterFamily<L> = Family<L, Counter>;
type GaugeFamily<L> = Family<L, Gauge>;
type HistogramFamily<L> = Family<L, Histogram>;

#[derive(Clone)]
pub struct GatewayMetrics {
    inner: Arc<Metrics>,
}

struct Metrics {
    registry: Registry,
    http_requests: CounterFamily<HttpRequestLabels>,
    admissions: CounterFamily<GenerationLabels>,
    routing_capacity_rejections: CounterFamily<ModelTrafficLabels>,
    capacity_fallbacks: CounterFamily<CapacityFallbackLabels>,
    session_routes: CounterFamily<SessionRouteLabels>,
    upstream_cost_nano_usd: CounterFamily<GenerationLabels>,
    capacity_rejection_timestamp_seconds: GaugeFamily<ModelLabels>,
    admission_rejections: CounterFamily<AdmissionRejectionLabels>,
    active_generations: GaugeFamily<GenerationLabels>,
    generations: CounterFamily<GenerationOutcomeLabels>,
    tokens: CounterFamily<TokenLabels>,
    calculated_charge_nano_usd: CounterFamily<GenerationLabels>,
    input_tokens_per_generation: HistogramFamily<GenerationLabels>,
    output_tokens_per_generation: HistogramFamily<GenerationLabels>,
    dispatch_latency_seconds: HistogramFamily<GenerationLabels>,
    time_to_first_token_seconds: HistogramFamily<GenerationLabels>,
    runtime_time_to_first_token_seconds: HistogramFamily<GenerationLabels>,
    runtime_latency_seconds: HistogramFamily<GenerationLabels>,
    generation_latency_seconds: HistogramFamily<GenerationLabels>,
    time_per_output_token_seconds: HistogramFamily<GenerationLabels>,
    output_tokens_per_second: HistogramFamily<GenerationLabels>,
    finalization_attempts: CounterFamily<FinalizationLabels>,
    finalization_retries: CounterFamily<GenerationLabels>,
    finalization_failures: CounterFamily<GenerationLabels>,
    unsettled_generations: CounterFamily<GenerationLabels>,
    dependency_ready: GaugeFamily<DependencyLabels>,
    last_finalization_failure_timestamp_seconds: Gauge,
    last_settlement_backpressure_timestamp_seconds: Gauge,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct HttpRequestLabels {
    traffic: String,
    route: String,
    status: String,
    error: String,
}

/// Identifies what served a generation. It never names the customer.
#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct GenerationLabels {
    model: String,
    deployment: String,
    protocol: String,
    stream: String,
    service_tier: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct ModelLabels {
    model: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct ModelTrafficLabels {
    model: String,
    traffic: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct CapacityFallbackLabels {
    model: String,
    capacity: String,
    reason: String,
    traffic: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct SessionRouteLabels {
    model: String,
    outcome: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct AdmissionRejectionLabels {
    #[prometheus(flatten)]
    generation: GenerationLabels,
    reason: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct GenerationOutcomeLabels {
    #[prometheus(flatten)]
    generation: GenerationLabels,
    status: String,
    error: String,
    cancellation_owner: String,
    traffic: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct TokenLabels {
    #[prometheus(flatten)]
    generation: GenerationLabels,
    kind: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct FinalizationLabels {
    #[prometheus(flatten)]
    generation: GenerationLabels,
    result: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct DependencyLabels {
    dependency: String,
}

fn registered<M: Metric + Clone>(registry: &mut Registry, name: &str, help: &str, metric: M) -> M {
    registry.register(name, help, metric.clone());
    metric
}

impl GatewayMetrics {
    pub fn new() -> Self {
        let mut registry = Registry::with_prefix("gradiated_gateway");

        let service_info = Gauge::<i64>::default();
        service_info.set(1);
        registered(
            &mut registry,
            "service_info",
            "Constant service identity metric used to detect missing gateway telemetry.",
            service_info,
        );

        let metrics = Metrics {
            http_requests: registered(
                &mut registry,
                "http_requests",
                "HTTP requests completed.",
                CounterFamily::default(),
            ),
            admissions: registered(
                &mut registry,
                "admissions",
                "Generations admitted by Valkey.",
                CounterFamily::default(),
            ),
            routing_capacity_rejections: registered(
                &mut registry,
                "routing_capacity_rejections",
                "Qualified requests rejected because every healthy runtime was at capacity.",
                CounterFamily::default(),
            ),
            capacity_fallbacks: registered(
                &mut registry,
                "capacity_fallbacks",
                "Generations moved to other capacity before any output, by destination and reason.",
                CounterFamily::default(),
            ),
            session_routes: registered(
                &mut registry,
                "session_routes",
                "Generations placed on a local replica, by whether the session kept its replica.",
                CounterFamily::default(),
            ),
            upstream_cost_nano_usd: registered(
                &mut registry,
                "upstream_cost_nano_usd",
                "What external capacity reported charging Gradiated, in integer nano-USD.",
                CounterFamily::default(),
            ),
            capacity_rejection_timestamp_seconds: registered(
                &mut registry,
                "capacity_rejection_timestamp_seconds",
                "Unix timestamp of the most recent routing or runtime capacity rejection.",
                GaugeFamily::default(),
            ),
            admission_rejections: registered(
                &mut registry,
                "admission_rejections",
                "Generation admission attempts rejected before runtime dispatch.",
                CounterFamily::default(),
            ),
            active_generations: registered(
                &mut registry,
                "active_generations",
                "Admitted generations that have not finished settlement.",
                GaugeFamily::default(),
            ),
            generations: registered(
                &mut registry,
                "generations",
                "Terminal generation outcomes.",
                CounterFamily::default(),
            ),
            tokens: registered(
                &mut registry,
                "tokens",
                "Authoritative generation tokens.",
                CounterFamily::default(),
            ),
            calculated_charge_nano_usd: registered(
                &mut registry,
                "calculated_charge_nano_usd",
                "Terminal calculated generation charge in integer nano-USD.",
                CounterFamily::default(),
            ),
            input_tokens_per_generation: registered(
                &mut registry,
                "input_tokens_per_generation",
                "Authoritative input-token distribution per generation.",
                token_histograms(),
            ),
            output_tokens_per_generation: registered(
                &mut registry,
                "output_tokens_per_generation",
                "Authoritative output-token distribution per generation.",
                token_histograms(),
            ),
            dispatch_latency_seconds: registered(
                &mut registry,
                "dispatch_latency_seconds",
                "Time from gateway receipt until runtime dispatch.",
                latency_histograms(),
            ),
            time_to_first_token_seconds: registered(
                &mut registry,
                "time_to_first_token_seconds",
                "Time from gateway receipt until first usable streamed output.",
                latency_histograms(),
            ),
            runtime_time_to_first_token_seconds: registered(
                &mut registry,
                "runtime_time_to_first_token_seconds",
                "Time from runtime dispatch until first usable streamed output.",
                latency_histograms(),
            ),
            runtime_latency_seconds: registered(
                &mut registry,
                "runtime_latency_seconds",
                "Time from runtime dispatch until terminal runtime handling.",
                latency_histograms(),
            ),
            generation_latency_seconds: registered(
                &mut registry,
                "generation_latency_seconds",
                "Time from gateway receipt until terminal runtime handling.",
                latency_histograms(),
            ),
            time_per_output_token_seconds: registered(
                &mut registry,
                "time_per_output_token_seconds",
                "Inter-token time after the first usable output token.",
                tpot_histograms(),
            ),
            output_tokens_per_second: registered(
                &mut registry,
                "output_tokens_per_second",
                "Authoritative output tokens divided by runtime latency.",
                throughput_histograms(),
            ),
            finalization_attempts: registered(
                &mut registry,
                "finalization_attempts",
                "Valkey finalization script attempts by result.",
                CounterFamily::default(),
            ),
            finalization_retries: registered(
                &mut registry,
                "finalization_retries",
                "Finalization retries after an unconfirmed attempt.",
                CounterFamily::default(),
            ),
            finalization_failures: registered(
                &mut registry,
                "finalization_failures",
                "Generations whose finalization remained unconfirmed.",
                CounterFamily::default(),
            ),
            unsettled_generations: registered(
                &mut registry,
                "unsettled_generations",
                "Generations served without a charge or a terminal event, their lease lost.",
                CounterFamily::default(),
            ),
            dependency_ready: registered(
                &mut registry,
                "dependency_ready",
                "Whether a dependency passed its latest readiness check.",
                GaugeFamily::default(),
            ),
            last_finalization_failure_timestamp_seconds: registered(
                &mut registry,
                "last_finalization_failure_timestamp_seconds",
                "Unix timestamp of the latest unconfirmed finalization; zero before any failure.",
                Gauge::default(),
            ),
            last_settlement_backpressure_timestamp_seconds: registered(
                &mut registry,
                "last_settlement_backpressure_timestamp_seconds",
                "Unix timestamp of the latest admission refused for settlement backlog; zero before any refusal.",
                Gauge::default(),
            ),
            registry,
        };

        Self {
            inner: Arc::new(metrics),
        }
    }

    pub fn record_http(
        &self,
        route: &'static str,
        status: u16,
        error: &'static str,
        is_verification: bool,
    ) {
        self.inner
            .http_requests
            .get_or_create(&HttpRequestLabels {
                traffic: traffic(is_verification).to_owned(),
                route: route.to_owned(),
                status: status.to_string(),
                error: error.to_owned(),
            })
            .inc();
    }

    pub(crate) fn record_admission_rejection(
        &self,
        scope: &GenerationScope<'_>,
        error: &AdmissionError,
    ) {
        if matches!(error, AdmissionError::SettlementBacklog) {
            self.inner
                .last_settlement_backpressure_timestamp_seconds
                .set(Utc::now().timestamp());
        }

        self.inner
            .admission_rejections
            .get_or_create(&AdmissionRejectionLabels {
                generation: scope.into(),
                reason: error.diagnostic_code().to_owned(),
            })
            .inc();
    }

    pub(crate) fn generation_admitted(
        &self,
        scope: &GenerationScope<'_>,
    ) -> AdmittedGenerationMetrics {
        let labels = GenerationLabels::from(scope);
        self.inner.admissions.get_or_create(&labels).inc();
        self.inner.active_generations.get_or_create(&labels).inc();
        drop(self.inner.runtime_latency_seconds.get_or_create(&labels));

        AdmittedGenerationMetrics {
            metrics: self.clone(),
            labels,
            is_verification: scope.is_verification,
        }
    }

    pub(crate) fn record_capacity_pressure(&self, model: &str) {
        self.inner
            .capacity_rejection_timestamp_seconds
            .get_or_create(&ModelLabels {
                model: model.to_owned(),
            })
            .set(Utc::now().timestamp());
    }

    pub(crate) fn routing_capacity_rejected(&self, model: &str, is_verification: bool) {
        self.record_capacity_pressure(model);

        self.inner
            .routing_capacity_rejections
            .get_or_create(&ModelTrafficLabels {
                model: model.to_owned(),
                traffic: traffic(is_verification).to_owned(),
            })
            .inc();
    }

    pub(crate) fn session_routed(&self, model: &str, outcome: &str) {
        self.inner
            .session_routes
            .get_or_create(&SessionRouteLabels {
                model: model.to_owned(),
                outcome: outcome.to_owned(),
            })
            .inc();
    }

    pub(crate) fn capacity(&self, model: &str, is_verification: bool) -> CapacityMetrics {
        CapacityMetrics {
            metrics: self.clone(),
            model: model.to_owned(),
            is_verification,
        }
    }

    pub fn set_dependency_ready(&self, dependency: &'static str, ready: bool) {
        self.inner
            .dependency_ready
            .get_or_create(&DependencyLabels {
                dependency: dependency.to_owned(),
            })
            .set(i64::from(ready));
    }

    pub fn encode(&self) -> String {
        let mut body = String::new();
        encode(&mut body, &self.inner.registry).expect("gateway metrics always encode");

        body
    }

    #[cfg(test)]
    pub(crate) fn sample(&self, name: &str, label: &str) -> Option<i64> {
        self.encode()
            .lines()
            .filter(|line| line.starts_with(&format!("gradiated_gateway_{name}{{")))
            .filter(|line| line.contains(label))
            .map(|line| line.rsplit(' ').next().unwrap().parse::<i64>().unwrap())
            .reduce(|total, value| total + value)
    }
}

impl Default for GatewayMetrics {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Capacity {
    Local,
    Adapter,
    OpenRouter,
}

impl Capacity {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Local => "local",
            Self::Adapter => "adapter",
            Self::OpenRouter => "openrouter",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum FallbackReason {
    NoDeployment,
    Unavailable,
    AtCapacity,
    CapacityExceeded,
    AttemptFailed,
}

impl FallbackReason {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::NoDeployment => "no_deployment",
            Self::Unavailable => "unavailable",
            Self::AtCapacity => "at_capacity",
            Self::CapacityExceeded => "capacity_exceeded",
            Self::AttemptFailed => "attempt_failed",
        }
    }

    fn is_capacity(self) -> bool {
        matches!(self, Self::AtCapacity | Self::CapacityExceeded)
    }
}

/// Records each move to other capacity when it happens, since saturation of our
/// own capacity is the autoscaling signal even when another capacity serves.
#[derive(Clone)]
pub(crate) struct CapacityMetrics {
    metrics: GatewayMetrics,
    model: String,
    is_verification: bool,
}

impl CapacityMetrics {
    pub(crate) fn fell_back(&self, to: Capacity, reason: FallbackReason) {
        if reason.is_capacity() {
            self.metrics.record_capacity_pressure(&self.model);
        }

        self.metrics
            .inner
            .capacity_fallbacks
            .get_or_create(&CapacityFallbackLabels {
                model: self.model.clone(),
                capacity: to.as_str().to_owned(),
                reason: reason.as_str().to_owned(),
                traffic: traffic(self.is_verification).to_owned(),
            })
            .inc();
    }
}

fn traffic(is_verification: bool) -> &'static str {
    if is_verification {
        "verification"
    } else {
        "routed"
    }
}

pub(crate) struct GenerationScope<'a> {
    pub model: &'a str,
    pub deployment: String,
    pub protocol: &'static str,
    pub stream: bool,
    pub service_tier: ServiceTier,
    pub is_verification: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum FinalizationAttempt {
    Settled,
    AlreadyAbsent,
    Error,
}

impl FinalizationAttempt {
    fn as_str(self) -> &'static str {
        match self {
            Self::Settled => "settled",
            Self::AlreadyAbsent => "already_absent",
            Self::Error => "error",
        }
    }
}

pub(crate) struct TerminalRecord<'a> {
    pub generation_id: Uuid,
    pub outcome: &'a TerminalOutcome,
    pub usage: NormalizedUsage,
    pub charge_nano_usd: u64,
    pub timing: &'a GenerationTiming,
    pub capacity: Capacity,
    pub fallback_reason: Option<FallbackReason>,
    pub upstream_cost_nano_usd: Option<u64>,
}

pub(crate) struct AdmittedGenerationMetrics {
    is_verification: bool,
    metrics: GatewayMetrics,
    labels: GenerationLabels,
}

impl AdmittedGenerationMetrics {
    pub(crate) fn prepare_deployment(&self, deployment: String) {
        let labels = GenerationLabels {
            deployment,
            ..self.labels.clone()
        };
        drop(
            self.metrics
                .inner
                .runtime_latency_seconds
                .get_or_create(&labels),
        );
    }

    pub(crate) fn served_by(&mut self, deployment: String) {
        if self.labels.deployment == deployment {
            return;
        }

        let active = &self.metrics.inner.active_generations;
        active.get_or_create(&self.labels).dec();
        self.labels.deployment = deployment;
        active.get_or_create(&self.labels).inc();
        drop(
            self.metrics
                .inner
                .runtime_latency_seconds
                .get_or_create(&self.labels),
        );
    }

    pub(crate) fn record_terminal(&self, record: &TerminalRecord<'_>) {
        let TerminalRecord {
            generation_id,
            outcome,
            usage,
            charge_nano_usd,
            timing,
            capacity,
            fallback_reason,
            upstream_cost_nano_usd,
        } = *record;
        let received_at = timing.received_at();
        let started_at = timing.started_at();
        let first_token_at = timing.first_token_at();
        let completed_at = timing.completed_at();
        let labels = &self.labels;
        let metrics = &self.metrics.inner;
        let status = GenerationStatus::as_str(outcome.status());
        let error_code = outcome.error_code().unwrap_or("none");
        if error_code == "capacity_exceeded" {
            self.metrics.record_capacity_pressure(&labels.model);
        }

        let traffic = traffic(self.is_verification);
        let cancellation_owner = outcome
            .cancellation_owner()
            .map_or("none", CancellationOwner::as_str);

        tracing::info!(
            %generation_id,
            model = %labels.model,
            deployment = %labels.deployment,
            protocol = %labels.protocol,
            stream = %labels.stream,
            service_tier = %labels.service_tier,
            status, error_code, cancellation_owner, traffic,
            capacity = capacity.as_str(),
            fallback_reason = fallback_reason.map(FallbackReason::as_str),
            upstream_cost_nano_usd,
            input_tokens = usage.input_tokens(),
            cached_input_tokens = usage.cached_input_tokens(),
            cache_write_tokens = usage.cache_write_tokens(),
            output_tokens = usage.output_tokens(),
            reasoning_tokens = usage.reasoning_tokens(),
            duration_ms = seconds_between(received_at, completed_at) * 1000.0,
            runtime_ms = seconds_between(started_at, completed_at) * 1000.0,
            ttft_ms = first_token_at.map(|first| seconds_between(received_at, first) * 1000.0),
            event = "generation_terminal",
            "generation reached terminal state; billing finalization follows"
        );

        metrics
            .generations
            .get_or_create(&GenerationOutcomeLabels {
                generation: labels.clone(),
                status: status.to_owned(),
                error: error_code.to_owned(),
                cancellation_owner: cancellation_owner.to_owned(),
                traffic: traffic.to_owned(),
            })
            .inc();
        for (kind, quantity) in [
            ("input", usage.input_tokens()),
            ("cached_input", usage.cached_input_tokens()),
            ("cache_write", usage.cache_write_tokens()),
            ("output", usage.output_tokens()),
            ("reasoning", usage.reasoning_tokens()),
        ] {
            metrics
                .tokens
                .get_or_create(&TokenLabels {
                    generation: labels.clone(),
                    kind: kind.to_owned(),
                })
                .inc_by(quantity);
        }
        metrics
            .calculated_charge_nano_usd
            .get_or_create(labels)
            .inc_by(charge_nano_usd);
        if let Some(cost) = upstream_cost_nano_usd {
            metrics
                .upstream_cost_nano_usd
                .get_or_create(labels)
                .inc_by(cost);
        }
        metrics
            .input_tokens_per_generation
            .get_or_create(labels)
            .observe(usage.input_tokens() as f64);
        metrics
            .output_tokens_per_generation
            .get_or_create(labels)
            .observe(usage.output_tokens() as f64);

        let observe = |histograms: &HistogramFamily<GenerationLabels>, start, end| {
            histograms
                .get_or_create(labels)
                .observe(seconds_between(start, end));
        };
        observe(&metrics.dispatch_latency_seconds, received_at, started_at);
        observe(&metrics.runtime_latency_seconds, started_at, completed_at);
        observe(
            &metrics.generation_latency_seconds,
            received_at,
            completed_at,
        );

        if let Some(first_token_at) = first_token_at {
            observe(
                &metrics.time_to_first_token_seconds,
                received_at,
                first_token_at,
            );
            observe(
                &metrics.runtime_time_to_first_token_seconds,
                started_at,
                first_token_at,
            );

            if usage.output_tokens() > 1 {
                let generation_seconds = seconds_between(first_token_at, completed_at);
                metrics
                    .time_per_output_token_seconds
                    .get_or_create(labels)
                    .observe(generation_seconds / (usage.output_tokens() - 1) as f64);
            }
        }

        let runtime_seconds = seconds_between(started_at, completed_at);
        if runtime_seconds > 0.0 && usage.output_tokens() > 0 {
            metrics
                .output_tokens_per_second
                .get_or_create(labels)
                .observe(usage.output_tokens() as f64 / runtime_seconds);
        }
    }

    pub(crate) fn record_unsettled_generation(&self) {
        self.metrics
            .inner
            .unsettled_generations
            .get_or_create(&self.labels)
            .inc();
    }

    pub(crate) fn record_finalization_attempt(&self, result: FinalizationAttempt) {
        self.metrics
            .inner
            .finalization_attempts
            .get_or_create(&FinalizationLabels {
                generation: self.labels.clone(),
                result: result.as_str().to_owned(),
            })
            .inc();
    }

    pub(crate) fn record_finalization_retry(&self) {
        self.metrics
            .inner
            .finalization_retries
            .get_or_create(&self.labels)
            .inc();
    }

    pub(crate) fn record_finalization_failure(&self) {
        self.metrics
            .inner
            .last_finalization_failure_timestamp_seconds
            .set(Utc::now().timestamp());
        self.metrics
            .inner
            .finalization_failures
            .get_or_create(&self.labels)
            .inc();
    }
}

impl Drop for AdmittedGenerationMetrics {
    fn drop(&mut self) {
        self.metrics
            .inner
            .active_generations
            .get_or_create(&self.labels)
            .dec();
    }
}

impl From<&GenerationScope<'_>> for GenerationLabels {
    fn from(scope: &GenerationScope<'_>) -> Self {
        Self {
            model: scope.model.to_owned(),
            deployment: scope.deployment.clone(),
            protocol: scope.protocol.to_owned(),
            stream: scope.stream.to_string(),
            service_tier: scope.service_tier.as_str().to_owned(),
        }
    }
}

fn seconds_between(start: DateTime<Utc>, end: DateTime<Utc>) -> f64 {
    end.signed_duration_since(start)
        .num_microseconds()
        .unwrap_or_default()
        .max(0) as f64
        / 1_000_000.0
}

const LATENCY_BUCKETS: [f64; 15] = [
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0,
];
const TPOT_BUCKETS: [f64; 12] = [
    0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0,
];
const THROUGHPUT_BUCKETS: [f64; 9] = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0];
const TOKEN_BUCKETS: [f64; 10] = [
    1.0,
    8.0,
    32.0,
    128.0,
    512.0,
    2_048.0,
    8_192.0,
    32_768.0,
    131_072.0,
    1_048_576.0,
];

fn latency_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| Histogram::new(LATENCY_BUCKETS))
}

fn tpot_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| Histogram::new(TPOT_BUCKETS))
}

fn throughput_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| Histogram::new(THROUGHPUT_BUCKETS))
}

fn token_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| Histogram::new(TOKEN_BUCKETS))
}

#[cfg(test)]
#[path = "metrics_tests.rs"]
mod tests;
