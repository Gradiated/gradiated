use foundry_core::action_ledger::{
    ActionId, ActionLedger, ActionWork, AdapterMeasurements, Bytes, CacheAction, CacheKeySpace,
    CacheOperation, CollectiveKind, Flops, Joules, MeasurementProvenance, MemoryAction,
    MemoryPayload, MemoryTier, Messages, NetworkAction, NetworkPattern, Operations,
    SchedulerAction, SchedulerDecision, Seconds, SynchronizationAction, SynchronizationKind, Usd,
};
use foundry_core::chakra_export::{
    CHAKRA_EXPORTER_ID, CHAKRA_EXPORTER_VERSION, CHAKRA_GLOBAL_METADATA_VERSION,
    CHAKRA_SCHEMA_COMMIT, CHAKRA_SCHEMA_TAG, ChakraAttributeValue, ChakraExportError,
    ChakraExporter, ChakraNodeKind, UnsupportedActionKind,
};

const LEDGER_FIXTURE: &str = include_str!("fixtures/glm-5.2-chakra-ledger-v1.json");
const EXPORT_FIXTURE: &str = include_str!("fixtures/glm-5.2-chakra-export-v1.json");

fn fixture() -> ActionLedger {
    ActionLedger::from_json(LEDGER_FIXTURE).expect("valid GLM Chakra subset fixture")
}

fn attribute<'a>(
    trace: &'a foundry_core::chakra_export::ChakraTrace,
    action_id: &str,
    name: &str,
) -> &'a ChakraAttributeValue {
    trace
        .nodes
        .iter()
        .find(|node| node.action_id.as_str() == action_id)
        .and_then(|node| node.attribute(name))
        .unwrap_or_else(|| panic!("missing {name} on {action_id}"))
}

#[test]
fn glm_compute_collective_dag_preserves_flops_bytes_messages_and_dependencies() {
    let ledger = fixture();
    let trace = ChakraExporter::export(&ledger).expect("representable trace");

    assert_eq!(trace.nodes.len(), 6);
    assert_eq!(trace.accounting.flops, Flops::new(171_966_464));
    assert_eq!(trace.accounting.non_flop_operations, Operations::new(8_192));
    assert_eq!(trace.accounting.network_bytes, Bytes::new(24_576));
    assert_eq!(trace.accounting.messages, Messages::new(56));

    assert_eq!(
        attribute(&trace, "dsa_index_scan", "foundry.flops"),
        &ChakraAttributeValue::Uint64(33_554_432)
    );
    assert_eq!(
        attribute(&trace, "dsa_topk", "foundry.non_flop_operations"),
        &ChakraAttributeValue::Uint64(8_192)
    );
    assert_eq!(
        attribute(&trace, "dsa_topk", "num_ops"),
        &ChakraAttributeValue::Int64(8_192)
    );
    assert_eq!(
        attribute(&trace, "moe_dispatch", "comm_size"),
        &ChakraAttributeValue::Int64(24_576)
    );
    assert_eq!(
        attribute(&trace, "moe_dispatch", "foundry.aggregate_bytes"),
        &ChakraAttributeValue::Uint64(24_576)
    );
    assert_eq!(
        attribute(&trace, "moe_dispatch", "foundry.messages"),
        &ChakraAttributeValue::Uint64(56)
    );

    assert_eq!(trace.nodes[0].action_id.as_str(), "dsa_index_scan");
    assert_eq!(trace.nodes[0].node_id, 1);
    for (index, node) in trace.nodes.iter().enumerate().skip(1) {
        assert_eq!(node.data_dependencies, vec![index as u64]);
    }
    assert_eq!(trace.nodes[2].kind, ChakraNodeKind::Collective);
    assert!(
        trace
            .nodes
            .iter()
            .enumerate()
            .all(|(index, node)| node.node_id == index as u64 + 1)
    );
}

#[test]
fn checked_export_fixture_pins_schema_provenance_lowering_and_binary_identity() {
    let ledger = fixture();
    let trace = ChakraExporter::export(&ledger).expect("representable trace");

    assert_eq!(trace.provenance.exporter_id, CHAKRA_EXPORTER_ID);
    assert_eq!(trace.provenance.exporter_version, CHAKRA_EXPORTER_VERSION);
    assert_eq!(trace.provenance.schema_tag, CHAKRA_SCHEMA_TAG);
    assert_eq!(trace.provenance.schema_commit, CHAKRA_SCHEMA_COMMIT);
    assert_eq!(
        trace.provenance.global_metadata_version,
        CHAKRA_GLOBAL_METADATA_VERSION
    );
    assert_eq!(trace.provenance.semantics, "interchange_only_no_timing");
    assert_eq!(
        trace.provenance.compute_num_ops_lowering,
        "flops_plus_non_flop_operations"
    );
    assert_eq!(
        trace.provenance.collective_size_lowering,
        "aggregate_bytes_as_comm_size"
    );
    assert_eq!(
        trace.provenance.message_count_lowering,
        "foundry_attribute_only"
    );
    assert_eq!(
        trace.provenance.dependency_lowering,
        "canonical_dependencies_as_data_deps"
    );
    assert_eq!(
        trace.provenance.rank_semantics,
        "aggregate_phase_no_rank_assignment"
    );
    assert!(!trace.bytes().is_empty());
    assert_eq!(
        trace.to_manifest_json().expect("manifest serialization"),
        EXPORT_FIXTURE.trim_end()
    );
}

