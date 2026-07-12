use foundry_core::glm_moe_route::{
    DeviceTopologySpec, DispatchPolicy, GLM_MOE_EXPERT_COUNT, GLM_MOE_LAYER_COUNT,
    GLM_MOE_ROUTE_REQUEST_SCHEMA_VERSION, GLM_MOE_TOP_K, GlmMoeGeometry, GlmMoeRouteReport,
    GlmMoeRouteRequest, InterconnectTrafficAssumptions, LayerRouteHistogram,
    LinkCalibrationAssumption, LinkEvidenceKind, NetworkRoutingPolicy, NetworkTopologyKind,
    PinnedRouteHistogram, PlacementPolicy, PlacementSimulationReport, PlacementStrategySpec,
    RouteEvidenceKind, RouteInputSpec, RouteProvenance, RouteScenarioSpec, SourceRouteHistogram,
    SourceShardMappingPolicy, SyntheticRouteDistribution, SyntheticRouteSpec, TopologyEvidence,
    evaluate_glm_moe_routes,
};
use std::fs;
use std::path::Path;

const EXPERT_BYTES: u64 = 75_497_472;

#[test]
fn exact_glm_geometry_and_dispatch_ledgers_reconcile() {
    let report = evaluate_glm_moe_routes(&request()).unwrap();
    let strategy = strategy(&report, "hot-affine", "fc4", "uniform");
    let expected_dispatches = u64::from(GLM_MOE_LAYER_COUNT) * 8 * 1_024 * 8;

    assert!(report.verify_content_id().unwrap());
    assert_eq!(strategy.traffic.total_dispatches, expected_dispatches);
    assert_eq!(
        strategy.traffic.local_dispatches + strategy.traffic.remote_dispatches,
        strategy.traffic.total_dispatches
    );
    assert_eq!(
        strategy
            .devices
            .iter()
            .map(|device| device.destination_dispatches)
            .sum::<u64>(),
        strategy.traffic.total_dispatches
    );
    assert_eq!(
        strategy
            .devices
            .iter()
            .map(|device| device.remote_dispatches_received)
            .sum::<u64>(),
        strategy.traffic.remote_dispatches
    );
    assert_eq!(
        strategy
            .devices
            .iter()
            .map(|device| device.remote_dispatches_sent)
            .sum::<u64>(),
        strategy.traffic.remote_dispatches
    );
    assert_eq!(
        strategy
            .links
            .iter()
            .map(|link| link.total_payload_bytes_lower_bound)
            .sum::<u64>(),
        strategy.traffic.network_hop_payload_bytes_lower_bound
    );
}

#[test]
fn traffic_aware_placement_and_replication_reduce_remote_dispatches() {
    let report = evaluate_glm_moe_routes(&request()).unwrap();
    let uniform = strategy(&report, "hot-affine", "fc4", "uniform");
    let aware = strategy(&report, "hot-affine", "fc4", "traffic-aware");
    let replicated = strategy(&report, "hot-affine", "fc4", "traffic-aware-replicated");

    assert!(aware.traffic.remote_dispatches < uniform.traffic.remote_dispatches);
    assert!(replicated.traffic.remote_dispatches <= aware.traffic.remote_dispatches);
    assert!(replicated.capacity.placed_additional_replicas > 0);
    assert!(replicated.capacity.placed_additional_replicas <= 256);
    assert!(replicated.devices.iter().all(|device| {
        device.resident_expert_bytes <= device.expert_memory_capacity_bytes
            && device.resident_expert_instances <= device.expert_slot_capacity
    }));
    assert!(
        aware.load_balance.max_to_mean_basis_points
            <= uniform.load_balance.max_to_mean_basis_points
    );
}

#[test]
fn ring_paths_increase_hop_bytes_without_changing_endpoint_dispatch() {
    let report = evaluate_glm_moe_routes(&request()).unwrap();
    let fully_connected = strategy(&report, "hot-affine", "fc4", "uniform");
    let ring = strategy(&report, "hot-affine", "ring4", "uniform");

    assert_eq!(
        fully_connected.traffic.remote_dispatches,
        ring.traffic.remote_dispatches
    );
    assert_eq!(
        fully_connected.traffic.endpoint_payload_bytes_lower_bound,
        ring.traffic.endpoint_payload_bytes_lower_bound
    );
    assert_eq!(
        fully_connected
            .traffic
            .network_hop_payload_bytes_lower_bound,
        fully_connected.traffic.endpoint_payload_bytes_lower_bound
    );
    assert!(
        ring.traffic.network_hop_payload_bytes_lower_bound
            > ring.traffic.endpoint_payload_bytes_lower_bound
    );
}

