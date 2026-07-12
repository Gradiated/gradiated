use crate::serving_benchmark::{
    MeasuredServingBenchmarkRequest, MeasuredServingRequestObservation,
    SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION, ServingBenchmarkError, ServingMeasurementProvenance,
    ServingModelIdentity, canonical_trace_content_id, evaluate_measured_serving_benchmark,
};
use crate::workload::{CanonicalTraceV2, WorkloadContractV2};
use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct VllmServingImportManifest {
    pub schema_version: u32,
    pub benchmark_id: String,
    pub ordered_request_ids: Vec<u64>,
    pub workload_contract: WorkloadContractV2,
    pub model: ServingModelIdentity,
    pub provenance: ServingMeasurementProvenance,
}

#[derive(Debug, Deserialize)]
struct VllmDetailedServingArtifact {
    date: String,
    backend: String,
    model_id: String,
    tokenizer_id: String,
    num_prompts: usize,
    duration: f64,
    completed: usize,
    failed: usize,
    total_input_tokens: u64,
    total_output_tokens: u64,
    input_lens: Vec<u32>,
    output_lens: Vec<u32>,
    ttfts: Vec<f64>,
    itls: Vec<Vec<f64>>,
    start_times: Vec<f64>,
    generated_texts: Vec<String>,
    errors: Vec<String>,
}

pub fn vllm_source_artifact_id(artifact_json: &[u8]) -> String {
    blake3::hash(artifact_json).to_hex().to_string()
}

pub fn import_vllm_serving_benchmark(
    artifact_json: &[u8],
    trace: CanonicalTraceV2,
    manifest: VllmServingImportManifest,
) -> Result<MeasuredServingBenchmarkRequest, VllmServingImportError> {
    let artifact = serde_json::from_slice::<VllmDetailedServingArtifact>(artifact_json)
        .map_err(|error| VllmServingImportError::InvalidJson(error.to_string()))?;
    validate_manifest(&manifest, artifact_json)?;
    validate_artifact(&artifact, &trace, &manifest)?;

    let trace_content_id = canonical_trace_content_id(&trace)?;
    let normalized_starts = normalized_start_microseconds(&artifact, &trace)?;
    let offset = trace
        .requests
        .iter()
        .zip(&normalized_starts)
        .map(|(request, start)| {
            request
                .arrival_timestamp_microseconds
                .saturating_sub(*start)
        })
        .max()
        .unwrap_or(0);
    let mut observations = Vec::with_capacity(trace.requests.len());

    for (index, request) in trace.requests.iter().enumerate() {
        let start_timestamp_microseconds = normalized_starts[index].checked_add(offset).ok_or(
            VllmServingImportError::TimestampOverflow {
                request_id: request.request_id,
            },
        )?;
        let ttft =
            positive_seconds_to_microseconds(artifact.ttfts[index], request.request_id, "ttfts")?;
        let first_token_timestamp_microseconds = start_timestamp_microseconds
            .checked_add(ttft)
            .ok_or(VllmServingImportError::TimestampOverflow {
                request_id: request.request_id,
            })?;
        let itl_seconds = sum_itls(&artifact.itls[index], request.request_id)?;
        if request.output_tokens > 1 && itl_seconds == 0.0 {
            return Err(VllmServingImportError::InvalidTiming {
                request_id: request.request_id,
                field: "itls",
            });
        }
        let itl = seconds_to_microseconds(itl_seconds, request.request_id, "itls")?;
        let end_timestamp_microseconds = first_token_timestamp_microseconds
            .checked_add(itl)
            .ok_or(VllmServingImportError::TimestampOverflow {
                request_id: request.request_id,
            })?;

        observations.push(MeasuredServingRequestObservation {
            request_id: request.request_id,
            model: manifest.model.clone(),
            provenance: manifest.provenance.clone(),
            trace_id: trace.trace_id.clone(),
            trace_content_id: trace_content_id.clone(),
            class: request.class,
            input_tokens: request.input_tokens,
            output_tokens: request.output_tokens,
            prefix_reused_tokens: request.prefix_reused_tokens,
            arrival_timestamp_microseconds: request.arrival_timestamp_microseconds,
            start_timestamp_microseconds,
            first_token_timestamp_microseconds: Some(first_token_timestamp_microseconds),
            end_timestamp_microseconds,
            success: true,
        });
    }

    let request = MeasuredServingBenchmarkRequest {
        schema_version: SERVING_BENCHMARK_REQUEST_SCHEMA_VERSION,
        benchmark_id: manifest.benchmark_id,
        workload_contract: manifest.workload_contract,
        trace,
        observations,
    };
    evaluate_measured_serving_benchmark(&request)?;
    Ok(request)
}

