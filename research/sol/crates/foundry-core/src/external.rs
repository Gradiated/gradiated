#[cfg(test)]
mod tests {
    use std::path::PathBuf;
    use std::sync::Arc;

    use crate::performance::{
        Bottleneck, OracleFidelity, PerformanceOracle, PhaseResult, PhaseWork,
    };
    use crate::spec::{
        AggregateHardwareSpec, HardwareFidelity, HardwareSpec, ModelArchitecture, ModelSpec,
        Precision,
    };

    use super::*;

    #[derive(Clone, Copy)]
    enum FakeBehavior {
        Success,
        NonZero,
        Timeout,
        WrongHash,
        WrongSchema,
        InvalidMeasurement,
    }

    struct FakeRunner {
        behavior: FakeBehavior,
    }

    impl ProcessRunner for FakeRunner {
        fn execute(&self, invocation: &ProcessInvocation) -> ProcessCapture {
            let request: ExternalSimulationRequest =
                serde_json::from_slice(&invocation.stdin).unwrap();
            match self.behavior {
                FakeBehavior::Success
                | FakeBehavior::WrongHash
                | FakeBehavior::WrongSchema
                | FakeBehavior::InvalidMeasurement => {
                    let mut result = measured_result(&request.input.work);
                    if matches!(self.behavior, FakeBehavior::InvalidMeasurement) {
                        result.latency_seconds = -1.0;
                    }
                    let response = ExternalSimulationResponse {
                        schema_version: if matches!(self.behavior, FakeBehavior::WrongSchema) {
                            EXTERNAL_SCHEMA_VERSION + 1
                        } else {
                            EXTERNAL_SCHEMA_VERSION
                        },
                        tool: request.tool.clone(),
                        input_hash: if matches!(self.behavior, FakeBehavior::WrongHash) {
                            "wrong".into()
                        } else {
                            request.input_hash.clone()
                        },
                        result,
                    };
                    ProcessCapture::completed(
                        0,
                        serde_json::to_vec(&response).unwrap(),
                        b"mock diagnostic".to_vec(),
                    )
                }
                FakeBehavior::NonZero => {
                    ProcessCapture::completed(7, b"not-json".to_vec(), b"tool failed".to_vec())
                }
                FakeBehavior::Timeout => ProcessCapture::failed(
                    ExternalRunStatus::TimedOut,
                    b"partial".to_vec(),
                    b"deadline".to_vec(),
                    "tool exceeded its timeout",
                ),
            }
        }
    }

    fn tool() -> ExternalToolSpec {
        ExternalToolSpec {
            identity: ExternalToolIdentity {
                name: "mock-accelerator-sim".into(),
                version: "1.2.3".into(),
            },
            executable: PathBuf::from("/never/executed/in/unit/tests"),
            arguments: vec!["--json".into()],
            timeout_milliseconds: 1_000,
            max_output_bytes: 1_048_576,
        }
    }

    fn model() -> ModelSpec {
        ModelSpec {
            model_id: "external-test".into(),
            model_revision: "test-fixture-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 1_000_000,
            layer_count: 4,
            hidden_size: 256,
            intermediate_size: 1_024,
            attention_head_count: 8,
            kv_head_count: 2,
            head_dimension: 32,
            vocabulary_size: 32_000,
            max_sequence_length: 4_096,
            weight_precision: Precision::Bf16,
            quantized_weight_storage: None,
            kv_precision: Precision::Fp16,
        }
    }

    fn hardware() -> HardwareSpec {
        HardwareSpec {
            name: "external-target".into(),
            fidelity: HardwareFidelity::Measured,
            physical_device_count: 1,
            aggregate: Some(AggregateHardwareSpec {
                memory_capacity_bytes: 8_000_000_000,
                memory_bandwidth_bytes_per_second: 1.0e12,
                compute_operations_per_second: 1.0e14,
                compute_efficiency: 0.8,
                memory_efficiency: 0.7,
                scale_up_bandwidth_bytes_per_second: 0.0,
                scale_up_latency_nanoseconds: 0.0,
                scale_up_energy_picojoules_per_byte: 0.0,
                idle_power_watts: 50.0,
                peak_power_watts: 400.0,
            }),
            design: None,
            accelerator_hourly_cost_usd: 2.0,
            host_hourly_cost_usd: 0.2,
        }
    }