#[test]
fn modeled_route_and_link_inputs_fail_closed_on_latency_and_cost() {
    let report = evaluate_glm_moe_routes(&request()).unwrap();
    let strategy = strategy(&report, "hot-affine", "fc4", "uniform");

    assert_eq!(strategy.link_serialization_time_lower_bound_seconds, None);
    assert_eq!(strategy.claims.end_to_end_latency_seconds_per_token, None);
    assert_eq!(strategy.claims.cost_per_million_output_tokens_usd, None);
    assert!(!strategy.claims.blockers.is_empty());
}

#[test]
fn measured_histogram_and_link_calibration_unlock_only_link_serialization() {
    let mut request = request();
    request.scenarios = vec![pinned_uniform_scenario(8, 256)];
    request.topologies.truncate(1);
    request.topologies[0].link.evidence = TopologyEvidence {
        kind: LinkEvidenceKind::MeasuredCalibration,
        source_artifact_id: "measured-link-calibration".into(),
    };
    request.strategies.truncate(1);

    let report = evaluate_glm_moe_routes(&request).unwrap();
    let strategy = strategy(&report, "pinned-uniform", "fc4", "uniform");

    assert!(
        strategy
            .link_serialization_time_lower_bound_seconds
            .is_some()
    );
    assert_eq!(strategy.claims.end_to_end_latency_seconds_per_token, None);
    assert_eq!(strategy.claims.cost_per_million_output_tokens_usd, None);
}

#[test]
fn malformed_histograms_geometry_capacity_and_provenance_are_rejected() {
    let mut geometry = request();
    geometry.geometry.top_k = 7;
    assert!(evaluate_glm_moe_routes(&geometry).is_err());

    let mut histogram = request();
    histogram.scenarios = vec![pinned_uniform_scenario(8, 256)];
    let RouteInputSpec::PinnedHistogram(pinned) = &mut histogram.scenarios[0].route else {
        panic!("expected pinned histogram")
    };
    pinned.layers[0].sources[0].expert_dispatch_counts[0] += 1;
    assert!(evaluate_glm_moe_routes(&histogram).is_err());

    let mut capacity = request();
    capacity.topologies[0].expert_memory_capacity_bytes_per_device = EXPERT_BYTES * 4_799;
    assert!(evaluate_glm_moe_routes(&capacity).is_err());

    let mut provenance = request();
    provenance.scenarios[0].provenance.kind = RouteEvidenceKind::MeasuredRouteHistogram;
    assert!(evaluate_glm_moe_routes(&provenance).is_err());
}

#[test]
fn schemas_reject_unknown_fields_and_report_identity_is_stable() {
    let mut json = serde_json::to_value(request()).unwrap();
    json["unknown"] = serde_json::json!(true);
    assert!(serde_json::from_value::<GlmMoeRouteRequest>(json).is_err());

    let first = evaluate_glm_moe_routes(&request()).unwrap();
    let second = evaluate_glm_moe_routes(&request()).unwrap();
    assert_eq!(first.content_id, second.content_id);
}

#[test]
fn checked_in_config_and_report_round_trip_exactly() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .unwrap();
    let request: GlmMoeRouteRequest = serde_json::from_slice(
        &fs::read(root.join("configs/glm-5.2-moe-route-skew-v1.json")).unwrap(),
    )
    .unwrap();
    let stored: GlmMoeRouteReport = serde_json::from_slice(
        &fs::read(root.join("experiments/glm-5.2/moe-route-skew-v1.json")).unwrap(),
    )
    .unwrap();

    let report = evaluate_glm_moe_routes(&request).unwrap();

    assert_eq!(report, stored);
    assert!(stored.verify_content_id().unwrap());
    assert_eq!(report.result.scenarios.len(), 2);
    assert!(report.result.scenarios.iter().all(|scenario| {
        scenario.route_input_content_id.len() == 64 && scenario.topologies.len() == 3
    }));
    assert!(
        report
            .result
            .scenarios
            .iter()
            .flat_map(|scenario| &scenario.topologies)
            .flat_map(|topology| &topology.strategies)
            .all(|strategy| {
                strategy
                    .claims
                    .end_to_end_latency_seconds_per_token
                    .is_none()
                    && strategy.claims.cost_per_million_output_tokens_usd.is_none()
            })
    );
}

