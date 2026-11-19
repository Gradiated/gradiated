"""linden-1 native SystemOne serving: Gradiated's decision front end (prompt.py) over a loopback SGLang engine.

The gateway's /v1/systemone contract (product/packages/contracts/src/systemone.ts), which the TypeSafe SDK speaks, is
the interface: kev_http's App validates requests, and every answer leaves with exactly the fields the gateway checks.
Each request renders one prompt per question; the questions share a prefix, which is prefilled once, and then all of
them go to SGLang in one batched /generate call that returns only the option-label log probabilities.
"""
from __future__ import annotations

import argparse
import atexit
import logging
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

from kev_http import App, InvalidRequest, respond_error, read_token
import prompt

log = logging.getLogger('linden.service')

MODEL = 'gradiated/linden-1'
# The immutable Hub commit of gradiated/linden-1; verify-build.py refuses to package an unpinned runtime. This is the
# FP8 checkpoint (compressed-tensors, FP8 dynamic), which SGLang loads as FP8 from its config; the BF16 weights are
# the Hub's bf16 branch (eba925a94f6308f486334be5669399bd620f8fce).
REVISION = 'ca21f84254e58d108e49747deefe08ceb3dfe939'
# The longest prompt SGLang accepts. Requests whose rendered prompt is longer are rejected, never truncated.
MAX_TOKENS = 32768
QUANTIZATIONS = {'none': [], 'fp8': ['--quantization', 'fp8']}
SGLANG_STARTUP_SECONDS = 1500
SGLANG_TIMEOUT_SECONDS = 120
ACTIVE_REQUESTS = 8
# A B300 pass of up to about 4,000 prompt tokens costs little more than a small one, so the questions of a request go
# to the engine in one pass, each with its own copy of the shared prefix, when that pass stays within this many tokens
# (2-5 questions about a short state: 48 ms instead of 96). Larger requests prefill the shared prefix in a pass of its
# own and then score the questions against the cached prefix.
ONE_PASS_MAX_TOKENS = 4096
MEDIA_PARTS = {'image', 'image_url', 'video', 'video_url', 'audio', 'audio_url', 'input_audio', 'file'}
ANSWER_FIELDS = {'noul': {'type', 'noul'}, 'choice': {'type', 'choice', 'confidence', 'probabilities'},
                 'score': {'type', 'score', 'legend', 'confidence', 'probabilities'}}


def text_only(state):
    """Chat states keep their turns, but only with text content; no media part (a `type` naming media, with its
    payload under that key, as in OpenAI content parts) may appear anywhere. Other objects are data, flattened to text."""
    messages = prompt.chat_messages(state)
    if messages is not None:
        for message in messages:
            content = message.get('content')
            if isinstance(content, list) and any(
                    not isinstance(part, dict) or part.get('type') != 'text' or not isinstance(part.get('text'), str)
                    for part in content):
                raise InvalidRequest('only text content parts are supported')
    stack = [state]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            kind = value.get('type')
            if isinstance(kind, str) and kind in MEDIA_PARTS and kind in value:
                raise InvalidRequest('images, audio and files are not supported')
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def outcome_keys(question):
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
    legend = answer['legend']
    score = answer['score']
    return (isinstance(legend, dict) and set(legend) == set(keys) and all(isinstance(v, str) for v in legend.values())
            and type(score) in (int, float) and math.isfinite(score) and 0 <= score <= len(keys) - 1)


