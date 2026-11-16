import concurrent.futures
import http.server
import importlib.util
import json
import os
import math
import re
import threading
from pathlib import Path
import sys
import time
import urllib.request
import uuid

from config import ACTIVE_REQUESTS, QUEUED_REQUESTS, QUEUE_TIMEOUT_SECONDS, MODEL, REVISION, settings

root = Path(__file__).resolve().parents[1]
base_path = root / 'warmup-base.py'
if not base_path.is_file():
    base_path = root / 'glm/warmup-supervisor.py'
spec = importlib.util.spec_from_file_location('kimi_warmup_base', base_path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.MODEL = MODEL
def startup_concurrencies(limit):
    if type(limit) is not int or limit < 1:
        raise ValueError('Kimi active request limit must be a positive integer')
    counts, value = {limit}, 1
    while value <= limit:
        counts.add(value)
        value *= 2
    return tuple(sorted(counts))


def cache_geometry(info):
    states = info.get('internal_states') if isinstance(info, dict) else None
    if not isinstance(states, list) or not states:
        raise RuntimeError('Kimi cache warmup requires scheduler geometry')
    geometries = []
    for state in [info, *states]:
        if not isinstance(state, dict):
            raise RuntimeError('Kimi cache warmup received invalid scheduler geometry')
        page, dcp = state.get('page_size'), state.get('dcp_size')
        if any(type(value) is not int or value < 1 for value in (page, dcp)):
            raise RuntimeError('Kimi cache warmup requires positive page_size and dcp_size')
        geometries.append((page, dcp))
    if len(set(geometries)) != 1:
        raise RuntimeError('Kimi cache warmup scheduler geometry disagrees')
    page, dcp = geometries[0]
    # SGLang aligns the radix cache to the DCP-widened allocator page.
    quantum = page * dcp
    if quantum > 16384:
        raise RuntimeError('Kimi cache warmup geometry exceeds bounded prefix budget')
    return {'page_size': page, 'dcp_size': dcp, 'cache_quantum': quantum,
            'prefix_tokens': 2 * quantum}


base.CONCURRENCIES = startup_concurrencies(ACTIVE_REQUESTS)
base_handler = base.handler


class Supervisor(base.Supervisor):
    def __init__(self, *args, backend_url=None, active_requests=ACTIVE_REQUESTS,
                 tokenizer_path=MODEL, **kwargs):
        super().__init__(*args, **kwargs)
        self.backend_url = backend_url
        self.active_requests = active_requests
        self.concurrencies = startup_concurrencies(active_requests)
        self.tokenizer_path = tokenizer_path

    def native_probe(self, input_ids, timeout, output_tokens=4):
        if not self.backend_url or not self.backend_url.startswith('http://127.0.0.1:'):
            raise RuntimeError('Kimi native warmup requires its private backend URL')
        payload = {'input_ids': input_ids, 'stream': False, 'sampling_params': {
            'temperature': 1.0, 'top_p': 0.95, 'max_new_tokens': output_tokens,
            'skip_special_tokens': False}}
        request = urllib.request.Request(self.backend_url + '/generate', data=json.dumps(payload).encode(),
                                         headers={'Content-Type': 'application/json'})
        started = time.monotonic()
        with urllib.request.urlopen(request, timeout=self.remaining(timeout)) as response:
            body = json.load(response)
        self.remaining(timeout)
        meta = body.get('meta_info') or {}
        prompt, cached, output = (meta.get(key) for key in ('prompt_tokens', 'cached_tokens', 'completion_tokens'))
        finish = (meta.get('finish_reason') or {}).get('type')
        if (body.get('error') or type(prompt) is not int or prompt != len(input_ids)
                or type(cached) is not int or not 0 <= cached <= prompt
                or type(output) is not int or not 0 < output <= output_tokens or finish not in ('stop', 'length')):
            raise RuntimeError('Kimi native warmup returned invalid token accounting')
        return {'prompt_tokens': prompt, 'cached_tokens': cached, 'completion_tokens': output,
                'elapsed_seconds': round(time.monotonic() - started, 3)}

    def load_tokenizer(self):
        from transformers import AutoTokenizer
        return AutoTokenizer.from_pretrained(self.tokenizer_path, revision=REVISION,
                                             trust_remote_code=True, local_files_only=True)

    def read_cache_geometry(self):
        if not self.backend_url or not self.backend_url.startswith('http://127.0.0.1:'):
            raise RuntimeError('Kimi cache warmup requires its private backend URL')
        with urllib.request.urlopen(self.backend_url + '/server_info', timeout=self.remaining(25)) as response:
            info = json.load(response)
        self.remaining(1)
        return cache_geometry(info)

    def cached_prefix(self, tokenizer, target):
        if type(target) is not int or not 1 <= target <= 32768:
            raise RuntimeError('Kimi cached warmup prefix exceeds bounded token budget')
        marker, count, seen = uuid.uuid4().hex, 0, set()
        for _ in range(32):
            self.remaining(1)
            messages = [{'role': 'user', 'content': marker + ' x' * count}]
            ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                 thinking=True, thinking_effort='max')
            if len(ids) == target:
                return ids
            seen.add(count)
            count += target - len(ids)
            if not 0 <= count <= target or count in seen:
                break
        raise RuntimeError('Kimi cached warmup could not render its pinned prefix')

    def warm_cached_prefills(self):
        self.remaining(1)
        geometry = self.read_cache_geometry()
        print(json.dumps({'phase': 'cached_prefill_geometry', **geometry}), flush=True)
        tokenizer = self.load_tokenizer()
        self.remaining(1)
        padding = tokenizer.encode(' x', add_special_tokens=False)
        if not padding or type(padding[0]) is not int:
            raise RuntimeError('Kimi cached warmup has no ordinary padding token')
        for new_tokens in (1, 2, 3, 4):
            input_ids = self.cached_prefix(tokenizer, geometry['prefix_tokens']) + [padding[0]] * new_tokens
            # A cold hybrid prefix can checkpoint recurrent state below the full
            # aligned prefix; prime again until the cache reports the full hit.
            for _ in range(3):
                primed = self.native_probe(input_ids, 180)
                if primed['prompt_tokens'] - primed['cached_tokens'] == new_tokens:
                    break
            for phase, timeout in (('compile_cached_prefill', 180), ('qualify_cached_prefill', 25)):
                result = self.native_probe(input_ids, timeout)
                if result['prompt_tokens'] - result['cached_tokens'] != new_tokens:
                    raise RuntimeError('Kimi cached warmup did not exercise the required new-token shape')
                print(json.dumps({'phase': phase, 'new_tokens': new_tokens, **result}), flush=True)

    def seeded_group(self, phase, seeds, timeout):
        if not 1 <= len(seeds) <= self.active_requests:
            raise RuntimeError('Kimi seeded warmup must stay within its active request limit')
        barrier = threading.Barrier(len(seeds))
        print(json.dumps({'phase': phase, 'concurrency': len(seeds),
                          'seeded_requests': sum(seed is not None for seed in seeds), 'event': 'started'}), flush=True)
        def request(seed):
            barrier.wait(timeout=self.remaining(5))
            return self.probe(32, timeout, 128, seed=seed)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(seeds)) as pool:
            results = list(pool.map(request, seeds))
        print(json.dumps({'phase': phase, 'concurrency': len(seeds), 'event': 'passed'}), flush=True)
        return results

    def warm_seeded_sampling(self):
        for seed in (0, 1):
            self.probe(32, 180, 16, seed=seed)
        for count in range(1, self.active_requests + 1):
            groups = [([0] * count, 'seeded'),
                      ([0 if index % 2 == 0 else None for index in range(count)], 'mixed_seed'),
                      ([None if index % 2 == 0 else 1 for index in range(count)], 'mixed_seed_inverse')]
            for seeds, name in groups:
                self.seeded_group(f'compile_{name}_bs{count}', seeds, 180)
                self.seeded_group(f'qualify_{name}_bs{count}', seeds, 25)

    def warmup(self):
        self.qualified.clear()
        while not self.health():
            self.remaining(2)
            self.stopping.wait(1)
        self.warm_cached_prefills()
        self.warm_seeded_sampling()
        previous = base.CONCURRENCIES
        base.CONCURRENCIES = self.concurrencies
        try:
            return super().warmup()
        finally:
            base.CONCURRENCIES = previous

    def probe_group(self, phase, shapes, timeout):
        results = []
        for start in range(0, len(shapes), self.active_requests):
            results.extend(super().probe_group(phase, shapes[start:start+self.active_requests], timeout))
        return results

    def probe(self, words, timeout, output_tokens=64, seed=None):
        prompt = uuid.uuid4().hex + ' ' + 'warmup ' * words + '\nReply with a numbered list.'
        body = {'model': MODEL, 'messages': [{'role': 'user', 'content': prompt}],
                'stream': True, 'max_tokens': output_tokens, 'reasoning_effort': 'max',
                'temperature': 1.0, 'top_p': 0.95, 'stream_options': {'include_usage': True}}
        if seed is not None:
            body['seed'] = seed
        payload = json.dumps(body).encode()
        request = urllib.request.Request(self.runtime_url + '/v1/chat/completions', data=payload,
                                         headers={'Content-Type': 'application/json'})
        started, saw_output, usage = time.monotonic(), False, None
        with urllib.request.urlopen(request, timeout=self.remaining(timeout)) as response:
            for line in response:
                self.remaining(timeout)
                if not line.startswith(b'data:'):
                    continue
                data = line[5:].strip()
                if data == b'[DONE]':
                    if (not saw_output or not usage or type(usage.get('completion_tokens')) is not int
                            or usage['completion_tokens'] <= 0 or type(usage.get('prompt_tokens')) is not int):
                        raise RuntimeError('Kimi warmup stream had no output or usage')
                    if usage.get('prompt_tokens', 0) < words:
                        raise RuntimeError('Kimi warmup prompt shorter than requested shape')
                    return {'prompt_tokens': usage['prompt_tokens'],
                            'elapsed_seconds': round(time.monotonic() - started, 3)}
                event = json.loads(data)
                if 'error' in event:
                    raise RuntimeError('Kimi warmup stream returned an error')
                if event.get('usage'):
                    usage = event['usage']
                for choice in event.get('choices', []):
                    if choice.get('finish_reason') not in (None, 'stop', 'length'):
                        raise RuntimeError('Kimi warmup stream was interrupted')
                    delta = choice.get('delta', {})
                    saw_output |= bool(delta.get('content') or delta.get('reasoning') or delta.get('reasoning_content'))
        raise RuntimeError('Kimi warmup stream ended without DONE')

    def health(self):
        if self.child is None or self.child.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(self.runtime_url + '/readiness', timeout=2) as response:
                if response.status != 200:
                    return False
            if not self.backend_url or not self.backend_url.startswith('http://127.0.0.1:'):
                return False
            # Native /health can pass while a GPU kernel is stuck; require a scheduler response.
            with urllib.request.urlopen(self.backend_url + '/health_generate', timeout=2) as response:
                return response.status == 200
        except Exception:
            return False


