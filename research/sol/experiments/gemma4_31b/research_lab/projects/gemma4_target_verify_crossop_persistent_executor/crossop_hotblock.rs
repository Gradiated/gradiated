use std::time::Instant;

const ROWS: usize = 384;
const REQUESTS: usize = 32;
const ROWS_PER_REQUEST: usize = 12;
const FP8_WIDTH: usize = 8192;
const EPSILON: f64 = 1.0e-6;
const FP8_MAX: f32 = 448.0;

#[derive(Clone, Copy)]
struct Geometry {
    q_heads: usize,
    kv_heads: usize,
    head_dim: usize,
    qkv_width: usize,
}

const LOCAL: Geometry = Geometry {
    q_heads: 32,
    kv_heads: 16,
    head_dim: 256,
    qkv_width: 16384,
};

const GLOBAL: Geometry = Geometry {
    q_heads: 32,
    kv_heads: 4,
    head_dim: 512,
    qkv_width: 20480,
};

fn source_value(row: usize, col: usize, salt: usize) -> f32 {
    let code = (row * 131 + col * 17 + salt * 43) % 2047;
    (code as f32 - 1023.0) / 509.0
}

fn fp8_abi_input_value(row: usize, col: usize) -> f32 {
    match row {
        0 => 0.0,
        1 => 2.0_f32.powi(-20),
        2 => {
            if col % 3 == 0 {
                4096.0
            } else if col % 3 == 1 {
                -4096.0
            } else {
                0.0
            }
        }
        _ => source_value(row, col, 7),
    }
}

fn bf16_round(value: f32) -> f32 {
    let bits = value.to_bits();
    let rounding_bias = 0x7fff + ((bits >> 16) & 1);
    f32::from_bits((bits.wrapping_add(rounding_bias)) & 0xffff0000)
}

fn rms_factor(values: &[f32]) -> f32 {
    let sum = values
        .iter()
        .map(|value| {
            let value = *value as f64;
            value * value
        })
        .sum::<f64>();
    (1.0 / (sum / values.len() as f64 + EPSILON).sqrt()) as f32
}

fn rope_in_place(head: &mut [f32], position: usize) {
    let half = head.len() / 2;
    for pair in 0..half {
        let exponent = -2.0 * pair as f64 / head.len() as f64;
        let angle = position as f64 * 10000.0_f64.powf(exponent);
        let (sin, cos) = angle.sin_cos();
        let x = head[2 * pair] as f64;
        let y = head[2 * pair + 1] as f64;
        head[2 * pair] = bf16_round((x * cos - y * sin) as f32);
        head[2 * pair + 1] = bf16_round((x * sin + y * cos) as f32);
    }
}

fn staged_normalize_then_rope(values: &mut [f32], heads: usize, head_dim: usize, position: usize) {
    for head in 0..heads {
        let range = head * head_dim..(head + 1) * head_dim;
        let factor = rms_factor(&values[range.clone()]);
        for value in &mut values[range] {
            *value = bf16_round(*value * factor);
        }
    }
    for head in 0..heads {
        let range = head * head_dim..(head + 1) * head_dim;
        rope_in_place(&mut values[range], position);
    }
}

fn fused_head_normalize_rope(input: &[f32], output: &mut [f32], position: usize) {
    let factor = rms_factor(input);
    for (dst, src) in output.iter_mut().zip(input) {
        *dst = bf16_round(*src * factor);
    }
    rope_in_place(output, position);
}

fn decode_e4m3fn(code: u8) -> Option<f32> {
    let sign = if code & 0x80 == 0 { 1.0 } else { -1.0 };
    let exponent = ((code >> 3) & 0x0f) as i32;
    let mantissa = (code & 0x07) as i32;
    if exponent == 15 && mantissa == 7 {
        return None;
    }
    let magnitude = if exponent == 0 {
        (mantissa as f32 / 8.0) * 2.0_f32.powi(-6)
    } else {
        (1.0 + mantissa as f32 / 8.0) * 2.0_f32.powi(exponent - 7)
    };
    Some(sign * magnitude)
}

fn encode_e4m3fn(value: f32) -> u8 {
    let clipped = value.clamp(-FP8_MAX, FP8_MAX);
    let mut best_code = 0_u8;
    let mut best_distance = f32::INFINITY;
    for code in 0_u8..=u8::MAX {
        if let Some(candidate) = decode_e4m3fn(code) {
            let distance = (candidate - clipped).abs();
            if distance < best_distance || (distance == best_distance && code & 1 == 0) {
                best_code = code;
                best_distance = distance;
            }
        }
    }
    best_code
}

