#!/usr/bin/env python3
"""Measure Kimi streams with server token counts, never SSE event counts."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

MODEL_REVISION = 'd9e99b0792a5e93b78ea9bea62a68167e36ddd9e'
RUNTIME_REVISION = 'afcd7d6b487a9cbe73e25941971b4cc107e6f9ae'


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def output_present(event):
    for choice in event.get('choices', []):
        delta = choice.get('delta') or {}
        if any(delta.get(k) for k in ('content', 'reasoning_content', 'reasoning', 'tool_calls')):
            return True
        if any(item.get('token_ids') for item in choice.get('internal_content', [])):
            return True
    return False


def internal_tokens(event):
    groups = [item['token_ids'] for choice in event.get('choices', [])
              for item in choice.get('internal_content', []) if 'token_ids' in item]
    return sum(len(ids) for ids in groups) if groups else None


def usage_count(usage, key):
    value = (usage or {}).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def measure_events(events, started, finished, minimum_output=512, floor=80):
    first = last = None
    first_count = None
    first_internal_count = None
    progress = 0
    id_count = 0
    have_ids = False
    usage = None
    done = False
    event_count = 0
    gaps = []
    row = {'ok': False, 'slo_met': False, 'started_at_monotonic': started,
           'finished_at_monotonic': finished, 'elapsed_s': finished - started}
    try:
        for now, event in events:
            if event == '[DONE]':
                done = True
                continue
            if event.get('error'):
                raise ValueError('server returned stream error')
            current_usage = event.get('usage')
            if current_usage:
                usage = current_usage
            cumulative = usage_count(current_usage, 'completion_tokens')
            ids = internal_tokens(event)
            if ids is not None:
                have_ids = True
                id_count += ids
            advanced = cumulative is not None and cumulative > progress
            if advanced or output_present(event):
                if first is None:
                    first = now
                    first_count = cumulative if advanced else None
                    first_internal_count = ids
                elif last is not None:
                    gaps.append(now - last)
                last = now
                event_count += 1
            if cumulative is not None:
                if cumulative < progress:
                    raise ValueError('completion usage decreased during stream')
                progress = cumulative
        count = usage_count(usage, 'completion_tokens')
        prompt_count = usage_count(usage, 'prompt_tokens')
        if not done or first is None or last is None or count is None or prompt_count is None:
            raise ValueError('missing output, final token usage, or [DONE]')
        if count < minimum_output:
            raise ValueError(f'output too short for gate: {count} < {minimum_output}')
        if count <= 1 or last <= first:
            raise ValueError('fewer than two timed token events')
        duration = last - first
        nominal = (count - 1) / duration
        lower_bound = count / (finished - started)
        exact_first = first_count is not None and 0 < first_count < count
        decode = (count - first_count) / duration if exact_first else None
        gated = decode if exact_first else lower_bound
        row.update(ok=True, slo_met=gated >= floor, completion_tokens=count,
                   prompt_tokens=prompt_count, usage=usage, ttft_s=first - started,
                   decode_duration_s=duration, nominal_decode_tps=nominal,
                   first_event_tokens=first_count, burst_adjusted_decode_tps=decode,
                   end_to_end_tps=lower_bound, gate_tps=gated,
                   gate_basis='counted-first-burst' if exact_first else 'end-to-end-lower-bound',
                   stream_events=event_count,
                   stream_gap_p95_s=percentile(gaps, .95) if gaps else None,
                   stream_gap_max_s=max(gaps, default=0),
                   first_output_at_monotonic=first, last_output_at_monotonic=last)
    except (TypeError, ValueError, KeyError) as error:
        row['error'] = str(error)
    row.update(internal_token_occurrences=id_count if have_ids else None,
               first_event_internal_occurrences=first_internal_count,
               internal_occurrences_exceed_usage=(id_count > progress) if have_ids and progress else None)
    return row


def diagnostic_events(events, started, limit=2048):
    rows = []
    for now, event in events[:limit]:
        if event == '[DONE]':
            rows.append({'offset_s': now-started, 'done': True})
        else:
            rows.append({'offset_s': now-started, 'completion_tokens': usage_count(event.get('usage'), 'completion_tokens'),
                         'prompt_tokens': usage_count(event.get('usage'), 'prompt_tokens'),
                         'internal_token_occurrences': internal_tokens(event), 'has_output': output_present(event),
                         'server_error': bool(event.get('error'))})
    return {'events': rows, 'truncated': len(events) > limit}


def post_json(url, payload, key, timeout):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    return urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(payload).encode(),
                                  headers=headers), timeout=timeout)


def normalize_native_event(event):
    if event.get('error'):
        return event
    meta = event.get('meta_info')
    if not isinstance(meta, dict):
        raise ValueError('native stream is missing meta_info')
    usage = {'prompt_tokens': usage_count(meta, 'prompt_tokens'),
             'completion_tokens': usage_count(meta, 'completion_tokens')}
    if usage_count(meta, 'cached_tokens') is not None:
        usage['prompt_tokens_details'] = {'cached_tokens': meta['cached_tokens']}
    return {'choices': [], 'usage': usage}


def request_once(args, fixture, deadline, minimum_output=None):
    started = time.monotonic()
    expires = min(deadline, started + args.request_timeout)
    payload = {'model': args.model, 'messages': fixture['messages'], 'stream': True,
               'max_tokens': args.output_tokens, 'temperature': args.temperature, 'top_p': args.top_p,
               'reasoning_effort': args.reasoning_effort, 'stream_options': {'include_usage': True}}
    if args.native_metrics:
        payload['stream_options'].update(continuous_usage_stats=True, include_internal_content=True)
    if args.ignore_eos:
        payload['ignore_eos'] = True
    protocol = getattr(args, 'protocol', 'chat')
    endpoint = '/v1/chat/completions'
    if protocol == 'generate':
        payload = {'input_ids': fixture['native_input_ids'], 'stream': True,
                   'sampling_params': {'max_new_tokens': args.output_tokens,
                                       'temperature': args.temperature, 'top_p': args.top_p,
                                       'skip_special_tokens': False}}
        if args.ignore_eos:
            payload['sampling_params']['ignore_eos'] = True
        endpoint = '/generate'
    events = []
    first = False
    try:
        remaining = expires - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('campaign deadline reached')
        with post_json(args.base_url.rstrip('/') + endpoint, payload, args.api_key, remaining) as response:
            while True:
                remaining = expires - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('absolute request deadline reached')
                response.fp.raw._sock.settimeout(min(args.idle_timeout, remaining) if first else remaining)
                line = response.readline()
                if not line:
                    break
                if not line.startswith(b'data:'):
                    continue
                raw = line[5:].strip()
                if raw == b'[DONE]':
                    events.append((time.monotonic(), '[DONE]'))
                    break
                event = json.loads(raw)
                if protocol == 'generate':
                    event = normalize_native_event(event)
                events.append((time.monotonic(), event))
                first = first or output_present(event) or bool(usage_count(event.get('usage'), 'completion_tokens'))
        row = measure_events(events, started, time.monotonic(),
                             args.min_output_tokens if minimum_output is None else minimum_output, args.floor_tps)
        if protocol == 'generate' and row['ok'] and row.get('prompt_tokens') != len(fixture['native_input_ids']):
            row.update(ok=False, slo_met=False, error='native prompt token usage differs from exact rendered input IDs')
    except Exception as error:
        row = {'ok': False, 'slo_met': False, 'error': type(error).__name__ + ': ' + str(error)[:200],
               'started_at_monotonic': started, 'finished_at_monotonic': time.monotonic(),
               'elapsed_s': time.monotonic() - started}
    row.update(fixture_id=fixture['id'], requested_prompt_tokens=fixture['target_tokens'],
               prepared_text_tokens=fixture.get('prepared_text_tokens'), reasoning_effort=args.reasoning_effort,
               protocol=protocol, counter_source='native-meta-info' if protocol == 'generate' else 'chat-usage')
    if protocol == 'generate':
        row['rendered_prompt_tokens'] = len(fixture['native_input_ids'])
        row['rendered_input_ids_sha256'] = hashlib.sha256(
            json.dumps(fixture['native_input_ids'], separators=(',', ':')).encode()).hexdigest()
    if getattr(args, 'diagnostic_events', False):
        row['stream_diagnostics'] = diagnostic_events(events, started)
    return row


def prepare_fixtures(args):
    if args.fixtures:
        fixtures = json.loads(args.fixtures.read_text())
        if not fixtures or any(not all(k in f for k in ('id', 'target_tokens', 'messages')) for f in fixtures):
            raise ValueError('fixtures must contain id, target_tokens and messages')
        return fixtures
    if not args.tokenizer_path:
        raise ValueError('use --tokenizer-path from the pinned model or a pretokenized --fixtures file')
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer_path), trust_remote_code=True,
                                             local_files_only=True)
    fixtures = []
    for target in args.prompt_tokens:
        for replica in range(args.fixtures_per_class):
            seed = args.seed + target + replica * 1000000
            rng = random.Random(seed)
            records = [f'Synthetic request {seed}. Analyze the following service log.\n']
            records.extend(f'Entry {i}: service {rng.choice(("api", "worker", "cache"))} processed '
                           f'{rng.randrange(100, 10000)} requests in {rng.randrange(1, 1000)} ms; '
                           f'status {rng.choice(("ok", "retry", "timeout"))}.\n' for i in range(target // 5))
            text = ''.join(records)
            ids = tokenizer.encode(text, add_special_tokens=False)[:target]
            text = tokenizer.decode(ids, skip_special_tokens=False)
            actual = len(tokenizer.encode(text, add_special_tokens=False))
            fixtures.append({'id': f'{target}-{replica}', 'target_tokens': target,
                             'prepared_text_tokens': actual, 'messages': [{'role': 'user', 'content': text}]})
    return fixtures


def interleave_fixtures(fixtures):
    groups = {}
    for fixture in fixtures:
        groups.setdefault(fixture['target_tokens'], []).append(fixture)
    return [group[index] for index in range(max(map(len, groups.values())))
            for group in groups.values() if index < len(group)]


def prepare_native_fixtures(args, fixtures, tokenizer=None):
    if tokenizer is None:
        if not args.tokenizer_path:
            raise ValueError('--protocol generate requires --tokenizer-path for exact Kimi chat rendering')
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer_path), trust_remote_code=True, local_files_only=True)
    prepared = []
    for fixture in fixtures:
        messages = fixture['messages']
        if (len(messages) != 1 or messages[0].get('role') != 'user'
                or not isinstance(messages[0].get('content'), str)
                or '<|kimi_image_placeholder|>' in messages[0]['content']):
            raise ValueError('native counter probe accepts one synthetic text-only user message per fixture')
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                            thinking=True, thinking_effort=args.reasoning_effort)
        if not isinstance(ids, list) or not ids or any(type(token) is not int or token < 0 for token in ids):
            raise ValueError('Kimi chat renderer did not return a nonempty list of input token IDs')
        prepared.append({**fixture, 'native_input_ids': ids,
                         'native_input_ids_sha256': hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()})
    return prepared


def summarize(rows, concurrency, trial):
    good = [r for r in rows if r['ok']]
    elapsed = max(r['finished_at_monotonic'] for r in rows) - min(r['started_at_monotonic'] for r in rows)
    rates = [r['gate_tps'] for r in good]
    return {'concurrency': concurrency, 'trial': trial, 'requests': len(rows), 'failures': len(rows)-len(good),
            'slo_met': bool(rows) and len(good) == len(rows) and all(r['slo_met'] for r in rows),
            'aggregate_output_tps': sum(r['completion_tokens'] for r in good) / max(elapsed, 1e-9),
            'elapsed_s': elapsed, 'gate_tps_min': min(rates, default=None),
            'gate_tps_p05': percentile(rates, .05) if rates else None,
            'gate_tps_p50': percentile(rates, .5) if rates else None,
            'ttft_p95_s': percentile([r['ttft_s'] for r in good], .95) if good else None,
            'rows': rows}


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--model', default='moonshotai/Kimi-K3.1-Pro')
    parser.add_argument('--protocol', choices=('chat', 'generate'), default='chat',
                        help='generate sends exact rendered Kimi input IDs to native /generate with authoritative counters')
    parser.add_argument('--label', required=True)
    parser.add_argument('--api-key-env', default='GRADIATED_RUNTIME_API_KEY')
    parser.add_argument('--tokenizer-path', type=Path, help='local pinned Kimi snapshot with custom tokenizer code')
    parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--prompt-tokens', default='2048,8192,32768')
    parser.add_argument('--fixtures-per-class', type=int, default=4)
    parser.add_argument('--concurrency', default='1,2,4,8,16,24,32')
    parser.add_argument('--requests-per-worker', type=int, default=3)
    parser.add_argument('--trials', type=int, default=3)
    parser.add_argument('--warmups', type=int, default=3)
    parser.add_argument('--output-tokens', type=int, default=512)
    parser.add_argument('--min-output-tokens', type=int, default=512)
    parser.add_argument('--floor-tps', type=float, default=80)
    parser.add_argument('--reasoning-effort', choices=('low', 'high', 'max'), default='max')
    parser.add_argument('--temperature', type=float, default=1.0)
    parser.add_argument('--top-p', type=float, default=.95)
    parser.add_argument('--native-metrics', action='store_true')
    parser.add_argument('--diagnostic-events', action='store_true', help='record bounded event times/counts without text or token IDs')
    parser.add_argument('--ignore-eos', action='store_true')
    parser.add_argument('--continue-after-failure', action='store_true')
    parser.add_argument('--request-timeout', type=float, default=600)
    parser.add_argument('--idle-timeout', type=float, default=30)
    parser.add_argument('--max-seconds', type=float, default=3600)
    parser.add_argument('--deadline-utc', help='absolute ISO8601 UTC deadline; bounds --max-seconds')
    parser.add_argument('--seed', type=int, default=314159)
    parser.add_argument('--hardware', default='8x NVIDIA B300 SXM6 AC')
    parser.add_argument('--runtime-revision', default=RUNTIME_REVISION)
    parser.add_argument('--model-revision', default=MODEL_REVISION)
    parser.add_argument('--config-json', type=Path, help='non-secret launch flags/arm metadata')
    parser.add_argument('--output', type=Path, default=Path('.agents/runtime/kimi-k31/probe.json'))
    args = parser.parse_args()
    args.api_key = os.environ.get(args.api_key_env, '')
    args.concurrency = [int(v) for v in args.concurrency.split(',')]
    args.prompt_tokens = [int(v) for v in args.prompt_tokens.split(',')]
    if (any(v <= 0 for v in args.concurrency + args.prompt_tokens)
            or min(args.trials, args.requests_per_worker, args.output_tokens, args.min_output_tokens,
                   args.fixtures_per_class) <= 0):
        parser.error('concurrency, prompt/output token counts, trials, requests and fixtures must be positive')
    if args.warmups < 0:
        parser.error('warmups must be nonnegative')
    if args.output_tokens < args.min_output_tokens:
        parser.error('output-tokens must cover min-output-tokens')
    if any(not math.isfinite(value) or value <= 0 for value in
           (args.request_timeout, args.idle_timeout, args.max_seconds)):
        parser.error('timeouts must be finite and positive')
    if (not math.isfinite(args.temperature) or not 0 <= args.temperature <= 2
            or not math.isfinite(args.top_p) or not 0 <= args.top_p <= 1):
        parser.error('temperature must be finite in [0, 2] and top-p finite in [0, 1]')
    if not math.isfinite(args.floor_tps) or args.floor_tps <= 0:
        parser.error('floor-tps must be finite and positive')
    deadline = time.monotonic() + args.max_seconds
    if args.deadline_utc:
        end = datetime.fromisoformat(args.deadline_utc.replace('Z', '+00:00'))
        if end.utcoffset() is None:
            parser.error('--deadline-utc requires a timezone')
        deadline = min(deadline, time.monotonic() + end.timestamp() - time.time())
    fixtures = interleave_fixtures(prepare_fixtures(args))
    if args.protocol == 'generate':
        fixtures = prepare_native_fixtures(args, fixtures)
    metadata = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items() if k != 'api_key'}
    metadata.update(started_utc=datetime.now(timezone.utc).isoformat(), evidence='measured-client-stream',
                    synthetic_prompts=True, quality_qualification=False,
                    fixture_sha256=hashlib.sha256(json.dumps(fixtures, sort_keys=True).encode()).hexdigest())
    if args.config_json:
        metadata['launch_configuration'] = json.loads(args.config_json.read_text())
    result = {'metadata': metadata, 'warmups': [], 'rounds': [], 'qualified_concurrency': None}
    for i in range(args.warmups):
        row = request_once(args, fixtures[i % len(fixtures)], deadline, minimum_output=2)
        result['warmups'].append(row)
        atomic_write(args.output, result)
        if not row['ok']:
            raise RuntimeError('warmup failed; inspect output')
    for concurrency in args.concurrency:
        passed = []
        for trial in range(args.trials):
            if time.monotonic() >= deadline:
                result['stopped_reason'] = 'campaign deadline reached'
                atomic_write(args.output, result)
                return 2
            order = list(range(concurrency * args.requests_per_worker))
            rng = random.Random(args.seed + trial)
            fixture_order = [fixtures[i % len(fixtures)] for i in order]
            rng.shuffle(fixture_order)
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                rows = list(pool.map(lambda fixture: request_once(args, fixture, deadline), fixture_order))
            summary = summarize(rows, concurrency, trial)
            result['rounds'].append(summary)
            passed.append(summary['slo_met'])
            atomic_write(args.output, result)
            print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}), flush=True)
        if all(passed):
            result['qualified_concurrency'] = concurrency
        elif not args.continue_after_failure:
            result['stopped_reason'] = 'first concurrency failing throughput floor'
            break
    atomic_write(args.output, result)
    return 0 if result['qualified_concurrency'] is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
