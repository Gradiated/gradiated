"""Check the packaged posthog/jeeves runtime without a GPU: pins, imports, the SGLang interfaces the pointer-head model
relies on, SGLang flags and answer formats."""
import argparse
import importlib.util
import json
from pathlib import Path
import py_compile
import re
import sys

import flashinfer
import flashinfer_jit_cache  # noqa: F401  prebuilt FlashInfer ops, so a start compiles none of them
import sglang
from sglang.srt.server_args import ServerArgs
import transformers
import uvicorn  # noqa: F401

from jeeves_sglang import readout
import jeeves_prompt as prompt
import posthog_common as common
import service

assert re.fullmatch(r'[0-9a-f]{40}', service.REVISION), 'pin the PostHog/jeeves-fp8 Hub revision in service.py'
assert (service.MODEL, service.CHECKPOINT) == ('posthog/jeeves', 'PostHog/jeeves-fp8')
assert sglang.__version__ == '0.5.21', sglang.__version__
assert transformers.__version__ == '5.12.1', transformers.__version__
assert flashinfer.__version__ == '0.6.18', flashinfer.__version__
assert (Path(sys.base_prefix) / 'include/python3.12/Python.h').is_file()


def source(module):
    return Path(importlib.util.find_spec(module).origin).read_text()


# jeeves_sglang/model.py builds on these SGLang 0.5.21 interfaces; a different SGLang must be checked again on a GPU.
assert 'SGLANG_EXTERNAL_MODEL_PACKAGE' in source('sglang.srt.models.registry')
text_model = source('sglang.srt.models.qwen3_5_text')
assert 'class Qwen3_5ForCausalLM' in text_model and 'self.lm_head = self.model.embed_tokens' in text_model
logits = source('sglang.srt.layers.logits_processor')
assert 'logits = lm_head.quant_method.apply(' in logits, 'the logits processor no longer applies a quant method head'
batch = source('sglang.srt.model_executor.forward_batch_info')
assert 'extend_seq_lens_cpu' in batch and 'extend_prefix_lens_cpu' in batch
assert 'def is_extend(' in batch
assert 'class QuantizeMethodBase' in source('sglang.srt.layers.quantization.base_config')
assert 'Qwen3_5Config' in source('sglang.srt.configs.hybrid_arch')
py_compile.compile('jeeves_sglang/model.py', doraise=True)

parser = argparse.ArgumentParser()
ServerArgs.add_cli_args(parser)
args = parser.parse_args(service.sglang_command('/m', 1)[3:])
assert args.disable_radix_cache and args.chunked_prefill_size == -1 and args.skip_server_warmup
assert args.max_prefill_tokens == service.MAX_TOKENS + 1 and args.context_length == service.MAX_TOKENS + 1
assert (args.cuda_graph_backend_decode, args.cuda_graph_backend_prefill) == ('disabled', 'disabled')
assert readout.MAX_OPTIONS == 255

# Every distribution gives an answer the gateway accepts, for every type and option count.
for kind in ('choice', 'score', 'noul'):
    for count in range(1 if kind != 'noul' else 2, 256 if kind != 'noul' else 3):
        question = {'type': kind, 'instructions': 'q', 'criteria': (
            {f'o{i}': None for i in range(count)} if kind == 'choice'
            else [f'level {i}' for i in range(count)] if kind == 'score' else None)}
        keys = prompt.keys(question)
        for scores in ([0.0] * count, [-float(i) for i in range(count)]):
            answer = common.answer(question, dict(zip(keys, common.softmax(scores))), service.Engine.legend(question))
            answer = json.loads(json.dumps(answer, allow_nan=False))
            assert common.valid_answer(answer, question), (kind, count)
print('Packaged posthog/jeeves runtime: pins, imports, SGLang interfaces and flags, and answer formats verified.')