fn hash_bytes(bytes: impl Iterator<Item = u8>) -> u64 {
    bytes.fold(0xcbf29ce484222325_u64, |hash, byte| {
        (hash ^ byte as u64).wrapping_mul(0x100000001b3)
    })
}

fn production_small_batch_quantize(value: f32, scale: f32) -> u8 {
    let scale_inv = 1.0 / scale;
    let scaled = value * scale_inv;
    let saturated = if scaled.is_nan() {
        FP8_MAX
    } else {
        scaled.clamp(-FP8_MAX, FP8_MAX)
    };
    encode_e4m3fn(saturated)
}

fn fp8_stock() -> (Vec<f32>, Vec<u8>, u64) {
    let mut normalized = vec![0.0_f32; ROWS * FP8_WIDTH];
    let mut scales = vec![0.0_f32; ROWS];
    let mut codes = vec![0_u8; ROWS * FP8_WIDTH];
    for row in 0..ROWS {
        let range = row * FP8_WIDTH..(row + 1) * FP8_WIDTH;
        let mut input = Vec::with_capacity(FP8_WIDTH);
        for col in 0..FP8_WIDTH {
            input.push(fp8_abi_input_value(row, col));
        }
        let factor = rms_factor(&input);
        for (dst, src) in normalized[range.clone()].iter_mut().zip(input) {
            *dst = bf16_round(src * factor);
        }
    }
    for row in 0..ROWS {
        let range = row * FP8_WIDTH..(row + 1) * FP8_WIDTH;
        let max_abs = normalized[range.clone()]
            .iter()
            .fold(0.0_f32, |maximum, value| maximum.max(value.abs()));
        let scale = max_abs / FP8_MAX;
        scales[row] = scale;
        for (code, value) in codes[range.clone()].iter_mut().zip(&normalized[range]) {
            *code = production_small_batch_quantize(*value, scale);
        }
    }
    let consumer_hash = hash_bytes(
        codes.iter().copied().chain(
            scales
                .iter()
                .flat_map(|value| value.to_bits().to_le_bytes()),
        ),
    );
    (scales, codes, consumer_hash)
}

fn fp8_request_executor() -> (Vec<f32>, Vec<u8>, u64) {
    let mut scales = vec![0.0_f32; ROWS];
    let mut codes = vec![0_u8; ROWS * FP8_WIDTH];
    for request in 0..REQUESTS {
        for local_row in 0..ROWS_PER_REQUEST {
            let row = request * ROWS_PER_REQUEST + local_row;
            let range = row * FP8_WIDTH..(row + 1) * FP8_WIDTH;
            let mut input = Vec::with_capacity(FP8_WIDTH);
            for col in 0..FP8_WIDTH {
                input.push(fp8_abi_input_value(row, col));
            }
            let factor = rms_factor(&input);
            let mut max_abs = 0.0_f32;
            for value in &mut input {
                *value = bf16_round(*value * factor);
                max_abs = max_abs.max(value.abs());
            }
            let scale = max_abs / FP8_MAX;
            scales[row] = scale;
            for (code, value) in codes[range].iter_mut().zip(input) {
                let scale_inv = 1.0 / scale;
                let scaled = value * scale_inv;
                let saturated = if scaled.is_nan() {
                    FP8_MAX
                } else {
                    scaled.max(-FP8_MAX).min(FP8_MAX)
                };
                *code = encode_e4m3fn(saturated);
            }
        }
    }
    let consumer_hash = hash_bytes(
        codes.iter().copied().chain(
            scales
                .iter()
                .flat_map(|value| value.to_bits().to_le_bytes()),
        ),
    );
    (scales, codes, consumer_hash)
}

struct ConsumerResult {
    output_mismatches: usize,
    max_abs_error: f32,
    stock_hash: u64,
    candidate_hash: u64,
    logical_weight_storage_bytes: usize,
    nonzero_weight_elements: usize,
    output_elements: usize,
}

fn hash_update_u16(hash: u64, value: u16) -> u64 {
    value
        .to_le_bytes()
        .iter()
        .copied()
        .fold(hash, |state, byte| {
            (state ^ byte as u64).wrapping_mul(0x100000001b3)
        })
}