class SGLang:
    """The loopback engine: one prefill per prompt and the log probabilities of chosen next tokens."""

    def __init__(self, url, session, http_error):
        self.url, self.session, self.http_error = url, session, http_error

    def _generate(self, body):
        response = self.session.post(f'{self.url}/generate', json=body, timeout=SGLANG_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def prefill(self, text):
        """Prefill a shared prefix into the radix cache; -> its token count."""
        meta = self._generate({'text': text, 'sampling_params': {'max_new_tokens': 1, 'temperature': 0.0}})['meta_info']
        return int(meta['prompt_tokens'])

    def score(self, texts, label_ids):
        """-> [(label log probabilities in label order, prompt tokens)] for a batch of prompts."""
        results = self._generate({'text': texts, 'sampling_params': {'max_new_tokens': 1, 'temperature': 0.0},
                                  'return_logprob': True, 'logprob_start_len': -1, 'token_ids_logprob': label_ids})
        if len(texts) == 1 and isinstance(results, dict):
            results = [results]
        if not isinstance(results, list) or len(results) != len(texts):
            raise RuntimeError('SGLang returned a different number of results')
        out = []
        for ids, result in zip(label_ids, results):
            meta = result['meta_info']
            got = {int(row[1]): row[0] for row in (meta.get('output_token_ids_logprobs') or [[]])[0]}
            row = [got.get(i) for i in ids]
            out.append(([v if v is not None and math.isfinite(v) else -math.inf for v in row],
                        int(meta['prompt_tokens'])))
        return out


class Engine:
    model = MODEL

    def __init__(self, renderer, sglang, sglang_alive):
        self.renderer, self.sglang, self.sglang_alive = renderer, sglang, sglang_alive
        self.healthy = True

    def answer(self, data):
        if not self.healthy or not self.sglang_alive():
            self.healthy = False
            raise RuntimeError('runtime requires restart')
        state, questions = data['state'], data['questions']
        text_only(state)
        answers = {key: prompt.certain(q) for key, q in questions.items() if prompt.single_outcome(q)}
        asked = {key: q for key, q in questions.items() if key not in answers}
        certain = {key: q for key, q in questions.items() if key in answers}
        try:
            # Rendering problems (too many options for the label set, unrenderable JSON) are the client's.
            rendered = self.renderer.render(state, asked) if asked else None
            certain_tokens = self._question_tokens(certain)
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidRequest(f'invalid decision request: {exc}') from None
        try:
            input_tokens = self._score(rendered, asked, answers) if asked else self._count(state)
        except self.sglang.http_error as exc:
            # SGLang answers 400 for a prompt over the context length; anything else is a failed engine.
            if exc.response is not None and exc.response.status_code == 400:
                raise InvalidRequest(f'request exceeds {MAX_TOKENS} tokens') from None
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        except Exception:
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        if certain and self._count(state) + max(map(self.renderer.count, map(prompt.certain_text, certain.values()))) \
                > MAX_TOKENS:
            # SGLang enforces the limit only for prompts it sees; a question answered without the model gets the same
            # limit on the state-plus-question prompt it would have had.
            raise InvalidRequest(f'request exceeds {MAX_TOKENS} tokens')
        # Questions answered without the model still count: their rendered text is input like any other.
        input_tokens += certain_tokens
        answers = {key: answers[key] for key in questions}
        if any(not valid_answer(answers[key], question) for key, question in questions.items()):
            self.healthy = False
            raise RuntimeError('invalid decision model output')
        return {'model': MODEL, 'answers': answers,
                'usage': {'input_tokens': input_tokens, 'cached_input_tokens': 0, 'output_tokens': 0}}

    def _score(self, rendered, asked, answers):
        keys = [rendered.prompts[key][1] for key in asked]
        label_ids = [self.renderer.label_ids[:len(k)] for k in keys]
        prefix_tokens = self.renderer.count(rendered.prefix) if len(asked) > 1 else 0
        if prefix_tokens:
            one_pass = prefix_tokens * len(asked) + sum(
                self.renderer.count(rendered.prompts[key][0][len(rendered.prefix):]) for key in asked)
            if one_pass > ONE_PASS_MAX_TOKENS:
                self.sglang.prefill(rendered.prefix)
        results = self.sglang.score([rendered.prompts[key][0] for key in asked], label_ids)
        for (key, question), question_keys, (row, _) in zip(asked.items(), keys, results):
            answers[key] = prompt.answer(question, question_keys, row)
        # Usage counts the distinct tokens of the request: the shared prefix once, then each question's own part.
        if not prefix_tokens:
            return sum(tokens for _, tokens in results)
        return prefix_tokens + sum(max(0, tokens - prefix_tokens) for _, tokens in results)

    def _question_tokens(self, questions):
        """Tokens of the question blocks of questions answered without the model."""
        return sum(self.renderer.count(prompt.certain_text(q)) for q in questions.values())

    def _count(self, state):
        """Input tokens of a request answered without the model (only single-outcome questions): its state."""
        prefix, _, _ = prompt.frame(self.renderer.tokenizer, state, None, False)
        return max(1, self.renderer.count(prefix))


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
    def __init__(self, engine, token=None, active_requests=ACTIVE_REQUESTS):
        super().__init__(engine, token)
        # SGLang batches concurrent prefills; the host proxy admits up to the pinned active_requests.
        self.slot = Slots(active_requests)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'] == '/health' and not (
                self.engine.healthy and self.engine.sglang_alive()):
            return await respond_error(send, 503, 'runtime requires restart')
        return await super().__call__(scope, receive, send)


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


