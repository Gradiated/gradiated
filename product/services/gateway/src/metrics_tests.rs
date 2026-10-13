use std::collections::{BTreeMap, BTreeSet};

use chrono::{TimeDelta, TimeZone};

use super::*;
use crate::{generation::FinishReason, GatewayError};

const GENERATION: [&str; 5] = ["deployment", "model", "protocol", "service_tier", "stream"];

fn scope(deployment: Uuid) -> GenerationScope<'static> {
    GenerationScope {
        model: "model-a",
        deployment,
        protocol: "openai_chat",
        stream: true,
        service_tier: ServiceTier::Fast,
    }
}

fn admitted(metrics: &GatewayMetrics) -> AdmittedGenerationMetrics {
    metrics.generation_admitted(&scope(Uuid::from_u128(1)))
}

struct Terminal {
    outcome: TerminalOutcome,
    usage: NormalizedUsage,
    charge_nano_usd: u64,
    timing: GenerationTiming,
}

impl Terminal {
    fn record(&self) -> TerminalRecord<'_> {
        TerminalRecord {
            generation_id: Uuid::from_u128(1),
            outcome: &self.outcome,
            usage: self.usage,
            charge_nano_usd: self.charge_nano_usd,
            timing: &self.timing,
        }
    }
}

fn terminal(output_tokens: u64, first_token_ms: Option<i64>, runtime_ms: i64) -> Terminal {
    let received_at = Utc.with_ymd_and_hms(2026, 8, 20, 12, 0, 0).unwrap();
    let started_at = received_at + TimeDelta::milliseconds(10);
    let stop = FinishReason::parse("stop".to_owned()).unwrap();

    Terminal {
        outcome: TerminalOutcome::succeeded(stop, true),
        usage: NormalizedUsage::new(100, 20, 0, output_tokens, 0).unwrap(),
        charge_nano_usd: 12_000,
        timing: GenerationTiming::ordered(
            received_at,
            started_at,
            first_token_ms.map(|ms| started_at + TimeDelta::milliseconds(ms)),
            started_at + TimeDelta::milliseconds(runtime_ms),
        ),
    }
}

fn admission_errors() -> Vec<(AdmissionError, &'static str)> {
    vec![
        (AdmissionError::InvalidTiming("skew"), "invalid_timing"),
        (AdmissionError::DeadlineElapsed, "deadline_elapsed"),
        (AdmissionError::InsufficientBalance, "insufficient_balance"),
        (AdmissionError::ConcurrencyExceeded, "concurrency_exceeded"),
        (AdmissionError::SettlementBacklog, "settlement_backlog"),
        (AdmissionError::DuplicateGeneration, "duplicate_generation"),
        (
            AdmissionError::UnknownScriptResult(7),
            "unknown_script_result",
        ),
        (
            AdmissionError::Redis(redis::RedisError::from((redis::ErrorKind::Io, "refused"))),
            "valkey_error",
        ),
    ]
}

fn reject(metrics: &GatewayMetrics, error: &AdmissionError) {
    metrics.record_admission_rejection(&scope(Uuid::from_u128(1)), error);
}

fn encoded_families(body: &str) -> BTreeMap<String, (String, BTreeSet<String>)> {
    let mut families = BTreeMap::new();
    let mut family = None;

    for line in body.lines() {
        if let Some(declaration) = line.strip_prefix("# TYPE ") {
            let (name, kind) = declaration.split_once(' ').unwrap();
            let encoded = match kind {
                "counter" => format!("{name}_total"),
                _ => name.to_owned(),
            };
            families.insert(encoded.clone(), (kind.to_owned(), BTreeSet::new()));
            family = Some(encoded);
            continue;
        }

        if line.starts_with('#') {
            continue;
        }

        let Some((_, labels)) = line.split_once('{') else {
            continue;
        };
        let keys = &mut families.get_mut(family.as_ref().unwrap()).unwrap().1;
        for pair in labels.split('}').next().unwrap().split(',') {
            let key = pair.split_once('=').unwrap().0;
            if key != "le" {
                keys.insert(key.to_owned());
            }
        }
    }

    families
}

