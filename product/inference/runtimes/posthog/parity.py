"""Parity of a deployed PostHog decision runtime with PostHog's reference outputs.

Replays the 46 cases of PostHog/hogference's tests/reference.json for the model (jev/ for posthog/jevk5, generated
with upstream jevk5 0.3.2 in bf16; jeeves/ for posthog/jeeves, generated with Jeeves's own runtime in bf16, no
thinking), one question per request, and fails (exit 1) if any probability moves by more than --max-dp or the top
answer changes on a clear decision (a reference top-two margin of at least 2 * --max-dp). The defaults are
hogference's own gates: 0.08 for JevK5 and 0.15 for Jeeves (its FP8 weights move near-ties by up to ~0.13).

It needs a running runtime, so a GPU. Through the gateway, pinned to one deployment:

    GRADIATED_API_KEY=... python3 product/inference/runtimes/posthog/parity.py --model posthog/jevk5 \\
        --url https://api.gradiated.com --deployment-id "$POD_UID"

or straight at a runtime's loopback port on its host (no key, no pin): --url http://127.0.0.1:$RUNTIME_PORT.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

RUNTIMES = Path(__file__).resolve().parent.parent
FIXTURES = {'posthog/jevk5': (RUNTIMES / 'jevk5/reference.json', 0.08),
            'posthog/jeeves': (RUNTIMES / 'jeeves/reference.json', 0.15)}
DEPLOYMENT_HEADER = 'x-gradiated-deployment-id'


def question(case_question):
    """The fixture's question as the gateway accepts it: PostHog's servers also take a choice's criteria as a list of
    names, which mean {name: null}."""
    q = dict(case_question)
    if q['type'] == 'choice' and isinstance(q.get('criteria'), list):
        q['criteria'] = dict.fromkeys(q['criteria'])
    return q


def request(model, case):
    return {'model': model, 'state': case['state'], 'questions': {'q': question(case['question'])}}


def served(answer, case_question):
    """The answer's probabilities in the fixture's order: noul [true, false]; a choice's criteria in order; a score's
    levels. Keyed reads, because the gateway does not keep the runtime's key order."""
    q = question(case_question)
    if answer['type'] == 'noul':
        return [answer['noul'], 1 - answer['noul']]
    keys = list(q['criteria']) if q['type'] == 'choice' else [str(i) for i in range(len(q['criteria']))]
    return [answer['probabilities'][key] for key in keys]


def post(url, body, key, deployment):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = f'Bearer {key}'
    if deployment:
        headers[DEPLOYMENT_HEADER] = deployment
    req = urllib.request.Request(f'{url.rstrip("/")}/v1/systemone', json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=120) as response:
        if deployment and response.headers.get(DEPLOYMENT_HEADER) != deployment:
            raise RuntimeError(f'the response came from deployment {response.headers.get(DEPLOYMENT_HEADER)!r}')
        return json.load(response)


def compare(cases, answers, max_dp):
    """-> (report lines, failures)."""
    lines, worst, dps, flips, bad = [], 0.0, [], 0, 0
    for i, (case, got) in enumerate(zip(cases, answers)):
        ref = case['probabilities']
        dp = max(abs(a - b) for a, b in zip(ref, got))
        worst, dps = max(worst, dp), dps + [dp]
        top = sorted(ref, reverse=True)
        flipped = ref.index(max(ref)) != got.index(max(got))
        near_tie = top[0] - top[1] < 2 * max_dp
        flips += flipped
        shown = f'case {i} ({case["input_tokens"]} reference tokens): ref={ref} got={[round(x, 4) for x in got]}'
        if flipped and near_tie:
            lines.append(f'flip on uncertain {shown}')
        if dp > max_dp or (flipped and not near_tie):
            bad += 1
            lines.append(f'FAIL {shown}')
    lines.append(f'{len(cases)} cases: max |dp| {worst:.4f}, mean |dp| {sum(dps) / len(dps):.4f}, '
                 f'top-answer changes {flips}, failures {bad}')
    return lines, bad


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--model', required=True, choices=sorted(FIXTURES))
    parser.add_argument('--url', default='https://api.gradiated.com')
    parser.add_argument('--deployment-id', help=f'pin every request to this deployment ({DEPLOYMENT_HEADER})')
    parser.add_argument('--max-dp', type=float)
    args = parser.parse_args(argv)
    fixture, default_dp = FIXTURES[args.model]
    cases = json.loads(fixture.read_text())['cases']
    key = os.environ.get('GRADIATED_API_KEY')
    answers = []
    for i, case in enumerate(cases):
        try:
            result = post(args.url, request(args.model, case), key, args.deployment_id)
        except urllib.error.HTTPError as exc:
            print(f'case {i}: HTTP {exc.code} {exc.read()[:500]!r}', file=sys.stderr)
            return 1
        answers.append(served(result['answers']['q'], case['question']))
        if result['usage']['input_tokens'] != case['input_tokens']:
            print(f'case {i}: {result["usage"]["input_tokens"]} input tokens, reference {case["input_tokens"]}')
    lines, bad = compare(cases, answers, args.max_dp if args.max_dp is not None else default_dp)
    print('\n'.join(lines))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
