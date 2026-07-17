#!/usr/bin/env python3
"""Bounded source/oracle gate for the SM89 persistent exact-W4 candidate."""
import hashlib
import json
import math
import shutil
import struct
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/root/.cache/glm47flash-awq-ab31d120')
SOURCE = HERE / 'persistent_moe_executor_sm89.cu'
HIDDEN, WIDTH, EXPERTS, TOPK, LAYERS, SMS = 2048, 1536, 64, 4, tuple(range(1, 47)), 142

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def header(path):
    with path.open('rb') as f:
        return json.loads(f.read(struct.unpack('<Q', f.read(8))[0]))

def nibble(word, column):
    value = (word >> (4 * (column & 7))) & 15
    return value - 16 if value >= 8 else value

def w4_dot(packed, scales, row, values):
    return sum(nibble(packed[row * ((len(values) + 7) // 8) + col // 8], col) * scales[row][col // 32] * value
               for col, value in enumerate(values))

def expert(x, weights):
    gate = [w4_dot(weights['gate'], weights['gate_scale'], row, x) for row in range(len(weights['gate_scale']))]
    up = [w4_dot(weights['up'], weights['up_scale'], row, x) for row in range(len(weights['up_scale']))]
    middle = [g / (1.0 + math.exp(-g)) * u for g, u in zip(gate, up)]
    return [w4_dot(weights['down'], weights['down_scale'], row, middle) for row in range(len(weights['down_scale']))]

def reference(xs, ids, route_weights, weights):
    result = [[0.0] * len(xs[0]) for _ in xs]
    for token, x in enumerate(xs):
        for slot in range(TOPK):
            value = expert(x, weights[ids[token * TOPK + slot]])
            for col, number in enumerate(value): result[token][col] += route_weights[token * TOPK + slot] * number
    return result

def persistent(xs, ids, route_weights, weights):
    result = [[0.0] * len(xs[0]) for _ in xs]
    queues = {}
    for assignment, chosen in enumerate(ids): queues.setdefault(chosen, []).append(assignment)
    for chosen in sorted(queues):
        for assignment in queues[chosen]:
            token = assignment // TOPK
            value = expert(xs[token], weights[chosen])
            for col, number in enumerate(value): result[token][col] += route_weights[assignment] * number
    return result

def maximum_difference(left, right):
    return max(abs(a - b) for lhs, rhs in zip(left, right) for a, b in zip(lhs, rhs))

def bf16(raw):
    return struct.unpack('<f', struct.pack('<I', raw << 16))[0]

def fixture_weights():
    index = json.loads((ROOT / 'model.safetensors.index.json').read_text())['weight_map']
    headers, files, bases, all_weights = {}, {}, {}, {}
    for expert_id in range(EXPERTS):
        current = {}
        for projection, rows, columns in (('gate_proj', WIDTH, HIDDEN), ('up_proj', WIDTH, HIDDEN), ('down_proj', HIDDEN, WIDTH)):
            packed_name = f'model.layers.1.mlp.experts.{expert_id}.{projection}.weight_packed'
            scale_name = f'model.layers.1.mlp.experts.{expert_id}.{projection}.weight_scale'
            filename = index[packed_name]
            if filename not in headers: headers[filename] = header(ROOT / filename)
            item = headers[filename]
            if filename not in files: files[filename] = (ROOT / filename).open('rb')
            stream = files[filename]
            if filename not in bases:
                with (ROOT / filename).open('rb') as source: bases[filename] = 8 + struct.unpack('<Q', source.read(8))[0]
            packed_offset = item[packed_name]['data_offsets'][0]
            scale_offset = item[scale_name]['data_offsets'][0]
            packed_columns, scale_columns = columns // 8, columns // 32
            words, scales = [], []
            for row in range(8):
                stream.seek(bases[filename] + packed_offset + 4 * row * packed_columns)
                words.append(struct.unpack('<I', stream.read(4))[0])
                stream.seek(bases[filename] + scale_offset + 2 * row * scale_columns)
                scales.append([bf16(struct.unpack('<H', stream.read(2))[0])])
            key = projection.split('_')[0]
            current[key] = words
            current[key + '_scale'] = scales
        all_weights[expert_id] = current
    for stream in files.values(): stream.close()
    return all_weights

def exact_checkpoint_contract():
    config = json.loads((ROOT / 'config.json').read_text())
    index = json.loads((ROOT / 'model.safetensors.index.json').read_text())['weight_map']
    cache, shapes, missing = {}, set(), []
    for layer in LAYERS:
        for expert_id in range(EXPERTS):
            for projection, shape in (('gate_proj', [WIDTH, HIDDEN // 8]), ('up_proj', [WIDTH, HIDDEN // 8]), ('down_proj', [HIDDEN, WIDTH // 8])):
                name = f'model.layers.{layer}.mlp.experts.{expert_id}.{projection}.weight_packed'
                filename = index.get(name)
                if not filename: missing.append(name); continue
                if filename not in cache: cache[filename] = header(ROOT / filename)
                item = cache[filename][name]
                shapes.add(tuple(item['shape']))
                if item['shape'] != shape: missing.append(name + ':shape')
    return {'checkpoint_root': str(ROOT), 'config_sha256': sha(ROOT / 'config.json'), 'index_sha256': sha(ROOT / 'model.safetensors.index.json'), 'revision': 'ab31d120fbe79988fe2a0259993cf3c222aa8881', 'layers_bound': [1, 46], 'layer_count': len(LAYERS), 'experts_per_layer': EXPERTS, 'top_k': config['num_experts_per_tok'], 'packed_shapes': sorted(shapes), 'missing_or_mismatched': len(missing), 'valid': not missing and config['hidden_size'] == HIDDEN and config['moe_intermediate_size'] == WIDTH and config['n_routed_experts'] == EXPERTS}

def oracle_case(name, tokens, ids):
    weights = fixture_weights(); xs = [[((token + col * 3) % 9 - 4) / 8 for col in range(8)] for token in range(tokens)]
    route = [((slot + 1) / 10) for slot in range(tokens * TOPK)]
    ref, queued = reference(xs, ids, route, weights), persistent(xs, ids, route, weights)
    difference = maximum_difference(ref, queued)
    return {'name': name, 'tokens': tokens, 'assignments': len(ids), 'histogram': dict(sorted(Counter(ids).items())), 'max_abs_difference': difference, 'tolerance': 1e-12, 'pass': difference <= 1e-12}

def compile_log():
    nvcc = shutil.which('nvcc')
    output = HERE / 'compile.log'
    if not nvcc:
        record = {'status': 'typed_compiler_boundary', 'stage': 'sm89_cuda_compile', 'exit_code': 127, 'command': ['nvcc', '-std=c++17', '-arch=sm_89', '-c', str(SOURCE)], 'stdout': '', 'stderr': 'nvcc is unavailable on this $0 host; no SM89 binary or timing was produced.', 'source_sha256': sha(SOURCE)}
    else:
        run = subprocess.run([nvcc, '-std=c++17', '-arch=sm_89', '-c', str(SOURCE), '-o', str(HERE / 'persistent_moe_executor_sm89.o')], text=True, capture_output=True)
        record = {'status': 'pass' if run.returncode == 0 else 'typed_compiler_failure', 'stage': 'sm89_cuda_compile', 'exit_code': run.returncode, 'command': run.args, 'stdout': run.stdout[-8000:], 'stderr': run.stderr[-8000:], 'source_sha256': sha(SOURCE)}
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    return record

def main():
    contract = exact_checkpoint_contract()
    cases = [oracle_case('duplicate_single_expert_c16', 16, [0] * 64), oracle_case('empty_experts_balanced_c16', 16, list(range(64))), oracle_case('representative_skew_c32', 32, [(i * 7) % 64 if i % 5 else 3 for i in range(128)])]
    oracle = {'schema_version': 1, 'evidence_label': 'executed_cpu_semantic_oracle_with_current_checkpoint_W4_samples_and_source_bound_exact_geometry', 'candidate_source_sha256': sha(SOURCE), 'checkpoint_contract': contract, 'fixture': 'first eight rows and first group-32 scale of each layer-1 expert projection are read from current packed W4 checkpoint bytes; the miniature computes eight dimensions only, preserving int4 nibble unpack, group32 scale selection, SiLU, top4 route weighting, grouping, duplicate, and empty-expert semantics. It is not a target-GPU performance result.', 'cases': cases, 'all_pass': contract['valid'] and all(case['pass'] for case in cases)}
    (HERE / 'numerical_oracle.json').write_text(json.dumps(oracle, indent=2, sort_keys=True) + '\n')
    compile_result = compile_log()
    combined_share, moe_share, required = .12374 + .03177, .12374, .08936
    gate = {'schema_version': 1, 'candidate': {'kind': 'one persistent assignment-queue W4 executor', 'source': str(SOURCE), 'source_sha256': sha(SOURCE), 'sm89': {'blocks': SMS, 'threads_per_block': 256, 'dynamic_shared_bytes': 0, 'max_shared_bytes_per_block': 99 * 1024, 'static_resource_status': 'shared-memory legal; register count requires nvcc/PTXAS'}, 'geometry': {'layers': [1, 46], 'c16_assignments': 64, 'c32_assignments': 128, 'experts': 64, 'top_k': 4, 'hidden': HIDDEN, 'moe_width': WIDTH}, 'useful_work_per_assignment_flops': 6 * HIDDEN * WIDTH, 'useful_weight_bytes_per_assignment_ideal': 3 * HIDDEN * WIDTH / 2}, 'measurement': {'status': 'not_measured', 'reason': compile_result['status'], 'elapsed_ms': None, 'p50_ms': None, 'p95_ms': None, 'registers_per_thread': None}, 'derived_gate': {'l40s_fused_moe_share': moe_share, 'l40s_routing_sort_share': .03177, 'combined_share': combined_share, 'required_c16_wall_reduction': required, 'minimum_combined_speedup': 2.349, 'minimum_fused_moe_only_speedup': 3.77, 'reported_share_recalculation': {'combined': combined_share / (combined_share - required), 'fused_only': moe_share / (moe_share - required)}, 'floor_source': 'director-approved economic gate; reported trace shares are rounded summed-work attribution and not endpoint critical-path proof', 'formula': 'wall reduction = component_share * (1 - 1 / speedup)'}, 'decision': {'status': 'typed_in_scope_compiler_boundary', 'nomination': 'none', 'reason': 'The CPU oracle passes exact scheduling semantics, but no nvcc/CUDA device exists on this host, so no SM89 binary, registers, timing, or component speedup exists. The director floors of 2.349x combined / 3.77x fused-only remain unmet rather than inferred.'}}
    (HERE / 'gate.json').write_text(json.dumps(gate, indent=2, sort_keys=True) + '\n')

if __name__ == '__main__': main()
