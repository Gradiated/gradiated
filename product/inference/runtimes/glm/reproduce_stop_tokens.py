#!/usr/bin/env python3
"""Send three bounded synthetic probes to a private GLM runtime."""
import argparse
import json
import time
import urllib.request
import uuid


def probe(url, model, marker, timeout, mask_extra_stops):
    schema = {'type': 'object', 'properties': {
        'marker': {'type': 'string', 'enum': [marker]}},
        'required': ['marker'], 'additionalProperties': False}
    body = {'model': model, 'messages': [{'role': 'user', 'content':
        'Return a JSON object containing the single marker string required by the schema. No explanation.'}],
        'response_format': {'type': 'json_schema', 'json_schema': {
            'name': 'synthetic_marker', 'schema': schema, 'strict': True}},
        'stream': True, 'stream_options': {'include_usage': True, 'continuous_usage_stats': True},
        'max_tokens': 96, 'temperature': 0, 'reasoning_effort': 'low',
        'chat_template_kwargs': {'enable_thinking': True}}
    if mask_extra_stops:
        body['bad_words'] = ['<|user|>', '<|observation|>']
    request_id = 'synthetic-stop-repro-' + uuid.uuid4().hex
    request = urllib.request.Request(url.rstrip('/') + '/v1/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
                                               'X-Request-Id': request_id})
    started = time.monotonic()
    result = {'marker': marker, 'request_id': request_id, 'errors': [],
              'done': False, 'finish_reason': None, 'stop_reason': None}
    content = ''
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for line in response:
                if time.monotonic() - started > timeout:
                    raise TimeoutError()
                if not line.startswith(b'data:'):
                    continue
                data = line[5:].strip()
                if data == b'[DONE]':
                    result['done'] = True
                    break
                event = json.loads(data)
                if 'error' in event:
                    result['errors'].append(event['error'])
                for choice in event.get('choices', []):
                    content += choice.get('delta', {}).get('content') or ''
                    if choice.get('finish_reason'):
                        result['finish_reason'] = choice['finish_reason']
                        result['stop_reason'] = choice.get('stop_reason')
        try:
            result['valid_json'] = json.loads(content) == {'marker': marker}
        except json.JSONDecodeError:
            result['valid_json'] = False
    except Exception as error:
        result['exception'] = type(error).__name__
        result['valid_json'] = False
    result['passed'] = (result['done'] and result['valid_json'] and not result['errors']
                        and result['finish_reason'] == 'stop')
    result['seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Private runtime URL, without /v1')
    parser.add_argument('--model', default='dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4')
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--mask-extra-stops', action='store_true',
        help='Diagnostic control: suppress extra EOS tokens for these requests only')
    args = parser.parse_args()
    if not 0 < args.timeout <= 15:
        parser.error('timeout must be greater than zero and at most 15 seconds')
    results = []
    for marker in ('ordinary-text', '<|user|>', '<|observation|>'):
        result = probe(args.url, args.model, marker, args.timeout, args.mask_extra_stops)
        results.append(result)
        print(json.dumps(result), flush=True)
    return 0 if all(result['passed'] for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
