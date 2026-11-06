import ast
import copy
import os
from pathlib import Path
import sys
import types
import unittest

from pydantic import BaseModel, model_serializer

SOURCE = Path(os.environ['KIMI_INSTALLED_SOURCE'])
PATH = SOURCE / 'sglang/srt/entrypoints/openai/serving_chat.py'
OPENAI = PATH.parent


def load_actual_methods(path):
    protocol = ast.parse((OPENAI/'protocol.py').read_text())
    usage = ast.parse((OPENAI/'usage_processor.py').read_text())
    chat = ast.parse(path.read_text())
    cls = next(n for n in chat.body if isinstance(n, ast.ClassDef) and n.name == 'OpenAIServingChat')
    selected = {'_reported_prompt_tokens', '_reported_cached_tokens', '_usage_headers', '_k3_usage', '_apply_k3_usage_details'}
    body = [copy.deepcopy(n) for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in selected]
    body.extend(copy.deepcopy(n) for n in cls.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == '_KIMI_K3_GENERATION_STUB_TOKENS' for t in n.targets))
    build = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_build_chat_response')
    normalize = next(n for n in build.body if isinstance(n, ast.If))
    args = lambda names: ast.arguments(posonlyargs=[], args=[ast.arg(arg=n) for n in names], kwonlyargs=[], kw_defaults=[], defaults=[])
    body.append(ast.FunctionDef(name='normalize_ret', args=args(['self', 'ret']), body=[copy.deepcopy(normalize),
                              ast.Return(value=ast.Name(id='ret', ctx=ast.Load()))], decorator_list=[]))
    stream = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_generate_chat_stream')
    collect = next(n for n in ast.walk(stream) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Subscript)
        and isinstance(t.value, ast.Name) and t.value.id == 'cached_tokens' for t in n.targets))
    body.append(ast.FunctionDef(name='collect_cached', args=args(['self', 'content', 'index', 'cached_tokens']),
                              body=[copy.deepcopy(collect), ast.Return(value=copy.deepcopy(collect.targets[0]))], decorator_list=[]))
    body[-1].body[-1].value.ctx = ast.Load()
    classes = [copy.deepcopy(n) for n in protocol.body if isinstance(n, ast.ClassDef)
               and n.name in {'PromptTokensDetails', 'CompletionTokensDetails', 'UsageInfo'}]
    classes += [copy.deepcopy(n) for n in usage.body if isinstance(n, ast.ClassDef) and n.name == 'UsageProcessor']
    classes.append(ast.ClassDef(name='SUT', bases=[], keywords=[], body=body, decorator_list=[]))
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *classes], type_ignores=[])
    module = types.ModuleType('cache_accounting_actual'); sys.modules[module.__name__] = module
    exec('from typing import *', module.__dict__)
    module.__dict__.update(BaseModel=BaseModel, model_serializer=model_serializer,
        envs=types.SimpleNamespace(SGLANG_USAGE_HEADER_PREFIX=types.SimpleNamespace(get=lambda: 'X-Test')))
    exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), module.__dict__)
    return module


actual = load_actual_methods(PATH)


class CacheBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.handler = actual.SUT(); self.handler.chat_encoding_spec = 'kimi_k3'

    def test_eight_boundary_cases_headers_and_body_agree(self):
        for raw_prompt, raw_cached in [(100, 0), (100, 64), (100, 97), (100, 98),
                                       (100, 99), (100, 100), (100, -1), (2, 2)]:
            with self.subTest(raw_prompt=raw_prompt, raw_cached=raw_cached):
                meta = {'prompt_tokens': raw_prompt, 'cached_tokens': raw_cached}
                prompt = max(0, raw_prompt-3); expected = min(max(raw_cached, 0), prompt)
                body = self.handler._k3_usage(prompt_tokens=prompt, completion_tokens=4, reasoning_tokens=2, cached_tokens=raw_cached)
                headers = self.handler._usage_headers(meta)
                self.assertEqual(body['prompt_tokens_details']['cached_tokens'], expected)
                self.assertEqual(int(headers['X-Test-Cached-Tokens']), expected)
                self.assertEqual(int(headers['X-Test-Prompt-Tokens']), prompt)

    def test_nonstream_batch_clamps_each_prompt_before_sum_and_deduplicates_choices(self):
        for cache_report in (False, True):
            for choices in (1, 2):
                with self.subTest(cache_report=cache_report, choices=choices):
                    raw = [{'meta_info': {'prompt_tokens': p, 'cached_tokens': c, 'completion_tokens': 4, 'reasoning_tokens': 2}}
                           for p, c in [(100, 100), (200, 64)] for _ in range(choices)]
                    normalized = self.handler.normalize_ret(raw)
                    usage = actual.UsageProcessor.calculate_response_usage(normalized, n_choices=choices, enable_cache_report=cache_report)
                    usage = self.handler._apply_k3_usage_details(usage, reasoning_tokens=4*choices,
                        cached_tokens=sum(normalized[i]['meta_info']['cached_tokens'] for i in range(0, len(raw), choices)))
                    self.assertEqual((usage.prompt_tokens, usage.prompt_tokens_details.cached_tokens), (294, 161))
                    self.assertEqual(raw[0]['meta_info']['cached_tokens'], 100)

    def test_stream_batch_clamps_each_prompt_before_sum(self):
        for cache_report in (False, True):
            cache, prompt = {}, {}
            for index, (p, c) in enumerate([(100, 100), (200, 0)]):
                meta = {'prompt_tokens': p, 'cached_tokens': c}
                prompt[index] = self.handler._reported_prompt_tokens(meta)
                self.handler.collect_cached({'meta_info': meta}, index, cache)
            usage = actual.UsageProcessor.calculate_streaming_usage(prompt, {0: 2, 1: 2}, {0: 4, 1: 4},
                        cached_tokens=cache, n_choices=1, enable_cache_report=cache_report)
            usage = self.handler._apply_k3_usage_details(usage, reasoning_tokens=4, cached_tokens=sum(cache.values()))
            self.assertEqual((usage.prompt_tokens, usage.prompt_tokens_details.cached_tokens), (294, 97))

    def test_existing_details_are_clamped_without_losing_multimodal_fields(self):
        usage = actual.UsageInfo(prompt_tokens=97, prompt_tokens_details=actual.PromptTokensDetails(cached_tokens=100, image_tokens=10))
        fixed = self.handler._apply_k3_usage_details(usage, reasoning_tokens=0, cached_tokens=100)
        self.assertEqual((fixed.prompt_tokens_details.cached_tokens, fixed.prompt_tokens_details.image_tokens), (97, 10))

    def test_other_encodings_and_disabled_headers_are_unchanged(self):
        usage = actual.UsageInfo(prompt_tokens=97)
        self.handler.chat_encoding_spec = 'other'
        self.assertIs(self.handler._apply_k3_usage_details(usage, reasoning_tokens=2, cached_tokens=100), usage)
        self.assertIsNone(usage.prompt_tokens_details)
        self.assertEqual(self.handler._usage_headers({'prompt_tokens': 100, 'cached_tokens': 100}), {})
        cache = {}; self.handler.collect_cached({'meta_info': {'cached_tokens': 100}}, 0, cache)
        self.assertEqual(cache, {0: 100})


if __name__ == '__main__':
    unittest.main()
