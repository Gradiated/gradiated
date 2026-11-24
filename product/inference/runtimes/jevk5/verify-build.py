"""Check the packaged posthog/jevk5 runtime without a GPU: pins, imports, SGLang flags and answer formats."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import flashinfer
import flashinfer_jit_cache  # noqa: F401  prebuilt FlashInfer ops, so a start compiles none of them
import sglang
from sglang.srt.server_args import ServerArgs
import transformers
import uvicorn  # noqa: F401

import jevk5_prompt
import posthog_common as common
import service

assert re.fullmatch(r'[0-9a-f]{40}', service.REVISION), 'pin the alibiserikbay/JevK5 Hub revision in service.py'
assert (service.MODEL, service.CHECKPOINT) == ('posthog/jevk5', 'alibiserikbay/JevK5')
assert hashlib.sha256(Path('jevk5_prompt.py').read_bytes()).hexdigest() == service.UPSTREAM_PROMPT_SHA256
assert Path('LICENSE.jevk5').is_file() and Path('NOTICE.jevk5').is_file()
assert sglang.__version__ == '0.5.21', sglang.__version__
assert transformers.__version__ == '5.12.1', transformers.__version__
assert flashinfer.__version__ == '0.6.18', flashinfer.__version__
assert (Path(sys.base_prefix) / 'include/python3.12/Python.h').is_file()

# SGLang serves JevK5ForCausalLM, Qwen3.5 text with GatedDeltaNet layers that loads the checkpoint's
# model.language_model.* weight names, and accepts every flag.
models = Path(importlib.util.find_spec('sglang.srt.models.qwen3_5_text').origin).read_text()
assert 'class Qwen3_5ForCausalLM' in models and 'EntryClass = [Qwen3_5MoeForCausalLM, Qwen3_5ForCausalLM]' in models
sys.path.insert(0, str(Path(__file__).resolve().parent))
from jevk5_sglang.model import EntryClass, VL_PREFIX  # noqa: E402
assert EntryClass.__name__ == 'JevK5ForCausalLM' and VL_PREFIX == 'model.language_model.'
assert service.sglang_environment(Path('/r')) == {'SGLANG_EXTERNAL_MODEL_PACKAGE': 'jevk5_sglang', 'PYTHONPATH': '/r'}
parser = argparse.ArgumentParser()
ServerArgs.add_cli_args(parser)
args = parser.parse_args(service.sglang_command('/m', 1)[3:])
assert args.context_length == service.MAX_TOKENS + 1 and args.enable_fp32_lm_head and args.skip_server_warmup
assert not args.disable_radix_cache and args.mamba_radix_cache_strategy == 'extra_buffer'
assert args.disable_overlap_schedule
assert json.loads(args.json_model_override_args) == {'architectures': ['JevK5ForCausalLM']}
assert (args.cuda_graph_backend_decode, args.cuda_graph_backend_prefill) == ('disabled', 'breakable')
assert args.cuda_graph_bs_prefill == [int(x) for x in common.PREFILL_CUDA_GRAPH_SIZES]

from sglang.srt.arg_groups.overrides import _MAMBA_RADIX_CACHE_ARCHS, _MAMBA_EXTRA_BUFFER_ARCHS  # noqa: E402
assert 'JevK5ForCausalLM' in _MAMBA_RADIX_CACHE_ARCHS & _MAMBA_EXTRA_BUFFER_ARCHS

# Every distribution gives an answer the gateway accepts, for every type and option count.
for kind in ('choice', 'score', 'noul'):
    for count in range(1 if kind != 'noul' else 2, 256 if kind != 'noul' else 3):
        question = {'type': kind, 'instructions': 'q', 'criteria': (
            {f'o{i}': None for i in range(count)} if kind == 'choice'
            else [f'level {i}' for i in range(count)] if kind == 'score' else None)}
        keys = [key for key, _ in service.options(question)]
        for logits in ([0.0] * count, [-float(i) for i in range(count)]):
            answer = common.answer(question, dict(zip(keys, common.softmax(logits))),
                                   service.legend(question) if kind == 'score' else None)
            answer = json.loads(json.dumps(answer, allow_nan=False))
            assert common.valid_answer(answer, question), (kind, count)
assert jevk5_prompt.LETTERS == 'ABCDEFGHIJKLMNOP'
print('Packaged posthog/jevk5 runtime: pins, imports, SGLang flags and answer formats verified.')
