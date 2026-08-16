use std::collections::VecDeque;

use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::performance::{PerformanceError, PerformanceOracle, PhaseResult, PhaseWork};
use crate::spec::{
    AgenticWorkloadSpec, ExecutionMappingSpec, ExperimentSpec, HardwareSpec, ModelArchitecture,
    ModelSpec, ServingSpec, ValidationErrors,
};

#[derive(Clone, Copy)]
pub struct SimulationInput<'a> {
    pub model: &'a ModelSpec,
    pub workload: &'a AgenticWorkloadSpec,
    pub hardware: &'a HardwareSpec,
    pub mapping: &'a ExecutionMappingSpec,
    pub serving: &'a ServingSpec,
}

impl<'a> From<&'a ExperimentSpec> for SimulationInput<'a> {
    fn from(spec: &'a ExperimentSpec) -> Self {
        Self {
            model: &spec.model,
            workload: &spec.workload,
            hardware: &spec.hardware,
            mapping: &spec.mapping,
            serving: &spec.serving,
        }
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct GeneratedRequest {
    pub request_id: u64,
    pub class_name: String,
    pub arrival_seconds: f64,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cached_prefix_tokens: u32,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
pub struct PhaseActivity {
    pub invocations: u64,
    pub scheduled_requests: u64,
    pub tokens: u64,
    pub flops: f64,
    pub executed_flops: f64,
    pub weight_bytes: u64,
    pub activation_bytes: u64,
    pub kv_read_bytes: u64,
    pub kv_write_bytes: u64,
    pub interchip_bytes: u64,
    pub busy_seconds: f64,
    pub energy_joules: f64,
}

impl PhaseActivity {
    fn record(
        &mut self,
        scheduled_requests: usize,
        result: &PhaseResult,
    ) -> Result<(), SimulationError> {
        self.invocations = checked_add(self.invocations, 1, "phase invocations")?;
        self.scheduled_requests = checked_add(
            self.scheduled_requests,
            u64::try_from(scheduled_requests).map_err(|_| SimulationError::Overflow {
                field: "scheduled requests",
            })?,
            "scheduled requests",
        )?;
        self.tokens = checked_add(self.tokens, result.new_tokens, "phase tokens")?;
        self.weight_bytes = checked_add(self.weight_bytes, result.weight_bytes, "weight traffic")?;
        self.activation_bytes = checked_add(
            self.activation_bytes,
            result.activation_bytes,
            "activation traffic",
        )?;
        self.kv_read_bytes = checked_add(self.kv_read_bytes, result.kv_read_bytes, "KV reads")?;
        self.kv_write_bytes = checked_add(self.kv_write_bytes, result.kv_write_bytes, "KV writes")?;
        self.interchip_bytes = checked_add(
            self.interchip_bytes,
            result.interchip_bytes,
            "interchip traffic",
        )?;
        self.flops += result.flops;
        self.executed_flops += result.executed_flops;
        self.busy_seconds += result.latency_seconds;
        self.energy_joules += result.energy_joules;
        if !self.flops.is_finite()
            || !self.busy_seconds.is_finite()
            || !self.energy_joules.is_finite()
        {
            return Err(SimulationError::Overflow {
                field: "phase activity",
            });
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct RequestMetrics {
    pub request_id: u64,
    pub class_name: String,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cached_prefix_tokens: u32,
    pub arrival_seconds: f64,
    pub first_token_seconds: f64,
    pub completion_seconds: f64,
    pub queue_time_milliseconds: f64,
    pub latency_milliseconds: f64,
    pub ttft_milliseconds: f64,
    pub tpot_milliseconds: f64,
    pub ttft_slo_met: bool,
    pub tpot_slo_met: bool,
}

impl RequestMetrics {
    pub fn meets_slos(&self) -> bool {
        self.ttft_slo_met && self.tpot_slo_met
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct SimulationReport {
    pub request_count: u64,
    pub completed_requests: u64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cached_prefix_tokens: u64,
    pub prefill_tokens: u64,
    pub duration_seconds: f64,
    pub throughput_requests_per_second: f64,
    pub output_tokens_per_second: f64,
    pub goodput_requests_per_second: f64,
    pub goodput_output_tokens_per_second: f64,
    pub mean_queue_time_milliseconds: f64,
    pub mean_latency_milliseconds: f64,
    pub p95_latency_milliseconds: f64,
    pub mean_ttft_milliseconds: f64,
    pub p95_ttft_milliseconds: f64,
    pub mean_tpot_milliseconds: f64,
    pub p95_tpot_milliseconds: f64,
    pub ttft_slo_met_requests: u64,
    pub tpot_slo_met_requests: u64,
    pub slo_met_requests: u64,
    pub kv_cache_capacity_bytes: u64,
    pub peak_kv_cache_bytes: u64,
    pub prefill: PhaseActivity,
    pub decode: PhaseActivity,
    pub total_busy_seconds: f64,
    pub total_energy_joules: f64,
    pub requests: Vec<RequestMetrics>,
}

#[derive(Debug, Error, PartialEq)]
pub enum SimulationError {
    #[error("model architecture does not have complete simulation accounting")]
    UnsupportedModelArchitecture,
    #[error("invalid experiment specification: {0}")]
    InvalidExperiment(ValidationErrors),
    #[error("{field} is invalid for simulation")]
    InvalidInput { field: &'static str },
    #[error("hardware memory capacity is unavailable")]
    MemoryCapacityUnavailable,
    #[error(
        "model weights require {required_bytes} bytes but hardware has {available_bytes} bytes"
    )]
    ModelDoesNotFit {
        required_bytes: u64,
        available_bytes: u64,
    },
    #[error(
        "a request requires {required_bytes} KV bytes but only {available_bytes} bytes are available"
    )]
    InsufficientKvMemory {
        required_bytes: u64,
        available_bytes: u64,
    },
    #[error("{field} exceeds the supported numeric range")]
    Overflow { field: &'static str },
    #[error("performance oracle failed: {0}")]
    Performance(#[from] PerformanceError),
    #[error("simulation stalled with {remaining_requests} requests remaining")]
    Stalled { remaining_requests: usize },
}

#[derive(Clone, Copy, Debug, Default)]
pub struct ServingSimulator;

impl ServingSimulator {
    pub fn run<O: PerformanceOracle + ?Sized>(
        &self,
        spec: &ExperimentSpec,
        oracle: &O,
    ) -> Result<SimulationReport, SimulationError> {
        spec.validate()
            .map_err(SimulationError::InvalidExperiment)?;
        self.run_input(SimulationInput::from(spec), oracle)
    }

    pub fn run_input<O: PerformanceOracle + ?Sized>(
        &self,
        input: SimulationInput<'_>,
        oracle: &O,
    ) -> Result<SimulationReport, SimulationError> {
        validate_input(input)?;
        if !matches!(input.model.architecture, ModelArchitecture::DenseDecoder) {
            return Err(SimulationError::UnsupportedModelArchitecture);
        }
        let requests = generate_requests(input.workload)?;
        let kv_bytes_per_token =
            input
                .model
                .kv_bytes_per_token()
                .ok_or(SimulationError::Overflow {
                    field: "KV bytes per token",
                })?;
        let memory_capacity = input
            .hardware
            .effective_memory_capacity_bytes()
            .ok_or(SimulationError::MemoryCapacityUnavailable)?;
        let model_bytes = input
            .model
            .weight_bytes()
            .ok_or(SimulationError::Overflow {
                field: "model weights",
            })?;
        if model_bytes > memory_capacity {
            return Err(SimulationError::ModelDoesNotFit {
                required_bytes: model_bytes,
                available_bytes: memory_capacity,
            });
        }
        let configured_kv_bytes =
            (memory_capacity as f64 * input.serving.kv_cache_memory_fraction).floor() as u64;
        let kv_capacity = configured_kv_bytes.min(memory_capacity - model_bytes);
        let mut states = requests
            .into_iter()
            .map(|request| RequestState::new(request, kv_bytes_per_token))
            .collect::<Result<Vec<_>, _>>()?;
        for state in &states {
            if state.reserved_kv_bytes > kv_capacity {
                return Err(SimulationError::InsufficientKvMemory {
                    required_bytes: state.reserved_kv_bytes,
                    available_bytes: kv_capacity,
                });
            }
        }

        let mut current_seconds = 0.0;
        let mut next_arrival = 0_usize;
        let mut pending = VecDeque::new();
        let mut active = Vec::new();
        let mut kv_bytes_in_use = 0_u64;
        let mut peak_kv_cache_bytes = 0_u64;
        let mut completed = 0_usize;
        let mut prefill = PhaseActivity::default();
        let mut decode = PhaseActivity::default();
        let mut consecutive_decode_steps = 0_u32;

        while completed < states.len() {
            while next_arrival < states.len()
                && states[next_arrival].request.arrival_seconds <= current_seconds
            {
                pending.push_back(next_arrival);
                next_arrival += 1;
            }
            admit_requests(
                &mut pending,
                &mut active,
                &states,
                &mut kv_bytes_in_use,
                &mut peak_kv_cache_bytes,
                kv_capacity,
                input.serving.max_concurrent_requests as usize,
            )?;

            if active.is_empty() {
                if let Some(state) = states.get(next_arrival) {
                    current_seconds = current_seconds.max(state.request.arrival_seconds);
                    continue;
                }
                return Err(SimulationError::Stalled {
                    remaining_requests: states.len() - completed,
                });
            }

            let decode_batch = active
                .iter()
                .copied()
                .filter(|index| states[*index].ready_to_decode())
                .take(input.serving.max_batch_size as usize)
                .collect::<Vec<_>>();
            let has_prefill = active
                .iter()
                .any(|index| states[*index].prefill_remaining > 0);
            let schedule_prefill = decode_batch.is_empty()
                || (has_prefill
                    && consecutive_decode_steps >= input.serving.prefill_interleave_decode_steps);
            let phase_start = current_seconds;
            if schedule_prefill {
                let prefill_batch = active
                    .iter()
                    .copied()
                    .filter(|index| states[*index].prefill_remaining > 0)
                    .take(input.serving.max_batch_size as usize)
                    .collect::<Vec<_>>();
                if prefill_batch.is_empty() {
                    return Err(SimulationError::Stalled {
                        remaining_requests: states.len() - completed,
                    });
                }
                let chunks = prefill_batch
                    .iter()
                    .map(|index| {
                        states[*index]
                            .prefill_remaining
                            .min(input.serving.prefill_chunk_tokens)
                    })
                    .collect::<Vec<_>>();
                let new_tokens = chunks.iter().try_fold(0_u64, |total, chunk| {
                    checked_add(total, u64::from(*chunk), "prefill tokens")
                })?;
                let attention_pairs = prefill_batch.iter().zip(&chunks).try_fold(
                    0_u64,
                    |total, (index, chunk)| {
                        let pairs = prefill_attention_pairs(
                            states[*index].context_tokens,
                            u64::from(*chunk),
                        )?;
                        checked_add(total, pairs, "prefill attention pairs")
                    },
                )?;
                mark_scheduled(&mut states, &prefill_batch, phase_start);
                let work = PhaseWork::prefill(
                    u32::try_from(prefill_batch.len()).map_err(|_| SimulationError::Overflow {
                        field: "prefill batch size",
                    })?,
                    new_tokens,
                    attention_pairs,
                )
                .with_interchip_bytes(interchip_bytes(
                    input.model,
                    input.mapping,
                    new_tokens,
                )?);
                let result = oracle.estimate(input.model, input.hardware, &work)?;
                current_seconds = advance_time(current_seconds, result.latency_seconds)?;
                for (index, chunk) in prefill_batch.iter().zip(chunks) {
                    let state = &mut states[*index];
                    state.prefill_remaining -= chunk;
                    state.context_tokens =
                        checked_add(state.context_tokens, u64::from(chunk), "request context")?;
                }
                prefill.record(prefill_batch.len(), &result)?;
                consecutive_decode_steps = 0;
            } else {
                let attention_pairs = decode_batch.iter().try_fold(0_u64, |total, index| {
                    checked_add(
                        total,
                        states[*index].context_tokens.saturating_add(1),
                        "decode attention pairs",
                    )
                })?;
                mark_scheduled(&mut states, &decode_batch, phase_start);
                let work = PhaseWork::decode(
                    u32::try_from(decode_batch.len()).map_err(|_| SimulationError::Overflow {
                        field: "decode batch size",
                    })?,
                    attention_pairs,
                )
                .with_interchip_bytes(interchip_bytes(
                    input.model,
                    input.mapping,
                    u64::try_from(decode_batch.len()).map_err(|_| SimulationError::Overflow {
                        field: "decode interchip tokens",
                    })?,
                )?);
                let result = oracle.estimate(input.model, input.hardware, &work)?;
                current_seconds = advance_time(current_seconds, result.latency_seconds)?;
                for index in &decode_batch {
                    states[*index].record_token(current_seconds, result.latency_seconds)?;
                }
                decode.record(decode_batch.len(), &result)?;
                consecutive_decode_steps = consecutive_decode_steps.saturating_add(1);

                let finished = decode_batch
                    .iter()
                    .copied()
                    .filter(|index| states[*index].is_complete())
                    .collect::<Vec<_>>();
                for index in &finished {
                    states[*index].completion_seconds = Some(current_seconds);
                    kv_bytes_in_use = kv_bytes_in_use
                        .checked_sub(states[*index].reserved_kv_bytes)
                        .ok_or(SimulationError::Overflow {
                            field: "KV cache accounting",
                        })?;
                    completed += 1;
                }
                active.retain(|index| !finished.contains(index));
            }
        }

        build_report(
            states,
            input.serving,
            kv_capacity,
            peak_kv_cache_bytes,
            prefill,
            decode,
        )
    }
}

fn interchip_bytes(
    model: &ModelSpec,
    mapping: &ExecutionMappingSpec,
    new_tokens: u64,
) -> Result<u64, SimulationError> {
    let activation_bytes = new_tokens
        .checked_mul(u64::from(model.hidden_size))
        .and_then(|value| value.checked_mul(2))
        .ok_or(SimulationError::Overflow {
            field: "interchip activations",
        })?;
    let tensor_parallel_bytes = activation_bytes
        .checked_mul(u64::from(model.layer_count))
        .and_then(|value| value.checked_mul(4))
        .and_then(|value| {
            value.checked_mul(u64::from(mapping.tensor_parallelism.saturating_sub(1)))
        })
        .ok_or(SimulationError::Overflow {
            field: "tensor-parallel traffic",
        })?;
    let pipeline_parallel_bytes = activation_bytes
        .checked_mul(u64::from(mapping.pipeline_parallelism.saturating_sub(1)))
        .ok_or(SimulationError::Overflow {
            field: "pipeline-parallel traffic",
        })?;
    tensor_parallel_bytes
        .checked_add(pipeline_parallel_bytes)
        .ok_or(SimulationError::Overflow {
            field: "interchip traffic",
        })
}

pub fn generate_requests(
    workload: &AgenticWorkloadSpec,
) -> Result<Vec<GeneratedRequest>, SimulationError> {
    if workload.request_count == 0 {
        return Err(SimulationError::InvalidInput {
            field: "workload.request_count",
        });
    }
    if !workload.arrival_rate_per_second.is_finite() || workload.arrival_rate_per_second <= 0.0 {
        return Err(SimulationError::InvalidInput {
            field: "workload.arrival_rate_per_second",
        });
    }
    if workload.request_classes.is_empty() {
        return Err(SimulationError::InvalidInput {
            field: "workload.request_classes",
        });
    }
    let total_share = workload
        .request_classes
        .iter()
        .map(|class| class.share)
        .sum::<f64>();
    if !total_share.is_finite() || (total_share - 1.0).abs() > 1.0e-6 {
        return Err(SimulationError::InvalidInput {
            field: "workload.request_classes.share",
        });
    }
    let request_count =
        usize::try_from(workload.request_count).map_err(|_| SimulationError::Overflow {
            field: "request count",
        })?;
    let mut requests = Vec::new();
    requests
        .try_reserve_exact(request_count)
        .map_err(|_| SimulationError::Overflow {
            field: "request allocation",
        })?;
    let mut random = SplitMix64::new(workload.seed);
    let mut arrival_seconds = 0.0;
    for request_id in 0..workload.request_count {
        if request_id > 0 {
            let uniform = random.unit_interval().max(f64::MIN_POSITIVE);
            arrival_seconds += -uniform.ln() / workload.arrival_rate_per_second;
        }
        let class_draw = random.unit_interval();
        let mut cumulative_share = 0.0;
        let mut selected =
            workload
                .request_classes
                .last()
                .ok_or(SimulationError::InvalidInput {
                    field: "workload.request_classes",
                })?;
        for class in &workload.request_classes {
            cumulative_share += class.share;
            if class_draw < cumulative_share {
                selected = class;
                break;
            }
        }
        let cached_prefix_tokens =
            (f64::from(selected.input_tokens) * selected.prefix_cache_hit_ratio).floor() as u32;
        requests.push(GeneratedRequest {
            request_id,
            class_name: selected.name.clone(),
            arrival_seconds,
            input_tokens: selected.input_tokens,
            output_tokens: selected.output_tokens,
            cached_prefix_tokens: cached_prefix_tokens.min(selected.input_tokens),
        });
    }
    Ok(requests)
}

struct RequestState {
    request: GeneratedRequest,
    prefill_remaining: u32,
    context_tokens: u64,
    decoded_tokens: u32,
    reserved_kv_bytes: u64,
    first_scheduled_seconds: Option<f64>,
    first_token_seconds: Option<f64>,
    last_token_seconds: Option<f64>,
    first_token_service_seconds: f64,
    inter_token_seconds: f64,
    inter_token_count: u32,
    completion_seconds: Option<f64>,
}

impl RequestState {
    fn new(request: GeneratedRequest, kv_bytes_per_token: u64) -> Result<Self, SimulationError> {
        let sequence_tokens = u64::from(request.input_tokens)
            .checked_add(u64::from(request.output_tokens))
            .ok_or(SimulationError::Overflow {
                field: "request sequence length",
            })?;
        let reserved_kv_bytes =
            sequence_tokens
                .checked_mul(kv_bytes_per_token)
                .ok_or(SimulationError::Overflow {
                    field: "request KV reservation",
                })?;
        Ok(Self {
            prefill_remaining: request.input_tokens - request.cached_prefix_tokens,
            context_tokens: u64::from(request.cached_prefix_tokens),
            request,
            decoded_tokens: 0,
            reserved_kv_bytes,
            first_scheduled_seconds: None,
            first_token_seconds: None,
            last_token_seconds: None,
            first_token_service_seconds: 0.0,
            inter_token_seconds: 0.0,
            inter_token_count: 0,
            completion_seconds: None,
        })
    }

    fn ready_to_decode(&self) -> bool {
        self.prefill_remaining == 0 && self.decoded_tokens < self.request.output_tokens
    }

    fn is_complete(&self) -> bool {
        self.decoded_tokens == self.request.output_tokens
    }

    fn record_token(
        &mut self,
        completion_seconds: f64,
        service_seconds: f64,
    ) -> Result<(), SimulationError> {
        if let Some(previous) = self.last_token_seconds {
            self.inter_token_seconds += completion_seconds - previous;
            self.inter_token_count =
                self.inter_token_count
                    .checked_add(1)
                    .ok_or(SimulationError::Overflow {
                        field: "inter-token count",
                    })?;
        } else {
            self.first_token_seconds = Some(completion_seconds);
            self.first_token_service_seconds = service_seconds;
        }
        self.last_token_seconds = Some(completion_seconds);
        self.decoded_tokens =
            self.decoded_tokens
                .checked_add(1)
                .ok_or(SimulationError::Overflow {
                    field: "decoded tokens",
                })?;
        self.context_tokens = checked_add(self.context_tokens, 1, "request context")?;
        Ok(())
    }
}

fn validate_input(input: SimulationInput<'_>) -> Result<(), SimulationError> {
    if input.serving.max_batch_size == 0 {
        return Err(SimulationError::InvalidInput {
            field: "serving.max_batch_size",
        });
    }
    if input.serving.prefill_chunk_tokens == 0 {
        return Err(SimulationError::InvalidInput {
            field: "serving.prefill_chunk_tokens",
        });
    }
    if input.serving.prefill_interleave_decode_steps == 0 {
        return Err(SimulationError::InvalidInput {
            field: "serving.prefill_interleave_decode_steps",
        });
    }
    if input.serving.max_concurrent_requests == 0 {
        return Err(SimulationError::InvalidInput {
            field: "serving.max_concurrent_requests",
        });
    }
    if !input.serving.kv_cache_memory_fraction.is_finite()
        || input.serving.kv_cache_memory_fraction <= 0.0
        || input.serving.kv_cache_memory_fraction > 1.0
    {
        return Err(SimulationError::InvalidInput {
            field: "serving.kv_cache_memory_fraction",
        });
    }
    Ok(())
}

fn admit_requests(
    pending: &mut VecDeque<usize>,
    active: &mut Vec<usize>,
    states: &[RequestState],
    kv_bytes_in_use: &mut u64,
    peak_kv_cache_bytes: &mut u64,
    kv_capacity: u64,
    max_concurrent_requests: usize,
) -> Result<(), SimulationError> {
    while active.len() < max_concurrent_requests {
        let Some(index) = pending.front().copied() else {
            break;
        };
        let next_usage = kv_bytes_in_use
            .checked_add(states[index].reserved_kv_bytes)
            .ok_or(SimulationError::Overflow {
                field: "KV cache usage",
            })?;
        if next_usage > kv_capacity {
            break;
        }
        pending.pop_front();
        active.push(index);
        *kv_bytes_in_use = next_usage;
        *peak_kv_cache_bytes = (*peak_kv_cache_bytes).max(next_usage);
    }
    Ok(())
}

fn mark_scheduled(states: &mut [RequestState], batch: &[usize], phase_start: f64) {
    for index in batch {
        states[*index]
            .first_scheduled_seconds
            .get_or_insert(phase_start);
    }
}

fn prefill_attention_pairs(context: u64, new_tokens: u64) -> Result<u64, SimulationError> {
    let prior = context
        .checked_mul(new_tokens)
        .ok_or(SimulationError::Overflow {
            field: "prefill attention pairs",
        })?;
    let within_chunk = new_tokens
        .checked_mul(new_tokens.saturating_add(1))
        .and_then(|pairs| pairs.checked_div(2))
        .ok_or(SimulationError::Overflow {
            field: "prefill attention pairs",
        })?;
    checked_add(prior, within_chunk, "prefill attention pairs")
}

fn advance_time(current: f64, duration: f64) -> Result<f64, SimulationError> {
    if !duration.is_finite() || duration <= 0.0 {
        return Err(SimulationError::InvalidInput {
            field: "oracle latency",
        });
    }
    let next = current + duration;
    if !next.is_finite() || next <= current {
        return Err(SimulationError::Overflow {
            field: "simulation time",
        });
    }
    Ok(next)
}

fn build_report(
    states: Vec<RequestState>,
    serving: &ServingSpec,
    kv_cache_capacity_bytes: u64,
    peak_kv_cache_bytes: u64,
    prefill: PhaseActivity,
    decode: PhaseActivity,
) -> Result<SimulationReport, SimulationError> {
    let mut requests = Vec::with_capacity(states.len());
    for state in states {
        let first_scheduled = state
            .first_scheduled_seconds
            .ok_or(SimulationError::Stalled {
                remaining_requests: 1,
            })?;
        let first_token = state.first_token_seconds.ok_or(SimulationError::Stalled {
            remaining_requests: 1,
        })?;
        let completion = state.completion_seconds.ok_or(SimulationError::Stalled {
            remaining_requests: 1,
        })?;
        let tpot_seconds = if state.inter_token_count > 0 {
            state.inter_token_seconds / f64::from(state.inter_token_count)
        } else {
            state.first_token_service_seconds
        };
        let ttft_milliseconds = (first_token - state.request.arrival_seconds) * 1_000.0;
        let tpot_milliseconds = tpot_seconds * 1_000.0;
        requests.push(RequestMetrics {
            request_id: state.request.request_id,
            class_name: state.request.class_name,
            input_tokens: state.request.input_tokens,
            output_tokens: state.request.output_tokens,
            cached_prefix_tokens: state.request.cached_prefix_tokens,
            arrival_seconds: state.request.arrival_seconds,
            first_token_seconds: first_token,
            completion_seconds: completion,
            queue_time_milliseconds: (first_scheduled - state.request.arrival_seconds) * 1_000.0,
            latency_milliseconds: (completion - state.request.arrival_seconds) * 1_000.0,
            ttft_milliseconds,
            tpot_milliseconds,
            ttft_slo_met: ttft_milliseconds <= serving.ttft_slo_milliseconds,
            tpot_slo_met: tpot_milliseconds <= serving.tpot_slo_milliseconds,
        });
    }
    let first_arrival = requests
        .iter()
        .map(|request| request.arrival_seconds)
        .reduce(f64::min)
        .unwrap_or(0.0);
    let last_completion = requests
        .iter()
        .map(|request| request.completion_seconds)
        .reduce(f64::max)
        .unwrap_or(first_arrival);
    let duration_seconds = last_completion - first_arrival;
    if !duration_seconds.is_finite() || duration_seconds <= 0.0 {
        return Err(SimulationError::InvalidInput {
            field: "simulation duration",
        });
    }
    let input_tokens = requests
        .iter()
        .map(|request| u64::from(request.input_tokens))
        .sum();
    let output_tokens = requests
        .iter()
        .map(|request| u64::from(request.output_tokens))
        .sum();
    let cached_prefix_tokens = requests
        .iter()
        .map(|request| u64::from(request.cached_prefix_tokens))
        .sum();
    let ttft_slo_met_requests = requests
        .iter()
        .filter(|request| request.ttft_slo_met)
        .count() as u64;
    let tpot_slo_met_requests = requests
        .iter()
        .filter(|request| request.tpot_slo_met)
        .count() as u64;
    let slo_met_requests = requests
        .iter()
        .filter(|request| request.meets_slos())
        .count() as u64;
    let good_output_tokens = requests
        .iter()
        .filter(|request| request.meets_slos())
        .map(|request| u64::from(request.output_tokens))
        .sum::<u64>();
    let queue_times = requests
        .iter()
        .map(|request| request.queue_time_milliseconds)
        .collect::<Vec<_>>();
    let latencies = requests
        .iter()
        .map(|request| request.latency_milliseconds)
        .collect::<Vec<_>>();
    let ttfts = requests
        .iter()
        .map(|request| request.ttft_milliseconds)
        .collect::<Vec<_>>();
    let tpots = requests
        .iter()
        .map(|request| request.tpot_milliseconds)
        .collect::<Vec<_>>();
    let request_count = requests.len() as u64;

    Ok(SimulationReport {
        request_count,
        completed_requests: request_count,
        input_tokens,
        output_tokens,
        cached_prefix_tokens,
        prefill_tokens: prefill.tokens,
        duration_seconds,
        throughput_requests_per_second: request_count as f64 / duration_seconds,
        output_tokens_per_second: output_tokens as f64 / duration_seconds,
        goodput_requests_per_second: slo_met_requests as f64 / duration_seconds,
        goodput_output_tokens_per_second: good_output_tokens as f64 / duration_seconds,
        mean_queue_time_milliseconds: mean(&queue_times),
        mean_latency_milliseconds: mean(&latencies),
        p95_latency_milliseconds: percentile(&latencies, 0.95),
        mean_ttft_milliseconds: mean(&ttfts),
        p95_ttft_milliseconds: percentile(&ttfts, 0.95),
        mean_tpot_milliseconds: mean(&tpots),
        p95_tpot_milliseconds: percentile(&tpots, 0.95),
        ttft_slo_met_requests,
        tpot_slo_met_requests,
        slo_met_requests,
        kv_cache_capacity_bytes,
        peak_kv_cache_bytes,
        total_busy_seconds: prefill.busy_seconds + decode.busy_seconds,
        total_energy_joules: prefill.energy_joules + decode.energy_joules,
        prefill,
        decode,
        requests,
    })
}

fn mean(values: &[f64]) -> f64 {
    values.iter().sum::<f64>() / values.len() as f64
}

fn percentile(values: &[f64], quantile: f64) -> f64 {
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let index = ((sorted.len() as f64 * quantile).ceil() as usize)
        .saturating_sub(1)
        .min(sorted.len().saturating_sub(1));
    sorted[index]
}

fn checked_add(left: u64, right: u64, field: &'static str) -> Result<u64, SimulationError> {
    left.checked_add(right)
        .ok_or(SimulationError::Overflow { field })
}

struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn unit_interval(&mut self) -> f64 {
        self.state = self.state.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut value = self.state;
        value = (value ^ (value >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        value ^= value >> 31;
        (value >> 11) as f64 * (1.0 / ((1_u64 << 53) as f64))
    }
}

#[cfg(test)]
mod tests {
    use crate::performance::{
        Bottleneck, OracleFidelity, PerformanceOracle, PhaseResult, PhaseWork,
    };
    use crate::spec::{
        AgenticWorkloadSpec, AggregateHardwareSpec, ExecutionMappingSpec, HardwareFidelity,
        HardwareSpec, ModelArchitecture, ModelSpec, Precision, RequestClass, ServingSpec,
    };

    use super::{ServingSimulator, SimulationError, SimulationInput, generate_requests};

    struct FixedOracle;

    impl PerformanceOracle for FixedOracle {
        fn estimate(
            &self,
            _model: &ModelSpec,
            _hardware: &HardwareSpec,
            work: &PhaseWork,
        ) -> Result<PhaseResult, crate::performance::PerformanceError> {
            let latency_seconds = match work.phase {
                crate::performance::InferencePhase::Prefill => 0.05,
                crate::performance::InferencePhase::Decode => 0.02,
            };
            Ok(PhaseResult {
                phase: work.phase,
                fidelity: OracleFidelity::External,
                batch_size: work.batch_size,
                new_tokens: work.new_tokens,
                flops: work.new_tokens as f64 * 100.0,
                executed_flops: work.new_tokens as f64 * 100.0,
                tile_utilization: 1.0,
                weight_bytes: 1_000,
                activation_bytes: 0,
                kv_read_bytes: work.attention_token_pairs * 10,
                kv_write_bytes: work.new_tokens * 10,
                interchip_bytes: work.interchip_bytes,
                effective_compute_operations_per_second: 1.0e12,
                effective_memory_bandwidth_bytes_per_second: 1.0e12,
                compute_seconds: latency_seconds,
                memory_seconds: latency_seconds,
                launch_seconds: 0.0,
                latency_seconds,
                energy_joules: latency_seconds * 100.0,
                bottleneck: Bottleneck::Compute,
                actions: vec![],
            })
        }
    }

    fn model() -> ModelSpec {
        ModelSpec {
            model_id: "simulation-test".into(),
            model_revision: "test-fixture-v1".into(),
            architecture: ModelArchitecture::DenseDecoder,
            parameter_count: 100,
            layer_count: 2,
            hidden_size: 16,
            intermediate_size: 64,
            attention_head_count: 2,
            kv_head_count: 1,
            head_dimension: 8,
            vocabulary_size: 1_000,
            max_sequence_length: 1_024,
            weight_precision: Precision::Fp16,
            quantized_weight_storage: None,
            kv_precision: Precision::Fp16,
        }
    }

    fn hardware(memory_capacity_bytes: u64) -> HardwareSpec {
        HardwareSpec {
            name: "simulation-hardware".into(),
            fidelity: HardwareFidelity::Analytical,
            physical_device_count: 1,
            aggregate: Some(AggregateHardwareSpec {
                memory_capacity_bytes,
                memory_bandwidth_bytes_per_second: 1.0e12,
                compute_operations_per_second: 1.0e12,
                compute_efficiency: 1.0,
                memory_efficiency: 1.0,
                scale_up_bandwidth_bytes_per_second: 0.0,
                scale_up_latency_nanoseconds: 0.0,
                scale_up_energy_picojoules_per_byte: 0.0,
                idle_power_watts: 10.0,
                peak_power_watts: 100.0,
            }),
            design: None,
            accelerator_hourly_cost_usd: 1.0,
            host_hourly_cost_usd: 0.1,
        }
    }

    fn workload(prefix_cache_hit_ratio: f64) -> AgenticWorkloadSpec {
        AgenticWorkloadSpec {
            seed: 17,
            request_count: 4,
            arrival_rate_per_second: 1.0e9,
            request_classes: vec![RequestClass {
                name: "agent-turn".into(),
                share: 1.0,
                input_tokens: 100,
                output_tokens: 2,
                prefix_cache_hit_ratio,
            }],
        }
    }

    fn serving() -> ServingSpec {
        ServingSpec {
            max_batch_size: 1,
            prefill_chunk_tokens: 32,
            prefill_interleave_decode_steps: 8,
            kv_cache_memory_fraction: 0.8,
            max_concurrent_requests: 4,
            ttft_slo_milliseconds: 10.0,
            tpot_slo_milliseconds: 10.0,
        }
    }

    fn mapping() -> ExecutionMappingSpec {
        ExecutionMappingSpec {
            tensor_parallelism: 1,
            pipeline_parallelism: 1,
            data_parallelism: 1,
            prefill_decode_disaggregated: false,
        }
    }

    #[test]
    fn request_generation_is_reproducible_from_seed() {
        let workload = workload(0.25);

        assert_eq!(
            generate_requests(&workload).unwrap(),
            generate_requests(&workload).unwrap()
        );
        let mut changed = workload.clone();
        changed.seed += 1;
        assert_ne!(
            generate_requests(&workload).unwrap(),
            generate_requests(&changed).unwrap()
        );
    }

    #[test]
    fn prefix_reuse_and_chunking_reduce_prefill_work() {
        let simulator = ServingSimulator;
        let model = model();
        let hardware = hardware(1_000_000);
        let serving = serving();
        let without_cache = workload(0.0);
        let with_cache = workload(0.5);
        let without = simulator
            .run_input(
                SimulationInput {
                    model: &model,
                    workload: &without_cache,
                    hardware: &hardware,
                    mapping: &mapping(),
                    serving: &serving,
                },
                &FixedOracle,
            )
            .unwrap();
        let with = simulator
            .run_input(
                SimulationInput {
                    model: &model,
                    workload: &with_cache,
                    hardware: &hardware,
                    mapping: &mapping(),
                    serving: &serving,
                },
                &FixedOracle,
            )
            .unwrap();

        assert_eq!(without.prefill_tokens, 400);
        assert_eq!(with.prefill_tokens, 200);
        assert!(without.prefill.invocations > without.completed_requests);
        assert!(with.prefill.busy_seconds < without.prefill.busy_seconds);
    }

    #[test]
    fn queueing_is_reflected_in_latency_slos_and_goodput() {
        let simulator = ServingSimulator;
        let model = model();
        let workload = workload(0.0);
        let hardware = hardware(1_000_000);
        let serving = serving();
        let report = simulator
            .run_input(
                SimulationInput {
                    model: &model,
                    workload: &workload,
                    hardware: &hardware,
                    mapping: &mapping(),
                    serving: &serving,
                },
                &FixedOracle,
            )
            .unwrap();

        assert!(report.mean_queue_time_milliseconds > 0.0);
        assert!(report.mean_ttft_milliseconds > 10.0);
        assert!(report.slo_met_requests < report.completed_requests);
        assert!(report.goodput_requests_per_second < report.throughput_requests_per_second);
        assert!((report.total_energy_joules - 100.0 * report.total_busy_seconds).abs() < 1.0e-9);
    }

    #[test]
    fn a_request_that_cannot_fit_returns_a_typed_error() {
        let simulator = ServingSimulator;
        let model = model();
        let workload = workload(0.0);
        let hardware = hardware(1_000);
        let serving = serving();
        let error = simulator
            .run_input(
                SimulationInput {
                    model: &model,
                    workload: &workload,
                    hardware: &hardware,
                    mapping: &mapping(),
                    serving: &serving,
                },
                &FixedOracle,
            )
            .unwrap_err();

        assert!(matches!(
            error,
            SimulationError::InsufficientKvMemory { .. }
        ));
    }

    #[test]
    fn model_parallel_mapping_generates_interchip_activity() {
        let model = model();
        let workload = workload(0.5);
        let hardware = hardware(1_000_000);
        let serving = serving();
        let mut mapping = mapping();
        mapping.tensor_parallelism = 2;

        let report = ServingSimulator
            .run_input(
                SimulationInput {
                    model: &model,
                    workload: &workload,
                    hardware: &hardware,
                    mapping: &mapping,
                    serving: &serving,
                },
                &FixedOracle,
            )
            .unwrap();

        assert!(report.prefill.interchip_bytes > 0);
        assert!(report.decode.interchip_bytes > 0);
    }
}
