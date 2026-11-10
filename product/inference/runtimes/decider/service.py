"""Bounded, text-only Decider v1.2 native SystemOne serving."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from kev_http import App, InvalidRequest, respond_error, read_token

MODEL = 'perplexity-ai/pplx-decider-v1.2'
REVISION = 'cce0f3f80033e9d89d80831d5281fd72124aacce'
MAX_TOKENS = 8192


def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def request(data):
    questions = {}
    for key, value in data['questions'].items():
        question = dict(value)
        question['instructions'] = text(question['instructions'])
        criteria = question.get('criteria')
        if isinstance(criteria, dict):
            question['criteria'] = {key: None if value is None else text(value)
                                    for key, value in criteria.items()}
        elif isinstance(criteria, list):
            question['criteria'] = [text(value) for value in criteria]
        questions[key] = question
    # Never forward nested media objects or accept image paths/URLs.
    return {'state': text(data['state']), 'questions': questions}


def probability(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def valid_answer(answer, question):
    if not isinstance(answer, dict) or answer.get('type') != question['type']:
        return False
    if 'confidence' in answer and not probability(answer['confidence']):
        return False
    if question['type'] == 'noul':
        return probability(answer.get('noul'))
    probabilities = answer.get('probabilities')
    expected = (set(question['criteria']) if question['type'] == 'choice'
                else {str(i) for i in range(len(question['criteria']))})
    # The pinned formatter normalizes full-precision floats. The gateway's
    # rounding tolerance is for other runtimes that round individual outcomes.
    if (not isinstance(probabilities, dict) or set(probabilities) != expected
            or not all(probability(value) for value in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > 0.0001):
        return False
    if question['type'] == 'choice':
        return answer.get('choice') in expected
    score = answer.get('score')
    return type(score) in (int, float) and math.isfinite(score) and 0 <= score <= len(expected) - 1


class Engine:
    model = MODEL

    def __init__(self, decider, invalid_errors, sync):
        self.decider, self.invalid_errors, self.sync = decider, invalid_errors, sync
        self.healthy = True

    def answer(self, data):
        if not self.healthy:
            raise RuntimeError('runtime requires restart')
        value = request(data)
        try:
            self.decider.encoder.validate(value)
            encoded = self.decider.encoder.encode(value)
            if encoded.length > MAX_TOKENS:
                raise InvalidRequest('joint prompt exceeds 8192 tokens')
            # Preserve one joint sequence. The upstream default recursively splits
            # over-length question sets; this runtime rejects them before inference.
            result = self.decider.decide(value)
            self.sync()
        except self.invalid_errors:
            raise InvalidRequest('invalid decision request or prompt budget') from None
        except InvalidRequest:
            raise
        except Exception:
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        usage = result.get('usage', {}) if isinstance(result, dict) else {}
        answers = result.get('answers') if isinstance(result, dict) else None
        if (not isinstance(usage, dict) or type(usage.get('input_tokens')) is not int
                or not 0 < usage['input_tokens'] <= MAX_TOKENS
                or type(usage.get('output_tokens')) is not int or usage['output_tokens'] != 0
                or type(usage.get('sequences')) is not int or usage['sequences'] != 1
                or not isinstance(answers, dict) or set(answers) != set(value['questions'])
                or any(not valid_answer(answers[key], question) for key, question in value['questions'].items())):
            self.healthy = False
            raise RuntimeError('invalid decision model output')
        return {'model': MODEL, 'answers': answers, 'usage': {
            'input_tokens': usage['input_tokens'], 'cached_input_tokens': 0, 'output_tokens': 0}}


class RuntimeApp(App):
    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['path'] == '/health' and not self.engine.healthy:
            return await respond_error(send, 503, 'runtime requires restart')
        return await super().__call__(scope, receive, send)


def load(cache):
    import torch
    from huggingface_hub import snapshot_download
    from pplx_decider import Decider, RequestError, LengthError

    checkpoint = snapshot_download(MODEL, revision=REVISION, cache_dir=cache,
        allow_patterns=['*.json', '*.safetensors', '*.jinja', '*.txt'])
    decider = Decider.from_pretrained(checkpoint, device='cuda', fast=False,
                                     max_length=MAX_TOKENS, batch_tokens=MAX_TOKENS)
    converted = [name for name, module in decider.backbone.named_modules()
                 if type(module).__name__ == 'Linear4bit']
    if (len(converted) != 192 or any(not name.startswith('language_model.layers.') or '.mlp.' not in name
                                    for name in converted)):
        raise RuntimeError('runtime requires exactly 192 NF4 decoder MLP projections')
    return Engine(decider, (RequestError, LengthError), torch.cuda.synchronize)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--token-file', type=Path)
    args = parser.parse_args()
    token = read_token(args.token_file) if args.token_file is not None else None
    engine = load(os.environ.get('HF_HOME', str(Path.home() / '.cache/huggingface')))
    engine.answer({'state': 'The shipment is delayed.', 'questions': {
        'delayed': {'type': 'noul', 'instructions': 'Is the shipment delayed?'},
        'route': {'type': 'choice', 'instructions': 'Choose a desk.',
                  'criteria': {'shipping': 'Shipping delays', 'billing': 'Payments'}},
        'urgency': {'type': 'score', 'instructions': 'Rate urgency.', 'criteria': ['routine', 'urgent']}}})
    import uvicorn
    uvicorn.run(RuntimeApp(engine, token), host='127.0.0.1', port=args.port,
                workers=1, access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