#[test]
fn all_representable_collectives_use_the_pinned_chakra_enum_codes() {
    let cases = [
        (CollectiveKind::AllReduce, 0),
        (CollectiveKind::AllGather, 2),
        (CollectiveKind::Broadcast, 5),
        (CollectiveKind::AllToAll, 6),
        (CollectiveKind::ReduceScatter, 7),
    ];

    for (collective, expected_code) in cases {
        let mut ledger = fixture();
        if let ActionWork::Network(work) = &mut ledger.actions[2].work {
            work.pattern = NetworkPattern::Collective {
                collective,
                participants: 8,
            };
        }
        let trace = ChakraExporter::export(&ledger).expect("representable collective");
        assert_eq!(
            attribute(&trace, "moe_dispatch", "comm_type"),
            &ChakraAttributeValue::Int64(expected_code)
        );
    }
}

#[test]
fn output_is_independent_of_input_order_and_calibrated_measurements() {
    let ledger = fixture();
    let expected = ChakraExporter::export(&ledger).expect("representable trace");
    let mut reordered = ledger.clone();
    reordered.actions.reverse();
    for action in &mut reordered.actions {
        action.dependencies.reverse();
    }
    reordered.actions[0].measurements = Some(AdapterMeasurements {
        provenance: MeasurementProvenance {
            adapter_id: "measured-backend".into(),
            adapter_version: "1".into(),
            calibration_artifact_id: "measurement:calibration-v1".into(),
            run_id: "run-1".into(),
        },
        latency: Some(Seconds::new(0.001)),
        energy: Some(Joules::new(2.0)),
        cost: Some(Usd::new(0.01)),
    });

    let actual = ChakraExporter::export(&reordered).expect("representable trace");
    assert_eq!(actual.bytes(), expected.bytes());
    assert_eq!(actual.binary_content_id, expected.binary_content_id);
    assert_eq!(actual.nodes, expected.nodes);
}

#[test]
fn unsupported_action_kinds_fail_explicitly() {
    let cases = [
        (
            ActionWork::Memory(MemoryAction {
                source: MemoryTier::Hbm,
                destination: MemoryTier::OnChip,
                payload: MemoryPayload::Weights,
                bytes: Bytes::new(1),
            }),
            UnsupportedActionKind::Memory,
        ),
        (
            ActionWork::Cache(CacheAction {
                operation: CacheOperation::Lookup,
                tier: MemoryTier::OnChip,
                key_space: CacheKeySpace::DsaIndices,
                bytes: Bytes::new(1),
                hit: Some(true),
            }),
            UnsupportedActionKind::Cache,
        ),
        (
            ActionWork::Synchronization(SynchronizationAction {
                kind: SynchronizationKind::Barrier,
                participants: 8,
            }),
            UnsupportedActionKind::Synchronization,
        ),
        (
            ActionWork::Scheduler(SchedulerAction {
                decision: SchedulerDecision::ExpertRouting,
                requests: 1,
                tokens: 1,
            }),
            UnsupportedActionKind::Scheduler,
        ),
    ];

    for (work, expected_kind) in cases {
        let mut ledger = fixture();
        ledger.actions[0].work = work;
        let result = ChakraExporter::export(&ledger);
        assert!(matches!(
            result,
            Err(ChakraExportError::UnsupportedAction {
                action_id,
                kind
            }) if action_id == ActionId::from("dsa_index_scan") && kind == expected_kind
        ));
    }
}

#[test]
fn point_to_point_fails_without_explicit_rank_tag_and_send_receive_semantics() {
    let mut ledger = fixture();
    ledger.actions[2].work = ActionWork::Network(NetworkAction {
        pattern: NetworkPattern::PointToPoint,
        source: "rank-0".into(),
        destination: "rank-1".into(),
        aggregate_bytes: Bytes::new(24_576),
        messages: Messages::new(1),
    });

    assert!(matches!(
        ChakraExporter::export(&ledger),
        Err(ChakraExportError::UnsupportedPointToPoint { action_id })
            if action_id == ActionId::from("moe_dispatch")
    ));
}

#[test]
fn standard_signed_attributes_fail_on_overflow_instead_of_truncating() {
    let mut compute_overflow = fixture();
    if let ActionWork::Compute(work) = &mut compute_overflow.actions[0].work {
        work.flops = Flops::new(i64::MAX as u64 + 1);
    }
    assert!(matches!(
        ChakraExporter::export(&compute_overflow),
        Err(ChakraExportError::StandardAttributeOutOfRange {
            action_id,
            field: "num_ops",
            ..
        }) if action_id == ActionId::from("dsa_index_scan")
    ));

    let mut operation_overflow = fixture();
    if let ActionWork::Compute(work) = &mut operation_overflow.actions[1].work {
        work.flops = Flops::new(u64::MAX);
    }
    assert!(matches!(
        ChakraExporter::export(&operation_overflow),
        Err(ChakraExportError::OperationCountOverflow { action_id })
            if action_id == ActionId::from("dsa_topk")
    ));

    let mut network_overflow = fixture();
    if let ActionWork::Network(work) = &mut network_overflow.actions[2].work {
        work.aggregate_bytes = Bytes::new(i64::MAX as u64 + 1);
    }
    assert!(matches!(
        ChakraExporter::export(&network_overflow),
        Err(ChakraExportError::StandardAttributeOutOfRange {
            action_id,
            field: "comm_size",
            ..
        }) if action_id == ActionId::from("moe_dispatch")
    ));
}

#[test]
fn malformed_ledgers_are_rejected_before_lowering() {
    let mut ledger = fixture();
    ledger.actions[1].dependencies = vec![ActionId::from("missing")];

    assert!(matches!(
        ChakraExporter::export(&ledger),
        Err(ChakraExportError::Ledger(_))
    ));
}