fn sparse_weight_k(output_col: usize, tap: usize) -> usize {
    (output_col
        .wrapping_mul(131)
        .wrapping_add(tap.wrapping_mul(2053)))
        % FP8_WIDTH
}

fn build_full_column_major_weight(output_width: usize) -> (Vec<u8>, Vec<f32>, usize) {
    let mut weight = vec![encode_e4m3fn(0.0); FP8_WIDTH * output_width];
    let mut scales = vec![0.0_f32; output_width];
    let mut nonzero = 0;
    for output_col in 0..output_width {
        scales[output_col] = (1 + output_col % 17) as f32 * 2.0_f32.powi(-10);
        for tap in 0..4 {
            let k = sparse_weight_k(output_col, tap);
            let sign = if (output_col + tap) % 2 == 0 {
                1.0
            } else {
                -1.0
            };
            weight[k + output_col * FP8_WIDTH] = encode_e4m3fn(sign * (tap + 1) as f32 / 2.0);
            nonzero += 1;
        }
    }
    (weight, scales, nonzero)
}

fn consume_gemma_qkv(
    activation: &[u8],
    activation_scales: &[f32],
    weight: &[u8],
    weight_scales: &[f32],
    output_width: usize,
) -> Vec<u16> {
    assert_eq!(activation.len(), ROWS * FP8_WIDTH);
    assert_eq!(activation_scales.len(), ROWS);
    assert_eq!(weight.len(), FP8_WIDTH * output_width);
    assert_eq!(weight_scales.len(), output_width);
    let mut output = vec![0_u16; ROWS * output_width];
    for row in 0..ROWS {
        for output_col in 0..output_width {
            let mut accumulator = 0.0_f32;
            for tap in 0..4 {
                let k = sparse_weight_k(output_col, tap);
                let activation_value = decode_e4m3fn(activation[row * FP8_WIDTH + k]).unwrap();
                let weight_value = decode_e4m3fn(weight[k + output_col * FP8_WIDTH]).unwrap();
                accumulator += activation_value * weight_value;
            }
            let value = accumulator * activation_scales[row] * weight_scales[output_col];
            output[row * output_width + output_col] = (bf16_round(value).to_bits() >> 16) as u16;
        }
    }
    output
}

fn gemma_qkv_consumer_pair(
    stock_activation: &[u8],
    stock_scales: &[f32],
    candidate_activation: &[u8],
    candidate_scales: &[f32],
    output_width: usize,
) -> ConsumerResult {
    let (weight, weight_scales, nonzero_weight_elements) =
        build_full_column_major_weight(output_width);
    let stock_output = consume_gemma_qkv(
        stock_activation,
        stock_scales,
        &weight,
        &weight_scales,
        output_width,
    );
    let candidate_output = consume_gemma_qkv(
        candidate_activation,
        candidate_scales,
        &weight,
        &weight_scales,
        output_width,
    );
    let mut output_mismatches = 0;
    let mut max_abs_error = 0.0_f32;
    let mut stock_hash = 0xcbf29ce484222325_u64;
    let mut candidate_hash = 0xcbf29ce484222325_u64;
    for (stock, candidate) in stock_output.iter().zip(&candidate_output) {
        if stock != candidate {
            output_mismatches += 1;
        }
        let stock_value = f32::from_bits((*stock as u32) << 16);
        let candidate_value = f32::from_bits((*candidate as u32) << 16);
        max_abs_error = max_abs_error.max((stock_value - candidate_value).abs());
        stock_hash = hash_update_u16(stock_hash, *stock);
        candidate_hash = hash_update_u16(candidate_hash, *candidate);
    }
    ConsumerResult {
        output_mismatches,
        max_abs_error,
        stock_hash,
        candidate_hash,
        logical_weight_storage_bytes: weight.len(),
        nonzero_weight_elements,
        output_elements: stock_output.len(),
    }
}

struct QkvResult {
    q: Vec<f32>,
    k: Vec<f32>,
    v: Vec<f32>,
}

