use std::collections::BTreeSet;
use std::fs::File;
use std::hint::black_box;
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;

use serde::{Deserialize, Serialize};
use thiserror::Error;

pub const QWEN_INT4_KERNEL_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const QWEN_INT4_KERNEL_REPORT_SCHEMA_VERSION: u32 = 1;
pub const QWEN_INT4_BATCH_FRONTIER_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const QWEN_INT4_BATCH_FRONTIER_REPORT_SCHEMA_VERSION: u32 = 1;
pub const QWEN_INT4_AARCH64_NEON_REQUEST_SCHEMA_VERSION: u32 = 1;
pub const QWEN_INT4_AARCH64_NEON_REPORT_SCHEMA_VERSION: u32 = 1;
const GROUP_SIZE: usize = 8;
const MAX_SAFETENSORS_HEADER_BYTES: u64 = 64 * 1024 * 1024;
const AARCH64_NEON_MAXIMUM_OUTPUT_ABSOLUTE_ERROR: f64 = 1e-3;
const AARCH64_NEON_MAXIMUM_OUTPUT_RMSE: f64 = 1e-4;
const AARCH64_NEON_STUDY_ID: &str = "qwen3-0.6b-int4-o-gate-up-aarch64-neon-v1";
const AARCH64_NEON_BASE_REQUEST_PATH: &str = "configs/qwen3-0.6b-int4-packed-kernel-smoke-v1.json";
const AARCH64_NEON_BASE_REQUEST_BLAKE3: &str =
    "b103d7a7f5b92223bf316f0e8424f37334cb89e2f14f8215d2223079f458a222";
const AARCH64_NEON_CHECKPOINT_SHA256: &str =
    "f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b";
const AARCH64_NEON_QUALITY_EVIDENCE_SHA256: &str =
    "810201f17e88b4a1be625627ca98b7ffd42ee9e15ab2dbe42f4d6aa32cfe4a05";
