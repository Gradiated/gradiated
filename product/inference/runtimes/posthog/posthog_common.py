"""Serving shared by the PostHog decision runtimes (posthog/jevk5, posthog/jeeves): a loopback SGLang engine behind
Kev's bounded ASGI adapter (kev_http), answering the gateway's /v1/systemone contract.

kev_http validates every request (product/packages/contracts/src/systemone.ts); each runtime's Engine turns a request
into token ids, asks SGLang for one token per prompt with the log probabilities of chosen token ids, and builds the
answers. Every answer leaves with exactly the fields the gateway checks (product/services/gateway/src/runtime/
systemone.rs); an answer that would fail them is an engine fault, never returned.
"""
from __future__ import annotations

import atexit
from array import array
from collections import OrderedDict
import hashlib
import logging
import math
import os
import socket
import subprocess
import sys
import threading
import time

from kev_http import App, respond_error

log = logging.getLogger('posthog.runtime')

SGLANG_STARTUP_SECONDS = 1500
SGLANG_TIMEOUT_SECONDS = 120
GDN_CHECKPOINT_TOKENS = 64
PREFILL_CUDA_GRAPH_SIZES = ('64', '128', '256', '512', '1024')
ANSWER_FIELDS = {'noul': {'type', 'noul'}, 'choice': {'type', 'choice', 'confidence', 'probabilities'},
                 'score': {'type', 'score', 'legend', 'confidence', 'probabilities'}}


class InvalidModelOutput(RuntimeError):
    """The engine answered with something no valid answer can be built from."""


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def outcome_keys(question):
    """The keys of an answer's probabilities: a choice's option names or a score's level indices."""
    return (list(question['criteria']) if question['type'] == 'choice'
            else [str(i) for i in range(len(question['criteria']))])


def valid_answer(answer, question):
    """Exactly the answer the gateway accepts (product/services/gateway/src/runtime/systemone.rs)."""
    kind = question['type']
    if not isinstance(answer, dict) or answer.get('type') != kind or set(answer) != ANSWER_FIELDS[kind]:
        return False
    if kind == 'noul':
        return probability(answer['noul'])
    keys = outcome_keys(question)
    probabilities = answer['probabilities']
    if (not probability(answer['confidence']) or not isinstance(probabilities, dict) or set(probabilities) != set(keys)
            or not all(probability(value) for value in probabilities.values())
            or abs(math.fsum(probabilities.values()) - 1) > 0.0001):
        return False
    if kind == 'choice':
        return answer['choice'] in keys
    legend, score = answer['legend'], answer['score']
    return (isinstance(legend, dict) and set(legend) == set(keys) and all(isinstance(v, str) for v in legend.values())
            and type(score) in (int, float) and math.isfinite(score) and 0 <= score <= len(keys) - 1)


def softmax(logits):
    """The distribution of finite logits; InvalidModelOutput for any other."""
    if not logits or not all(type(v) in (int, float) and math.isfinite(v) for v in logits):
        raise InvalidModelOutput('non-finite option logits')
    top = max(logits)
    weights = [math.exp(v - top) for v in logits]
    total = math.fsum(weights)
    return [w / total for w in weights]


def answer(question, probabilities, legend=None):
    """PostHog's /v1/systemone answer for a distribution over the question's outcomes, in the gateway's shape.

    probabilities maps every outcome key (noul: "true" and "false"; choice: option names; score: level indices) to its
    probability. confidence is the top probability, as PostHog's servers report it. A noul answer is only the
    probability of true and a score answer carries its legend, because the gateway accepts exactly those fields.
    """
    kind = question['type']
    if kind == 'noul':
        return {'type': 'noul', 'noul': probabilities['true']}
    keys = outcome_keys(question)
    probabilities = {key: probabilities[key] for key in keys}
    confidence = max(probabilities.values())
    if kind == 'choice':
        return {'type': 'choice', 'choice': max(keys, key=probabilities.__getitem__), 'confidence': confidence,
                'probabilities': probabilities}
    score = min(len(keys) - 1.0, math.fsum(int(key) * p for key, p in probabilities.items()))
    return {'type': 'score', 'score': max(0.0, score), 'legend': legend, 'confidence': confidence,
            'probabilities': probabilities}


def single_outcome(question):
    """A one-option choice or a one-level score, which the gateway accepts and PostHog's servers refuse: certain."""
    return question['type'] in ('choice', 'score') and len(question['criteria']) == 1


