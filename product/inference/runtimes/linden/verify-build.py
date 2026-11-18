"""Check the packaged runtime without a GPU: pins, imports, bundled FlashInfer kernels and answer formats."""
import hashlib
import json
from pathlib import Path
import re
import sys

import flashinfer
import flashinfer_jit_cache  # noqa: F401  prebuilt ops, so a B300 start compiles nothing
import sglang
import transformers
import uvicorn  # noqa: F401

import prompt
import service

assert re.fullmatch(r'[0-9a-f]{40}', service.REVISION), 'pin the gradiated/linden-1 Hub revision in service.py'
assert service.MODEL == 'gradiated/linden-1'
assert sglang.__version__ == '0.5.21', sglang.__version__
assert transformers.__version__ == '5.12.1', transformers.__version__
assert flashinfer.__version__ == '0.6.18', flashinfer.__version__
assert (Path(sys.base_prefix) / 'include/python3.12/Python.h').is_file()
assert service.sglang_command('/m', 1, 'fp8')[-2:] == ['--quantization', 'fp8']
assert '--quantization' not in service.sglang_command('/m', 1, 'none')
assert not any(Path('.').glob('knowline*')), 'no KnowLine code ships in the bundle'

manifest = json.loads(Path('artifacts.json').read_text())
assert manifest['flashinfer_version'] == flashinfer.__version__
for item in manifest['files']:
    data = (Path('flashinfer-artifacts') / item['path']).read_bytes()
    assert len(data) == item['size'] and hashlib.sha256(data).hexdigest() == item['sha256'], item['path']

# Every label softmax gives an answer the gateway accepts, for every type and option count.
for kind in ('choice', 'score', 'noul'):
    for count in range(1 if kind in ('choice', 'score') else 2, 65):
        question = {'type': kind, 'instructions': 'q', 'criteria': (
            {f'o{i}': None for i in range(count)} if kind == 'choice'
            else [f'level {i}' for i in range(count)] if kind == 'score' else None)}
        if kind == 'noul' and count > 2:
            break
        if prompt.single_outcome(question):
            answers = [prompt.certain(question)]
        else:
            keys, _ = prompt.options(question)
            answers = [prompt.answer(question, keys, row) for row in ([0.0] * len(keys), [-float(i) for i in range(len(keys))])]
        for answer in answers:
            answer = json.loads(json.dumps(answer, allow_nan=False))
            assert service.valid_answer(answer, question), (kind, count)
print('Packaged linden-1 runtime: pins, imports, FlashInfer kernels and answer formats verified.')