fn validate_manifest(
    manifest: &VllmServingImportManifest,
    artifact_json: &[u8],
) -> Result<(), VllmServingImportError> {
    if manifest.schema_version != VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION {
        return Err(VllmServingImportError::UnsupportedManifestSchemaVersion {
            expected: VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION,
            actual: manifest.schema_version,
        });
    }
    if manifest.benchmark_id.trim().is_empty() {
        return Err(VllmServingImportError::InvalidField("benchmark_id"));
    }
    if manifest.provenance.engine.name != "vllm" {
        return Err(VllmServingImportError::InvalidField(
            "provenance.engine.name",
        ));
    }
    let actual = vllm_source_artifact_id(artifact_json);
    if manifest.provenance.source_artifact_id != actual {
        return Err(VllmServingImportError::SourceArtifactMismatch {
            expected: manifest.provenance.source_artifact_id.clone(),
            actual,
        });
    }
    Ok(())
}

fn validate_artifact(
    artifact: &VllmDetailedServingArtifact,
    trace: &CanonicalTraceV2,
    manifest: &VllmServingImportManifest,
) -> Result<(), VllmServingImportError> {
    for (field, value) in [
        ("date", artifact.date.as_str()),
        ("backend", artifact.backend.as_str()),
        ("model_id", artifact.model_id.as_str()),
        ("tokenizer_id", artifact.tokenizer_id.as_str()),
    ] {
        if value.trim().is_empty() {
            return Err(VllmServingImportError::InvalidField(field));
        }
    }
    if !artifact.duration.is_finite() || artifact.duration <= 0.0 {
        return Err(VllmServingImportError::InvalidField("duration"));
    }
    if artifact.model_id != manifest.model.model_id {
        return Err(VllmServingImportError::ArtifactIdentityMismatch { field: "model_id" });
    }
    if artifact.tokenizer_id != manifest.model.tokenizer_id {
        return Err(VllmServingImportError::ArtifactIdentityMismatch {
            field: "tokenizer_id",
        });
    }

    let request_count = artifact.input_lens.len();
    validate_len("output_lens", request_count, artifact.output_lens.len())?;
    validate_len("ttfts", request_count, artifact.ttfts.len())?;
    validate_len("itls", request_count, artifact.itls.len())?;
    validate_len("start_times", request_count, artifact.start_times.len())?;
    validate_len(
        "generated_texts",
        request_count,
        artifact.generated_texts.len(),
    )?;
    validate_len("errors", request_count, artifact.errors.len())?;
    validate_len("trace.requests", request_count, trace.requests.len())?;
    validate_len(
        "manifest.ordered_request_ids",
        request_count,
        manifest.ordered_request_ids.len(),
    )?;

    if artifact.num_prompts != request_count {
        return Err(VllmServingImportError::CountMismatch {
            field: "num_prompts",
            expected: request_count,
            actual: artifact.num_prompts,
        });
    }
    let accounted = artifact.completed.checked_add(artifact.failed).ok_or(
        VllmServingImportError::CountOverflow {
            field: "completed + failed",
        },
    )?;
    if accounted != request_count {
        return Err(VllmServingImportError::CountMismatch {
            field: "completed + failed",
            expected: request_count,
            actual: accounted,
        });
    }
    let observed_failures = artifact
        .errors
        .iter()
        .filter(|error| !error.is_empty())
        .count();
    if observed_failures != artifact.failed {
        return Err(VllmServingImportError::CountMismatch {
            field: "errors",
            expected: artifact.failed,
            actual: observed_failures,
        });
    }
    if artifact.failed != 0 {
        return Err(VllmServingImportError::FailedRequestsUnsupported {
            failed: artifact.failed,
        });
    }

    let input_tokens = artifact
        .input_lens
        .iter()
        .try_fold(0_u64, |total, value| total.checked_add(u64::from(*value)))
        .ok_or(VllmServingImportError::CountOverflow {
            field: "total_input_tokens",
        })?;
    validate_token_total(
        "total_input_tokens",
        input_tokens,
        artifact.total_input_tokens,
    )?;
    let output_tokens = artifact
        .output_lens
        .iter()
        .try_fold(0_u64, |total, value| total.checked_add(u64::from(*value)))
        .ok_or(VllmServingImportError::CountOverflow {
            field: "total_output_tokens",
        })?;
    validate_token_total(
        "total_output_tokens",
        output_tokens,
        artifact.total_output_tokens,
    )?;

    for (index, request) in trace.requests.iter().enumerate() {
        let actual_request_id = manifest.ordered_request_ids[index];
        if actual_request_id != request.request_id {
            return Err(VllmServingImportError::RequestOrderMismatch {
                index,
                expected: request.request_id,
                actual: actual_request_id,
            });
        }
        validate_token_count(
            request.request_id,
            "input_tokens",
            request.input_tokens,
            artifact.input_lens[index],
        )?;
        validate_token_count(
            request.request_id,
            "output_tokens",
            request.output_tokens,
            artifact.output_lens[index],
        )?;
        validate_seconds(
            artifact.start_times[index],
            request.request_id,
            "start_times",
        )?;
        validate_seconds(artifact.ttfts[index], request.request_id, "ttfts")?;
        for itl in &artifact.itls[index] {
            validate_seconds(*itl, request.request_id, "itls")?;
        }
    }
    validate_timeline_duration(artifact, trace)?;
    Ok(())
}