class SGLang:
    """The loopback engine: one prefill per prompt and the log probabilities of chosen next tokens."""

    def __init__(self, url, session, http_error):
        self.url, self.session, self.http_error = url, session, http_error

    def _generate(self, body):
        response = self.session.post(f'{self.url}/generate', json=body, timeout=SGLANG_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def prefill(self, ids):
        """Compute a shared prefix into the radix cache, so the prompts that start with it reuse its state."""
        self._generate({'input_ids': list(ids), 'sampling_params': {'max_new_tokens': 1, 'temperature': 0.0}})

    def logprobs(self, rows, token_ids, *, custom_params=None):
        """-> for each prompt (a list of token ids), the next-token log probabilities of its token_ids, in order.
        A missing or non-finite value is None."""
        if not rows:
            return []
        sampling = {'max_new_tokens': 1, 'temperature': 0.0}
        if custom_params is not None:
            sampling['custom_params'] = custom_params
        body = {'input_ids': [list(ids) for ids in rows], 'sampling_params': sampling,
                'return_logprob': True, 'logprob_start_len': -1,
                'token_ids_logprob': [list(ids) for ids in token_ids]}
        results = self._generate(body)
        if len(rows) == 1 and isinstance(results, dict):
            results = [results]
        if not isinstance(results, list) or len(results) != len(rows):
            raise RuntimeError('SGLang returned a different number of results')
        out = []
        for ids, result in zip(token_ids, results):
            got = {int(row[1]): row[0] for row in (result['meta_info'].get('output_token_ids_logprobs') or [[]])[0]}
            out.append([v if type(v) in (int, float) and math.isfinite(v) else None for v in map(got.get, ids)])
        return out


class Slots:
    """A bounded admission counter with the Lock interface kev_http's App uses."""

    def __init__(self, count):
        self.count, self.used, self.lock = count, 0, threading.Lock()

    def acquire(self, blocking=True):
        with self.lock:
            if self.used >= self.count:
                return False
            self.used += 1
            return True

    def release(self):
        with self.lock:
            if self.used <= 0:
                raise RuntimeError('release without acquire')
            self.used -= 1

    def locked(self):
        with self.lock:
            return self.used >= self.count


class RuntimeApp(App):
    def __init__(self, engine, token=None, active_requests=8):
        super().__init__(engine, token)
        # SGLang batches concurrent prefills; the host proxy admits up to the pinned active_requests.
        self.slot = Slots(active_requests)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'] == '/health' and not (
                self.engine.healthy and self.engine.sglang_alive()):
            return await respond_error(send, 503, 'runtime requires restart')
        return await super().__call__(scope, receive, send)


def common_prefix_length(rows):
    """Tokens every row starts with, leaving each row at least one token of its own to compute."""
    limit = min(len(row) for row in rows) - 1
    low, high = min(rows), max(rows)  # every row lies between the lexicographic extremes
    for i in range(limit):
        if low[i] != high[i]:
            return i
    return max(0, limit)


def die_with_parent():
    """Linux PR_SET_PDEATHSIG: the engine never outlives the adapter and keeps the GPU."""
    import ctypes
    import signal

    if ctypes.CDLL('libc.so.6', use_errno=True).prctl(1, signal.SIGKILL) != 0:
        os._exit(1)


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class WarmStateTracker:
    """Thread-safe bounded LRU of recently prefilled state-prefix digests for cold/warm batching decisions."""

    def __init__(self, max_entries=128):
        self.max_entries = max_entries
        self._seen = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key(ids):
        if len(ids) < GDN_CHECKPOINT_TOKENS:
            return None
        return hashlib.blake2b(array('q', ids).tobytes(), digest_size=16).digest()

    def is_warm(self, state_key):
        if state_key is None:
            return False
        with self._lock:
            return state_key in self._seen

    def mark(self, state_key):
        if state_key is None:
            return
        with self._lock:
            self._seen.pop(state_key, None)
            self._seen[state_key] = None
            if len(self._seen) > self.max_entries:
                self._seen.popitem(last=False)


def sglang_command(checkpoint, port, max_tokens, flags):
    """SGLang for prompts of at most max_tokens tokens, each answered with one token (max_tokens + 1 context)."""
    return [sys.executable, '-m', 'sglang.launch_server', '--model-path', checkpoint, '--served-model-name', 'm',
            '--tp', '1', '--host', '127.0.0.1', '--port', str(port), '--context-length', str(max_tokens + 1),
            # Every request generates one token (no decode steps). Disable decode graphs and overlap scheduling
            # (which otherwise launches an unused 1-token eager decode step after every prefill), and capture
            # breakable prefill CUDA graphs up to 1,024 tokens to accelerate short and warm-cache suffix prefills.
            '--cuda-graph-backend-decode', 'disabled',
            '--cuda-graph-backend-prefill', 'breakable', '--cuda-graph-bs-prefill', *PREFILL_CUDA_GRAPH_SIZES,
            '--disable-overlap-schedule',
            # The adapter runs its own warmup through the real request path.
            '--skip-server-warmup', *flags]


def start_sglang(command, environment=None):
    import requests

    port = int(command[command.index('--port') + 1])
    # The checkpoint is local; the engine must not reach the Hub or run checkpoint code.
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', **(environment or {})}
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, preexec_fn=die_with_parent)
    atexit.register(process.kill)
    deadline = time.monotonic() + SGLANG_STARTUP_SECONDS
    url = f'http://127.0.0.1:{port}'
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('SGLang exited during startup')
        try:
            if requests.get(f'{url}/health', timeout=3).status_code == 200:
                return process, url
        except requests.RequestException:
            pass
        time.sleep(2)
    process.kill()
    raise RuntimeError('SGLang did not become healthy')


def client(url, active_requests):
    import requests

    session = requests.Session()
    session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=active_requests * 2))
    return SGLang(url, session, requests.HTTPError)


def snapshot(model, revision, allow_patterns):
    """The pinned Hub revision in HF_HOME: weights, tokenizer and configuration only; no repository code runs."""
    from huggingface_hub import snapshot_download

    if len(revision) != 40:
        raise RuntimeError(f'{model} revision is not pinned')
    cache = os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface'))
    return snapshot_download(model, revision=revision, cache_dir=cache, allow_patterns=allow_patterns)


def serve(engine, port, token, active_requests):
    import uvicorn

    uvicorn.run(RuntimeApp(engine, token, active_requests), host='127.0.0.1', port=port,
                workers=1, limit_concurrency=64, timeout_keep_alive=5, access_log=False, log_level='warning')