    fn measured_result(work: &PhaseWork) -> PhaseResult {
        PhaseResult {
            phase: work.phase,
            fidelity: OracleFidelity::External,
            batch_size: work.batch_size,
            new_tokens: work.new_tokens,
            flops: 1.0e9,
            executed_flops: 1.0e9,
            tile_utilization: 1.0,
            weight_bytes: 2_000_000,
            activation_bytes: 0,
            kv_read_bytes: 10_000,
            kv_write_bytes: 1_000,
            interchip_bytes: work.interchip_bytes,
            effective_compute_operations_per_second: 1.0e14,
            effective_memory_bandwidth_bytes_per_second: 1.0e12,
            compute_seconds: 0.001,
            memory_seconds: 0.002,
            launch_seconds: 0.0001,
            latency_seconds: 0.0021,
            energy_joules: 0.5,
            bottleneck: Bottleneck::Hbm,
            actions: vec![],
        }
    }

    fn adapter(behavior: FakeBehavior) -> ExternalProcessAdapter {
        ExternalProcessAdapter::with_runner(tool(), Arc::new(FakeRunner { behavior })).unwrap()
    }

    #[test]
    fn request_hash_is_deterministic_and_content_addressed() {
        let first = ExternalSimulationRequest::new(
            tool().identity,
            &model(),
            &hardware(),
            &PhaseWork::decode(4, 2_048),
        )
        .unwrap();
        let same = ExternalSimulationRequest::new(
            tool().identity,
            &model(),
            &hardware(),
            &PhaseWork::decode(4, 2_048),
        )
        .unwrap();
        let changed = ExternalSimulationRequest::new(
            tool().identity,
            &model(),
            &hardware(),
            &PhaseWork::decode(8, 4_096),
        )
        .unwrap();

        assert_eq!(first.input_hash, same.input_hash);
        assert_ne!(first.input_hash, changed.input_hash);
    }

    #[test]
    fn successful_process_output_becomes_a_replayable_record() {
        let work = PhaseWork::decode(4, 2_048);
        let record = adapter(FakeBehavior::Success)
            .run(&model(), &hardware(), &work)
            .unwrap();

        assert_eq!(record.status, ExternalRunStatus::Succeeded);
        assert_eq!(record.stderr, "mock diagnostic");
        assert_eq!(record.result().unwrap().latency_seconds, 0.0021);

        let encoded = serde_json::to_vec(&record).unwrap();
        let decoded: ExternalRunRecord = serde_json::from_slice(&encoded).unwrap();
        let oracle = ExternalPerformanceOracle::from_records(tool().identity, [decoded]).unwrap();
        let replayed = oracle.estimate(&model(), &hardware(), &work).unwrap();

        assert_eq!(replayed, measured_result(&work));
        assert_eq!(replayed.fidelity, OracleFidelity::External);
    }

    #[test]
    fn nonzero_exit_and_timeout_capture_stderr_and_failure() {
        let work = PhaseWork::decode(1, 128);
        let failed = adapter(FakeBehavior::NonZero)
            .run(&model(), &hardware(), &work)
            .unwrap();
        let timed_out = adapter(FakeBehavior::Timeout)
            .run(&model(), &hardware(), &work)
            .unwrap();

        assert_eq!(failed.status, ExternalRunStatus::NonZeroExit);
        assert_eq!(failed.exit_code, Some(7));
        assert_eq!(failed.stderr, "tool failed");
        assert!(failed.error.as_deref().unwrap().contains("status 7"));
        assert_eq!(timed_out.status, ExternalRunStatus::TimedOut);
        assert_eq!(timed_out.stderr, "deadline");
        assert!(timed_out.error.is_some());
    }

    #[test]
    fn response_hash_mismatch_is_rejected_and_recorded() {
        let record = adapter(FakeBehavior::WrongHash)
            .run(&model(), &hardware(), &PhaseWork::decode(1, 128))
            .unwrap();

        assert_eq!(record.status, ExternalRunStatus::HashMismatch);
        assert!(record.response.is_some());
        assert!(record.result().is_err());
    }

    #[test]
    fn stdout_schema_and_measurement_values_are_validated() {
        let work = PhaseWork::decode(1, 128);
        let wrong_schema = adapter(FakeBehavior::WrongSchema)
            .run(&model(), &hardware(), &work)
            .unwrap();
        let invalid_measurement = adapter(FakeBehavior::InvalidMeasurement)
            .run(&model(), &hardware(), &work)
            .unwrap();

        assert_eq!(wrong_schema.status, ExternalRunStatus::SchemaMismatch);
        assert_eq!(
            invalid_measurement.status,
            ExternalRunStatus::InvalidMeasurement
        );
    }