fn qkv_stock(geometry: Geometry) -> QkvResult {
    let q_width = geometry.q_heads * geometry.head_dim;
    let kv_width = geometry.kv_heads * geometry.head_dim;
    assert_eq!(geometry.qkv_width, q_width + 2 * kv_width);
    let mut q = vec![0.0_f32; ROWS * q_width];
    let mut k = vec![0.0_f32; ROWS * kv_width];
    let mut v = vec![0.0_f32; ROWS * kv_width];
    for row in 0..ROWS {
        for col in 0..q_width {
            q[row * q_width + col] = source_value(row, col, 11);
        }
        for col in 0..kv_width {
            k[row * kv_width + col] = source_value(row, q_width + col, 11);
            v[row * kv_width + col] = bf16_round(source_value(row, q_width + kv_width + col, 11));
        }
    }
    for row in 0..ROWS {
        let position = 4096 + row % ROWS_PER_REQUEST;
        staged_normalize_then_rope(
            &mut q[row * q_width..(row + 1) * q_width],
            geometry.q_heads,
            geometry.head_dim,
            position,
        );
        staged_normalize_then_rope(
            &mut k[row * kv_width..(row + 1) * kv_width],
            geometry.kv_heads,
            geometry.head_dim,
            position,
        );
    }
    QkvResult { q, k, v }
}

fn qkv_request_executor(geometry: Geometry) -> QkvResult {
    let q_width = geometry.q_heads * geometry.head_dim;
    let kv_width = geometry.kv_heads * geometry.head_dim;
    let mut q = vec![0.0_f32; ROWS * q_width];
    let mut k = vec![0.0_f32; ROWS * kv_width];
    let mut v = vec![0.0_f32; ROWS * kv_width];
    for request in 0..REQUESTS {
        for local_row in 0..ROWS_PER_REQUEST {
            let row = request * ROWS_PER_REQUEST + local_row;
            let position = 4096 + local_row;
            for head in 0..geometry.q_heads {
                let source_offset = head * geometry.head_dim;
                let destination_offset = row * q_width + source_offset;
                let mut input = Vec::with_capacity(geometry.head_dim);
                for lane in 0..geometry.head_dim {
                    input.push(source_value(row, source_offset + lane, 11));
                }
                fused_head_normalize_rope(
                    &input,
                    &mut q[destination_offset..destination_offset + geometry.head_dim],
                    position,
                );
            }
            for head in 0..geometry.kv_heads {
                let source_offset = q_width + head * geometry.head_dim;
                let destination_offset = row * kv_width + head * geometry.head_dim;
                let mut input = Vec::with_capacity(geometry.head_dim);
                for lane in 0..geometry.head_dim {
                    input.push(source_value(row, source_offset + lane, 11));
                    v[destination_offset + lane] = bf16_round(source_value(
                        row,
                        q_width + kv_width + head * geometry.head_dim + lane,
                        11,
                    ));
                }
                fused_head_normalize_rope(
                    &input,
                    &mut k[destination_offset..destination_offset + geometry.head_dim],
                    position,
                );
            }
        }
    }
    QkvResult { q, k, v }
}

fn accepted_prefix_lengths() -> [usize; REQUESTS] {
    let mut lengths = [0_usize; REQUESTS];
    for (request, length) in lengths.iter_mut().enumerate() {
        *length = (request * 7 + 3) % (ROWS_PER_REQUEST + 1);
    }
    lengths
}

fn commit_mask(lengths: &[usize; REQUESTS]) -> Vec<u8> {
    let mut mask = vec![0_u8; ROWS];
    for request in 0..REQUESTS {
        for local_row in 0..lengths[request] {
            mask[request * ROWS_PER_REQUEST + local_row] = 1;
        }
    }
    mask
}

fn vector_mismatch(left: &[f32], right: &[f32]) -> (usize, f32) {
    left.iter()
        .zip(right)
        .fold((0_usize, 0.0_f32), |(count, max_abs), (a, b)| {
            let difference = (*a - *b).abs();
            (
                count + usize::from(a.to_bits() != b.to_bits()),
                max_abs.max(difference),
            )
        })
}

