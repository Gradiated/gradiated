use std::collections::BTreeSet;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use clap::{Parser, Subcommand, ValueEnum};
use foundry_core::action_ledger::ActionLedger;
use foundry_core::analysis::{DecisionMetadata, compare_studies, evaluate_study_slos};
use foundry_core::artifact::{Artifact, ArtifactId, ArtifactKind, ArtifactStore, Provenance};
use foundry_core::attribution::{FactorialObservation, shapley_attribution};
use foundry_core::calibration::{CalibrationRequest, calibrate};
use foundry_core::capacity::plan_capacity;
use foundry_core::chakra_export::ChakraExporter;
use foundry_core::claim_composition::{CompositionRequest, evaluate_claim_composition};
use foundry_core::codesign::{ModelVariant, QualityEvidence};
use foundry_core::deployment_screen::{
    DeploymentScreenReport, DeploymentScreenRequest, evaluate_deployment_screen,
};
use foundry_core::economic_frontier::{EconomicFrontierRequest, evaluate_economic_frontier};
use foundry_core::economics::ServerTcoInputs;
use foundry_core::experiment::{CostChoice, ExperimentRunner, OracleChoice, RunOptions};
use foundry_core::external::{ExternalPerformanceInput, ExternalProcessAdapter, ExternalToolSpec};
use foundry_core::glm_agentic_mapping::{
    GlmAgenticMappingInputs, GlmAgenticMappingRequest, GlmAgenticSourceFileHashes,
    evaluate_glm_agentic_mapping_screen,
};
use foundry_core::glm_decode::{
    GlmDecodeLoweringReport, GlmDecodeLoweringRequest, evaluate_glm_decode_lowering,
};
use foundry_core::glm_dsa::{GlmDsaSweepRequest, evaluate_glm_dsa_sweep};
use foundry_core::glm_mapping_context_frontier::{
    GlmMappingContextFrontierRequest, evaluate_glm_mapping_context_frontier,
};
use foundry_core::glm_moe_route::{GlmMoeRouteRequest, evaluate_glm_moe_routes};
use foundry_core::glm_parallel_mapping::{
    GlmParallelMappingRequest, evaluate_glm_parallel_mapping,
};
use foundry_core::glm_pd_serving::{GlmPdServingRequest, evaluate_glm_pd_serving};
use foundry_core::glm_storage::{
    GlmStorageEnvelopeReport, GlmStorageEnvelopeRequest, evaluate_glm_storage_envelope,
};
use foundry_core::group::HardwareGroupSpec;
use foundry_core::kernel::KernelProblem;
use foundry_core::ledger_roofline::{
    LedgerRooflineHardwarePlan, LedgerRooflineReport, evaluate_ledger_roofline,
};
use foundry_core::ledger_serving::{
    LEDGER_SERVING_REQUEST_SCHEMA_VERSION, LedgerServingReport, LedgerServingSimulationRequest,
    simulate_exact_ledger_serving,
};
use foundry_core::mtp::{GlmMtpSweepRequest, evaluate_glm_mtp_sweep};
use foundry_core::public_agentic_proxy::{
    PublicAgenticProxyReport, PublicAgenticProxyRequest, generate_public_agentic_proxy,
};
use foundry_core::qwen_int4_kernel::{
    QwenInt4Aarch64NeonRequest, QwenInt4BatchFrontierRequest, QwenInt4KernelSmokeRequest,
    run_qwen_int4_aarch64_neon, run_qwen_int4_batch_frontier, run_qwen_int4_kernel_smoke,
};
use foundry_core::residency_frontier::{
    GlmResidencyFrontierRequest, evaluate_glm_residency_frontier,
};
use foundry_core::sensitivity::{SensitivityRequest, analyze_codesign_sensitivity};
use foundry_core::serving_benchmark::{
    MeasuredServingBenchmarkRequest, evaluate_measured_serving_benchmark,
};
use foundry_core::sizing::{HardwareSizer, HardwareSizingConstraints};
use foundry_core::spec::{ExperimentSpec, KernelSpec};
use foundry_core::study::{CoDesignStudyReport, StudyOverrides, run_codesign_study_with_overrides};
use foundry_core::tiered_cache::{GlmTieredCacheRequest, evaluate_glm_tiered_cache};
use foundry_core::timeloop_export::TimeloopProblemExporter;
use foundry_core::vllm_serving::{VllmServingImportManifest, import_vllm_serving_benchmark};
use foundry_core::workload::{CanonicalTraceV2, WorkloadContractV2};