    #[test]
    fn replay_requires_the_exact_recorded_input() {
        let recorded_work = PhaseWork::decode(4, 2_048);
        let record = adapter(FakeBehavior::Success)
            .run(&model(), &hardware(), &recorded_work)
            .unwrap();
        let oracle = ExternalPerformanceOracle::from_records(tool().identity, [record]).unwrap();

        let error = oracle
            .estimate(&model(), &hardware(), &PhaseWork::decode(8, 4_096))
            .unwrap_err();

        assert_eq!(
            error,
            crate::performance::PerformanceError::MissingResource {
                resource: "recorded external measurement"
            }
        );
    }

    #[test]
    fn conflicting_measurements_for_one_hash_are_rejected() {
        let work = PhaseWork::decode(4, 2_048);
        let first = adapter(FakeBehavior::Success)
            .run(&model(), &hardware(), &work)
            .unwrap();
        let mut conflicting = first.clone();
        conflicting.response.as_mut().unwrap().result.energy_joules = 0.75;

        let error = ExternalPerformanceOracle::from_records(tool().identity, [first, conflicting])
            .unwrap_err();

        assert_eq!(error, ExternalOracleError::ConflictingMeasurement);
    }

    #[test]
    fn spawn_failure_is_returned_as_a_record() {
        let mut spec = tool();
        spec.executable = PathBuf::from("/definitely/not/an/external/simulator");
        let record = ExternalProcessAdapter::new(spec)
            .unwrap()
            .run(&model(), &hardware(), &PhaseWork::decode(1, 128))
            .unwrap();

        assert_eq!(record.status, ExternalRunStatus::SpawnFailed);
        assert!(record.error.is_some());
    }

    #[cfg(unix)]
    #[test]
    fn system_runner_enforces_timeout() {
        let mut spec = tool();
        spec.executable = PathBuf::from("/bin/sleep");
        spec.arguments = vec!["1".into()];
        spec.timeout_milliseconds = 20;
        let started = std::time::Instant::now();

        let record = ExternalProcessAdapter::new(spec)
            .unwrap()
            .run(&model(), &hardware(), &PhaseWork::decode(1, 128))
            .unwrap();

        assert_eq!(record.status, ExternalRunStatus::TimedOut);
        assert_eq!(record.tool_spec.timeout_milliseconds, 20);
        assert!(started.elapsed() < std::time::Duration::from_millis(500));
    }

    #[cfg(unix)]
    #[test]
    fn process_arguments_are_passed_literally_without_a_shell() {
        let executable = ["/usr/bin/printf", "/bin/printf"]
            .into_iter()
            .map(PathBuf::from)
            .find(|path| path.exists());
        let Some(executable) = executable else {
            return;
        };
        let marker =
            std::env::temp_dir().join(format!("foundry-external-no-shell-{}", std::process::id()));
        assert!(!marker.exists());
        let literal = format!("$(touch {})", marker.display());
        let mut spec = tool();
        spec.executable = executable;
        spec.arguments = vec!["%s".into(), literal.clone()];

        let record = ExternalProcessAdapter::new(spec)
            .unwrap()
            .run(&model(), &hardware(), &PhaseWork::decode(1, 128))
            .unwrap();

        assert_eq!(record.status, ExternalRunStatus::InvalidJson);
        assert_eq!(record.stdout, literal);
        assert!(!marker.exists());
    }