fn qkv_geometry_result(geometry: Geometry) -> (usize, f32, usize, u64, u128, u128) {
    let start = Instant::now();
    let stock = qkv_stock(geometry);
    let stock_elapsed = start.elapsed().as_micros();
    let start = Instant::now();
    let candidate = qkv_request_executor(geometry);
    let candidate_elapsed = start.elapsed().as_micros();
    let (q_mismatch, q_max_abs) = vector_mismatch(&stock.q, &candidate.q);
    let (k_mismatch, k_max_abs) = vector_mismatch(&stock.k, &candidate.k);
    let (v_mismatch, v_max_abs) = vector_mismatch(&stock.v, &candidate.v);
    let mask = commit_mask(&accepted_prefix_lengths());
    let row_width = geometry.kv_heads * geometry.head_dim;
    let mut visible_k = candidate.k.clone();
    let mut visible_v = candidate.v.clone();
    for (row, visible) in mask.iter().enumerate() {
        if *visible == 0 {
            visible_k[row * row_width..(row + 1) * row_width].fill(0.0);
            visible_v[row * row_width..(row + 1) * row_width].fill(0.0);
        }
    }
    let rejected_nonzero = mask
        .iter()
        .zip(
            visible_k
                .chunks_exact(row_width)
                .zip(visible_v.chunks_exact(row_width)),
        )
        .filter(|(visible, _)| **visible == 0)
        .filter(|(_, (k_row, v_row))| k_row.iter().chain(*v_row).any(|value| value.to_bits() != 0))
        .count();
    let hash = hash_bytes(
        candidate
            .q
            .iter()
            .chain(&visible_k)
            .chain(&visible_v)
            .flat_map(|value| value.to_bits().to_le_bytes())
            .chain(mask),
    );
    (
        q_mismatch + k_mismatch + v_mismatch,
        q_max_abs.max(k_max_abs).max(v_max_abs),
        rejected_nonzero,
        hash,
        stock_elapsed,
        candidate_elapsed,
    )
}

