use foundry_core::serving_benchmark::{
    SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION, ServingEngineIdentity, ServingEvidenceKind,
    ServingHardwareTopology, ServingMeasurementProvenance, ServingModelIdentity,
    canonical_trace_content_id, evaluate_measured_serving_benchmark,
};
use foundry_core::vllm_serving::{
    VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION, VllmServingImportError, VllmServingImportManifest,
    import_vllm_serving_benchmark,
};
use foundry_core::workload::{SyntheticAgentFixture, privacy_safe_synthetic_agent_fixture};
use serde_json::{Value, json};

#[test]
fn imports_aligned_successful_vllm_measurements() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let artifact = artifact_bytes(&artifact(&fixture));
    let import_manifest = manifest(&fixture, &artifact);

    let request =
        import_vllm_serving_benchmark(&artifact, fixture.trace.clone(), import_manifest).unwrap();

    assert_eq!(
        request.schema_version,
        SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION
    );
    assert_eq!(request.observations.len(), fixture.trace.requests.len());
    assert_eq!(
        request.observations[0].start_timestamp_microseconds,
        fixture.trace.requests[0].arrival_timestamp_microseconds
    );
    assert_eq!(
        request.observations[0].first_token_timestamp_microseconds,
        Some(10_000)
    );
    assert_eq!(request.observations[0].end_timestamp_microseconds, 13_000);
    assert_eq!(
        request.observations[0].trace_content_id,
        canonical_trace_content_id(&fixture.trace).unwrap()
    );
    assert!(evaluate_measured_serving_benchmark(&request).is_ok());
    assert!(
        !serde_json::to_string(&request)
            .unwrap()
            .contains("redacted-output")
    );
}

#[test]
fn aligns_perf_counter_times_with_the_smallest_nonnegative_shared_offset() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    artifact["start_times"] = json!([100.0, 100.5, 101.5, 102.5, 103.5, 104.5]);
    let artifact = artifact_bytes(&artifact);
    let manifest = manifest(&fixture, &artifact);

    let request = import_vllm_serving_benchmark(&artifact, fixture.trace, manifest).unwrap();

    assert_eq!(
        request.observations[0].start_timestamp_microseconds,
        500_000
    );
    assert_eq!(
        request.observations[1].start_timestamp_microseconds,
        1_000_000
    );
    assert!(
        request
            .observations
            .iter()
            .all(|observation| observation.start_timestamp_microseconds
                >= observation.arrival_timestamp_microseconds)
    );
}

#[test]
fn rejects_misaligned_parallel_arrays() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    artifact["itls"].as_array_mut().unwrap().pop();
    let artifact = artifact_bytes(&artifact);
    let manifest = manifest(&fixture, &artifact);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, manifest),
        Err(VllmServingImportError::ArrayLengthMismatch {
            field: "itls",
            expected: 6,
            actual: 5
        })
    ));
}

#[test]
fn rejects_stock_failed_requests_without_end_timestamps() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    artifact["completed"] = json!(5);
    artifact["failed"] = json!(1);
    artifact["errors"][0] = json!("request failed");
    artifact["output_lens"][0] = json!(0);
    let artifact = artifact_bytes(&artifact);
    let import_manifest = manifest(&fixture, &artifact);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, import_manifest),
        Err(VllmServingImportError::FailedRequestsUnsupported { failed: 1 })
    ));
}

#[test]
fn rejects_token_count_drift() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    let expected = fixture.trace.requests[0].output_tokens;
    artifact["output_lens"][0] = json!(expected - 1);
    artifact["total_output_tokens"] = json!(artifact["total_output_tokens"].as_u64().unwrap() - 1);
    let artifact = artifact_bytes(&artifact);
    let manifest = manifest(&fixture, &artifact);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, manifest),
        Err(VllmServingImportError::TokenCountMismatch {
            request_id: 1,
            field: "output_tokens",
            expected: value,
            actual
        }) if value == expected && actual == expected - 1
    ));
}

#[test]
fn rejects_non_finite_or_negative_timing() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    artifact["ttfts"][0] = json!(-0.01);
    let artifact = artifact_bytes(&artifact);
    let import_manifest = manifest(&fixture, &artifact);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, import_manifest),
        Err(VllmServingImportError::InvalidTiming {
            request_id: 1,
            field: "ttfts"
        })
    ));

    let artifact = String::from_utf8(artifact)
        .unwrap()
        .replacen("-0.01", "NaN", 1);
    assert!(matches!(
        import_vllm_serving_benchmark(
            artifact.as_bytes(),
            privacy_safe_synthetic_agent_fixture().trace,
            manifest(&privacy_safe_synthetic_agent_fixture(), artifact.as_bytes())
        ),
        Err(VllmServingImportError::InvalidJson(_))
    ));
}

#[test]
fn rejects_request_timeline_beyond_benchmark_duration() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    artifact["duration"] = json!(0.001);
    let artifact = artifact_bytes(&artifact);
    let manifest = manifest(&fixture, &artifact);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, manifest),
        Err(VllmServingImportError::InvalidTiming {
            request_id: 1,
            field: "duration"
        })
    ));
}