    #[cfg(unix)]
    #[test]
    fn system_runner_bounds_captured_output() {
        let executable = ["/usr/bin/printf", "/bin/printf"]
            .into_iter()
            .map(PathBuf::from)
            .find(|path| path.exists());
        let Some(executable) = executable else {
            return;
        };
        let mut spec = tool();
        spec.executable = executable;
        spec.arguments = vec!["%s".into(), "x".repeat(1_024)];
        spec.max_output_bytes = 32;

        let record = ExternalProcessAdapter::new(spec)
            .unwrap()
            .run(&model(), &hardware(), &PhaseWork::decode(1, 128))
            .unwrap();

        assert_eq!(record.status, ExternalRunStatus::OutputLimitExceeded);
        assert_eq!(record.stdout.len(), 32);
    }
}
use std::collections::BTreeMap;
use std::fmt;
use std::io::{ErrorKind, Read, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::performance::{
    OracleFidelity, PerformanceError, PerformanceOracle, PhaseResult, PhaseWork,
};
use crate::spec::{HardwareSpec, ModelSpec};

pub const EXTERNAL_SCHEMA_VERSION: u32 = 1;
const MAX_CAPTURE_BYTES: usize = 64 * 1024 * 1024;
const MAX_REQUEST_BYTES: usize = 64 * 1024 * 1024;
const MAX_TIMEOUT_MILLISECONDS: u64 = 86_400_000;

#[derive(Clone, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
pub struct ExternalToolIdentity {
    pub name: String,
    pub version: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalToolSpec {
    pub identity: ExternalToolIdentity,
    pub executable: PathBuf,
    pub arguments: Vec<String>,
    pub timeout_milliseconds: u64,
    pub max_output_bytes: usize,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalPerformanceInput {
    pub model: ModelSpec,
    pub hardware: HardwareSpec,
    pub work: PhaseWork,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalSimulationRequest {
    pub schema_version: u32,
    pub tool: ExternalToolIdentity,
    pub input_hash: String,
    pub input: ExternalPerformanceInput,
}

#[derive(Serialize)]
struct HashableRequest<'a> {
    schema_version: u32,
    tool: &'a ExternalToolIdentity,
    input: &'a ExternalPerformanceInput,
}

impl ExternalSimulationRequest {
    pub fn new(
        tool: ExternalToolIdentity,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<Self, ExternalAdapterError> {
        validate_identity(&tool)?;
        let input = ExternalPerformanceInput {
            model: model.clone(),
            hardware: hardware.clone(),
            work: *work,
        };
        let input_hash = request_hash(&tool, &input)?;
        Ok(Self {
            schema_version: EXTERNAL_SCHEMA_VERSION,
            tool,
            input_hash,
            input,
        })
    }

    pub fn verify_hash(&self) -> Result<bool, ExternalAdapterError> {
        Ok(self.schema_version == EXTERNAL_SCHEMA_VERSION
            && self.input_hash == request_hash(&self.tool, &self.input)?)
    }
}

fn request_hash(
    tool: &ExternalToolIdentity,
    input: &ExternalPerformanceInput,
) -> Result<String, ExternalAdapterError> {
    let bytes = serde_json::to_vec(&HashableRequest {
        schema_version: EXTERNAL_SCHEMA_VERSION,
        tool,
        input,
    })
    .map_err(|error| ExternalAdapterError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalSimulationResponse {
    pub schema_version: u32,
    pub tool: ExternalToolIdentity,
    pub input_hash: String,
    pub result: PhaseResult,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ExternalRunStatus {
    Succeeded,
    TimedOut,
    SpawnFailed,
    IoFailed,
    NonZeroExit,
    OutputLimitExceeded,
    InvalidUtf8,
    InvalidJson,
    SchemaMismatch,
    ToolMismatch,
    HashMismatch,
    InvalidMeasurement,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct ExternalRunRecord {
    pub tool_spec: ExternalToolSpec,
    pub request: ExternalSimulationRequest,
    pub status: ExternalRunStatus,
    pub exit_code: Option<i32>,
    pub stdout: String,
    pub stderr: String,
    pub response: Option<ExternalSimulationResponse>,
    pub error: Option<String>,
}

impl ExternalRunRecord {
    pub fn result(&self) -> Result<&PhaseResult, ExternalRecordError> {
        if self.status != ExternalRunStatus::Succeeded {
            return Err(ExternalRecordError::Unsuccessful(self.status));
        }
        self.response
            .as_ref()
            .map(|response| &response.result)
            .ok_or(ExternalRecordError::MissingResponse)
    }

    fn failure(
        tool_spec: ExternalToolSpec,
        request: ExternalSimulationRequest,
        status: ExternalRunStatus,
        capture: ProcessCapture,
        error: String,
    ) -> Self {
        Self {
            tool_spec,
            request,
            status,
            exit_code: capture.exit_code,
            stdout: String::from_utf8_lossy(&capture.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&capture.stderr).into_owned(),
            response: None,
            error: Some(error),
        }
    }
}

#[derive(Clone, Copy, Debug, Error, Eq, PartialEq)]
pub enum ExternalRecordError {
    #[error("external run was not successful: {0:?}")]
    Unsuccessful(ExternalRunStatus),
    #[error("successful external run is missing its response")]
    MissingResponse,
}

#[derive(Clone)]
pub struct ExternalProcessAdapter {
    tool: ExternalToolSpec,
    runner: Arc<dyn ProcessRunner>,
}

impl fmt::Debug for ExternalProcessAdapter {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ExternalProcessAdapter")
            .field("tool", &self.tool)
            .finish_non_exhaustive()
    }
}

impl ExternalProcessAdapter {
    pub fn new(tool: ExternalToolSpec) -> Result<Self, ExternalAdapterError> {
        Self::with_runner(tool, Arc::new(SystemProcessRunner))
    }

    fn with_runner(
        tool: ExternalToolSpec,
        runner: Arc<dyn ProcessRunner>,
    ) -> Result<Self, ExternalAdapterError> {
        validate_tool(&tool)?;
        Ok(Self { tool, runner })
    }

    pub fn tool(&self) -> &ExternalToolSpec {
        &self.tool
    }

    pub fn request(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<ExternalSimulationRequest, ExternalAdapterError> {
        ExternalSimulationRequest::new(self.tool.identity.clone(), model, hardware, work)
    }

    pub fn run(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<ExternalRunRecord, ExternalAdapterError> {
        let request = self.request(model, hardware, work)?;
        let mut stdin = serde_json::to_vec(&request)
            .map_err(|error| ExternalAdapterError::Serialization(error.to_string()))?;
        if stdin.len() > MAX_REQUEST_BYTES {
            return Err(ExternalAdapterError::InputLimitExceeded {
                bytes: stdin.len(),
                limit: MAX_REQUEST_BYTES,
            });
        }
        stdin.push(b'\n');
        let capture = self.runner.execute(&ProcessInvocation {
            executable: self.tool.executable.clone(),
            arguments: self.tool.arguments.clone(),
            stdin,
            timeout: Duration::from_millis(self.tool.timeout_milliseconds),
            max_output_bytes: self.tool.max_output_bytes,
        });
        Ok(record_capture(self.tool.clone(), request, capture))
    }
}

fn record_capture(
    tool_spec: ExternalToolSpec,
    request: ExternalSimulationRequest,
    capture: ProcessCapture,
) -> ExternalRunRecord {
    if let Some((status, error)) = &capture.failure {
        return ExternalRunRecord::failure(
            tool_spec,
            request,
            *status,
            capture.clone(),
            error.clone(),
        );
    }
    if capture.stdout_truncated || capture.stderr_truncated {
        return ExternalRunRecord::failure(
            tool_spec,
            request,
            ExternalRunStatus::OutputLimitExceeded,
            capture,
            "external tool exceeded the configured output limit".into(),
        );
    }
    if capture.exit_code != Some(0) {
        let message = capture
            .exit_code
            .map(|code| format!("external tool exited with status {code}"))
            .unwrap_or_else(|| "external tool terminated without an exit status".into());
        return ExternalRunRecord::failure(
            tool_spec,
            request,
            ExternalRunStatus::NonZeroExit,
            capture,
            message,
        );
    }
    let stdout = match String::from_utf8(capture.stdout.clone()) {
        Ok(stdout) => stdout,
        Err(error) => {
            return ExternalRunRecord::failure(
                tool_spec,
                request,
                ExternalRunStatus::InvalidUtf8,
                capture,
                error.to_string(),
            );
        }
    };
    let stderr = String::from_utf8_lossy(&capture.stderr).into_owned();
    let mut response: ExternalSimulationResponse = match serde_json::from_str(&stdout) {
        Ok(response) => response,
        Err(error) => {
            return ExternalRunRecord {
                tool_spec,
                request,
                status: ExternalRunStatus::InvalidJson,
                exit_code: capture.exit_code,
                stdout,
                stderr,
                response: None,
                error: Some(error.to_string()),
            };
        }
    };
    let validation = validate_response(&request, &response);
    if let Err((status, error)) = validation {
        return ExternalRunRecord {
            tool_spec,
            request,
            status,
            exit_code: capture.exit_code,
            stdout,
            stderr,
            response: Some(response),
            error: Some(error),
        };
    }
    response.result.fidelity = OracleFidelity::External;
    ExternalRunRecord {
        tool_spec,
        request,
        status: ExternalRunStatus::Succeeded,
        exit_code: capture.exit_code,
        stdout,
        stderr,
        response: Some(response),
        error: None,
    }
}

fn validate_response(
    request: &ExternalSimulationRequest,
    response: &ExternalSimulationResponse,
) -> Result<(), (ExternalRunStatus, String)> {
    if response.schema_version != EXTERNAL_SCHEMA_VERSION {
        return Err((
            ExternalRunStatus::SchemaMismatch,
            format!(
                "expected schema {}, received {}",
                EXTERNAL_SCHEMA_VERSION, response.schema_version
            ),
        ));
    }
    if response.tool != request.tool {
        return Err((
            ExternalRunStatus::ToolMismatch,
            "response tool identity does not match the request".into(),
        ));
    }
    if response.input_hash != request.input_hash {
        return Err((
            ExternalRunStatus::HashMismatch,
            "response input hash does not match the request".into(),
        ));
    }
    validate_measurement(&request.input.work, &response.result)
        .map_err(|error| (ExternalRunStatus::InvalidMeasurement, error.to_string()))
}

fn validate_measurement(work: &PhaseWork, result: &PhaseResult) -> Result<(), ExternalOracleError> {
    if result.phase != work.phase
        || result.batch_size != work.batch_size
        || result.new_tokens != work.new_tokens
        || result.interchip_bytes != work.interchip_bytes
    {
        return Err(ExternalOracleError::InvalidMeasurement(
            "phase work identity does not match".into(),
        ));
    }
    for (field, value, positive) in [
        ("flops", result.flops, false),
        ("executed_flops", result.executed_flops, false),
        (
            "effective_compute_operations_per_second",
            result.effective_compute_operations_per_second,
            true,
        ),
        (
            "effective_memory_bandwidth_bytes_per_second",
            result.effective_memory_bandwidth_bytes_per_second,
            true,
        ),
        ("compute_seconds", result.compute_seconds, false),
        ("memory_seconds", result.memory_seconds, false),
        ("launch_seconds", result.launch_seconds, false),
        ("latency_seconds", result.latency_seconds, true),
        ("energy_joules", result.energy_joules, false),
    ] {
        if !value.is_finite() || if positive { value <= 0.0 } else { value < 0.0 } {
            return Err(ExternalOracleError::InvalidMeasurement(field.into()));
        }
    }
    if result.executed_flops < result.flops
        || !result.tile_utilization.is_finite()
        || result.tile_utilization <= 0.0
        || result.tile_utilization > 1.0
    {
        return Err(ExternalOracleError::InvalidMeasurement(
            "tile execution accounting".into(),
        ));
    }
    for action in &result.actions {
        if !action.operations.is_finite()
            || action.operations < 0.0
            || !action.latency_seconds.is_finite()
            || action.latency_seconds < 0.0
            || !action.energy_joules.is_finite()
            || action.energy_joules < 0.0
        {
            return Err(ExternalOracleError::InvalidMeasurement(
                "invalid action value".into(),
            ));
        }
    }
    Ok(())
}

#[derive(Clone, Debug)]
pub struct ExternalPerformanceOracle {
    tool: ExternalToolIdentity,
    measurements: BTreeMap<String, PhaseResult>,
}

impl ExternalPerformanceOracle {
    pub fn from_records(
        tool: ExternalToolIdentity,
        records: impl IntoIterator<Item = ExternalRunRecord>,
    ) -> Result<Self, ExternalOracleError> {
        validate_identity(&tool)
            .map_err(|error| ExternalOracleError::InvalidRecord(error.to_string()))?;
        let mut measurements = BTreeMap::new();
        for record in records {
            if record.request.tool != tool || record.tool_spec.identity != tool {
                return Err(ExternalOracleError::ToolMismatch);
            }
            if !record
                .request
                .verify_hash()
                .map_err(|error| ExternalOracleError::InvalidRecord(error.to_string()))?
            {
                return Err(ExternalOracleError::InvalidRecord(
                    "request hash is invalid".into(),
                ));
            }
            let mut result = record
                .result()
                .map_err(|error| ExternalOracleError::InvalidRecord(error.to_string()))?
                .clone();
            let response = record.response.as_ref().ok_or_else(|| {
                ExternalOracleError::InvalidRecord("successful record has no response".into())
            })?;
            validate_response(&record.request, response)
                .map_err(|(_, error)| ExternalOracleError::InvalidRecord(error))?;
            validate_measurement(&record.request.input.work, &result)?;
            result.fidelity = OracleFidelity::External;
            if let Some(existing) = measurements.insert(record.request.input_hash, result.clone()) {
                if existing != result {
                    return Err(ExternalOracleError::ConflictingMeasurement);
                }
            }
        }
        Ok(Self { tool, measurements })
    }

    pub fn replay(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, ExternalOracleError> {
        let request = ExternalSimulationRequest::new(self.tool.clone(), model, hardware, work)
            .map_err(|error| ExternalOracleError::InvalidRecord(error.to_string()))?;
        self.measurements
            .get(&request.input_hash)
            .cloned()
            .ok_or(ExternalOracleError::MissingMeasurement)
    }

    pub fn measurement_count(&self) -> usize {
        self.measurements.len()
    }

    pub fn tool_identity(&self) -> &ExternalToolIdentity {
        &self.tool
    }
}

impl PerformanceOracle for ExternalPerformanceOracle {
    fn estimate(
        &self,
        model: &ModelSpec,
        hardware: &HardwareSpec,
        work: &PhaseWork,
    ) -> Result<PhaseResult, PerformanceError> {
        self.replay(model, hardware, work)
            .map_err(|_| PerformanceError::MissingResource {
                resource: "recorded external measurement",
            })
    }
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum ExternalOracleError {
    #[error("record belongs to a different external tool")]
    ToolMismatch,
    #[error("external record is invalid: {0}")]
    InvalidRecord(String),
    #[error("external measurement is invalid: {0}")]
    InvalidMeasurement(String),
    #[error("conflicting external measurements share an input hash")]
    ConflictingMeasurement,
    #[error("no external measurement was recorded for this input")]
    MissingMeasurement,
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum ExternalAdapterError {
    #[error("invalid external tool field: {field}")]
    InvalidTool { field: &'static str },
    #[error("failed to serialize external request: {0}")]
    Serialization(String),
    #[error("external request is {bytes} bytes, exceeding the {limit}-byte limit")]
    InputLimitExceeded { bytes: usize, limit: usize },
}

fn validate_identity(identity: &ExternalToolIdentity) -> Result<(), ExternalAdapterError> {
    if identity.name.trim().is_empty() {
        return Err(ExternalAdapterError::InvalidTool {
            field: "identity.name",
        });
    }
    if identity.version.trim().is_empty() {
        return Err(ExternalAdapterError::InvalidTool {
            field: "identity.version",
        });
    }
    Ok(())
}

fn validate_tool(tool: &ExternalToolSpec) -> Result<(), ExternalAdapterError> {
    validate_identity(&tool.identity)?;
    if tool.executable.as_os_str().is_empty() || !tool.executable.is_absolute() {
        return Err(ExternalAdapterError::InvalidTool {
            field: "executable",
        });
    }
    if tool.timeout_milliseconds == 0 || tool.timeout_milliseconds > MAX_TIMEOUT_MILLISECONDS {
        return Err(ExternalAdapterError::InvalidTool {
            field: "timeout_milliseconds",
        });
    }
    if tool.max_output_bytes == 0 || tool.max_output_bytes > MAX_CAPTURE_BYTES {
        return Err(ExternalAdapterError::InvalidTool {
            field: "max_output_bytes",
        });
    }
    Ok(())
}

trait ProcessRunner: Send + Sync {
    fn execute(&self, invocation: &ProcessInvocation) -> ProcessCapture;
}

struct ProcessInvocation {
    executable: PathBuf,
    arguments: Vec<String>,
    stdin: Vec<u8>,
    timeout: Duration,
    max_output_bytes: usize,
}

#[derive(Clone)]
struct ProcessCapture {
    exit_code: Option<i32>,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    stdout_truncated: bool,
    stderr_truncated: bool,
    failure: Option<(ExternalRunStatus, String)>,
}

impl ProcessCapture {
    #[cfg(test)]
    fn completed(exit_code: i32, stdout: Vec<u8>, stderr: Vec<u8>) -> Self {
        Self {
            exit_code: Some(exit_code),
            stdout,
            stderr,
            stdout_truncated: false,
            stderr_truncated: false,
            failure: None,
        }
    }

    #[cfg(test)]
    fn failed(status: ExternalRunStatus, stdout: Vec<u8>, stderr: Vec<u8>, error: &str) -> Self {
        Self {
            exit_code: None,
            stdout,
            stderr,
            stdout_truncated: false,
            stderr_truncated: false,
            failure: Some((status, error.into())),
        }
    }
}

struct SystemProcessRunner;

impl ProcessRunner for SystemProcessRunner {
    fn execute(&self, invocation: &ProcessInvocation) -> ProcessCapture {
        let mut command = Command::new(&invocation.executable);
        command
            .args(&invocation.arguments)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                return process_failure(ExternalRunStatus::SpawnFailed, error.to_string());
            }
        };
        let stdout = match child.stdout.take() {
            Some(stdout) => stdout,
            None => {
                let _ = child.kill();
                let _ = child.wait();
                return process_failure(
                    ExternalRunStatus::IoFailed,
                    "external tool stdout was not piped".into(),
                );
            }
        };
        let stderr = match child.stderr.take() {
            Some(stderr) => stderr,
            None => {
                let _ = child.kill();
                let _ = child.wait();
                return process_failure(
                    ExternalRunStatus::IoFailed,
                    "external tool stderr was not piped".into(),
                );
            }
        };
        let mut stdin = match child.stdin.take() {
            Some(stdin) => stdin,
            None => {
                let _ = child.kill();
                let _ = child.wait();
                return process_failure(
                    ExternalRunStatus::IoFailed,
                    "external tool stdin was not piped".into(),
                );
            }
        };
        let output_limit = invocation.max_output_bytes;
        let stdout_reader = thread::spawn(move || read_limited(stdout, output_limit));
        let stderr_reader = thread::spawn(move || read_limited(stderr, output_limit));
        let input = invocation.stdin.clone();
        let stdin_writer = thread::spawn(move || match stdin.write_all(&input) {
            Err(error) if error.kind() == ErrorKind::BrokenPipe => Ok(()),
            result => result.map_err(|error| error.to_string()),
        });

        let deadline = Instant::now() + invocation.timeout;
        loop {
            match child.try_wait() {
                Ok(Some(status)) => {
                    return join_capture(
                        status.code(),
                        stdin_writer,
                        stdout_reader,
                        stderr_reader,
                        None,
                    );
                }
                Ok(None) if Instant::now() >= deadline => {
                    let _ = child.kill();
                    let status = child.wait().ok().and_then(|status| status.code());
                    return join_capture(
                        status,
                        stdin_writer,
                        stdout_reader,
                        stderr_reader,
                        Some((
                            ExternalRunStatus::TimedOut,
                            format!(
                                "external tool exceeded {} ms timeout",
                                invocation.timeout.as_millis()
                            ),
                        )),
                    );
                }
                Ok(None) => thread::sleep(Duration::from_millis(1)),
                Err(error) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return join_capture(
                        None,
                        stdin_writer,
                        stdout_reader,
                        stderr_reader,
                        Some((ExternalRunStatus::IoFailed, error.to_string())),
                    );
                }
            }
        }
    }
}

type ReaderHandle = thread::JoinHandle<Result<(Vec<u8>, bool), String>>;
type WriterHandle = thread::JoinHandle<Result<(), String>>;

fn read_limited(reader: impl Read, limit: usize) -> Result<(Vec<u8>, bool), String> {
    let byte_limit = u64::try_from(limit)
        .map_err(|error| error.to_string())?
        .checked_add(1)
        .ok_or_else(|| "output limit overflow".to_string())?;
    let mut bytes = Vec::new();
    reader
        .take(byte_limit)
        .read_to_end(&mut bytes)
        .map_err(|error| error.to_string())?;
    let truncated = bytes.len() > limit;
    bytes.truncate(limit);
    Ok((bytes, truncated))
}

fn join_capture(
    exit_code: Option<i32>,
    stdin_writer: WriterHandle,
    stdout_reader: ReaderHandle,
    stderr_reader: ReaderHandle,
    failure: Option<(ExternalRunStatus, String)>,
) -> ProcessCapture {
    let writer_failure = stdin_writer
        .join()
        .map_err(|_| "external stdin writer panicked".to_string())
        .and_then(|result| result)
        .err()
        .map(|error| (ExternalRunStatus::IoFailed, error));
    let stdout = join_reader(stdout_reader, "stdout");
    let stderr = join_reader(stderr_reader, "stderr");
    let reader_failure = stdout
        .as_ref()
        .err()
        .or_else(|| stderr.as_ref().err())
        .map(|error| (ExternalRunStatus::IoFailed, error.clone()));
    let (stdout, stdout_truncated) = stdout.unwrap_or_default();
    let (stderr, stderr_truncated) = stderr.unwrap_or_default();
    ProcessCapture {
        exit_code,
        stdout,
        stderr,
        stdout_truncated,
        stderr_truncated,
        failure: failure.or(writer_failure).or(reader_failure),
    }
}

fn join_reader(handle: ReaderHandle, stream: &str) -> Result<(Vec<u8>, bool), String> {
    handle
        .join()
        .map_err(|_| format!("external {stream} reader panicked"))?
        .map_err(|error| format!("failed to read external {stream}: {error}"))
}

fn process_failure(status: ExternalRunStatus, error: String) -> ProcessCapture {
    ProcessCapture {
        exit_code: None,
        stdout: Vec::new(),
        stderr: Vec::new(),
        stdout_truncated: false,
        stderr_truncated: false,
        failure: Some((status, error)),
    }
}