fn main() {
    assert_eq!(ROWS, REQUESTS * ROWS_PER_REQUEST);
    let start = Instant::now();
    let (stock_scales, stock_codes, stock_hash) = fp8_stock();
    let stock_fp8_us = start.elapsed().as_micros();
    let start = Instant::now();
    let (candidate_scales, candidate_codes, candidate_hash) = fp8_request_executor();
    let candidate_fp8_us = start.elapsed().as_micros();
    let scale_mismatches = stock_scales
        .iter()
        .zip(&candidate_scales)
        .filter(|(a, b)| a.to_bits() != b.to_bits())
        .count();
    let code_mismatches = stock_codes
        .iter()
        .zip(&candidate_codes)
        .filter(|(a, b)| a != b)
        .count();
    let start = Instant::now();
    let local_fp8_consumer = gemma_qkv_consumer_pair(
        &stock_codes,
        &stock_scales,
        &candidate_codes,
        &candidate_scales,
        LOCAL.qkv_width,
    );
    let local_fp8_consumer_us = start.elapsed().as_micros();
    let start = Instant::now();
    let global_fp8_consumer = gemma_qkv_consumer_pair(
        &stock_codes,
        &stock_scales,
        &candidate_codes,
        &candidate_scales,
        GLOBAL.qkv_width,
    );
    let global_fp8_consumer_us = start.elapsed().as_micros();
    let local = qkv_geometry_result(LOCAL);
    let global = qkv_geometry_result(GLOBAL);
    let accepted_rows: usize = accepted_prefix_lengths().iter().sum();
    let correct = scale_mismatches == 0
        && code_mismatches == 0
        && stock_hash == candidate_hash
        && local_fp8_consumer.output_mismatches == 0
        && local_fp8_consumer.max_abs_error == 0.0
        && local_fp8_consumer.stock_hash == local_fp8_consumer.candidate_hash
        && global_fp8_consumer.output_mismatches == 0
        && global_fp8_consumer.max_abs_error == 0.0
        && global_fp8_consumer.stock_hash == global_fp8_consumer.candidate_hash
        && local.0 == 0
        && local.1 == 0.0
        && local.2 == 0
        && global.0 == 0
        && global.1 == 0.0
        && global.2 == 0;
    println!(
        concat!(
            "{{\n",
            "  \"schema_version\": 1,\n",
            "  \"classification\": \"{}\",\n",
            "  \"evidence_label\": \"measured_cpu_reference\",\n",
            "  \"geometry\": {{\"rows\": {}, \"requests\": {}, \"rows_per_request\": {}, \"fp8_width\": {}}},\n",
            "  \"fp8_boundary\": {{\"scale_mismatches\": {}, \"code_mismatches\": {}, \"stock_consumer_hash\": \"{:016x}\", \"candidate_consumer_hash\": \"{:016x}\", \"stock_elapsed_us_descriptive\": {}, \"candidate_elapsed_us_descriptive\": {}}},\n",
            "  \"production_fp8_abi\": {{\"activation\": {{\"shape\": [384, 8192], \"strides\": [8192, 1], \"dtype\": \"E4M3FN\", \"scale_shape\": [384, 1], \"scale_dtype\": \"FP32\", \"scale_granularity\": \"per_token\", \"zero_row_scale_bits\": {}, \"zero_row_first_code\": {}}}, \"weight\": {{\"layout\": \"column_major\", \"dtype\": \"E4M3FN\", \"scale_dtype\": \"FP32\", \"scale_granularity\": \"per_output_channel\"}}, \"consumer\": \"sgl_kernel.fp8_scaled_mm -> Gemma4Attention.qkv_proj\", \"output_dtype\": \"BF16\"}},\n",
            "  \"local_fp8_qkv_consumer\": {{\"input_shape\": [384, 8192], \"weight_shape\": [8192, 16384], \"output_shape\": [384, 16384], \"output_elements\": {}, \"output_mismatches\": {}, \"max_abs_error\": {}, \"stock_output_hash\": \"{:016x}\", \"candidate_output_hash\": \"{:016x}\", \"logical_weight_storage_bytes\": {}, \"nonzero_fixture_weight_elements\": {}, \"elapsed_us_descriptive\": {}}},\n",
            "  \"global_fp8_qkv_consumer\": {{\"input_shape\": [384, 8192], \"weight_shape\": [8192, 20480], \"output_shape\": [384, 20480], \"output_elements\": {}, \"output_mismatches\": {}, \"max_abs_error\": {}, \"stock_output_hash\": \"{:016x}\", \"candidate_output_hash\": \"{:016x}\", \"logical_weight_storage_bytes\": {}, \"nonzero_fixture_weight_elements\": {}, \"elapsed_us_descriptive\": {}}},\n",
            "  \"local_qkv_boundary\": {{\"shape\": [384, 16384], \"mismatches\": {}, \"max_abs_error\": {}, \"rejected_slots_exposed\": {}, \"consumer_hash\": \"{:016x}\", \"stock_elapsed_us_descriptive\": {}, \"candidate_elapsed_us_descriptive\": {}}},\n",
            "  \"global_qkv_boundary\": {{\"shape\": [384, 20480], \"mismatches\": {}, \"max_abs_error\": {}, \"rejected_slots_exposed\": {}, \"consumer_hash\": \"{:016x}\", \"stock_elapsed_us_descriptive\": {}, \"candidate_elapsed_us_descriptive\": {}}},\n",
            "  \"commit\": {{\"accepted_rows\": {}, \"provisional_rows\": {}, \"rejected_rows\": {}, \"rejected_rows_zeroed\": true, \"acceptance_input\": \"synthetic_request_prefix_lengths\"}},\n",
            "  \"timing_scope\": \"descriptive CPU only; no H200 or endpoint performance claim\"\n",
            "}}\n"
        ),
        if correct { "cpu_reference_pass" } else { "cpu_reference_fail" },
        ROWS,
        REQUESTS,
        ROWS_PER_REQUEST,
        FP8_WIDTH,
        scale_mismatches,
        code_mismatches,
        stock_hash,
        candidate_hash,
        stock_fp8_us,
        candidate_fp8_us,
        stock_scales[0].to_bits(),
        stock_codes[0],
        local_fp8_consumer.output_elements,
        local_fp8_consumer.output_mismatches,
        local_fp8_consumer.max_abs_error,
        local_fp8_consumer.stock_hash,
        local_fp8_consumer.candidate_hash,
        local_fp8_consumer.logical_weight_storage_bytes,
        local_fp8_consumer.nonzero_weight_elements,
        local_fp8_consumer_us,
        global_fp8_consumer.output_elements,
        global_fp8_consumer.output_mismatches,
        global_fp8_consumer.max_abs_error,
        global_fp8_consumer.stock_hash,
        global_fp8_consumer.candidate_hash,
        global_fp8_consumer.logical_weight_storage_bytes,
        global_fp8_consumer.nonzero_weight_elements,
        global_fp8_consumer_us,
        local.0,
        local.1,
        local.2,
        local.3,
        local.4,
        local.5,
        global.0,
        global.1,
        global.2,
        global.3,
        global.4,
        global.5,
        accepted_rows,
        ROWS,
        ROWS - accepted_rows,
    );
    if !correct {
        std::process::exit(2);
    }
}
