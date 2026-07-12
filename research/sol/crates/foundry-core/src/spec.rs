use serde::{Deserialize, Serialize};
use std::fmt;

pub const CURRENT_SCHEMA_VERSION: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExperimentSpec {
    pub schema_version: u32,
    pub experiment_name: String,
    pub model: ModelSpec,
    pub quality_suite_id: String,
    pub workload: AgenticWorkloadSpec,
    pub hardware: HardwareSpec,
    pub kernel: KernelSpec,
    pub mapping: ExecutionMappingSpec,
    pub serving: ServingSpec,
    pub economics: EconomicsSpec,
    pub quality_constraints: Vec<QualityConstraint>,
    pub search_space: SearchSpace,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ModelSpec {
    pub model_id: String,
    pub model_revision: String,
    pub architecture: ModelArchitecture,
    pub parameter_count: u64,
    pub layer_count: u32,
    pub hidden_size: u32,
    pub intermediate_size: u32,
    pub attention_head_count: u32,
    pub kv_head_count: u32,
    pub head_dimension: u32,
    pub vocabulary_size: u32,
    pub max_sequence_length: u32,
    pub weight_precision: Precision,
    #[serde(default)]
    pub quantized_weight_storage: Option<QuantizedWeightStorageSpec>,
    pub kv_precision: Precision,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum QuantizedWeightCoverage {
    Fraction { numerator: u64, denominator: u64 },
    Count { parameters: u64 },
}

impl QuantizedWeightCoverage {
    fn resolve(&self, total_parameters: u64) -> Option<u64> {
        match self {
            Self::Fraction {
                numerator,
                denominator,
            } => {
                if *numerator == 0 || *denominator == 0 || numerator > denominator {
                    return None;
                }
                let scaled = u128::from(total_parameters).checked_mul(u128::from(*numerator))?;
                if scaled % u128::from(*denominator) != 0 {
                    return None;
                }
                u64::try_from(scaled / u128::from(*denominator)).ok()
            }
            Self::Count { parameters } => {
                (*parameters > 0 && *parameters <= total_parameters).then_some(*parameters)
            }
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(deny_unknown_fields)]
pub struct QuantizedWeightStorageSpec {
    pub coverage: QuantizedWeightCoverage,
    pub group_size: u32,
    pub code_bits: u8,
    pub scale_bits: u8,
    pub unquantized_bits: u8,
    pub fixed_metadata_bytes: u64,
}

impl QuantizedWeightStorageSpec {
    pub fn grouped_all(
        group_size: u32,
        code_bits: u8,
        scale_bits: u8,
        unquantized_bits: u8,
        fixed_metadata_bytes: u64,
    ) -> Self {
        Self {
            coverage: QuantizedWeightCoverage::Fraction {
                numerator: 1,
                denominator: 1,
            },
            group_size,
            code_bits,
            scale_bits,
            unquantized_bits,
            fixed_metadata_bytes,
        }
    }

    pub fn payload_bits_per_quantized_weight(&self) -> Option<f64> {
        (self.group_size > 0 && self.code_bits > 0 && self.scale_bits > 0).then(|| {
            f64::from(self.code_bits) + f64::from(self.scale_bits) / f64::from(self.group_size)
        })
    }

    pub(crate) fn stored_bits(&self, total_parameters: u64) -> Option<u128> {
        if self.group_size == 0
            || self.code_bits == 0
            || self.scale_bits == 0
            || self.unquantized_bits == 0
        {
            return None;
        }
        let quantized = self.coverage.resolve(total_parameters)?;
        let unquantized = total_parameters.checked_sub(quantized)?;
        let groups = quantized.div_ceil(u64::from(self.group_size));
        u128::from(quantized)
            .checked_mul(u128::from(self.code_bits))?
            .checked_add(u128::from(groups).checked_mul(u128::from(self.scale_bits))?)?
            .checked_add(u128::from(unquantized).checked_mul(u128::from(self.unquantized_bits))?)?
            .checked_add(u128::from(self.fixed_metadata_bytes).checked_mul(8)?)
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum ModelArchitecture {
    DenseDecoder,
    HybridMoeMlaDsa(HybridMoeMlaDsaSpec),
}

pub const HYBRID_MOE_MLA_DSA_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ActiveParameterCount {
    Exact { parameters: u64 },
    Approximate { parameters: u64 },
}

impl ActiveParameterCount {
    pub const fn parameters(self) -> u64 {
        match self {
            Self::Exact { parameters } | Self::Approximate { parameters } => parameters,
        }
    }

    pub const fn exact(self) -> Option<u64> {
        match self {
            Self::Exact { parameters } => Some(parameters),
            Self::Approximate { .. } => None,
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(deny_unknown_fields)]
pub struct HybridMoeMlaDsaSpec {
    pub schema_version: u32,
    pub active_parameter_count: ActiveParameterCount,
    pub checkpoint_fixed_storage_bytes: u64,
    pub dense_layer_count: u32,
    pub moe_layer_count: u32,
    pub moe: MoeSpec,
    pub mla: MlaSpec,
    pub dsa_indexer: DsaIndexerSpec,
    pub mtp: MtpSpec,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(deny_unknown_fields)]
pub struct MoeSpec {
    pub routed_expert_count: u32,
    pub routed_experts_per_token: u32,
    pub shared_expert_count: u32,
    pub expert_intermediate_size: u32,
    pub routed_expert_weight_precision: Precision,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub routed_expert_quantized_weight_storage: Option<QuantizedWeightStorageSpec>,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(deny_unknown_fields)]
pub struct MlaSpec {
    pub query_low_rank_dimension: u32,
    pub semantic_kv_dimension: u32,
    pub query_key_nope_dimension: u32,
    pub rotary_kv_dimension: u32,
    pub value_dimension: u32,
    pub rope_theta: u64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(deny_unknown_fields)]
pub struct DsaIndexerSpec {
    pub query_head_count: u32,
    pub query_head_dimension: u32,
    pub key_head_count: u32,
    pub key_head_dimension: u32,
    pub selected_token_count: u32,
    pub full_layer_count: u32,
    pub shared_layer_count: u32,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(deny_unknown_fields)]
pub struct MtpSpec {
    pub layer_count: u32,
    pub shared_parameters: bool,
    pub shares_dsa_indices: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum Precision {
    Fp32,
    Bf16,
    Fp16,
    Fp8,
    Int8,
    Int4,
    Int3,
    Int2,
}

impl Precision {
    pub const fn bits(self) -> u8 {
        match self {
            Self::Fp32 => 32,
            Self::Bf16 | Self::Fp16 => 16,
            Self::Fp8 | Self::Int8 => 8,
            Self::Int4 => 4,
            Self::Int3 => 3,
            Self::Int2 => 2,
        }
    }

    pub fn bytes_per_element(self) -> f64 {
        f64::from(self.bits()) / 8.0
    }
}

impl ModelSpec {
    pub fn validate(&self) -> Result<(), ValidationErrors> {
        let mut validator = Validator::default();
        self.validate_into(&mut validator);
        validator.finish()
    }

    pub fn weight_bytes(&self) -> Option<u64> {
        bits_to_packed_bytes(self.weight_storage_bits()?)
    }

    pub fn weight_storage_bits(&self) -> Option<u128> {
        let Some(hybrid) = self.hybrid_spec() else {
            return stored_weight_bits(
                self.parameter_count,
                self.weight_precision,
                self.quantized_weight_storage.as_ref(),
            );
        };
        let routed = hybrid.routed_expert_parameter_count(self.hidden_size)?;
        let non_routed = self.parameter_count.checked_sub(routed)?;
        let parameter_bits = stored_weight_bits(
            non_routed,
            self.weight_precision,
            self.quantized_weight_storage.as_ref(),
        )?
        .checked_add(stored_weight_bits(
            routed,
            hybrid.moe.routed_expert_weight_precision,
            hybrid.moe.routed_expert_quantized_weight_storage.as_ref(),
        )?)?;
        parameter_bits
            .checked_add(u128::from(hybrid.checkpoint_fixed_storage_bytes).checked_mul(8)?)
    }

    pub fn effective_weight_storage_bits(&self) -> Option<f64> {
        if self.parameter_count == 0 {
            return None;
        }
        Some(self.weight_storage_bits()? as f64 / self.parameter_count as f64)
    }

    pub fn reported_active_parameter_count(&self) -> u64 {
        match self.architecture {
            ModelArchitecture::DenseDecoder => self.parameter_count,
            ModelArchitecture::HybridMoeMlaDsa(hybrid) => {
                hybrid.active_parameter_count.parameters()
            }
        }
    }

    pub fn exact_active_parameter_count(&self) -> Option<u64> {
        match self.architecture {
            ModelArchitecture::DenseDecoder => Some(self.parameter_count),
            ModelArchitecture::HybridMoeMlaDsa(hybrid) => hybrid.active_parameter_count.exact(),
        }
    }

    pub fn active_weight_bytes(&self) -> Option<u64> {
        bits_to_packed_bytes(self.active_weight_storage_bits()?)
    }

    pub fn active_weight_storage_bits(&self) -> Option<u128> {
        let active = self.exact_active_parameter_count()?;
        let Some(hybrid) = self.hybrid_spec() else {
            return stored_weight_bits(
                active,
                self.weight_precision,
                self.quantized_weight_storage.as_ref(),
            );
        };
        let routed = hybrid.active_routed_expert_parameter_count(self.hidden_size)?;
        let non_routed = active.checked_sub(routed)?;
        stored_weight_bits(
            non_routed,
            self.weight_precision,
            self.quantized_weight_storage.as_ref(),
        )?
        .checked_add(stored_weight_bits(
            routed,
            hybrid.moe.routed_expert_weight_precision,
            hybrid.moe.routed_expert_quantized_weight_storage.as_ref(),
        )?)
    }

    pub fn kv_bytes_per_token(&self) -> Option<u64> {
        if !self.has_complete_kv_cache_accounting() {
            return None;
        }
        self.semantic_kv_bytes_per_token()
    }

    pub fn semantic_kv_bytes_per_token(&self) -> Option<u64> {
        let elements = match self.architecture {
            ModelArchitecture::DenseDecoder => u128::from(self.layer_count)
                .checked_mul(u128::from(self.kv_head_count))?
                .checked_mul(u128::from(self.head_dimension))?
                .checked_mul(2)?,
            ModelArchitecture::HybridMoeMlaDsa(hybrid) => u128::from(self.layer_count)
                .checked_mul(u128::from(
                    hybrid
                        .mla
                        .semantic_kv_dimension
                        .checked_add(hybrid.mla.rotary_kv_dimension)?,
                ))?,
        };
        packed_bytes(elements, self.kv_precision)
    }

    pub const fn has_complete_kv_cache_accounting(&self) -> bool {
        matches!(self.architecture, ModelArchitecture::DenseDecoder)
    }

    pub const fn hybrid_spec(&self) -> Option<&HybridMoeMlaDsaSpec> {
        match &self.architecture {
            ModelArchitecture::DenseDecoder => None,
            ModelArchitecture::HybridMoeMlaDsa(hybrid) => Some(hybrid),
        }
    }

    pub fn routed_expert_parameter_count(&self) -> Option<u64> {
        self.hybrid_spec()?
            .routed_expert_parameter_count(self.hidden_size)
    }

    pub fn active_routed_expert_parameter_count(&self) -> Option<u64> {
        self.hybrid_spec()?
            .active_routed_expert_parameter_count(self.hidden_size)
    }

    pub fn shared_expert_parameter_count(&self) -> Option<u64> {
        self.hybrid_spec()?
            .shared_expert_parameter_count(self.hidden_size)
    }

    pub fn dense_mlp_parameter_count(&self) -> Option<u64> {
        self.hybrid_spec()?
            .dense_mlp_parameter_count(self.hidden_size, self.intermediate_size)
    }

    pub fn stored_feed_forward_parameter_count(&self) -> Option<u64> {
        self.hybrid_spec()?
            .stored_feed_forward_parameter_count(self.hidden_size, self.intermediate_size)
    }

    pub fn active_feed_forward_parameter_count_per_token(&self) -> Option<u64> {
        self.hybrid_spec()?
            .active_feed_forward_parameter_count_per_token(self.hidden_size, self.intermediate_size)
    }

    pub fn active_feed_forward_flops_per_token(&self) -> Option<u128> {
        u128::from(self.active_feed_forward_parameter_count_per_token()?).checked_mul(2)
    }

    pub fn dsa_indexer_parameters_per_full_layer(&self) -> Option<u64> {
        self.hybrid_spec()?
            .dsa_indexer_parameters_per_full_layer(self.hidden_size)
    }

    pub fn dsa_indexer_parameter_count(&self) -> Option<u64> {
        self.hybrid_spec()?
            .dsa_indexer_parameter_count(self.hidden_size)
    }
}

impl HybridMoeMlaDsaSpec {
    fn routed_expert_parameter_count(self, hidden_size: u32) -> Option<u64> {
        gated_mlp_parameter_count(
            self.moe_layer_count,
            self.moe.routed_expert_count,
            hidden_size,
            self.moe.expert_intermediate_size,
        )
    }

    fn active_routed_expert_parameter_count(self, hidden_size: u32) -> Option<u64> {
        gated_mlp_parameter_count(
            self.moe_layer_count,
            self.moe.routed_experts_per_token,
            hidden_size,
            self.moe.expert_intermediate_size,
        )
    }

    fn shared_expert_parameter_count(self, hidden_size: u32) -> Option<u64> {
        gated_mlp_parameter_count(
            self.moe_layer_count,
            self.moe.shared_expert_count,
            hidden_size,
            self.moe.expert_intermediate_size,
        )
    }

    fn dense_mlp_parameter_count(self, hidden_size: u32, intermediate_size: u32) -> Option<u64> {
        gated_mlp_parameter_count(self.dense_layer_count, 1, hidden_size, intermediate_size)
    }

    fn stored_feed_forward_parameter_count(
        self,
        hidden_size: u32,
        intermediate_size: u32,
    ) -> Option<u64> {
        self.routed_expert_parameter_count(hidden_size)?
            .checked_add(self.shared_expert_parameter_count(hidden_size)?)?
            .checked_add(self.dense_mlp_parameter_count(hidden_size, intermediate_size)?)
    }

    fn active_feed_forward_parameter_count_per_token(
        self,
        hidden_size: u32,
        intermediate_size: u32,
    ) -> Option<u64> {
        self.active_routed_expert_parameter_count(hidden_size)?
            .checked_add(self.shared_expert_parameter_count(hidden_size)?)?
            .checked_add(self.dense_mlp_parameter_count(hidden_size, intermediate_size)?)
    }

    fn dsa_indexer_parameters_per_full_layer(self, hidden_size: u32) -> Option<u64> {
        let query_projection = checked_product_u64(&[
            u64::from(self.mla.query_low_rank_dimension),
            u64::from(self.dsa_indexer.query_head_count),
            u64::from(self.dsa_indexer.query_head_dimension),
        ])?;
        let key_projection = checked_product_u64(&[
            u64::from(hidden_size),
            u64::from(self.dsa_indexer.key_head_count),
            u64::from(self.dsa_indexer.key_head_dimension),
        ])?;
        let head_weight_projection = checked_product_u64(&[
            u64::from(hidden_size),
            u64::from(self.dsa_indexer.query_head_count),
        ])?;
        let key_norm = checked_product_u64(&[
            2,
            u64::from(self.dsa_indexer.key_head_count),
            u64::from(self.dsa_indexer.key_head_dimension),
        ])?;
        query_projection
            .checked_add(key_projection)?
            .checked_add(head_weight_projection)?
            .checked_add(key_norm)
    }

    fn dsa_indexer_parameter_count(self, hidden_size: u32) -> Option<u64> {
        self.dsa_indexer_parameters_per_full_layer(hidden_size)?
            .checked_mul(u64::from(self.dsa_indexer.full_layer_count))
    }
}

fn gated_mlp_parameter_count(
    layer_count: u32,
    expert_count: u32,
    hidden_size: u32,
    intermediate_size: u32,
) -> Option<u64> {
    checked_product_u64(&[
        u64::from(layer_count),
        u64::from(expert_count),
        3,
        u64::from(hidden_size),
        u64::from(intermediate_size),
    ])
}

fn checked_product_u64(values: &[u64]) -> Option<u64> {
    values
        .iter()
        .try_fold(1_u64, |product, value| product.checked_mul(*value))
}

pub fn glm_5_2_bf16_reference() -> ModelSpec {
    ModelSpec {
        model_id: "zai-org/GLM-5.2".into(),
        model_revision: "b4734de4facf877f85769a911abafc5283eab3d9".into(),
        architecture: ModelArchitecture::HybridMoeMlaDsa(HybridMoeMlaDsaSpec {
            schema_version: HYBRID_MOE_MLA_DSA_SCHEMA_VERSION,
            active_parameter_count: ActiveParameterCount::Approximate {
                parameters: 40_000_000_000,
            },
            checkpoint_fixed_storage_bytes: 38_912,
            dense_layer_count: 3,
            moe_layer_count: 75,
            moe: MoeSpec {
                routed_expert_count: 256,
                routed_experts_per_token: 8,
                shared_expert_count: 1,
                expert_intermediate_size: 2_048,
                routed_expert_weight_precision: Precision::Bf16,
                routed_expert_quantized_weight_storage: None,
            },
            mla: MlaSpec {
                query_low_rank_dimension: 2_048,
                semantic_kv_dimension: 512,
                query_key_nope_dimension: 192,
                rotary_kv_dimension: 64,
                value_dimension: 256,
                rope_theta: 8_000_000,
            },
            dsa_indexer: DsaIndexerSpec {
                query_head_count: 32,
                query_head_dimension: 128,
                key_head_count: 1,
                key_head_dimension: 128,
                selected_token_count: 2_048,
                full_layer_count: 21,
                shared_layer_count: 57,
            },
            mtp: MtpSpec {
                layer_count: 1,
                shared_parameters: true,
                shares_dsa_indices: true,
            },
        }),
        parameter_count: 753_329_940_480,
        layer_count: 78,
        hidden_size: 6_144,
        intermediate_size: 12_288,
        attention_head_count: 64,
        kv_head_count: 0,
        head_dimension: 256,
        vocabulary_size: 154_880,
        max_sequence_length: 1_048_576,
        weight_precision: Precision::Bf16,
        quantized_weight_storage: None,
        kv_precision: Precision::Bf16,
    }
}

fn packed_bytes(elements: u128, precision: Precision) -> Option<u64> {
    let bits = elements.checked_mul(u128::from(precision.bits()))?;
    bits_to_packed_bytes(bits)
}

pub(crate) fn stored_weight_bits(
    parameter_count: u64,
    arithmetic_precision: Precision,
    quantized_storage: Option<&QuantizedWeightStorageSpec>,
) -> Option<u128> {
    match quantized_storage {
        Some(storage) => storage.stored_bits(parameter_count),
        None => u128::from(parameter_count).checked_mul(u128::from(arithmetic_precision.bits())),
    }
}

pub(crate) fn stored_weight_bytes(
    parameter_count: u64,
    arithmetic_precision: Precision,
    quantized_storage: Option<&QuantizedWeightStorageSpec>,
) -> Option<u64> {
    bits_to_packed_bytes(stored_weight_bits(
        parameter_count,
        arithmetic_precision,
        quantized_storage,
    )?)
}

fn bits_to_packed_bytes(bits: u128) -> Option<u64> {
    u64::try_from(bits.checked_add(7)?.checked_div(8)?).ok()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AgenticWorkloadSpec {
    pub seed: u64,
    pub request_count: u64,
    pub arrival_rate_per_second: f64,
    pub request_classes: Vec<RequestClass>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RequestClass {
    pub name: String,
    pub share: f64,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub prefix_cache_hit_ratio: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HardwareSpec {
    pub name: String,
    pub fidelity: HardwareFidelity,
    pub physical_device_count: u32,
    pub aggregate: Option<AggregateHardwareSpec>,
    pub design: Option<HardwareDesignSpec>,
    pub accelerator_hourly_cost_usd: f64,
    pub host_hourly_cost_usd: f64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum HardwareFidelity {
    Analytical,
    Architecture,
    Rtl,
    Measured,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AggregateHardwareSpec {
    pub memory_capacity_bytes: u64,
    pub memory_bandwidth_bytes_per_second: f64,
    pub compute_operations_per_second: f64,
    pub compute_efficiency: f64,
    pub memory_efficiency: f64,
    pub scale_up_bandwidth_bytes_per_second: f64,
    pub scale_up_latency_nanoseconds: f64,
    pub scale_up_energy_picojoules_per_byte: f64,
    pub idle_power_watts: f64,
    pub peak_power_watts: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HardwareDesignSpec {
    pub process: ProcessSpec,
    pub die: DieSpec,
    pub package: PackageSpec,
    pub compute: ComputeSpec,
    pub on_chip_memory: Vec<OnChipMemoryTierSpec>,
    pub off_chip_memory: Vec<OffChipMemoryTierSpec>,
    pub network: OnDieNetworkSpec,
    pub interconnect: InterconnectSpec,
    pub power_thermal: PowerThermalSpec,
    pub manufacturing: ManufacturingSpec,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProcessSpec {
    pub node_nanometers: f64,
    pub transistor_density_million_per_square_millimeter: f64,
    pub wafer_diameter_millimeters: f64,
    pub wafer_cost_usd: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DieSpec {
    pub die_count: u32,
    pub area_square_millimeters: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PackageSpec {
    pub package_type: String,
    pub interposer_area_square_millimeters: f64,
    pub package_cost_usd: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ComputeSpec {
    pub array_count: u32,
    pub array: ComputeArraySpec,
    pub frequency_hz: f64,
    pub arithmetic: Vec<ArithmeticSpec>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ComputeArraySpec {
    pub rows: u32,
    pub columns: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ArithmeticSpec {
    pub precision: Precision,
    pub operations_per_cycle_per_element: f64,
    pub energy_picojoules_per_operation: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OnChipMemoryTierSpec {
    pub name: String,
    pub kind: OnChipMemoryKind,
    pub capacity_bytes: u64,
    pub bandwidth_bytes_per_second: f64,
    pub energy_picojoules_per_byte: f64,
    pub area_square_millimeters: f64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum OnChipMemoryKind {
    RegisterFile,
    Sram,
    Cache,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OffChipMemoryTierSpec {
    pub name: String,
    pub kind: OffChipMemoryKind,
    pub capacity_bytes: u64,
    pub bandwidth_bytes_per_second: f64,
    pub energy_picojoules_per_byte: f64,
    pub area_square_millimeters: f64,
    pub controller_latency_nanoseconds: f64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum OffChipMemoryKind {
    Hbm,
    Dram,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OnDieNetworkSpec {
    pub topology: NetworkTopology,
    pub bisection_bandwidth_bytes_per_second: f64,
    pub hop_latency_nanoseconds: f64,
    pub energy_picojoules_per_byte_per_hop: f64,
    pub area_square_millimeters: f64,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum NetworkTopology {
    Mesh,
    Ring,
    Crossbar,
    Tree,
    Custom,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InterconnectSpec {
    pub scale_up: Vec<LinkSpec>,
    pub scale_out: Vec<LinkSpec>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct LinkSpec {
    pub name: String,
    pub link_count: u32,
    pub bandwidth_bytes_per_second_per_link: f64,
    pub latency_nanoseconds: f64,
    pub energy_picojoules_per_byte: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PowerThermalSpec {
    pub idle_power_watts: f64,
    pub thermal_design_power_watts: f64,
    pub cooling_capacity_watts: f64,
    pub maximum_junction_temperature_celsius: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ManufacturingSpec {
    pub defect_density_per_square_centimeter: f64,
    pub die_yield: f64,
    pub package_yield: f64,
    pub assembly_cost_usd: f64,
    pub test_cost_usd: f64,
    pub non_recurring_engineering_cost_usd: f64,
    pub amortization_units: u64,
}

impl HardwareSpec {
    pub fn effective_compute_operations_per_second(&self) -> Option<f64> {
        if let Some(aggregate) = &self.aggregate {
            return Some(aggregate.compute_operations_per_second * aggregate.compute_efficiency);
        }
        let compute = &self.design.as_ref()?.compute;
        let fastest_arithmetic = compute
            .arithmetic
            .iter()
            .map(|arithmetic| arithmetic.operations_per_cycle_per_element)
            .reduce(f64::max)?;
        Some(
            f64::from(compute.array_count)
                * f64::from(compute.array.rows)
                * f64::from(compute.array.columns)
                * compute.frequency_hz
                * fastest_arithmetic,
        )
    }

    pub fn effective_compute_flops_per_second(&self) -> Option<f64> {
        self.effective_compute_operations_per_second()
    }

    pub fn effective_memory_capacity_bytes(&self) -> Option<u64> {
        if let Some(aggregate) = &self.aggregate {
            return Some(aggregate.memory_capacity_bytes);
        }
        let design = self.design.as_ref()?;
        design
            .on_chip_memory
            .iter()
            .map(|tier| tier.capacity_bytes)
            .chain(
                design
                    .off_chip_memory
                    .iter()
                    .map(|tier| tier.capacity_bytes),
            )
            .try_fold(0_u64, u64::checked_add)
    }

    pub fn effective_memory_bandwidth_bytes_per_second(&self) -> Option<f64> {
        if let Some(aggregate) = &self.aggregate {
            return Some(aggregate.memory_bandwidth_bytes_per_second * aggregate.memory_efficiency);
        }
        let design = self.design.as_ref()?;
        Some(
            design
                .on_chip_memory
                .iter()
                .map(|tier| tier.bandwidth_bytes_per_second)
                .chain(
                    design
                        .off_chip_memory
                        .iter()
                        .map(|tier| tier.bandwidth_bytes_per_second),
                )
                .sum(),
        )
    }

    pub fn effective_idle_power_watts(&self) -> Option<f64> {
        self.aggregate
            .as_ref()
            .map(|aggregate| aggregate.idle_power_watts)
            .or_else(|| {
                self.design
                    .as_ref()
                    .map(|design| design.power_thermal.idle_power_watts)
            })
    }

    pub fn effective_peak_power_watts(&self) -> Option<f64> {
        self.aggregate
            .as_ref()
            .map(|aggregate| aggregate.peak_power_watts)
            .or_else(|| {
                self.design
                    .as_ref()
                    .map(|design| design.power_thermal.thermal_design_power_watts)
            })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct KernelSpec {
    pub backend: KernelBackend,
    pub attention: AttentionKernel,
    pub fusion: FusionPolicy,
    pub tile_rows: u32,
    pub tile_columns: u32,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum KernelBackend {
    Rust,
    Cuda,
    Triton,
    Analytical,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum AttentionKernel {
    Standard,
    Flash,
    Paged,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(rename_all = "snake_case")]
pub enum FusionPolicy {
    None,
    Attention,
    Mlp,
    AttentionAndMlp,
    FullLayer,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ExecutionMappingSpec {
    pub tensor_parallelism: u32,
    pub pipeline_parallelism: u32,
    pub data_parallelism: u32,
    pub prefill_decode_disaggregated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ServingSpec {
    pub max_batch_size: u32,
    pub prefill_chunk_tokens: u32,
    pub prefill_interleave_decode_steps: u32,
    pub kv_cache_memory_fraction: f64,
    pub max_concurrent_requests: u32,
    pub ttft_slo_milliseconds: f64,
    pub tpot_slo_milliseconds: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct EconomicsSpec {
    pub electricity_usd_per_kwh: f64,
    pub power_usage_effectiveness: f64,
    pub target_gross_margin: f64,
    pub provider_overhead_usd_per_hour: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityConstraint {
    pub metric: String,
    pub baseline_score: f64,
    pub minimum_score: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SearchSpace {
    pub weight_precisions: Vec<Precision>,
    #[serde(default)]
    pub quantized_weight_storage: Option<QuantizedWeightStorageSpec>,
    pub kv_precisions: Vec<Precision>,
    pub max_batch_sizes: Vec<u32>,
    pub prefill_chunk_tokens: Vec<u32>,
    pub kernel: Option<KernelSearchSpace>,
    pub hardware: Option<HardwareSearchSpace>,
    pub mapping: Option<MappingSearchSpace>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct KernelSearchSpace {
    pub attention_kernels: Vec<AttentionKernel>,
    pub fusion_policies: Vec<FusionPolicy>,
    pub tile_rows: Vec<u32>,
    pub tile_columns: Vec<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HardwareSearchSpace {
    pub compute_array_counts: Vec<u32>,
    pub on_chip_memory_capacities_bytes: Vec<u64>,
    pub off_chip_memory_bandwidth_bytes_per_second: Vec<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MappingSearchSpace {
    pub tensor_parallelism: Vec<u32>,
    pub pipeline_parallelism: Vec<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ValidationError {
    pub field: String,
    pub problem: ValidationProblem,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ValidationProblem {
    Required,
    MustBePositive,
    MustBeNonNegative,
    MustBeFinite,
    RatioOutOfRange,
    BelowMinimum { minimum: f64 },
    MustSumToOne { actual: f64 },
    Inconsistent { reason: String },
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ValidationErrors {
    pub errors: Vec<ValidationError>,
}

impl ValidationErrors {
    pub fn iter(&self) -> impl Iterator<Item = &ValidationError> {
        self.errors.iter()
    }

    pub fn has_field(&self, field: &str) -> bool {
        self.errors.iter().any(|error| error.field == field)
    }
}

impl fmt::Display for ValidationErrors {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{} validation error(s)", self.errors.len())
    }
}

impl std::error::Error for ValidationErrors {}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
#[serde(transparent)]
pub struct ContentId([u8; 32]);

impl ContentId {
    pub const fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }

    pub fn to_hex(self) -> String {
        blake3::Hash::from_bytes(self.0).to_hex().to_string()
    }
}

impl fmt::Display for ContentId {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&blake3::Hash::from_bytes(self.0).to_hex())
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ContentIdentityError {
    #[error("invalid experiment specification: {0}")]
    Validation(#[from] ValidationErrors),
    #[error("failed to serialize experiment specification: {0}")]
    Serialization(#[from] serde_json::Error),
}

impl ExperimentSpec {
    pub fn validate(&self) -> Result<(), ValidationErrors> {
        let mut validator = Validator::default();
        self.validate_into(&mut validator);
        validator.finish()
    }

    pub fn content_id(&self) -> Result<ContentId, ContentIdentityError> {
        self.validate()?;
        let serialized = serde_json::to_vec(self)?;
        Ok(ContentId(*blake3::hash(&serialized).as_bytes()))
    }

    fn validate_into(&self, validator: &mut Validator) {
        if self.schema_version != CURRENT_SCHEMA_VERSION {
            validator.push(
                "schema_version",
                ValidationProblem::UnsupportedSchemaVersion {
                    expected: CURRENT_SCHEMA_VERSION,
                    actual: self.schema_version,
                },
            );
        }
        validator.required("experiment_name", &self.experiment_name);
        self.model.validate_into(validator);
        validator.required("quality_suite_id", &self.quality_suite_id);
        self.workload.validate_into(validator);
        self.hardware.validate_into(validator);
        self.kernel.validate_into(validator);
        self.mapping.validate_into(validator);
        self.serving.validate_into(validator);
        self.economics.validate_into(validator);
        if self.quality_constraints.is_empty() {
            validator.push("quality_constraints", ValidationProblem::Required);
        }
        for (index, constraint) in self.quality_constraints.iter().enumerate() {
            constraint.validate_into(validator, index);
        }
        self.search_space.validate_into(validator);
        for (index, class) in self.workload.request_classes.iter().enumerate() {
            if class.input_tokens.saturating_add(class.output_tokens)
                > self.model.max_sequence_length
            {
                validator.push(
                    format!("workload.request_classes[{index}]"),
                    ValidationProblem::Inconsistent {
                        reason: "input and output tokens exceed model context".into(),
                    },
                );
            }
        }
    }
}

impl ModelSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.required("model.model_id", &self.model_id);
        validator.required("model.model_revision", &self.model_revision);
        validator.positive_u64("model.parameter_count", self.parameter_count);
        validator.positive_u32("model.layer_count", self.layer_count);
        validator.positive_u32("model.hidden_size", self.hidden_size);
        validator.positive_u32("model.intermediate_size", self.intermediate_size);
        validator.positive_u32("model.attention_head_count", self.attention_head_count);
        validator.positive_u32("model.head_dimension", self.head_dimension);
        validator.positive_u32("model.vocabulary_size", self.vocabulary_size);
        validator.positive_u32("model.max_sequence_length", self.max_sequence_length);
        if self.weight_precision.bits() < 8 && self.quantized_weight_storage.is_none() {
            validator.push(
                "model.quantized_weight_storage",
                ValidationProblem::Inconsistent {
                    reason: "sub-byte arithmetic requires an explicit weight storage format".into(),
                },
            );
        }
        let default_weight_parameters = match self.architecture {
            ModelArchitecture::DenseDecoder => Some(self.parameter_count),
            ModelArchitecture::HybridMoeMlaDsa(hybrid) => hybrid
                .routed_expert_parameter_count(self.hidden_size)
                .and_then(|routed| self.parameter_count.checked_sub(routed)),
        };
        if self
            .quantized_weight_storage
            .as_ref()
            .is_some_and(|storage| {
                default_weight_parameters
                    .and_then(|parameters| storage.stored_bits(parameters))
                    .is_none()
            })
        {
            validator.push(
                "model.quantized_weight_storage",
                ValidationProblem::Inconsistent {
                    reason: "quantized weight storage is invalid or exceeds numeric limits".into(),
                },
            );
        }
        match self.architecture {
            ModelArchitecture::DenseDecoder => self.validate_dense_attention(validator),
            ModelArchitecture::HybridMoeMlaDsa(hybrid) => hybrid.validate_into(self, validator),
        }
    }

    fn validate_dense_attention(&self, validator: &mut Validator) {
        validator.positive_u32("model.kv_head_count", self.kv_head_count);
        if self.kv_head_count > self.attention_head_count
            || (self.kv_head_count != 0 && self.attention_head_count % self.kv_head_count != 0)
        {
            validator.push(
                "model.kv_head_count",
                ValidationProblem::Inconsistent {
                    reason: "attention heads must be divisible by KV heads".into(),
                },
            );
        }
        if self.attention_head_count.checked_mul(self.head_dimension) != Some(self.hidden_size) {
            validator.push(
                "model.hidden_size",
                ValidationProblem::Inconsistent {
                    reason: "hidden size must equal attention heads times head dimension".into(),
                },
            );
        }
    }
}

impl HybridMoeMlaDsaSpec {
    fn validate_into(&self, model: &ModelSpec, validator: &mut Validator) {
        if self.schema_version != HYBRID_MOE_MLA_DSA_SCHEMA_VERSION {
            validator.push(
                "model.architecture.schema_version",
                ValidationProblem::UnsupportedSchemaVersion {
                    expected: HYBRID_MOE_MLA_DSA_SCHEMA_VERSION,
                    actual: self.schema_version,
                },
            );
        }
        validator.positive_u32(
            "model.architecture.dense_layer_count",
            self.dense_layer_count,
        );
        validator.positive_u32("model.architecture.moe_layer_count", self.moe_layer_count);
        if self.dense_layer_count.checked_add(self.moe_layer_count) != Some(model.layer_count) {
            validator.push(
                "model.architecture.layer_counts",
                ValidationProblem::Inconsistent {
                    reason: "dense and MoE layers must sum to model layers".into(),
                },
            );
        }
        let active_parameters = self.active_parameter_count.parameters();
        if active_parameters == 0 || active_parameters > model.parameter_count {
            validator.push(
                "model.architecture.active_parameter_count",
                ValidationProblem::Inconsistent {
                    reason:
                        "active parameters must be positive and no greater than resident parameters"
                            .into(),
                },
            );
        }
        self.moe.validate_into(model, self, validator);
        self.mla.validate_into(model, validator);
        self.dsa_indexer.validate_into(model, validator);
        self.mtp.validate_into(validator);
        if model.kv_head_count != 0 {
            validator.push(
                "model.kv_head_count",
                ValidationProblem::Inconsistent {
                    reason: "MLA models must not declare GQA KV heads".into(),
                },
            );
        }
        let known_stored = self
            .stored_feed_forward_parameter_count(model.hidden_size, model.intermediate_size)
            .and_then(|parameters| {
                parameters.checked_add(self.dsa_indexer_parameter_count(model.hidden_size)?)
            });
        if known_stored.is_none_or(|parameters| parameters > model.parameter_count) {
            validator.push(
                "model.parameter_count",
                ValidationProblem::Inconsistent {
                    reason: "resident parameters are smaller than the exact architecture ledger"
                        .into(),
                },
            );
        }
        if self
            .active_feed_forward_parameter_count_per_token(
                model.hidden_size,
                model.intermediate_size,
            )
            .is_none_or(|parameters| parameters > active_parameters)
        {
            validator.push(
                "model.architecture.active_parameter_count",
                ValidationProblem::Inconsistent {
                    reason: "active parameters are smaller than active feed-forward parameters"
                        .into(),
                },
            );
        }
    }
}

impl MoeSpec {
    fn validate_into(
        &self,
        model: &ModelSpec,
        hybrid: &HybridMoeMlaDsaSpec,
        validator: &mut Validator,
    ) {
        validator.positive_u32(
            "model.architecture.moe.routed_expert_count",
            self.routed_expert_count,
        );
        validator.positive_u32(
            "model.architecture.moe.routed_experts_per_token",
            self.routed_experts_per_token,
        );
        validator.positive_u32(
            "model.architecture.moe.shared_expert_count",
            self.shared_expert_count,
        );
        validator.positive_u32(
            "model.architecture.moe.expert_intermediate_size",
            self.expert_intermediate_size,
        );
        if self.routed_experts_per_token > self.routed_expert_count {
            validator.push(
                "model.architecture.moe.routed_experts_per_token",
                ValidationProblem::Inconsistent {
                    reason: "selected routed experts cannot exceed resident routed experts".into(),
                },
            );
        }
        if self.routed_expert_weight_precision.bits() < 8
            && self.routed_expert_quantized_weight_storage.is_none()
        {
            validator.push(
                "model.architecture.moe.routed_expert_quantized_weight_storage",
                ValidationProblem::Inconsistent {
                    reason: "sub-byte expert arithmetic requires explicit expert storage".into(),
                },
            );
        }
        let routed_parameters = hybrid.routed_expert_parameter_count(model.hidden_size);
        if self
            .routed_expert_quantized_weight_storage
            .as_ref()
            .is_some_and(|storage| {
                routed_parameters
                    .and_then(|parameters| storage.stored_bits(parameters))
                    .is_none()
            })
        {
            validator.push(
                "model.architecture.moe.routed_expert_quantized_weight_storage",
                ValidationProblem::Inconsistent {
                    reason: "expert storage is invalid or exceeds numeric limits".into(),
                },
            );
        }
    }
}

impl MlaSpec {
    fn validate_into(&self, model: &ModelSpec, validator: &mut Validator) {
        for (field, value) in [
            (
                "model.architecture.mla.query_low_rank_dimension",
                self.query_low_rank_dimension,
            ),
            (
                "model.architecture.mla.semantic_kv_dimension",
                self.semantic_kv_dimension,
            ),
            (
                "model.architecture.mla.query_key_nope_dimension",
                self.query_key_nope_dimension,
            ),
            (
                "model.architecture.mla.rotary_kv_dimension",
                self.rotary_kv_dimension,
            ),
            (
                "model.architecture.mla.value_dimension",
                self.value_dimension,
            ),
        ] {
            validator.positive_u32(field, value);
        }
        validator.positive_u64("model.architecture.mla.rope_theta", self.rope_theta);
        if self
            .query_key_nope_dimension
            .checked_add(self.rotary_kv_dimension)
            != Some(model.head_dimension)
        {
            validator.push(
                "model.head_dimension",
                ValidationProblem::Inconsistent {
                    reason: "MLA head dimension must equal NoPE plus rotary dimensions".into(),
                },
            );
        }
    }
}

impl DsaIndexerSpec {
    fn validate_into(&self, model: &ModelSpec, validator: &mut Validator) {
        for (field, value) in [
            (
                "model.architecture.dsa_indexer.query_head_count",
                self.query_head_count,
            ),
            (
                "model.architecture.dsa_indexer.query_head_dimension",
                self.query_head_dimension,
            ),
            (
                "model.architecture.dsa_indexer.key_head_count",
                self.key_head_count,
            ),
            (
                "model.architecture.dsa_indexer.key_head_dimension",
                self.key_head_dimension,
            ),
            (
                "model.architecture.dsa_indexer.selected_token_count",
                self.selected_token_count,
            ),
            (
                "model.architecture.dsa_indexer.full_layer_count",
                self.full_layer_count,
            ),
            (
                "model.architecture.dsa_indexer.shared_layer_count",
                self.shared_layer_count,
            ),
        ] {
            validator.positive_u32(field, value);
        }
        if self.full_layer_count.checked_add(self.shared_layer_count) != Some(model.layer_count) {
            validator.push(
                "model.architecture.dsa_indexer.layer_counts",
                ValidationProblem::Inconsistent {
                    reason: "full and shared indexer layers must sum to model layers".into(),
                },
            );
        }
        if self.query_head_count > model.attention_head_count
            || (self.query_head_count != 0
                && model.attention_head_count % self.query_head_count != 0)
        {
            validator.push(
                "model.architecture.dsa_indexer.query_head_count",
                ValidationProblem::Inconsistent {
                    reason: "attention heads must be divisible by indexer query heads".into(),
                },
            );
        }
        if self.selected_token_count > model.max_sequence_length {
            validator.push(
                "model.architecture.dsa_indexer.selected_token_count",
                ValidationProblem::Inconsistent {
                    reason: "selected tokens cannot exceed maximum sequence length".into(),
                },
            );
        }
    }
}

impl MtpSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32("model.architecture.mtp.layer_count", self.layer_count);
    }
}

impl AgenticWorkloadSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u64("workload.request_count", self.request_count);
        validator.positive_f64(
            "workload.arrival_rate_per_second",
            self.arrival_rate_per_second,
        );
        if self.request_classes.is_empty() {
            validator.push("workload.request_classes", ValidationProblem::Required);
        }
        for (index, class) in self.request_classes.iter().enumerate() {
            let base = format!("workload.request_classes[{index}]");
            validator.required(format!("{base}.name"), &class.name);
            validator.ratio_open_closed(format!("{base}.share"), class.share);
            validator.positive_u32(format!("{base}.input_tokens"), class.input_tokens);
            validator.positive_u32(format!("{base}.output_tokens"), class.output_tokens);
            validator.ratio_closed(
                format!("{base}.prefix_cache_hit_ratio"),
                class.prefix_cache_hit_ratio,
            );
        }
        let share: f64 = self.request_classes.iter().map(|class| class.share).sum();
        if share.is_finite() && (share - 1.0).abs() > 1e-9 {
            validator.push(
                "workload.request_classes.share",
                ValidationProblem::MustSumToOne { actual: share },
            );
        }
    }
}

impl HardwareSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.required("hardware.name", &self.name);
        validator.positive_u32("hardware.physical_device_count", self.physical_device_count);
        validator.positive_f64(
            "hardware.accelerator_hourly_cost_usd",
            self.accelerator_hourly_cost_usd,
        );
        validator.non_negative_f64("hardware.host_hourly_cost_usd", self.host_hourly_cost_usd);
        if self.aggregate.is_none() && self.design.is_none() {
            validator.push(
                "hardware",
                ValidationProblem::Inconsistent {
                    reason: "an aggregate or detailed design is required".into(),
                },
            );
        }
        if matches!(
            self.fidelity,
            HardwareFidelity::Architecture | HardwareFidelity::Rtl
        ) && self.design.is_none()
        {
            validator.push("hardware.design", ValidationProblem::Required);
        }
        if matches!(
            self.fidelity,
            HardwareFidelity::Analytical | HardwareFidelity::Measured
        ) && self.aggregate.is_none()
        {
            validator.push("hardware.aggregate", ValidationProblem::Required);
        }
        if let Some(aggregate) = &self.aggregate {
            aggregate.validate_into(validator);
        }
        if let Some(design) = &self.design {
            design.validate_into(validator);
        }
    }
}

impl AggregateHardwareSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u64(
            "hardware.aggregate.memory_capacity_bytes",
            self.memory_capacity_bytes,
        );
        validator.positive_f64(
            "hardware.aggregate.memory_bandwidth_bytes_per_second",
            self.memory_bandwidth_bytes_per_second,
        );
        validator.positive_f64(
            "hardware.aggregate.compute_operations_per_second",
            self.compute_operations_per_second,
        );
        validator.ratio_open_closed(
            "hardware.aggregate.compute_efficiency",
            self.compute_efficiency,
        );
        validator.ratio_open_closed(
            "hardware.aggregate.memory_efficiency",
            self.memory_efficiency,
        );
        validator.non_negative_f64(
            "hardware.aggregate.scale_up_bandwidth_bytes_per_second",
            self.scale_up_bandwidth_bytes_per_second,
        );
        validator.non_negative_f64(
            "hardware.aggregate.scale_up_latency_nanoseconds",
            self.scale_up_latency_nanoseconds,
        );
        validator.non_negative_f64(
            "hardware.aggregate.scale_up_energy_picojoules_per_byte",
            self.scale_up_energy_picojoules_per_byte,
        );
        validator.non_negative_f64("hardware.aggregate.idle_power_watts", self.idle_power_watts);
        validator.positive_f64("hardware.aggregate.peak_power_watts", self.peak_power_watts);
        if self.idle_power_watts > self.peak_power_watts {
            validator.push(
                "hardware.aggregate.idle_power_watts",
                ValidationProblem::Inconsistent {
                    reason: "idle power cannot exceed peak power".into(),
                },
            );
        }
    }
}

impl HardwareDesignSpec {
    fn validate_into(&self, validator: &mut Validator) {
        self.process.validate_into(validator);
        self.die.validate_into(validator);
        self.package.validate_into(validator);
        self.compute.validate_into(validator);
        if self.on_chip_memory.is_empty() {
            validator.push(
                "hardware.design.on_chip_memory",
                ValidationProblem::Required,
            );
        }
        for (index, tier) in self.on_chip_memory.iter().enumerate() {
            tier.validate_into(validator, index);
        }
        if self.off_chip_memory.is_empty() {
            validator.push(
                "hardware.design.off_chip_memory",
                ValidationProblem::Required,
            );
        }
        for (index, tier) in self.off_chip_memory.iter().enumerate() {
            tier.validate_into(validator, index);
        }
        self.network.validate_into(validator);
        self.interconnect.validate_into(validator);
        self.power_thermal.validate_into(validator);
        self.manufacturing.validate_into(validator);
    }
}

impl ProcessSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_f64(
            "hardware.design.process.node_nanometers",
            self.node_nanometers,
        );
        validator.positive_f64(
            "hardware.design.process.transistor_density_million_per_square_millimeter",
            self.transistor_density_million_per_square_millimeter,
        );
        validator.positive_f64(
            "hardware.design.process.wafer_diameter_millimeters",
            self.wafer_diameter_millimeters,
        );
        validator.positive_f64(
            "hardware.design.process.wafer_cost_usd",
            self.wafer_cost_usd,
        );
    }
}

impl DieSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32("hardware.design.die.die_count", self.die_count);
        validator.positive_f64(
            "hardware.design.die.area_square_millimeters",
            self.area_square_millimeters,
        );
    }
}

impl PackageSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.required("hardware.design.package.package_type", &self.package_type);
        validator.positive_f64(
            "hardware.design.package.interposer_area_square_millimeters",
            self.interposer_area_square_millimeters,
        );
        validator.non_negative_f64(
            "hardware.design.package.package_cost_usd",
            self.package_cost_usd,
        );
    }
}

impl ComputeSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32("hardware.design.compute.array_count", self.array_count);
        validator.positive_u32("hardware.design.compute.array.rows", self.array.rows);
        validator.positive_u32("hardware.design.compute.array.columns", self.array.columns);
        validator.positive_f64("hardware.design.compute.frequency_hz", self.frequency_hz);
        if self.arithmetic.is_empty() {
            validator.push(
                "hardware.design.compute.arithmetic",
                ValidationProblem::Required,
            );
        }
        for (index, arithmetic) in self.arithmetic.iter().enumerate() {
            validator.positive_f64(
                format!(
                    "hardware.design.compute.arithmetic[{index}].operations_per_cycle_per_element"
                ),
                arithmetic.operations_per_cycle_per_element,
            );
            validator.positive_f64(
                format!(
                    "hardware.design.compute.arithmetic[{index}].energy_picojoules_per_operation"
                ),
                arithmetic.energy_picojoules_per_operation,
            );
        }
    }
}

impl OnChipMemoryTierSpec {
    fn validate_into(&self, validator: &mut Validator, index: usize) {
        let base = format!("hardware.design.on_chip_memory[{index}]");
        validator.required(format!("{base}.name"), &self.name);
        validator.positive_u64(format!("{base}.capacity_bytes"), self.capacity_bytes);
        validator.positive_f64(
            format!("{base}.bandwidth_bytes_per_second"),
            self.bandwidth_bytes_per_second,
        );
        validator.positive_f64(
            format!("{base}.energy_picojoules_per_byte"),
            self.energy_picojoules_per_byte,
        );
        validator.positive_f64(
            format!("{base}.area_square_millimeters"),
            self.area_square_millimeters,
        );
    }
}

impl OffChipMemoryTierSpec {
    fn validate_into(&self, validator: &mut Validator, index: usize) {
        let base = format!("hardware.design.off_chip_memory[{index}]");
        validator.required(format!("{base}.name"), &self.name);
        validator.positive_u64(format!("{base}.capacity_bytes"), self.capacity_bytes);
        validator.positive_f64(
            format!("{base}.bandwidth_bytes_per_second"),
            self.bandwidth_bytes_per_second,
        );
        validator.positive_f64(
            format!("{base}.energy_picojoules_per_byte"),
            self.energy_picojoules_per_byte,
        );
        validator.positive_f64(
            format!("{base}.area_square_millimeters"),
            self.area_square_millimeters,
        );
        validator.positive_f64(
            format!("{base}.controller_latency_nanoseconds"),
            self.controller_latency_nanoseconds,
        );
    }
}

impl OnDieNetworkSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_f64(
            "hardware.design.network.bisection_bandwidth_bytes_per_second",
            self.bisection_bandwidth_bytes_per_second,
        );
        validator.positive_f64(
            "hardware.design.network.hop_latency_nanoseconds",
            self.hop_latency_nanoseconds,
        );
        validator.positive_f64(
            "hardware.design.network.energy_picojoules_per_byte_per_hop",
            self.energy_picojoules_per_byte_per_hop,
        );
        validator.positive_f64(
            "hardware.design.network.area_square_millimeters",
            self.area_square_millimeters,
        );
    }
}

impl InterconnectSpec {
    fn validate_into(&self, validator: &mut Validator) {
        for (scope, links) in [("scale_up", &self.scale_up), ("scale_out", &self.scale_out)] {
            for (index, link) in links.iter().enumerate() {
                link.validate_into(validator, scope, index);
            }
        }
    }
}

impl LinkSpec {
    fn validate_into(&self, validator: &mut Validator, scope: &str, index: usize) {
        let base = format!("hardware.design.interconnect.{scope}[{index}]");
        validator.required(format!("{base}.name"), &self.name);
        validator.positive_u32(format!("{base}.link_count"), self.link_count);
        validator.positive_f64(
            format!("{base}.bandwidth_bytes_per_second_per_link"),
            self.bandwidth_bytes_per_second_per_link,
        );
        validator.positive_f64(
            format!("{base}.latency_nanoseconds"),
            self.latency_nanoseconds,
        );
        validator.positive_f64(
            format!("{base}.energy_picojoules_per_byte"),
            self.energy_picojoules_per_byte,
        );
    }
}

impl PowerThermalSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.non_negative_f64(
            "hardware.design.power_thermal.idle_power_watts",
            self.idle_power_watts,
        );
        validator.positive_f64(
            "hardware.design.power_thermal.thermal_design_power_watts",
            self.thermal_design_power_watts,
        );
        validator.positive_f64(
            "hardware.design.power_thermal.cooling_capacity_watts",
            self.cooling_capacity_watts,
        );
        validator.positive_f64(
            "hardware.design.power_thermal.maximum_junction_temperature_celsius",
            self.maximum_junction_temperature_celsius,
        );
        if self.idle_power_watts > self.thermal_design_power_watts {
            validator.push(
                "hardware.design.power_thermal.idle_power_watts",
                ValidationProblem::Inconsistent {
                    reason: "idle power cannot exceed thermal design power".into(),
                },
            );
        }
        if self.cooling_capacity_watts < self.thermal_design_power_watts {
            validator.push(
                "hardware.design.power_thermal.cooling_capacity_watts",
                ValidationProblem::Inconsistent {
                    reason: "cooling capacity must cover thermal design power".into(),
                },
            );
        }
    }
}

impl ManufacturingSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.non_negative_f64(
            "hardware.design.manufacturing.defect_density_per_square_centimeter",
            self.defect_density_per_square_centimeter,
        );
        validator.ratio_open_closed("hardware.design.manufacturing.die_yield", self.die_yield);
        validator.ratio_open_closed(
            "hardware.design.manufacturing.package_yield",
            self.package_yield,
        );
        validator.non_negative_f64(
            "hardware.design.manufacturing.assembly_cost_usd",
            self.assembly_cost_usd,
        );
        validator.non_negative_f64(
            "hardware.design.manufacturing.test_cost_usd",
            self.test_cost_usd,
        );
        validator.non_negative_f64(
            "hardware.design.manufacturing.non_recurring_engineering_cost_usd",
            self.non_recurring_engineering_cost_usd,
        );
        validator.positive_u64(
            "hardware.design.manufacturing.amortization_units",
            self.amortization_units,
        );
    }
}

impl KernelSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32("kernel.tile_rows", self.tile_rows);
        validator.positive_u32("kernel.tile_columns", self.tile_columns);
    }
}

impl ExecutionMappingSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32("mapping.tensor_parallelism", self.tensor_parallelism);
        validator.positive_u32("mapping.pipeline_parallelism", self.pipeline_parallelism);
        validator.positive_u32("mapping.data_parallelism", self.data_parallelism);
    }
}

impl ServingSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32("serving.max_batch_size", self.max_batch_size);
        validator.positive_u32("serving.prefill_chunk_tokens", self.prefill_chunk_tokens);
        validator.positive_u32(
            "serving.prefill_interleave_decode_steps",
            self.prefill_interleave_decode_steps,
        );
        validator.ratio_open_closed(
            "serving.kv_cache_memory_fraction",
            self.kv_cache_memory_fraction,
        );
        validator.positive_u32(
            "serving.max_concurrent_requests",
            self.max_concurrent_requests,
        );
        validator.positive_f64("serving.ttft_slo_milliseconds", self.ttft_slo_milliseconds);
        validator.positive_f64("serving.tpot_slo_milliseconds", self.tpot_slo_milliseconds);
    }
}

impl EconomicsSpec {
    fn validate_into(&self, validator: &mut Validator) {
        validator.non_negative_f64(
            "economics.electricity_usd_per_kwh",
            self.electricity_usd_per_kwh,
        );
        validator.minimum_f64(
            "economics.power_usage_effectiveness",
            self.power_usage_effectiveness,
            1.0,
        );
        validator.ratio_half_open("economics.target_gross_margin", self.target_gross_margin);
        if let Some(overhead) = self.provider_overhead_usd_per_hour {
            validator.non_negative_f64("economics.provider_overhead_usd_per_hour", overhead);
        }
    }
}

impl QualityConstraint {
    fn validate_into(&self, validator: &mut Validator, index: usize) {
        let base = format!("quality_constraints[{index}]");
        validator.required(format!("{base}.metric"), &self.metric);
        validator.finite(format!("{base}.baseline_score"), self.baseline_score);
        validator.finite(format!("{base}.minimum_score"), self.minimum_score);
        if self.minimum_score > self.baseline_score {
            validator.push(
                format!("{base}.minimum_score"),
                ValidationProblem::Inconsistent {
                    reason: "minimum score cannot exceed baseline score".into(),
                },
            );
        }
    }
}

impl SearchSpace {
    fn validate_into(&self, validator: &mut Validator) {
        validator.non_empty("search_space.weight_precisions", &self.weight_precisions);
        if self
            .weight_precisions
            .iter()
            .any(|precision| precision.bits() < 8)
            && self.quantized_weight_storage.is_none()
        {
            validator.push(
                "search_space.quantized_weight_storage",
                ValidationProblem::Inconsistent {
                    reason: "sub-byte search candidates require an explicit storage format".into(),
                },
            );
        }
        validator.non_empty("search_space.kv_precisions", &self.kv_precisions);
        validator.positive_u32_candidates("search_space.max_batch_sizes", &self.max_batch_sizes);
        validator.positive_u32_candidates(
            "search_space.prefill_chunk_tokens",
            &self.prefill_chunk_tokens,
        );
        if let Some(kernel) = &self.kernel {
            kernel.validate_into(validator);
        }
        if let Some(hardware) = &self.hardware {
            hardware.validate_into(validator);
        }
        if let Some(mapping) = &self.mapping {
            mapping.validate_into(validator);
        }
    }
}

impl KernelSearchSpace {
    fn validate_into(&self, validator: &mut Validator) {
        validator.non_empty(
            "search_space.kernel.attention_kernels",
            &self.attention_kernels,
        );
        validator.non_empty("search_space.kernel.fusion_policies", &self.fusion_policies);
        validator.positive_u32_candidates("search_space.kernel.tile_rows", &self.tile_rows);
        validator.positive_u32_candidates("search_space.kernel.tile_columns", &self.tile_columns);
    }
}

impl HardwareSearchSpace {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32_candidates(
            "search_space.hardware.compute_array_counts",
            &self.compute_array_counts,
        );
        validator.positive_u64_candidates(
            "search_space.hardware.on_chip_memory_capacities_bytes",
            &self.on_chip_memory_capacities_bytes,
        );
        validator.positive_f64_candidates(
            "search_space.hardware.off_chip_memory_bandwidth_bytes_per_second",
            &self.off_chip_memory_bandwidth_bytes_per_second,
        );
    }
}

impl MappingSearchSpace {
    fn validate_into(&self, validator: &mut Validator) {
        validator.positive_u32_candidates(
            "search_space.mapping.tensor_parallelism",
            &self.tensor_parallelism,
        );
        validator.positive_u32_candidates(
            "search_space.mapping.pipeline_parallelism",
            &self.pipeline_parallelism,
        );
    }
}

#[derive(Default)]
struct Validator {
    errors: Vec<ValidationError>,
}

impl Validator {
    fn finish(self) -> Result<(), ValidationErrors> {
        if self.errors.is_empty() {
            Ok(())
        } else {
            Err(ValidationErrors {
                errors: self.errors,
            })
        }
    }

    fn push(&mut self, field: impl Into<String>, problem: ValidationProblem) {
        self.errors.push(ValidationError {
            field: field.into(),
            problem,
        });
    }

    fn required(&mut self, field: impl Into<String>, value: &str) {
        if value.trim().is_empty() {
            self.push(field, ValidationProblem::Required);
        }
    }

    fn positive_u32(&mut self, field: impl Into<String>, value: u32) {
        if value == 0 {
            self.push(field, ValidationProblem::MustBePositive);
        }
    }

    fn positive_u64(&mut self, field: impl Into<String>, value: u64) {
        if value == 0 {
            self.push(field, ValidationProblem::MustBePositive);
        }
    }

    fn finite(&mut self, field: impl Into<String>, value: f64) -> bool {
        if value.is_finite() {
            true
        } else {
            self.push(field, ValidationProblem::MustBeFinite);
            false
        }
    }

    fn positive_f64(&mut self, field: impl Into<String>, value: f64) {
        let field = field.into();
        if self.finite(field.clone(), value) && value <= 0.0 {
            self.push(field, ValidationProblem::MustBePositive);
        }
    }

    fn non_negative_f64(&mut self, field: impl Into<String>, value: f64) {
        let field = field.into();
        if self.finite(field.clone(), value) && value < 0.0 {
            self.push(field, ValidationProblem::MustBeNonNegative);
        }
    }

    fn minimum_f64(&mut self, field: impl Into<String>, value: f64, minimum: f64) {
        let field = field.into();
        if self.finite(field.clone(), value) && value < minimum {
            self.push(field, ValidationProblem::BelowMinimum { minimum });
        }
    }

    fn ratio_closed(&mut self, field: impl Into<String>, value: f64) {
        let field = field.into();
        if self.finite(field.clone(), value) && !(0.0..=1.0).contains(&value) {
            self.push(field, ValidationProblem::RatioOutOfRange);
        }
    }

    fn ratio_open_closed(&mut self, field: impl Into<String>, value: f64) {
        let field = field.into();
        if self.finite(field.clone(), value) && (value <= 0.0 || value > 1.0) {
            self.push(field, ValidationProblem::RatioOutOfRange);
        }
    }

    fn ratio_half_open(&mut self, field: impl Into<String>, value: f64) {
        let field = field.into();
        if self.finite(field.clone(), value) && !(0.0..1.0).contains(&value) {
            self.push(field, ValidationProblem::RatioOutOfRange);
        }
    }

    fn non_empty<T>(&mut self, field: impl Into<String>, values: &[T]) {
        if values.is_empty() {
            self.push(field, ValidationProblem::Required);
        }
    }

    fn positive_u32_candidates(&mut self, field: &str, values: &[u32]) {
        self.non_empty(field, values);
        for (index, value) in values.iter().enumerate() {
            self.positive_u32(format!("{field}[{index}]"), *value);
        }
    }

    fn positive_u64_candidates(&mut self, field: &str, values: &[u64]) {
        self.non_empty(field, values);
        for (index, value) in values.iter().enumerate() {
            self.positive_u64(format!("{field}[{index}]"), *value);
        }
    }

    fn positive_f64_candidates(&mut self, field: &str, values: &[f64]) {
        self.non_empty(field, values);
        for (index, value) in values.iter().enumerate() {
            self.positive_f64(format!("{field}[{index}]"), *value);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_ratios_and_zero_values_are_rejected() {
        let mut spec = valid_spec();
        spec.workload.arrival_rate_per_second = 0.0;
        spec.workload.request_classes[0].prefix_cache_hit_ratio = 1.1;
        spec.serving.kv_cache_memory_fraction = 0.0;

        let errors = spec.validate().unwrap_err();

        assert!(errors.has_field("workload.arrival_rate_per_second"));
        assert!(errors.has_field("workload.request_classes[0].prefix_cache_hit_ratio"));
        assert!(errors.has_field("serving.kv_cache_memory_fraction"));
    }

    #[test]
    fn request_class_shares_must_sum_to_one() {
        let mut spec = valid_spec();
        spec.workload.request_classes[0].share = 0.7;

        let errors = spec.validate().unwrap_err();

        assert!(errors.has_field("workload.request_classes.share"));
    }

    #[test]
    fn quality_identity_requires_a_pinned_model_revision_and_suite() {
        let mut spec = valid_spec();
        spec.model.model_revision.clear();
        spec.quality_suite_id.clear();

        let errors = spec.validate().unwrap_err();

        assert!(errors.has_field("model.model_revision"));
        assert!(errors.has_field("quality_suite_id"));
    }

    #[test]
    fn identical_specs_have_identical_content_identity() {
        let spec = valid_spec();
        let deserialized: ExperimentSpec =
            serde_json::from_slice(&serde_json::to_vec(&spec).unwrap()).unwrap();

        assert_eq!(
            spec.content_id().unwrap(),
            deserialized.content_id().unwrap()
        );

        let mut different = spec.clone();
        different.workload.seed += 1;
        assert_ne!(spec.content_id().unwrap(), different.content_id().unwrap());
    }

    #[test]
    fn detailed_hardware_derives_fidelity_zero_aggregates() {
        let hardware = detailed_hardware();

        assert_eq!(hardware.effective_memory_capacity_bytes(), Some(96_000));
        assert_eq!(
            hardware.effective_memory_bandwidth_bytes_per_second(),
            Some(3_100.0)
        );
        assert_eq!(
            hardware.effective_compute_operations_per_second(),
            Some(2.0 * 8.0 * 8.0 * 1_000_000_000.0 * 2.0)
        );
        assert_eq!(hardware.effective_idle_power_watts(), Some(60.0));
        assert_eq!(hardware.effective_peak_power_watts(), Some(350.0));
    }

    #[test]
    fn model_sizes_follow_precision_and_attention_geometry() {
        let model = valid_spec().model;

        assert_eq!(model.weight_bytes(), Some(4_228_125_000));
        assert_eq!(model.kv_bytes_per_token(), Some(147_456));
    }

    #[test]
    fn groupwise_quantized_storage_accounts_for_scales_and_fixed_metadata() {
        let mut model = valid_spec().model;
        model.parameter_count = 256;
        model.weight_precision = Precision::Int4;
        model.quantized_weight_storage = Some(QuantizedWeightStorageSpec {
            coverage: QuantizedWeightCoverage::Fraction {
                numerator: 1,
                denominator: 1,
            },
            group_size: 128,
            code_bits: 4,
            scale_bits: 16,
            unquantized_bits: 16,
            fixed_metadata_bytes: 10,
        });

        assert_eq!(
            model
                .quantized_weight_storage
                .as_ref()
                .unwrap()
                .payload_bits_per_quantized_weight(),
            Some(4.125)
        );
        assert_eq!(model.weight_storage_bits(), Some(1_136));
        assert_eq!(model.weight_bytes(), Some(142));
        assert_eq!(model.effective_weight_storage_bits(), Some(4.4375));
    }

    #[test]
    fn quantized_storage_rejects_inexact_coverage_and_byte_overflow() {
        let mut model = valid_spec().model;
        model.parameter_count = 10;
        model.weight_precision = Precision::Int4;
        model.quantized_weight_storage = Some(QuantizedWeightStorageSpec {
            coverage: QuantizedWeightCoverage::Fraction {
                numerator: 1,
                denominator: 3,
            },
            group_size: 8,
            code_bits: 4,
            scale_bits: 16,
            unquantized_bits: 16,
            fixed_metadata_bytes: 0,
        });
        assert_eq!(model.weight_bytes(), None);

        model.parameter_count = u64::MAX;
        model.quantized_weight_storage = Some(QuantizedWeightStorageSpec {
            coverage: QuantizedWeightCoverage::Count { parameters: 1 },
            group_size: 1,
            code_bits: 4,
            scale_bits: 16,
            unquantized_bits: 16,
            fixed_metadata_bytes: u64::MAX,
        });
        assert_eq!(model.weight_bytes(), None);
    }

    #[test]
    fn sub_byte_models_require_an_explicit_storage_format() {
        let mut spec = valid_spec();
        spec.model.quantized_weight_storage = None;

        let errors = spec.validate().unwrap_err();

        assert!(errors.has_field("model.quantized_weight_storage"));
    }

    fn valid_spec() -> ExperimentSpec {
        ExperimentSpec {
            schema_version: CURRENT_SCHEMA_VERSION,
            experiment_name: "qwen-agentic-cost".into(),
            model: ModelSpec {
                model_id: "Qwen/Qwen3-8B".into(),
                model_revision: "reference-fixture-v1".into(),
                architecture: ModelArchitecture::DenseDecoder,
                parameter_count: 8_200_000_000,
                layer_count: 36,
                hidden_size: 4_096,
                intermediate_size: 12_288,
                attention_head_count: 32,
                kv_head_count: 8,
                head_dimension: 128,
                vocabulary_size: 151_936,
                max_sequence_length: 32_768,
                weight_precision: Precision::Int4,
                quantized_weight_storage: Some(QuantizedWeightStorageSpec::grouped_all(
                    128, 4, 16, 16, 0,
                )),
                kv_precision: Precision::Fp16,
            },
            quality_suite_id: "agentic-v1".into(),
            workload: AgenticWorkloadSpec {
                seed: 7,
                request_count: 1_000,
                arrival_rate_per_second: 2.0,
                request_classes: vec![RequestClass {
                    name: "agent-turn".into(),
                    share: 1.0,
                    input_tokens: 8_192,
                    output_tokens: 1_024,
                    prefix_cache_hit_ratio: 0.5,
                }],
            },
            hardware: aggregate_hardware(),
            kernel: KernelSpec {
                backend: KernelBackend::Rust,
                attention: AttentionKernel::Paged,
                fusion: FusionPolicy::AttentionAndMlp,
                tile_rows: 128,
                tile_columns: 128,
            },
            mapping: ExecutionMappingSpec {
                tensor_parallelism: 1,
                pipeline_parallelism: 1,
                data_parallelism: 1,
                prefill_decode_disaggregated: false,
            },
            serving: ServingSpec {
                max_batch_size: 32,
                prefill_chunk_tokens: 512,
                prefill_interleave_decode_steps: 8,
                kv_cache_memory_fraction: 0.8,
                max_concurrent_requests: 128,
                ttft_slo_milliseconds: 1_000.0,
                tpot_slo_milliseconds: 50.0,
            },
            economics: EconomicsSpec {
                electricity_usd_per_kwh: 0.12,
                power_usage_effectiveness: 1.2,
                target_gross_margin: 0.6,
                provider_overhead_usd_per_hour: Some(0.1),
            },
            quality_constraints: vec![QualityConstraint {
                metric: "agentic-task-success".into(),
                baseline_score: 0.8,
                minimum_score: 0.79,
            }],
            search_space: SearchSpace {
                weight_precisions: vec![Precision::Int4, Precision::Int8],
                quantized_weight_storage: Some(QuantizedWeightStorageSpec::grouped_all(
                    128, 4, 16, 16, 0,
                )),
                kv_precisions: vec![Precision::Fp8, Precision::Fp16],
                max_batch_sizes: vec![16, 32],
                prefill_chunk_tokens: vec![256, 512],
                kernel: None,
                hardware: None,
                mapping: None,
            },
        }
    }

    fn aggregate_hardware() -> HardwareSpec {
        HardwareSpec {
            name: "aggregate-gpu".into(),
            fidelity: HardwareFidelity::Analytical,
            physical_device_count: 1,
            aggregate: Some(AggregateHardwareSpec {
                memory_capacity_bytes: 80_000_000_000,
                memory_bandwidth_bytes_per_second: 3_000_000_000_000.0,
                compute_operations_per_second: 1_000_000_000_000_000.0,
                compute_efficiency: 0.7,
                memory_efficiency: 0.8,
                scale_up_bandwidth_bytes_per_second: 0.0,
                scale_up_latency_nanoseconds: 0.0,
                scale_up_energy_picojoules_per_byte: 0.0,
                idle_power_watts: 70.0,
                peak_power_watts: 700.0,
            }),
            design: None,
            accelerator_hourly_cost_usd: 2.0,
            host_hourly_cost_usd: 0.25,
        }
    }

    fn detailed_hardware() -> HardwareSpec {
        HardwareSpec {
            name: "custom-asic".into(),
            fidelity: HardwareFidelity::Architecture,
            physical_device_count: 1,
            aggregate: None,
            design: Some(HardwareDesignSpec {
                process: ProcessSpec {
                    node_nanometers: 4.0,
                    transistor_density_million_per_square_millimeter: 200.0,
                    wafer_diameter_millimeters: 300.0,
                    wafer_cost_usd: 20_000.0,
                },
                die: DieSpec {
                    die_count: 1,
                    area_square_millimeters: 600.0,
                },
                package: PackageSpec {
                    package_type: "2.5D".into(),
                    interposer_area_square_millimeters: 1_200.0,
                    package_cost_usd: 500.0,
                },
                compute: ComputeSpec {
                    array_count: 2,
                    array: ComputeArraySpec {
                        rows: 8,
                        columns: 8,
                    },
                    frequency_hz: 1_000_000_000.0,
                    arithmetic: vec![ArithmeticSpec {
                        precision: Precision::Int4,
                        operations_per_cycle_per_element: 2.0,
                        energy_picojoules_per_operation: 0.2,
                    }],
                },
                on_chip_memory: vec![OnChipMemoryTierSpec {
                    name: "sram".into(),
                    kind: OnChipMemoryKind::Sram,
                    capacity_bytes: 32_000,
                    bandwidth_bytes_per_second: 100.0,
                    energy_picojoules_per_byte: 0.5,
                    area_square_millimeters: 50.0,
                }],
                off_chip_memory: vec![OffChipMemoryTierSpec {
                    name: "hbm".into(),
                    kind: OffChipMemoryKind::Hbm,
                    capacity_bytes: 64_000,
                    bandwidth_bytes_per_second: 3_000.0,
                    energy_picojoules_per_byte: 5.0,
                    area_square_millimeters: 100.0,
                    controller_latency_nanoseconds: 50.0,
                }],
                network: OnDieNetworkSpec {
                    topology: NetworkTopology::Mesh,
                    bisection_bandwidth_bytes_per_second: 1_000.0,
                    hop_latency_nanoseconds: 2.0,
                    energy_picojoules_per_byte_per_hop: 0.1,
                    area_square_millimeters: 20.0,
                },
                interconnect: InterconnectSpec {
                    scale_up: vec![LinkSpec {
                        name: "die-link".into(),
                        link_count: 2,
                        bandwidth_bytes_per_second_per_link: 50.0,
                        latency_nanoseconds: 10.0,
                        energy_picojoules_per_byte: 1.0,
                    }],
                    scale_out: vec![],
                },
                power_thermal: PowerThermalSpec {
                    idle_power_watts: 60.0,
                    thermal_design_power_watts: 350.0,
                    cooling_capacity_watts: 400.0,
                    maximum_junction_temperature_celsius: 95.0,
                },
                manufacturing: ManufacturingSpec {
                    defect_density_per_square_centimeter: 0.1,
                    die_yield: 0.8,
                    package_yield: 0.95,
                    assembly_cost_usd: 100.0,
                    test_cost_usd: 50.0,
                    non_recurring_engineering_cost_usd: 10_000_000.0,
                    amortization_units: 100_000,
                },
            }),
            accelerator_hourly_cost_usd: 0.8,
            host_hourly_cost_usd: 0.25,
        }
    }
}
