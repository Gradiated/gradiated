use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use thiserror::Error;

pub const ACTION_LEDGER_SCHEMA_VERSION: u32 = 1;

macro_rules! integer_unit {
    ($name:ident) => {
        #[derive(
            Clone,
            Copy,
            Debug,
            Default,
            Deserialize,
            Eq,
            Hash,
            Ord,
            PartialEq,
            PartialOrd,
            Serialize,
        )]
        #[serde(transparent)]
        pub struct $name(u64);

        impl $name {
            pub const fn new(value: u64) -> Self {
                Self(value)
            }

            pub const fn get(self) -> u64 {
                self.0
            }
        }
    };
}

macro_rules! float_unit {
    ($name:ident) => {
        #[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Serialize)]
        #[serde(transparent)]
        pub struct $name(f64);

        impl $name {
            pub const fn new(value: f64) -> Self {
                Self(value)
            }

            pub const fn get(self) -> f64 {
                self.0
            }
        }
    };
}

integer_unit!(Flops);
integer_unit!(Operations);
integer_unit!(Bytes);
integer_unit!(Messages);
float_unit!(Seconds);
float_unit!(Joules);
float_unit!(Usd);

#[derive(Clone, Debug, Deserialize, Eq, Hash, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(transparent)]
pub struct ActionId(String);

impl ActionId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl From<&str> for ActionId {
    fn from(value: &str) -> Self {
        Self(value.to_owned())
    }
}

impl From<String> for ActionId {
    fn from(value: String) -> Self {
        Self(value)
    }
}

impl fmt::Display for ActionId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, Hash, PartialEq, Serialize)]
#[serde(transparent)]
pub struct LedgerContentId(String);

