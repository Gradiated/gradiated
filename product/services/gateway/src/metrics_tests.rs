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
    generation.record_terminal(&TerminalRecord {
        generation_id: Uuid::from_u128(1),
        status: "succeeded",
        error: "none",
        cancellation_owner: "none",
        usage: NormalizedUsage::new(100, 20, 0, 10, 0).unwrap(),
        charge_nano_usd: 12_000,
        received_at,
        started_at: received_at + chrono::TimeDelta::milliseconds(10),
        first_token_at: Some(received_at + chrono::TimeDelta::milliseconds(110)),
        completed_at: received_at + chrono::TimeDelta::milliseconds(200),
    });
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
#[test]
fn retains_first_integrity_event_without_a_prior_scrape() {
    let metrics = GatewayMetrics::new();
    assert!(metrics
        .encode()
        .contains("gradiated_gateway_last_finalization_failure_timestamp_seconds 0"));
    let generation = metrics.generation_admitted(
        "test",
        Uuid::from_u128(1),
        "openai",
        false,
        ServiceTier::Fast,
    );
    generation.record_finalization_failure();
    assert!(
        metrics
            .inner
            .last_finalization_failure_timestamp_seconds
            .get()
            > 0
    );
    metrics.record_admission_rejection(
        "test",
        Uuid::from_u128(1),
        "openai",
        false,
        ServiceTier::Fast,
        &AdmissionError::SettlementBacklog,
    );
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
    let generation = metrics.generation_admitted(
        "model-a",
        Uuid::from_u128(2),
        "openai",
        true,
        ServiceTier::Fast,
    );
    let start = Utc::now();
    generation.record_terminal(&TerminalRecord {
        generation_id: Uuid::from_u128(1),
        status: "succeeded",
        error: "none",
        cancellation_owner: "none",
        usage: NormalizedUsage::new(100, 20, 7, 10, 3).unwrap(),
        charge_nano_usd: 100,
        received_at: start,
        started_at: start,
        first_token_at: Some(start + chrono::TimeDelta::milliseconds(100)),
        completed_at: start + chrono::TimeDelta::seconds(1),
    });
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