#[test]
fn encodes_the_registered_metric_contract() {
    let metrics = GatewayMetrics::new();
    metrics.record_http("models", 200, "none");
    metrics.set_dependency_ready("valkey", true);
    for (error, _) in admission_errors() {
        reject(&metrics, &error);
    }

    let generation = admitted(&metrics);
    generation.record_terminal(&terminal(10, Some(100), 200).record());
    for result in [
        FinalizationAttempt::Settled,
        FinalizationAttempt::AlreadyAbsent,
        FinalizationAttempt::Error,
    ] {
        generation.record_finalization_attempt(result);
    }
    generation.record_finalization_retry();
    generation.record_finalization_failure();
    generation.record_unsettled_generation();

    let with = |extra: &[&str]| -> BTreeSet<String> {
        GENERATION
            .iter()
            .chain(extra)
            .map(|key| key.to_string())
            .collect()
    };
    let generation_labels = with(&[]);
    let none = BTreeSet::new();
    let expected: BTreeMap<String, (String, BTreeSet<String>)> = [
        ("service_info", "gauge", none.clone()),
        (
            "http_requests_total",
            "counter",
            ["error", "route", "status"].map(str::to_owned).into(),
        ),
        ("admissions_total", "counter", generation_labels.clone()),
        ("admission_rejections_total", "counter", with(&["reason"])),
        ("active_generations", "gauge", generation_labels.clone()),
        (
            "generations_total",
            "counter",
            with(&["cancellation_owner", "error", "status"]),
        ),
        ("tokens_total", "counter", with(&["kind"])),
        (
            "calculated_charge_nano_usd_total",
            "counter",
            generation_labels.clone(),
        ),
        (
            "input_tokens_per_generation",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "output_tokens_per_generation",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "dispatch_latency_seconds",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "time_to_first_token_seconds",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "runtime_time_to_first_token_seconds",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "runtime_latency_seconds",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "generation_latency_seconds",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "time_per_output_token_seconds",
            "histogram",
            generation_labels.clone(),
        ),
        (
            "output_tokens_per_second",
            "histogram",
            generation_labels.clone(),
        ),
        ("finalization_attempts_total", "counter", with(&["result"])),
        (
            "finalization_retries_total",
            "counter",
            generation_labels.clone(),
        ),
        (
            "finalization_failures_total",
            "counter",
            generation_labels.clone(),
        ),
        (
            "unsettled_generations_total",
            "counter",
            generation_labels.clone(),
        ),
        (
            "dependency_ready",
            "gauge",
            ["dependency"].map(str::to_owned).into(),
        ),
        (
            "last_finalization_failure_timestamp_seconds",
            "gauge",
            none.clone(),
        ),
        (
            "last_settlement_backpressure_timestamp_seconds",
            "gauge",
            none,
        ),
    ]
    .into_iter()
    .map(|(name, kind, labels)| {
        (
            format!("gradiated_gateway_{name}"),
            (kind.to_owned(), labels),
        )
    })
    .collect();

    assert_eq!(expected.len(), 24);
    assert_eq!(encoded_families(&metrics.encode()), expected);
}

#[test]
fn active_generations_counts_admitted_metrics_until_they_drop() {
    let metrics = GatewayMetrics::new();
    let generation = admitted(&metrics);

    assert_eq!(metrics.sample("active_generations", ""), Some(1));

    drop(generation);

    assert_eq!(metrics.sample("active_generations", ""), Some(0));
}

#[test]
fn each_admission_rejection_is_labelled_with_its_reason() {
    for (error, reason) in admission_errors() {
        let metrics = GatewayMetrics::new();
        reject(&metrics, &error);

        let body = metrics.encode();
        let rejection = body
            .lines()
            .find(|line| line.starts_with("gradiated_gateway_admission_rejections_total{"))
            .unwrap();
        assert!(
            rejection.contains(&format!("reason=\"{reason}\"")),
            "{error:?} encoded as {rejection}"
        );
    }
}

#[test]
fn time_per_output_token_needs_more_than_one_output_token() {
    for output_tokens in [0, 1] {
        let metrics = GatewayMetrics::new();
        admitted(&metrics).record_terminal(&terminal(output_tokens, Some(100), 200).record());

        let body = metrics.encode();
        assert!(body.contains("gradiated_gateway_time_to_first_token_seconds_count"));
        assert!(!body.contains("gradiated_gateway_time_per_output_token_seconds_count"));
    }
}

#[test]
fn output_throughput_needs_elapsed_runtime() {
    let metrics = GatewayMetrics::new();
    admitted(&metrics).record_terminal(&terminal(10, None, 0).record());

    let body = metrics.encode();
    assert!(body.contains("gradiated_gateway_runtime_latency_seconds_count"));
    assert!(!body.contains("gradiated_gateway_output_tokens_per_second_count"));
}

