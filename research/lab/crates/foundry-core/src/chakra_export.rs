use crate::action_ledger::{
    Action, ActionId, ActionLedger, ActionWork, Bytes, CollectiveKind, ComputeClass, EvidenceKind,
    Flops, InferencePhase, LedgerError, Messages, NetworkPattern, Operations,
};
use prost::Message;
use serde::Serialize;
use std::collections::BTreeMap;
use thiserror::Error;

pub const CHAKRA_SCHEMA_TAG: &str = "v0.0.4";
pub const CHAKRA_SCHEMA_COMMIT: &str = "8b20269327725ad078483ce85d5f6dbb1cbfa611";
pub const CHAKRA_GLOBAL_METADATA_VERSION: &str = "0.0.4";
pub const CHAKRA_EXPORTER_ID: &str = "foundry-core/chakra-export";
pub const CHAKRA_EXPORTER_VERSION: &str = "1";

const EXPORT_SEMANTICS: &str = "interchange_only_no_timing";
const COMPUTE_NUM_OPS_LOWERING: &str = "flops_plus_non_flop_operations";
const COLLECTIVE_SIZE_LOWERING: &str = "aggregate_bytes_as_comm_size";
const MESSAGE_COUNT_LOWERING: &str = "foundry_attribute_only";
const DEPENDENCY_LOWERING: &str = "canonical_dependencies_as_data_deps";
const RANK_SEMANTICS: &str = "aggregate_phase_no_rank_assignment";

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChakraExportProvenance {
    pub exporter_id: String,
    pub exporter_version: String,
    pub schema_tag: String,
    pub schema_commit: String,
    pub global_metadata_version: String,
    pub source_ledger_content_id: String,
    pub source_producer_name: String,
    pub source_producer_version: String,
    pub model_id: String,
    pub model_revision: String,
    pub phase: InferencePhase,
    pub batch_size: u32,
    pub context_tokens: u64,
    pub candidate_tokens: u64,
    pub committed_tokens: u64,
    pub semantics: String,
    pub compute_num_ops_lowering: String,
    pub collective_size_lowering: String,
    pub message_count_lowering: String,
    pub dependency_lowering: String,
    pub rank_semantics: String,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChakraExportAccounting {
    pub flops: Flops,
    pub non_flop_operations: Operations,
    pub network_bytes: Bytes,
    pub messages: Messages,
    pub compute_nodes: u64,
    pub collective_nodes: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ChakraNodeKind {
    Compute,
    Collective,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "type", content = "value", rename_all = "snake_case")]
pub enum ChakraAttributeValue {
    Int64(i64),
    Uint64(u64),
    Bool(bool),
    String(String),
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChakraAttribute {
    pub name: String,
    pub value: ChakraAttributeValue,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChakraNode {
    pub node_id: u64,
    pub action_id: ActionId,
    pub name: String,
    pub kind: ChakraNodeKind,
    pub data_dependencies: Vec<u64>,
    pub attributes: Vec<ChakraAttribute>,
}

impl ChakraNode {
    pub fn attribute(&self, name: &str) -> Option<&ChakraAttributeValue> {
        self.attributes
            .iter()
            .find(|attribute| attribute.name == name)
            .map(|attribute| &attribute.value)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChakraTrace {
    pub provenance: ChakraExportProvenance,
    pub accounting: ChakraExportAccounting,
    pub binary_content_id: String,
    pub encoded_bytes: u64,
    pub nodes: Vec<ChakraNode>,
    #[serde(skip)]
    bytes: Vec<u8>,
}

impl ChakraTrace {
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    pub fn to_manifest_json(&self) -> Result<String, ChakraExportError> {
        let nodes = self
            .nodes
            .iter()
            .map(|node| ChakraManifestNode {
                node_id: node.node_id,
                action_id: &node.action_id,
                name: &node.name,
                kind: node.kind,
                data_dependencies: &node.data_dependencies,
            })
            .collect::<Vec<_>>();
        Ok(serde_json::to_string_pretty(&ChakraManifest {
            provenance: &self.provenance,
            accounting: self.accounting,
            binary_content_id: &self.binary_content_id,
            encoded_bytes: self.encoded_bytes,
            nodes,
        })?)
    }
}

#[derive(Serialize)]
struct ChakraManifest<'a> {
    provenance: &'a ChakraExportProvenance,
    accounting: ChakraExportAccounting,
    binary_content_id: &'a str,
    encoded_bytes: u64,
    nodes: Vec<ChakraManifestNode<'a>>,
}

#[derive(Serialize)]
struct ChakraManifestNode<'a> {
    node_id: u64,
    action_id: &'a ActionId,
    name: &'a str,
    kind: ChakraNodeKind,
    data_dependencies: &'a [u64],
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum UnsupportedActionKind {
    Memory,
    Cache,
    Synchronization,
    Scheduler,
}

#[derive(Debug, Error)]
pub enum ChakraExportError {
    #[error("invalid source action ledger: {0}")]
    Ledger(#[from] LedgerError),
    #[error("action {action_id} has unsupported Chakra export kind {kind:?}")]
    UnsupportedAction {
        action_id: ActionId,
        kind: UnsupportedActionKind,
    },
    #[error(
        "action {action_id} is point-to-point and lacks explicit Chakra rank, tag, and send/receive lowering"
    )]
    UnsupportedPointToPoint { action_id: ActionId },
    #[error("action {action_id} overflows the combined compute operation count")]
    OperationCountOverflow { action_id: ActionId },
    #[error("action {action_id} value {value} is outside Chakra signed field {field}")]
    StandardAttributeOutOfRange {
        action_id: ActionId,
        field: &'static str,
        value: u64,
    },
    #[error("Chakra node count does not fit in u64")]
    NodeCountOverflow,
    #[error("Chakra encoded size does not fit in u64")]
    EncodedSizeOverflow,
    #[error("Chakra export internal action mapping is inconsistent")]
    InternalActionMapping,
    #[error("Chakra protobuf encoding failed: {0}")]
    WireEncoding(#[from] prost::EncodeError),
    #[error("Chakra protobuf decoding failed during export verification: {0}")]
    WireDecoding(#[from] prost::DecodeError),
    #[error("Chakra protobuf round-trip changed the export")]
    WireRoundTrip,
    #[error("Chakra manifest serialization failed: {0}")]
    ManifestSerialization(#[from] serde_json::Error),
}

pub struct ChakraExporter;

impl ChakraExporter {
    pub fn export(ledger: &ActionLedger) -> Result<ChakraTrace, ChakraExportError> {
        ledger.validate()?;
        let ordered_ids = ledger.topological_action_ids()?;
        let actions = ledger
            .actions
            .iter()
            .map(|action| (&action.id, action))
            .collect::<BTreeMap<_, _>>();
        let node_ids = ordered_ids
            .iter()
            .enumerate()
            .map(|(index, action_id)| {
                let node_id = u64::try_from(index)
                    .ok()
                    .and_then(|value| value.checked_add(1))
                    .ok_or(ChakraExportError::NodeCountOverflow)?;
                Ok((action_id.clone(), node_id))
            })
            .collect::<Result<BTreeMap<_, _>, ChakraExportError>>()?;

        let mut nodes = Vec::with_capacity(ordered_ids.len());
        for action_id in ordered_ids {
            let action = actions
                .get(&action_id)
                .copied()
                .ok_or(ChakraExportError::InternalActionMapping)?;
            let node_id = *node_ids
                .get(&action_id)
                .ok_or(ChakraExportError::InternalActionMapping)?;
            nodes.push(lower_action(action, node_id, &node_ids)?);
        }

        let source_accounting = ledger.accounting()?;
        let accounting = ChakraExportAccounting {
            flops: source_accounting.flops,
            non_flop_operations: source_accounting.non_flop_operations,
            network_bytes: source_accounting.network_bytes,
            messages: source_accounting.messages,
            compute_nodes: source_accounting.compute_actions,
            collective_nodes: source_accounting.network_actions,
        };
        let provenance = export_provenance(ledger)?;
        let metadata = wire_metadata(&provenance);
        let wire_nodes = nodes.iter().map(wire_node).collect::<Vec<_>>();
        let bytes = encode_verified_stream(&metadata, &wire_nodes)?;
        let encoded_bytes =
            u64::try_from(bytes.len()).map_err(|_| ChakraExportError::EncodedSizeOverflow)?;
        let binary_content_id = blake3::hash(&bytes).to_hex().to_string();

        Ok(ChakraTrace {
            provenance,
            accounting,
            binary_content_id,
            encoded_bytes,
            nodes,
            bytes,
        })
    }
}

fn export_provenance(ledger: &ActionLedger) -> Result<ChakraExportProvenance, ChakraExportError> {
    Ok(ChakraExportProvenance {
        exporter_id: CHAKRA_EXPORTER_ID.into(),
        exporter_version: CHAKRA_EXPORTER_VERSION.into(),
        schema_tag: CHAKRA_SCHEMA_TAG.into(),
        schema_commit: CHAKRA_SCHEMA_COMMIT.into(),
        global_metadata_version: CHAKRA_GLOBAL_METADATA_VERSION.into(),
        source_ledger_content_id: ledger.content_id()?.as_str().into(),
        source_producer_name: ledger.provenance.producer.name.clone(),
        source_producer_version: ledger.provenance.producer.version.clone(),
        model_id: ledger.provenance.model.model_id.clone(),
        model_revision: ledger.provenance.model.model_revision.clone(),
        phase: ledger.provenance.phase.phase,
        batch_size: ledger.provenance.phase.batch_size,
        context_tokens: ledger.provenance.phase.context_tokens,
        candidate_tokens: ledger.provenance.phase.candidate_tokens,
        committed_tokens: ledger.provenance.phase.committed_tokens,
        semantics: EXPORT_SEMANTICS.into(),
        compute_num_ops_lowering: COMPUTE_NUM_OPS_LOWERING.into(),
        collective_size_lowering: COLLECTIVE_SIZE_LOWERING.into(),
        message_count_lowering: MESSAGE_COUNT_LOWERING.into(),
        dependency_lowering: DEPENDENCY_LOWERING.into(),
        rank_semantics: RANK_SEMANTICS.into(),
    })
}

fn lower_action(
    action: &Action,
    node_id: u64,
    node_ids: &BTreeMap<ActionId, u64>,
) -> Result<ChakraNode, ChakraExportError> {
    let mut data_dependencies = action
        .dependencies
        .iter()
        .map(|dependency| {
            node_ids
                .get(dependency)
                .copied()
                .ok_or(ChakraExportError::InternalActionMapping)
        })
        .collect::<Result<Vec<_>, _>>()?;
    data_dependencies.sort_unstable();

    match &action.work {
        ActionWork::Compute(work) => {
            let operations = work
                .flops
                .get()
                .checked_add(work.non_flop_operations.get())
                .ok_or_else(|| ChakraExportError::OperationCountOverflow {
                    action_id: action.id.clone(),
                })?;
            let num_ops = signed_standard_value(&action.id, "num_ops", operations)?;
            let mut attributes = evidence_attributes(action);
            attributes.extend([
                attribute("foundry.compute_class", compute_class_name(work.class)),
                attribute("foundry.flops", work.flops.get()),
                attribute(
                    "foundry.non_flop_operations",
                    work.non_flop_operations.get(),
                ),
                attribute("is_cpu_op", false),
                attribute("num_ops", num_ops),
            ]);
            sort_attributes(&mut attributes);
            Ok(ChakraNode {
                node_id,
                action_id: action.id.clone(),
                name: format!("foundry:{}:{}", action.id, work.label),
                kind: ChakraNodeKind::Compute,
                data_dependencies,
                attributes,
            })
        }
        ActionWork::Network(work) => match work.pattern {
            NetworkPattern::PointToPoint => Err(ChakraExportError::UnsupportedPointToPoint {
                action_id: action.id.clone(),
            }),
            NetworkPattern::Collective {
                collective,
                participants,
            } => {
                let comm_size =
                    signed_standard_value(&action.id, "comm_size", work.aggregate_bytes.get())?;
                let mut attributes = evidence_attributes(action);
                attributes.extend([
                    attribute("comm_size", comm_size),
                    attribute("comm_type", collective_code(collective)),
                    attribute("foundry.aggregate_bytes", work.aggregate_bytes.get()),
                    attribute("foundry.collective", collective_name(collective)),
                    attribute("foundry.destination", work.destination.clone()),
                    attribute("foundry.messages", work.messages.get()),
                    attribute("foundry.participants", u64::from(participants)),
                    attribute("foundry.source", work.source.clone()),
                    attribute("is_cpu_op", false),
                ]);
                sort_attributes(&mut attributes);
                Ok(ChakraNode {
                    node_id,
                    action_id: action.id.clone(),
                    name: format!("foundry:{}:{}", action.id, collective_name(collective)),
                    kind: ChakraNodeKind::Collective,
                    data_dependencies,
                    attributes,
                })
            }
        },
        ActionWork::Memory(_) => unsupported(action, UnsupportedActionKind::Memory),
        ActionWork::Cache(_) => unsupported(action, UnsupportedActionKind::Cache),
        ActionWork::Synchronization(_) => {
            unsupported(action, UnsupportedActionKind::Synchronization)
        }
        ActionWork::Scheduler(_) => unsupported(action, UnsupportedActionKind::Scheduler),
    }
}

fn unsupported(
    action: &Action,
    kind: UnsupportedActionKind,
) -> Result<ChakraNode, ChakraExportError> {
    Err(ChakraExportError::UnsupportedAction {
        action_id: action.id.clone(),
        kind,
    })
}

fn signed_standard_value(
    action_id: &ActionId,
    field: &'static str,
    value: u64,
) -> Result<i64, ChakraExportError> {
    i64::try_from(value).map_err(|_| ChakraExportError::StandardAttributeOutOfRange {
        action_id: action_id.clone(),
        field,
        value,
    })
}

fn evidence_attributes(action: &Action) -> Vec<ChakraAttribute> {
    vec![
        attribute("foundry.action_id", action.id.as_str()),
        attribute(
            "foundry.evidence_kind",
            evidence_kind_name(action.evidence.kind),
        ),
        attribute(
            "foundry.evidence_source_artifact_id",
            action.evidence.source_artifact_id.clone(),
        ),
    ]
}

fn attribute(name: &str, value: impl Into<ChakraAttributeValue>) -> ChakraAttribute {
    ChakraAttribute {
        name: name.into(),
        value: value.into(),
    }
}

fn sort_attributes(attributes: &mut [ChakraAttribute]) {
    attributes.sort_by(|left, right| left.name.cmp(&right.name));
}

impl From<i64> for ChakraAttributeValue {
    fn from(value: i64) -> Self {
        Self::Int64(value)
    }
}

impl From<u64> for ChakraAttributeValue {
    fn from(value: u64) -> Self {
        Self::Uint64(value)
    }
}

impl From<bool> for ChakraAttributeValue {
    fn from(value: bool) -> Self {
        Self::Bool(value)
    }
}

impl From<&str> for ChakraAttributeValue {
    fn from(value: &str) -> Self {
        Self::String(value.into())
    }
}

impl From<String> for ChakraAttributeValue {
    fn from(value: String) -> Self {
        Self::String(value)
    }
}

fn compute_class_name(class: ComputeClass) -> &'static str {
    match class {
        ComputeClass::MatrixMultiply => "matrix_multiply",
        ComputeClass::AttentionScore => "attention_score",
        ComputeClass::TopK => "top_k",
        ComputeClass::Reduction => "reduction",
        ComputeClass::Elementwise => "elementwise",
    }
}

fn evidence_kind_name(kind: EvidenceKind) -> &'static str {
    match kind {
        EvidenceKind::ReleasedFact => "released_fact",
        EvidenceKind::DerivedFact => "derived_fact",
        EvidenceKind::WorkloadTrace => "workload_trace",
        EvidenceKind::Assumption => "assumption",
    }
}

fn phase_name(phase: InferencePhase) -> &'static str {
    match phase {
        InferencePhase::Prefill => "prefill",
        InferencePhase::Decode => "decode",
    }
}

fn collective_name(collective: CollectiveKind) -> &'static str {
    match collective {
        CollectiveKind::AllReduce => "all_reduce",
        CollectiveKind::AllGather => "all_gather",
        CollectiveKind::ReduceScatter => "reduce_scatter",
        CollectiveKind::AllToAll => "all_to_all",
        CollectiveKind::Broadcast => "broadcast",
    }
}

fn collective_code(collective: CollectiveKind) -> i64 {
    match collective {
        CollectiveKind::AllReduce => 0,
        CollectiveKind::AllGather => 2,
        CollectiveKind::Broadcast => 5,
        CollectiveKind::AllToAll => 6,
        CollectiveKind::ReduceScatter => 7,
    }
}

fn wire_metadata(provenance: &ChakraExportProvenance) -> wire::GlobalMetadata {
    let mut attributes = vec![
        attribute(
            "foundry.action_ledger_content_id",
            provenance.source_ledger_content_id.clone(),
        ),
        attribute("foundry.adapter_id", provenance.exporter_id.clone()),
        attribute(
            "foundry.adapter_version",
            provenance.exporter_version.clone(),
        ),
        attribute("foundry.batch_size", u64::from(provenance.batch_size)),
        attribute("foundry.candidate_tokens", provenance.candidate_tokens),
        attribute(
            "foundry.collective_size_lowering",
            provenance.collective_size_lowering.clone(),
        ),
        attribute("foundry.committed_tokens", provenance.committed_tokens),
        attribute(
            "foundry.compute_num_ops_lowering",
            provenance.compute_num_ops_lowering.clone(),
        ),
        attribute("foundry.context_tokens", provenance.context_tokens),
        attribute(
            "foundry.dependency_lowering",
            provenance.dependency_lowering.clone(),
        ),
        attribute(
            "foundry.message_count_lowering",
            provenance.message_count_lowering.clone(),
        ),
        attribute("foundry.model_id", provenance.model_id.clone()),
        attribute("foundry.model_revision", provenance.model_revision.clone()),
        attribute("foundry.phase", phase_name(provenance.phase)),
        attribute("foundry.rank_semantics", provenance.rank_semantics.clone()),
        attribute("foundry.schema_commit", provenance.schema_commit.clone()),
        attribute("foundry.schema_tag", provenance.schema_tag.clone()),
        attribute("foundry.semantics", provenance.semantics.clone()),
        attribute(
            "foundry.source_producer_name",
            provenance.source_producer_name.clone(),
        ),
        attribute(
            "foundry.source_producer_version",
            provenance.source_producer_version.clone(),
        ),
    ];
    sort_attributes(&mut attributes);
    wire::GlobalMetadata {
        version: provenance.global_metadata_version.clone(),
        attr: attributes.iter().map(wire_attribute).collect(),
    }
}

fn wire_node(node: &ChakraNode) -> wire::Node {
    wire::Node {
        id: node.node_id,
        name: node.name.clone(),
        r#type: match node.kind {
            ChakraNodeKind::Compute => wire::NodeType::Comp as i32,
            ChakraNodeKind::Collective => wire::NodeType::CommColl as i32,
        },
        ctrl_deps: Vec::new(),
        data_deps: node.data_dependencies.clone(),
        attr: node.attributes.iter().map(wire_attribute).collect(),
    }
}

fn wire_attribute(attribute: &ChakraAttribute) -> wire::AttributeProto {
    use wire::attribute_proto::Value;
    let value = match &attribute.value {
        ChakraAttributeValue::Int64(value) => Value::Int64(*value),
        ChakraAttributeValue::Uint64(value) => Value::Uint64(*value),
        ChakraAttributeValue::Bool(value) => Value::Bool(*value),
        ChakraAttributeValue::String(value) => Value::String(value.clone()),
    };
    wire::AttributeProto {
        name: attribute.name.clone(),
        doc_string: String::new(),
        value: Some(value),
    }
}

fn encode_verified_stream(
    metadata: &wire::GlobalMetadata,
    nodes: &[wire::Node],
) -> Result<Vec<u8>, ChakraExportError> {
    let mut bytes = Vec::new();
    metadata.encode_length_delimited(&mut bytes)?;
    for node in nodes {
        node.encode_length_delimited(&mut bytes)?;
    }

    let mut input = bytes.as_slice();
    let decoded_metadata = wire::GlobalMetadata::decode_length_delimited(&mut input)?;
    if &decoded_metadata != metadata {
        return Err(ChakraExportError::WireRoundTrip);
    }
    for expected in nodes {
        let decoded = wire::Node::decode_length_delimited(&mut input)?;
        if &decoded != expected {
            return Err(ChakraExportError::WireRoundTrip);
        }
    }
    if !input.is_empty() {
        return Err(ChakraExportError::WireRoundTrip);
    }
    Ok(bytes)
}

mod wire {
    #[derive(Clone, PartialEq, ::prost::Message)]
    pub struct AttributeProto {
        #[prost(string, tag = "1")]
        pub name: String,
        #[prost(string, tag = "2")]
        pub doc_string: String,
        #[prost(oneof = "attribute_proto::Value", tags = "9, 13, 27, 29")]
        pub value: Option<attribute_proto::Value>,
    }

    pub mod attribute_proto {
        #[derive(Clone, PartialEq, ::prost::Oneof)]
        pub enum Value {
            #[prost(int64, tag = "9")]
            Int64(i64),
            #[prost(uint64, tag = "13")]
            Uint64(u64),
            #[prost(bool, tag = "27")]
            Bool(bool),
            #[prost(string, tag = "29")]
            String(String),
        }
    }

    #[derive(Clone, PartialEq, ::prost::Message)]
    pub struct GlobalMetadata {
        #[prost(string, tag = "1")]
        pub version: String,
        #[prost(message, repeated, tag = "2")]
        pub attr: Vec<AttributeProto>,
    }

    #[derive(Clone, PartialEq, ::prost::Message)]
    pub struct Node {
        #[prost(uint64, tag = "1")]
        pub id: u64,
        #[prost(string, tag = "2")]
        pub name: String,
        #[prost(enumeration = "NodeType", tag = "3")]
        pub r#type: i32,
        #[prost(uint64, repeated, tag = "4")]
        pub ctrl_deps: Vec<u64>,
        #[prost(uint64, repeated, tag = "5")]
        pub data_deps: Vec<u64>,
        #[prost(message, repeated, tag = "10")]
        pub attr: Vec<AttributeProto>,
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, ::prost::Enumeration)]
    #[repr(i32)]
    pub enum NodeType {
        Invalid = 0,
        Metadata = 1,
        MemLoad = 2,
        MemStore = 3,
        Comp = 4,
        CommSend = 5,
        CommRecv = 6,
        CommColl = 7,
    }
}