fn validate_timeline_duration(
    artifact: &VllmDetailedServingArtifact,
    trace: &CanonicalTraceV2,
) -> Result<(), VllmServingImportError> {
    let minimum = artifact
        .start_times
        .iter()
        .copied()
        .min_by(f64::total_cmp)
        .ok_or(VllmServingImportError::InvalidField("start_times"))?;
    for (index, request) in trace.requests.iter().enumerate() {
        let relative_end = artifact.start_times[index] - minimum
            + artifact.ttfts[index]
            + sum_itls(&artifact.itls[index], request.request_id)?;
        if !relative_end.is_finite() || relative_end > artifact.duration {
            return Err(VllmServingImportError::InvalidTiming {
                request_id: request.request_id,
                field: "duration",
            });
        }
    }
    Ok(())
}

fn normalized_start_microseconds(
    artifact: &VllmDetailedServingArtifact,
    trace: &CanonicalTraceV2,
) -> Result<Vec<u64>, VllmServingImportError> {
    let minimum = artifact
        .start_times
        .iter()
        .copied()
        .min_by(f64::total_cmp)
        .ok_or(VllmServingImportError::InvalidField("start_times"))?;
    artifact
        .start_times
        .iter()
        .zip(&trace.requests)
        .map(|(start, request)| {
            seconds_to_microseconds(*start - minimum, request.request_id, "start_times")
        })
        .collect()
}

fn sum_itls(values: &[f64], request_id: u64) -> Result<f64, VllmServingImportError> {
    values.iter().try_fold(0.0, |total, value| {
        let next = total + value;
        if next.is_finite() {
            Ok(next)
        } else {
            Err(VllmServingImportError::InvalidTiming {
                request_id,
                field: "itls",
            })
        }
    })
}

fn positive_seconds_to_microseconds(
    seconds: f64,
    request_id: u64,
    field: &'static str,
) -> Result<u64, VllmServingImportError> {
    if seconds <= 0.0 {
        return Err(VllmServingImportError::InvalidTiming { request_id, field });
    }
    seconds_to_microseconds(seconds, request_id, field)
}

