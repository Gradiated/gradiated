use std::sync::Arc;

use chrono::{DateTime, Utc};
use prometheus_client::{
    encoding::{text::encode, EncodeLabelSet},
    metrics::{counter::Counter, family::Family, gauge::Gauge, histogram::Histogram},
    registry::Registry,
};
use uuid::Uuid;

use crate::{AdmissionError, NormalizedUsage, ServiceTier};

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
    dependency_ready: GaugeFamily<DependencyLabels>,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct HttpRequestLabels {
    route: String,
    status: String,
    error: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct GenerationLabels {
    model: String,
    deployment: String,
    protocol: String,
    stream: String,
    service_tier: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct AdmissionRejectionLabels {
    model: String,
    deployment: String,
    protocol: String,
    stream: String,
    service_tier: String,
    reason: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct GenerationOutcomeLabels {
    model: String,
    deployment: String,
    stream: String,
    service_tier: String,
    status: String,
    error: String,
    cancellation_owner: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct TokenLabels {
    model: String,
    deployment: String,
    stream: String,
    service_tier: String,
    kind: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct FinalizationLabels {
    model: String,
    deployment: String,
    stream: String,
    service_tier: String,
    result: String,
}

#[derive(Clone, Debug, EncodeLabelSet, Eq, Hash, PartialEq)]
struct DependencyLabels {
    dependency: String,
}

pub struct AdmittedGenerationMetrics {
    metrics: GatewayMetrics,
    labels: GenerationLabels,
}

impl GatewayMetrics {
    pub fn new() -> Self {
        let mut registry = Registry::with_prefix("gradiated_gateway");
        let service_info: Gauge = Gauge::default();
        service_info.set(1);
        registry.register(
            "service_info",
            "Constant service identity metric used to detect missing gateway telemetry.",
            service_info,
        );
        let http_requests = CounterFamily::default();
        let admissions = CounterFamily::default();
        let admission_rejections = CounterFamily::default();
        let active_generations = GaugeFamily::default();
        let generations = CounterFamily::default();
        let tokens = CounterFamily::default();
        let calculated_charge_nano_usd = CounterFamily::default();
        let input_tokens_per_generation = token_histograms();
        let output_tokens_per_generation = token_histograms();
        let dispatch_latency_seconds = latency_histograms();
        let time_to_first_token_seconds = latency_histograms();
        let runtime_time_to_first_token_seconds = latency_histograms();
        let runtime_latency_seconds = latency_histograms();
        let generation_latency_seconds = latency_histograms();
        let time_per_output_token_seconds = tpot_histograms();
        let output_tokens_per_second = throughput_histograms();
        let finalization_attempts = CounterFamily::default();
        let finalization_retries = CounterFamily::default();
        let finalization_failures = CounterFamily::default();
        let dependency_ready = GaugeFamily::default();

        registry.register(
            "http_requests",
            "HTTP requests completed.",
            http_requests.clone(),
        );
        registry.register(
            "admissions",
            "Generations admitted by Valkey.",
            admissions.clone(),
        );
        registry.register(
            "admission_rejections",
            "Generation admission attempts rejected before runtime dispatch.",
            admission_rejections.clone(),
        );
        registry.register(
            "active_generations",
            "Admitted generations that have not finished settlement.",
            active_generations.clone(),
        );
        registry.register(
            "generations",
            "Terminal generation outcomes.",
            generations.clone(),
        );
        registry.register("tokens", "Authoritative generation tokens.", tokens.clone());
        registry.register(
            "calculated_charge_nano_usd",
            "Terminal calculated generation charge in integer nano-USD.",
            calculated_charge_nano_usd.clone(),
        );
        registry.register(
            "input_tokens_per_generation",
            "Authoritative input-token distribution per generation.",
            input_tokens_per_generation.clone(),
        );
        registry.register(
            "output_tokens_per_generation",
            "Authoritative output-token distribution per generation.",
            output_tokens_per_generation.clone(),
        );
        registry.register(
            "dispatch_latency_seconds",
            "Time from gateway receipt until runtime dispatch.",
            dispatch_latency_seconds.clone(),
        );
        registry.register(
            "time_to_first_token_seconds",
            "Time from gateway receipt until first usable streamed output.",
            time_to_first_token_seconds.clone(),
        );
        registry.register(
            "runtime_time_to_first_token_seconds",
            "Time from runtime dispatch until first usable streamed output.",
            runtime_time_to_first_token_seconds.clone(),
        );
        registry.register(
            "runtime_latency_seconds",
            "Time from runtime dispatch until terminal runtime handling.",
            runtime_latency_seconds.clone(),
        );
        registry.register(
            "generation_latency_seconds",
            "Time from gateway receipt until terminal runtime handling.",
            generation_latency_seconds.clone(),
        );
        registry.register(
            "time_per_output_token_seconds",
            "Inter-token time after the first usable output token.",
            time_per_output_token_seconds.clone(),
        );
        registry.register(
            "output_tokens_per_second",
            "Authoritative output tokens divided by runtime latency.",
            output_tokens_per_second.clone(),
        );
        registry.register(
            "finalization_attempts",
            "Valkey finalization script attempts by result.",
            finalization_attempts.clone(),
        );
        registry.register(
            "finalization_retries",
            "Finalization retries after an unconfirmed attempt.",
            finalization_retries.clone(),
        );
        registry.register(
            "finalization_failures",
            "Generations whose finalization remained unconfirmed.",
            finalization_failures.clone(),
        );
        registry.register(
            "dependency_ready",
            "Whether a dependency passed its latest readiness check.",
            dependency_ready.clone(),
        );

        Self {
            inner: Arc::new(Metrics {
                registry,
                http_requests,
                admissions,
                admission_rejections,
                active_generations,
                generations,
                tokens,
                calculated_charge_nano_usd,
                input_tokens_per_generation,
                output_tokens_per_generation,
                dispatch_latency_seconds,
                time_to_first_token_seconds,
                runtime_time_to_first_token_seconds,
                runtime_latency_seconds,
                generation_latency_seconds,
                time_per_output_token_seconds,
                output_tokens_per_second,
                finalization_attempts,
                finalization_retries,
                finalization_failures,
                dependency_ready,
            }),
        }
    }

    pub fn record_http(&self, route: &'static str, status: u16, error: &'static str) {
        self.inner
            .http_requests
            .get_or_create(&HttpRequestLabels {
                route: route.to_owned(),
                status: status.to_string(),
                error: error.to_owned(),
            })
            .inc();
    }

    pub fn record_admission_rejection(
        &self,
        model: &str,
        deployment: Uuid,
        protocol: &str,
        stream: bool,
        service_tier: ServiceTier,
        error: &AdmissionError,
    ) {
        let labels = generation_labels(model, deployment, protocol, stream, service_tier);
        self.inner
            .admission_rejections
            .get_or_create(&AdmissionRejectionLabels {
                model: labels.model,
                deployment: labels.deployment,
                protocol: labels.protocol,
                stream: labels.stream,
                service_tier: labels.service_tier,
                reason: admission_reason(error).to_owned(),
            })
            .inc();
    }

    pub fn generation_admitted(
        &self,
        model: &str,
        deployment: Uuid,
        protocol: &str,
        stream: bool,
        service_tier: ServiceTier,
    ) -> AdmittedGenerationMetrics {
        let labels = generation_labels(model, deployment, protocol, stream, service_tier);
        self.inner.admissions.get_or_create(&labels).inc();
        self.inner.active_generations.get_or_create(&labels).inc();
        AdmittedGenerationMetrics {
            metrics: self.clone(),
            labels,
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
}

impl AdmittedGenerationMetrics {
    #[allow(clippy::too_many_arguments)]
    pub fn record_terminal(
        &self,
        status: &'static str,
        error: &'static str,
        cancellation_owner: &'static str,
        usage: NormalizedUsage,
        charge_nano_usd: u64,
        received_at: DateTime<Utc>,
        started_at: DateTime<Utc>,
        first_token_at: Option<DateTime<Utc>>,
        completed_at: DateTime<Utc>,
    ) {
        self.metrics
            .inner
            .generations
            .get_or_create(&GenerationOutcomeLabels {
                model: self.labels.model.clone(),
                deployment: self.labels.deployment.clone(),
                stream: self.labels.stream.clone(),
                service_tier: self.labels.service_tier.clone(),
                status: status.to_owned(),
                error: error.to_owned(),
                cancellation_owner: cancellation_owner.to_owned(),
            })
            .inc();
        for (kind, quantity) in [
            ("input", usage.input_tokens()),
            ("cached_input", usage.cached_input_tokens()),
            ("cache_write", usage.cache_write_tokens()),
            ("output", usage.output_tokens()),
            ("reasoning", usage.reasoning_tokens()),
        ] {
            self.metrics
                .inner
                .tokens
                .get_or_create(&TokenLabels {
                    model: self.labels.model.clone(),
                    deployment: self.labels.deployment.clone(),
                    stream: self.labels.stream.clone(),
                    service_tier: self.labels.service_tier.clone(),
                    kind: kind.to_owned(),
                })
                .inc_by(quantity);
        }
        self.metrics
            .inner
            .calculated_charge_nano_usd
            .get_or_create(&self.labels)
            .inc_by(charge_nano_usd);
        self.metrics
            .inner
            .input_tokens_per_generation
            .get_or_create(&self.labels)
            .observe(usage.input_tokens() as f64);
        self.metrics
            .inner
            .output_tokens_per_generation
            .get_or_create(&self.labels)
            .observe(usage.output_tokens() as f64);

        observe_duration(
            &self.metrics.inner.dispatch_latency_seconds,
            &self.labels,
            received_at,
            started_at,
        );
        observe_duration(
            &self.metrics.inner.runtime_latency_seconds,
            &self.labels,
            started_at,
            completed_at,
        );
        observe_duration(
            &self.metrics.inner.generation_latency_seconds,
            &self.labels,
            received_at,
            completed_at,
        );
        if let Some(first_token_at) = first_token_at {
            observe_duration(
                &self.metrics.inner.time_to_first_token_seconds,
                &self.labels,
                received_at,
                first_token_at,
            );
            observe_duration(
                &self.metrics.inner.runtime_time_to_first_token_seconds,
                &self.labels,
                started_at,
                first_token_at,
            );
            if usage.output_tokens() > 1 {
                let generation_seconds = seconds_between(first_token_at, completed_at);
                self.metrics
                    .inner
                    .time_per_output_token_seconds
                    .get_or_create(&self.labels)
                    .observe(generation_seconds / (usage.output_tokens() - 1) as f64);
            }
        }
        let runtime_seconds = seconds_between(started_at, completed_at);
        if runtime_seconds > 0.0 && usage.output_tokens() > 0 {
            self.metrics
                .inner
                .output_tokens_per_second
                .get_or_create(&self.labels)
                .observe(usage.output_tokens() as f64 / runtime_seconds);
        }
    }

    pub fn record_finalization_attempt(&self, result: &'static str) {
        self.metrics
            .inner
            .finalization_attempts
            .get_or_create(&FinalizationLabels {
                model: self.labels.model.clone(),
                deployment: self.labels.deployment.clone(),
                stream: self.labels.stream.clone(),
                service_tier: self.labels.service_tier.clone(),
                result: result.to_owned(),
            })
            .inc();
    }

    pub fn record_finalization_retry(&self) {
        self.metrics
            .inner
            .finalization_retries
            .get_or_create(&self.labels)
            .inc();
    }

    pub fn record_finalization_failure(&self) {
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

impl Default for GatewayMetrics {
    fn default() -> Self {
        Self::new()
    }
}

fn generation_labels(
    model: &str,
    deployment: Uuid,
    protocol: &str,
    stream: bool,
    service_tier: ServiceTier,
) -> GenerationLabels {
    GenerationLabels {
        model: model.to_owned(),
        deployment: deployment.to_string(),
        protocol: protocol.to_owned(),
        stream: stream.to_string(),
        service_tier: service_tier.as_str().to_owned(),
    }
}

fn admission_reason(error: &AdmissionError) -> &'static str {
    match error {
        AdmissionError::InvalidTiming(_) => "invalid_timing",
        AdmissionError::DeadlineElapsed => "deadline_elapsed",
        AdmissionError::InsufficientBalance => "insufficient_balance",
        AdmissionError::ConcurrencyExceeded => "concurrency_exceeded",
        AdmissionError::SettlementBacklog => "settlement_backlog",
        AdmissionError::DuplicateGeneration => "duplicate_generation",
        AdmissionError::UnknownScriptResult(_) => "unknown_script_result",
        AdmissionError::Redis(_) => "valkey_error",
    }
}

fn observe_duration(
    histograms: &HistogramFamily<GenerationLabels>,
    labels: &GenerationLabels,
    start: DateTime<Utc>,
    end: DateTime<Utc>,
) {
    histograms
        .get_or_create(labels)
        .observe(seconds_between(start, end));
}

fn seconds_between(start: DateTime<Utc>, end: DateTime<Utc>) -> f64 {
    end.signed_duration_since(start)
        .num_microseconds()
        .unwrap_or_default()
        .max(0) as f64
        / 1_000_000.0
}

fn latency_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| {
        Histogram::new([
            0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0,
        ])
    })
}

fn tpot_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| {
        Histogram::new([
            0.001, 0.0025, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0,
        ])
    })
}

fn throughput_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| {
        Histogram::new([1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0])
    })
}

fn token_histograms() -> HistogramFamily<GenerationLabels> {
    Family::new_with_constructor(|| {
        Histogram::new([
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
        ])
    })
}

#[cfg(test)]
mod tests {
    use chrono::TimeZone;

    use super::*;

    #[test]
    fn exposes_generation_dashboard_metrics_without_identity_labels() {
        let metrics = GatewayMetrics::new();
        metrics.record_http("models", 401, "invalid_api_key");
        metrics.set_dependency_ready("valkey", true);
        let generation = metrics.generation_admitted(
            "model-a",
            Uuid::from_u128(0x0198c36f9b6a70008000000000000001),
            "openai_chat",
            true,
            ServiceTier::Fast,
        );
        let received_at = Utc.with_ymd_and_hms(2026, 8, 20, 12, 0, 0).unwrap();
        generation.record_terminal(
            "succeeded",
            "none",
            "none",
            NormalizedUsage::new(100, 20, 0, 10, 0).unwrap(),
            12_000,
            received_at,
            received_at + chrono::TimeDelta::milliseconds(10),
            Some(received_at + chrono::TimeDelta::milliseconds(110)),
            received_at + chrono::TimeDelta::milliseconds(200),
        );
        generation.record_finalization_attempt("settled");
        drop(generation);
        let body = metrics.encode();

        assert!(body.contains("model=\"model-a\""));
        assert!(body.contains("gradiated_gateway_service_info 1"));
        assert!(body.contains("stream=\"true\""));
        assert!(body.contains("service_tier=\"fast\""));
        // Dashboards split ordinary LLM traffic from other protocols on this label.
        assert!(body.contains("protocol=\"openai_chat\""));
        assert!(body.contains("gradiated_gateway_time_to_first_token_seconds_count"));
        assert!(body.contains("gradiated_gateway_time_per_output_token_seconds_count"));
        assert!(body.contains("gradiated_gateway_output_tokens_per_second_count"));
        assert!(body.contains("gradiated_gateway_tokens_total"));
        assert!(body.contains("gradiated_gateway_calculated_charge_nano_usd_total"));
        assert!(!body.contains("organization"));
        assert!(!body.contains("workspace"));
        assert!(!body.contains("api_key=\""));
        assert!(!body.contains("generation_id=\""));
    }
}