#[test]
fn exposes_generation_dashboard_metrics_without_identity_labels() {
    let metrics = GatewayMetrics::new();
    metrics.record_http("models", 401, "invalid_api_key");
    metrics.set_dependency_ready("valkey", true);
    let generation =
        metrics.generation_admitted(&scope(Uuid::from_u128(0x0198c36f9b6a70008000000000000001)));
    generation.record_terminal(&terminal(10, Some(100), 190).record());
    generation.record_finalization_attempt(FinalizationAttempt::Settled);
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

#[test]
fn integrity_timestamps_stay_zero_until_their_first_event_without_a_scrape() {
    let metrics = GatewayMetrics::new();
    assert!(metrics
        .encode()
        .contains("gradiated_gateway_last_finalization_failure_timestamp_seconds 0"));
    let generation = admitted(&metrics);
    generation.record_finalization_failure();
    assert!(
        metrics
            .inner
            .last_finalization_failure_timestamp_seconds
            .get()
            > 0
    );
    reject(&metrics, &AdmissionError::SettlementBacklog);
    assert!(
        metrics
            .inner
            .last_settlement_backpressure_timestamp_seconds
            .get()
            > 0
    );
    let restarted = GatewayMetrics::new();
    assert_eq!(
        restarted
            .inner
            .last_finalization_failure_timestamp_seconds
            .get(),
        0
    );
}

#[test]
fn terminal_log_and_metrics_preserve_token_categories_without_payloads() {
    let logs = crate::diagnostics::capture::Logs::default();
    let _guard = logs.start();
    let metrics = GatewayMetrics::new();
    let generation = metrics.generation_admitted(&scope(Uuid::from_u128(2)));
    let terminal = Terminal {
        usage: NormalizedUsage::new(100, 20, 7, 10, 3).unwrap(),
        charge_nano_usd: 100,
        ..terminal(10, Some(100), 1_000)
    };
    generation.record_terminal(&terminal.record());
    let events = logs.events();
    let fields = &events[0]["fields"];
    assert_eq!(fields["event"], "generation_terminal");
    assert_eq!(fields["generation_id"], Uuid::from_u128(1).to_string());
    for (field, expected) in [
        ("input_tokens", 100),
        ("cached_input_tokens", 20),
        ("cache_write_tokens", 7),
        ("output_tokens", 10),
        ("reasoning_tokens", 3),
    ] {
        assert_eq!(fields[field], expected);
    }
    assert!(fields.get("prompt").is_none());
    assert!(fields.get("completion").is_none());
    let body = metrics.encode();
    for (kind, value) in [
        ("input", 100),
        ("cached_input", 20),
        ("cache_write", 7),
        ("output", 10),
        ("reasoning", 3),
    ] {
        assert!(body
            .lines()
            .any(|line| line.starts_with("gradiated_gateway_tokens_total{")
                && line.contains(&format!("kind=\"{kind}\""))
                && line.ends_with(&format!(" {value}"))));
    }
}

#[test]
fn terminal_labels_name_the_status_error_and_cancellation_owner() {
    let metrics = GatewayMetrics::new();
    let terminal = Terminal {
        outcome: TerminalOutcome::cancelled(
            CancellationOwner::Client,
            &GatewayError::RuntimeUnavailable,
            false,
        ),
        ..terminal(1, None, 10)
    };
    admitted(&metrics).record_terminal(&terminal.record());

    let body = metrics.encode();
    let outcome = body
        .lines()
        .find(|line| line.starts_with("gradiated_gateway_generations_total{"))
        .unwrap();
    assert!(outcome.contains("status=\"cancelled\""), "{outcome}");
    assert!(
        outcome.contains("error=\"runtime_unavailable\""),
        "{outcome}"
    );
    assert!(
        outcome.contains("cancellation_owner=\"client\""),
        "{outcome}"
    );
}

#[test]
fn served_by_moves_the_active_generation_to_the_serving_deployment() {
    let metrics = GatewayMetrics::new();
    let (primary, fallback) = (Uuid::from_u128(1), Uuid::from_u128(2));
    let active = |deployment: Uuid| {
        metrics.sample(
            "active_generations",
            &format!("deployment=\"{deployment}\""),
        )
    };
    let mut generation = metrics.generation_admitted(&scope(primary));

    generation.served_by(primary);
    assert_eq!((active(primary), active(fallback)), (Some(1), None));

    generation.served_by(fallback);
    assert_eq!((active(primary), active(fallback)), (Some(0), Some(1)));

    drop(generation);
    assert_eq!((active(primary), active(fallback)), (Some(0), Some(0)));
}

#[test]
fn runtime_work_has_a_zero_baseline_before_completion_including_fallbacks() {
    let metrics = GatewayMetrics::new();
    let baseline = |deployment: Uuid| {
        metrics.encode().lines().any(|line| {
            line.starts_with("gradiated_gateway_runtime_latency_seconds_sum{")
                && line.contains(&format!("deployment=\"{deployment}\""))
                && line.rsplit(' ').next().unwrap().parse::<f64>().unwrap() == 0.0
        })
    };
    let mut generation = admitted(&metrics);
    assert!(baseline(Uuid::from_u128(1)));
    generation.prepare_deployment(Uuid::from_u128(2));
    assert!(baseline(Uuid::from_u128(2)));
    generation.served_by(Uuid::from_u128(2));
    assert!(baseline(Uuid::from_u128(2)));
}
