use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const GLM_TIERED_CACHE_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const GLM_TIERED_CACHE_REPORT_SCHEMA_VERSION: u32 = 1;
const EXCLUSIVE_LRU_POLICY: &str = "exclusive_lru_promote_on_hit";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CacheEvidenceKind {
    PublishedSpecification,
    MeasuredTrace,
    MeasuredHardware,
    SyntheticTrace,
    ModeledAssumption,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheEvidence {
    pub kind: CacheEvidenceKind,
    pub source_artifact_id: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheFootprint {
    pub mla_bytes_per_token: u64,
    pub indexer_bytes_per_token: u64,
    pub extra_bytes_per_token: u64,
    pub evidence: CacheEvidence,
}

impl CacheFootprint {
    fn total_bytes_per_token(&self) -> Result<u64, TieredCacheError> {
        self.mla_bytes_per_token
            .checked_add(self.indexer_bytes_per_token)
            .and_then(|value| value.checked_add(self.extra_bytes_per_token))
            .filter(|value| *value > 0)
            .ok_or(TieredCacheError::ArithmeticOverflow)
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheTierSpec {
    pub tier_id: String,
    pub capacity_bytes: u64,
    pub read_bandwidth_bytes_per_second: u64,
    pub write_bandwidth_bytes_per_second: u64,
    pub fixed_access_latency_microseconds: f64,
    pub evidence: CacheEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheLinkSpec {
    pub upper_tier_id: String,
    pub lower_tier_id: String,
    pub bandwidth_bytes_per_second: u64,
    pub fixed_latency_microseconds: f64,
    pub evidence: CacheEvidence,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TieredCacheScenario {
    pub scenario_id: String,
    pub policy: String,
    pub tiers: Vec<CacheTierSpec>,
    pub links: Vec<CacheLinkSpec>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheAccess {
    pub request_id: u64,
    pub arrival_timestamp_microseconds: u64,
    pub prefix_key: String,
    pub prefix_tokens: u32,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmTieredCacheRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub footprint: CacheFootprint,
    pub trace_evidence: CacheEvidence,
    pub accesses: Vec<CacheAccess>,
    pub scenarios: Vec<TieredCacheScenario>,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TieredCacheTotals {
    pub requests: u64,
    pub hit_requests: u64,
    pub miss_requests: u64,
    pub hot_tier_hit_requests: u64,
    pub lower_tier_hit_requests: u64,
    pub accessed_tokens: u64,
    pub hit_tokens: u64,
    pub miss_recompute_tokens: u64,
    pub promotion_bytes: u64,
    pub demotion_bytes: u64,
    pub link_transfer_bytes: u64,
    pub modeled_transfer_time_microseconds: f64,
    pub dropped_entries: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheTierReport {
    pub tier_id: String,
    pub capacity_bytes: u64,
    pub final_used_bytes: u64,
    pub peak_used_bytes: u64,
    pub hits: u64,
    pub insertions: u64,
    pub evictions: u64,
    pub dropped_evictions: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheLinkReport {
    pub upper_tier_id: String,
    pub lower_tier_id: String,
    pub promotion_bytes: u64,
    pub demotion_bytes: u64,
    pub total_bytes: u64,
    pub modeled_transfer_time_microseconds: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CacheAccessReport {
    pub request_id: u64,
    pub prefix_key: String,
    pub prefix_tokens: u32,
    pub entry_bytes: u64,
    pub hit_tier: Option<String>,
    pub promoted_to_tier: Option<String>,
    pub recompute_tokens: u32,
    pub link_transfer_bytes: u64,
    pub modeled_transfer_time_microseconds: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TieredCacheScenarioReport {
    pub scenario_id: String,
    pub policy: String,
    pub totals: TieredCacheTotals,
    pub tiers: Vec<CacheTierReport>,
    pub links: Vec<CacheLinkReport>,
    pub accesses: Vec<CacheAccessReport>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TieredCacheClaimBlocker {
    TraceIsNotMeasured,
    TierAndLinkTimingIsNotMeasured,
    RecomputeWorkIsNotCalibrated,
    ConcurrentContentionIsNotModeled,
    ServingIntegrationIsNotMeasured,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TieredCacheClaimGate {
    pub end_to_end_latency_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub blockers: Vec<TieredCacheClaimBlocker>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmTieredCacheResult {
    pub study_id: String,
    pub model_id: String,
    pub model_revision: String,
    pub footprint: CacheFootprint,
    pub total_bytes_per_token: u64,
    pub trace_evidence: CacheEvidence,
    pub scenarios: Vec<TieredCacheScenarioReport>,
    pub claims: TieredCacheClaimGate,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GlmTieredCacheReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: GlmTieredCacheResult,
}

impl GlmTieredCacheReport {
    pub fn verify_content_id(&self) -> Result<bool, TieredCacheError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

pub fn evaluate_glm_tiered_cache(
    request: &GlmTieredCacheRequest,
) -> Result<GlmTieredCacheReport, TieredCacheError> {
    let bytes_per_token = validate_request(request)?;
    let scenarios = request
        .scenarios
        .iter()
        .map(|scenario| ScenarioSimulator::new(scenario).run(&request.accesses, bytes_per_token))
        .collect::<Result<Vec<_>, _>>()?;
    let result = GlmTieredCacheResult {
        study_id: request.study_id.clone(),
        model_id: request.model_id.clone(),
        model_revision: request.model_revision.clone(),
        footprint: request.footprint.clone(),
        total_bytes_per_token: bytes_per_token,
        trace_evidence: request.trace_evidence.clone(),
        scenarios,
        claims: claim_gate(request),
    };
    let schema_version = GLM_TIERED_CACHE_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(GlmTieredCacheReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_request(request: &GlmTieredCacheRequest) -> Result<u64, TieredCacheError> {
    if request.schema_version != GLM_TIERED_CACHE_REQUEST_SCHEMA_VERSION {
        return Err(TieredCacheError::UnsupportedSchemaVersion {
            expected: GLM_TIERED_CACHE_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    for (field, value) in [
        ("study_id", request.study_id.as_str()),
        ("model_id", request.model_id.as_str()),
        ("model_revision", request.model_revision.as_str()),
    ] {
        validate_required(field, value)?;
    }
    validate_evidence("footprint.evidence", &request.footprint.evidence)?;
    validate_evidence("trace_evidence", &request.trace_evidence)?;
    let bytes_per_token = request.footprint.total_bytes_per_token()?;
    validate_accesses(&request.accesses, bytes_per_token)?;
    if request.scenarios.is_empty() {
        return Err(TieredCacheError::InvalidField("scenarios"));
    }
    let mut scenario_ids = BTreeSet::new();
    for scenario in &request.scenarios {
        if !scenario_ids.insert(scenario.scenario_id.as_str()) {
            return Err(TieredCacheError::DuplicateScenario(
                scenario.scenario_id.clone(),
            ));
        }
        validate_scenario(scenario)?;
    }
    Ok(bytes_per_token)
}

fn validate_accesses(
    accesses: &[CacheAccess],
    bytes_per_token: u64,
) -> Result<(), TieredCacheError> {
    if accesses.is_empty() {
        return Err(TieredCacheError::InvalidField("accesses"));
    }
    let mut request_ids = BTreeSet::new();
    let mut key_tokens = BTreeMap::new();
    let mut previous = None;
    for access in accesses {
        validate_required("accesses.prefix_key", &access.prefix_key)?;
        if access.prefix_tokens == 0 {
            return Err(TieredCacheError::InvalidField("accesses.prefix_tokens"));
        }
        if !request_ids.insert(access.request_id) {
            return Err(TieredCacheError::DuplicateRequest(access.request_id));
        }
        let canonical_key = (access.arrival_timestamp_microseconds, access.request_id);
        if previous.is_some_and(|value| canonical_key < value) {
            return Err(TieredCacheError::NonCanonicalAccessOrder);
        }
        previous = Some(canonical_key);
        if key_tokens
            .insert(access.prefix_key.as_str(), access.prefix_tokens)
            .is_some_and(|tokens| tokens != access.prefix_tokens)
        {
            return Err(TieredCacheError::InconsistentPrefixSize(
                access.prefix_key.clone(),
            ));
        }
        bytes_per_token
            .checked_mul(u64::from(access.prefix_tokens))
            .ok_or(TieredCacheError::ArithmeticOverflow)?;
    }
    Ok(())
}

fn validate_scenario(scenario: &TieredCacheScenario) -> Result<(), TieredCacheError> {
    validate_required("scenarios.scenario_id", &scenario.scenario_id)?;
    if scenario.policy != EXCLUSIVE_LRU_POLICY {
        return Err(TieredCacheError::UnsupportedPolicy(scenario.policy.clone()));
    }
    if scenario.tiers.is_empty() {
        return Err(TieredCacheError::InvalidField("scenarios.tiers"));
    }
    let mut tier_ids = BTreeSet::new();
    for tier in &scenario.tiers {
        validate_required("scenarios.tiers.tier_id", &tier.tier_id)?;
        validate_evidence("scenarios.tiers.evidence", &tier.evidence)?;
        if !tier_ids.insert(tier.tier_id.as_str()) {
            return Err(TieredCacheError::DuplicateTier(tier.tier_id.clone()));
        }
        if tier.capacity_bytes == 0
            || tier.read_bandwidth_bytes_per_second == 0
            || tier.write_bandwidth_bytes_per_second == 0
            || !tier.fixed_access_latency_microseconds.is_finite()
            || tier.fixed_access_latency_microseconds < 0.0
        {
            return Err(TieredCacheError::InvalidField("scenarios.tiers"));
        }
    }
    if scenario.links.len() + 1 != scenario.tiers.len() {
        return Err(TieredCacheError::InvalidField("scenarios.links"));
    }
    for (index, link) in scenario.links.iter().enumerate() {
        validate_evidence("scenarios.links.evidence", &link.evidence)?;
        if link.upper_tier_id != scenario.tiers[index].tier_id
            || link.lower_tier_id != scenario.tiers[index + 1].tier_id
            || link.bandwidth_bytes_per_second == 0
            || !link.fixed_latency_microseconds.is_finite()
            || link.fixed_latency_microseconds < 0.0
        {
            return Err(TieredCacheError::InvalidField("scenarios.links"));
        }
    }
    Ok(())
}

#[derive(Clone)]
struct EntryState {
    key: String,
    bytes: u64,
    last_access: u64,
}

struct TierState {
    spec: CacheTierSpec,
    entries: BTreeMap<String, EntryState>,
    used_bytes: u64,
    peak_used_bytes: u64,
    hits: u64,
    insertions: u64,
    evictions: u64,
    dropped_evictions: u64,
}

struct LinkState {
    spec: CacheLinkSpec,
    promotion_bytes: u64,
    demotion_bytes: u64,
    modeled_transfer_time_microseconds: f64,
}

#[derive(Default)]
struct Movement {
    promotion_bytes: u64,
    demotion_bytes: u64,
    link_transfer_bytes: u64,
    modeled_transfer_time_microseconds: f64,
}

struct ScenarioSimulator {
    scenario_id: String,
    policy: String,
    tiers: Vec<TierState>,
    links: Vec<LinkState>,
    totals: TieredCacheTotals,
    access_clock: u64,
}

impl ScenarioSimulator {
    fn new(scenario: &TieredCacheScenario) -> Self {
        Self {
            scenario_id: scenario.scenario_id.clone(),
            policy: scenario.policy.clone(),
            tiers: scenario
                .tiers
                .iter()
                .cloned()
                .map(|spec| TierState {
                    spec,
                    entries: BTreeMap::new(),
                    used_bytes: 0,
                    peak_used_bytes: 0,
                    hits: 0,
                    insertions: 0,
                    evictions: 0,
                    dropped_evictions: 0,
                })
                .collect(),
            links: scenario
                .links
                .iter()
                .cloned()
                .map(|spec| LinkState {
                    spec,
                    promotion_bytes: 0,
                    demotion_bytes: 0,
                    modeled_transfer_time_microseconds: 0.0,
                })
                .collect(),
            totals: TieredCacheTotals::default(),
            access_clock: 0,
        }
    }

    fn run(
        mut self,
        accesses: &[CacheAccess],
        bytes_per_token: u64,
    ) -> Result<TieredCacheScenarioReport, TieredCacheError> {
        let mut reports = Vec::with_capacity(accesses.len());
        for access in accesses {
            reports.push(self.access(access, bytes_per_token)?);
        }
        let tiers = self
            .tiers
            .into_iter()
            .map(|tier| CacheTierReport {
                tier_id: tier.spec.tier_id,
                capacity_bytes: tier.spec.capacity_bytes,
                final_used_bytes: tier.used_bytes,
                peak_used_bytes: tier.peak_used_bytes,
                hits: tier.hits,
                insertions: tier.insertions,
                evictions: tier.evictions,
                dropped_evictions: tier.dropped_evictions,
            })
            .collect();
        let links = self
            .links
            .into_iter()
            .map(|link| {
                Ok(CacheLinkReport {
                    upper_tier_id: link.spec.upper_tier_id,
                    lower_tier_id: link.spec.lower_tier_id,
                    promotion_bytes: link.promotion_bytes,
                    demotion_bytes: link.demotion_bytes,
                    total_bytes: checked_add(link.promotion_bytes, link.demotion_bytes)?,
                    modeled_transfer_time_microseconds: link.modeled_transfer_time_microseconds,
                })
            })
            .collect::<Result<Vec<_>, TieredCacheError>>()?;
        Ok(TieredCacheScenarioReport {
            scenario_id: self.scenario_id,
            policy: self.policy,
            totals: self.totals,
            tiers,
            links,
            accesses: reports,
        })
    }

    fn access(
        &mut self,
        access: &CacheAccess,
        bytes_per_token: u64,
    ) -> Result<CacheAccessReport, TieredCacheError> {
        self.access_clock = self
            .access_clock
            .checked_add(1)
            .ok_or(TieredCacheError::ArithmeticOverflow)?;
        self.totals.requests = checked_add(self.totals.requests, 1)?;
        self.totals.accessed_tokens =
            checked_add(self.totals.accessed_tokens, u64::from(access.prefix_tokens))?;
        let entry_bytes = bytes_per_token
            .checked_mul(u64::from(access.prefix_tokens))
            .ok_or(TieredCacheError::ArithmeticOverflow)?;
        let hit_index = self
            .tiers
            .iter()
            .position(|tier| tier.entries.contains_key(&access.prefix_key));
        let mut movement = Movement::default();
        let mut hit_tier = None;
        let mut promoted_to_tier = None;
        let recompute_tokens;
        if let Some(source_index) = hit_index {
            hit_tier = Some(self.tiers[source_index].spec.tier_id.clone());
            self.tiers[source_index].hits = checked_add(self.tiers[source_index].hits, 1)?;
            self.totals.hit_requests = checked_add(self.totals.hit_requests, 1)?;
            self.totals.hit_tokens =
                checked_add(self.totals.hit_tokens, u64::from(access.prefix_tokens))?;
            recompute_tokens = 0;
            if source_index == 0 {
                self.totals.hot_tier_hit_requests =
                    checked_add(self.totals.hot_tier_hit_requests, 1)?;
                self.tiers[0]
                    .entries
                    .get_mut(&access.prefix_key)
                    .ok_or(TieredCacheError::ArithmeticOverflow)?
                    .last_access = self.access_clock;
            } else {
                self.totals.lower_tier_hit_requests =
                    checked_add(self.totals.lower_tier_hit_requests, 1)?;
                let target_index = (0..source_index)
                    .find(|index| self.tiers[*index].spec.capacity_bytes >= entry_bytes)
                    .unwrap_or(source_index);
                if target_index < source_index {
                    let mut entry = self.remove_entry(source_index, &access.prefix_key)?;
                    entry.last_access = self.access_clock;
                    self.charge_promotion(target_index, source_index, entry.bytes, &mut movement)?;
                    promoted_to_tier = Some(self.tiers[target_index].spec.tier_id.clone());
                    self.place_entry(target_index, entry, &mut movement)?;
                } else {
                    self.tiers[source_index]
                        .entries
                        .get_mut(&access.prefix_key)
                        .ok_or(TieredCacheError::ArithmeticOverflow)?
                        .last_access = self.access_clock;
                }
            }
        } else {
            self.totals.miss_requests = checked_add(self.totals.miss_requests, 1)?;
            self.totals.miss_recompute_tokens = checked_add(
                self.totals.miss_recompute_tokens,
                u64::from(access.prefix_tokens),
            )?;
            recompute_tokens = access.prefix_tokens;
            let entry = EntryState {
                key: access.prefix_key.clone(),
                bytes: entry_bytes,
                last_access: self.access_clock,
            };
            if let Some(target_index) = self
                .tiers
                .iter()
                .position(|tier| tier.spec.capacity_bytes >= entry_bytes)
            {
                if target_index > 0 {
                    self.charge_demotion(0, target_index, entry.bytes, &mut movement)?;
                }
                self.place_entry(target_index, entry, &mut movement)?;
            } else {
                self.totals.dropped_entries = checked_add(self.totals.dropped_entries, 1)?;
            }
        }
        self.record_movement(&movement)?;
        Ok(CacheAccessReport {
            request_id: access.request_id,
            prefix_key: access.prefix_key.clone(),
            prefix_tokens: access.prefix_tokens,
            entry_bytes,
            hit_tier,
            promoted_to_tier,
            recompute_tokens,
            link_transfer_bytes: movement.link_transfer_bytes,
            modeled_transfer_time_microseconds: movement.modeled_transfer_time_microseconds,
        })
    }

    fn place_entry(
        &mut self,
        tier_index: usize,
        entry: EntryState,
        movement: &mut Movement,
    ) -> Result<(), TieredCacheError> {
        while self.tiers[tier_index]
            .used_bytes
            .checked_add(entry.bytes)
            .ok_or(TieredCacheError::ArithmeticOverflow)?
            > self.tiers[tier_index].spec.capacity_bytes
        {
            let eviction_key = self.tiers[tier_index]
                .entries
                .values()
                .min_by_key(|candidate| (candidate.last_access, candidate.key.as_str()))
                .map(|candidate| candidate.key.clone())
                .ok_or(TieredCacheError::ArithmeticOverflow)?;
            let evicted = self.remove_entry(tier_index, &eviction_key)?;
            self.tiers[tier_index].evictions = checked_add(self.tiers[tier_index].evictions, 1)?;
            self.demote_entry(tier_index, evicted, movement)?;
        }
        self.tiers[tier_index].used_bytes = self.tiers[tier_index]
            .used_bytes
            .checked_add(entry.bytes)
            .ok_or(TieredCacheError::ArithmeticOverflow)?;
        self.tiers[tier_index].peak_used_bytes = self.tiers[tier_index]
            .peak_used_bytes
            .max(self.tiers[tier_index].used_bytes);
        self.tiers[tier_index].insertions = checked_add(self.tiers[tier_index].insertions, 1)?;
        self.tiers[tier_index]
            .entries
            .insert(entry.key.clone(), entry);
        Ok(())
    }

    fn demote_entry(
        &mut self,
        source_index: usize,
        entry: EntryState,
        movement: &mut Movement,
    ) -> Result<(), TieredCacheError> {
        let target_index = ((source_index + 1)..self.tiers.len())
            .find(|index| self.tiers[*index].spec.capacity_bytes >= entry.bytes);
        if let Some(target_index) = target_index {
            self.charge_demotion(source_index, target_index, entry.bytes, movement)?;
            self.place_entry(target_index, entry, movement)
        } else {
            self.tiers[source_index].dropped_evictions =
                checked_add(self.tiers[source_index].dropped_evictions, 1)?;
            self.totals.dropped_entries = checked_add(self.totals.dropped_entries, 1)?;
            Ok(())
        }
    }

    fn remove_entry(
        &mut self,
        tier_index: usize,
        key: &str,
    ) -> Result<EntryState, TieredCacheError> {
        let entry = self.tiers[tier_index]
            .entries
            .remove(key)
            .ok_or(TieredCacheError::ArithmeticOverflow)?;
        self.tiers[tier_index].used_bytes = self.tiers[tier_index]
            .used_bytes
            .checked_sub(entry.bytes)
            .ok_or(TieredCacheError::ArithmeticOverflow)?;
        Ok(entry)
    }

    fn charge_promotion(
        &mut self,
        target_index: usize,
        source_index: usize,
        bytes: u64,
        movement: &mut Movement,
    ) -> Result<(), TieredCacheError> {
        for link_index in target_index..source_index {
            let microseconds = self.link_time_microseconds(link_index, bytes, true);
            self.links[link_index].promotion_bytes =
                checked_add(self.links[link_index].promotion_bytes, bytes)?;
            self.links[link_index].modeled_transfer_time_microseconds += microseconds;
            movement.promotion_bytes = checked_add(movement.promotion_bytes, bytes)?;
            movement.link_transfer_bytes = checked_add(movement.link_transfer_bytes, bytes)?;
            movement.modeled_transfer_time_microseconds += microseconds;
        }
        Ok(())
    }

    fn charge_demotion(
        &mut self,
        source_index: usize,
        target_index: usize,
        bytes: u64,
        movement: &mut Movement,
    ) -> Result<(), TieredCacheError> {
        for link_index in source_index..target_index {
            let microseconds = self.link_time_microseconds(link_index, bytes, false);
            self.links[link_index].demotion_bytes =
                checked_add(self.links[link_index].demotion_bytes, bytes)?;
            self.links[link_index].modeled_transfer_time_microseconds += microseconds;
            movement.demotion_bytes = checked_add(movement.demotion_bytes, bytes)?;
            movement.link_transfer_bytes = checked_add(movement.link_transfer_bytes, bytes)?;
            movement.modeled_transfer_time_microseconds += microseconds;
        }
        Ok(())
    }

    fn link_time_microseconds(&self, link_index: usize, bytes: u64, promotion: bool) -> f64 {
        let upper = &self.tiers[link_index].spec;
        let lower = &self.tiers[link_index + 1].spec;
        let link = &self.links[link_index].spec;
        let bytes = bytes as f64;
        let (read_bandwidth, write_bandwidth) = if promotion {
            (
                lower.read_bandwidth_bytes_per_second,
                upper.write_bandwidth_bytes_per_second,
            )
        } else {
            (
                upper.read_bandwidth_bytes_per_second,
                lower.write_bandwidth_bytes_per_second,
            )
        };
        upper.fixed_access_latency_microseconds
            + lower.fixed_access_latency_microseconds
            + link.fixed_latency_microseconds
            + 1_000_000.0
                * bytes
                * (1.0 / read_bandwidth as f64
                    + 1.0 / link.bandwidth_bytes_per_second as f64
                    + 1.0 / write_bandwidth as f64)
    }

    fn record_movement(&mut self, movement: &Movement) -> Result<(), TieredCacheError> {
        self.totals.promotion_bytes =
            checked_add(self.totals.promotion_bytes, movement.promotion_bytes)?;
        self.totals.demotion_bytes =
            checked_add(self.totals.demotion_bytes, movement.demotion_bytes)?;
        self.totals.link_transfer_bytes = checked_add(
            self.totals.link_transfer_bytes,
            movement.link_transfer_bytes,
        )?;
        self.totals.modeled_transfer_time_microseconds +=
            movement.modeled_transfer_time_microseconds;
        if !self.totals.modeled_transfer_time_microseconds.is_finite() {
            return Err(TieredCacheError::ArithmeticOverflow);
        }
        Ok(())
    }
}

fn claim_gate(request: &GlmTieredCacheRequest) -> TieredCacheClaimGate {
    let mut blockers = Vec::new();
    if request.trace_evidence.kind != CacheEvidenceKind::MeasuredTrace {
        blockers.push(TieredCacheClaimBlocker::TraceIsNotMeasured);
    }
    if request.scenarios.iter().any(|scenario| {
        scenario
            .tiers
            .iter()
            .any(|tier| tier.evidence.kind != CacheEvidenceKind::MeasuredHardware)
            || scenario
                .links
                .iter()
                .any(|link| link.evidence.kind != CacheEvidenceKind::MeasuredHardware)
    }) {
        blockers.push(TieredCacheClaimBlocker::TierAndLinkTimingIsNotMeasured);
    }
    blockers.push(TieredCacheClaimBlocker::RecomputeWorkIsNotCalibrated);
    blockers.push(TieredCacheClaimBlocker::ConcurrentContentionIsNotModeled);
    blockers.push(TieredCacheClaimBlocker::ServingIntegrationIsNotMeasured);
    TieredCacheClaimGate {
        end_to_end_latency_claim_permitted: false,
        cost_per_token_claim_permitted: false,
        blockers,
    }
}

fn checked_add(left: u64, right: u64) -> Result<u64, TieredCacheError> {
    left.checked_add(right)
        .ok_or(TieredCacheError::ArithmeticOverflow)
}

fn validate_evidence(
    field: &'static str,
    evidence: &CacheEvidence,
) -> Result<(), TieredCacheError> {
    validate_required(field, &evidence.source_artifact_id)
}

fn validate_required(field: &'static str, value: &str) -> Result<(), TieredCacheError> {
    if value.trim().is_empty() {
        Err(TieredCacheError::InvalidField(field))
    } else {
        Ok(())
    }
}

#[derive(Serialize)]
struct HashableReport<'a> {
    schema_version: u32,
    result: &'a GlmTieredCacheResult,
}

fn report_content_id(
    schema_version: u32,
    result: &GlmTieredCacheResult,
) -> Result<String, TieredCacheError> {
    let bytes = serde_json::to_vec(&HashableReport {
        schema_version,
        result,
    })
    .map_err(|error| TieredCacheError::Serialization(error.to_string()))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

#[derive(Clone, Debug, Error, PartialEq)]
pub enum TieredCacheError {
    #[error("unsupported GLM tiered-cache schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid GLM tiered-cache field {0}")]
    InvalidField(&'static str),
    #[error("unsupported tiered-cache policy {0}")]
    UnsupportedPolicy(String),
    #[error("duplicate tiered-cache scenario {0}")]
    DuplicateScenario(String),
    #[error("duplicate tier {0}")]
    DuplicateTier(String),
    #[error("duplicate cache access request {0}")]
    DuplicateRequest(u64),
    #[error("cache accesses are not ordered by arrival timestamp and request id")]
    NonCanonicalAccessOrder,
    #[error("prefix key {0} has inconsistent token sizes")]
    InconsistentPrefixSize(String),
    #[error("GLM tiered-cache arithmetic overflowed")]
    ArithmeticOverflow,
    #[error("GLM tiered-cache serialization failed: {0}")]
    Serialization(String),
}