#[test]
fn rejects_artifact_and_manifest_identity_drift() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let mut artifact = artifact(&fixture);
    artifact["model_id"] = json!("different/model");
    let artifact = artifact_bytes(&artifact);
    let manifest = manifest(&fixture, &artifact);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, manifest),
        Err(VllmServingImportError::ArtifactIdentityMismatch { field: "model_id" })
    ));
}

#[test]
fn rejects_unpinned_positional_request_order() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let artifact = artifact_bytes(&artifact(&fixture));
    let mut manifest = manifest(&fixture, &artifact);
    manifest.ordered_request_ids.swap(0, 1);

    assert!(matches!(
        import_vllm_serving_benchmark(&artifact, fixture.trace, manifest),
        Err(VllmServingImportError::RequestOrderMismatch {
            index: 0,
            expected: 1,
            actual: 2
        })
    ));
}

#[test]
fn rejects_raw_artifact_content_drift() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let artifact = artifact_bytes(&artifact(&fixture));
    let manifest = manifest(&fixture, &artifact);
    let mut changed = artifact;
    changed.push(b'\n');

    assert!(matches!(
        import_vllm_serving_benchmark(&changed, fixture.trace, manifest),
        Err(VllmServingImportError::SourceArtifactMismatch { .. })
    ));
}

#[test]
fn manifest_rejects_unknown_fields() {
    let fixture = privacy_safe_synthetic_agent_fixture();
    let artifact = artifact_bytes(&artifact(&fixture));
    let manifest = manifest(&fixture, &artifact);
    let mut value = serde_json::to_value(manifest).unwrap();
    value["unexpected"] = json!(true);

    assert!(serde_json::from_value::<VllmServingImportManifest>(value).is_err());
}

fn artifact(fixture: &SyntheticAgentFixture) -> Value {
    let input_lens = fixture
        .trace
        .requests
        .iter()
        .map(|request| request.input_tokens)
        .collect::<Vec<_>>();
    let output_lens = fixture
        .trace
        .requests
        .iter()
        .map(|request| request.output_tokens)
        .collect::<Vec<_>>();
    let start_times = fixture
        .trace
        .requests
        .iter()
        .map(|request| 100.0 + request.arrival_timestamp_microseconds as f64 / 1_000_000.0)
        .collect::<Vec<_>>();
    json!({
        "date": "20260712-120000",
        "backend": "openai-chat",
        "model_id": fixture.trace.identity.model_id,
        "tokenizer_id": fixture.trace.identity.tokenizer_id,
        "num_prompts": fixture.trace.requests.len(),
        "duration": 6.0,
        "completed": fixture.trace.requests.len(),
        "failed": 0,
        "total_input_tokens": input_lens.iter().map(|value| u64::from(*value)).sum::<u64>(),
        "total_output_tokens": output_lens.iter().map(|value| u64::from(*value)).sum::<u64>(),
        "input_lens": input_lens,
        "output_lens": output_lens,
        "ttfts": vec![0.01; fixture.trace.requests.len()],
        "itls": vec![vec![0.001, 0.002]; fixture.trace.requests.len()],
        "start_times": start_times,
        "generated_texts": vec!["redacted-output"; fixture.trace.requests.len()],
        "errors": vec![""; fixture.trace.requests.len()],
        "request_throughput": 1.0,
        "p99_ttft_ms": 10.0
    })
}

fn artifact_bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).unwrap()
}

fn manifest(fixture: &SyntheticAgentFixture, artifact: &[u8]) -> VllmServingImportManifest {
    VllmServingImportManifest {
        schema_version: VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION,
        benchmark_id: "vllm-agent-run".into(),
        ordered_request_ids: fixture
            .trace
            .requests
            .iter()
            .map(|request| request.request_id)
            .collect(),
        workload_contract: fixture.contract.clone(),
        model: ServingModelIdentity {
            model_id: fixture.trace.identity.model_id.clone(),
            model_revision: fixture.trace.identity.model_revision.clone(),
            checkpoint_id: "checkpoint-id".into(),
            checkpoint_revision: "checkpoint-revision".into(),
            tokenizer_id: fixture.trace.identity.tokenizer_id.clone(),
            tokenizer_revision: fixture.trace.identity.tokenizer_revision.clone(),
        },
        provenance: ServingMeasurementProvenance {
            evidence_kind: ServingEvidenceKind::MeasuredHardware,
            run_id: "vllm-run".into(),
            source_artifact_id: blake3::hash(artifact).to_hex().to_string(),
            engine: ServingEngineIdentity {
                name: "vllm".into(),
                version: "0.1.dev1".into(),
                build_id: "bec0a4ede621bc9f".into(),
            },
            hardware: ServingHardwareTopology {
                device_model: "H100 SXM".into(),
                device_count: 1,
                topology: "single_device".into(),
                interconnect: "none".into(),
                device_set_hash: "device-set-hash".into(),
            },
            measurement_tool: "foundry-vllm-adapter".into(),
            software_revision: "adapter-revision".into(),
            captured_at_unix_milliseconds: 1_750_000_000_000,
        },
    }
}