impl LedgerContentId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum InferencePhase {
    Prefill,
    Decode,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceKind {
    ReleasedFact,
    DerivedFact,
    WorkloadTrace,
    Assumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceProvenance {
    pub kind: EvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProducerProvenance {
    pub name: String,
    pub version: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelProvenance {
    pub model_id: String,
    pub model_revision: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PhaseProvenance {
    pub phase: InferencePhase,
    pub batch_size: u32,
    pub context_tokens: u64,
    pub candidate_tokens: u64,
    pub committed_tokens: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerProvenance {
    pub producer: ProducerProvenance,
    pub model: ModelProvenance,
    pub phase: PhaseProvenance,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ComputeClass {
    MatrixMultiply,
    AttentionScore,
    TopK,
    Reduction,
    Elementwise,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ComputeAction {
    pub class: ComputeClass,
    pub label: String,
    pub flops: Flops,
    pub non_flop_operations: Operations,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryTier {
    Register,
    OnChip,
    Hbm,
    HostDram,
    Cxl,
    Nvme,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MemoryPayload {
    Weights,
    Activations,
    Kv,
    Indices,
    MtpState,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryAction {
    pub source: MemoryTier,
    pub destination: MemoryTier,
    pub payload: MemoryPayload,
    pub bytes: Bytes,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CacheOperation {
    Lookup,
    Store,
    Evict,
    Promote,
    Demote,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CacheKeySpace {
    Kv,
    Prefix,
    DsaIndices,
    MtpState,
    Weights,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheAction {
    pub operation: CacheOperation,
    pub tier: MemoryTier,
    pub key_space: CacheKeySpace,
    pub bytes: Bytes,
    pub hit: Option<bool>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CollectiveKind {
    AllReduce,
    AllGather,
    ReduceScatter,
    AllToAll,
    Broadcast,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum NetworkPattern {
    PointToPoint,
    Collective {
        collective: CollectiveKind,
        participants: u32,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NetworkAction {
    pub pattern: NetworkPattern,
    pub source: String,
    pub destination: String,
    pub aggregate_bytes: Bytes,
    pub messages: Messages,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SynchronizationKind {
    Barrier,
    Event,
    Semaphore,
    Fence,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SynchronizationAction {
    pub kind: SynchronizationKind,
    pub participants: u32,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SchedulerDecision {
    BatchFormation,
    ExpertRouting,
    CacheAdmission,
    MtpDraft,
    MtpVerify,
    TokenCommit,
    Placement,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SchedulerAction {
    pub decision: SchedulerDecision,
    pub requests: u32,
    pub tokens: u64,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(
    tag = "type",
    content = "details",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum ActionWork {
    Compute(ComputeAction),
    Memory(MemoryAction),
    Cache(CacheAction),
    Network(NetworkAction),
    Synchronization(SynchronizationAction),
    Scheduler(SchedulerAction),
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MeasurementProvenance {
    pub adapter_id: String,
    pub adapter_version: String,
    pub calibration_artifact_id: String,
    pub run_id: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AdapterMeasurements {
    pub provenance: MeasurementProvenance,
    pub latency: Option<Seconds>,
    pub energy: Option<Joules>,
    pub cost: Option<Usd>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Action {
    pub id: ActionId,
    pub dependencies: Vec<ActionId>,
    pub evidence: EvidenceProvenance,
    pub work: ActionWork,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub measurements: Option<AdapterMeasurements>,
}

impl Action {
    pub fn is_compute(&self) -> bool {
        matches!(self.work, ActionWork::Compute(_))
    }

    pub fn is_memory(&self) -> bool {
        matches!(self.work, ActionWork::Memory(_))
    }

    pub fn is_cache(&self) -> bool {
        matches!(self.work, ActionWork::Cache(_))
    }

    pub fn is_network(&self) -> bool {
        matches!(self.work, ActionWork::Network(_))
    }

    pub fn is_synchronization(&self) -> bool {
        matches!(self.work, ActionWork::Synchronization(_))
    }

    pub fn is_scheduler(&self) -> bool {
        matches!(self.work, ActionWork::Scheduler(_))
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ActionLedger {
    pub schema_version: u32,
    pub provenance: LedgerProvenance,
    pub actions: Vec<Action>,
}

impl ActionLedger {
    pub fn from_json(json: &str) -> Result<Self, LedgerError> {
        let ledger: Self = serde_json::from_str(json)?;
        ledger.validate()?;
        Ok(ledger)
    }

    pub fn to_canonical_json(&self) -> Result<String, LedgerError> {
        self.validate()?;
        Ok(serde_json::to_string(&self.canonicalized())?)
    }

    pub fn canonicalized(&self) -> Self {
        let mut canonical = self.clone();
        canonical
            .actions
            .sort_by(|left, right| left.id.cmp(&right.id));
        for action in &mut canonical.actions {
            action.dependencies.sort();
        }
        canonical
    }

    pub fn content_id(&self) -> Result<LedgerContentId, LedgerError> {
        self.validate()?;
        let mut canonical = self.canonicalized();
        for action in &mut canonical.actions {
            action.measurements = None;
        }
        let bytes = serde_json::to_vec(&canonical)?;
        Ok(LedgerContentId(blake3::hash(&bytes).to_hex().to_string()))
    }

    pub fn validate(&self) -> Result<(), LedgerError> {
        if self.schema_version != ACTION_LEDGER_SCHEMA_VERSION {
            return Err(LedgerError::UnsupportedSchemaVersion {
                expected: ACTION_LEDGER_SCHEMA_VERSION,
                actual: self.schema_version,
            });
        }
        validate_required("provenance.producer.name", &self.provenance.producer.name)?;
        validate_required(
            "provenance.producer.version",
            &self.provenance.producer.version,
        )?;
        validate_required("provenance.model.model_id", &self.provenance.model.model_id)?;
        validate_required(
            "provenance.model.model_revision",
            &self.provenance.model.model_revision,
        )?;
        if self.provenance.phase.batch_size == 0 {
            return Err(LedgerError::InvalidField(
                "provenance.phase.batch_size".into(),
            ));
        }
        if self.provenance.phase.context_tokens == 0 {
            return Err(LedgerError::InvalidField(
                "provenance.phase.context_tokens".into(),
            ));
        }
        if self.provenance.phase.candidate_tokens == 0 {
            return Err(LedgerError::InvalidField(
                "provenance.phase.candidate_tokens".into(),
            ));
        }
        if self.provenance.phase.committed_tokens == 0 {
            return Err(LedgerError::InvalidField(
                "provenance.phase.committed_tokens".into(),
            ));
        }
        if self.provenance.phase.candidate_tokens < self.provenance.phase.committed_tokens {
            return Err(LedgerError::InvalidField(
                "provenance.phase.candidate_tokens".into(),
            ));
        }
        if self.actions.is_empty() {
            return Err(LedgerError::EmptyLedger);
        }

        let mut ids = BTreeSet::new();
        for action in &self.actions {
            validate_required("actions.id", action.id.as_str())?;
            if !ids.insert(action.id.clone()) {
                return Err(LedgerError::DuplicateActionId(action.id.clone()));
            }
            action.validate()?;
        }
        for action in &self.actions {
            let mut dependencies = BTreeSet::new();
            for dependency in &action.dependencies {
                if dependency == &action.id {
                    return Err(LedgerError::SelfDependency(action.id.clone()));
                }
                if !dependencies.insert(dependency) {
                    return Err(LedgerError::DuplicateDependency {
                        action_id: action.id.clone(),
                        dependency_id: dependency.clone(),
                    });
                }
                if !ids.contains(dependency) {
                    return Err(LedgerError::UnknownDependency {
                        action_id: action.id.clone(),
                        dependency_id: dependency.clone(),
                    });
                }
            }
        }
        self.topological_ids_unchecked()?;
        Ok(())
    }

    pub fn topological_action_ids(&self) -> Result<Vec<ActionId>, LedgerError> {
        self.validate()?;
        self.topological_ids_unchecked()
    }

    pub fn accounting(&self) -> Result<LedgerAccounting, LedgerError> {
        self.validate()?;
        let mut accounting = LedgerAccounting::default();
        for action in &self.actions {
            match &action.work {
                ActionWork::Compute(work) => {
                    accounting.flops = Flops::new(checked_add(
                        accounting.flops.get(),
                        work.flops.get(),
                        AccountingUnit::Flops,
                    )?);
                    accounting.non_flop_operations = Operations::new(checked_add(
                        accounting.non_flop_operations.get(),
                        work.non_flop_operations.get(),
                        AccountingUnit::Operations,
                    )?);
                    accounting.compute_actions =
                        checked_add(accounting.compute_actions, 1, AccountingUnit::Actions)?;
                }
                ActionWork::Memory(work) => {
                    accounting.memory_bytes = Bytes::new(checked_add(
                        accounting.memory_bytes.get(),
                        work.bytes.get(),
                        AccountingUnit::Bytes,
                    )?);
                    accounting.memory_actions =
                        checked_add(accounting.memory_actions, 1, AccountingUnit::Actions)?;
                }
                ActionWork::Cache(work) => {
                    accounting.cache_bytes = Bytes::new(checked_add(
                        accounting.cache_bytes.get(),
                        work.bytes.get(),
                        AccountingUnit::Bytes,
                    )?);
                    accounting.cache_actions =
                        checked_add(accounting.cache_actions, 1, AccountingUnit::Actions)?;
                }
                ActionWork::Network(work) => {
                    accounting.network_bytes = Bytes::new(checked_add(
                        accounting.network_bytes.get(),
                        work.aggregate_bytes.get(),
                        AccountingUnit::Bytes,
                    )?);
                    accounting.messages = Messages::new(checked_add(
                        accounting.messages.get(),
                        work.messages.get(),
                        AccountingUnit::Messages,
                    )?);
                    accounting.network_actions =
                        checked_add(accounting.network_actions, 1, AccountingUnit::Actions)?;
                }
                ActionWork::Synchronization(_) => {
                    accounting.synchronization_actions = checked_add(
                        accounting.synchronization_actions,
                        1,
                        AccountingUnit::Actions,
                    )?;
                }
                ActionWork::Scheduler(_) => {
                    accounting.scheduler_actions =
                        checked_add(accounting.scheduler_actions, 1, AccountingUnit::Actions)?;
                }
            }
        }
        Ok(accounting)
    }

    pub fn attach_measurements(
        &mut self,
        action_id: &ActionId,
        measurements: AdapterMeasurements,
    ) -> Result<(), LedgerError> {
        self.validate()?;
        measurements.validate(action_id)?;
        let action = self
            .actions
            .iter_mut()
            .find(|action| &action.id == action_id)
            .ok_or_else(|| LedgerError::UnknownAction(action_id.clone()))?;
        if action.measurements.is_some() {
            return Err(LedgerError::MeasurementsAlreadyAttached(action_id.clone()));
        }
        action.measurements = Some(measurements);
        Ok(())
    }

    pub fn total_latency(&self) -> Result<Seconds, LedgerError> {
        self.total_measurement(MeasurementMetric::Latency)
            .map(Seconds::new)
    }

    pub fn total_energy(&self) -> Result<Joules, LedgerError> {
        self.total_measurement(MeasurementMetric::Energy)
            .map(Joules::new)
    }

    pub fn total_cost(&self) -> Result<Usd, LedgerError> {
        self.total_measurement(MeasurementMetric::Cost)
            .map(Usd::new)
    }

    fn topological_ids_unchecked(&self) -> Result<Vec<ActionId>, LedgerError> {
        let mut indegree = BTreeMap::new();
        let mut children: BTreeMap<ActionId, Vec<ActionId>> = BTreeMap::new();
        for action in &self.actions {
            indegree.insert(action.id.clone(), action.dependencies.len());
            children.entry(action.id.clone()).or_default();
        }
        for action in &self.actions {
            for dependency in &action.dependencies {
                children
                    .entry(dependency.clone())
                    .or_default()
                    .push(action.id.clone());
            }
        }
        let mut ready = indegree
            .iter()
            .filter_map(|(id, count)| (*count == 0).then_some(id.clone()))
            .collect::<BTreeSet<_>>();
        let mut ordered = Vec::with_capacity(self.actions.len());
        while let Some(id) = ready.pop_first() {
            ordered.push(id.clone());
            for child in children.get(&id).into_iter().flatten() {
                let count = indegree
                    .get_mut(child)
                    .ok_or(LedgerError::DependencyCycle)?;
                *count = count.checked_sub(1).ok_or(LedgerError::DependencyCycle)?;
                if *count == 0 {
                    ready.insert(child.clone());
                }
            }
        }
        if ordered.len() == self.actions.len() {
            Ok(ordered)
        } else {
            Err(LedgerError::DependencyCycle)
        }
    }

    fn total_measurement(&self, metric: MeasurementMetric) -> Result<f64, LedgerError> {
        self.validate()?;
        let mut total = 0.0;
        for action in &self.actions {
            let measurements =
                action
                    .measurements
                    .as_ref()
                    .ok_or_else(|| LedgerError::MissingMeasurement {
                        action_id: action.id.clone(),
                        metric,
                    })?;
            let value = match metric {
                MeasurementMetric::Latency => measurements.latency.map(Seconds::get),
                MeasurementMetric::Energy => measurements.energy.map(Joules::get),
                MeasurementMetric::Cost => measurements.cost.map(Usd::get),
            }
            .ok_or_else(|| LedgerError::MissingMeasurement {
                action_id: action.id.clone(),
                metric,
            })?;
            total += value;
            if !total.is_finite() {
                return Err(LedgerError::MeasurementOverflow(metric));
            }
        }
        Ok(total)
    }
}

impl Action {
    fn validate(&self) -> Result<(), LedgerError> {
        validate_required(
            "actions.evidence.source_artifact_id",
            &self.evidence.source_artifact_id,
        )?;
        match &self.work {
            ActionWork::Compute(work) => {
                validate_required("actions.work.compute.label", &work.label)?;
                if work.flops.get() == 0 && work.non_flop_operations.get() == 0 {
                    return Err(LedgerError::InvalidField("actions.work.compute".into()));
                }
            }
            ActionWork::Memory(work) => {
                if work.source == work.destination {
                    return Err(LedgerError::InvalidField(
                        "actions.work.memory.destination".into(),
                    ));
                }
                validate_positive_bytes("actions.work.memory.bytes", work.bytes)?;
            }
            ActionWork::Cache(work) => {
                validate_positive_bytes("actions.work.cache.bytes", work.bytes)?;
                match (work.operation, work.hit) {
                    (CacheOperation::Lookup, None) => {
                        return Err(LedgerError::InvalidField("actions.work.cache.hit".into()));
                    }
                    (CacheOperation::Lookup, Some(_)) | (_, None) => {}
                    (_, Some(_)) => {
                        return Err(LedgerError::InvalidField("actions.work.cache.hit".into()));
                    }
                }
            }
            ActionWork::Network(work) => {
                validate_required("actions.work.network.source", &work.source)?;
                validate_required("actions.work.network.destination", &work.destination)?;
                validate_positive_bytes(
                    "actions.work.network.aggregate_bytes",
                    work.aggregate_bytes,
                )?;
                if work.messages.get() == 0 {
                    return Err(LedgerError::InvalidField(
                        "actions.work.network.messages".into(),
                    ));
                }
                if let NetworkPattern::Collective { participants, .. } = work.pattern
                    && participants < 2
                {
                    return Err(LedgerError::InvalidField(
                        "actions.work.network.pattern.participants".into(),
                    ));
                }
            }
            ActionWork::Synchronization(work) => {
                if work.participants == 0 {
                    return Err(LedgerError::InvalidField(
                        "actions.work.synchronization.participants".into(),
                    ));
                }
            }
            ActionWork::Scheduler(work) => {
                if work.requests == 0 {
                    return Err(LedgerError::InvalidField(
                        "actions.work.scheduler.requests".into(),
                    ));
                }
            }
        }
        if let Some(measurements) = &self.measurements {
            measurements.validate(&self.id)?;
        }
        Ok(())
    }
}

impl AdapterMeasurements {
    fn validate(&self, action_id: &ActionId) -> Result<(), LedgerError> {
        validate_required(
            "actions.measurements.provenance.adapter_id",
            &self.provenance.adapter_id,
        )?;
        validate_required(
            "actions.measurements.provenance.adapter_version",
            &self.provenance.adapter_version,
        )?;
        validate_required(
            "actions.measurements.provenance.calibration_artifact_id",
            &self.provenance.calibration_artifact_id,
        )?;
        validate_required(
            "actions.measurements.provenance.run_id",
            &self.provenance.run_id,
        )?;
        if self.latency.is_none() && self.energy.is_none() && self.cost.is_none() {
            return Err(LedgerError::InvalidField("actions.measurements".into()));
        }
        for (metric, value) in [
            (MeasurementMetric::Latency, self.latency.map(Seconds::get)),
            (MeasurementMetric::Energy, self.energy.map(Joules::get)),
            (MeasurementMetric::Cost, self.cost.map(Usd::get)),
        ] {
            if value.is_some_and(|value| !value.is_finite() || value < 0.0) {
                return Err(LedgerError::InvalidMeasurement {
                    action_id: action_id.clone(),
                    metric,
                });
            }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Default, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerAccounting {
    pub flops: Flops,
    pub non_flop_operations: Operations,
    pub memory_bytes: Bytes,
    pub cache_bytes: Bytes,
    pub network_bytes: Bytes,
    pub messages: Messages,
    pub compute_actions: u64,
    pub memory_actions: u64,
    pub cache_actions: u64,
    pub network_actions: u64,
    pub synchronization_actions: u64,
    pub scheduler_actions: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AccountingUnit {
    Flops,
    Operations,
    Bytes,
    Messages,
    Actions,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum MeasurementMetric {
    Latency,
    Energy,
    Cost,
}

#[derive(Debug, Error)]
pub enum LedgerError {
    #[error("unsupported action-ledger schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("required action-ledger field is invalid: {0}")]
    InvalidField(String),
    #[error("action ledger must contain at least one action")]
    EmptyLedger,
    #[error("duplicate action id: {0}")]
    DuplicateActionId(ActionId),
    #[error("action {0} depends on itself")]
    SelfDependency(ActionId),
    #[error("action {action_id} repeats dependency {dependency_id}")]
    DuplicateDependency {
        action_id: ActionId,
        dependency_id: ActionId,
    },
    #[error("action {action_id} references unknown dependency {dependency_id}")]
    UnknownDependency {
        action_id: ActionId,
        dependency_id: ActionId,
    },
    #[error("action dependency graph contains a cycle")]
    DependencyCycle,
    #[error("action-ledger accounting overflowed {0:?}")]
    AccountingOverflow(AccountingUnit),
    #[error("action {action_id} is missing calibrated {metric:?}")]
    MissingMeasurement {
        action_id: ActionId,
        metric: MeasurementMetric,
    },
    #[error("action {action_id} contains invalid calibrated {metric:?}")]
    InvalidMeasurement {
        action_id: ActionId,
        metric: MeasurementMetric,
    },
    #[error("calibrated {0:?} total overflowed")]
    MeasurementOverflow(MeasurementMetric),
    #[error("action measurements are already attached: {0}")]
    MeasurementsAlreadyAttached(ActionId),
    #[error("action does not exist: {0}")]
    UnknownAction(ActionId),
    #[error("action-ledger serialization failed: {0}")]
    Serialization(#[from] serde_json::Error),
}

fn validate_required(field: &str, value: &str) -> Result<(), LedgerError> {
    if value.trim().is_empty() {
        Err(LedgerError::InvalidField(field.into()))
    } else {
        Ok(())
    }
}

fn validate_positive_bytes(field: &str, bytes: Bytes) -> Result<(), LedgerError> {
    if bytes.get() == 0 {
        Err(LedgerError::InvalidField(field.into()))
    } else {
        Ok(())
    }
}

fn checked_add(left: u64, right: u64, unit: AccountingUnit) -> Result<u64, LedgerError> {
    left.checked_add(right)
        .ok_or(LedgerError::AccountingOverflow(unit))
}