def namespace_metrics(text, prefix):
    lines = []
    for line in text.splitlines():
        fields = line.split()
        if line.startswith(('# HELP ', '# TYPE ')):
            name = fields[2] if len(fields) > 2 else ''
        elif line.startswith('#') or not fields:
            continue
        else:
            name = fields[0].split('{', 1)[0]
        if name.startswith(prefix):
            lines.append(line)
    return '\n'.join(lines).encode()


def full_kv_pressure(text):
    values = []
    sample = re.compile(r'sglang:full_token_usage(?:\{(?:[^"{}]|"(?:\\.|[^"\\])*")*\})?\s+(\S+)(?:\s+\d+)?')
    for line in text.splitlines():
        if not line.startswith('sglang:full_token_usage'):
            continue
        match = sample.fullmatch(line)
        if match is None:
            raise ValueError('Malformed native full-token pressure sample')
        value = float(match[1])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('Native full-token pressure is not a ratio')
        values.append(value)
    if not values:
        raise ValueError('Native full-token pressure is unavailable')
    return max(values)


def metrics(config):
    texts = []
    for port in [config['backend'], config['metrics']]:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics', timeout=2) as response:
            if response.status != 200:
                raise RuntimeError('Native runtime metrics unavailable')
            body = response.read(4 * 1024 * 1024)
            if len(body) >= 4 * 1024 * 1024:
                raise ValueError('Native metrics response exceeds bound')
            texts.append(body.decode())
    pressure = full_kv_pressure(texts[0])
    chunks = [namespace_metrics(texts[0], 'sglang:'), namespace_metrics(texts[1], 'smg_')]
    for name, value, help_text in [
        ('gradiated_runtime_active_request_limit', config.get('active_requests', ACTIVE_REQUESTS), 'SMG requests holding an active permit.'),
        ('gradiated_runtime_waiting_request_limit', QUEUED_REQUESTS, 'SMG requests waiting for a permit.'),
        ('gradiated_runtime_queue_timeout_seconds', QUEUE_TIMEOUT_SECONDS, 'Native SMG maximum queue age.'),
        ('vllm:kv_cache_usage_perc', pressure, 'Compatibility alias: maximum native SGLang non-evictable full-attention KV usage ratio.'),
    ]:
        chunks.append(f'\n# HELP {name} {help_text}\n# TYPE {name} gauge\n{name} {value}\n'.encode())
    return b'\n'.join(chunks)


def handler(supervisor, config):
    parent = base_handler(supervisor)
    class Handler(parent):
        def do_GET(self):
            if self.path != '/metrics':
                return super().do_GET()
            try:
                body, code = metrics(config), 200
            except (OSError, RuntimeError, ValueError):
                body, code = b'native metrics unavailable\n', 503
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main(environment=os.environ):
    config = settings(environment)
    original = base.handler
    base.handler = lambda supervisor: handler(supervisor, config)
    try:
        supervisor = Supervisor([sys.executable, str(root / 'kimi-k31/service.py')],
            runtime_url=f"http://127.0.0.1:{config['front']}",
            backend_url=f"http://127.0.0.1:{config['backend']}", active_requests=config['active_requests'],
            timeout=int(environment.get('RUNTIME_STARTUP_TIMEOUT_SECONDS', '3600')),
            max_queued_requests=config['active_requests'] + QUEUED_REQUESTS)
        return supervisor.run(port=config['warmup'])
    finally:
        base.handler = original


if __name__ == '__main__':
    raise SystemExit(main())