def sglang_command(checkpoint, port, quantization):
    if quantization not in QUANTIZATIONS:
        raise RuntimeError(f'LINDEN_QUANTIZATION must be one of {sorted(QUANTIZATIONS)}')
    return [sys.executable, '-m', 'sglang.launch_server', '--model-path', checkpoint, '--served-model-name', 'm',
            '--tp', '1', '--host', '127.0.0.1', '--port', str(port), '--mem-fraction-static', '0.85',
            # One token beyond the prompt limit: each request also asks for the scored label token.
            '--context-length', str(MAX_TOKENS + 1), '--chunked-prefill-size', str(MAX_TOKENS),
            '--enable-fp32-lm-head', *QUANTIZATIONS[quantization]]


def start_sglang(checkpoint, quantization):
    import requests

    port = free_port()
    # The checkpoint is local; the engine must not reach the Hub or run checkpoint code.
    environment = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
    process = subprocess.Popen(sglang_command(checkpoint, port, quantization), env=environment,
                               stdin=subprocess.DEVNULL, preexec_fn=die_with_parent)
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


def snapshot(cache):
    from huggingface_hub import snapshot_download

    if len(REVISION) != 40:
        raise RuntimeError('linden-1 revision is not pinned')
    # Weights, tokenizer and configuration only: no code from the model repository runs.
    return snapshot_download(MODEL, revision=REVISION, cache_dir=cache,
                             allow_patterns=['*.json', '*.safetensors', '*.jinja'])


def load(checkpoint, quantization):
    import requests
    from transformers import AutoTokenizer

    process, url = start_sglang(checkpoint, quantization)
    renderer = prompt.Renderer(AutoTokenizer.from_pretrained(checkpoint))
    session = requests.Session()
    session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=ACTIVE_REQUESTS * 2))
    sglang = SGLang(url, session, requests.HTTPError)
    return Engine(renderer, sglang, lambda: process.poll() is None)


def warm(engine):
    started = time.perf_counter()
    questions = {
        'delayed': {'type': 'noul', 'instructions': 'Is the shipment delayed?'},
        'route': {'type': 'choice', 'instructions': 'Choose a desk.',
                  'criteria': {'shipping': 'Shipping delays', 'billing': 'Payments'}},
        'urgency': {'type': 'score', 'instructions': 'Rate urgency.', 'criteria': ['routine', 'urgent']}}
    # Short (read twice), one question, and long (read once with the question header) requests.
    for state, asked in (('The shipment is delayed.', questions),
                         ('The shipment is delayed.', {'delayed': questions['delayed']}),
                         ({'ticket': 'The shipment is delayed. ' * 700}, questions)):
        engine.answer({'model': MODEL, 'state': state, 'questions': asked})
    log.info('Runtime warmup completed in %.3fs', time.perf_counter() - started)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--token-file', type=Path)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    token = read_token(args.token_file) if args.token_file is not None else None
    checkpoint = snapshot(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface')))
    engine = load(checkpoint, os.environ.get('LINDEN_QUANTIZATION', 'none'))
    warm(engine)
    import uvicorn
    uvicorn.run(RuntimeApp(engine, token), host='127.0.0.1', port=args.port,
                workers=1, limit_concurrency=64, timeout_keep_alive=5, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
