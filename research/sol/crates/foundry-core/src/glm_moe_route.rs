use std::cmp::Reverse;
use std::collections::{BTreeMap, BTreeSet, VecDeque};

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const GLM_MOE_ROUTE_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_MOE_ROUTE_REPORT_SCHEMA_VERSION: u32 = 1;
pub const GLM_MOE_LAYER_COUNT: u32 = 75;
pub const GLM_MOE_EXPERT_COUNT: u32 = 256;
pub const GLM_MOE_TOP_K: u32 = 8;

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMoeGeometry {
    pub moe_layer_count: u32,
    pub routed_expert_count: u32,
    pub top_k: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InterconnectTrafficAssumptions {
    pub expert_storage_bytes: u64,
    pub activation_payload_bytes_per_dispatch: u64,
    pub result_payload_bytes_per_dispatch: u64,
    pub source_artifact_id: String,
    pub basis: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RouteEvidenceKind {
    MeasuredRouteHistogram,
    ModeledAssumption,
    AnalyticalBound,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RouteProvenance {
    pub kind: RouteEvidenceKind,
    pub source_artifact_id: String,
    pub model_id: String,
    pub model_revision: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SyntheticRouteDistribution {
    Uniform,
    RotatingHotset {
        hot_expert_count: u32,
        hot_dispatch_share_basis_points: u32,
        layer_rotation_stride: u32,
        source_rotation_stride: u32,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SyntheticRouteSpec {
    pub source_shard_count: u32,
    pub tokens_per_source_shard: u64,
    pub distribution: SyntheticRouteDistribution,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SourceRouteHistogram {
    pub source_shard: u32,
    pub token_count: u64,
    pub expert_dispatch_counts: Vec<u64>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LayerRouteHistogram {
    pub layer_index: u32,
    pub sources: Vec<SourceRouteHistogram>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PinnedRouteHistogram {
    pub source_shard_count: u32,
    pub layers: Vec<LayerRouteHistogram>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    tag = "kind",
    content = "value",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum RouteInputSpec {
    Synthetic(SyntheticRouteSpec),
    PinnedHistogram(PinnedRouteHistogram),
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RouteScenarioSpec {
    pub scenario_id: String,
    pub route: RouteInputSpec,
    pub provenance: RouteProvenance,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NetworkTopologyKind {
    FullyConnected,
    BidirectionalRing,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LinkEvidenceKind {
    MeasuredCalibration,
    PublishedSpecification,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TopologyEvidence {
    pub kind: LinkEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LinkCalibrationAssumption {
    pub payload_bytes_per_second_per_direction: u64,
    pub evidence: TopologyEvidence,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceShardMappingPolicy {
    ModuloDeviceCount,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DispatchPolicy {
    LocalReplicaFirstThenLeastLoadedReplica,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NetworkRoutingPolicy {
    ShortestHopLowestDeviceTieBreak,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeviceTopologySpec {
    pub topology_id: String,
    pub device_count: u32,
    pub expert_memory_capacity_bytes_per_device: u64,
    pub network: NetworkTopologyKind,
    pub routing: NetworkRoutingPolicy,
    pub link: LinkCalibrationAssumption,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum PlacementPolicy {
    Uniform,
    TrafficAware {
        additional_replica_budget: u64,
        maximum_replicas_per_expert: u32,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlacementStrategySpec {
    pub strategy_id: String,
    pub policy: PlacementPolicy,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMoeRouteRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub geometry: GlmMoeGeometry,
    pub traffic: InterconnectTrafficAssumptions,
    pub source_shard_mapping: SourceShardMappingPolicy,
    pub dispatch_policy: DispatchPolicy,
    pub scenarios: Vec<RouteScenarioSpec>,
    pub topologies: Vec<DeviceTopologySpec>,
    pub strategies: Vec<PlacementStrategySpec>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlacementCapacityReport {
    pub expert_slot_capacity_per_device: u64,
    pub total_expert_slot_capacity: u64,
    pub primary_expert_instances: u64,
    pub requested_additional_replicas: u64,
    pub placed_additional_replicas: u64,
    pub total_resident_expert_instances: u64,
    pub total_resident_expert_bytes: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DevicePlacementLoadReport {
    pub device_id: u32,
    pub expert_memory_capacity_bytes: u64,
    pub expert_slot_capacity: u64,
    pub resident_expert_instances: u64,
    pub resident_expert_bytes: u64,
    pub source_dispatches: u64,
    pub destination_dispatches: u64,
    pub local_dispatches_served: u64,
    pub remote_dispatches_received: u64,
    pub remote_dispatches_sent: u64,
    pub load_to_mean_basis_points: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LoadBalanceReport {
    pub minimum_device_dispatches: u64,
    pub maximum_device_dispatches: u64,
    pub mean_dispatches_numerator: u64,
    pub mean_dispatches_denominator: u32,
    pub max_to_mean_basis_points: u32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExpertTrafficReport {
    pub total_dispatches: u64,
    pub local_dispatches: u64,
    pub remote_dispatches: u64,
    pub local_dispatch_fraction_basis_points: u32,
    pub remote_flow_count: u64,
    pub endpoint_payload_bytes_lower_bound: u64,
    pub endpoint_message_count_lower_bound: u64,
    pub network_hop_payload_bytes_lower_bound: u64,
    pub network_hop_message_count_lower_bound: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TopologyLinkLoadReport {
    pub endpoint_a: u32,
    pub endpoint_b: u32,
    pub a_to_b_payload_bytes_lower_bound: u64,
    pub b_to_a_payload_bytes_lower_bound: u64,
    pub a_to_b_message_count_lower_bound: u64,
    pub b_to_a_message_count_lower_bound: u64,
    pub total_payload_bytes_lower_bound: u64,
    pub total_message_count_lower_bound: u64,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum LinkSerializationBlocker {
    RouteHistogramIsNotMeasured,
    LinkBandwidthIsNotMeasured,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EndToEndClaimBlocker {
    RouteHistogramIsNotMeasured,
    LinkBandwidthIsNotMeasured,
    MissingMeasuredEndToEndServingEvidence,
    MissingEconomicUtilizationEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EndToEndClaimReport {
    pub end_to_end_latency_seconds_per_token: Option<f64>,
    pub cost_per_million_output_tokens_usd: Option<f64>,
    pub blockers: Vec<EndToEndClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PlacementSimulationReport {
    pub strategy_id: String,
    pub policy: PlacementPolicy,
    pub capacity: PlacementCapacityReport,
    pub devices: Vec<DevicePlacementLoadReport>,
    pub load_balance: LoadBalanceReport,
    pub traffic: ExpertTrafficReport,
    pub links: Vec<TopologyLinkLoadReport>,
    pub link_serialization_time_lower_bound_seconds: Option<f64>,
    pub link_serialization_blockers: Vec<LinkSerializationBlocker>,
    pub claims: EndToEndClaimReport,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TopologySimulationReport {
    pub topology_id: String,
    pub device_count: u32,
    pub network: NetworkTopologyKind,
    pub routing: NetworkRoutingPolicy,
    pub link: LinkCalibrationAssumption,
    pub strategies: Vec<PlacementSimulationReport>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RouteScenarioReport {
    pub scenario_id: String,
    pub route_input_content_id: String,
    pub source_shard_count: u32,
    pub tokens_per_layer: u64,
    pub dispatches_per_layer: u64,
    pub provenance: RouteProvenance,
    pub topologies: Vec<TopologySimulationReport>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMoeRouteResult {
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub geometry: GlmMoeGeometry,
    pub traffic_assumptions: InterconnectTrafficAssumptions,
    pub source_shard_mapping: SourceShardMappingPolicy,
    pub dispatch_policy: DispatchPolicy,
    pub scenarios: Vec<RouteScenarioReport>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmMoeRouteReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmMoeRouteResult,
}

impl GlmMoeRouteReport {
    pub fn verify_content_id(&self) -> Result<bool, GlmMoeRouteError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

#[derive(Clone)]
struct ExpandedScenario {
    source_shard_count: u32,
    layers: Vec<LayerRouteHistogram>,
}

struct ExpertDemand {
    layer_index: u32,
    expert_index: u32,
    total_dispatches: u64,
    dispatches_by_source_device: Vec<u64>,
}

struct Placement {
    replicas_by_expert: Vec<Vec<u32>>,
    resident_experts_by_device: Vec<u64>,
    requested_additional_replicas: u64,
    placed_additional_replicas: u64,
}

#[derive(Clone, Copy, Default)]
struct DirectedLinkLoad {
    payload_bytes: u64,
    message_count: u64,
}

pub fn evaluate_glm_moe_routes(
    request: &GlmMoeRouteRequest,
) -> Result<GlmMoeRouteReport, GlmMoeRouteError> {
    validate_request(request)?;
    let scenarios = request
        .scenarios
        .iter()
        .map(|scenario| evaluate_scenario(request, scenario))
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmMoeRouteResult {
        study_id: request.study_id.clone(),
        model_id: request.model_id.clone(),
        model_revision: request.model_revision.clone(),
        geometry: request.geometry,
        traffic_assumptions: request.traffic.clone(),
        source_shard_mapping: request.source_shard_mapping,
        dispatch_policy: request.dispatch_policy,
        scenarios,
    };
    let schema_version = GLM_MOE_ROUTE_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmMoeRouteReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &GlmMoeRouteRequest) -> Result<(), GlmMoeRouteError> {
    if request.schema_version != GLM_MOE_ROUTE_REQUEST_SCHEMA_VERSION {
        return Err(GlmMoeRouteError::UnsupportedSchemaVersion {
            expected: GLM_MOE_ROUTE_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    for (field, value) in [
        ("study_id", request.study_id.as_str()),
        ("model_id", request.model_id.as_str()),
        ("model_revision", request.model_revision.as_str()),
        (
            "traffic.source_artifact_id",
            request.traffic.source_artifact_id.as_str(),
        ),
        ("traffic.basis", request.traffic.basis.as_str()),
    ] {
        validate_required(field, value)?;
    }
    if request.geometry.moe_layer_count != GLM_MOE_LAYER_COUNT
        || request.geometry.routed_expert_count != GLM_MOE_EXPERT_COUNT
        || request.geometry.top_k != GLM_MOE_TOP_K
    {
        return Err(GlmMoeRouteError::InvalidGlmGeometry);
    }
    if request.traffic.expert_storage_bytes == 0
        || request.traffic.activation_payload_bytes_per_dispatch == 0
        || request.traffic.result_payload_bytes_per_dispatch == 0
    {
        return Err(GlmMoeRouteError::InvalidField("traffic"));
    }
    validate_scenarios(request)?;
    validate_topologies(request)?;
    validate_strategies(request)?;
    validate_cross_product_capacity(request)
}

fn validate_scenarios(request: &GlmMoeRouteRequest) -> Result<(), GlmMoeRouteError> {
    if request.scenarios.is_empty() {
        return Err(GlmMoeRouteError::InvalidField("scenarios"));
    }
    let mut ids = BTreeSet::new();
    for scenario in &request.scenarios {
        validate_required("scenarios.scenario_id", &scenario.scenario_id)?;
        if !ids.insert(scenario.scenario_id.as_str()) {
            return Err(GlmMoeRouteError::DuplicateScenario(
                scenario.scenario_id.clone(),
            ));
        }
        for (field, value) in [
            (
                "scenarios.provenance.source_artifact_id",
                scenario.provenance.source_artifact_id.as_str(),
            ),
            (
                "scenarios.provenance.model_id",
                scenario.provenance.model_id.as_str(),
            ),
            (
                "scenarios.provenance.model_revision",
                scenario.provenance.model_revision.as_str(),
            ),
        ] {
            validate_required(field, value)?;
        }
        if scenario.provenance.model_id != request.model_id
            || scenario.provenance.model_revision != request.model_revision
        {
            return Err(GlmMoeRouteError::RouteModelIdentityMismatch(
                scenario.scenario_id.clone(),
            ));
        }
        match &scenario.route {
            RouteInputSpec::Synthetic(spec) => {
                if scenario.provenance.kind != RouteEvidenceKind::ModeledAssumption {
                    return Err(GlmMoeRouteError::SyntheticRouteIsNotModeled(
                        scenario.scenario_id.clone(),
                    ));
                }
                validate_synthetic(spec)?;
                validate_histogram(&generate_synthetic(spec)?)?;
            }
            RouteInputSpec::PinnedHistogram(histogram) => validate_histogram(histogram)?,
        }
    }
    Ok(())
}

fn validate_synthetic(spec: &SyntheticRouteSpec) -> Result<(), GlmMoeRouteError> {
    if spec.source_shard_count == 0
        || spec.source_shard_count > GLM_MOE_EXPERT_COUNT
        || spec.tokens_per_source_shard == 0
    {
        return Err(GlmMoeRouteError::InvalidField("scenarios.route.synthetic"));
    }
    if let SyntheticRouteDistribution::RotatingHotset {
        hot_expert_count,
        hot_dispatch_share_basis_points,
        layer_rotation_stride,
        source_rotation_stride,
    } = spec.distribution
        && (hot_expert_count == 0
            || hot_expert_count >= GLM_MOE_EXPERT_COUNT
            || hot_dispatch_share_basis_points == 0
            || hot_dispatch_share_basis_points >= 10_000
            || layer_rotation_stride == 0
            || source_rotation_stride == 0)
    {
        return Err(GlmMoeRouteError::InvalidField(
            "scenarios.route.synthetic.distribution",
        ));
    }
    Ok(())
}

fn validate_histogram(histogram: &PinnedRouteHistogram) -> Result<(), GlmMoeRouteError> {
    if histogram.source_shard_count == 0 || histogram.layers.len() != GLM_MOE_LAYER_COUNT as usize {
        return Err(GlmMoeRouteError::InvalidHistogramShape);
    }
    let mut expected_tokens: Option<Vec<u64>> = None;
    for (expected_layer, layer) in histogram.layers.iter().enumerate() {
        if layer.layer_index != expected_layer as u32
            || layer.sources.len() != histogram.source_shard_count as usize
        {
            return Err(GlmMoeRouteError::InvalidHistogramShape);
        }
        for (expected_source, source) in layer.sources.iter().enumerate() {
            if source.source_shard != expected_source as u32
                || source.token_count == 0
                || source.expert_dispatch_counts.len() != GLM_MOE_EXPERT_COUNT as usize
            {
                return Err(GlmMoeRouteError::InvalidHistogramShape);
            }
            if let Some(tokens) = expected_tokens.as_ref() {
                if tokens[expected_source] != source.token_count {
                    return Err(GlmMoeRouteError::InconsistentHistogramTokenCount);
                }
            }
            let expected_dispatches = source
                .token_count
                .checked_mul(u64::from(GLM_MOE_TOP_K))
                .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
            let actual_dispatches = checked_sum(&source.expert_dispatch_counts)?;
            if actual_dispatches != expected_dispatches
                || source
                    .expert_dispatch_counts
                    .iter()
                    .any(|count| *count > source.token_count)
            {
                return Err(GlmMoeRouteError::InvalidHistogramDispatchLedger {
                    layer_index: layer.layer_index,
                    source_shard: source.source_shard,
                });
            }
        }
        if expected_tokens.is_none() {
            expected_tokens = Some(
                layer
                    .sources
                    .iter()
                    .map(|source| source.token_count)
                    .collect::<Vec<_>>(),
            );
        }
    }
    Ok(())
}

fn validate_topologies(request: &GlmMoeRouteRequest) -> Result<(), GlmMoeRouteError> {
    if request.topologies.is_empty() {
        return Err(GlmMoeRouteError::InvalidField("topologies"));
    }
    let mut ids = BTreeSet::new();
    for topology in &request.topologies {
        validate_required("topologies.topology_id", &topology.topology_id)?;
        validate_required(
            "topologies.link.evidence.source_artifact_id",
            &topology.link.evidence.source_artifact_id,
        )?;
        if !ids.insert(topology.topology_id.as_str()) {
            return Err(GlmMoeRouteError::DuplicateTopology(
                topology.topology_id.clone(),
            ));
        }
        if topology.device_count < 2
            || topology.device_count > GLM_MOE_EXPERT_COUNT
            || matches!(topology.network, NetworkTopologyKind::BidirectionalRing)
                && topology.device_count < 3
            || topology.expert_memory_capacity_bytes_per_device == 0
            || topology.link.payload_bytes_per_second_per_direction == 0
        {
            return Err(GlmMoeRouteError::InvalidField("topologies"));
        }
        for scenario in &request.scenarios {
            let source_shards = source_shard_count(&scenario.route);
            if source_shards % topology.device_count != 0 {
                return Err(GlmMoeRouteError::SourceShardsDoNotMapEvenly {
                    scenario_id: scenario.scenario_id.clone(),
                    topology_id: topology.topology_id.clone(),
                });
            }
        }
    }
    Ok(())
}

fn validate_strategies(request: &GlmMoeRouteRequest) -> Result<(), GlmMoeRouteError> {
    if request.strategies.is_empty() {
        return Err(GlmMoeRouteError::InvalidField("strategies"));
    }
    let mut ids = BTreeSet::new();
    for strategy in &request.strategies {
        validate_required("strategies.strategy_id", &strategy.strategy_id)?;
        if !ids.insert(strategy.strategy_id.as_str()) {
            return Err(GlmMoeRouteError::DuplicateStrategy(
                strategy.strategy_id.clone(),
            ));
        }
        if let PlacementPolicy::TrafficAware {
            maximum_replicas_per_expert,
            ..
        } = strategy.policy
            && maximum_replicas_per_expert == 0
        {
            return Err(GlmMoeRouteError::InvalidField("strategies.policy"));
        }
    }
    Ok(())
}

fn validate_cross_product_capacity(request: &GlmMoeRouteRequest) -> Result<(), GlmMoeRouteError> {
    let primary_count = u64::from(GLM_MOE_LAYER_COUNT)
        .checked_mul(u64::from(GLM_MOE_EXPERT_COUNT))
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    for topology in &request.topologies {
        let slots_per_device =
            topology.expert_memory_capacity_bytes_per_device / request.traffic.expert_storage_bytes;
        let total_slots = slots_per_device
            .checked_mul(u64::from(topology.device_count))
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
        if total_slots < primary_count {
            return Err(GlmMoeRouteError::InsufficientExpertCapacity(
                topology.topology_id.clone(),
            ));
        }
        for strategy in &request.strategies {
            if let PlacementPolicy::TrafficAware {
                additional_replica_budget,
                maximum_replicas_per_expert,
            } = strategy.policy
            {
                if maximum_replicas_per_expert > topology.device_count
                    || additional_replica_budget > total_slots - primary_count
                {
                    return Err(GlmMoeRouteError::InsufficientReplicationCapacity {
                        topology_id: topology.topology_id.clone(),
                        strategy_id: strategy.strategy_id.clone(),
                    });
                }
            }
        }
    }
    Ok(())
}

fn evaluate_scenario(
    request: &GlmMoeRouteRequest,
    scenario: &RouteScenarioSpec,
) -> Result<RouteScenarioReport, GlmMoeRouteError> {
    let expanded = expand_scenario(scenario)?;
    let tokens_per_layer = checked_sum(
        &expanded.layers[0]
            .sources
            .iter()
            .map(|source| source.token_count)
            .collect::<Vec<_>>(),
    )?;
    let dispatches_per_layer = tokens_per_layer
        .checked_mul(u64::from(GLM_MOE_TOP_K))
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let topologies = request
        .topologies
        .iter()
        .map(|topology| evaluate_topology(request, scenario, &expanded, topology))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(RouteScenarioReport {
        scenario_id: scenario.scenario_id.clone(),
        route_input_content_id: route_input_content_id(&scenario.route)?,
        source_shard_count: expanded.source_shard_count,
        tokens_per_layer,
        dispatches_per_layer,
        provenance: scenario.provenance.clone(),
        topologies,
    })
}

fn evaluate_topology(
    request: &GlmMoeRouteRequest,
    scenario: &RouteScenarioSpec,
    expanded: &ExpandedScenario,
    topology: &DeviceTopologySpec,
) -> Result<TopologySimulationReport, GlmMoeRouteError> {
    let demands = build_demands(expanded, topology.device_count)?;
    let links = topology_links(topology.device_count, topology.network);
    let paths = shortest_paths(topology.device_count, &links)?;
    let strategies = request
        .strategies
        .iter()
        .map(|strategy| {
            evaluate_strategy(
                request, scenario, topology, strategy, &demands, &links, &paths,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(TopologySimulationReport {
        topology_id: topology.topology_id.clone(),
        device_count: topology.device_count,
        network: topology.network,
        routing: topology.routing,
        link: topology.link.clone(),
        strategies,
    })
}

fn evaluate_strategy(
    request: &GlmMoeRouteRequest,
    scenario: &RouteScenarioSpec,
    topology: &DeviceTopologySpec,
    strategy: &PlacementStrategySpec,
    demands: &[ExpertDemand],
    links: &[(u32, u32)],
    paths: &[Vec<Vec<u32>>],
) -> Result<PlacementSimulationReport, GlmMoeRouteError> {
    let slots_per_device =
        topology.expert_memory_capacity_bytes_per_device / request.traffic.expert_storage_bytes;
    let placement = place_experts(demands, topology.device_count, slots_per_device, strategy)?;
    let simulation = simulate_dispatch(request, topology, demands, &placement, links, paths)?;
    let primary_expert_instances =
        u64::try_from(demands.len()).map_err(|_| GlmMoeRouteError::ArithmeticOverflow)?;
    let total_resident_expert_instances = checked_sum(&placement.resident_experts_by_device)?;
    let total_resident_expert_bytes = total_resident_expert_instances
        .checked_mul(request.traffic.expert_storage_bytes)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let capacity = PlacementCapacityReport {
        expert_slot_capacity_per_device: slots_per_device,
        total_expert_slot_capacity: slots_per_device
            .checked_mul(u64::from(topology.device_count))
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?,
        primary_expert_instances,
        requested_additional_replicas: placement.requested_additional_replicas,
        placed_additional_replicas: placement.placed_additional_replicas,
        total_resident_expert_instances,
        total_resident_expert_bytes,
    };
    let (link_serialization_time_lower_bound_seconds, link_serialization_blockers) =
        link_serialization(scenario, topology, &simulation.links);
    let claims = end_to_end_claims(scenario, topology);
    Ok(PlacementSimulationReport {
        strategy_id: strategy.strategy_id.clone(),
        policy: strategy.policy,
        capacity,
        devices: simulation.devices,
        load_balance: simulation.load_balance,
        traffic: simulation.traffic,
        links: simulation.links,
        link_serialization_time_lower_bound_seconds,
        link_serialization_blockers,
        claims,
    })
}

fn expand_scenario(scenario: &RouteScenarioSpec) -> Result<ExpandedScenario, GlmMoeRouteError> {
    let histogram = match &scenario.route {
        RouteInputSpec::Synthetic(spec) => generate_synthetic(spec)?,
        RouteInputSpec::PinnedHistogram(histogram) => histogram.clone(),
    };
    Ok(ExpandedScenario {
        source_shard_count: histogram.source_shard_count,
        layers: histogram.layers,
    })
}

fn generate_synthetic(spec: &SyntheticRouteSpec) -> Result<PinnedRouteHistogram, GlmMoeRouteError> {
    let dispatches = spec
        .tokens_per_source_shard
        .checked_mul(u64::from(GLM_MOE_TOP_K))
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let layers = (0..GLM_MOE_LAYER_COUNT)
        .map(|layer_index| {
            let sources = (0..spec.source_shard_count)
                .map(|source_shard| {
                    let expert_dispatch_counts = match spec.distribution {
                        SyntheticRouteDistribution::Uniform => allocate_uniform(
                            dispatches,
                            GLM_MOE_EXPERT_COUNT,
                            (layer_index + source_shard) % GLM_MOE_EXPERT_COUNT,
                        )?,
                        SyntheticRouteDistribution::RotatingHotset {
                            hot_expert_count,
                            hot_dispatch_share_basis_points,
                            layer_rotation_stride,
                            source_rotation_stride,
                        } => allocate_hotset(
                            dispatches,
                            hot_expert_count,
                            hot_dispatch_share_basis_points,
                            (layer_index
                                .checked_mul(layer_rotation_stride)
                                .and_then(|value| {
                                    source_shard
                                        .checked_mul(source_rotation_stride)
                                        .and_then(|source| value.checked_add(source))
                                })
                                .ok_or(GlmMoeRouteError::ArithmeticOverflow)?)
                                % GLM_MOE_EXPERT_COUNT,
                        )?,
                    };
                    Ok(SourceRouteHistogram {
                        source_shard,
                        token_count: spec.tokens_per_source_shard,
                        expert_dispatch_counts,
                    })
                })
                .collect::<Result<Vec<_>, GlmMoeRouteError>>()?;
            Ok(LayerRouteHistogram {
                layer_index,
                sources,
            })
        })
        .collect::<Result<Vec<_>, GlmMoeRouteError>>()?;
    Ok(PinnedRouteHistogram {
        source_shard_count: spec.source_shard_count,
        layers,
    })
}

fn allocate_uniform(
    dispatches: u64,
    expert_count: u32,
    start: u32,
) -> Result<Vec<u64>, GlmMoeRouteError> {
    let mut counts = vec![dispatches / u64::from(expert_count); expert_count as usize];
    let remainder = dispatches % u64::from(expert_count);
    for offset in 0..remainder {
        let expert = (u64::from(start) + offset) % u64::from(expert_count);
        counts[expert as usize] = counts[expert as usize]
            .checked_add(1)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    }
    Ok(counts)
}

fn allocate_hotset(
    dispatches: u64,
    hot_expert_count: u32,
    hot_share_basis_points: u32,
    start: u32,
) -> Result<Vec<u64>, GlmMoeRouteError> {
    let hot_dispatches = u64::try_from(
        u128::from(dispatches)
            .checked_mul(u128::from(hot_share_basis_points))
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?
            / 10_000,
    )
    .map_err(|_| GlmMoeRouteError::ArithmeticOverflow)?;
    let cold_dispatches = dispatches
        .checked_sub(hot_dispatches)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let hot_indices = (0..hot_expert_count)
        .map(|offset| (start + offset) % GLM_MOE_EXPERT_COUNT)
        .collect::<Vec<_>>();
    let hot_set = hot_indices.iter().copied().collect::<BTreeSet<_>>();
    let cold_indices = (0..GLM_MOE_EXPERT_COUNT)
        .map(|offset| (start + offset) % GLM_MOE_EXPERT_COUNT)
        .filter(|expert| !hot_set.contains(expert))
        .collect::<Vec<_>>();
    let mut counts = vec![0_u64; GLM_MOE_EXPERT_COUNT as usize];
    allocate_to_indices(&mut counts, hot_dispatches, &hot_indices)?;
    allocate_to_indices(&mut counts, cold_dispatches, &cold_indices)?;
    Ok(counts)
}

fn allocate_to_indices(
    counts: &mut [u64],
    dispatches: u64,
    indices: &[u32],
) -> Result<(), GlmMoeRouteError> {
    let count = u64::try_from(indices.len()).map_err(|_| GlmMoeRouteError::ArithmeticOverflow)?;
    let base = dispatches / count;
    let remainder = dispatches % count;
    for (position, expert) in indices.iter().enumerate() {
        counts[*expert as usize] = base
            .checked_add(u64::from((position as u64) < remainder))
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    }
    Ok(())
}

fn build_demands(
    scenario: &ExpandedScenario,
    device_count: u32,
) -> Result<Vec<ExpertDemand>, GlmMoeRouteError> {
    let mut demands =
        Vec::with_capacity((GLM_MOE_LAYER_COUNT as usize) * (GLM_MOE_EXPERT_COUNT as usize));
    for layer in &scenario.layers {
        for expert_index in 0..GLM_MOE_EXPERT_COUNT {
            let mut by_device = vec![0_u64; device_count as usize];
            for source in &layer.sources {
                let device = source.source_shard % device_count;
                by_device[device as usize] = by_device[device as usize]
                    .checked_add(source.expert_dispatch_counts[expert_index as usize])
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
            }
            demands.push(ExpertDemand {
                layer_index: layer.layer_index,
                expert_index,
                total_dispatches: checked_sum(&by_device)?,
                dispatches_by_source_device: by_device,
            });
        }
    }
    Ok(demands)
}

fn place_experts(
    demands: &[ExpertDemand],
    device_count: u32,
    slots_per_device: u64,
    strategy: &PlacementStrategySpec,
) -> Result<Placement, GlmMoeRouteError> {
    match strategy.policy {
        PlacementPolicy::Uniform => place_uniform(demands, device_count, slots_per_device),
        PlacementPolicy::TrafficAware {
            additional_replica_budget,
            maximum_replicas_per_expert,
        } => place_traffic_aware(
            demands,
            device_count,
            slots_per_device,
            additional_replica_budget,
            maximum_replicas_per_expert,
        ),
    }
}

fn place_uniform(
    demands: &[ExpertDemand],
    device_count: u32,
    slots_per_device: u64,
) -> Result<Placement, GlmMoeRouteError> {
    let mut replicas = vec![Vec::new(); demands.len()];
    let mut resident = vec![0_u64; device_count as usize];
    for (index, expert_replicas) in replicas.iter_mut().enumerate() {
        let device =
            u32::try_from(index).map_err(|_| GlmMoeRouteError::ArithmeticOverflow)? % device_count;
        resident[device as usize] = resident[device as usize]
            .checked_add(1)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
        if resident[device as usize] > slots_per_device {
            return Err(GlmMoeRouteError::PlacementCapacityExceeded);
        }
        expert_replicas.push(device);
    }
    Ok(Placement {
        replicas_by_expert: replicas,
        resident_experts_by_device: resident,
        requested_additional_replicas: 0,
        placed_additional_replicas: 0,
    })
}

fn place_traffic_aware(
    demands: &[ExpertDemand],
    device_count: u32,
    slots_per_device: u64,
    replica_budget: u64,
    maximum_replicas: u32,
) -> Result<Placement, GlmMoeRouteError> {
    let mut order = (0..demands.len()).collect::<Vec<_>>();
    order.sort_by_key(|index| {
        let demand = &demands[*index];
        (
            Reverse(demand.total_dispatches),
            demand.layer_index,
            demand.expert_index,
        )
    });
    let mut replicas = vec![Vec::new(); demands.len()];
    let mut resident = vec![0_u64; device_count as usize];
    let mut predicted_load = vec![0_u64; device_count as usize];
    for index in order {
        let demand = &demands[index];
        let device = (0..device_count)
            .filter(|device| resident[*device as usize] < slots_per_device)
            .min_by_key(|device| {
                (
                    Reverse(demand.dispatches_by_source_device[*device as usize]),
                    predicted_load[*device as usize],
                    resident[*device as usize],
                    *device,
                )
            })
            .ok_or(GlmMoeRouteError::PlacementCapacityExceeded)?;
        replicas[index].push(device);
        resident[device as usize] = resident[device as usize]
            .checked_add(1)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
        predicted_load[device as usize] = predicted_load[device as usize]
            .checked_add(demand.total_dispatches)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    }
    let mut candidates = Vec::new();
    for (index, demand) in demands.iter().enumerate() {
        for device in 0..device_count {
            if !replicas[index].contains(&device) {
                candidates.push((
                    demand.dispatches_by_source_device[device as usize],
                    demand.total_dispatches,
                    demand.layer_index,
                    demand.expert_index,
                    index,
                    device,
                ));
            }
        }
    }
    candidates.sort_by_key(|candidate| {
        (
            Reverse(candidate.0),
            Reverse(candidate.1),
            candidate.2,
            candidate.3,
            candidate.5,
        )
    });
    let mut placed = 0_u64;
    for (gain, _, _, _, index, device) in candidates {
        if placed == replica_budget {
            break;
        }
        if gain == 0
            || replicas[index].len() >= maximum_replicas as usize
            || resident[device as usize] >= slots_per_device
            || replicas[index].contains(&device)
        {
            continue;
        }
        replicas[index].push(device);
        replicas[index].sort_unstable();
        resident[device as usize] = resident[device as usize]
            .checked_add(1)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
        placed = placed
            .checked_add(1)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    }
    Ok(Placement {
        replicas_by_expert: replicas,
        resident_experts_by_device: resident,
        requested_additional_replicas: replica_budget,
        placed_additional_replicas: placed,
    })
}

struct DispatchSimulation {
    devices: Vec<DevicePlacementLoadReport>,
    load_balance: LoadBalanceReport,
    traffic: ExpertTrafficReport,
    links: Vec<TopologyLinkLoadReport>,
}

fn simulate_dispatch(
    request: &GlmMoeRouteRequest,
    topology: &DeviceTopologySpec,
    demands: &[ExpertDemand],
    placement: &Placement,
    links: &[(u32, u32)],
    paths: &[Vec<Vec<u32>>],
) -> Result<DispatchSimulation, GlmMoeRouteError> {
    let device_count = topology.device_count as usize;
    let mut source_dispatches = vec![0_u64; device_count];
    let mut destination_dispatches = vec![0_u64; device_count];
    let mut local_dispatches_served = vec![0_u64; device_count];
    let mut remote_received = vec![0_u64; device_count];
    let mut remote_sent = vec![0_u64; device_count];
    let mut local_dispatches = 0_u64;
    let mut remote_dispatches = 0_u64;
    let mut remote_flow_count = 0_u64;
    let mut directed_links = BTreeMap::<(u32, u32), DirectedLinkLoad>::new();
    for (index, demand) in demands.iter().enumerate() {
        let replicas = &placement.replicas_by_expert[index];
        for source in 0..topology.device_count {
            let count = demand.dispatches_by_source_device[source as usize];
            if count == 0 {
                continue;
            }
            source_dispatches[source as usize] = source_dispatches[source as usize]
                .checked_add(count)
                .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
            let destination = if replicas.contains(&source) {
                source
            } else {
                *replicas
                    .iter()
                    .min_by_key(|device| (destination_dispatches[**device as usize], **device))
                    .ok_or(GlmMoeRouteError::PlacementCapacityExceeded)?
            };
            destination_dispatches[destination as usize] = destination_dispatches
                [destination as usize]
                .checked_add(count)
                .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
            if source == destination {
                local_dispatches = local_dispatches
                    .checked_add(count)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
                local_dispatches_served[source as usize] = local_dispatches_served[source as usize]
                    .checked_add(count)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
            } else {
                remote_dispatches = remote_dispatches
                    .checked_add(count)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
                remote_flow_count = remote_flow_count
                    .checked_add(1)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
                remote_sent[source as usize] = remote_sent[source as usize]
                    .checked_add(count)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
                remote_received[destination as usize] = remote_received[destination as usize]
                    .checked_add(count)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
                add_path_load(
                    &mut directed_links,
                    &paths[source as usize][destination as usize],
                    count,
                    request.traffic.activation_payload_bytes_per_dispatch,
                )?;
                let mut reverse = paths[source as usize][destination as usize].clone();
                reverse.reverse();
                add_path_load(
                    &mut directed_links,
                    &reverse,
                    count,
                    request.traffic.result_payload_bytes_per_dispatch,
                )?;
            }
        }
    }
    let total_dispatches = checked_sum(&destination_dispatches)?;
    if local_dispatches
        .checked_add(remote_dispatches)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?
        != total_dispatches
    {
        return Err(GlmMoeRouteError::LedgerInvariantViolation);
    }
    let endpoint_bytes_per_remote = request
        .traffic
        .activation_payload_bytes_per_dispatch
        .checked_add(request.traffic.result_payload_bytes_per_dispatch)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let endpoint_payload_bytes_lower_bound = remote_dispatches
        .checked_mul(endpoint_bytes_per_remote)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let endpoint_message_count_lower_bound = remote_flow_count
        .checked_mul(2)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let link_reports = build_link_reports(links, &directed_links)?;
    let network_hop_payload_bytes_lower_bound = link_reports
        .iter()
        .try_fold(0_u64, |sum, link| {
            sum.checked_add(link.total_payload_bytes_lower_bound)
        })
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let network_hop_message_count_lower_bound = link_reports
        .iter()
        .try_fold(0_u64, |sum, link| {
            sum.checked_add(link.total_message_count_lower_bound)
        })
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    let devices = build_device_reports(
        request,
        topology,
        placement,
        &source_dispatches,
        &destination_dispatches,
        &local_dispatches_served,
        &remote_received,
        &remote_sent,
        total_dispatches,
    )?;
    let minimum_device_dispatches = destination_dispatches.iter().copied().min().unwrap_or(0);
    let maximum_device_dispatches = destination_dispatches.iter().copied().max().unwrap_or(0);
    let load_balance = LoadBalanceReport {
        minimum_device_dispatches,
        maximum_device_dispatches,
        mean_dispatches_numerator: total_dispatches,
        mean_dispatches_denominator: topology.device_count,
        max_to_mean_basis_points: ratio_to_mean_basis_points(
            maximum_device_dispatches,
            total_dispatches,
            topology.device_count,
        )?,
    };
    let traffic = ExpertTrafficReport {
        total_dispatches,
        local_dispatches,
        remote_dispatches,
        local_dispatch_fraction_basis_points: fraction_basis_points(
            local_dispatches,
            total_dispatches,
        )?,
        remote_flow_count,
        endpoint_payload_bytes_lower_bound,
        endpoint_message_count_lower_bound,
        network_hop_payload_bytes_lower_bound,
        network_hop_message_count_lower_bound,
    };
    Ok(DispatchSimulation {
        devices,
        load_balance,
        traffic,
        links: link_reports,
    })
}

#[allow(clippy::too_many_arguments)]
fn build_device_reports(
    request: &GlmMoeRouteRequest,
    topology: &DeviceTopologySpec,
    placement: &Placement,
    source_dispatches: &[u64],
    destination_dispatches: &[u64],
    local_dispatches_served: &[u64],
    remote_received: &[u64],
    remote_sent: &[u64],
    total_dispatches: u64,
) -> Result<Vec<DevicePlacementLoadReport>, GlmMoeRouteError> {
    let slots =
        topology.expert_memory_capacity_bytes_per_device / request.traffic.expert_storage_bytes;
    (0..topology.device_count)
        .map(|device| {
            let resident_expert_instances = placement.resident_experts_by_device[device as usize];
            Ok(DevicePlacementLoadReport {
                device_id: device,
                expert_memory_capacity_bytes: topology.expert_memory_capacity_bytes_per_device,
                expert_slot_capacity: slots,
                resident_expert_instances,
                resident_expert_bytes: resident_expert_instances
                    .checked_mul(request.traffic.expert_storage_bytes)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?,
                source_dispatches: source_dispatches[device as usize],
                destination_dispatches: destination_dispatches[device as usize],
                local_dispatches_served: local_dispatches_served[device as usize],
                remote_dispatches_received: remote_received[device as usize],
                remote_dispatches_sent: remote_sent[device as usize],
                load_to_mean_basis_points: ratio_to_mean_basis_points(
                    destination_dispatches[device as usize],
                    total_dispatches,
                    topology.device_count,
                )?,
            })
        })
        .collect()
}

fn add_path_load(
    directed_links: &mut BTreeMap<(u32, u32), DirectedLinkLoad>,
    path: &[u32],
    dispatch_count: u64,
    payload_bytes_per_dispatch: u64,
) -> Result<(), GlmMoeRouteError> {
    let payload = dispatch_count
        .checked_mul(payload_bytes_per_dispatch)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    for edge in path.windows(2) {
        let load = directed_links.entry((edge[0], edge[1])).or_default();
        load.payload_bytes = load
            .payload_bytes
            .checked_add(payload)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
        load.message_count = load
            .message_count
            .checked_add(1)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    }
    Ok(())
}

fn build_link_reports(
    links: &[(u32, u32)],
    directed: &BTreeMap<(u32, u32), DirectedLinkLoad>,
) -> Result<Vec<TopologyLinkLoadReport>, GlmMoeRouteError> {
    links
        .iter()
        .map(|(a, b)| {
            let a_to_b = directed.get(&(*a, *b)).copied().unwrap_or_default();
            let b_to_a = directed.get(&(*b, *a)).copied().unwrap_or_default();
            Ok(TopologyLinkLoadReport {
                endpoint_a: *a,
                endpoint_b: *b,
                a_to_b_payload_bytes_lower_bound: a_to_b.payload_bytes,
                b_to_a_payload_bytes_lower_bound: b_to_a.payload_bytes,
                a_to_b_message_count_lower_bound: a_to_b.message_count,
                b_to_a_message_count_lower_bound: b_to_a.message_count,
                total_payload_bytes_lower_bound: a_to_b
                    .payload_bytes
                    .checked_add(b_to_a.payload_bytes)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?,
                total_message_count_lower_bound: a_to_b
                    .message_count
                    .checked_add(b_to_a.message_count)
                    .ok_or(GlmMoeRouteError::ArithmeticOverflow)?,
            })
        })
        .collect()
}

fn topology_links(device_count: u32, topology: NetworkTopologyKind) -> Vec<(u32, u32)> {
    match topology {
        NetworkTopologyKind::FullyConnected => (0..device_count)
            .flat_map(|a| ((a + 1)..device_count).map(move |b| (a, b)))
            .collect(),
        NetworkTopologyKind::BidirectionalRing => {
            let mut links = BTreeSet::new();
            for device in 0..device_count {
                let peer = (device + 1) % device_count;
                links.insert((device.min(peer), device.max(peer)));
            }
            links.into_iter().collect()
        }
    }
}

fn shortest_paths(
    device_count: u32,
    links: &[(u32, u32)],
) -> Result<Vec<Vec<Vec<u32>>>, GlmMoeRouteError> {
    let mut adjacency = vec![Vec::new(); device_count as usize];
    for (a, b) in links {
        adjacency[*a as usize].push(*b);
        adjacency[*b as usize].push(*a);
    }
    for neighbors in &mut adjacency {
        neighbors.sort_unstable();
    }
    (0..device_count)
        .map(|source| {
            (0..device_count)
                .map(|destination| shortest_path(source, destination, &adjacency))
                .collect()
        })
        .collect()
}

fn shortest_path(
    source: u32,
    destination: u32,
    adjacency: &[Vec<u32>],
) -> Result<Vec<u32>, GlmMoeRouteError> {
    if source == destination {
        return Ok(vec![source]);
    }
    let mut parent = vec![None; adjacency.len()];
    let mut queue = VecDeque::from([source]);
    parent[source as usize] = Some(source);
    while let Some(current) = queue.pop_front() {
        for neighbor in &adjacency[current as usize] {
            if parent[*neighbor as usize].is_none() {
                parent[*neighbor as usize] = Some(current);
                queue.push_back(*neighbor);
            }
        }
    }
    if parent[destination as usize].is_none() {
        return Err(GlmMoeRouteError::DisconnectedTopology);
    }
    let mut path = vec![destination];
    let mut current = destination;
    while current != source {
        current = parent[current as usize].ok_or(GlmMoeRouteError::DisconnectedTopology)?;
        path.push(current);
    }
    path.reverse();
    Ok(path)
}

fn link_serialization(
    scenario: &RouteScenarioSpec,
    topology: &DeviceTopologySpec,
    links: &[TopologyLinkLoadReport],
) -> (Option<f64>, Vec<LinkSerializationBlocker>) {
    let mut blockers = Vec::new();
    if scenario.provenance.kind != RouteEvidenceKind::MeasuredRouteHistogram {
        blockers.push(LinkSerializationBlocker::RouteHistogramIsNotMeasured);
    }
    if topology.link.evidence.kind != LinkEvidenceKind::MeasuredCalibration {
        blockers.push(LinkSerializationBlocker::LinkBandwidthIsNotMeasured);
    }
    if blockers.is_empty() {
        let maximum_direction_bytes = links
            .iter()
            .map(|link| {
                link.a_to_b_payload_bytes_lower_bound
                    .max(link.b_to_a_payload_bytes_lower_bound)
            })
            .max()
            .unwrap_or(0);
        (
            Some(
                maximum_direction_bytes as f64
                    / topology.link.payload_bytes_per_second_per_direction as f64,
            ),
            blockers,
        )
    } else {
        (None, blockers)
    }
}

fn end_to_end_claims(
    scenario: &RouteScenarioSpec,
    topology: &DeviceTopologySpec,
) -> EndToEndClaimReport {
    let mut blockers = Vec::new();
    if scenario.provenance.kind != RouteEvidenceKind::MeasuredRouteHistogram {
        blockers.push(EndToEndClaimBlocker::RouteHistogramIsNotMeasured);
    }
    if topology.link.evidence.kind != LinkEvidenceKind::MeasuredCalibration {
        blockers.push(EndToEndClaimBlocker::LinkBandwidthIsNotMeasured);
    }
    blockers.push(EndToEndClaimBlocker::MissingMeasuredEndToEndServingEvidence);
    blockers.push(EndToEndClaimBlocker::MissingEconomicUtilizationEvidence);
    EndToEndClaimReport {
        end_to_end_latency_seconds_per_token: None,
        cost_per_million_output_tokens_usd: None,
        blockers,
    }
}

fn source_shard_count(route: &RouteInputSpec) -> u32 {
    match route {
        RouteInputSpec::Synthetic(spec) => spec.source_shard_count,
        RouteInputSpec::PinnedHistogram(histogram) => histogram.source_shard_count,
    }
}

fn ratio_to_mean_basis_points(value: u64, total: u64, count: u32) -> Result<u32, GlmMoeRouteError> {
    if total == 0 {
        return Err(GlmMoeRouteError::ArithmeticOverflow);
    }
    let numerator = u128::from(value)
        .checked_mul(u128::from(count))
        .and_then(|scaled| scaled.checked_mul(10_000))
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?;
    u32::try_from(numerator.div_ceil(u128::from(total)))
        .map_err(|_| GlmMoeRouteError::ArithmeticOverflow)
}

fn fraction_basis_points(part: u64, total: u64) -> Result<u32, GlmMoeRouteError> {
    if total == 0 {
        return Err(GlmMoeRouteError::ArithmeticOverflow);
    }
    let value = u128::from(part)
        .checked_mul(10_000)
        .ok_or(GlmMoeRouteError::ArithmeticOverflow)?
        / u128::from(total);
    u32::try_from(value).map_err(|_| GlmMoeRouteError::ArithmeticOverflow)
}

fn checked_sum(values: &[u64]) -> Result<u64, GlmMoeRouteError> {
    values.iter().try_fold(0_u64, |sum, value| {
        sum.checked_add(*value)
            .ok_or(GlmMoeRouteError::ArithmeticOverflow)
    })
}

fn validate_required(field: &'static str, value: &str) -> Result<(), GlmMoeRouteError> {
    if value.trim().is_empty() {
        Err(GlmMoeRouteError::InvalidField(field))
    } else {
        Ok(())
    }
}

fn route_input_content_id(route: &RouteInputSpec) -> Result<String, GlmMoeRouteError> {
    let bytes = serde_json::to_vec(route)
        .map_err(|error| GlmMoeRouteError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmMoeRouteResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmMoeRouteResult,
) -> Result<String, GlmMoeRouteError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| GlmMoeRouteError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum GlmMoeRouteError {
    #[error("unsupported GLM MoE route schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM MoE route field {0}")]
    InvalidField(&'static str),
    #[error("GLM MoE geometry must be 75 layers, 256 routed experts, and top-8")]
    InvalidGlmGeometry,
    #[error("duplicate route scenario {0}")]
    DuplicateScenario(String),
    #[error("duplicate topology {0}")]
    DuplicateTopology(String),
    #[error("duplicate placement strategy {0}")]
    DuplicateStrategy(String),
    #[error("route scenario {0} model identity does not match the request")]
    RouteModelIdentityMismatch(String),
    #[error("synthetic route scenario {0} must be labeled as a modeled assumption")]
    SyntheticRouteIsNotModeled(String),
    #[error("pinned route histogram has an invalid shape")]
    InvalidHistogramShape,
    #[error("pinned route histogram changes token count between layers")]
    InconsistentHistogramTokenCount,
    #[error("route histogram ledger is invalid at layer {layer_index}, source {source_shard}")]
    InvalidHistogramDispatchLedger { layer_index: u32, source_shard: u32 },
    #[error("scenario {scenario_id} source shards do not map evenly onto topology {topology_id}")]
    SourceShardsDoNotMapEvenly {
        scenario_id: String,
        topology_id: String,
    },
    #[error("topology {0} cannot hold one copy of every routed expert")]
    InsufficientExpertCapacity(String),
    #[error("topology {topology_id} cannot satisfy strategy {strategy_id} replication budget")]
    InsufficientReplicationCapacity {
        topology_id: String,
        strategy_id: String,
    },
    #[error("expert placement exceeded device capacity")]
    PlacementCapacityExceeded,
    #[error("device topology is disconnected")]
    DisconnectedTopology,
    #[error("route, placement, or traffic ledgers failed to reconcile")]
    LedgerInvariantViolation,
    #[error("GLM MoE route arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("GLM MoE route serialization failed: {0}")]
    Serialization(String),
}
