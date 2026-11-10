"""Exercise the packaged upstream formatter without loading GPU weights."""
import json
from pathlib import Path
import sys

import bitsandbytes
import torch
import uvicorn
from pplx_decider.protocol import MAX_OPTIONS, answer

import service

assert service.MAX_TOKENS == 8192
assert (Path(sys.base_prefix) / 'include/python3.12/Python.h').is_file()

for kind in ['choice', 'score']:
    for count in range(1 if kind == 'choice' else 2, MAX_OPTIONS + 1):
        question = {'type': kind, 'criteria': (
            {str(i): None for i in range(count)} if kind == 'choice'
            else [f'level {i}' for i in range(count)])}
        for values in [[1.] * count, [float(i + 1) for i in range(count)]]:
            response = json.loads(json.dumps(answer(question, values), allow_nan=False))
            assert service.valid_answer(response, question), (kind, count)
            assert abs(sum(response['probabilities'].values()) - 1) < 1e-12

thirds = answer({'type': 'choice', 'criteria': {'a': None, 'b': None, 'c': None}}, [1., 1., 1.])
assert thirds['probabilities']['a'] == 1 / 3
print('Packaged formatter preserves normalized full-precision probabilities for all supported option counts.')
