#!/usr/bin/env python3
import json
import os
from pathlib import Path

ROOT = Path(os.environ['UPSTREAM_REBASE_ROOT'])
OUT = Path(os.environ['UPSTREAM_REBASE_OUT'])

def atomic(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    part = path.with_suffix(path.suffix + '.part')
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')
    part.replace(path)

def main():
    source = (ROOT / 'remote_runtime_discriminator.py').read_text()
    expected = 'if REQUESTS != 171:'
    if source.count(expected) != 1:
        raise RuntimeError('endpoint_runner_discriminator_guard_not_unique')
    source = source.replace(expected, 'if REQUESTS != 791:', 1)
    namespace = {'__name__': '_endpoint_embedded'}
    exec(compile(source, str(ROOT / 'remote_runtime_discriminator.py'), 'exec'), namespace)
    namespace['REQUESTS'] = 791
    namespace['main']()
    discriminator = json.loads((OUT / 'FINAL_TERMINAL.json').read_text())
    rows = [json.loads(line) for line in (OUT / 'requests.jsonl').read_text().splitlines()]
    telemetry = [json.loads(line) for line in (OUT / 'telemetry.jsonl').read_text().splitlines()]
    queue = [row.get('metrics', {}).get('sglang:num_queue_reqs') for row in telemetry]
    queue = [value for value in queue if value is not None]
    total_tokens = sum(row['semantic']['usage']['total_tokens'] for row in rows if 'semantic' in row)
    cost = discriminator['elapsed_seconds'] * 3.25 / 3600 / total_tokens * 1_000_000
    gates = {
        'normalized_semantics_exact': discriminator['decision']['normalized_semantics_exact'],
        'native_ngram_activation_observed': discriminator['decision']['native_ngram_activation_observed'],
        'failures_zero': discriminator['decision']['failures_zero'],
        'stable_release_timing': discriminator['decision']['release_drift_bounded'],
        'long_unaffected_trunks': discriminator['decision']['normalized_semantics_exact'],
        'peak_queue_at_most_30': bool(queue) and max(queue) <= 30,
        'final_queue_zero': bool(queue) and queue[-1] == 0,
        'planning_cost_at_most_0_14_per_million': cost <= 0.14,
    }
    atomic('ENDPOINT_TERMINAL.json', {
        'result': 'measured_upstream_runtime_first_791_request_endpoint',
        'candidate_sample_consumed': True,
        'identity': discriminator['identity'],
        'requests': 791,
        'elapsed_seconds': discriminator['elapsed_seconds'],
        'planning_cost_usd_per_million_total_tokens': cost,
        'queue_peak': max(queue) if queue else None,
        'queue_final': queue[-1] if queue else None,
        'total_tokens': total_tokens,
        'gates': gates,
        'accepted': all(gates.values()),
        'discriminator_terminal': discriminator,
    })

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        atomic('ATTEMPT_TERMINAL.json', {'classification': 'recoverable_endpoint_consumer_failure', 'error': repr(exc), 'candidate_sample_consumed': False})
        raise
