use crate::spec::{
    ContentId, ContentIdentityError, ExperimentSpec, HardwareSearchSpace, HardwareSpec,
    KernelSearchSpace, KernelSpec, MappingSearchSpace, OnChipMemoryKind, ValidationErrors,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use thiserror::Error;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct QualityScore {
    pub metric: String,
    pub score: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateEvaluation {
    pub quality_scores: Vec<QualityScore>,
    pub peak_memory_bytes: u64,
    pub p95_ttft_milliseconds: f64,
    pub p95_tpot_milliseconds: f64,
    pub input_price_per_million_tokens: f64,
    pub output_price_per_million_tokens: f64,
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[error("{message}")]
pub struct CandidateEvaluationError {
    pub message: String,
}

impl CandidateEvaluationError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

pub trait CandidateEvaluator {
    fn evaluate(
        &mut self,
        candidate: &ExperimentSpec,
    ) -> Result<CandidateEvaluation, CandidateEvaluationError>;
}

impl<F> CandidateEvaluator for F
where
    F: FnMut(&ExperimentSpec) -> Result<CandidateEvaluation, CandidateEvaluationError>,
{
    fn evaluate(
        &mut self,
        candidate: &ExperimentSpec,
    ) -> Result<CandidateEvaluation, CandidateEvaluationError> {
        self(candidate)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "constraint", rename_all = "snake_case")]
pub enum ConstraintViolation {
    MissingQuality {
        metric: String,
    },
    Quality {
        metric: String,
        score: f64,
        minimum_score: f64,
    },
    Memory {
        peak_bytes: u64,
        limit_bytes: u64,
    },
    Ttft {
        actual_milliseconds: f64,
        limit_milliseconds: f64,
    },
    Tpot {
        actual_milliseconds: f64,
        limit_milliseconds: f64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AgentPriceMix {
    pub input_token_fraction: f64,
    pub output_token_fraction: f64,
}

impl AgentPriceMix {
    pub fn from_spec(spec: &ExperimentSpec) -> Result<Self, SearchError> {
        spec.validate()?;
        let input_tokens: f64 = spec
            .workload
            .request_classes
            .iter()
            .map(|class| class.share * f64::from(class.input_tokens))
            .sum();
        let output_tokens: f64 = spec
            .workload
            .request_classes
            .iter()
            .map(|class| class.share * f64::from(class.output_tokens))
            .sum();
        let total_tokens = input_tokens + output_tokens;
        Ok(Self {
            input_token_fraction: input_tokens / total_tokens,
            output_token_fraction: output_tokens / total_tokens,
        })
    }

    pub fn weighted_price(&self, evaluation: &CandidateEvaluation) -> f64 {
        self.input_token_fraction * evaluation.input_price_per_million_tokens
            + self.output_token_fraction * evaluation.output_price_per_million_tokens
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateResult {
    pub id: ContentId,
    pub spec: ExperimentSpec,
    pub evaluation: CandidateEvaluation,
    pub weighted_price_per_million_tokens: f64,
    pub constraint_violations: Vec<ConstraintViolation>,
}

impl CandidateResult {
    pub fn is_feasible(&self) -> bool {
        self.constraint_violations.is_empty()
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AttributionComponent {
    pub candidate_id: ContentId,
    pub feasible: bool,
    pub standalone_weighted_price_per_million_tokens: f64,
    pub improvement_usd_per_million: f64,
    pub constraint_violations: Vec<ConstraintViolation>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SearchAttribution {
    pub baseline_weighted_price_per_million_tokens: f64,
    pub best_weighted_price_per_million_tokens: f64,
    pub model: AttributionComponent,
    pub kernel_mapping: AttributionComponent,
    pub hardware: AttributionComponent,
    pub serving: AttributionComponent,
    pub interaction_residual_usd_per_million: f64,
}

impl SearchAttribution {
    pub fn total_improvement_usd_per_million(&self) -> f64 {
        self.baseline_weighted_price_per_million_tokens
            - self.best_weighted_price_per_million_tokens
    }

    pub fn attributed_improvement_usd_per_million(&self) -> f64 {
        self.model.improvement_usd_per_million
            + self.kernel_mapping.improvement_usd_per_million
            + self.hardware.improvement_usd_per_million
            + self.serving.improvement_usd_per_million
            + self.interaction_residual_usd_per_million
    }

    pub fn reconciles(&self, tolerance_usd_per_million: f64) -> bool {
        (self.total_improvement_usd_per_million() - self.attributed_improvement_usd_per_million())
            .abs()
            <= tolerance_usd_per_million
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SearchReport {
    pub agent_mix: AgentPriceMix,
    pub baseline: CandidateResult,
    pub best: CandidateResult,
    pub ranked_candidates: Vec<CandidateResult>,
    pub infeasible_candidates: Vec<CandidateResult>,
    pub attribution: SearchAttribution,
}

#[derive(Debug, Error)]
pub enum SearchError {
    #[error("invalid experiment specification: {0}")]
    InvalidSpec(#[from] ValidationErrors),
    #[error("failed to identify a search candidate: {0}")]
    CandidateIdentity(#[from] ContentIdentityError),
    #[error("candidate {candidate_id} evaluation failed: {source}")]
    Evaluation {
        candidate_id: ContentId,
        #[source]
        source: CandidateEvaluationError,
    },
    #[error("candidate {candidate_id} returned an invalid {field}")]
    InvalidEvaluation {
        candidate_id: ContentId,
        field: &'static str,
    },
    #[error("hardware search requires a detailed hardware design")]
    HardwareSearchRequiresDetailedDesign,
    #[error("hardware search requires at least one on-chip memory tier")]
    MissingOnChipMemory,
    #[error("hardware search requires at least one off-chip memory tier")]
    MissingOffChipMemory,
    #[error("candidate {candidate_id} has no effective memory capacity")]
    MissingMemoryCapacity { candidate_id: ContentId },
    #[error("the search produced no feasible candidate")]
    NoFeasibleCandidates,
}

pub fn run_search<E>(
    baseline_spec: &ExperimentSpec,
    evaluator: &mut E,
) -> Result<SearchReport, SearchError>
where
    E: CandidateEvaluator + ?Sized,
{
    baseline_spec.validate()?;
    let agent_mix = AgentPriceMix::from_spec(baseline_spec)?;
    let candidates = expand_search_candidates(baseline_spec)?;
    let mut evaluated = BTreeMap::new();
    for candidate in candidates {
        evaluate_and_store(&candidate, evaluator, &agent_mix, &mut evaluated)?;
    }

    let baseline_id = baseline_spec.content_id()?;
    let baseline = evaluated
        .get(&baseline_id.to_hex())
        .cloned()
        .ok_or(SearchError::NoFeasibleCandidates)?;
    let mut ranked_candidates: Vec<_> = evaluated
        .values()
        .filter(|candidate| candidate.is_feasible())
        .cloned()
        .collect();
    ranked_candidates.sort_by(compare_candidates);
    let best = ranked_candidates
        .first()
        .cloned()
        .ok_or(SearchError::NoFeasibleCandidates)?;
    let mut infeasible_candidates: Vec<_> = evaluated
        .values()
        .filter(|candidate| !candidate.is_feasible())
        .cloned()
        .collect();
    infeasible_candidates.sort_by(compare_candidates);
    let attribution = calculate_attribution(
        baseline_spec,
        &baseline,
        &best,
        evaluator,
        &agent_mix,
        &mut evaluated,
    )?;

    Ok(SearchReport {
        agent_mix,
        baseline,
        best,
        ranked_candidates,
        infeasible_candidates,
        attribution,
    })
}

fn compare_candidates(left: &CandidateResult, right: &CandidateResult) -> std::cmp::Ordering {
    left.weighted_price_per_million_tokens
        .total_cmp(&right.weighted_price_per_million_tokens)
        .then_with(|| {
            left.evaluation
                .input_price_per_million_tokens
                .total_cmp(&right.evaluation.input_price_per_million_tokens)
        })
        .then_with(|| {
            left.evaluation
                .output_price_per_million_tokens
                .total_cmp(&right.evaluation.output_price_per_million_tokens)
        })
        .then_with(|| left.id.as_bytes().cmp(right.id.as_bytes()))
}

pub fn expand_search_candidates(
    baseline: &ExperimentSpec,
) -> Result<Vec<ExperimentSpec>, SearchError> {
    baseline.validate()?;
    let kernels = expand_kernels(&baseline.kernel, baseline.search_space.kernel.as_ref());
    let hardware = expand_hardware(&baseline.hardware, baseline.search_space.hardware.as_ref())?;
    let mappings = expand_mappings(&baseline.mapping, baseline.search_space.mapping.as_ref());
    let mut unique = BTreeMap::new();
    insert_unique(&mut unique, baseline.clone())?;

    for weight_precision in &baseline.search_space.weight_precisions {
        for kv_precision in &baseline.search_space.kv_precisions {
            for max_batch_size in &baseline.search_space.max_batch_sizes {
                for prefill_chunk_tokens in &baseline.search_space.prefill_chunk_tokens {
                    for kernel in &kernels {
                        for candidate_hardware in &hardware {
                            for mapping in &mappings {
                                let mut candidate = baseline.clone();
                                candidate.model.weight_precision = *weight_precision;
                                candidate.model.quantized_weight_storage =
                                    if weight_precision.bits() < 8 {
                                        baseline.search_space.quantized_weight_storage
                                    } else {
                                        None
                                    };
                                candidate.model.kv_precision = *kv_precision;
                                candidate.serving.max_batch_size = *max_batch_size;
                                candidate.serving.prefill_chunk_tokens = *prefill_chunk_tokens;
                                candidate.kernel = kernel.clone();
                                candidate.hardware = candidate_hardware.clone();
                                candidate.mapping = mapping.clone();
                                insert_unique(&mut unique, candidate)?;
                            }
                        }
                    }
                }
            }
        }
    }

    Ok(unique.into_values().collect())
}

pub fn evaluate_constraints(
    candidate: &ExperimentSpec,
    evaluation: &CandidateEvaluation,
) -> Result<Vec<ConstraintViolation>, SearchError> {
    let candidate_id = candidate.content_id()?;
    validate_evaluation(candidate_id, evaluation)?;
    constraint_violations(candidate, candidate_id, evaluation)
}

fn expand_kernels(baseline: &KernelSpec, space: Option<&KernelSearchSpace>) -> Vec<KernelSpec> {
    let Some(space) = space else {
        return vec![baseline.clone()];
    };
    let mut kernels = Vec::new();
    for attention in &space.attention_kernels {
        for fusion in &space.fusion_policies {
            for tile_rows in &space.tile_rows {
                for tile_columns in &space.tile_columns {
                    let mut kernel = baseline.clone();
                    kernel.attention = *attention;
                    kernel.fusion = *fusion;
                    kernel.tile_rows = *tile_rows;
                    kernel.tile_columns = *tile_columns;
                    kernels.push(kernel);
                }
            }
        }
    }
    kernels
}

fn expand_hardware(
    baseline: &HardwareSpec,
    space: Option<&HardwareSearchSpace>,
) -> Result<Vec<HardwareSpec>, SearchError> {
    let Some(space) = space else {
        return Ok(vec![baseline.clone()]);
    };
    let design = baseline
        .design
        .as_ref()
        .ok_or(SearchError::HardwareSearchRequiresDetailedDesign)?;
    let on_chip_index = design
        .on_chip_memory
        .iter()
        .position(|tier| tier.kind == OnChipMemoryKind::Sram)
        .or_else(|| (!design.on_chip_memory.is_empty()).then_some(0))
        .ok_or(SearchError::MissingOnChipMemory)?;
    if design.off_chip_memory.is_empty() {
        return Err(SearchError::MissingOffChipMemory);
    }
    let mut candidates = Vec::new();
    for array_count in &space.compute_array_counts {
        for on_chip_capacity in &space.on_chip_memory_capacities_bytes {
            for off_chip_bandwidth in &space.off_chip_memory_bandwidth_bytes_per_second {
                let mut hardware = baseline.clone();
                let candidate_design = hardware
                    .design
                    .as_mut()
                    .ok_or(SearchError::HardwareSearchRequiresDetailedDesign)?;
                candidate_design.compute.array_count = *array_count;
                candidate_design.on_chip_memory[on_chip_index].capacity_bytes = *on_chip_capacity;
                candidate_design.off_chip_memory[0].bandwidth_bytes_per_second =
                    *off_chip_bandwidth;
                candidates.push(hardware);
            }
        }
    }
    Ok(candidates)
}

fn expand_mappings(
    baseline: &crate::spec::ExecutionMappingSpec,
    space: Option<&MappingSearchSpace>,
) -> Vec<crate::spec::ExecutionMappingSpec> {
    let Some(space) = space else {
        return vec![baseline.clone()];
    };
    let mut mappings = Vec::new();
    for tensor_parallelism in &space.tensor_parallelism {
        for pipeline_parallelism in &space.pipeline_parallelism {
            let mut mapping = baseline.clone();
            mapping.tensor_parallelism = *tensor_parallelism;
            mapping.pipeline_parallelism = *pipeline_parallelism;
            mappings.push(mapping);
        }
    }
    mappings
}

fn insert_unique(
    unique: &mut BTreeMap<String, ExperimentSpec>,
    candidate: ExperimentSpec,
) -> Result<(), SearchError> {
    let id = candidate.content_id()?;
    unique.entry(id.to_hex()).or_insert(candidate);
    Ok(())
}

fn evaluate_and_store<E>(
    candidate: &ExperimentSpec,
    evaluator: &mut E,
    agent_mix: &AgentPriceMix,
    evaluated: &mut BTreeMap<String, CandidateResult>,
) -> Result<CandidateResult, SearchError>
where
    E: CandidateEvaluator + ?Sized,
{
    let id = candidate.content_id()?;
    let key = id.to_hex();
    if let Some(result) = evaluated.get(&key) {
        return Ok(result.clone());
    }
    let evaluation = evaluator
        .evaluate(candidate)
        .map_err(|source| SearchError::Evaluation {
            candidate_id: id,
            source,
        })?;
    validate_evaluation(id, &evaluation)?;
    let result = CandidateResult {
        id,
        spec: candidate.clone(),
        weighted_price_per_million_tokens: agent_mix.weighted_price(&evaluation),
        constraint_violations: constraint_violations(candidate, id, &evaluation)?,
        evaluation,
    };
    evaluated.insert(key, result.clone());
    Ok(result)
}

fn validate_evaluation(
    candidate_id: ContentId,
    evaluation: &CandidateEvaluation,
) -> Result<(), SearchError> {
    for (field, value) in [
        ("p95 TTFT", evaluation.p95_ttft_milliseconds),
        ("p95 TPOT", evaluation.p95_tpot_milliseconds),
        (
            "input price per million tokens",
            evaluation.input_price_per_million_tokens,
        ),
        (
            "output price per million tokens",
            evaluation.output_price_per_million_tokens,
        ),
    ] {
        if !value.is_finite() || value < 0.0 {
            return Err(SearchError::InvalidEvaluation {
                candidate_id,
                field,
            });
        }
    }
    if evaluation
        .quality_scores
        .iter()
        .any(|quality| !quality.score.is_finite())
    {
        return Err(SearchError::InvalidEvaluation {
            candidate_id,
            field: "quality score",
        });
    }
    Ok(())
}

fn constraint_violations(
    candidate: &ExperimentSpec,
    candidate_id: ContentId,
    evaluation: &CandidateEvaluation,
) -> Result<Vec<ConstraintViolation>, SearchError> {
    let mut violations = Vec::new();
    for constraint in &candidate.quality_constraints {
        match evaluation
            .quality_scores
            .iter()
            .find(|quality| quality.metric == constraint.metric)
        {
            Some(quality) if quality.score < constraint.minimum_score => {
                violations.push(ConstraintViolation::Quality {
                    metric: constraint.metric.clone(),
                    score: quality.score,
                    minimum_score: constraint.minimum_score,
                });
            }
            Some(_) => {}
            None => violations.push(ConstraintViolation::MissingQuality {
                metric: constraint.metric.clone(),
            }),
        }
    }
    let memory_capacity = candidate
        .hardware
        .effective_memory_capacity_bytes()
        .ok_or(SearchError::MissingMemoryCapacity { candidate_id })?;
    let limit_bytes = (memory_capacity as f64 * candidate.serving.kv_cache_memory_fraction)
        .floor()
        .min(u64::MAX as f64) as u64;
    if evaluation.peak_memory_bytes > limit_bytes {
        violations.push(ConstraintViolation::Memory {
            peak_bytes: evaluation.peak_memory_bytes,
            limit_bytes,
        });
    }
    if evaluation.p95_ttft_milliseconds > candidate.serving.ttft_slo_milliseconds {
        violations.push(ConstraintViolation::Ttft {
            actual_milliseconds: evaluation.p95_ttft_milliseconds,
            limit_milliseconds: candidate.serving.ttft_slo_milliseconds,
        });
    }
    if evaluation.p95_tpot_milliseconds > candidate.serving.tpot_slo_milliseconds {
        violations.push(ConstraintViolation::Tpot {
            actual_milliseconds: evaluation.p95_tpot_milliseconds,
            limit_milliseconds: candidate.serving.tpot_slo_milliseconds,
        });
    }
    Ok(violations)
}

fn calculate_attribution<E>(
    baseline_spec: &ExperimentSpec,
    baseline: &CandidateResult,
    best: &CandidateResult,
    evaluator: &mut E,
    agent_mix: &AgentPriceMix,
    evaluated: &mut BTreeMap<String, CandidateResult>,
) -> Result<SearchAttribution, SearchError>
where
    E: CandidateEvaluator + ?Sized,
{
    let mut model_spec = baseline_spec.clone();
    model_spec.model.weight_precision = best.spec.model.weight_precision;
    model_spec.model.quantized_weight_storage = best.spec.model.quantized_weight_storage;
    model_spec.model.kv_precision = best.spec.model.kv_precision;

    let mut kernel_mapping_spec = baseline_spec.clone();
    kernel_mapping_spec.kernel = best.spec.kernel.clone();
    kernel_mapping_spec.mapping = best.spec.mapping.clone();

    let mut hardware_spec = baseline_spec.clone();
    hardware_spec.hardware = best.spec.hardware.clone();

    let mut serving_spec = baseline_spec.clone();
    serving_spec.serving.max_batch_size = best.spec.serving.max_batch_size;
    serving_spec.serving.prefill_chunk_tokens = best.spec.serving.prefill_chunk_tokens;

    let model = attribution_component(
        model_spec,
        baseline.weighted_price_per_million_tokens,
        evaluator,
        agent_mix,
        evaluated,
    )?;
    let kernel_mapping = attribution_component(
        kernel_mapping_spec,
        baseline.weighted_price_per_million_tokens,
        evaluator,
        agent_mix,
        evaluated,
    )?;
    let hardware = attribution_component(
        hardware_spec,
        baseline.weighted_price_per_million_tokens,
        evaluator,
        agent_mix,
        evaluated,
    )?;
    let serving = attribution_component(
        serving_spec,
        baseline.weighted_price_per_million_tokens,
        evaluator,
        agent_mix,
        evaluated,
    )?;
    let total_improvement =
        baseline.weighted_price_per_million_tokens - best.weighted_price_per_million_tokens;
    let standalone_improvement = model.improvement_usd_per_million
        + kernel_mapping.improvement_usd_per_million
        + hardware.improvement_usd_per_million
        + serving.improvement_usd_per_million;

    Ok(SearchAttribution {
        baseline_weighted_price_per_million_tokens: baseline.weighted_price_per_million_tokens,
        best_weighted_price_per_million_tokens: best.weighted_price_per_million_tokens,
        model,
        kernel_mapping,
        hardware,
        serving,
        interaction_residual_usd_per_million: total_improvement - standalone_improvement,
    })
}

fn attribution_component<E>(
    spec: ExperimentSpec,
    baseline_weighted_price: f64,
    evaluator: &mut E,
    agent_mix: &AgentPriceMix,
    evaluated: &mut BTreeMap<String, CandidateResult>,
) -> Result<AttributionComponent, SearchError>
where
    E: CandidateEvaluator + ?Sized,
{
    let result = evaluate_and_store(&spec, evaluator, agent_mix, evaluated)?;
    let feasible = result.is_feasible();
    Ok(AttributionComponent {
        candidate_id: result.id,
        feasible,
        standalone_weighted_price_per_million_tokens: result.weighted_price_per_million_tokens,
        improvement_usd_per_million: if feasible {
            baseline_weighted_price - result.weighted_price_per_million_tokens
        } else {
            0.0
        },
        constraint_violations: result.constraint_violations,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::{
        AgenticWorkloadSpec, AggregateHardwareSpec, AttentionKernel, CURRENT_SCHEMA_VERSION,
        EconomicsSpec, ExecutionMappingSpec, ExperimentSpec, FusionPolicy, HardwareFidelity,
        HardwareSpec, KernelBackend, KernelSpec, ModelArchitecture, ModelSpec, Precision,
        QualityConstraint, RequestClass, SearchSpace, ServingSpec,
    };

    #[test]
    fn int4_search_candidates_keep_the_declared_groupwise_storage() {
        let candidates = expand_search_candidates(&base_spec()).unwrap();
        let int4 = candidates
            .iter()
            .find(|candidate| candidate.model.weight_precision == Precision::Int4)
            .unwrap();
        let storage = int4.model.quantized_weight_storage.as_ref().unwrap();

        assert_eq!(storage.payload_bits_per_quantized_weight(), Some(4.125));
        assert!(int4.model.effective_weight_storage_bits().unwrap() > 4.0);
    }

    #[test]
    fn infeasible_candidates_are_retained_with_constraint_violations() {
        let mut spec = base_spec();
        spec.search_space.max_batch_sizes = vec![4, 64];
        spec.search_space.prefill_chunk_tokens = vec![4, 8];
        let mut evaluator = |candidate: &ExperimentSpec| {
            Ok(CandidateEvaluation {
                quality_scores: vec![QualityScore {
                    metric: "task-success".into(),
                    score: 0.8,
                }],
                peak_memory_bytes: if candidate.serving.max_batch_size == 64 {
                    900
                } else {
                    500
                },
                p95_ttft_milliseconds: if candidate.serving.prefill_chunk_tokens == 8 {
                    120.0
                } else {
                    80.0
                },
                p95_tpot_milliseconds: 20.0,
                input_price_per_million_tokens: 1.0,
                output_price_per_million_tokens: 2.0,
            })
        };

        let report = run_search(&spec, &mut evaluator).unwrap();

        assert!(!report.infeasible_candidates.is_empty());
        assert!(report.infeasible_candidates.iter().any(|candidate| {
            candidate
                .constraint_violations
                .iter()
                .any(|violation| matches!(violation, ConstraintViolation::Memory { .. }))
        }));
        assert!(report.infeasible_candidates.iter().any(|candidate| {
            candidate
                .constraint_violations
                .iter()
                .any(|violation| matches!(violation, ConstraintViolation::Ttft { .. }))
        }));
        assert!(
            report
                .ranked_candidates
                .iter()
                .all(|candidate| candidate.constraint_violations.is_empty())
        );
    }

    #[test]
    fn ranking_is_deterministic_and_uses_the_canonical_agent_mix() {
        let spec = base_spec();
        let evaluator = |candidate: &ExperimentSpec| {
            let input_price = f64::from(candidate.model.weight_precision.bits());
            let output_price = f64::from(candidate.model.kv_precision.bits())
                + 1.0 / f64::from(candidate.serving.max_batch_size);
            Ok(CandidateEvaluation {
                quality_scores: vec![QualityScore {
                    metric: "task-success".into(),
                    score: 0.8,
                }],
                peak_memory_bytes: 500,
                p95_ttft_milliseconds: 80.0,
                p95_tpot_milliseconds: 20.0,
                input_price_per_million_tokens: input_price,
                output_price_per_million_tokens: output_price,
            })
        };
        let mut first_evaluator = evaluator;
        let mut second_evaluator = evaluator;

        let first = run_search(&spec, &mut first_evaluator).unwrap();
        let second = run_search(&spec, &mut second_evaluator).unwrap();

        let first_ids: Vec<_> = first
            .ranked_candidates
            .iter()
            .map(|candidate| candidate.id)
            .collect();
        let second_ids: Vec<_> = second
            .ranked_candidates
            .iter()
            .map(|candidate| candidate.id)
            .collect();
        assert_eq!(first_ids, second_ids);
        assert_eq!(first.best.id, second.best.id);
        assert_eq!(first.agent_mix.input_token_fraction, 0.8);
        assert_eq!(first.agent_mix.output_token_fraction, 0.2);
        assert!(
            first
                .ranked_candidates
                .windows(2)
                .all(|pair| pair[0].weighted_price_per_million_tokens
                    <= pair[1].weighted_price_per_million_tokens)
        );
    }

    #[test]
    fn attribution_reconciles_axis_effects_and_interactions() {
        let mut spec = base_spec();
        spec.model.weight_precision = Precision::Fp16;
        spec.model.quantized_weight_storage = None;
        spec.search_space.weight_precisions = vec![Precision::Int8];
        spec.search_space.kv_precisions = vec![Precision::Fp16];
        spec.search_space.max_batch_sizes = vec![4];
        spec.search_space.prefill_chunk_tokens = vec![8];
        let mut evaluator = |candidate: &ExperimentSpec| {
            let model_changed = candidate.model.weight_precision == Precision::Int8;
            let serving_changed = candidate.serving.max_batch_size == 4;
            let mut improvement = 0.0;
            if model_changed {
                improvement += 2.0;
            }
            if serving_changed {
                improvement += 3.0;
            }
            if model_changed && serving_changed {
                improvement += 1.0;
            }
            Ok(CandidateEvaluation {
                quality_scores: vec![QualityScore {
                    metric: "task-success".into(),
                    score: 0.8,
                }],
                peak_memory_bytes: 500,
                p95_ttft_milliseconds: 80.0,
                p95_tpot_milliseconds: 20.0,
                input_price_per_million_tokens: 10.0 - improvement,
                output_price_per_million_tokens: 20.0 - improvement,
            })
        };

        let report = run_search(&spec, &mut evaluator).unwrap();

        assert!((report.attribution.model.improvement_usd_per_million - 2.0).abs() < 1e-12);
        assert!((report.attribution.serving.improvement_usd_per_million - 3.0).abs() < 1e-12);
        assert!((report.attribution.interaction_residual_usd_per_million - 1.0).abs() < 1e-12);
        assert!(report.attribution.reconciles(1e-12));
        assert_eq!(report.baseline.spec.model.weight_precision, Precision::Fp16);
        assert_eq!(report.best.spec.model.weight_precision, Precision::Int8);
    }

    fn base_spec() -> ExperimentSpec {
        ExperimentSpec {
            schema_version: CURRENT_SCHEMA_VERSION,
            experiment_name: "search-test".into(),
            model: ModelSpec {
                model_id: "test-model".into(),
                model_revision: "test-fixture-v1".into(),
                architecture: ModelArchitecture::DenseDecoder,
                parameter_count: 100,
                layer_count: 2,
                hidden_size: 8,
                intermediate_size: 16,
                attention_head_count: 2,
                kv_head_count: 1,
                head_dimension: 4,
                vocabulary_size: 32,
                max_sequence_length: 32,
                weight_precision: Precision::Fp16,
                quantized_weight_storage: None,
                kv_precision: Precision::Fp16,
            },
            quality_suite_id: "test-suite-v1".into(),
            workload: AgenticWorkloadSpec {
                seed: 7,
                request_count: 100,
                arrival_rate_per_second: 1.0,
                request_classes: vec![RequestClass {
                    name: "agent".into(),
                    share: 1.0,
                    input_tokens: 8,
                    output_tokens: 2,
                    prefix_cache_hit_ratio: 0.0,
                }],
            },
            hardware: HardwareSpec {
                name: "test-gpu".into(),
                fidelity: HardwareFidelity::Analytical,
                physical_device_count: 1,
                aggregate: Some(AggregateHardwareSpec {
                    memory_capacity_bytes: 1_000,
                    memory_bandwidth_bytes_per_second: 1_000.0,
                    compute_operations_per_second: 1_000.0,
                    compute_efficiency: 1.0,
                    memory_efficiency: 1.0,
                    scale_up_bandwidth_bytes_per_second: 0.0,
                    scale_up_latency_nanoseconds: 0.0,
                    scale_up_energy_picojoules_per_byte: 0.0,
                    idle_power_watts: 10.0,
                    peak_power_watts: 20.0,
                }),
                design: None,
                accelerator_hourly_cost_usd: 1.0,
                host_hourly_cost_usd: 0.1,
            },
            kernel: KernelSpec {
                backend: KernelBackend::Rust,
                attention: AttentionKernel::Paged,
                fusion: FusionPolicy::AttentionAndMlp,
                tile_rows: 8,
                tile_columns: 8,
            },
            mapping: ExecutionMappingSpec {
                tensor_parallelism: 1,
                pipeline_parallelism: 1,
                data_parallelism: 1,
                prefill_decode_disaggregated: false,
            },
            serving: ServingSpec {
                max_batch_size: 1,
                prefill_chunk_tokens: 8,
                prefill_interleave_decode_steps: 8,
                kv_cache_memory_fraction: 0.8,
                max_concurrent_requests: 8,
                ttft_slo_milliseconds: 100.0,
                tpot_slo_milliseconds: 50.0,
            },
            economics: EconomicsSpec {
                electricity_usd_per_kwh: 0.1,
                power_usage_effectiveness: 1.2,
                target_gross_margin: 0.5,
                provider_overhead_usd_per_hour: None,
            },
            quality_constraints: vec![QualityConstraint {
                metric: "task-success".into(),
                baseline_score: 0.8,
                minimum_score: 0.79,
            }],
            search_space: SearchSpace {
                weight_precisions: vec![Precision::Int4, Precision::Int8],
                quantized_weight_storage: Some(
                    crate::spec::QuantizedWeightStorageSpec::grouped_all(128, 4, 16, 16, 0),
                ),
                kv_precisions: vec![Precision::Fp8, Precision::Fp16],
                max_batch_sizes: vec![4, 1],
                prefill_chunk_tokens: vec![8, 4],
                kernel: None,
                hardware: None,
                mapping: None,
            },
        }
    }
}