const AARCH64_NEON_TENSOR_SOURCE_PINS: [(&str, &str); 3] = [
    (
        "model.layers.0.self_attn.o_proj.weight",
        "88c9cc589476128bec96ece9d825422cbad162a70c16625119b2e132be518e1a",
    ),
    (
        "model.layers.0.mlp.gate_proj.weight",
        "8e9fffe22ba26c6f63da2e9c984ecd6f269a64034a04719340ec9d055c13fd0e",
    ),
    (
        "model.layers.0.mlp.up_proj.weight",
        "bcb34ecc8344764a96f5b21fafbcfd06166708de42dc91e409b957953037b595",
    ),
];

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ScaleStorage {
    Bfloat16,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum QwenTensorFamily {
    AttentionOutput,
    MlpGate,
    MlpUp,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenCheckpointPin {
    pub model_id: String,
    pub model_revision: String,
    pub path: PathBuf,
    pub expected_file_bytes: u64,
    pub expected_sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QualityEvidencePin {
    pub path: PathBuf,
    pub expected_sha256: String,
    pub candidate: String,
    pub scope: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenTensorPin {
    pub family: QwenTensorFamily,
    pub name: String,
    pub expected_dtype: String,
    pub expected_rows: usize,
    pub expected_columns: usize,
    pub expected_source_bytes_blake3: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Int4BenchmarkPlan {
    pub seed: u64,
    pub group_size: usize,
    pub scale_storage: ScaleStorage,
    pub thread_count: usize,
    pub warmup_iterations: usize,
    pub measured_iterations: usize,
    pub require_release_build: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorrectnessThresholds {
    pub maximum_dequantized_weight_absolute_error: f64,
    pub maximum_dequantized_weight_rmse: f64,
    pub maximum_output_absolute_error: f64,
    pub maximum_output_rmse: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4KernelSmokeRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub checkpoint: QwenCheckpointPin,
    pub quality_evidence: QualityEvidencePin,
    pub benchmark: Int4BenchmarkPlan,
    pub correctness: CorrectnessThresholds,
    pub tensors: Vec<QwenTensorPin>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4Aarch64NeonTensorSourcePin {
    pub name: String,
    pub expected_source_bytes_blake3: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4Aarch64NeonBenchmarkPlan {
    pub required_target_architecture: String,
    pub required_target_feature: String,
    pub require_release_build: bool,
    pub thread_count: usize,
    pub warmup_iterations: usize,
    pub measured_iterations: usize,
    pub preallocated_output_buffers: bool,
    pub alternate_forward_reverse_order: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4Aarch64NeonCorrectnessThresholds {
    pub maximum_output_absolute_error: f64,
    pub maximum_output_rmse: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4Aarch64NeonRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub base_request_path: PathBuf,
    pub expected_base_request_blake3: String,
    pub expected_checkpoint_sha256: String,
    pub expected_quality_evidence_sha256: String,
    pub tensor_source_pins: Vec<QwenInt4Aarch64NeonTensorSourcePin>,
    pub benchmark: QwenInt4Aarch64NeonBenchmarkPlan,
    pub correctness: QwenInt4Aarch64NeonCorrectnessThresholds,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PackedInt4Matrix {
    rows: usize,
    columns: usize,
    packed_codes: Vec<u8>,
    scale_bits: Vec<u16>,
    scale_storage: ScaleStorage,
}

impl PackedInt4Matrix {
    pub fn pack_group8(
        weights: &[f32],
        rows: usize,
        columns: usize,
        scale_storage: ScaleStorage,
    ) -> Result<Self, QwenInt4KernelError> {
        Self::pack_groupwise(weights, rows, columns, GROUP_SIZE, scale_storage)
    }

    pub fn pack_groupwise(
        weights: &[f32],
        rows: usize,
        columns: usize,
        group_size: usize,
        scale_storage: ScaleStorage,
    ) -> Result<Self, QwenInt4KernelError> {
        if group_size != GROUP_SIZE {
            return Err(QwenInt4KernelError::UnsupportedGroupSize(group_size));
        }
        let expected = rows
            .checked_mul(columns)
            .ok_or(QwenInt4KernelError::DimensionOverflow)?;
        if weights.len() != expected {
            return Err(QwenInt4KernelError::WeightCountMismatch {
                expected,
                actual: weights.len(),
            });
        }
        if rows == 0 || columns == 0 || columns % GROUP_SIZE != 0 {
            return Err(QwenInt4KernelError::InvalidMatrixShape { rows, columns });
        }
        if weights.iter().any(|weight| !weight.is_finite()) {
            return Err(QwenInt4KernelError::NonFiniteWeight);
        }

        let mut packed_codes = Vec::with_capacity(expected / 2);
        let mut scale_bits = Vec::with_capacity(expected / GROUP_SIZE);
        for row in weights.chunks_exact(columns) {
            for group in row.chunks_exact(GROUP_SIZE) {
                let maximum = group
                    .iter()
                    .map(|weight| weight.abs())
                    .fold(0.0_f32, f32::max);
                let scale = if maximum == 0.0 { 1.0 } else { maximum / 7.0 };
                let stored_scale_bits = f32_to_bf16_bits(scale);
                scale_bits.push(stored_scale_bits);
                for pair in group.chunks_exact(2) {
                    let low = quantized_code(pair[0], scale);
                    let high = quantized_code(pair[1], scale);
                    packed_codes.push(encode_signed_int4(low) | (encode_signed_int4(high) << 4));
                }
            }
        }
        Ok(Self {
            rows,
            columns,
            packed_codes,
            scale_bits,
            scale_storage,
        })
    }

    pub fn packed_codes(&self) -> &[u8] {
        &self.packed_codes
    }

    pub fn scale_bits(&self) -> &[u16] {
        &self.scale_bits
    }

    pub fn code_bytes(&self) -> usize {
        self.packed_codes.len()
    }

    pub fn scale_bytes(&self) -> usize {
        self.scale_bits.len() * size_of::<u16>()
    }

    pub fn packed_bytes(&self) -> usize {
        self.code_bytes() + self.scale_bytes()
    }

    pub fn logical_bytes_read_per_output(&self) -> usize {
        self.columns / 2 + self.columns / GROUP_SIZE * size_of::<u16>()
    }

    pub fn dequantize(&self) -> Vec<f32> {
        let mut output = Vec::with_capacity(self.rows * self.columns);
        let groups_per_row = self.columns / GROUP_SIZE;
        for row in 0..self.rows {
            for group in 0..groups_per_row {
                let group_index = row * groups_per_row + group;
                let scale = bf16_bits_to_f32(self.scale_bits[group_index]);
                let byte_base = group_index * GROUP_SIZE / 2;
                for byte in &self.packed_codes[byte_base..byte_base + GROUP_SIZE / 2] {
                    output.push(f32::from(decode_signed_int4(byte & 0x0f)) * scale);
                    output.push(f32::from(decode_signed_int4(byte >> 4)) * scale);
                }
            }
        }
        output
    }

    pub fn matvec(&self, input: &[f32]) -> Result<Vec<f32>, QwenInt4KernelError> {
        let mut output = vec![0.0; self.rows];
        self.matvec_into(input, &mut output)?;
        Ok(output)
    }

    pub fn matvec_into(
        &self,
        input: &[f32],
        output: &mut [f32],
    ) -> Result<(), QwenInt4KernelError> {
        if input.len() != self.columns {
            return Err(QwenInt4KernelError::InputWidthMismatch {
                expected: self.columns,
                actual: input.len(),
            });
        }
        if output.len() != self.rows {
            return Err(QwenInt4KernelError::OutputHeightMismatch {
                expected: self.rows,
                actual: output.len(),
            });
        }
        let groups_per_row = self.columns / GROUP_SIZE;
        for (row, output_value) in output.iter_mut().enumerate() {
            let mut sum = 0.0_f32;
            for group in 0..groups_per_row {
                let group_index = row * groups_per_row + group;
                let scale = bf16_bits_to_f32(self.scale_bits[group_index]);
                let byte_base = group_index * GROUP_SIZE / 2;
                let input_base = group * GROUP_SIZE;
                for pair in 0..GROUP_SIZE / 2 {
                    let byte = self.packed_codes[byte_base + pair];
                    let column = input_base + pair * 2;
                    let low = f32::from(decode_signed_int4(byte & 0x0f)) * scale;
                    let high = f32::from(decode_signed_int4(byte >> 4)) * scale;
                    sum += low * input[column];
                    sum += high * input[column + 1];
                }
            }
            *output_value = sum;
        }
        Ok(())
    }

    #[cfg(target_arch = "aarch64")]
    pub fn matvec_aarch64_neon(&self, input: &[f32]) -> Result<Vec<f32>, QwenInt4KernelError> {
        let mut output = vec![0.0; self.rows];
        self.matvec_aarch64_neon_into(input, &mut output)?;
        Ok(output)
    }

    #[cfg(target_arch = "aarch64")]
    pub fn matvec_aarch64_neon_into(
        &self,
        input: &[f32],
        output: &mut [f32],
    ) -> Result<(), QwenInt4KernelError> {
        if input.len() != self.columns {
            return Err(QwenInt4KernelError::InputWidthMismatch {
                expected: self.columns,
                actual: input.len(),
            });
        }
        if output.len() != self.rows {
            return Err(QwenInt4KernelError::OutputHeightMismatch {
                expected: self.rows,
                actual: output.len(),
            });
        }
        unsafe { self.matvec_aarch64_neon_into_unchecked(input, output) };
        Ok(())
    }

    #[cfg(target_arch = "aarch64")]
    #[target_feature(enable = "neon")]
    unsafe fn matvec_aarch64_neon_into_unchecked(&self, input: &[f32], output: &mut [f32]) {
        use std::arch::aarch64::{
            vaddq_f32, vaddvq_f32, vcvtq_f32_s32, vget_high_s16, vget_low_s16, vld1_s8, vld1q_f32,
            vmovl_s8, vmovl_s16, vmulq_f32,
        };

        let groups_per_row = self.columns / GROUP_SIZE;
        for (row, output_value) in output.iter_mut().enumerate() {
            let mut sum = 0.0_f32;
            for group in 0..groups_per_row {
                let group_index = row * groups_per_row + group;
                let scale = bf16_bits_to_f32(self.scale_bits[group_index]);
                let byte_base = group_index * GROUP_SIZE / 2;
                let input_base = group * GROUP_SIZE;
                let mut codes = [0_i8; GROUP_SIZE];
                for pair in 0..GROUP_SIZE / 2 {
                    let byte = self.packed_codes[byte_base + pair];
                    codes[pair * 2] = decode_signed_int4(byte & 0x0f);
                    codes[pair * 2 + 1] = decode_signed_int4(byte >> 4);
                }
                let group_sum = unsafe {
                    let code_i16 = vmovl_s8(vld1_s8(codes.as_ptr()));
                    let code_low = vcvtq_f32_s32(vmovl_s16(vget_low_s16(code_i16)));
                    let code_high = vcvtq_f32_s32(vmovl_s16(vget_high_s16(code_i16)));
                    let input_low = vld1q_f32(input.as_ptr().add(input_base));
                    let input_high = vld1q_f32(input.as_ptr().add(input_base + 4));
                    vaddvq_f32(vaddq_f32(
                        vmulq_f32(code_low, input_low),
                        vmulq_f32(code_high, input_high),
                    ))
                };
                sum += group_sum * scale;
            }
            *output_value = sum;
        }
    }

    pub fn batch_matmul_feature_major(
        &self,
        input: &[f32],
        batch_size: usize,
        batch_tile_size: usize,
    ) -> Result<Vec<f32>, QwenInt4KernelError> {
        let output_elements = self
            .rows
            .checked_mul(batch_size)
            .ok_or(QwenInt4KernelError::DimensionOverflow)?;
        let mut output = vec![0.0; output_elements];
        self.batch_matmul_feature_major_into(input, batch_size, batch_tile_size, &mut output)?;
        Ok(output)
    }

    pub fn batch_matmul_feature_major_into(
        &self,
        input: &[f32],
        batch_size: usize,
        batch_tile_size: usize,
        output: &mut [f32],
    ) -> Result<(), QwenInt4KernelError> {
        validate_batch_buffers(
            self.rows,
            self.columns,
            input,
            batch_size,
            batch_tile_size,
            output,
        )?;
        output.fill(0.0);
        let groups_per_row = self.columns / GROUP_SIZE;
        for row in 0..self.rows {
            for tile_start in (0..batch_size).step_by(batch_tile_size) {
                let tile_end = (tile_start + batch_tile_size).min(batch_size);
                let output_tile =
                    &mut output[row * batch_size + tile_start..row * batch_size + tile_end];
                for group in 0..groups_per_row {
                    let group_index = row * groups_per_row + group;
                    let scale = bf16_bits_to_f32(self.scale_bits[group_index]);
                    let byte_base = group_index * GROUP_SIZE / 2;
                    let column_base = group * GROUP_SIZE;
                    for pair in 0..GROUP_SIZE / 2 {
                        let byte = self.packed_codes[byte_base + pair];
                        let low = f32::from(decode_signed_int4(byte & 0x0f)) * scale;
                        let high = f32::from(decode_signed_int4(byte >> 4)) * scale;
                        let low_column = column_base + pair * 2;
                        let high_column = low_column + 1;
                        let low_input = &input[low_column * batch_size + tile_start
                            ..low_column * batch_size + tile_end];
                        let high_input = &input[high_column * batch_size + tile_start
                            ..high_column * batch_size + tile_end];
                        for lane in 0..output_tile.len() {
                            output_tile[lane] += low * low_input[lane];
                            output_tile[lane] += high * high_input[lane];
                        }
                    }
                }
            }
        }
        Ok(())
    }

    pub fn checksum_blake3(&self) -> String {
        let mut hasher = blake3::Hasher::new();
        hasher.update(&(self.rows as u64).to_le_bytes());
        hasher.update(&(self.columns as u64).to_le_bytes());
        hasher.update(&[match self.scale_storage {
            ScaleStorage::Bfloat16 => 1,
        }]);
        hasher.update(&self.packed_codes);
        for scale in &self.scale_bits {
            hasher.update(&scale.to_le_bytes());
        }
        hasher.finalize().to_hex().to_string()
    }
}

pub fn floating_group8_qdq(
    weights: &[f32],
    rows: usize,
    columns: usize,
    scale_storage: ScaleStorage,
) -> Result<Vec<f32>, QwenInt4KernelError> {
    if scale_storage != ScaleStorage::Bfloat16 {
        return Err(QwenInt4KernelError::InvalidField("scale_storage"));
    }
    let expected = rows
        .checked_mul(columns)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if weights.len() != expected {
        return Err(QwenInt4KernelError::WeightCountMismatch {
            expected,
            actual: weights.len(),
        });
    }
    if rows == 0 || columns == 0 || columns % GROUP_SIZE != 0 {
        return Err(QwenInt4KernelError::InvalidMatrixShape { rows, columns });
    }
    if weights.iter().any(|weight| !weight.is_finite()) {
        return Err(QwenInt4KernelError::NonFiniteWeight);
    }
    let mut restored = Vec::with_capacity(expected);
    for row in weights.chunks_exact(columns) {
        for group in row.chunks_exact(GROUP_SIZE) {
            let maximum = group
                .iter()
                .map(|weight| weight.abs())
                .fold(0.0_f32, f32::max);
            let scale = if maximum == 0.0 { 1.0 } else { maximum / 7.0 };
            let stored_scale = bf16_bits_to_f32(f32_to_bf16_bits(scale));
            restored.extend(
                group
                    .iter()
                    .map(|weight| f32::from(quantized_code(*weight, scale)) * stored_scale),
            );
        }
    }
    Ok(restored)
}

pub fn floating_qdq_batch_matmul_feature_major(
    weights: &[f32],
    rows: usize,
    columns: usize,
    input: &[f32],
    batch_size: usize,
    batch_tile_size: usize,
) -> Result<Vec<f32>, QwenInt4KernelError> {
    let weight_elements = rows
        .checked_mul(columns)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if weights.len() != weight_elements {
        return Err(QwenInt4KernelError::WeightCountMismatch {
            expected: weight_elements,
            actual: weights.len(),
        });
    }
    let output_elements = rows
        .checked_mul(batch_size)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let mut output = vec![0.0; output_elements];
    floating_qdq_batch_matmul_feature_major_into(
        weights,
        rows,
        columns,
        input,
        batch_size,
        batch_tile_size,
        &mut output,
    )?;
    Ok(output)
}

fn floating_qdq_batch_matmul_feature_major_into(
    weights: &[f32],
    rows: usize,
    columns: usize,
    input: &[f32],
    batch_size: usize,
    batch_tile_size: usize,
    output: &mut [f32],
) -> Result<(), QwenInt4KernelError> {
    validate_batch_buffers(rows, columns, input, batch_size, batch_tile_size, output)?;
    let expected_weights = rows
        .checked_mul(columns)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if weights.len() != expected_weights {
        return Err(QwenInt4KernelError::WeightCountMismatch {
            expected: expected_weights,
            actual: weights.len(),
        });
    }
    if rows == 0 || columns == 0 || columns % GROUP_SIZE != 0 {
        return Err(QwenInt4KernelError::InvalidMatrixShape { rows, columns });
    }
    output.fill(0.0);
    let groups_per_row = columns / GROUP_SIZE;
    for row in 0..rows {
        for tile_start in (0..batch_size).step_by(batch_tile_size) {
            let tile_end = (tile_start + batch_tile_size).min(batch_size);
            let output_tile =
                &mut output[row * batch_size + tile_start..row * batch_size + tile_end];
            for group in 0..groups_per_row {
                let column_base = group * GROUP_SIZE;
                for pair in 0..GROUP_SIZE / 2 {
                    let low_column = column_base + pair * 2;
                    let high_column = low_column + 1;
                    let low_weight = weights[row * columns + low_column];
                    let high_weight = weights[row * columns + high_column];
                    let low_input = &input
                        [low_column * batch_size + tile_start..low_column * batch_size + tile_end];
                    let high_input = &input[high_column * batch_size + tile_start
                        ..high_column * batch_size + tile_end];
                    for lane in 0..output_tile.len() {
                        output_tile[lane] += low_weight * low_input[lane];
                        output_tile[lane] += high_weight * high_input[lane];
                    }
                }
            }
        }
    }
    Ok(())
}

fn validate_batch_buffers(
    rows: usize,
    columns: usize,
    input: &[f32],
    batch_size: usize,
    batch_tile_size: usize,
    output: &[f32],
) -> Result<(), QwenInt4KernelError> {
    if batch_size == 0 {
        return Err(QwenInt4KernelError::InvalidBatchSize);
    }
    if batch_tile_size == 0 {
        return Err(QwenInt4KernelError::InvalidBatchTileSize);
    }
    let expected_input = columns
        .checked_mul(batch_size)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if input.len() != expected_input {
        return Err(QwenInt4KernelError::BatchInputCountMismatch {
            expected: expected_input,
            actual: input.len(),
        });
    }
    let expected_output = rows
        .checked_mul(batch_size)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if output.len() != expected_output {
        return Err(QwenInt4KernelError::BatchOutputCountMismatch {
            expected: expected_output,
            actual: output.len(),
        });
    }
    Ok(())
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HostIdentity {
    pub hostname: String,
    pub operating_system: String,
    pub architecture: String,
    pub cpu_model: String,
    pub available_parallelism: usize,
    pub benchmark_thread_count: usize,
    pub rust_profile: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StorageMeasurement {
    pub source_bfloat16_bytes: u64,
    pub packed_code_bytes: u64,
    pub group_scale_bytes: u64,
    pub total_packed_bytes: u64,
    pub scale_overhead_fraction_of_codes: f64,
    pub scale_fraction_of_packed_storage: f64,
    pub packed_fraction_of_source_bfloat16: f64,
    pub logical_packed_weight_bytes_read_per_output: u64,
    pub logical_f32_qdq_weight_bytes_read_per_output: u64,
    pub logical_input_bytes_if_read_once_per_matvec: u64,
    pub logical_output_write_bytes_per_matvec: u64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KernelCorrectnessMeasurement {
    pub packed_dequantized_weight_checksum_blake3: String,
    pub floating_qdq_weight_checksum_blake3: String,
    pub maximum_dequantized_weight_absolute_error: f64,
    pub dequantized_weight_rmse: f64,
    pub packed_output_checksum_blake3: String,
    pub floating_reference_output_checksum_blake3: String,
    pub maximum_absolute_error: f64,
    pub rmse: f64,
    pub checksum_match: bool,
    pub passed: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimingMeasurement {
    pub iterations: usize,
    pub minimum_seconds: f64,
    pub median_seconds: f64,
    pub logical_bytes_per_call: u64,
    pub best_logical_effective_bandwidth_gbps: f64,
    pub median_logical_effective_bandwidth_gbps: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TensorKernelMeasurement {
    pub family: QwenTensorFamily,
    pub tensor_name: String,
    pub source_dtype: String,
    pub rows: usize,
    pub columns: usize,
    pub parameter_count: u64,
    pub source_bytes_blake3: String,
    pub input_checksum_blake3: String,
    pub packed_checksum_blake3: String,
    pub source_load_seconds: f64,
    pub pack_seconds: f64,
    pub storage: StorageMeasurement,
    pub correctness: KernelCorrectnessMeasurement,
    pub packed_scalar: TimingMeasurement,
    pub floating_qdq_scalar_reference: TimingMeasurement,
    pub raw_speed_ratio_reference_over_packed: f64,
    pub raw_time_ratio_packed_over_reference: f64,
    pub boundary: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AggregateKernelMeasurement {
    pub tensor_count: usize,
    pub parameter_count: u64,
    pub source_bfloat16_bytes: u64,
    pub total_packed_bytes: u64,
    pub summed_packed_median_seconds: f64,
    pub summed_floating_reference_median_seconds: f64,
    pub raw_speed_ratio_reference_over_packed: f64,
    pub raw_time_ratio_packed_over_reference: f64,
    pub all_correctness_checks_passed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KernelSourceVerification {
    pub checkpoint_file_size_verified: bool,
    pub checkpoint_declared_sha256_recomputed: bool,
    pub measured_tensor_blake3_pins_verified: bool,
    pub quality_evidence_declared_sha256_recomputed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct KernelSmokeClaims {
    pub local_packed_scalar_correctness_permitted: bool,
    pub local_scalar_timing_observation_permitted: bool,
    pub tuned_kernel_claim_permitted: bool,
    pub blas_or_vllm_comparison_permitted: bool,
    pub quality_equivalence_claim_permitted: bool,
    pub serving_claim_permitted: bool,
    pub energy_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub production_claim_permitted: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4KernelSmokeResult {
    pub study_id: String,
    pub checkpoint: QwenCheckpointPin,
    pub quality_evidence: QualityEvidencePin,
    pub host: HostIdentity,
    pub benchmark: Int4BenchmarkPlan,
    pub source_verification: KernelSourceVerification,
    pub reference_boundary: String,
    pub measurements: Vec<TensorKernelMeasurement>,
    pub aggregate: AggregateKernelMeasurement,
    pub claims: KernelSmokeClaims,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4KernelSmokeReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: QwenInt4KernelSmokeResult,
}

impl QwenInt4KernelSmokeReport {
    pub fn verify_content_id(&self) -> Result<bool, QwenInt4KernelError> {
        Ok(self.content_id == report_content_id(self.schema_version, &self.result)?)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4BatchFrontierRequest {
    pub schema_version: u32,
    pub study_id: String,
    pub base_request_path: PathBuf,
    pub expected_base_request_blake3: String,
    pub scalar_smoke_report_path: PathBuf,
    pub expected_scalar_smoke_report_blake3: String,
    pub batch_sizes: Vec<usize>,
    pub batch_tile_size: usize,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CompilerIdentity {
    pub rustc_verbose: String,
    pub target_architecture: String,
    pub target_operating_system: String,
    pub release_profile: bool,
    pub explicit_simd_intrinsics_used: bool,
    pub auto_vectorization_inspected: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DequantizedWeightCorrectness {
    pub packed_checksum_blake3: String,
    pub floating_qdq_checksum_blake3: String,
    pub maximum_absolute_error: f64,
    pub rmse: f64,
    pub checksum_match: bool,
    pub passed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchWorkEquality {
    pub output_elements: u64,
    pub packed_multiply_accumulate_terms: u64,
    pub floating_reference_multiply_accumulate_terms: u64,
    pub nominal_arithmetic_operations_each: u64,
    pub exact_work_count_equal: bool,
    pub accumulation_order_equal: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchMemoryAccounting {
    pub batch_tile_count: u64,
    pub source_bfloat16_weight_resident_bytes: u64,
    pub packed_code_resident_bytes: u64,
    pub packed_scale_resident_bytes: u64,
    pub packed_weight_resident_bytes: u64,
    pub floating_qdq_weight_resident_bytes: u64,
    pub feature_major_input_resident_bytes: u64,
    pub row_major_output_resident_bytes: u64,
    pub packed_total_resident_bytes: u64,
    pub floating_reference_total_resident_bytes: u64,
    pub packed_logical_weight_stream_bytes_per_call: u64,
    pub floating_reference_logical_weight_stream_bytes_per_call: u64,
    pub logical_activation_operand_bytes_per_call: u64,
    pub logical_minimum_output_write_bytes_per_call: u64,
    pub packed_minimum_logical_bytes_per_call: u64,
    pub floating_reference_minimum_logical_bytes_per_call: u64,
    pub scope: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchOutputCorrectness {
    pub packed_checksum_blake3: String,
    pub floating_reference_checksum_blake3: String,
    pub maximum_absolute_error: f64,
    pub rmse: f64,
    pub checksum_match: bool,
    pub passed: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchKernelMeasurement {
    pub batch_size: usize,
    pub batch_tile_size: usize,
    pub input_layout: String,
    pub output_layout: String,
    pub input_checksum_blake3: String,
    pub work: BatchWorkEquality,
    pub memory: BatchMemoryAccounting,
    pub correctness: BatchOutputCorrectness,
    pub packed_weight_stationary: TimingMeasurement,
    pub floating_qdq_weight_stationary_reference: TimingMeasurement,
    pub raw_speed_ratio_reference_over_packed: f64,
    pub raw_time_ratio_packed_over_reference: f64,
    pub packed_faster: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TensorBatchFrontierMeasurement {
    pub family: QwenTensorFamily,
    pub tensor_name: String,
    pub rows: usize,
    pub columns: usize,
    pub parameter_count: u64,
    pub source_bytes_blake3: String,
    pub packed_checksum_blake3: String,
    pub source_load_seconds: f64,
    pub pack_seconds: f64,
    pub storage: StorageMeasurement,
    pub dequantized_weight_correctness: DequantizedWeightCorrectness,
    pub points: Vec<BatchKernelMeasurement>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AggregateBatchFrontierPoint {
    pub batch_size: usize,
    pub tensor_count: usize,
    pub multiply_accumulate_terms: u64,
    pub summed_packed_median_seconds: f64,
    pub summed_floating_reference_median_seconds: f64,
    pub raw_speed_ratio_reference_over_packed: f64,
    pub raw_time_ratio_packed_over_reference: f64,
    pub packed_faster: bool,
    pub all_work_counts_equal: bool,
    pub all_correctness_checks_passed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchCrossoverConclusion {
    pub observed_packed_win_batches: Vec<usize>,
    pub first_observed_packed_win_batch: Option<usize>,
    pub strict_no_crossover_in_sweep: bool,
    pub tested_batch_sizes: Vec<usize>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchOneScalarReconciliation {
    pub scalar_smoke_report_path: PathBuf,
    pub scalar_smoke_report_blake3: String,
    pub scalar_smoke_report_content_id: String,
    pub scalar_reference_over_packed_speed_ratio: f64,
    pub frontier_batch_one_reference_over_packed_speed_ratio: f64,
    pub both_observe_packed_slower: bool,
    pub direction_consistent: bool,
    pub same_host_cpu: bool,
    pub same_release_profile: bool,
    pub boundary_difference: String,
    pub conclusion: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct BatchFrontierClaims {
    pub local_batch_correctness_permitted: bool,
    pub local_batch_timing_observation_permitted: bool,
    pub tuned_kernel_claim_permitted: bool,
    pub explicit_simd_claim_permitted: bool,
    pub blas_or_vllm_comparison_permitted: bool,
    pub gpu_claim_permitted: bool,
    pub quality_equivalence_claim_permitted: bool,
    pub serving_claim_permitted: bool,
    pub energy_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub production_claim_permitted: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4BatchFrontierResult {
    pub study_id: String,
    pub base_request_path: PathBuf,
    pub base_request_blake3: String,
    pub base_study_id: String,
    pub checkpoint: QwenCheckpointPin,
    pub quality_evidence: QualityEvidencePin,
    pub host: HostIdentity,
    pub compiler: CompilerIdentity,
    pub benchmark: Int4BenchmarkPlan,
    pub batch_sizes: Vec<usize>,
    pub batch_tile_size: usize,
    pub implementation_boundary: String,
    pub source_verification: KernelSourceVerification,
    pub measurements: Vec<TensorBatchFrontierMeasurement>,
    pub aggregate_points: Vec<AggregateBatchFrontierPoint>,
    pub batch_one_scalar_reconciliation: BatchOneScalarReconciliation,
    pub crossover: BatchCrossoverConclusion,
    pub claims: BatchFrontierClaims,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4BatchFrontierReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: QwenInt4BatchFrontierResult,
}

impl QwenInt4BatchFrontierReport {
    pub fn verify_content_id(&self) -> Result<bool, QwenInt4KernelError> {
        Ok(self.content_id == batch_frontier_content_id(self.schema_version, &self.result)?)
    }
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonSourceVerification {
    pub base_request_blake3_verified: bool,
    pub checkpoint_sha256_pin_matches_base_request: bool,
    pub quality_evidence_sha256_pin_matches_base_request: bool,
    pub tensor_source_pins_match_base_request: bool,
    pub checkpoint_file_size_verified: bool,
    pub measured_tensor_blake3_pins_verified: bool,
    pub checkpoint_declared_sha256_recomputed: bool,
    pub quality_evidence_declared_sha256_recomputed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonWorkBoundary {
    pub output_elements: u64,
    pub multiply_accumulate_terms_each: u64,
    pub nominal_arithmetic_operations_each: u64,
    pub identical_input_for_all_paths: bool,
    pub identical_packed_matrix_for_neon_and_scalar: bool,
    pub independently_materialized_f32_qdq_reference: bool,
    pub exact_term_count_equal: bool,
    pub accumulation_order_equal: bool,
    pub scope: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonMemoryBoundary {
    pub source_bfloat16_weight_resident_bytes: u64,
    pub packed_code_resident_bytes: u64,
    pub packed_scale_resident_bytes: u64,
    pub packed_weight_resident_bytes: u64,
    pub floating_qdq_weight_resident_bytes: u64,
    pub input_resident_bytes: u64,
    pub output_buffer_bytes_each: u64,
    pub preallocated_output_buffer_count: usize,
    pub timed_region_allocation_bytes: u64,
    pub neon_minimum_logical_bytes_per_call: u64,
    pub scalar_packed_minimum_logical_bytes_per_call: u64,
    pub floating_qdq_minimum_logical_bytes_per_call: u64,
    pub scope: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonOutputComparison {
    pub candidate_output_checksum_blake3: String,
    pub reference_output_checksum_blake3: String,
    pub maximum_absolute_error: f64,
    pub rmse: f64,
    pub maximum_absolute_error_threshold: f64,
    pub rmse_threshold: f64,
    pub passed: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonAlternatingOrder {
    pub forward_order: Vec<String>,
    pub reverse_order: Vec<String>,
    pub forward_warmup_count: usize,
    pub reverse_warmup_count: usize,
    pub forward_measured_count: usize,
    pub reverse_measured_count: usize,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonTensorMeasurement {
    pub family: QwenTensorFamily,
    pub tensor_name: String,
    pub source_dtype: String,
    pub rows: usize,
    pub columns: usize,
    pub parameter_count: u64,
    pub source_bytes_blake3: String,
    pub input_checksum_blake3: String,
    pub packed_checksum_blake3: String,
    pub source_load_seconds: f64,
    pub pack_seconds: f64,
    pub storage: StorageMeasurement,
    pub dequantized_weight_correctness: DequantizedWeightCorrectness,
    pub work: Aarch64NeonWorkBoundary,
    pub memory: Aarch64NeonMemoryBoundary,
    pub neon_vs_scalar_packed_correctness: Aarch64NeonOutputComparison,
    pub neon_vs_floating_qdq_correctness: Aarch64NeonOutputComparison,
    pub alternating_order: Aarch64NeonAlternatingOrder,
    pub aarch64_neon: TimingMeasurement,
    pub scalar_packed: TimingMeasurement,
    pub floating_qdq_scalar_reference: TimingMeasurement,
    pub scalar_packed_over_neon_speed_ratio: f64,
    pub floating_qdq_over_neon_speed_ratio: f64,
    pub neon_faster_than_scalar_packed: bool,
    pub neon_faster_than_floating_qdq: bool,
    pub boundary: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonAggregateMeasurement {
    pub tensor_count: usize,
    pub parameter_count: u64,
    pub summed_neon_median_seconds: f64,
    pub summed_scalar_packed_median_seconds: f64,
    pub summed_floating_qdq_median_seconds: f64,
    pub scalar_packed_over_neon_speed_ratio: f64,
    pub floating_qdq_over_neon_speed_ratio: f64,
    pub neon_faster_than_scalar_packed: bool,
    pub neon_faster_than_floating_qdq: bool,
    pub all_work_counts_equal: bool,
    pub all_correctness_checks_passed: bool,
    pub all_timed_regions_allocation_free: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Aarch64NeonClaims {
    pub local_aarch64_neon_intrinsic_correctness_permitted: bool,
    pub local_aarch64_neon_timing_observation_permitted: bool,
    pub local_scalar_packed_comparison_permitted: bool,
    pub local_f32_qdq_scalar_comparison_permitted: bool,
    pub tuned_kernel_claim_permitted: bool,
    pub blas_or_vllm_comparison_permitted: bool,
    pub gpu_claim_permitted: bool,
    pub quality_equivalence_claim_permitted: bool,
    pub serving_claim_permitted: bool,
    pub energy_claim_permitted: bool,
    pub cost_per_token_claim_permitted: bool,
    pub provider_claim_permitted: bool,
    pub production_claim_permitted: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PredictiveMeasurementScope {
    pub model_id: String,
    pub model_revision: String,
    pub workload_id: String,
    pub workload_revision: String,
    pub context_regime: String,
    pub hardware_id: String,
    pub hardware_revision: String,
    pub software_id: String,
    pub software_revision: String,
    pub intervention_id: String,
    pub intervention_revision: String,
    pub metric_id: String,
    pub metric_unit: String,
    pub higher_is_better: bool,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4Aarch64NeonResult {
    pub study_id: String,
    pub base_request_path: PathBuf,
    pub base_request_blake3: String,
    pub base_study_id: String,
    pub checkpoint: QwenCheckpointPin,
    pub quality_evidence: QualityEvidencePin,
    pub tensor_source_pins: Vec<QwenInt4Aarch64NeonTensorSourcePin>,
    pub host: HostIdentity,
    pub compiler: CompilerIdentity,
    pub benchmark: QwenInt4Aarch64NeonBenchmarkPlan,
    pub correctness: QwenInt4Aarch64NeonCorrectnessThresholds,
    pub predictive_scope: PredictiveMeasurementScope,
    pub source_verification: Aarch64NeonSourceVerification,
    pub implementation_boundary: String,
    pub measurements: Vec<Aarch64NeonTensorMeasurement>,
    pub aggregate: Aarch64NeonAggregateMeasurement,
    pub claims: Aarch64NeonClaims,
    pub limitations: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct QwenInt4Aarch64NeonReport {
    pub schema_version: u32,
    pub content_id: String,
    pub result: QwenInt4Aarch64NeonResult,
}

impl QwenInt4Aarch64NeonReport {
    pub fn verify_content_id(&self) -> Result<bool, QwenInt4KernelError> {
        Ok(self.content_id == aarch64_neon_content_id(self.schema_version, &self.result)?)
    }
}

fn aarch64_neon_predictive_scope() -> PredictiveMeasurementScope {
    PredictiveMeasurementScope {
        model_id: "Qwen/Qwen3-0.6B".into(),
        model_revision: "c1899de289a04d12100db370d81485cdf75e47ca".into(),
        workload_id: "qwen3-0.6b-layer0-o-gate-up-packed-matvec".into(),
        workload_revision: "8c9f38791aea1e54178371a6aa41c0da5dda4c39b2640c778bbb044bfbd4165d"
            .into(),
        context_regime: "decode-batch1-three-layer0-tensors".into(),
        hardware_id: "Apple M4 Pro".into(),
        hardware_revision: "Mac16,7-Apple-M4-Pro-14c-48GB".into(),
        software_id: "foundry-qwen-int4-aarch64-neon".into(),
        software_revision: "qwen-int4-aarch64-neon-v1".into(),
        intervention_id: "aarch64-neon-group8-packed-matvec".into(),
        intervention_revision: "v1".into(),
        metric_id: "summed_three_tensor_median_seconds".into(),
        metric_unit: "seconds".into(),
        higher_is_better: false,
    }
}

pub fn validate_qwen_int4_aarch64_neon_request_contract(
    request: &QwenInt4Aarch64NeonRequest,
) -> Result<(), QwenInt4KernelError> {
    if request.schema_version != QWEN_INT4_AARCH64_NEON_REQUEST_SCHEMA_VERSION {
        return Err(QwenInt4KernelError::UnsupportedSchemaVersion {
            expected: QWEN_INT4_AARCH64_NEON_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    if request.study_id != AARCH64_NEON_STUDY_ID {
        return Err(QwenInt4KernelError::InvalidField("study_id"));
    }
    if request.base_request_path != Path::new(AARCH64_NEON_BASE_REQUEST_PATH)
        || request.expected_base_request_blake3 != AARCH64_NEON_BASE_REQUEST_BLAKE3
    {
        return Err(QwenInt4KernelError::InvalidField("base_request"));
    }
    if request.expected_checkpoint_sha256 != AARCH64_NEON_CHECKPOINT_SHA256 {
        return Err(QwenInt4KernelError::InvalidField(
            "expected_checkpoint_sha256",
        ));
    }
    if request.expected_quality_evidence_sha256 != AARCH64_NEON_QUALITY_EVIDENCE_SHA256 {
        return Err(QwenInt4KernelError::InvalidField(
            "expected_quality_evidence_sha256",
        ));
    }
    if request.tensor_source_pins.len() != AARCH64_NEON_TENSOR_SOURCE_PINS.len()
        || request
            .tensor_source_pins
            .iter()
            .zip(AARCH64_NEON_TENSOR_SOURCE_PINS)
            .any(|(actual, expected)| {
                actual.name != expected.0 || actual.expected_source_bytes_blake3 != expected.1
            })
    {
        return Err(QwenInt4KernelError::InvalidField("tensor_source_pins"));
    }
    if request.benchmark.required_target_architecture != "aarch64" {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.required_target_architecture",
        ));
    }
    if request.benchmark.required_target_feature != "neon" {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.required_target_feature",
        ));
    }
    if !request.benchmark.require_release_build {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.require_release_build",
        ));
    }
    if request.benchmark.thread_count != 1 {
        return Err(QwenInt4KernelError::InvalidField("benchmark.thread_count"));
    }
    if request.benchmark.warmup_iterations != 5 {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.warmup_iterations",
        ));
    }
    if request.benchmark.measured_iterations != 31 {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.measured_iterations",
        ));
    }
    if !request.benchmark.preallocated_output_buffers {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.preallocated_output_buffers",
        ));
    }
    if !request.benchmark.alternate_forward_reverse_order {
        return Err(QwenInt4KernelError::InvalidField(
            "benchmark.alternate_forward_reverse_order",
        ));
    }
    if request.correctness.maximum_output_absolute_error
        != AARCH64_NEON_MAXIMUM_OUTPUT_ABSOLUTE_ERROR
    {
        return Err(QwenInt4KernelError::InvalidField(
            "correctness.maximum_output_absolute_error",
        ));
    }
    if request.correctness.maximum_output_rmse != AARCH64_NEON_MAXIMUM_OUTPUT_RMSE {
        return Err(QwenInt4KernelError::InvalidField(
            "correctness.maximum_output_rmse",
        ));
    }
    Ok(())
}

pub fn run_qwen_int4_aarch64_neon(
    request: &QwenInt4Aarch64NeonRequest,
) -> Result<QwenInt4Aarch64NeonReport, QwenInt4KernelError> {
    validate_qwen_int4_aarch64_neon_request_contract(request)?;
    if std::env::consts::ARCH != request.benchmark.required_target_architecture {
        return Err(QwenInt4KernelError::TargetArchitectureMismatch {
            expected: request.benchmark.required_target_architecture.clone(),
            actual: std::env::consts::ARCH.into(),
        });
    }
    if cfg!(debug_assertions) {
        return Err(QwenInt4KernelError::ReleaseBuildRequired);
    }
    let base_request_bytes = std::fs::read(&request.base_request_path)?;
    let base_request_blake3 = blake3::hash(&base_request_bytes).to_hex().to_string();
    if base_request_blake3 != request.expected_base_request_blake3 {
        return Err(QwenInt4KernelError::BaseRequestChecksumMismatch {
            expected: request.expected_base_request_blake3.clone(),
            actual: base_request_blake3,
        });
    }
    let base_request = serde_json::from_slice::<QwenInt4KernelSmokeRequest>(&base_request_bytes)?;
    validate_request(&base_request)?;
    validate_aarch64_neon_source_bindings(request, &base_request)?;
    #[cfg(target_arch = "aarch64")]
    {
        run_qwen_int4_aarch64_neon_on_supported_host(request, &base_request, base_request_blake3)
    }
    #[cfg(not(target_arch = "aarch64"))]
    {
        Err(QwenInt4KernelError::TargetArchitectureMismatch {
            expected: "aarch64".into(),
            actual: std::env::consts::ARCH.into(),
        })
    }
}

fn validate_aarch64_neon_source_bindings(
    request: &QwenInt4Aarch64NeonRequest,
    base_request: &QwenInt4KernelSmokeRequest,
) -> Result<(), QwenInt4KernelError> {
    if request.expected_checkpoint_sha256 != base_request.checkpoint.expected_sha256 {
        return Err(QwenInt4KernelError::InvalidField(
            "expected_checkpoint_sha256",
        ));
    }
    if request.expected_quality_evidence_sha256 != base_request.quality_evidence.expected_sha256 {
        return Err(QwenInt4KernelError::InvalidField(
            "expected_quality_evidence_sha256",
        ));
    }
    let requested = request
        .tensor_source_pins
        .iter()
        .map(|pin| (pin.name.as_str(), pin.expected_source_bytes_blake3.as_str()))
        .collect::<BTreeSet<_>>();
    let base = base_request
        .tensors
        .iter()
        .map(|pin| (pin.name.as_str(), pin.expected_source_bytes_blake3.as_str()))
        .collect::<BTreeSet<_>>();
    if requested != base {
        return Err(QwenInt4KernelError::InvalidField("tensor_source_pins"));
    }
    Ok(())
}

#[cfg(target_arch = "aarch64")]
fn run_qwen_int4_aarch64_neon_on_supported_host(
    request: &QwenInt4Aarch64NeonRequest,
    base_request: &QwenInt4KernelSmokeRequest,
    base_request_blake3: String,
) -> Result<QwenInt4Aarch64NeonReport, QwenInt4KernelError> {
    let mut measurements = Vec::with_capacity(base_request.tensors.len());
    for (index, tensor) in base_request.tensors.iter().enumerate() {
        measurements.push(measure_aarch64_neon_tensor(
            base_request,
            request,
            tensor,
            index as u64,
        )?);
    }
    let aggregate = aggregate_aarch64_neon_measurements(&measurements)?;
    let mut compiler = compiler_identity();
    compiler.explicit_simd_intrinsics_used = true;
    let result = QwenInt4Aarch64NeonResult {
        study_id: request.study_id.clone(),
        base_request_path: request.base_request_path.clone(),
        base_request_blake3,
        base_study_id: base_request.study_id.clone(),
        checkpoint: base_request.checkpoint.clone(),
        quality_evidence: base_request.quality_evidence.clone(),
        tensor_source_pins: request.tensor_source_pins.clone(),
        host: host_identity(request.benchmark.thread_count),
        compiler,
        benchmark: request.benchmark.clone(),
        correctness: request.correctness.clone(),
        predictive_scope: aarch64_neon_predictive_scope(),
        source_verification: Aarch64NeonSourceVerification {
            base_request_blake3_verified: true,
            checkpoint_sha256_pin_matches_base_request: true,
            quality_evidence_sha256_pin_matches_base_request: true,
            tensor_source_pins_match_base_request: true,
            checkpoint_file_size_verified: true,
            measured_tensor_blake3_pins_verified: true,
            checkpoint_declared_sha256_recomputed: false,
            quality_evidence_declared_sha256_recomputed: false,
        },
        implementation_boundary: "All three paths consume the same precomputed f32 input. NEON and scalar packed paths consume the identical signed group-8 INT4 code and BF16-scale matrix; the scalar f32 control consumes an independently materialized QDQ matrix with the same represented values. Quantization, packing, QDQ materialization, input generation, allocation, and checksum work are outside the timed region. Each timed call writes a distinct preallocated f32 output buffer. Forward NEON→scalar-packed→f32-QDQ and reverse f32-QDQ→scalar-packed→NEON orders alternate by sample.".into(),
        measurements,
        aggregate,
        claims: Aarch64NeonClaims {
            local_aarch64_neon_intrinsic_correctness_permitted: true,
            local_aarch64_neon_timing_observation_permitted: true,
            local_scalar_packed_comparison_permitted: true,
            local_f32_qdq_scalar_comparison_permitted: true,
            tuned_kernel_claim_permitted: false,
            blas_or_vllm_comparison_permitted: false,
            gpu_claim_permitted: false,
            quality_equivalence_claim_permitted: false,
            serving_claim_permitted: false,
            energy_claim_permitted: false,
            cost_per_token_claim_permitted: false,
            provider_claim_permitted: false,
            production_claim_permitted: false,
        },
        limitations: vec![
            "The NEON path is an exact local intrinsic implementation, not a tuned kernel: it decodes each group through a temporary stack array and has no multi-row tiling, prefetch, cache blocking, fusion, or threading.".into(),
            "The f32 QDQ control is a one-thread scalar Rust matvec over independently materialized weights, not BF16 BLAS, Accelerate, llama.cpp, vLLM, SGLang, a GPU kernel, or a provider baseline.".into(),
            "The immutable 1e-3 maximum-error and 1e-4 RMSE gates permit only f32 accumulation-order differences and are checked before timing; failure aborts the report.".into(),
            "Logical byte counts describe resident operands and one minimum stream per call. They are not hardware-counter cache, DRAM, or energy measurements.".into(),
            "Timing consists of 31 alternating-order release-build samples on one local AArch64 thread under uncontrolled host load; it is not a confidence interval or production benchmark.".into(),
            "Only the three exact layer-zero tensors from the prior selective-INT4 study are measured. Full-model quality, retained BF16 paths, fusion, scheduling, serving, and cost are excluded.".into(),
            "The prior quality artifact used a different runtime representation. Binding its hash records provenance but does not transfer quality approval to this packed intrinsic path.".into(),
            "The declared checkpoint and quality-evidence SHA-256 pins are cross-checked against the byte-pinned base request but are not recomputed in this runner. File size and each measured tensor BLAKE3 are verified.".into(),
        ],
    };
    let schema_version = QWEN_INT4_AARCH64_NEON_REPORT_SCHEMA_VERSION;
    let content_id = aarch64_neon_content_id(schema_version, &result)?;
    Ok(QwenInt4Aarch64NeonReport {
        schema_version,
        content_id,
        result,
    })
}

#[cfg(target_arch = "aarch64")]
struct Aarch64NeonExecution<'a> {
    packed: &'a PackedInt4Matrix,
    floating_qdq_weights: &'a [f32],
    rows: usize,
    columns: usize,
    input: &'a [f32],
}

#[cfg(target_arch = "aarch64")]
struct Aarch64NeonOutputs {
    neon: Vec<f32>,
    scalar_packed: Vec<f32>,
    floating_qdq: Vec<f32>,
}

#[cfg(target_arch = "aarch64")]
struct Aarch64NeonPathTimings {
    neon_seconds: f64,
    scalar_packed_seconds: f64,
    floating_qdq_seconds: f64,
}

#[cfg(target_arch = "aarch64")]
impl Aarch64NeonExecution<'_> {
    fn execute_order(
        &self,
        forward: bool,
        outputs: &mut Aarch64NeonOutputs,
    ) -> Result<(), QwenInt4KernelError> {
        if forward {
            self.execute_neon(&mut outputs.neon)?;
            self.execute_scalar_packed(&mut outputs.scalar_packed)?;
            self.execute_floating_qdq(&mut outputs.floating_qdq);
        } else {
            self.execute_floating_qdq(&mut outputs.floating_qdq);
            self.execute_scalar_packed(&mut outputs.scalar_packed)?;
            self.execute_neon(&mut outputs.neon)?;
        }
        Ok(())
    }

    fn time_order(
        &self,
        forward: bool,
        outputs: &mut Aarch64NeonOutputs,
    ) -> Result<Aarch64NeonPathTimings, QwenInt4KernelError> {
        let (neon_seconds, scalar_packed_seconds, floating_qdq_seconds) = if forward {
            let neon_seconds = time_aarch64_neon(self.packed, self.input, &mut outputs.neon)?;
            let scalar_packed_seconds =
                time_packed(self.packed, self.input, &mut outputs.scalar_packed)?;
            let floating_qdq_seconds = time_floating(
                self.floating_qdq_weights,
                self.rows,
                self.columns,
                self.input,
                &mut outputs.floating_qdq,
            );
            (neon_seconds, scalar_packed_seconds, floating_qdq_seconds)
        } else {
            let floating_qdq_seconds = time_floating(
                self.floating_qdq_weights,
                self.rows,
                self.columns,
                self.input,
                &mut outputs.floating_qdq,
            );
            let scalar_packed_seconds =
                time_packed(self.packed, self.input, &mut outputs.scalar_packed)?;
            let neon_seconds = time_aarch64_neon(self.packed, self.input, &mut outputs.neon)?;
            (neon_seconds, scalar_packed_seconds, floating_qdq_seconds)
        };
        Ok(Aarch64NeonPathTimings {
            neon_seconds,
            scalar_packed_seconds,
            floating_qdq_seconds,
        })
    }

    fn execute_neon(&self, output: &mut [f32]) -> Result<(), QwenInt4KernelError> {
        self.packed
            .matvec_aarch64_neon_into(black_box(self.input), black_box(output))?;
        black_box(output);
        Ok(())
    }

    fn execute_scalar_packed(&self, output: &mut [f32]) -> Result<(), QwenInt4KernelError> {
        self.packed
            .matvec_into(black_box(self.input), black_box(output))?;
        black_box(output);
        Ok(())
    }

    fn execute_floating_qdq(&self, output: &mut [f32]) {
        floating_matvec_into(
            black_box(self.floating_qdq_weights),
            self.rows,
            self.columns,
            black_box(self.input),
            black_box(output),
        );
        black_box(output);
    }
}

#[cfg(target_arch = "aarch64")]
fn measure_aarch64_neon_tensor(
    base_request: &QwenInt4KernelSmokeRequest,
    request: &QwenInt4Aarch64NeonRequest,
    tensor: &QwenTensorPin,
    tensor_index: u64,
) -> Result<Aarch64NeonTensorMeasurement, QwenInt4KernelError> {
    let load_start = Instant::now();
    let loaded = load_bf16_tensor(&base_request.checkpoint.path, tensor)?;
    let source_load_seconds = load_start.elapsed().as_secs_f64();
    let source_bytes_blake3 = blake3::hash(&loaded.raw_bytes).to_hex().to_string();
    if source_bytes_blake3 != tensor.expected_source_bytes_blake3 {
        return Err(QwenInt4KernelError::TensorChecksumMismatch {
            tensor: tensor.name.clone(),
            expected: tensor.expected_source_bytes_blake3.clone(),
            actual: source_bytes_blake3,
        });
    }

    let pack_start = Instant::now();
    let packed = PackedInt4Matrix::pack_group8(
        &loaded.weights,
        tensor.expected_rows,
        tensor.expected_columns,
        base_request.benchmark.scale_storage,
    )?;
    let pack_seconds = pack_start.elapsed().as_secs_f64();
    let floating_qdq_weights = floating_group8_qdq(
        &loaded.weights,
        tensor.expected_rows,
        tensor.expected_columns,
        base_request.benchmark.scale_storage,
    )?;
    let packed_dequantized_weights = packed.dequantize();
    let (weight_maximum_absolute_error, weight_rmse) =
        error_metrics(&packed_dequantized_weights, &floating_qdq_weights);
    let packed_weight_checksum = checksum_f32(&packed_dequantized_weights);
    let floating_weight_checksum = checksum_f32(&floating_qdq_weights);
    let dequantized_weight_correctness = DequantizedWeightCorrectness {
        checksum_match: packed_weight_checksum == floating_weight_checksum,
        packed_checksum_blake3: packed_weight_checksum,
        floating_qdq_checksum_blake3: floating_weight_checksum,
        maximum_absolute_error: weight_maximum_absolute_error,
        rmse: weight_rmse,
        passed: weight_maximum_absolute_error
            <= base_request
                .correctness
                .maximum_dequantized_weight_absolute_error
            && weight_rmse <= base_request.correctness.maximum_dequantized_weight_rmse,
    };
    if !dequantized_weight_correctness.passed {
        return Err(QwenInt4KernelError::CorrectnessThresholdFailed {
            tensor: tensor.name.clone(),
            maximum_absolute_error: weight_maximum_absolute_error,
            rmse: weight_rmse,
        });
    }
    drop(packed_dequantized_weights);

    let input = deterministic_input(
        tensor.expected_columns,
        base_request.benchmark.seed ^ tensor_index.wrapping_mul(0x9e37_79b9_7f4a_7c15),
    );
    let mut outputs = Aarch64NeonOutputs {
        neon: vec![0.0_f32; tensor.expected_rows],
        scalar_packed: vec![0.0_f32; tensor.expected_rows],
        floating_qdq: vec![0.0_f32; tensor.expected_rows],
    };
    let execution = Aarch64NeonExecution {
        packed: &packed,
        floating_qdq_weights: &floating_qdq_weights,
        rows: tensor.expected_rows,
        columns: tensor.expected_columns,
        input: &input,
    };
    execution.execute_order(true, &mut outputs)?;
    let neon_vs_scalar_packed_correctness =
        aarch64_neon_output_comparison(&outputs.neon, &outputs.scalar_packed, &request.correctness);
    let neon_vs_floating_qdq_correctness =
        aarch64_neon_output_comparison(&outputs.neon, &outputs.floating_qdq, &request.correctness);
    for correctness in [
        &neon_vs_scalar_packed_correctness,
        &neon_vs_floating_qdq_correctness,
    ] {
        if !correctness.passed {
            return Err(QwenInt4KernelError::CorrectnessThresholdFailed {
                tensor: tensor.name.clone(),
                maximum_absolute_error: correctness.maximum_absolute_error,
                rmse: correctness.rmse,
            });
        }
    }

    for iteration in 0..request.benchmark.warmup_iterations {
        execution.execute_order(iteration % 2 == 0, &mut outputs)?;
    }
    let mut neon_timings = Vec::with_capacity(request.benchmark.measured_iterations);
    let mut scalar_packed_timings = Vec::with_capacity(request.benchmark.measured_iterations);
    let mut floating_qdq_timings = Vec::with_capacity(request.benchmark.measured_iterations);
    for iteration in 0..request.benchmark.measured_iterations {
        let sample = execution.time_order(iteration % 2 == 0, &mut outputs)?;
        neon_timings.push(sample.neon_seconds);
        scalar_packed_timings.push(sample.scalar_packed_seconds);
        floating_qdq_timings.push(sample.floating_qdq_seconds);
    }

    let parameter_count = to_u64(loaded.weights.len())?;
    let storage = matrix_storage_measurement(
        &packed,
        parameter_count,
        tensor.expected_rows,
        tensor.expected_columns,
    )?;
    let input_resident_bytes = checked_mul_u64(to_u64(input.len())?, 4)?;
    let output_buffer_bytes_each = checked_mul_u64(to_u64(tensor.expected_rows)?, 4)?;
    let floating_qdq_weight_resident_bytes = checked_mul_u64(parameter_count, 4)?;
    let packed_minimum_logical_bytes_per_call = checked_add_u64(
        checked_add_u64(storage.total_packed_bytes, input_resident_bytes)?,
        output_buffer_bytes_each,
    )?;
    let floating_qdq_minimum_logical_bytes_per_call = checked_add_u64(
        checked_add_u64(floating_qdq_weight_resident_bytes, input_resident_bytes)?,
        output_buffer_bytes_each,
    )?;
    let aarch64_neon = timing_measurement(neon_timings, packed_minimum_logical_bytes_per_call);
    let scalar_packed =
        timing_measurement(scalar_packed_timings, packed_minimum_logical_bytes_per_call);
    let floating_qdq_scalar_reference = timing_measurement(
        floating_qdq_timings,
        floating_qdq_minimum_logical_bytes_per_call,
    );
    let scalar_packed_over_neon_speed_ratio =
        scalar_packed.median_seconds / aarch64_neon.median_seconds;
    let floating_qdq_over_neon_speed_ratio =
        floating_qdq_scalar_reference.median_seconds / aarch64_neon.median_seconds;
    let forward_warmup_count = request.benchmark.warmup_iterations.div_ceil(2);
    let forward_measured_count = request.benchmark.measured_iterations.div_ceil(2);
    Ok(Aarch64NeonTensorMeasurement {
        family: tensor.family,
        tensor_name: tensor.name.clone(),
        source_dtype: tensor.expected_dtype.clone(),
        rows: tensor.expected_rows,
        columns: tensor.expected_columns,
        parameter_count,
        source_bytes_blake3: tensor.expected_source_bytes_blake3.clone(),
        input_checksum_blake3: checksum_f32(&input),
        packed_checksum_blake3: packed.checksum_blake3(),
        source_load_seconds,
        pack_seconds,
        storage: storage.clone(),
        dequantized_weight_correctness,
        work: Aarch64NeonWorkBoundary {
            output_elements: to_u64(tensor.expected_rows)?,
            multiply_accumulate_terms_each: parameter_count,
            nominal_arithmetic_operations_each: checked_mul_u64(parameter_count, 2)?,
            identical_input_for_all_paths: true,
            identical_packed_matrix_for_neon_and_scalar: true,
            independently_materialized_f32_qdq_reference: true,
            exact_term_count_equal: true,
            accumulation_order_equal: false,
            scope: "Each path produces the same row count and evaluates one weight-input term per matrix element. The NEON path horizontally reduces eight products before adding a scaled group sum, while both scalar paths accumulate terms in column order; exact term counts match but floating-point accumulation order does not.".into(),
        },
        memory: Aarch64NeonMemoryBoundary {
            source_bfloat16_weight_resident_bytes: checked_mul_u64(parameter_count, 2)?,
            packed_code_resident_bytes: storage.packed_code_bytes,
            packed_scale_resident_bytes: storage.group_scale_bytes,
            packed_weight_resident_bytes: storage.total_packed_bytes,
            floating_qdq_weight_resident_bytes,
            input_resident_bytes,
            output_buffer_bytes_each,
            preallocated_output_buffer_count: 3,
            timed_region_allocation_bytes: 0,
            neon_minimum_logical_bytes_per_call: packed_minimum_logical_bytes_per_call,
            scalar_packed_minimum_logical_bytes_per_call:
                packed_minimum_logical_bytes_per_call,
            floating_qdq_minimum_logical_bytes_per_call,
            scope: "Resident bytes exclude allocator metadata. Minimum logical bytes count one resident weight representation, one input vector, and one output write per call; they are operand-accounting bounds rather than measured cache, DRAM, or temporary-stack traffic.".into(),
        },
        neon_vs_scalar_packed_correctness,
        neon_vs_floating_qdq_correctness,
        alternating_order: Aarch64NeonAlternatingOrder {
            forward_order: vec![
                "aarch64_neon".into(),
                "scalar_packed".into(),
                "floating_qdq_scalar_reference".into(),
            ],
            reverse_order: vec![
                "floating_qdq_scalar_reference".into(),
                "scalar_packed".into(),
                "aarch64_neon".into(),
            ],
            forward_warmup_count,
            reverse_warmup_count: request.benchmark.warmup_iterations - forward_warmup_count,
            forward_measured_count,
            reverse_measured_count: request.benchmark.measured_iterations
                - forward_measured_count,
        },
        aarch64_neon,
        scalar_packed,
        floating_qdq_scalar_reference,
        scalar_packed_over_neon_speed_ratio,
        floating_qdq_over_neon_speed_ratio,
        neon_faster_than_scalar_packed: scalar_packed_over_neon_speed_ratio > 1.0,
        neon_faster_than_floating_qdq: floating_qdq_over_neon_speed_ratio > 1.0,
        boundary: "Release-profile, one-thread local AArch64 timing of one exact intrinsic path, the existing scalar packed path, and an independently materialized scalar f32-QDQ path. All outputs are preallocated and order alternates; no tuned library, serving runtime, GPU, energy, or cost baseline is present.".into(),
    })
}

#[cfg(target_arch = "aarch64")]
fn aarch64_neon_output_comparison(
    candidate: &[f32],
    reference: &[f32],
    thresholds: &QwenInt4Aarch64NeonCorrectnessThresholds,
) -> Aarch64NeonOutputComparison {
    let (maximum_absolute_error, rmse) = error_metrics(candidate, reference);
    Aarch64NeonOutputComparison {
        candidate_output_checksum_blake3: checksum_f32(candidate),
        reference_output_checksum_blake3: checksum_f32(reference),
        maximum_absolute_error,
        rmse,
        maximum_absolute_error_threshold: thresholds.maximum_output_absolute_error,
        rmse_threshold: thresholds.maximum_output_rmse,
        passed: maximum_absolute_error <= thresholds.maximum_output_absolute_error
            && rmse <= thresholds.maximum_output_rmse,
    }
}

#[cfg(target_arch = "aarch64")]
fn aggregate_aarch64_neon_measurements(
    measurements: &[Aarch64NeonTensorMeasurement],
) -> Result<Aarch64NeonAggregateMeasurement, QwenInt4KernelError> {
    let parameter_count = measurements.iter().try_fold(0_u64, |total, measurement| {
        checked_add_u64(total, measurement.parameter_count)
    })?;
    let summed_neon_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.aarch64_neon.median_seconds)
        .sum::<f64>();
    let summed_scalar_packed_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.scalar_packed.median_seconds)
        .sum::<f64>();
    let summed_floating_qdq_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.floating_qdq_scalar_reference.median_seconds)
        .sum::<f64>();
    let scalar_packed_over_neon_speed_ratio =
        summed_scalar_packed_median_seconds / summed_neon_median_seconds;
    let floating_qdq_over_neon_speed_ratio =
        summed_floating_qdq_median_seconds / summed_neon_median_seconds;
    Ok(Aarch64NeonAggregateMeasurement {
        tensor_count: measurements.len(),
        parameter_count,
        summed_neon_median_seconds,
        summed_scalar_packed_median_seconds,
        summed_floating_qdq_median_seconds,
        scalar_packed_over_neon_speed_ratio,
        floating_qdq_over_neon_speed_ratio,
        neon_faster_than_scalar_packed: scalar_packed_over_neon_speed_ratio > 1.0,
        neon_faster_than_floating_qdq: floating_qdq_over_neon_speed_ratio > 1.0,
        all_work_counts_equal: measurements
            .iter()
            .all(|measurement| measurement.work.exact_term_count_equal),
        all_correctness_checks_passed: measurements.iter().all(|measurement| {
            measurement.dequantized_weight_correctness.passed
                && measurement.neon_vs_scalar_packed_correctness.passed
                && measurement.neon_vs_floating_qdq_correctness.passed
        }),
        all_timed_regions_allocation_free: measurements
            .iter()
            .all(|measurement| measurement.memory.timed_region_allocation_bytes == 0),
    })
}

pub fn run_qwen_int4_kernel_smoke(
    request: &QwenInt4KernelSmokeRequest,
) -> Result<QwenInt4KernelSmokeReport, QwenInt4KernelError> {
    validate_request(request)?;
    let host = host_identity(request.benchmark.thread_count);
    let mut measurements = Vec::with_capacity(request.tensors.len());
    for (index, tensor) in request.tensors.iter().enumerate() {
        measurements.push(measure_tensor(request, tensor, index as u64)?);
    }
    let aggregate = aggregate_measurements(&measurements);
    let result = QwenInt4KernelSmokeResult {
        study_id: request.study_id.clone(),
        checkpoint: request.checkpoint.clone(),
        quality_evidence: request.quality_evidence.clone(),
        host,
        benchmark: request.benchmark.clone(),
        source_verification: KernelSourceVerification {
            checkpoint_file_size_verified: true,
            checkpoint_declared_sha256_recomputed: false,
            measured_tensor_blake3_pins_verified: true,
            quality_evidence_declared_sha256_recomputed: false,
        },
        reference_boundary: "The packed representation uses low-nibble-first signed two's-complement INT4 codes and one round-to-nearest-even BF16 scale per group of eight. The control is a one-thread scalar f32 matrix-vector multiply over independently materialized QDQ weights. It is intentionally matched to the scalar packed loop to isolate storage decoding, and is not a tuned BF16 kernel, BLAS, vLLM, llama.cpp, provider, or GPU baseline.".into(),
        measurements,
        aggregate,
        claims: KernelSmokeClaims {
            local_packed_scalar_correctness_permitted: true,
            local_scalar_timing_observation_permitted: true,
            tuned_kernel_claim_permitted: false,
            blas_or_vllm_comparison_permitted: false,
            quality_equivalence_claim_permitted: false,
            serving_claim_permitted: false,
            energy_claim_permitted: false,
            cost_per_token_claim_permitted: false,
            production_claim_permitted: false,
        },
        limitations: vec![
            "The quality run quantized with float32 scales and copied dequantized values into BF16 parameters; this smoke stores BF16 group scales, so kernel correctness does not transfer the prior quality verdict to the packed format.".into(),
            "The scalar implementation has no architecture-specific SIMD, tiling, threading, activation batching, fusion, or cache control.".into(),
            "Logical effective bandwidth divides declared representation bytes by wall time; it is not a hardware-counter measurement of DRAM traffic and tensors may interact with host caches.".into(),
            "Timing is a local host observation under uncontrolled system load and has no confidence interval beyond the retained minimum and median samples.".into(),
            "Only one layer-zero tensor from each selected Qwen family is measured; full-model scheduling and retained BF16 tensors are excluded.".into(),
            "The configured checkpoint and quality-evidence SHA-256 values are provenance labels, not recomputed by this dependency-minimal smoke. File size and every measured tensor's BLAKE3 pin are verified before packing.".into(),
        ],
    };
    let schema_version = QWEN_INT4_KERNEL_REPORT_SCHEMA_VERSION;
    let content_id = report_content_id(schema_version, &result)?;
    Ok(QwenInt4KernelSmokeReport {
        schema_version,
        content_id,
        result,
    })
}

pub fn run_qwen_int4_batch_frontier(
    request: &QwenInt4BatchFrontierRequest,
) -> Result<QwenInt4BatchFrontierReport, QwenInt4KernelError> {
    validate_batch_frontier_request(request)?;
    let base_request_bytes = std::fs::read(&request.base_request_path)?;
    let base_request_blake3 = blake3::hash(&base_request_bytes).to_hex().to_string();
    if base_request_blake3 != request.expected_base_request_blake3 {
        return Err(QwenInt4KernelError::BaseRequestChecksumMismatch {
            expected: request.expected_base_request_blake3.clone(),
            actual: base_request_blake3,
        });
    }
    let base_request = serde_json::from_slice::<QwenInt4KernelSmokeRequest>(&base_request_bytes)?;
    validate_request(&base_request)?;
    let scalar_smoke_report_bytes = std::fs::read(&request.scalar_smoke_report_path)?;
    let scalar_smoke_report_blake3 = blake3::hash(&scalar_smoke_report_bytes)
        .to_hex()
        .to_string();
    if scalar_smoke_report_blake3 != request.expected_scalar_smoke_report_blake3 {
        return Err(QwenInt4KernelError::ScalarReportChecksumMismatch {
            expected: request.expected_scalar_smoke_report_blake3.clone(),
            actual: scalar_smoke_report_blake3,
        });
    }
    let scalar_smoke_report =
        serde_json::from_slice::<QwenInt4KernelSmokeReport>(&scalar_smoke_report_bytes)?;
    if !scalar_smoke_report.verify_content_id()?
        || scalar_smoke_report.result.study_id != base_request.study_id
    {
        return Err(QwenInt4KernelError::InvalidField("scalar_smoke_report"));
    }
    let mut measurements = Vec::with_capacity(base_request.tensors.len());
    for (index, tensor) in base_request.tensors.iter().enumerate() {
        measurements.push(measure_batch_frontier_tensor(
            &base_request,
            request,
            tensor,
            index as u64,
        )?);
    }
    let aggregate_points = aggregate_batch_frontier(request, &measurements)?;
    let batch_one = aggregate_points
        .iter()
        .find(|point| point.batch_size == 1)
        .ok_or(QwenInt4KernelError::MissingBatchPoint(1))?;
    let scalar_ratio = scalar_smoke_report
        .result
        .aggregate
        .raw_speed_ratio_reference_over_packed;
    let frontier_ratio = batch_one.raw_speed_ratio_reference_over_packed;
    let host = host_identity(base_request.benchmark.thread_count);
    let batch_one_scalar_reconciliation = BatchOneScalarReconciliation {
        scalar_smoke_report_path: request.scalar_smoke_report_path.clone(),
        scalar_smoke_report_blake3: request.expected_scalar_smoke_report_blake3.clone(),
        scalar_smoke_report_content_id: scalar_smoke_report.content_id.clone(),
        scalar_reference_over_packed_speed_ratio: scalar_ratio,
        frontier_batch_one_reference_over_packed_speed_ratio: frontier_ratio,
        both_observe_packed_slower: scalar_ratio < 1.0 && frontier_ratio < 1.0,
        direction_consistent: (scalar_ratio > 1.0) == (frontier_ratio > 1.0),
        same_host_cpu: scalar_smoke_report.result.host.cpu_model == host.cpu_model,
        same_release_profile: scalar_smoke_report.result.host.rust_profile == host.rust_profile,
        boundary_difference: "The scalar smoke uses a specialized row-dot-product f32 control and a scalar packed group loop. The batch frontier uses the same generalized row→tile→group→nibble-pair→lane structure for packed and f32 controls, with B=1 represented as one lane. The timings are separate runs and their ratio magnitudes are not directly interchangeable.".into(),
        conclusion: "The final matched B=1 frontier and the original scalar smoke agree in direction: packed decode is slower. The frontier narrows the loss because both sides share the generalized group/pair/tile control structure; this is not a compression win or a work-count mismatch.".into(),
    };
    let observed_packed_win_batches = aggregate_points
        .iter()
        .filter(|point| point.packed_faster)
        .map(|point| point.batch_size)
        .collect::<Vec<_>>();
    let crossover = BatchCrossoverConclusion {
        first_observed_packed_win_batch: observed_packed_win_batches.first().copied(),
        strict_no_crossover_in_sweep: observed_packed_win_batches.is_empty(),
        observed_packed_win_batches,
        tested_batch_sizes: request.batch_sizes.clone(),
    };
    let result = QwenInt4BatchFrontierResult {
        study_id: request.study_id.clone(),
        base_request_path: request.base_request_path.clone(),
        base_request_blake3: request.expected_base_request_blake3.clone(),
        base_study_id: base_request.study_id.clone(),
        checkpoint: base_request.checkpoint.clone(),
        quality_evidence: base_request.quality_evidence.clone(),
        host,
        compiler: compiler_identity(),
        benchmark: base_request.benchmark.clone(),
        batch_sizes: request.batch_sizes.clone(),
        batch_tile_size: request.batch_tile_size,
        implementation_boundary: "Both timed kernels consume prearranged feature-major activations X[K,B] and produce row-major outputs Y[M,B]. For each output row and batch tile they traverse columns in increasing order, then contiguous batch lanes. The packed path loads one BF16 scale and decodes each signed INT4 nibble pair once per tile before reusing both values across the tile. The floating control reads an independently materialized f32 QDQ weight once per tile and uses the identical lane loop. Input rearrangement, quantization, packing, allocation, BLAS, vLLM, explicit SIMD intrinsics, threading, and serving are outside the timed region.".into(),
        source_verification: KernelSourceVerification {
            checkpoint_file_size_verified: true,
            checkpoint_declared_sha256_recomputed: false,
            measured_tensor_blake3_pins_verified: true,
            quality_evidence_declared_sha256_recomputed: false,
        },
        measurements,
        aggregate_points,
        batch_one_scalar_reconciliation,
        crossover,
        claims: BatchFrontierClaims {
            local_batch_correctness_permitted: true,
            local_batch_timing_observation_permitted: true,
            tuned_kernel_claim_permitted: false,
            explicit_simd_claim_permitted: false,
            blas_or_vllm_comparison_permitted: false,
            gpu_claim_permitted: false,
            quality_equivalence_claim_permitted: false,
            serving_claim_permitted: false,
            energy_claim_permitted: false,
            cost_per_token_claim_permitted: false,
            production_claim_permitted: false,
        },
        limitations: vec![
            "Feature-major activation arrangement is a kernel input contract and its creation cost is excluded from the timings.".into(),
            "The Rust compiler may transform ordinary loops, but generated assembly and hardware counters were not inspected; no SIMD or tuned-kernel claim is permitted.".into(),
            "The f32 QDQ reference is a matched one-thread Rust control, not a tuned BF16 BLAS, llama.cpp, vLLM, GPU, or provider baseline.".into(),
            "Logical byte counts are declared operand-accounting minima, not measured cache or DRAM transactions. Output accumulator traffic beyond one final write is excluded.".into(),
            "Timing is a release-build local host observation under uncontrolled load. Minimum and median samples are retained without a statistical confidence interval.".into(),
            "Only one exact layer-zero tensor from each quality-selected family is measured. Full-model fusion, retained BF16 tensors, scheduling, and serving are absent.".into(),
            "The packed BF16-scale representation differs from the prior BF16 QDQ quality experiment, so exact local kernel correctness does not transfer its quality verdict.".into(),
        ],
    };
    let schema_version = QWEN_INT4_BATCH_FRONTIER_REPORT_SCHEMA_VERSION;
    let content_id = batch_frontier_content_id(schema_version, &result)?;
    Ok(QwenInt4BatchFrontierReport {
        schema_version,
        content_id,
        result,
    })
}

fn validate_batch_frontier_request(
    request: &QwenInt4BatchFrontierRequest,
) -> Result<(), QwenInt4KernelError> {
    if request.schema_version != QWEN_INT4_BATCH_FRONTIER_REQUEST_SCHEMA_VERSION {
        return Err(QwenInt4KernelError::UnsupportedSchemaVersion {
            expected: QWEN_INT4_BATCH_FRONTIER_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    if request.study_id.trim().is_empty() {
        return Err(QwenInt4KernelError::InvalidField("study_id"));
    }
    if request.base_request_path.as_os_str().is_empty()
        || !is_lower_hex_256(&request.expected_base_request_blake3)
        || request.scalar_smoke_report_path.as_os_str().is_empty()
        || !is_lower_hex_256(&request.expected_scalar_smoke_report_blake3)
    {
        return Err(QwenInt4KernelError::InvalidField("base_request"));
    }
    if request.batch_sizes.is_empty()
        || request.batch_sizes.contains(&0)
        || !request.batch_sizes.contains(&1)
        || request
            .batch_sizes
            .windows(2)
            .any(|window| window[0] >= window[1])
    {
        return Err(QwenInt4KernelError::InvalidField("batch_sizes"));
    }
    if request.batch_tile_size == 0 {
        return Err(QwenInt4KernelError::InvalidBatchTileSize);
    }
    Ok(())
}

fn measure_batch_frontier_tensor(
    base_request: &QwenInt4KernelSmokeRequest,
    frontier_request: &QwenInt4BatchFrontierRequest,
    tensor: &QwenTensorPin,
    tensor_index: u64,
) -> Result<TensorBatchFrontierMeasurement, QwenInt4KernelError> {
    let load_start = Instant::now();
    let loaded = load_bf16_tensor(&base_request.checkpoint.path, tensor)?;
    let source_load_seconds = load_start.elapsed().as_secs_f64();
    let source_bytes_blake3 = blake3::hash(&loaded.raw_bytes).to_hex().to_string();
    if source_bytes_blake3 != tensor.expected_source_bytes_blake3 {
        return Err(QwenInt4KernelError::TensorChecksumMismatch {
            tensor: tensor.name.clone(),
            expected: tensor.expected_source_bytes_blake3.clone(),
            actual: source_bytes_blake3,
        });
    }
    let pack_start = Instant::now();
    let packed = PackedInt4Matrix::pack_group8(
        &loaded.weights,
        tensor.expected_rows,
        tensor.expected_columns,
        base_request.benchmark.scale_storage,
    )?;
    let pack_seconds = pack_start.elapsed().as_secs_f64();
    let floating_qdq_weights = floating_group8_qdq(
        &loaded.weights,
        tensor.expected_rows,
        tensor.expected_columns,
        base_request.benchmark.scale_storage,
    )?;
    let packed_dequantized_weights = packed.dequantize();
    let (weight_maximum_absolute_error, weight_rmse) =
        error_metrics(&packed_dequantized_weights, &floating_qdq_weights);
    let packed_weight_checksum = checksum_f32(&packed_dequantized_weights);
    let floating_weight_checksum = checksum_f32(&floating_qdq_weights);
    let weight_correctness = DequantizedWeightCorrectness {
        checksum_match: packed_weight_checksum == floating_weight_checksum,
        packed_checksum_blake3: packed_weight_checksum,
        floating_qdq_checksum_blake3: floating_weight_checksum,
        maximum_absolute_error: weight_maximum_absolute_error,
        rmse: weight_rmse,
        passed: weight_maximum_absolute_error
            <= base_request
                .correctness
                .maximum_dequantized_weight_absolute_error
            && weight_rmse <= base_request.correctness.maximum_dequantized_weight_rmse,
    };
    if !weight_correctness.passed {
        return Err(QwenInt4KernelError::CorrectnessThresholdFailed {
            tensor: tensor.name.clone(),
            maximum_absolute_error: weight_correctness.maximum_absolute_error,
            rmse: weight_correctness.rmse,
        });
    }
    let parameter_count = to_u64(loaded.weights.len())?;
    let storage = matrix_storage_measurement(
        &packed,
        parameter_count,
        tensor.expected_rows,
        tensor.expected_columns,
    )?;
    let points = frontier_request
        .batch_sizes
        .iter()
        .map(|batch_size| {
            measure_batch_frontier_point(
                base_request,
                frontier_request,
                tensor,
                tensor_index,
                &packed,
                &floating_qdq_weights,
                parameter_count,
                *batch_size,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Ok(TensorBatchFrontierMeasurement {
        family: tensor.family,
        tensor_name: tensor.name.clone(),
        rows: tensor.expected_rows,
        columns: tensor.expected_columns,
        parameter_count,
        source_bytes_blake3: tensor.expected_source_bytes_blake3.clone(),
        packed_checksum_blake3: packed.checksum_blake3(),
        source_load_seconds,
        pack_seconds,
        storage,
        dequantized_weight_correctness: weight_correctness,
        points,
    })
}

#[allow(clippy::too_many_arguments)]
fn measure_batch_frontier_point(
    base_request: &QwenInt4KernelSmokeRequest,
    frontier_request: &QwenInt4BatchFrontierRequest,
    tensor: &QwenTensorPin,
    tensor_index: u64,
    packed: &PackedInt4Matrix,
    floating_qdq_weights: &[f32],
    parameter_count: u64,
    batch_size: usize,
) -> Result<BatchKernelMeasurement, QwenInt4KernelError> {
    let seed = base_request.benchmark.seed
        ^ tensor_index.wrapping_mul(0x9e37_79b9_7f4a_7c15)
        ^ (batch_size as u64).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    let input_elements = tensor
        .expected_columns
        .checked_mul(batch_size)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let input = deterministic_input(input_elements, seed);
    let input_checksum_blake3 = checksum_f32(&input);
    let output_elements = tensor
        .expected_rows
        .checked_mul(batch_size)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let mut packed_output = vec![0.0_f32; output_elements];
    let mut floating_output = vec![0.0_f32; output_elements];
    packed.batch_matmul_feature_major_into(
        &input,
        batch_size,
        frontier_request.batch_tile_size,
        &mut packed_output,
    )?;
    floating_qdq_batch_matmul_feature_major_into(
        floating_qdq_weights,
        tensor.expected_rows,
        tensor.expected_columns,
        &input,
        batch_size,
        frontier_request.batch_tile_size,
        &mut floating_output,
    )?;
    let (maximum_absolute_error, rmse) = error_metrics(&packed_output, &floating_output);
    let packed_checksum_blake3 = checksum_f32(&packed_output);
    let floating_reference_checksum_blake3 = checksum_f32(&floating_output);
    let correctness = BatchOutputCorrectness {
        checksum_match: packed_checksum_blake3 == floating_reference_checksum_blake3,
        packed_checksum_blake3,
        floating_reference_checksum_blake3,
        maximum_absolute_error,
        rmse,
        passed: maximum_absolute_error <= base_request.correctness.maximum_output_absolute_error
            && rmse <= base_request.correctness.maximum_output_rmse,
    };
    if !correctness.passed {
        return Err(QwenInt4KernelError::CorrectnessThresholdFailed {
            tensor: tensor.name.clone(),
            maximum_absolute_error,
            rmse,
        });
    }
    for _ in 0..base_request.benchmark.warmup_iterations {
        packed.batch_matmul_feature_major_into(
            black_box(&input),
            batch_size,
            frontier_request.batch_tile_size,
            black_box(&mut packed_output),
        )?;
        floating_qdq_batch_matmul_feature_major_into(
            black_box(floating_qdq_weights),
            tensor.expected_rows,
            tensor.expected_columns,
            black_box(&input),
            batch_size,
            frontier_request.batch_tile_size,
            black_box(&mut floating_output),
        )?;
        black_box(&packed_output);
        black_box(&floating_output);
    }
    let mut packed_timings = Vec::with_capacity(base_request.benchmark.measured_iterations);
    let mut floating_timings = Vec::with_capacity(base_request.benchmark.measured_iterations);
    for iteration in 0..base_request.benchmark.measured_iterations {
        if iteration % 2 == 0 {
            packed_timings.push(time_packed_batch(
                packed,
                &input,
                batch_size,
                frontier_request.batch_tile_size,
                &mut packed_output,
            )?);
            floating_timings.push(time_floating_batch(
                floating_qdq_weights,
                tensor.expected_rows,
                tensor.expected_columns,
                &input,
                batch_size,
                frontier_request.batch_tile_size,
                &mut floating_output,
            )?);
        } else {
            floating_timings.push(time_floating_batch(
                floating_qdq_weights,
                tensor.expected_rows,
                tensor.expected_columns,
                &input,
                batch_size,
                frontier_request.batch_tile_size,
                &mut floating_output,
            )?);
            packed_timings.push(time_packed_batch(
                packed,
                &input,
                batch_size,
                frontier_request.batch_tile_size,
                &mut packed_output,
            )?);
        }
    }
    let memory = batch_memory_accounting(
        packed,
        tensor.expected_rows,
        tensor.expected_columns,
        parameter_count,
        batch_size,
        frontier_request.batch_tile_size,
    )?;
    let packed_weight_stationary =
        timing_measurement(packed_timings, memory.packed_minimum_logical_bytes_per_call);
    let floating_qdq_weight_stationary_reference = timing_measurement(
        floating_timings,
        memory.floating_reference_minimum_logical_bytes_per_call,
    );
    let raw_speed_ratio_reference_over_packed = floating_qdq_weight_stationary_reference
        .median_seconds
        / packed_weight_stationary.median_seconds;
    let multiply_accumulate_terms = checked_mul_u64(parameter_count, to_u64(batch_size)?)?;
    let work = BatchWorkEquality {
        output_elements: to_u64(output_elements)?,
        packed_multiply_accumulate_terms: multiply_accumulate_terms,
        floating_reference_multiply_accumulate_terms: multiply_accumulate_terms,
        nominal_arithmetic_operations_each: checked_mul_u64(multiply_accumulate_terms, 2)?,
        exact_work_count_equal: true,
        accumulation_order_equal: true,
    };
    Ok(BatchKernelMeasurement {
        batch_size,
        batch_tile_size: frontier_request.batch_tile_size,
        input_layout: "feature_major_k_by_batch_contiguous_batch_lane".into(),
        output_layout: "row_major_output_row_by_batch_contiguous_batch_lane".into(),
        input_checksum_blake3,
        work,
        memory,
        correctness,
        packed_weight_stationary,
        floating_qdq_weight_stationary_reference,
        raw_speed_ratio_reference_over_packed,
        raw_time_ratio_packed_over_reference: 1.0 / raw_speed_ratio_reference_over_packed,
        packed_faster: raw_speed_ratio_reference_over_packed > 1.0,
    })
}

fn matrix_storage_measurement(
    packed: &PackedInt4Matrix,
    parameter_count: u64,
    rows: usize,
    columns: usize,
) -> Result<StorageMeasurement, QwenInt4KernelError> {
    let source_bfloat16_bytes = checked_mul_u64(parameter_count, 2)?;
    let packed_code_bytes = to_u64(packed.code_bytes())?;
    let group_scale_bytes = to_u64(packed.scale_bytes())?;
    let total_packed_bytes = checked_add_u64(packed_code_bytes, group_scale_bytes)?;
    Ok(StorageMeasurement {
        source_bfloat16_bytes,
        packed_code_bytes,
        group_scale_bytes,
        total_packed_bytes,
        scale_overhead_fraction_of_codes: group_scale_bytes as f64 / packed_code_bytes as f64,
        scale_fraction_of_packed_storage: group_scale_bytes as f64 / total_packed_bytes as f64,
        packed_fraction_of_source_bfloat16: total_packed_bytes as f64
            / source_bfloat16_bytes as f64,
        logical_packed_weight_bytes_read_per_output: to_u64(
            packed.logical_bytes_read_per_output(),
        )?,
        logical_f32_qdq_weight_bytes_read_per_output: checked_mul_u64(to_u64(columns)?, 4)?,
        logical_input_bytes_if_read_once_per_matvec: checked_mul_u64(to_u64(columns)?, 4)?,
        logical_output_write_bytes_per_matvec: checked_mul_u64(to_u64(rows)?, 4)?,
    })
}

fn batch_memory_accounting(
    packed: &PackedInt4Matrix,
    rows: usize,
    columns: usize,
    parameter_count: u64,
    batch_size: usize,
    batch_tile_size: usize,
) -> Result<BatchMemoryAccounting, QwenInt4KernelError> {
    let tile_count = batch_size
        .checked_add(batch_tile_size - 1)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?
        / batch_tile_size;
    let batch_tile_count = to_u64(tile_count)?;
    let source_bfloat16_weight_resident_bytes = checked_mul_u64(parameter_count, 2)?;
    let packed_code_resident_bytes = to_u64(packed.code_bytes())?;
    let packed_scale_resident_bytes = to_u64(packed.scale_bytes())?;
    let packed_weight_resident_bytes =
        checked_add_u64(packed_code_resident_bytes, packed_scale_resident_bytes)?;
    let floating_qdq_weight_resident_bytes = checked_mul_u64(parameter_count, 4)?;
    let feature_major_input_resident_bytes =
        checked_mul_u64(checked_mul_u64(to_u64(columns)?, to_u64(batch_size)?)?, 4)?;
    let row_major_output_resident_bytes =
        checked_mul_u64(checked_mul_u64(to_u64(rows)?, to_u64(batch_size)?)?, 4)?;
    let packed_total_resident_bytes = checked_add_u64(
        checked_add_u64(
            packed_weight_resident_bytes,
            feature_major_input_resident_bytes,
        )?,
        row_major_output_resident_bytes,
    )?;
    let floating_reference_total_resident_bytes = checked_add_u64(
        checked_add_u64(
            floating_qdq_weight_resident_bytes,
            feature_major_input_resident_bytes,
        )?,
        row_major_output_resident_bytes,
    )?;
    let packed_logical_weight_stream_bytes_per_call =
        checked_mul_u64(packed_weight_resident_bytes, batch_tile_count)?;
    let floating_reference_logical_weight_stream_bytes_per_call =
        checked_mul_u64(floating_qdq_weight_resident_bytes, batch_tile_count)?;
    let logical_activation_operand_bytes_per_call =
        checked_mul_u64(checked_mul_u64(parameter_count, to_u64(batch_size)?)?, 4)?;
    let logical_minimum_output_write_bytes_per_call = row_major_output_resident_bytes;
    let packed_minimum_logical_bytes_per_call = checked_add_u64(
        checked_add_u64(
            packed_logical_weight_stream_bytes_per_call,
            logical_activation_operand_bytes_per_call,
        )?,
        logical_minimum_output_write_bytes_per_call,
    )?;
    let floating_reference_minimum_logical_bytes_per_call = checked_add_u64(
        checked_add_u64(
            floating_reference_logical_weight_stream_bytes_per_call,
            logical_activation_operand_bytes_per_call,
        )?,
        logical_minimum_output_write_bytes_per_call,
    )?;
    Ok(BatchMemoryAccounting {
        batch_tile_count,
        source_bfloat16_weight_resident_bytes,
        packed_code_resident_bytes,
        packed_scale_resident_bytes,
        packed_weight_resident_bytes,
        floating_qdq_weight_resident_bytes,
        feature_major_input_resident_bytes,
        row_major_output_resident_bytes,
        packed_total_resident_bytes,
        floating_reference_total_resident_bytes,
        packed_logical_weight_stream_bytes_per_call,
        floating_reference_logical_weight_stream_bytes_per_call,
        logical_activation_operand_bytes_per_call,
        logical_minimum_output_write_bytes_per_call,
        packed_minimum_logical_bytes_per_call,
        floating_reference_minimum_logical_bytes_per_call,
        scope: "Resident bytes count one weight representation, one feature-major input, and one row-major output. Minimum logical bytes count one weight stream per batch tile, every activation operand use, and one final output write; allocator metadata, cache-line amplification, cache hits/misses, prefetch, and intermediate accumulator traffic are excluded.".into(),
    })
}

fn validate_request(request: &QwenInt4KernelSmokeRequest) -> Result<(), QwenInt4KernelError> {
    if request.schema_version != QWEN_INT4_KERNEL_REQUEST_SCHEMA_VERSION {
        return Err(QwenInt4KernelError::UnsupportedSchemaVersion {
            expected: QWEN_INT4_KERNEL_REQUEST_SCHEMA_VERSION,
            actual: request.schema_version,
        });
    }
    if request.study_id.trim().is_empty() {
        return Err(QwenInt4KernelError::InvalidField("study_id"));
    }
    if request.checkpoint.model_id.trim().is_empty()
        || request.checkpoint.model_revision.trim().is_empty()
        || !is_lower_hex_256(&request.checkpoint.expected_sha256)
    {
        return Err(QwenInt4KernelError::InvalidField("checkpoint"));
    }
    let actual_file_bytes = request.checkpoint.path.metadata()?.len();
    if actual_file_bytes != request.checkpoint.expected_file_bytes {
        return Err(QwenInt4KernelError::CheckpointSizeMismatch {
            expected: request.checkpoint.expected_file_bytes,
            actual: actual_file_bytes,
        });
    }
    if request.quality_evidence.path.metadata()?.len() == 0
        || !is_lower_hex_256(&request.quality_evidence.expected_sha256)
        || request.quality_evidence.candidate.trim().is_empty()
        || request.quality_evidence.scope.trim().is_empty()
    {
        return Err(QwenInt4KernelError::InvalidField("quality_evidence"));
    }
    if request.benchmark.group_size != GROUP_SIZE {
        return Err(QwenInt4KernelError::UnsupportedGroupSize(
            request.benchmark.group_size,
        ));
    }
    if request.benchmark.thread_count != 1 {
        return Err(QwenInt4KernelError::InvalidField("benchmark.thread_count"));
    }
    if request.benchmark.warmup_iterations == 0 || request.benchmark.measured_iterations < 3 {
        return Err(QwenInt4KernelError::InvalidField("benchmark.iterations"));
    }
    if request.benchmark.require_release_build && cfg!(debug_assertions) {
        return Err(QwenInt4KernelError::ReleaseBuildRequired);
    }
    if !request
        .correctness
        .maximum_dequantized_weight_absolute_error
        .is_finite()
        || request
            .correctness
            .maximum_dequantized_weight_absolute_error
            < 0.0
        || !request
            .correctness
            .maximum_dequantized_weight_rmse
            .is_finite()
        || request.correctness.maximum_dequantized_weight_rmse < 0.0
        || !request
            .correctness
            .maximum_output_absolute_error
            .is_finite()
        || request.correctness.maximum_output_absolute_error < 0.0
        || !request.correctness.maximum_output_rmse.is_finite()
        || request.correctness.maximum_output_rmse < 0.0
    {
        return Err(QwenInt4KernelError::InvalidField("correctness"));
    }
    if request.tensors.len() != 3 {
        return Err(QwenInt4KernelError::InvalidField("tensors"));
    }
    let expected_families = BTreeSet::from([
        QwenTensorFamily::AttentionOutput,
        QwenTensorFamily::MlpGate,
        QwenTensorFamily::MlpUp,
    ]);
    let actual_families = request
        .tensors
        .iter()
        .map(|tensor| tensor.family)
        .collect::<BTreeSet<_>>();
    if actual_families != expected_families {
        return Err(QwenInt4KernelError::InvalidField("tensors.family"));
    }
    for tensor in &request.tensors {
        if tensor.name.trim().is_empty()
            || tensor.expected_dtype != "BF16"
            || tensor.expected_rows == 0
            || tensor.expected_columns == 0
            || tensor.expected_columns % GROUP_SIZE != 0
            || !is_lower_hex_256(&tensor.expected_source_bytes_blake3)
        {
            return Err(QwenInt4KernelError::InvalidField("tensors.pin"));
        }
    }
    Ok(())
}

fn measure_tensor(
    request: &QwenInt4KernelSmokeRequest,
    tensor: &QwenTensorPin,
    tensor_index: u64,
) -> Result<TensorKernelMeasurement, QwenInt4KernelError> {
    let load_start = Instant::now();
    let loaded = load_bf16_tensor(&request.checkpoint.path, tensor)?;
    let source_load_seconds = load_start.elapsed().as_secs_f64();
    let source_bytes_blake3 = blake3::hash(&loaded.raw_bytes).to_hex().to_string();
    if source_bytes_blake3 != tensor.expected_source_bytes_blake3 {
        return Err(QwenInt4KernelError::TensorChecksumMismatch {
            tensor: tensor.name.clone(),
            expected: tensor.expected_source_bytes_blake3.clone(),
            actual: source_bytes_blake3,
        });
    }

    let pack_start = Instant::now();
    let packed = PackedInt4Matrix::pack_group8(
        &loaded.weights,
        tensor.expected_rows,
        tensor.expected_columns,
        request.benchmark.scale_storage,
    )?;
    let pack_seconds = pack_start.elapsed().as_secs_f64();
    let reference_weights = floating_group8_qdq(
        &loaded.weights,
        tensor.expected_rows,
        tensor.expected_columns,
        request.benchmark.scale_storage,
    )?;
    let packed_dequantized_weights = packed.dequantize();
    let (maximum_dequantized_weight_absolute_error, dequantized_weight_rmse) =
        error_metrics(&packed_dequantized_weights, &reference_weights);
    let packed_dequantized_weight_checksum_blake3 = checksum_f32(&packed_dequantized_weights);
    let floating_qdq_weight_checksum_blake3 = checksum_f32(&reference_weights);
    drop(packed_dequantized_weights);
    let input = deterministic_input(
        tensor.expected_columns,
        request.benchmark.seed ^ tensor_index.wrapping_mul(0x9e37_79b9_7f4a_7c15),
    );
    let input_checksum_blake3 = checksum_f32(&input);
    let mut packed_output = vec![0.0_f32; tensor.expected_rows];
    let mut reference_output = vec![0.0_f32; tensor.expected_rows];
    packed.matvec_into(&input, &mut packed_output)?;
    floating_matvec_into(
        &reference_weights,
        tensor.expected_rows,
        tensor.expected_columns,
        &input,
        &mut reference_output,
    );
    let correctness = correctness_measurement(
        &packed_output,
        &reference_output,
        packed_dequantized_weight_checksum_blake3,
        floating_qdq_weight_checksum_blake3,
        maximum_dequantized_weight_absolute_error,
        dequantized_weight_rmse,
        &request.correctness,
    );
    if !correctness.passed {
        return Err(QwenInt4KernelError::CorrectnessThresholdFailed {
            tensor: tensor.name.clone(),
            maximum_absolute_error: correctness.maximum_absolute_error,
            rmse: correctness.rmse,
        });
    }

    for _ in 0..request.benchmark.warmup_iterations {
        packed.matvec_into(black_box(&input), black_box(&mut packed_output))?;
        floating_matvec_into(
            black_box(&reference_weights),
            tensor.expected_rows,
            tensor.expected_columns,
            black_box(&input),
            black_box(&mut reference_output),
        );
        black_box(&packed_output);
        black_box(&reference_output);
    }
    let mut packed_timings = Vec::with_capacity(request.benchmark.measured_iterations);
    let mut reference_timings = Vec::with_capacity(request.benchmark.measured_iterations);
    for iteration in 0..request.benchmark.measured_iterations {
        if iteration % 2 == 0 {
            packed_timings.push(time_packed(&packed, &input, &mut packed_output)?);
            reference_timings.push(time_floating(
                &reference_weights,
                tensor.expected_rows,
                tensor.expected_columns,
                &input,
                &mut reference_output,
            ));
        } else {
            reference_timings.push(time_floating(
                &reference_weights,
                tensor.expected_rows,
                tensor.expected_columns,
                &input,
                &mut reference_output,
            ));
            packed_timings.push(time_packed(&packed, &input, &mut packed_output)?);
        }
    }

    let parameters =
        u64::try_from(loaded.weights.len()).map_err(|_| QwenInt4KernelError::DimensionOverflow)?;
    let source_bytes = parameters
        .checked_mul(2)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let code_bytes = to_u64(packed.code_bytes())?;
    let scale_bytes = to_u64(packed.scale_bytes())?;
    let packed_bytes = code_bytes
        .checked_add(scale_bytes)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let input_bytes = to_u64(input.len())?
        .checked_mul(4)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let output_bytes = to_u64(tensor.expected_rows)?
        .checked_mul(4)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let packed_logical_bytes = packed_bytes
        .checked_add(input_bytes)
        .and_then(|value| value.checked_add(output_bytes))
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let reference_weight_bytes = parameters
        .checked_mul(4)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let reference_logical_bytes = reference_weight_bytes
        .checked_add(input_bytes)
        .and_then(|value| value.checked_add(output_bytes))
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let packed_scalar = timing_measurement(packed_timings, packed_logical_bytes);
    let floating_qdq_scalar_reference =
        timing_measurement(reference_timings, reference_logical_bytes);
    let raw_speed_ratio_reference_over_packed =
        floating_qdq_scalar_reference.median_seconds / packed_scalar.median_seconds;
    Ok(TensorKernelMeasurement {
        family: tensor.family,
        tensor_name: tensor.name.clone(),
        source_dtype: "BF16".into(),
        rows: tensor.expected_rows,
        columns: tensor.expected_columns,
        parameter_count: parameters,
        source_bytes_blake3: tensor.expected_source_bytes_blake3.clone(),
        input_checksum_blake3,
        packed_checksum_blake3: packed.checksum_blake3(),
        source_load_seconds,
        pack_seconds,
        storage: StorageMeasurement {
            source_bfloat16_bytes: source_bytes,
            packed_code_bytes: code_bytes,
            group_scale_bytes: scale_bytes,
            total_packed_bytes: packed_bytes,
            scale_overhead_fraction_of_codes: scale_bytes as f64 / code_bytes as f64,
            scale_fraction_of_packed_storage: scale_bytes as f64 / packed_bytes as f64,
            packed_fraction_of_source_bfloat16: packed_bytes as f64 / source_bytes as f64,
            logical_packed_weight_bytes_read_per_output: to_u64(
                packed.logical_bytes_read_per_output(),
            )?,
            logical_f32_qdq_weight_bytes_read_per_output: to_u64(tensor.expected_columns)?
                .checked_mul(4)
                .ok_or(QwenInt4KernelError::DimensionOverflow)?,
            logical_input_bytes_if_read_once_per_matvec: input_bytes,
            logical_output_write_bytes_per_matvec: output_bytes,
        },
        correctness,
        packed_scalar,
        floating_qdq_scalar_reference,
        raw_speed_ratio_reference_over_packed,
        raw_time_ratio_packed_over_reference: 1.0 / raw_speed_ratio_reference_over_packed,
        boundary: "Single-thread scalar packed decode plus steady-state matvec versus single-thread scalar f32 QDQ steady-state matvec; one-shot quantization and packing time is reported separately and excluded from both timing distributions. No BLAS, vLLM, SIMD intrinsic, GPU, or provider control.".into(),
    })
}

fn time_packed(
    packed: &PackedInt4Matrix,
    input: &[f32],
    output: &mut [f32],
) -> Result<f64, QwenInt4KernelError> {
    let start = Instant::now();
    packed.matvec_into(black_box(input), black_box(output))?;
    black_box(output);
    Ok(start.elapsed().as_secs_f64())
}

#[cfg(target_arch = "aarch64")]
fn time_aarch64_neon(
    packed: &PackedInt4Matrix,
    input: &[f32],
    output: &mut [f32],
) -> Result<f64, QwenInt4KernelError> {
    let start = Instant::now();
    packed.matvec_aarch64_neon_into(black_box(input), black_box(output))?;
    black_box(output);
    Ok(start.elapsed().as_secs_f64())
}

fn time_packed_batch(
    packed: &PackedInt4Matrix,
    input: &[f32],
    batch_size: usize,
    batch_tile_size: usize,
    output: &mut [f32],
) -> Result<f64, QwenInt4KernelError> {
    let start = Instant::now();
    packed.batch_matmul_feature_major_into(
        black_box(input),
        batch_size,
        batch_tile_size,
        black_box(output),
    )?;
    black_box(output);
    Ok(start.elapsed().as_secs_f64())
}

#[allow(clippy::too_many_arguments)]
fn time_floating_batch(
    weights: &[f32],
    rows: usize,
    columns: usize,
    input: &[f32],
    batch_size: usize,
    batch_tile_size: usize,
    output: &mut [f32],
) -> Result<f64, QwenInt4KernelError> {
    let start = Instant::now();
    floating_qdq_batch_matmul_feature_major_into(
        black_box(weights),
        rows,
        columns,
        black_box(input),
        batch_size,
        batch_tile_size,
        black_box(output),
    )?;
    black_box(output);
    Ok(start.elapsed().as_secs_f64())
}

fn time_floating(
    weights: &[f32],
    rows: usize,
    columns: usize,
    input: &[f32],
    output: &mut [f32],
) -> f64 {
    let start = Instant::now();
    floating_matvec_into(
        black_box(weights),
        rows,
        columns,
        black_box(input),
        black_box(output),
    );
    black_box(output);
    start.elapsed().as_secs_f64()
}

fn floating_matvec_into(
    weights: &[f32],
    rows: usize,
    columns: usize,
    input: &[f32],
    output: &mut [f32],
) {
    debug_assert_eq!(weights.len(), rows * columns);
    debug_assert_eq!(input.len(), columns);
    debug_assert_eq!(output.len(), rows);
    for (row, output_value) in weights.chunks_exact(columns).zip(output.iter_mut()) {
        let mut sum = 0.0_f32;
        for (weight, input_value) in row.iter().zip(input) {
            sum += weight * input_value;
        }
        *output_value = sum;
    }
}

fn timing_measurement(mut timings: Vec<f64>, logical_bytes_per_call: u64) -> TimingMeasurement {
    timings.sort_by(f64::total_cmp);
    let minimum_seconds = timings[0];
    let median_seconds = if timings.len() % 2 == 0 {
        let upper = timings.len() / 2;
        (timings[upper - 1] + timings[upper]) / 2.0
    } else {
        timings[timings.len() / 2]
    };
    TimingMeasurement {
        iterations: timings.len(),
        minimum_seconds,
        median_seconds,
        logical_bytes_per_call,
        best_logical_effective_bandwidth_gbps: logical_bytes_per_call as f64
            / minimum_seconds
            / 1_000_000_000.0,
        median_logical_effective_bandwidth_gbps: logical_bytes_per_call as f64
            / median_seconds
            / 1_000_000_000.0,
    }
}

fn correctness_measurement(
    packed: &[f32],
    reference: &[f32],
    packed_dequantized_weight_checksum_blake3: String,
    floating_qdq_weight_checksum_blake3: String,
    maximum_dequantized_weight_absolute_error: f64,
    dequantized_weight_rmse: f64,
    thresholds: &CorrectnessThresholds,
) -> KernelCorrectnessMeasurement {
    let (maximum_absolute_error, rmse) = error_metrics(packed, reference);
    let packed_output_checksum_blake3 = checksum_f32(packed);
    let floating_reference_output_checksum_blake3 = checksum_f32(reference);
    let checksum_match = packed_output_checksum_blake3 == floating_reference_output_checksum_blake3;
    KernelCorrectnessMeasurement {
        packed_dequantized_weight_checksum_blake3,
        floating_qdq_weight_checksum_blake3,
        maximum_dequantized_weight_absolute_error,
        dequantized_weight_rmse,
        packed_output_checksum_blake3,
        floating_reference_output_checksum_blake3,
        maximum_absolute_error,
        rmse,
        checksum_match,
        passed: maximum_dequantized_weight_absolute_error
            <= thresholds.maximum_dequantized_weight_absolute_error
            && dequantized_weight_rmse <= thresholds.maximum_dequantized_weight_rmse
            && maximum_absolute_error <= thresholds.maximum_output_absolute_error
            && rmse <= thresholds.maximum_output_rmse,
    }
}

fn error_metrics(actual: &[f32], expected: &[f32]) -> (f64, f64) {
    debug_assert_eq!(actual.len(), expected.len());
    let mut maximum_absolute_error = 0.0_f64;
    let mut squared_error = 0.0_f64;
    for (actual, expected) in actual.iter().zip(expected) {
        let error = f64::from(*actual) - f64::from(*expected);
        maximum_absolute_error = maximum_absolute_error.max(error.abs());
        squared_error += error * error;
    }
    (
        maximum_absolute_error,
        (squared_error / actual.len() as f64).sqrt(),
    )
}

fn aggregate_measurements(measurements: &[TensorKernelMeasurement]) -> AggregateKernelMeasurement {
    let parameter_count = measurements
        .iter()
        .map(|measurement| measurement.parameter_count)
        .sum();
    let source_bfloat16_bytes = measurements
        .iter()
        .map(|measurement| measurement.storage.source_bfloat16_bytes)
        .sum();
    let total_packed_bytes = measurements
        .iter()
        .map(|measurement| measurement.storage.total_packed_bytes)
        .sum();
    let summed_packed_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.packed_scalar.median_seconds)
        .sum();
    let summed_floating_reference_median_seconds = measurements
        .iter()
        .map(|measurement| measurement.floating_qdq_scalar_reference.median_seconds)
        .sum();
    AggregateKernelMeasurement {
        tensor_count: measurements.len(),
        parameter_count,
        source_bfloat16_bytes,
        total_packed_bytes,
        summed_packed_median_seconds,
        summed_floating_reference_median_seconds,
        raw_speed_ratio_reference_over_packed: summed_floating_reference_median_seconds
            / summed_packed_median_seconds,
        raw_time_ratio_packed_over_reference: summed_packed_median_seconds
            / summed_floating_reference_median_seconds,
        all_correctness_checks_passed: measurements
            .iter()
            .all(|measurement| measurement.correctness.passed),
    }
}

fn aggregate_batch_frontier(
    request: &QwenInt4BatchFrontierRequest,
    measurements: &[TensorBatchFrontierMeasurement],
) -> Result<Vec<AggregateBatchFrontierPoint>, QwenInt4KernelError> {
    request
        .batch_sizes
        .iter()
        .map(|batch_size| {
            let points = measurements
                .iter()
                .map(|measurement| {
                    measurement
                        .points
                        .iter()
                        .find(|point| point.batch_size == *batch_size)
                        .ok_or(QwenInt4KernelError::MissingBatchPoint(*batch_size))
                })
                .collect::<Result<Vec<_>, _>>()?;
            let multiply_accumulate_terms = points.iter().try_fold(0_u64, |total, point| {
                checked_add_u64(total, point.work.packed_multiply_accumulate_terms)
            })?;
            let summed_packed_median_seconds = points
                .iter()
                .map(|point| point.packed_weight_stationary.median_seconds)
                .sum::<f64>();
            let summed_floating_reference_median_seconds = points
                .iter()
                .map(|point| {
                    point
                        .floating_qdq_weight_stationary_reference
                        .median_seconds
                })
                .sum::<f64>();
            let raw_speed_ratio_reference_over_packed =
                summed_floating_reference_median_seconds / summed_packed_median_seconds;
            Ok(AggregateBatchFrontierPoint {
                batch_size: *batch_size,
                tensor_count: points.len(),
                multiply_accumulate_terms,
                summed_packed_median_seconds,
                summed_floating_reference_median_seconds,
                raw_speed_ratio_reference_over_packed,
                raw_time_ratio_packed_over_reference: 1.0 / raw_speed_ratio_reference_over_packed,
                packed_faster: raw_speed_ratio_reference_over_packed > 1.0,
                all_work_counts_equal: points.iter().all(|point| point.work.exact_work_count_equal),
                all_correctness_checks_passed: points.iter().all(|point| point.correctness.passed),
            })
        })
        .collect()
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SafetensorsTensorHeader {
    dtype: String,
    shape: Vec<usize>,
    data_offsets: [u64; 2],
}

struct LoadedBfloat16Tensor {
    raw_bytes: Vec<u8>,
    weights: Vec<f32>,
}

fn load_bf16_tensor(
    path: &Path,
    pin: &QwenTensorPin,
) -> Result<LoadedBfloat16Tensor, QwenInt4KernelError> {
    let mut file = File::open(path)?;
    let file_bytes = file.metadata()?.len();
    let mut length_bytes = [0_u8; 8];
    file.read_exact(&mut length_bytes)?;
    let header_bytes = u64::from_le_bytes(length_bytes);
    if header_bytes == 0 || header_bytes > MAX_SAFETENSORS_HEADER_BYTES {
        return Err(QwenInt4KernelError::InvalidSafetensorsHeaderLength(
            header_bytes,
        ));
    }
    let data_base = 8_u64
        .checked_add(header_bytes)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if data_base > file_bytes {
        return Err(QwenInt4KernelError::SafetensorsOffsetOutOfBounds);
    }
    let mut header = vec![
        0_u8;
        usize::try_from(header_bytes)
            .map_err(|_| QwenInt4KernelError::DimensionOverflow)?
    ];
    file.read_exact(&mut header)?;
    let root = serde_json::from_slice::<serde_json::Value>(&header)?;
    let value = root
        .as_object()
        .and_then(|entries| entries.get(&pin.name))
        .ok_or_else(|| QwenInt4KernelError::TensorNotFound(pin.name.clone()))?;
    let tensor = serde_json::from_value::<SafetensorsTensorHeader>(value.clone())?;
    if tensor.dtype != pin.expected_dtype {
        return Err(QwenInt4KernelError::TensorDtypeMismatch {
            tensor: pin.name.clone(),
            expected: pin.expected_dtype.clone(),
            actual: tensor.dtype,
        });
    }
    let expected_shape = [pin.expected_rows, pin.expected_columns];
    if tensor.shape.as_slice() != expected_shape {
        return Err(QwenInt4KernelError::TensorShapeMismatch {
            tensor: pin.name.clone(),
            expected: expected_shape.to_vec(),
            actual: tensor.shape,
        });
    }
    let [start, end] = tensor.data_offsets;
    if start > end {
        return Err(QwenInt4KernelError::SafetensorsOffsetOutOfBounds);
    }
    let absolute_start = data_base
        .checked_add(start)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let absolute_end = data_base
        .checked_add(end)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if absolute_end > file_bytes {
        return Err(QwenInt4KernelError::SafetensorsOffsetOutOfBounds);
    }
    let expected_elements = pin
        .expected_rows
        .checked_mul(pin.expected_columns)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    let expected_bytes = expected_elements
        .checked_mul(2)
        .ok_or(QwenInt4KernelError::DimensionOverflow)?;
    if end - start
        != u64::try_from(expected_bytes).map_err(|_| QwenInt4KernelError::DimensionOverflow)?
    {
        return Err(QwenInt4KernelError::TensorByteLengthMismatch {
            tensor: pin.name.clone(),
            expected: expected_bytes,
            actual: usize::try_from(end - start)
                .map_err(|_| QwenInt4KernelError::DimensionOverflow)?,
        });
    }
    file.seek(SeekFrom::Start(absolute_start))?;
    let mut raw_bytes = vec![0_u8; expected_bytes];
    file.read_exact(&mut raw_bytes)?;
    let weights = raw_bytes
        .chunks_exact(2)
        .map(|bytes| bf16_bits_to_f32(u16::from_le_bytes([bytes[0], bytes[1]])))
        .collect();
    Ok(LoadedBfloat16Tensor { raw_bytes, weights })
}

fn quantized_code(value: f32, scale: f32) -> i8 {
    (value / scale).round_ties_even().clamp(-7.0, 7.0) as i8
}

fn encode_signed_int4(value: i8) -> u8 {
    (value as u8) & 0x0f
}

fn decode_signed_int4(value: u8) -> i8 {
    ((value << 4) as i8) >> 4
}

fn f32_to_bf16_bits(value: f32) -> u16 {
    let bits = value.to_bits();
    let rounding_bias = 0x7fff + ((bits >> 16) & 1);
    ((bits.wrapping_add(rounding_bias)) >> 16) as u16
}

fn bf16_bits_to_f32(bits: u16) -> f32 {
    f32::from_bits(u32::from(bits) << 16)
}

fn deterministic_input(length: usize, seed: u64) -> Vec<f32> {
    let mut state = if seed == 0 {
        0x6a09_e667_f3bc_c909
    } else {
        seed
    };
    (0..length)
        .map(|_| {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            let unit = (state >> 40) as f32 / ((1_u32 << 24) - 1) as f32;
            unit * 2.0 - 1.0
        })
        .collect()
}

fn checksum_f32(values: &[f32]) -> String {
    let mut hasher = blake3::Hasher::new();
    for value in values {
        hasher.update(&value.to_le_bytes());
    }
    hasher.finalize().to_hex().to_string()
}

fn host_identity(benchmark_thread_count: usize) -> HostIdentity {
    let cpu_model = command_output("sysctl", &["-n", "machdep.cpu.brand_string"])
        .or_else(read_first_cpu_model)
        .unwrap_or_else(|| "unknown".into());
    let operating_system = command_output("uname", &["-srv"])
        .unwrap_or_else(|| format!("{} unknown", std::env::consts::OS));
    HostIdentity {
        hostname: command_output("hostname", &[]).unwrap_or_else(|| "unknown".into()),
        operating_system,
        architecture: std::env::consts::ARCH.into(),
        cpu_model,
        available_parallelism: std::thread::available_parallelism()
            .map(usize::from)
            .unwrap_or(1),
        benchmark_thread_count,
        rust_profile: if cfg!(debug_assertions) {
            "debug".into()
        } else {
            "release".into()
        },
    }
}

fn compiler_identity() -> CompilerIdentity {
    CompilerIdentity {
        rustc_verbose: command_output("rustc", &["-Vv"]).unwrap_or_else(|| "unknown".into()),
        target_architecture: std::env::consts::ARCH.into(),
        target_operating_system: std::env::consts::OS.into(),
        release_profile: !cfg!(debug_assertions),
        explicit_simd_intrinsics_used: false,
        auto_vectorization_inspected: false,
    }
}

fn command_output(program: &str, arguments: &[&str]) -> Option<String> {
    let output = Command::new(program).args(arguments).output().ok()?;
    if !output.status.success() {
        return None;
    }
    let value = String::from_utf8(output.stdout).ok()?;
    let value = value.trim();
    (!value.is_empty()).then(|| value.to_owned())
}

fn read_first_cpu_model() -> Option<String> {
    let cpu_info = std::fs::read_to_string("/proc/cpuinfo").ok()?;
    cpu_info.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        matches!(key.trim(), "model name" | "Hardware")
            .then(|| value.trim().to_owned())
            .filter(|value| !value.is_empty())
    })
}

fn report_content_id(
    schema_version: u32,
    result: &QwenInt4KernelSmokeResult,
) -> Result<String, QwenInt4KernelError> {
    serialized_content_id(schema_version, result)
}

fn batch_frontier_content_id(
    schema_version: u32,
    result: &QwenInt4BatchFrontierResult,
) -> Result<String, QwenInt4KernelError> {
    serialized_content_id(schema_version, result)
}

fn aarch64_neon_content_id(
    schema_version: u32,
    result: &QwenInt4Aarch64NeonResult,
) -> Result<String, QwenInt4KernelError> {
    serialized_content_id(schema_version, result)
}

fn serialized_content_id<T: Serialize>(
    schema_version: u32,
    result: &T,
) -> Result<String, QwenInt4KernelError> {
    let bytes = serde_json::to_vec(&(schema_version, result))?;
    Ok(blake3::hash(&bytes).to_hex().to_string())
}

fn to_u64(value: usize) -> Result<u64, QwenInt4KernelError> {
    u64::try_from(value).map_err(|_| QwenInt4KernelError::DimensionOverflow)
}

fn checked_mul_u64(left: u64, right: u64) -> Result<u64, QwenInt4KernelError> {
    left.checked_mul(right)
        .ok_or(QwenInt4KernelError::DimensionOverflow)
}

fn checked_add_u64(left: u64, right: u64) -> Result<u64, QwenInt4KernelError> {
    left.checked_add(right)
        .ok_or(QwenInt4KernelError::DimensionOverflow)
}

fn is_lower_hex_256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[derive(Debug, Error)]
pub enum QwenInt4KernelError {
    #[error("unsupported request schema version {actual}; expected {expected}")]
    UnsupportedSchemaVersion { expected: u32, actual: u32 },
    #[error("invalid field: {0}")]
    InvalidField(&'static str),
    #[error("only signed group-8 INT4 is supported, got group size {0}")]
    UnsupportedGroupSize(usize),
    #[error("matrix dimensions overflow")]
    DimensionOverflow,
    #[error("invalid matrix shape {rows}x{columns}")]
    InvalidMatrixShape { rows: usize, columns: usize },
    #[error("weight count mismatch: expected {expected}, got {actual}")]
    WeightCountMismatch { expected: usize, actual: usize },
    #[error("matrix contains a non-finite weight")]
    NonFiniteWeight,
    #[error("input width mismatch: expected {expected}, got {actual}")]
    InputWidthMismatch { expected: usize, actual: usize },
    #[error("output height mismatch: expected {expected}, got {actual}")]
    OutputHeightMismatch { expected: usize, actual: usize },
    #[error("batch size must be positive")]
    InvalidBatchSize,
    #[error("batch tile size must be positive")]
    InvalidBatchTileSize,
    #[error("feature-major batch input count mismatch: expected {expected}, got {actual}")]
    BatchInputCountMismatch { expected: usize, actual: usize },
    #[error("row-major batch output count mismatch: expected {expected}, got {actual}")]
    BatchOutputCountMismatch { expected: usize, actual: usize },
    #[error("checkpoint size mismatch: expected {expected}, got {actual}")]
    CheckpointSizeMismatch { expected: u64, actual: u64 },
    #[error("base request checksum mismatch: expected {expected}, got {actual}")]
    BaseRequestChecksumMismatch { expected: String, actual: String },
    #[error("scalar smoke report checksum mismatch: expected {expected}, got {actual}")]
    ScalarReportChecksumMismatch { expected: String, actual: String },
    #[error("batch frontier is missing batch size {0}")]
    MissingBatchPoint(usize),
    #[error("release build is required for benchmark measurement")]
    ReleaseBuildRequired,
    #[error("target architecture mismatch: expected {expected}, got {actual}")]
    TargetArchitectureMismatch { expected: String, actual: String },
    #[error("invalid safetensors header length {0}")]
    InvalidSafetensorsHeaderLength(u64),
    #[error("safetensors offset is outside the file")]
    SafetensorsOffsetOutOfBounds,
    #[error("tensor not found: {0}")]
    TensorNotFound(String),
    #[error("tensor {tensor} dtype mismatch: expected {expected}, got {actual}")]
    TensorDtypeMismatch {
        tensor: String,
        expected: String,
        actual: String,
    },
    #[error("tensor {tensor} shape mismatch: expected {expected:?}, got {actual:?}")]
    TensorShapeMismatch {
        tensor: String,
        expected: Vec<usize>,
        actual: Vec<usize>,
    },
    #[error("tensor {tensor} byte length mismatch: expected {expected}, got {actual}")]
    TensorByteLengthMismatch {
        tensor: String,
        expected: usize,
        actual: usize,
    },
    #[error("tensor {tensor} checksum mismatch: expected {expected}, got {actual}")]
    TensorChecksumMismatch {
        tensor: String,
        expected: String,
        actual: String,
    },
    #[error(
        "tensor {tensor} failed correctness thresholds: max error {maximum_absolute_error}, RMSE {rmse}"
    )]
    CorrectnessThresholdFailed {
        tensor: String,
        maximum_absolute_error: f64,
        rmse: f64,
    },
    #[error("I/O failed: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON failed: {0}")]
    Json(#[from] serde_json::Error),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn bfloat16_rounding_uses_round_to_nearest_even() {
        assert_eq!(f32_to_bf16_bits(1.0), 0x3f80);
        assert_eq!(bf16_bits_to_f32(0x3f80), 1.0);
        assert_eq!(f32_to_bf16_bits(f32::from_bits(0x3f80_8000)), 0x3f80);
        assert_eq!(f32_to_bf16_bits(f32::from_bits(0x3f81_8000)), 0x3f82);
    }

    #[test]
    fn signed_nibble_round_trip_covers_full_storage_range() {
        for value in -8_i8..=7 {
            assert_eq!(decode_signed_int4(encode_signed_int4(value)), value);
        }
    }

    #[test]
    fn serialized_content_identity_covers_schema_and_result() {
        let result = serde_json::json!({"study_id": "neon-v1", "samples": 31});
        let content_id = serialized_content_id(1, &result).expect("identity must serialize");

        assert_eq!(
            content_id,
            serialized_content_id(1, &result).expect("identity must be deterministic")
        );
        assert_ne!(
            content_id,
            serialized_content_id(2, &result).expect("schema identity must serialize")
        );
        assert_ne!(
            content_id,
            serialized_content_id(
                1,
                &serde_json::json!({"study_id": "neon-v1", "samples": 30}),
            )
            .expect("mutated result identity must serialize")
        );
    }

    #[test]
    fn aarch64_neon_report_scope_matches_prediction_contract() {
        assert_eq!(
            aarch64_neon_predictive_scope(),
            PredictiveMeasurementScope {
                model_id: "Qwen/Qwen3-0.6B".into(),
                model_revision: "c1899de289a04d12100db370d81485cdf75e47ca".into(),
                workload_id: "qwen3-0.6b-layer0-o-gate-up-packed-matvec".into(),
                workload_revision:
                    "8c9f38791aea1e54178371a6aa41c0da5dda4c39b2640c778bbb044bfbd4165d".into(),
                context_regime: "decode-batch1-three-layer0-tensors".into(),
                hardware_id: "Apple M4 Pro".into(),
                hardware_revision: "Mac16,7-Apple-M4-Pro-14c-48GB".into(),
                software_id: "foundry-qwen-int4-aarch64-neon".into(),
                software_revision: "qwen-int4-aarch64-neon-v1".into(),
                intervention_id: "aarch64-neon-group8-packed-matvec".into(),
                intervention_revision: "v1".into(),
                metric_id: "summed_three_tensor_median_seconds".into(),
                metric_unit: "seconds".into(),
                higher_is_better: false,
            }
        );
    }

    #[test]
    fn safetensors_loader_checks_dtype_shape_offsets_and_bytes() {
        let data = [0x80_u8, 0x3f].repeat(8);
        let path = write_safetensors("BF16", &[1, 8], [0, 16], &data);
        let pin = tensor_pin();

        let loaded = load_bf16_tensor(&path, &pin).expect("valid pinned tensor must load");
        assert_eq!(loaded.raw_bytes, data);
        assert_eq!(loaded.weights, vec![1.0; 8]);

        let mut wrong_shape = pin.clone();
        wrong_shape.expected_rows = 2;
        wrong_shape.expected_columns = 4;
        assert!(matches!(
            load_bf16_tensor(&path, &wrong_shape),
            Err(QwenInt4KernelError::TensorShapeMismatch { .. })
        ));
        std::fs::remove_file(path).expect("temporary tensor must be removable");

        let wrong_dtype = write_safetensors("F16", &[1, 8], [0, 16], &data);
        assert!(matches!(
            load_bf16_tensor(&wrong_dtype, &pin),
            Err(QwenInt4KernelError::TensorDtypeMismatch { .. })
        ));
        std::fs::remove_file(wrong_dtype).expect("temporary tensor must be removable");

        let bad_offset = write_safetensors("BF16", &[1, 8], [0, 18], &data);
        assert!(matches!(
            load_bf16_tensor(&bad_offset, &pin),
            Err(QwenInt4KernelError::SafetensorsOffsetOutOfBounds)
        ));
        std::fs::remove_file(bad_offset).expect("temporary tensor must be removable");
    }

    fn tensor_pin() -> QwenTensorPin {
        QwenTensorPin {
            family: QwenTensorFamily::AttentionOutput,
            name: "tensor".into(),
            expected_dtype: "BF16".into(),
            expected_rows: 1,
            expected_columns: 8,
            expected_source_bytes_blake3: "0".repeat(64),
        }
    }

    fn write_safetensors(
        dtype: &str,
        shape: &[usize],
        data_offsets: [u64; 2],
        data: &[u8],
    ) -> PathBuf {
        let header = serde_json::to_vec(&serde_json::json!({
            "tensor": {
                "dtype": dtype,
                "shape": shape,
                "data_offsets": data_offsets
            }
        }))
        .expect("header must serialize");
        let mut bytes = Vec::with_capacity(8 + header.len() + data.len());
        bytes.extend_from_slice(&(header.len() as u64).to_le_bytes());
        bytes.extend_from_slice(&header);
        bytes.extend_from_slice(data);
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock must be after epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("qwen-int4-safetensors-{nonce}"));
        std::fs::write(&path, bytes).expect("temporary tensor must be writable");
        path
    }
}