fn request() -> GlmMoeRouteRequest {
    GlmMoeRouteRequest {
        schema_version: GLM_MOE_ROUTE_REQUEST_SCHEMA_VERSION,
        study_id: "glm-moe-route-test".into(),
        model_id: "zai-org/GLM-5.2".into(),
        model_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
        geometry: GlmMoeGeometry {
            moe_layer_count: GLM_MOE_LAYER_COUNT,
            routed_expert_count: GLM_MOE_EXPERT_COUNT,
            top_k: GLM_MOE_TOP_K,
        },
        traffic: InterconnectTrafficAssumptions {
            expert_storage_bytes: EXPERT_BYTES,
            activation_payload_bytes_per_dispatch: 12_288,
            result_payload_bytes_per_dispatch: 12_288,
            source_artifact_id: "modeled-assumption:glm-bf16-expert-and-activation-bytes".into(),
            basis: "BF16 expert weights and hidden-state payloads; protocol overhead excluded"
                .into(),
        },
        source_shard_mapping: SourceShardMappingPolicy::ModuloDeviceCount,
        dispatch_policy: DispatchPolicy::LocalReplicaFirstThenLeastLoadedReplica,
        scenarios: vec![RouteScenarioSpec {
            scenario_id: "hot-affine".into(),
            route: RouteInputSpec::Synthetic(SyntheticRouteSpec {
                source_shard_count: 8,
                tokens_per_source_shard: 1_024,
                distribution: SyntheticRouteDistribution::RotatingHotset {
                    hot_expert_count: 16,
                    hot_dispatch_share_basis_points: 9_000,
                    layer_rotation_stride: 7,
                    source_rotation_stride: 32,
                },
            }),
            provenance: RouteProvenance {
                kind: RouteEvidenceKind::ModeledAssumption,
                source_artifact_id: "synthetic:rotating-hotset-test".into(),
                model_id: "zai-org/GLM-5.2".into(),
                model_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
            },
        }],
        topologies: vec![
            topology("fc4", NetworkTopologyKind::FullyConnected),
            topology("ring4", NetworkTopologyKind::BidirectionalRing),
        ],
        strategies: vec![
            PlacementStrategySpec {
                strategy_id: "uniform".into(),
                policy: PlacementPolicy::Uniform,
            },
            PlacementStrategySpec {
                strategy_id: "traffic-aware".into(),
                policy: PlacementPolicy::TrafficAware {
                    additional_replica_budget: 0,
                    maximum_replicas_per_expert: 1,
                },
            },
            PlacementStrategySpec {
                strategy_id: "traffic-aware-replicated".into(),
                policy: PlacementPolicy::TrafficAware {
                    additional_replica_budget: 256,
                    maximum_replicas_per_expert: 2,
                },
            },
        ],
    }
}

fn topology(topology_id: &str, network: NetworkTopologyKind) -> DeviceTopologySpec {
    DeviceTopologySpec {
        topology_id: topology_id.into(),
        device_count: 4,
        expert_memory_capacity_bytes_per_device: EXPERT_BYTES * 5_200,
        network,
        routing: NetworkRoutingPolicy::ShortestHopLowestDeviceTieBreak,
        link: LinkCalibrationAssumption {
            payload_bytes_per_second_per_direction: 100_000_000_000,
            evidence: TopologyEvidence {
                kind: LinkEvidenceKind::ModeledAssumption,
                source_artifact_id: format!("modeled-link:{topology_id}"),
            },
        },
    }
}

fn pinned_uniform_scenario(source_shard_count: u32, tokens: u64) -> RouteScenarioSpec {
    let dispatches = tokens * u64::from(GLM_MOE_TOP_K);
    let base = dispatches / u64::from(GLM_MOE_EXPERT_COUNT);
    let remainder = dispatches % u64::from(GLM_MOE_EXPERT_COUNT);
    let layers = (0..GLM_MOE_LAYER_COUNT)
        .map(|layer_index| LayerRouteHistogram {
            layer_index,
            sources: (0..source_shard_count)
                .map(|source_shard| {
                    let mut counts = vec![base; GLM_MOE_EXPERT_COUNT as usize];
                    for offset in 0..remainder {
                        let expert = (u64::from(layer_index) + u64::from(source_shard) + offset)
                            % u64::from(GLM_MOE_EXPERT_COUNT);
                        counts[expert as usize] += 1;
                    }
                    SourceRouteHistogram {
                        source_shard,
                        token_count: tokens,
                        expert_dispatch_counts: counts,
                    }
                })
                .collect(),
        })
        .collect();
    RouteScenarioSpec {
        scenario_id: "pinned-uniform".into(),
        route: RouteInputSpec::PinnedHistogram(PinnedRouteHistogram {
            source_shard_count,
            layers,
        }),
        provenance: RouteProvenance {
            kind: RouteEvidenceKind::MeasuredRouteHistogram,
            source_artifact_id: "measured-route-histogram".into(),
            model_id: "zai-org/GLM-5.2".into(),
            model_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
        },
    }
}

fn strategy<'a>(
    report: &'a GlmMoeRouteReport,
    scenario_id: &str,
    topology_id: &str,
    strategy_id: &str,
) -> &'a PlacementSimulationReport {
    report
        .result
        .scenarios
        .iter()
        .find(|scenario| scenario.scenario_id == scenario_id)
        .unwrap()
        .topologies
        .iter()
        .find(|topology| topology.topology_id == topology_id)
        .unwrap()
        .strategies
        .iter()
        .find(|strategy| strategy.strategy_id == strategy_id)
        .unwrap()
}
