#!/usr/bin/env python3
"""Measure isolated vLLM streaming under mixed synthetic token prompt lengths."""
import argparse
import concurrent.futures
import json
import itertools
import functools
import hashlib
from collections.abc import Mapping
import random
import statistics
import time
import threading
import urllib.request
from pathlib import Path


def percentile(values, quantile):
    values = sorted(values)
    if not values:
        return None
    return values[round((len(values) - 1) * quantile)]


def prepare_chat(url, model, target, seed, tokenizer=None, cache_dir=None):
    cache_path = None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([2, model, target, seed, str(getattr(tokenizer, 'name_or_path', None))]).encode()).hexdigest()
        cache_path = cache_dir / (key+'.json')
        if cache_path.exists():
            saved = json.loads(cache_path.read_text())
            return saved['messages'], saved['count']
    rng = random.Random(seed)
    records = [f"Record {seed}: summarize these synthetic service logs, report errors and latency patterns.\n"]
    for i in range(target // 8 + 100):
        records.append(f"Entry {i}: service {rng.choice(['api', 'worker', 'cache'])} processed "
                       f"{rng.randrange(100, 10000)} requests in {rng.randrange(1, 1000)} ms; "
                       f"status {rng.choice(['ok', 'retry', 'timeout'])}.\n")
    text = ''.join(records)
    if tokenizer is not None:
        ids = tokenizer.encode(text, add_special_tokens=False, truncation=True, max_length=target)
        size = target - 64
        best_local = None
        for _ in range(6):
            messages = [{'role': 'user', 'content': tokenizer.decode(ids[:size]) + '\nSummarize the log patterns.'}]
            encoded = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                     reasoning_effort='low')
            encoded_ids = encoded['input_ids'] if isinstance(encoded, Mapping) else encoded
            if encoded_ids and isinstance(encoded_ids[0], list):
                encoded_ids = encoded_ids[0]
            count = len(encoded_ids)
            if count <= target and (best_local is None or count > best_local[1]):
                best_local = (messages, count)
            if count == target:
                break
            size += target-count
        if best_local is not None:
            messages, count = best_local
        req = urllib.request.Request(url+'/tokenize', data=json.dumps({'model': model, 'messages': messages,
                'chat_template_kwargs': {'reasoning_effort': 'low'}}).encode(),
                headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            actual = json.load(response)['count']
        if actual != count or actual > target or target-actual > 8:
            raise RuntimeError(f'Local/server chat tokenizer mismatch or length overflow: {count}, {actual}, {target}')
        if cache_path:
            cache_path.write_text(json.dumps({'messages': messages, 'count': actual}))
        return messages, actual
    low, high = 1, len(text)
    best = None
    for _ in range(18):
        middle = (low+high)//2
        messages = [{'role': 'user', 'content': text[:middle] + '\nSummarize the log patterns.'}]
        payload = {'model': model, 'messages': messages,
                   'chat_template_kwargs': {'reasoning_effort': 'low'}}
        req = urllib.request.Request(url+'/tokenize', data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            count = json.load(response)['count']
        if best is None or abs(count-target) < abs(best[1]-target):
            best = (messages, count)
        if count == target or low >= high:
            break
        if count < target:
            low = middle+1
        else:
            high = middle-1
    if abs(best[1]-target) > max(8, target*.005):
        raise RuntimeError('Chat fixture length outside tolerance')
    if cache_path:
        cache_path.write_text(json.dumps({'messages': best[0], 'count': best[1]}))
    return best


def request(url, model, length, output_tokens, seed, delay, epoch, protocol="completions", prepared=None, idle_timeout=30, request_deadline=630, first_output_signal=None):
    rng = random.Random(seed)
    tokens = [rng.randrange(1000, 20000) for _ in range(length)] if protocol == 'completions' else []
    time.sleep(max(0, epoch + delay - time.monotonic()))
    started = time.monotonic()
    payload = {'model': model, 'prompt': tokens, 'max_tokens': output_tokens,
               'temperature': 0, 'ignore_eos': True, 'stream': True,
               'stream_options': {'include_usage': True}}
    expected_tokens = length
    if protocol == 'chat':
        payload.pop('prompt')
        payload['messages'], expected_tokens = prepared
        payload['chat_template_kwargs'] = {'reasoning_effort': 'low'}
    row = {'input_tokens': expected_tokens, 'requested_input_tokens': length, 'seed': seed, 'scheduled_offset_s': delay,
           'started_offset_s': started - epoch, 'ok': False}
    first = None
    previous = None
    gaps = []
    usage = None
    done = False
    try:
        endpoint = '/v1/chat/completions' if protocol == 'chat' else '/v1/completions'
        req = urllib.request.Request(url + endpoint, data=json.dumps(payload).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=request_deadline) as response:
            while True:
                remaining = request_deadline-(time.monotonic()-started)
                if remaining <= 0:
                    raise TimeoutError('request deadline exceeded')
                response.fp.raw._sock.settimeout(min(idle_timeout, remaining))
                line = response.readline()
                if not line:
                    break
                if not line.startswith(b'data:'):
                    continue
                raw = line[5:].strip()
                if raw == b'[DONE]':
                    done = True
                    break
                event = json.loads(raw)
                if event.get('error'):
                    raise RuntimeError(str(event['error']))
                now = time.monotonic()
                if any(choice.get('text') or any(choice.get('delta', {}).get(key) for key in
                        ('content', 'reasoning', 'reasoning_content')) for choice in event.get('choices', [])):
                    if first is None:
                        first = now
                        if first_output_signal is not None:
                            first_output_signal.set()
                    if previous is not None:
                        gaps.append(now - previous)
                    previous = now
                if event.get('usage'):
                    usage = event['usage']
        if not done or first is None or not usage:
            raise RuntimeError('Missing content, usage or stream terminator')
        if usage['prompt_tokens'] != expected_tokens or usage['completion_tokens'] != output_tokens:
            raise RuntimeError('Token counts differ from requested geometry')
        row.update(ok=True, ttft_s=first-started, first_output_offset_s=first-epoch, usage=usage,
                   stream_gap_p95_s=percentile(gaps, .95), stream_gap_max_s=max(gaps, default=0),
                   stream_events=len(gaps)+1,
                   decode_tokens_per_s=(output_tokens-1)/max(time.monotonic()-first, 1e-6))
    except Exception as error:
        row['error'] = str(error)
    row.update(elapsed_s=time.monotonic()-started, finished_offset_s=time.monotonic()-epoch)
    return row


def quality_smoke(url, model, prepare=prepare_chat, contexts=(512, 32768, 131072)):
    results = []
    for length, position, marker in zip(contexts, (0, .5, .9), ('cobalt', 'marigold', 'tamarind')):
        messages, _ = prepare(url, model, length, 90000000+length)
        text = messages[0]['content']
        index = int(len(text)*position)
        messages[0]['content'] = (text[:index] + f"\nAUDIT_CODEWORD={marker}\n" + text[index:] +
            "\nFind the AUDIT_CODEWORD in the logs. Reply with only its value, no explanation.")
        body = {'model': model, 'messages': messages, 'temperature': 0, 'max_tokens': 1024,
                'chat_template_kwargs': {'reasoning_effort': 'low'}}
        req = urllib.request.Request(url+'/v1/chat/completions', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        started = time.monotonic()
        with urllib.request.urlopen(req, timeout=690) as response:
            result = json.load(response)
        message = result['choices'][0]['message']
        content = (message.get('content') or '').strip().lower().strip(' .`\n')
        results.append({'requested_context_tokens': length, 'marker_position': position,
                        'correct': content == marker, 'marker_present': marker in content, 'has_content': bool(content),
                        'finish_reason': result['choices'][0]['finish_reason'],
                        'usage': result.get('usage'), 'elapsed_s': time.monotonic()-started})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--model', default='dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4')
    parser.add_argument('--label', required=True)
    parser.add_argument('--protocol', choices=('chat', 'completions'), default='chat')
    parser.add_argument('--quality-smoke', action='store_true')
    parser.add_argument('--quality-contexts', default='512,32768,131072')
    parser.add_argument('--tokenizer-path', type=Path)
    parser.add_argument('--fixture-cache', type=Path)
    parser.add_argument('--response-idle-timeout', type=float, default=30)
    parser.add_argument('--request-deadline', type=float, default=630)
    parser.add_argument('--seed-offset', type=int, default=0)
    parser.add_argument('--long-tokens', default='32768,131072')
    parser.add_argument('--short-tokens', type=int, default=512)
    parser.add_argument('--output-tokens', type=int, default=256)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--orderings', default='long-first,decode-first')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = {'label': args.label, 'synthetic_prompts': True,
               'quality_qualification': False, 'timing': 'client SSE events; MTP may emit multiple tokens per event',
               'configuration': {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}, 'rounds': []}
    tokenizer = None
    if args.tokenizer_path:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(str(args.tokenizer_path), local_files_only=True)
    prepare = functools.partial(prepare_chat, tokenizer=tokenizer, cache_dir=args.fixture_cache)
    if args.quality_smoke:
        results['quality_smoke'] = quality_smoke(args.url, args.model, prepare, tuple(map(int, args.quality_contexts.split(','))))
        args.output.write_text(json.dumps(results, indent=2)+'\n')
        print(json.dumps({'quality_smoke': results['quality_smoke']}), flush=True)
    warmup_input = prepare(args.url, args.model, args.short_tokens, 7) if args.protocol == 'chat' else None
    warmup = request(args.url, args.model, args.short_tokens, 32, 7, 0, time.monotonic(), args.protocol, warmup_input, args.response_idle_timeout, args.request_deadline)
    if not warmup['ok']:
        raise RuntimeError(warmup)
    orderings = args.orderings.split(',')
    if set(orderings) - {'long-first', 'decode-first'}:
        parser.error('orderings must be long-first and/or decode-first')
    for repeat, long_tokens, ordering in itertools.product(
            range(args.repeats), map(int, args.long_tokens.split(',')), orderings):
        if ordering == 'long-first':
            shapes = [(long_tokens, 0)] + [(args.short_tokens, .25*i) for i in range(1, 7)]
        else:
            shapes = [(args.short_tokens, .1*i) for i in range(3)] + [(long_tokens, .5)] + [
                (args.short_tokens, .75+.25*i) for i in range(3)]
        seeds = [args.seed_offset + 1000000*repeat + long_tokens + i + 20000000*(ordering == 'decode-first')
                 for i in range(len(shapes))]
        prepared = [prepare(args.url, args.model, length, seed) if args.protocol == 'chat' else None
                    for (length, _), seed in zip(shapes, seeds)]
        epoch = time.monotonic() + .1
        first_signals = [threading.Event() for _ in range(3)]
        long_started = threading.Event()

        def run_slot(i):
            length, delay = shapes[i]
            signal = None
            if ordering == 'decode-first':
                if i < 3:
                    signal = first_signals[i]
                elif i == 3:
                    for event in first_signals:
                        if not event.wait(timeout=30):
                            raise RuntimeError('Short streams did not start before long-prompt injection')
                    time.sleep(.1)
                    long_started.set()
                    delay = 0
                else:
                    if not long_started.wait(timeout=35):
                        raise RuntimeError('Long-prompt injection did not start')
                    time.sleep(.25*(i-3))
                    delay = 0
            return request(args.url, args.model, length, args.output_tokens, seeds[i], delay,
                           epoch, args.protocol, prepared[i], args.response_idle_timeout,
                           args.request_deadline, signal)

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(shapes)) as pool:
            rows = list(pool.map(run_slot, range(len(shapes))))
        good = [r for r in rows if r['ok']]
        shorts = [r for r in good if r['requested_input_tokens'] == args.short_tokens]
        elapsed = max(r['finished_offset_s'] for r in rows)
        summary = {'repeat': repeat, 'long_tokens': long_tokens, 'ordering': ordering,
                   'errors': len(rows)-len(good), 'arrival_trigger': 'first-short-output' if ordering == 'decode-first' else 'fixed-offset',
                   'short_ttft_p50_s': statistics.median(r['ttft_s'] for r in shorts) if shorts else None,
                   'short_ttft_p95_s': percentile([r['ttft_s'] for r in shorts], .95),
                   'short_max_stream_gap_s': max((r['stream_gap_max_s'] for r in shorts), default=None),
                   'aggregate_output_tokens_per_s': sum(r['usage']['completion_tokens'] for r in good)/elapsed,
                   'measurements': rows}
        results['rounds'].append(summary)
        args.output.write_text(json.dumps(results, indent=2)+'\n')
        print(json.dumps({k:v for k,v in summary.items() if k != 'measurements'}), flush=True)
        if summary['errors']:
            raise RuntimeError('Mixed workload failed; partial results retained')


if __name__ == '__main__':
    main()