fn seconds_to_microseconds(
    seconds: f64,
    request_id: u64,
    field: &'static str,
) -> Result<u64, VllmServingImportError> {
    validate_seconds(seconds, request_id, field)?;
    let microseconds = seconds * 1_000_000.0;
    if !microseconds.is_finite() || microseconds > u64::MAX as f64 {
        return Err(VllmServingImportError::TimestampOverflow { request_id });
    }
    Ok(microseconds.round() as u64)
}

fn validate_seconds(
    seconds: f64,
    request_id: u64,
    field: &'static str,
) -> Result<(), VllmServingImportError> {
    if !seconds.is_finite() || seconds < 0.0 {
        Err(VllmServingImportError::InvalidTiming { request_id, field })
    } else {
        Ok(())
    }
}

fn validate_len(
    field: &'static str,
    expected: usize,
    actual: usize,
) -> Result<(), VllmServingImportError> {
    if expected == actual {
        Ok(())
    } else {
        Err(VllmServingImportError::ArrayLengthMismatch {
            field,
            expected,
            actual,
        })
    }
}

fn validate_token_total(
    field: &'static str,
    expected: u64,
    actual: u64,
) -> Result<(), VllmServingImportError> {
    if expected == actual {
        Ok(())
    } else {
        Err(VllmServingImportError::TokenTotalMismatch {
            field,
            expected,
            actual,
        })
    }
}

fn validate_token_count(
    request_id: u64,
    field: &'static str,
    expected: u32,
    actual: u32,
) -> Result<(), VllmServingImportError> {
    if expected == actual {
        Ok(())
    } else {
        Err(VllmServingImportError::TokenCountMismatch {
            request_id,
            field,
            expected,
            actual,
        })
    }
}

#[derive(Debug, Error)]
pub enum VllmServingImportError {
    #[error("vLLM serving artifact is invalid JSON: {0}")]
    InvalidJson(String),
    #[error("unsupported vLLM import manifest schema version {actual}; expected {expected}")]
    UnsupportedManifestSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid vLLM import field {0}")]
    InvalidField(&'static str),
    #[error("vLLM source artifact content ID differs: expected {expected}, got {actual}")]
    SourceArtifactMismatch { expected: String, actual: String },
    #[error("vLLM artifact identity differs for {field}")]
    ArtifactIdentityMismatch { field: &'static str },
    #[error("vLLM array {field} has length {actual}; expected {expected}")]
    ArrayLengthMismatch {
        field: &'static str,
        expected: usize,
        actual: usize,
    },
    #[error("vLLM count {field} is {actual}; expected {expected}")]
    CountMismatch {
        field: &'static str,
        expected: usize,
        actual: usize,
    },
    #[error("vLLM count {field} overflowed")]
    CountOverflow { field: &'static str },
    #[error("stock vLLM artifacts cannot preserve end timestamps for {failed} failed requests")]
    FailedRequestsUnsupported { failed: usize },
    #[error("vLLM token total {field} is {actual}; expected {expected}")]
    TokenTotalMismatch {
        field: &'static str,
        expected: u64,
        actual: u64,
    },
    #[error("vLLM positional request {index} is {actual}; expected {expected}")]
    RequestOrderMismatch {
        index: usize,
        expected: u64,
        actual: u64,
    },
    #[error("request {request_id} vLLM {field} is {actual}; expected {expected}")]
    TokenCountMismatch {
        request_id: u64,
        field: &'static str,
        expected: u32,
        actual: u32,
    },
    #[error("request {request_id} has invalid vLLM timing field {field}")]
    InvalidTiming {
        request_id: u64,
        field: &'static str,
    },
    #[error("request {request_id} timestamp cannot be represented in microseconds")]
    TimestampOverflow { request_id: u64 },
    #[error("imported serving benchmark is invalid: {0}")]
    ServingBenchmark(#[from] ServingBenchmarkError),
}