#[derive(Debug, Parser)]
#[command(
    name = "foundry",
    version,
    about = "Model-specific inference co-design"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Validate {
        spec: PathBuf,
    },
    Simulate {
        spec: PathBuf,
        #[arg(long, value_enum, default_value_t = OracleArg::Auto)]
        oracle: OracleArg,
        #[arg(long)]
        server_tco: Option<PathBuf>,
        #[arg(long)]
        hardware_group: Option<PathBuf>,
        #[arg(long)]
        quality_evidence: Option<PathBuf>,
        #[arg(long)]
        artifact_dir: Option<PathBuf>,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    CapacityPlan {
        spec: PathBuf,
        #[arg(long, default_value_t = 128)]
        maximum_replicas: u32,
        #[arg(long, value_enum, default_value_t = OracleArg::Auto)]
        oracle: OracleArg,
        #[arg(long)]
        server_tco: Option<PathBuf>,
        #[arg(long)]
        hardware_group: Option<PathBuf>,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    SizeHardware {
        spec: PathBuf,
        #[arg(long)]
        constraints: Option<PathBuf>,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    CodesignStudy {
        spec: PathBuf,
        #[arg(long)]
        constraints: PathBuf,
        #[arg(long)]
        model_variant: Vec<PathBuf>,
        #[arg(long)]
        kernel_spec: Option<PathBuf>,
        #[arg(long)]
        server_tco: Option<PathBuf>,
        #[arg(long, value_enum, default_value_t = OracleArg::Auto)]
        oracle: OracleArg,
        #[arg(long, default_value_t = 128)]
        maximum_replicas: u32,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    CompareStudies {
        baseline: PathBuf,
        candidate: PathBuf,
        metadata: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    AttributeFactorial {
        manifest: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    Sensitivity {
        study: PathBuf,
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    ExternalRun {
        tool: PathBuf,
        input: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    ClassSlo {
        study: PathBuf,
        contract: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    PublicAgenticProxy {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    Calibrate {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    ServingBenchmark {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    ImportVllmServing {
        artifact: PathBuf,
        trace: PathBuf,
        manifest: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmStorageEnvelope {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmResidencyFrontier {
        request: PathBuf,
        storage: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmParallelMapping {
        request: PathBuf,
        storage: PathBuf,
        route: PathBuf,
        dsa: PathBuf,
        lowering_request: PathBuf,
        lowering: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmMappingContextFrontier {
        request: PathBuf,
        storage: PathBuf,
        mapping_16k: PathBuf,
        mapping_90k: PathBuf,
        lowering_16k: PathBuf,
        lowering_90k: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmAgenticMappingScreen {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmMoeRoute {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmMtpSweep {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmDsaSweep {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmDecodeLower {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmPdServing {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    QwenInt4KernelSmoke {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    QwenInt4BatchFrontier {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    QwenInt4Aarch64Neon {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    TimeloopProblemExport {
        problem: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
        #[arg(long)]
        problem_yaml: Option<PathBuf>,
    },
    ClaimComposition {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    DeploymentScreen {
        request: PathBuf,
        storage: PathBuf,
        roofline: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    EconomicFrontier {
        request: PathBuf,
        source_screen: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    InspectActionLedger {
        ledger: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    GlmTieredCache {
        request: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    LedgerRoofline {
        ledger: PathBuf,
        hardware_plan: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    LedgerServingExact {
        manifest: PathBuf,
        #[arg(long)]
        output: Option<PathBuf>,
    },
    ExportChakra {
        ledger: PathBuf,
        output: PathBuf,
        #[arg(long)]
        manifest: PathBuf,
    },
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, ValueEnum)]
enum OracleArg {
    #[default]
    Auto,
    Roofline,
    TensorTile,
}

impl From<OracleArg> for OracleChoice {
    fn from(value: OracleArg) -> Self {
        match value {
            OracleArg::Auto => Self::Auto,
            OracleArg::Roofline => Self::Roofline,
            OracleArg::TensorTile => Self::TensorTile,
        }
    }
}

fn main() -> Result<()> {
    run(Cli::parse())
}

fn run(cli: Cli) -> Result<()> {
    match cli.command {
        Command::Validate { spec } => {
            let spec = read_json::<ExperimentSpec>(&spec)?;
            spec.validate()
                .map_err(anyhow::Error::new)
                .context("experiment specification is invalid")?;
            let output = serde_json::json!({
                "valid": true,
                "content_id": spec.content_id()?.to_hex(),
                "experiment_name": spec.experiment_name,
                "model_id": spec.model.model_id,
                "hardware": spec.hardware.name,
            });
            write_json(&output, None)
        }
        Command::Simulate {
            spec,
            oracle,
            server_tco,
            hardware_group,
            quality_evidence,
            artifact_dir,
            output,
        } => {
            let mut spec = read_json::<ExperimentSpec>(&spec)?;
            if let Some(path) = hardware_group {
                spec = read_json::<HardwareGroupSpec>(&path)?.apply(&spec)?;
            }
            let cost = match server_tco {
                Some(path) => CostChoice::CustomSilicon(read_json::<ServerTcoInputs>(&path)?),
                None => CostChoice::KnownHourly,
            };
            let quality = match quality_evidence {
                Some(path) => read_json::<QualityEvidence>(&path)?,
                None => QualityEvidence::Unvalidated,
            };
            let report = ExperimentRunner.run(
                &spec,
                &RunOptions {
                    oracle: oracle.into(),
                    cost,
                    quality,
                    quality_variant: None,
                },
            )?;
            let artifact_id = if let Some(root) = artifact_dir {
                let store = ArtifactStore::new(root);
                let spec_id = store.put(&Artifact {
                    schema_version: 1,
                    kind: ArtifactKind::ExperimentSpec,
                    provenance: provenance(Vec::new()),
                    payload: spec,
                })?;
                Some(
                    store
                        .put(&Artifact {
                            schema_version: 1,
                            kind: ArtifactKind::ExperimentReport,
                            provenance: provenance(vec![spec_id]),
                            payload: report.clone(),
                        })?
                        .as_str()
                        .to_owned(),
                )
            } else {
                None
            };
            let envelope = serde_json::json!({
                "artifact_id": artifact_id,
                "report": report,
            });
            write_json(&envelope, output.as_deref())
        }
        Command::CapacityPlan {
            spec,
            maximum_replicas,
            oracle,
            server_tco,
            hardware_group,
            output,
        } => {
            let mut spec = read_json::<ExperimentSpec>(&spec)?;
            if let Some(path) = hardware_group {
                spec = read_json::<HardwareGroupSpec>(&path)?.apply(&spec)?;
            }
            let cost = match server_tco {
                Some(path) => CostChoice::CustomSilicon(read_json::<ServerTcoInputs>(&path)?),
                None => CostChoice::KnownHourly,
            };
            let plan = plan_capacity(
                &spec,
                &RunOptions {
                    oracle: oracle.into(),
                    cost,
                    quality: QualityEvidence::Unvalidated,
                    quality_variant: None,
                },
                maximum_replicas,
            )?;
            write_json(&plan, output.as_deref())
        }
        Command::SizeHardware {
            spec,
            constraints,
            output,
        } => {
            let spec = read_json::<ExperimentSpec>(&spec)?;
            let constraints = match constraints {
                Some(path) => read_json::<HardwareSizingConstraints>(&path)?,
                None => HardwareSizingConstraints::default(),
            };
            let report = HardwareSizer.synthesize(&spec.model, &constraints)?;
            write_json(&report, output.as_deref())
        }
        Command::CodesignStudy {
            spec,
            constraints,
            model_variant,
            kernel_spec,
            server_tco,
            oracle,
            maximum_replicas,
            output,
        } => {
            let spec = read_json::<ExperimentSpec>(&spec)?;
            let constraints = read_json::<HardwareSizingConstraints>(&constraints)?;
            let variants = model_variant
                .iter()
                .map(|path| read_json::<ModelVariant>(path))
                .collect::<Result<Vec<_>>>()?;
            let variant = compose_variants(variants);
            let kernel = kernel_spec
                .as_deref()
                .map(read_json::<KernelSpec>)
                .transpose()?;
            let cost = match server_tco {
                Some(path) => CostChoice::CustomSilicon(read_json::<ServerTcoInputs>(&path)?),
                None => CostChoice::KnownHourly,
            };
            let report = run_codesign_study_with_overrides(
                &spec,
                variant.as_ref(),
                &constraints,
                &RunOptions {
                    oracle: oracle.into(),
                    cost,
                    quality: QualityEvidence::Unvalidated,
                    quality_variant: None,
                },
                maximum_replicas,
                &StudyOverrides { kernel },
            )?;
            write_json(&report, output.as_deref())
        }
        Command::CompareStudies {
            baseline,
            candidate,
            metadata,
            output,
        } => {
            let baseline = read_json::<CoDesignStudyReport>(&baseline)?;
            let candidate = read_json::<CoDesignStudyReport>(&candidate)?;
            let metadata = read_json::<DecisionMetadata>(&metadata)?;
            let decision = compare_studies(&baseline, &candidate, metadata)?;
            write_json(&decision, output.as_deref())
        }
        Command::AttributeFactorial { manifest, output } => {
            let manifest = read_json::<FactorialManifest>(&manifest)?;
            let observations = manifest
                .observations
                .into_iter()
                .map(|entry| {
                    let study = read_json::<CoDesignStudyReport>(&entry.study)?;
                    FactorialObservation::from_study(
                        entry.enabled_axes.into_iter().collect(),
                        &study,
                    )
                    .map_err(anyhow::Error::new)
                })
                .collect::<Result<Vec<_>>>()?;
            let report = shapley_attribution(&manifest.axes, observations)?;
            write_json(&report, output.as_deref())
        }
        Command::Sensitivity {
            study,
            request,
            output,
        } => {
            let study = read_json::<CoDesignStudyReport>(&study)?;
            let request = read_json::<SensitivityRequest>(&request)?;
            let report = analyze_codesign_sensitivity(&study, &request)?;
            write_json(&report, output.as_deref())
        }
        Command::ExternalRun {
            tool,
            input,
            output,
        } => {
            let tool = read_json::<ExternalToolSpec>(&tool)?;
            let input = read_json::<ExternalPerformanceInput>(&input)?;
            let record = ExternalProcessAdapter::new(tool)?.run(
                &input.model,
                &input.hardware,
                &input.work,
            )?;
            write_json(&record, output.as_deref())
        }
        Command::ClassSlo {
            study,
            contract,
            output,
        } => {
            let study = read_json::<CoDesignStudyReport>(&study)?;
            let contract = read_json::<WorkloadContractV2>(&contract)?;
            let report = evaluate_study_slos(&study, &contract)?;
            write_json(&report, output.as_deref())
        }
        Command::PublicAgenticProxy { request, output } => {
            let request = read_json::<PublicAgenticProxyRequest>(&request)?;
            let report = generate_public_agentic_proxy(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::Calibrate { request, output } => {
            let request = read_json::<CalibrationRequest>(&request)?;
            let report = calibrate(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::ServingBenchmark { request, output } => {
            let request = read_json::<MeasuredServingBenchmarkRequest>(&request)?;
            let report = evaluate_measured_serving_benchmark(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::ImportVllmServing {
            artifact,
            trace,
            manifest,
            output,
        } => {
            let artifact_json = fs::read(&artifact)
                .with_context(|| format!("failed to read {}", artifact.display()))?;
            let trace = read_json::<CanonicalTraceV2>(&trace)?;
            let manifest = read_json::<VllmServingImportManifest>(&manifest)?;
            let request = import_vllm_serving_benchmark(&artifact_json, trace, manifest)?;
            write_json(&request, output.as_deref())
        }
        Command::GlmStorageEnvelope { request, output } => {
            let request = read_json::<GlmStorageEnvelopeRequest>(&request)?;
            let report = evaluate_glm_storage_envelope(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::GlmResidencyFrontier {
            request,
            storage,
            output,
        } => {
            let request = read_json::<GlmResidencyFrontierRequest>(&request)?;
            let storage = read_json::<GlmStorageEnvelopeReport>(&storage)?;
            let report = evaluate_glm_residency_frontier(&request, &storage)?;
            write_json(&report, output.as_deref())
        }
        Command::GlmParallelMapping {
            request,
            storage,
            route,
            dsa,
            lowering_request,
            lowering,
            output,
        } => {
            let request = read_json::<GlmParallelMappingRequest>(&request)?;
            let storage = read_json::<GlmStorageEnvelopeReport>(&storage)?;
            let route = read_json::<foundry_core::glm_moe_route::GlmMoeRouteReport>(&route)?;
            let dsa = read_json::<foundry_core::glm_dsa::GlmDsaSweepReport>(&dsa)?;
            let lowering_request = read_json::<GlmDecodeLoweringRequest>(&lowering_request)?;
            let lowering = read_json::<GlmDecodeLoweringReport>(&lowering)?;
            let report = evaluate_glm_parallel_mapping(
                &request,
                &storage,
                &route,
                &dsa,
                &lowering_request,
                &lowering,
            )?;
            write_json(&report, output.as_deref())
        }
        Command::GlmMappingContextFrontier {
            request,
            storage,
            mapping_16k,
            mapping_90k,
            lowering_16k,
            lowering_90k,
            output,
        } => {
            let request = read_json::<GlmMappingContextFrontierRequest>(&request)?;
            let storage = read_json::<GlmStorageEnvelopeReport>(&storage)?;
            let mapping_16k = read_json::<
                foundry_core::glm_parallel_mapping::GlmParallelMappingReport,
            >(&mapping_16k)?;
            let mapping_90k = read_json::<
                foundry_core::glm_parallel_mapping::GlmParallelMappingReport,
            >(&mapping_90k)?;
            let lowering_16k = read_json::<GlmDecodeLoweringReport>(&lowering_16k)?;
            let lowering_90k = read_json::<GlmDecodeLoweringReport>(&lowering_90k)?;
            let report = evaluate_glm_mapping_context_frontier(
                &request,
                &storage,
                &mapping_16k,
                &mapping_90k,
                &lowering_16k,
                &lowering_90k,
            )?;
            write_json(&report, output.as_deref())
        }
        Command::GlmAgenticMappingScreen { request, output } => {
            let manifest = read_json::<GlmAgenticMappingRequest>(&request)?;
            let base = request.parent().context("mapping manifest has no parent")?;
            let (proxy, proxy_hash) = read_blake3_pinned_json::<PublicAgenticProxyReport>(
                base,
                &manifest.sources.proxy.path,
                &manifest.sources.proxy.file_blake3,
            )?;
            let (frontier_request, frontier_request_hash) =
                read_blake3_pinned_json::<GlmMappingContextFrontierRequest>(
                    base,
                    &manifest.sources.frontier_request.path,
                    &manifest.sources.frontier_request.file_blake3,
                )?;
            let (storage, storage_hash) = read_blake3_pinned_json::<GlmStorageEnvelopeReport>(
                base,
                &manifest.sources.storage.path,
                &manifest.sources.storage.file_blake3,
            )?;
            let (mapping_16k, mapping_16k_hash) = read_blake3_pinned_json::<
                foundry_core::glm_parallel_mapping::GlmParallelMappingReport,
            >(
                base,
                &manifest.sources.mapping_16k.path,
                &manifest.sources.mapping_16k.file_blake3,
            )?;
            let (mapping_90k, mapping_90k_hash) = read_blake3_pinned_json::<
                foundry_core::glm_parallel_mapping::GlmParallelMappingReport,
            >(
                base,
                &manifest.sources.mapping_90k.path,
                &manifest.sources.mapping_90k.file_blake3,
            )?;
            let (lowering_16k, lowering_16k_hash) =
                read_blake3_pinned_json::<GlmDecodeLoweringReport>(
                    base,
                    &manifest.sources.lowering_16k.path,
                    &manifest.sources.lowering_16k.file_blake3,
                )?;
            let (lowering_90k, lowering_90k_hash) =
                read_blake3_pinned_json::<GlmDecodeLoweringReport>(
                    base,
                    &manifest.sources.lowering_90k.path,
                    &manifest.sources.lowering_90k.file_blake3,
                )?;
            let hashes = GlmAgenticSourceFileHashes {
                proxy: proxy_hash,
                frontier_request: frontier_request_hash,
                storage: storage_hash,
                mapping_16k: mapping_16k_hash,
                mapping_90k: mapping_90k_hash,
                lowering_16k: lowering_16k_hash,
                lowering_90k: lowering_90k_hash,
            };
            let report = evaluate_glm_agentic_mapping_screen(
                &manifest,
                &GlmAgenticMappingInputs {
                    source_file_hashes: &hashes,
                    proxy: &proxy,
                    frontier_request: &frontier_request,
                    storage: &storage,
                    mapping_16k: &mapping_16k,
                    mapping_90k: &mapping_90k,
                    lowering_16k: &lowering_16k,
                    lowering_90k: &lowering_90k,
                },
            )?;
            write_json(&report, output.as_deref())
        }
        Command::GlmMoeRoute { request, output } => {
            let request = read_json::<GlmMoeRouteRequest>(&request)?;
            let report = evaluate_glm_moe_routes(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::GlmMtpSweep { request, output } => {
            let request = read_json::<GlmMtpSweepRequest>(&request)?;
            let report = evaluate_glm_mtp_sweep(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::GlmDsaSweep { request, output } => {
            let request = read_json::<GlmDsaSweepRequest>(&request)?;
            let report = evaluate_glm_dsa_sweep(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::GlmDecodeLower { request, output } => {
            let request = read_json::<GlmDecodeLoweringRequest>(&request)?;
            let report = evaluate_glm_decode_lowering(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::GlmPdServing { request, output } => {
            let request = read_json::<GlmPdServingRequest>(&request)?;
            let report = evaluate_glm_pd_serving(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::QwenInt4KernelSmoke { request, output } => {
            let request = read_json::<QwenInt4KernelSmokeRequest>(&request)?;
            let report = run_qwen_int4_kernel_smoke(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::QwenInt4BatchFrontier { request, output } => {
            let request = read_json::<QwenInt4BatchFrontierRequest>(&request)?;
            let report = run_qwen_int4_batch_frontier(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::QwenInt4Aarch64Neon { request, output } => {
            let request = read_json::<QwenInt4Aarch64NeonRequest>(&request)?;
            let report = run_qwen_int4_aarch64_neon(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::TimeloopProblemExport {
            problem,
            output,
            problem_yaml,
        } => {
            let problem = read_json::<KernelProblem>(&problem)?;
            let export = TimeloopProblemExporter::export(&problem)?;
            if let Some(path) = problem_yaml {
                fs::write(&path, &export.problem_yaml)
                    .with_context(|| format!("failed to write {}", path.display()))?;
            }
            write_json(&export, output.as_deref())
        }
        Command::ClaimComposition { request, output } => {
            let request = read_json::<CompositionRequest>(&request)?;
            let report = evaluate_claim_composition(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::DeploymentScreen {
            request,
            storage,
            roofline,
            output,
        } => {
            let request = read_json::<DeploymentScreenRequest>(&request)?;
            let storage = read_json::<GlmStorageEnvelopeReport>(&storage)?;
            let roofline = read_json::<LedgerRooflineReport>(&roofline)?;
            let report = evaluate_deployment_screen(&request, &storage, &roofline)?;
            write_json(&report, output.as_deref())
        }
        Command::EconomicFrontier {
            request,
            source_screen,
            output,
        } => {
            let request = read_json::<EconomicFrontierRequest>(&request)?;
            let source = read_json::<DeploymentScreenReport>(&source_screen)?;
            let report = evaluate_economic_frontier(&request, &source)?;
            write_json(&report, output.as_deref())
        }
        Command::InspectActionLedger { ledger, output } => {
            let ledger = read_json::<ActionLedger>(&ledger)?;
            ledger.validate()?;
            let content_id = ledger.content_id()?;
            let accounting = ledger.accounting()?;
            let topological_action_ids = ledger
                .topological_action_ids()?
                .into_iter()
                .map(|id| id.as_str().to_owned())
                .collect::<Vec<_>>();
            let latency_seconds = ledger.total_latency().ok().map(|value| value.get());
            let energy_joules = ledger.total_energy().ok().map(|value| value.get());
            let cost_usd = ledger.total_cost().ok().map(|value| value.get());
            let report = serde_json::json!({
                "schema_version": 1,
                "ledger_content_id": content_id.as_str(),
                "provenance": ledger.provenance,
                "accounting": accounting,
                "topological_action_ids": topological_action_ids,
                "calibrated_totals": {
                    "latency_seconds": latency_seconds,
                    "energy_joules": energy_joules,
                    "cost_usd": cost_usd,
                    "complete": latency_seconds.is_some()
                        && energy_joules.is_some()
                        && cost_usd.is_some()
                }
            });
            write_json(&report, output.as_deref())
        }
        Command::GlmTieredCache { request, output } => {
            let request = read_json::<GlmTieredCacheRequest>(&request)?;
            let report = evaluate_glm_tiered_cache(&request)?;
            write_json(&report, output.as_deref())
        }
        Command::LedgerRoofline {
            ledger,
            hardware_plan,
            output,
        } => {
            let ledger = read_json::<ActionLedger>(&ledger)?;
            let plan = read_json::<LedgerRooflineHardwarePlan>(&hardware_plan)?;
            let report = evaluate_ledger_roofline(&plan.into_request(ledger))?;
            write_json(&report, output.as_deref())
        }
        Command::LedgerServingExact { manifest, output } => {
            let artifact = evaluate_ledger_serving_manifest(&manifest)?;
            write_json(&artifact, output.as_deref())
        }
        Command::ExportChakra {
            ledger,
            output,
            manifest,
        } => {
            let ledger = read_json::<ActionLedger>(&ledger)?;
            let trace = ChakraExporter::export(&ledger)?;
            fs::write(&output, trace.bytes())
                .with_context(|| format!("failed to write {}", output.display()))?;
            fs::write(&manifest, trace.to_manifest_json()? + "\n")
                .with_context(|| format!("failed to write {}", manifest.display()))
        }
    }
}

fn provenance(source_artifacts: Vec<foundry_core::artifact::ArtifactId>) -> Provenance {
    Provenance {
        producer: "foundry-cli".into(),
        producer_version: env!("CARGO_PKG_VERSION").into(),
        source_artifacts,
    }
}

fn compose_variants(mut variants: Vec<ModelVariant>) -> Option<ModelVariant> {
    if variants.is_empty() {
        return None;
    }
    if variants.len() == 1 {
        return variants.pop();
    }
    let name = variants
        .iter()
        .map(|variant| variant.name.as_str())
        .collect::<Vec<_>>()
        .join("+");
    let changes = variants
        .into_iter()
        .flat_map(|variant| variant.changes)
        .collect();
    Some(ModelVariant {
        name,
        changes,
        quality: QualityEvidence::Unvalidated,
    })
}

#[derive(serde::Deserialize)]
struct FactorialManifest {
    axes: Vec<String>,
    observations: Vec<FactorialManifestEntry>,
}

#[derive(serde::Deserialize)]
struct FactorialManifestEntry {
    enabled_axes: Vec<String>,
    study: PathBuf,
}

const LEDGER_SERVING_PATH_MANIFEST_SCHEMA_VERSION: u32 = 1;

#[derive(Clone, Debug, serde::Deserialize, PartialEq, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct PinnedJsonPath {
    path: PathBuf,
    artifact_id: ArtifactId,
}

#[derive(Clone, Copy, Debug, serde::Deserialize, Eq, PartialEq, serde::Serialize)]
#[serde(rename_all = "snake_case")]
enum LedgerServingSloEvidenceKind {
    SyntheticAssumption,
}

#[derive(Clone, Debug, serde::Deserialize, Eq, PartialEq, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct LedgerServingSloProvenance {
    evidence_kind: LedgerServingSloEvidenceKind,
    source_artifact_id: String,
    basis: String,
}

#[derive(Clone, Debug, serde::Deserialize, PartialEq, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct LedgerServingPathManifest {
    schema_version: u32,
    study_id: String,
    workload_contract: PinnedJsonPath,
    trace: PinnedJsonPath,
    lowering_report: PinnedJsonPath,
    lowering_report_content_id: String,
    roofline_report: PinnedJsonPath,
    roofline_report_content_id: String,
    ledger_content_id: String,
    hardware_ids: Vec<String>,
    slo_provenance: LedgerServingSloProvenance,
}

#[derive(Clone, Debug, serde::Deserialize, Eq, PartialEq, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct LedgerServingSourceArtifacts {
    manifest: ArtifactId,
    workload_contract: ArtifactId,
    trace: ArtifactId,
    lowering_report: ArtifactId,
    roofline_report: ArtifactId,
}

#[derive(Clone, Debug, serde::Deserialize, PartialEq, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct LedgerServingStudyResult {
    study_id: String,
    sources: LedgerServingSourceArtifacts,
    slo_provenance: LedgerServingSloProvenance,
    reports: Vec<LedgerServingReport>,
}

fn evaluate_ledger_serving_manifest(
    manifest_path: &Path,
) -> Result<Artifact<LedgerServingStudyResult>> {
    let manifest_bytes = fs::read(manifest_path)
        .with_context(|| format!("failed to read {}", manifest_path.display()))?;
    let manifest_artifact_id = ArtifactId::from_bytes(&manifest_bytes);
    let manifest = serde_json::from_slice::<LedgerServingPathManifest>(&manifest_bytes)
        .with_context(|| format!("failed to parse JSON from {}", manifest_path.display()))?;
    validate_ledger_serving_manifest(&manifest)?;
    let base = manifest_path.parent().unwrap_or_else(|| Path::new("."));
    let (workload_contract, workload_contract_artifact_id) =
        read_pinned_json::<WorkloadContractV2>(base, &manifest.workload_contract)?;
    let (trace, trace_artifact_id) = read_pinned_json::<CanonicalTraceV2>(base, &manifest.trace)?;
    let (lowering, lowering_report_artifact_id) =
        read_pinned_json::<GlmDecodeLoweringReport>(base, &manifest.lowering_report)?;
    let (roofline, roofline_report_artifact_id) =
        read_pinned_json::<LedgerRooflineReport>(base, &manifest.roofline_report)?;
    if !lowering.verify_content_id()? {
        anyhow::bail!("lowering report content identity is invalid");
    }
    if lowering.content_id != manifest.lowering_report_content_id {
        anyhow::bail!("lowering report content identity differs from manifest pin");
    }
    if !roofline.verify_content_id()? {
        anyhow::bail!("roofline report content identity is invalid");
    }
    if roofline.content_id != manifest.roofline_report_content_id {
        anyhow::bail!("roofline report content identity differs from manifest pin");
    }
    let ledger = lowering
        .result
        .hardware_study_ledger
        .clone()
        .context("lowering report has no selected hardware-study ledger")?;
    let ledger_content_id = ledger.content_id()?.as_str().to_owned();
    if ledger_content_id != manifest.ledger_content_id {
        anyhow::bail!("lowering ledger content identity differs from manifest pin");
    }
    if roofline.result.ledger_content_id != manifest.ledger_content_id {
        anyhow::bail!("roofline input ledger differs from manifest pin");
    }
    let reports = manifest
        .hardware_ids
        .iter()
        .map(|hardware_id| {
            simulate_exact_ledger_serving(&LedgerServingSimulationRequest {
                schema_version: LEDGER_SERVING_REQUEST_SCHEMA_VERSION,
                simulation_id: manifest.study_id.clone(),
                workload_contract: workload_contract.clone(),
                trace: trace.clone(),
                ledger: ledger.clone(),
                roofline: roofline.clone(),
                hardware_id: hardware_id.clone(),
            })
            .map_err(anyhow::Error::new)
        })
        .collect::<Result<Vec<_>>>()?;
    let sources = LedgerServingSourceArtifacts {
        manifest: manifest_artifact_id.clone(),
        workload_contract: workload_contract_artifact_id.clone(),
        trace: trace_artifact_id.clone(),
        lowering_report: lowering_report_artifact_id.clone(),
        roofline_report: roofline_report_artifact_id.clone(),
    };
    Ok(Artifact {
        schema_version: 1,
        kind: ArtifactKind::ServingSimulation,
        provenance: provenance(vec![
            manifest_artifact_id,
            workload_contract_artifact_id,
            trace_artifact_id,
            lowering_report_artifact_id,
            roofline_report_artifact_id,
        ]),
        payload: LedgerServingStudyResult {
            study_id: manifest.study_id,
            sources,
            slo_provenance: manifest.slo_provenance,
            reports,
        },
    })
}

fn validate_ledger_serving_manifest(manifest: &LedgerServingPathManifest) -> Result<()> {
    if manifest.schema_version != LEDGER_SERVING_PATH_MANIFEST_SCHEMA_VERSION {
        anyhow::bail!(
            "unsupported ledger serving path manifest schema version {}",
            manifest.schema_version
        );
    }
    for (field, value) in [
        ("study_id", manifest.study_id.as_str()),
        (
            "lowering_report_content_id",
            manifest.lowering_report_content_id.as_str(),
        ),
        (
            "roofline_report_content_id",
            manifest.roofline_report_content_id.as_str(),
        ),
        ("ledger_content_id", manifest.ledger_content_id.as_str()),
        (
            "slo_provenance.source_artifact_id",
            manifest.slo_provenance.source_artifact_id.as_str(),
        ),
        (
            "slo_provenance.basis",
            manifest.slo_provenance.basis.as_str(),
        ),
    ] {
        if value.trim().is_empty() {
            anyhow::bail!("ledger serving manifest field {field} is empty");
        }
    }
    if manifest.hardware_ids.is_empty() {
        anyhow::bail!("ledger serving manifest has no hardware selections");
    }
    let mut hardware_ids = BTreeSet::new();
    for hardware_id in &manifest.hardware_ids {
        if hardware_id.trim().is_empty() {
            anyhow::bail!("ledger serving manifest contains an empty hardware selection");
        }
        if !hardware_ids.insert(hardware_id) {
            anyhow::bail!("ledger serving manifest repeats hardware {hardware_id}");
        }
    }
    Ok(())
}

fn read_pinned_json<T: serde::de::DeserializeOwned>(
    base: &Path,
    pin: &PinnedJsonPath,
) -> Result<(T, ArtifactId)> {
    if pin.path.is_absolute() {
        anyhow::bail!("pinned JSON path must be relative: {}", pin.path.display());
    }
    let path = base.join(&pin.path);
    let bytes = fs::read(&path).with_context(|| format!("failed to read {}", path.display()))?;
    let actual = ArtifactId::from_bytes(&bytes);
    if actual != pin.artifact_id {
        anyhow::bail!(
            "artifact identity mismatch for {}: expected {}, got {}",
            path.display(),
            pin.artifact_id.as_str(),
            actual.as_str()
        );
    }
    let value = serde_json::from_slice(&bytes)
        .with_context(|| format!("failed to parse JSON from {}", path.display()))?;
    Ok((value, actual))
}

fn read_json<T: serde::de::DeserializeOwned>(path: &Path) -> Result<T> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    serde_json::from_slice(&bytes)
        .with_context(|| format!("failed to parse JSON from {}", path.display()))
}

fn read_blake3_pinned_json<T: serde::de::DeserializeOwned>(
    base: &Path,
    path: &Path,
    expected: &str,
) -> Result<(T, String)> {
    if path.is_absolute() {
        anyhow::bail!("pinned JSON path must be relative: {}", path.display());
    }
    let resolved = base.join(path);
    let bytes =
        fs::read(&resolved).with_context(|| format!("failed to read {}", resolved.display()))?;
    let actual = ArtifactId::from_bytes(&bytes).as_str().to_owned();
    if actual != expected {
        anyhow::bail!(
            "file BLAKE3 mismatch for {}: expected {}, got {}",
            resolved.display(),
            expected,
            actual
        );
    }
    let value = serde_json::from_slice(&bytes)
        .with_context(|| format!("failed to parse JSON from {}", resolved.display()))?;
    Ok((value, actual))
}

fn write_json<T: serde::Serialize>(value: &T, path: Option<&Path>) -> Result<()> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    match path {
        Some(path) => {
            fs::write(path, bytes).with_context(|| format!("failed to write {}", path.display()))
        }
        None => {
            let mut stdout = io::stdout().lock();
            stdout.write_all(&bytes)?;
            stdout.flush()?;
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use foundry_core::glm_moe_route::GlmMoeRouteReport;
    use foundry_core::serving_benchmark::{
        MeasuredServingBenchmarkRequest, ServingEngineIdentity, ServingEvidenceKind,
        ServingHardwareTopology, ServingMeasurementProvenance, ServingModelIdentity,
    };
    use foundry_core::vllm_serving::{
        VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION, vllm_source_artifact_id,
    };
    use foundry_core::workload::privacy_safe_synthetic_agent_fixture;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static TEST_DIRECTORY_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    #[test]
    fn parses_validate_command() {
        let cli = Cli::try_parse_from(["foundry", "validate", "experiment.json"]).unwrap();

        assert!(matches!(cli.command, Command::Validate { .. }));
    }

    #[test]
    fn parses_public_agentic_proxy_command() {
        let cli = Cli::try_parse_from([
            "foundry",
            "public-agentic-proxy",
            "proxy.json",
            "--output",
            "artifact.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::PublicAgenticProxy { .. }));
    }

    #[test]
    fn parses_glm_agentic_mapping_screen_command() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-agentic-mapping-screen",
            "screen.json",
            "--output",
            "artifact.json",
        ])
        .unwrap();

        assert!(matches!(
            cli.command,
            Command::GlmAgenticMappingScreen { .. }
        ));
    }

    #[test]
    fn evaluates_pinned_glm_agentic_mapping_manifest() {
        let temporary = TestDir::new();
        let output = temporary.0.join("glm-agentic-mapping.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let request = root.join("configs/glm-5.2-agentic-mapping-screen-v1.json");

        run(Cli {
            command: Command::GlmAgenticMappingScreen {
                request,
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report =
            read_json::<foundry_core::glm_agentic_mapping::GlmAgenticMappingReport>(&output)
                .unwrap();
        assert!(report.verify_content_id().unwrap());
        assert!(report.result.source_file_hashes_verified);
        assert_eq!(report.result.exact_context_evaluation_count, 45);
        assert_eq!(report.result.request_weighted_evaluation_count, 320);
        assert!(!report.result.claims.full_deployment_claim_permitted);
    }

    #[test]
    fn generates_public_agentic_proxy_artifact() {
        let temporary = TestDir::new();
        let output = temporary.0.join("agentic-proxy.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let request = root.join("configs/workloads/aa-agentperf-public-proxy-v1.json");

        run(Cli {
            command: Command::PublicAgenticProxy {
                request,
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report =
            read_json::<foundry_core::public_agentic_proxy::PublicAgenticProxyReport>(&output)
                .unwrap();
        assert!(report.verify_content_id().unwrap());
        assert_eq!(report.result.summary.request_count, 64);
        assert!(!report.result.claim_gates.nvidia_performance_claim_permitted);
    }

    #[test]
    fn parses_detailed_simulation_options() {
        let cli = Cli::try_parse_from([
            "foundry",
            "simulate",
            "experiment.json",
            "--oracle",
            "tensor-tile",
            "--server-tco",
            "tco.json",
            "--artifact-dir",
            "artifacts",
        ])
        .unwrap();

        let Command::Simulate {
            oracle,
            server_tco,
            artifact_dir,
            ..
        } = cli.command
        else {
            panic!("expected simulate command")
        };
        assert_eq!(oracle, OracleArg::TensorTile);
        assert_eq!(server_tco, Some(PathBuf::from("tco.json")));
        assert_eq!(artifact_dir, Some(PathBuf::from("artifacts")));
    }

    #[test]
    fn parses_capacity_plan_limit() {
        let cli = Cli::try_parse_from([
            "foundry",
            "capacity-plan",
            "experiment.json",
            "--maximum-replicas",
            "64",
        ])
        .unwrap();

        assert!(matches!(
            cli.command,
            Command::CapacityPlan {
                maximum_replicas: 64,
                ..
            }
        ));
    }

    #[test]
    fn parses_hardware_sizing_constraints() {
        let cli = Cli::try_parse_from([
            "foundry",
            "size-hardware",
            "experiment.json",
            "--constraints",
            "sizing.json",
        ])
        .unwrap();

        assert!(matches!(
            cli.command,
            Command::SizeHardware {
                constraints: Some(_),
                ..
            }
        ));
    }

    #[test]
    fn parses_codesign_model_variant() {
        let cli = Cli::try_parse_from([
            "foundry",
            "codesign-study",
            "experiment.json",
            "--constraints",
            "sizing.json",
            "--model-variant",
            "variant.json",
        ])
        .unwrap();

        assert!(matches!(
            cli.command,
            Command::CodesignStudy {
                model_variant,
                ..
            } if model_variant.len() == 1
        ));
    }

    #[test]
    fn parses_qwen_int4_kernel_smoke() {
        let cli = Cli::try_parse_from([
            "foundry",
            "qwen-int4-kernel-smoke",
            "request.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::QwenInt4KernelSmoke { .. }));
    }

    #[test]
    fn parses_qwen_int4_batch_frontier() {
        let cli = Cli::try_parse_from([
            "foundry",
            "qwen-int4-batch-frontier",
            "request.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::QwenInt4BatchFrontier { .. }));
    }

    #[test]
    fn parses_qwen_int4_aarch64_neon() {
        let cli = Cli::try_parse_from([
            "foundry",
            "qwen-int4-aarch64-neon",
            "request.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::QwenInt4Aarch64Neon { .. }));
    }

    #[test]
    fn parses_timeloop_problem_export() {
        let cli = Cli::try_parse_from([
            "foundry",
            "timeloop-problem-export",
            "problem.json",
            "--output",
            "manifest.json",
            "--problem-yaml",
            "problem.yaml",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::TimeloopProblemExport { .. }));
    }

    #[test]
    fn parses_claim_composition() {
        let cli = Cli::try_parse_from([
            "foundry",
            "claim-composition",
            "request.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::ClaimComposition { .. }));
    }

    #[test]
    fn runs_current_claim_composition_from_checked_input() {
        let temporary = TestDir::new();
        let output = temporary.0.join("claim-composition.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::ClaimComposition {
                request: root.join("configs/glm-5.2-current-cost-claim-composition-v1.json"),
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report =
            read_json::<foundry_core::claim_composition::CompositionReport>(&output).unwrap();
        let stored = read_json::<foundry_core::claim_composition::CompositionReport>(
            &root.join("experiments/glm-5.2/current-cost-claim-composition-v1.json"),
        )
        .unwrap();
        assert_eq!(report, stored);
        assert!(!report.combined_claim_permitted);
        assert!(report.admissible_evidence_ids.is_empty());
        assert!(report.verify_content_id().unwrap());
    }

    #[test]
    fn runs_timeloop_problem_export_from_checked_input() {
        let temporary = TestDir::new();
        let output = temporary.0.join("timeloop-manifest.json");
        let yaml = temporary.0.join("problem.yaml");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::TimeloopProblemExport {
                problem: root.join("configs/timeloop/qwen3-0.6b-o-proj-bf16-decode-b1-v1.json"),
                output: Some(output.clone()),
                problem_yaml: Some(yaml.clone()),
            },
        })
        .unwrap();

        let report =
            read_json::<foundry_core::timeloop_export::TimeloopProblemExport>(&output).unwrap();
        let stored = read_json::<foundry_core::timeloop_export::TimeloopProblemExport>(
            &root.join("experiments/qwen3-0.6b/timeloop-o-proj-bf16-decode-b1-v1.json"),
        )
        .unwrap();
        assert_eq!(report, stored);
        assert_eq!(fs::read_to_string(yaml).unwrap(), stored.problem_yaml);
        assert!(report.verify_content_id().unwrap());
    }

    #[test]
    fn parses_study_comparison() {
        let cli = Cli::try_parse_from([
            "foundry",
            "compare-studies",
            "baseline.json",
            "candidate.json",
            "metadata.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::CompareStudies { .. }));
    }

    #[test]
    fn parses_factorial_attribution() {
        let cli = Cli::try_parse_from(["foundry", "attribute-factorial", "manifest.json"]).unwrap();

        assert!(matches!(cli.command, Command::AttributeFactorial { .. }));
    }

    #[test]
    fn parses_sensitivity_analysis() {
        let cli =
            Cli::try_parse_from(["foundry", "sensitivity", "study.json", "request.json"]).unwrap();

        assert!(matches!(cli.command, Command::Sensitivity { .. }));
    }

    #[test]
    fn parses_external_simulator_run() {
        let cli =
            Cli::try_parse_from(["foundry", "external-run", "tool.json", "input.json"]).unwrap();

        assert!(matches!(cli.command, Command::ExternalRun { .. }));
    }

    #[test]
    fn parses_class_slo_evaluation() {
        let cli =
            Cli::try_parse_from(["foundry", "class-slo", "study.json", "contract.json"]).unwrap();

        assert!(matches!(cli.command, Command::ClassSlo { .. }));
    }

    #[test]
    fn parses_calibration_report() {
        let cli = Cli::try_parse_from([
            "foundry",
            "calibrate",
            "calibration.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::Calibrate { .. }));
    }

    #[test]
    fn parses_measured_serving_benchmark() {
        let cli = Cli::try_parse_from([
            "foundry",
            "serving-benchmark",
            "benchmark.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::ServingBenchmark { .. }));
    }

    #[test]
    fn parses_vllm_serving_import() {
        let cli = Cli::try_parse_from([
            "foundry",
            "import-vllm-serving",
            "vllm.json",
            "trace.json",
            "manifest.json",
            "--output",
            "request.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::ImportVllmServing { .. }));
    }

    #[test]
    fn parses_glm_storage_envelope() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-storage-envelope",
            "glm-envelope.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmStorageEnvelope { .. }));
    }

    #[test]
    fn parses_glm_residency_frontier() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-residency-frontier",
            "frontier.json",
            "storage.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmResidencyFrontier { .. }));
    }

    #[test]
    fn runs_glm_residency_frontier_from_checked_inputs() {
        let temporary = TestDir::new();
        let output = temporary.0.join("residency-frontier.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::GlmResidencyFrontier {
                request: root.join("configs/glm-5.2-nvfp4-fp8-kv-four-b200-frontier-v1.json"),
                storage: root.join("experiments/glm-5.2/storage-envelope-v1.json"),
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report =
            read_json::<foundry_core::residency_frontier::GlmResidencyFrontierReport>(&output)
                .unwrap();
        assert!(report.verify_content_id().unwrap());
        assert_eq!(report.result.target_device_count, 4);
        assert!(!report.result.frontiers[0].aggregate_capacity_feasible);
    }

    #[test]
    fn parses_glm_parallel_mapping() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-parallel-mapping",
            "mapping.json",
            "storage.json",
            "route.json",
            "dsa.json",
            "lowering-request.json",
            "lowering.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmParallelMapping { .. }));
    }

    #[test]
    fn runs_glm_parallel_mapping_from_checked_inputs() {
        let temporary = TestDir::new();
        let output = temporary.0.join("parallel-mapping.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::GlmParallelMapping {
                request: root.join("configs/glm-5.2-parallel-mapping-control-v1.json"),
                storage: root.join("experiments/glm-5.2/storage-envelope-v1.json"),
                route: root.join("experiments/glm-5.2/moe-route-skew-v1.json"),
                dsa: root.join("experiments/glm-5.2/dsa-indexshare-sweep-v1.json"),
                lowering_request: root.join("configs/glm-5.2-nvfp4-whole-decode-lowering-v1.json"),
                lowering: root.join("experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json"),
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report =
            read_json::<foundry_core::glm_parallel_mapping::GlmParallelMappingReport>(&output)
                .unwrap();
        let stored = read_json::<foundry_core::glm_parallel_mapping::GlmParallelMappingReport>(
            &root.join("experiments/glm-5.2/parallel-mapping-control-v1.json"),
        )
        .unwrap();
        assert_eq!(report, stored);
        assert!(report.verify_content_id().unwrap());
    }

    #[test]
    fn parses_glm_mapping_context_frontier() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-mapping-context-frontier",
            "frontier.json",
            "storage.json",
            "mapping-16k.json",
            "mapping-90k.json",
            "lowering-16k.json",
            "lowering-90k.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(
            cli.command,
            Command::GlmMappingContextFrontier { .. }
        ));
    }

    #[test]
    fn runs_glm_mapping_context_frontier_from_checked_inputs() {
        let temporary = TestDir::new();
        let output = temporary.0.join("mapping-context-frontier.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::GlmMappingContextFrontier {
                request: root.join("configs/glm-5.2-parallel-mapping-context-frontier-v1.json"),
                storage: root.join("experiments/glm-5.2/storage-envelope-v1.json"),
                mapping_16k: root.join("experiments/glm-5.2/parallel-mapping-control-v1.json"),
                mapping_90k: root.join("experiments/glm-5.2/parallel-mapping-90k-control-v1.json"),
                lowering_16k: root.join("experiments/glm-5.2/nvfp4-whole-decode-lowering-v1.json"),
                lowering_90k: root
                    .join("experiments/glm-5.2/nvfp4-whole-decode-lowering-90k-control-v1.json"),
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report = read_json::<
            foundry_core::glm_mapping_context_frontier::GlmMappingContextFrontierReport,
        >(&output)
        .unwrap();
        let stored = read_json::<
            foundry_core::glm_mapping_context_frontier::GlmMappingContextFrontierReport,
        >(
            &root.join("experiments/glm-5.2/parallel-mapping-context-frontier-v1.json")
        )
        .unwrap();
        assert_eq!(report, stored);
        assert!(report.verify_content_id().unwrap());
    }

    #[test]
    fn parses_glm_mtp_sweep() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-mtp-sweep",
            "glm-mtp.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmMtpSweep { .. }));
    }

    #[test]
    fn parses_glm_dsa_sweep() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-dsa-sweep",
            "glm-dsa.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmDsaSweep { .. }));
    }

    #[test]
    fn parses_glm_decode_lowering() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-decode-lower",
            "glm-decode.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmDecodeLower { .. }));
    }

    #[test]
    fn parses_glm_pd_serving_control() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-pd-serving",
            "glm-pd-serving.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmPdServing { .. }));
    }

    #[test]
    fn parses_deployment_screen() {
        let cli = Cli::try_parse_from([
            "foundry",
            "deployment-screen",
            "screen.json",
            "storage.json",
            "roofline.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::DeploymentScreen { .. }));
    }

    #[test]
    fn parses_economic_frontier() {
        let cli = Cli::try_parse_from([
            "foundry",
            "economic-frontier",
            "frontier.json",
            "source-screen.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::EconomicFrontier { .. }));
    }

    #[test]
    fn parses_glm_moe_route_simulation() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-moe-route",
            "glm-route.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmMoeRoute { .. }));
    }

    #[test]
    fn runs_glm_moe_route_simulation_from_checked_config() {
        let temporary = TestDir::new();
        let output = temporary.0.join("glm-moe-route-report.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::GlmMoeRoute {
                request: root.join("configs/glm-5.2-moe-route-skew-v1.json"),
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report = read_json::<GlmMoeRouteReport>(&output).unwrap();
        assert!(report.verify_content_id().unwrap());
        assert_eq!(report.result.scenarios.len(), 2);
    }

    #[test]
    fn runs_glm_whole_decode_lowering_from_checked_config() {
        let temporary = TestDir::new();
        let output = temporary.0.join("glm-whole-decode-report.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();

        run(Cli {
            command: Command::GlmDecodeLower {
                request: root.join("configs/glm-5.2-whole-decode-lowering-v1.json"),
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report = read_json::<GlmDecodeLoweringReport>(&output).unwrap();
        assert!(report.verify_content_id().unwrap());
        assert_eq!(report.result.route.total_dispatches, 9_600);
        assert!(!report.result.completeness.cost_per_token_claim_permitted);
    }

    #[test]
    fn inspects_an_uncalibrated_action_ledger_without_inventing_totals() {
        let temporary = TestDir::new();
        let output = temporary.0.join("ledger-report.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let ledger = root.join("crates/foundry-core/tests/fixtures/glm-5.2-decode-ledger-v1.json");

        run(Cli {
            command: Command::InspectActionLedger {
                ledger,
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let report = read_json::<serde_json::Value>(&output).unwrap();
        assert_eq!(report["accounting"]["compute_actions"], 6);
        assert_eq!(report["accounting"]["memory_bytes"], 5_275_648);
        assert_eq!(
            report["calibrated_totals"]["latency_seconds"],
            serde_json::Value::Null
        );
        assert_eq!(
            report["calibrated_totals"]["energy_joules"],
            serde_json::Value::Null
        );
        assert_eq!(
            report["calibrated_totals"]["cost_usd"],
            serde_json::Value::Null
        );
        assert_eq!(report["calibrated_totals"]["complete"], false);
    }

    #[test]
    fn parses_glm_tiered_cache() {
        let cli = Cli::try_parse_from([
            "foundry",
            "glm-tiered-cache",
            "glm-cache.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::GlmTieredCache { .. }));
    }

    #[test]
    fn parses_ledger_roofline() {
        let cli = Cli::try_parse_from([
            "foundry",
            "ledger-roofline",
            "ledger.json",
            "hardware.json",
            "--output",
            "report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::LedgerRoofline { .. }));
    }

    #[test]
    fn parses_exact_ledger_serving() {
        let cli = Cli::try_parse_from([
            "foundry",
            "ledger-serving-exact",
            "serving-manifest.json",
            "--output",
            "serving-report.json",
        ])
        .unwrap();

        assert!(matches!(cli.command, Command::LedgerServingExact { .. }));
    }

    #[test]
    fn checked_exact_ledger_serving_artifact_round_trips_all_hardware() {
        let temporary = TestDir::new();
        let output = temporary.0.join("ledger-serving.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let manifest = root.join("configs/glm-5.2-exact-ledger-serving-v1.json");
        let stored = read_json::<Artifact<LedgerServingStudyResult>>(
            &root.join("experiments/glm-5.2/exact-ledger-serving-v1.json"),
        )
        .unwrap();

        run(Cli {
            command: Command::LedgerServingExact {
                manifest,
                output: Some(output.clone()),
            },
        })
        .unwrap();

        let generated = read_json::<Artifact<LedgerServingStudyResult>>(&output).unwrap();
        assert_eq!(generated, stored);
        assert_eq!(generated.kind, ArtifactKind::ServingSimulation);
        assert_eq!(generated.payload.reports.len(), 3);
        assert!(
            generated
                .payload
                .reports
                .iter()
                .all(|report| report.verify_content_id().unwrap())
        );
        assert!(generated.payload.reports.iter().all(|report| {
            !report.result.claims.end_to_end_latency_claim_permitted
                && !report.result.claims.slo_claim_permitted
                && !report.result.claims.cost_per_token_claim_permitted
        }));

        let first = &generated.payload.reports[0].result;
        for result in generated
            .payload
            .reports
            .iter()
            .map(|report| &report.result)
        {
            assert_eq!(result.simulation_id, first.simulation_id);
            assert_eq!(result.workload_contract_id, first.workload_contract_id);
            assert_eq!(result.trace_id, first.trace_id);
            assert_eq!(result.trace_content_id, first.trace_content_id);
            assert_eq!(
                result.quantum.ledger_content_id,
                first.quantum.ledger_content_id
            );
            assert_eq!(
                result.quantum.roofline_content_id,
                first.quantum.roofline_content_id
            );
            assert_eq!(result.quantum.batch_size, first.quantum.batch_size);
            assert_eq!(
                result.quantum.aggregate_context_tokens,
                first.quantum.aggregate_context_tokens
            );
            assert_eq!(
                result.quantum.candidate_tokens,
                first.quantum.candidate_tokens
            );
            assert_eq!(
                result.quantum.committed_tokens,
                first.quantum.committed_tokens
            );
            assert_eq!(result.claims, first.claims);
        }
        assert_eq!(
            generated
                .payload
                .reports
                .iter()
                .map(|report| report.result.quantum.hardware_id.as_str())
                .collect::<Vec<_>>(),
            vec![
                "h200-published-peak-component",
                "custom-original-throughput-component",
                "rubin-preliminary-peak-component",
            ]
        );
    }

    #[test]
    fn exact_ledger_serving_manifest_rejects_source_drift_and_unknown_fields() {
        let temporary = TestDir::new();
        let source = temporary.0.join("source.json");
        fs::write(&source, b"{\"value\":1}").unwrap();
        let pin = PinnedJsonPath {
            path: PathBuf::from("source.json"),
            artifact_id: ArtifactId::from_bytes(b"{\"value\":1}"),
        };
        fs::write(&source, b"{\"value\":2}").unwrap();

        assert!(read_pinned_json::<serde_json::Value>(&temporary.0, &pin).is_err());

        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let mut manifest = serde_json::to_value(
            read_json::<LedgerServingPathManifest>(
                &root.join("configs/glm-5.2-exact-ledger-serving-v1.json"),
            )
            .unwrap(),
        )
        .unwrap();
        manifest
            .as_object_mut()
            .unwrap()
            .insert("unknown".into(), true.into());
        assert!(serde_json::from_value::<LedgerServingPathManifest>(manifest).is_err());
    }

    #[test]
    fn exports_chakra_wire_bytes_with_a_manifest() {
        let temporary = TestDir::new();
        let output = temporary.0.join("trace.et");
        let manifest = temporary.0.join("trace.json");
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let ledger = root.join("crates/foundry-core/tests/fixtures/glm-5.2-chakra-ledger-v1.json");

        run(Cli {
            command: Command::ExportChakra {
                ledger,
                output: output.clone(),
                manifest: manifest.clone(),
            },
        })
        .unwrap();

        let manifest = read_json::<serde_json::Value>(&manifest).unwrap();
        assert_eq!(fs::read(output).unwrap().len(), 3_084);
        assert_eq!(manifest["encoded_bytes"], 3_084);
        assert_eq!(manifest["provenance"]["schema_tag"], "v0.0.4");
        assert_eq!(
            manifest["provenance"]["semantics"],
            "interchange_only_no_timing"
        );
    }

    #[test]
    fn imports_vllm_serving_files_into_a_measured_request() {
        let root = TestDir::new();
        let artifact_path = root.0.join("vllm.json");
        let trace_path = root.0.join("trace.json");
        let manifest_path = root.0.join("manifest.json");
        let output_path = root.0.join("request.json");
        let fixture = privacy_safe_synthetic_agent_fixture();
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
        let artifact = serde_json::to_vec(&serde_json::json!({
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
            "itls": vec![vec![0.001]; fixture.trace.requests.len()],
            "start_times": start_times,
            "generated_texts": vec!["redacted"; fixture.trace.requests.len()],
            "errors": vec![""; fixture.trace.requests.len()]
        }))
        .unwrap();
        let manifest = VllmServingImportManifest {
            schema_version: VLLM_SERVING_IMPORT_MANIFEST_SCHEMA_VERSION,
            benchmark_id: "cli-vllm-import".into(),
            ordered_request_ids: fixture
                .trace
                .requests
                .iter()
                .map(|request| request.request_id)
                .collect(),
            workload_contract: fixture.contract,
            model: ServingModelIdentity {
                model_id: fixture.trace.identity.model_id.clone(),
                model_revision: fixture.trace.identity.model_revision.clone(),
                checkpoint_id: "checkpoint".into(),
                checkpoint_revision: "checkpoint-revision".into(),
                tokenizer_id: fixture.trace.identity.tokenizer_id.clone(),
                tokenizer_revision: fixture.trace.identity.tokenizer_revision.clone(),
            },
            provenance: ServingMeasurementProvenance {
                evidence_kind: ServingEvidenceKind::MeasuredHardware,
                run_id: "run".into(),
                source_artifact_id: vllm_source_artifact_id(&artifact),
                engine: ServingEngineIdentity {
                    name: "vllm".into(),
                    version: "0.1.dev1".into(),
                    build_id: "vllm-build".into(),
                },
                hardware: ServingHardwareTopology {
                    device_model: "H100 SXM".into(),
                    device_count: 1,
                    topology: "single_device".into(),
                    interconnect: "none".into(),
                    device_set_hash: "device-set".into(),
                },
                measurement_tool: "foundry-vllm-adapter".into(),
                software_revision: "adapter-revision".into(),
                captured_at_unix_milliseconds: 1_750_000_000_000,
            },
        };
        fs::write(&artifact_path, artifact).unwrap();
        fs::write(&trace_path, serde_json::to_vec(&fixture.trace).unwrap()).unwrap();
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();

        run(Cli {
            command: Command::ImportVllmServing {
                artifact: artifact_path,
                trace: trace_path,
                manifest: manifest_path,
                output: Some(output_path.clone()),
            },
        })
        .unwrap();

        let request = read_json::<MeasuredServingBenchmarkRequest>(&output_path).unwrap();
        assert_eq!(request.benchmark_id, "cli-vllm-import");
        assert_eq!(request.observations.len(), fixture.trace.requests.len());
    }

    struct TestDir(PathBuf);

    impl TestDir {
        fn new() -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let sequence = TEST_DIRECTORY_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "foundry-cli-vllm-import-{}-{nonce}-{sequence}",
                std::process::id()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }

    impl Drop for TestDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
}
