import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

try:
    from tokenizers import Tokenizer, decoders, models
    from transformers import PreTrainedTokenizerFast
    import xgrammar as xgr
    from vllm.v1.structured_output import backend_xgrammar as backend
    from vllm.v1.structured_output.backend_types import StructuredOutputOptions
except ImportError:
    if os.environ.get('GRADIATED_REQUIRE_GLM_GRAMMAR') == '1':
        raise
    backend = None

if backend and os.environ.get('GRADIATED_GLM_GRAMMAR_BACKEND'):
    source = Path(os.environ['GRADIATED_GLM_GRAMMAR_BACKEND'])
    spec = importlib.util.spec_from_file_location('glm_grammar_stop_candidate', source)
    backend = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = backend
    spec.loader.exec_module(backend)


@unittest.skipUnless(backend, 'requires the pinned vLLM and XGrammar runtime')
class GrammarStopTokensTest(unittest.TestCase):
    def grammar(self, model_eos):
        vocab = {'{': 0, '}': 1, '"': 2, 'x': 3, ':': 4, 'a': 5,
                 '<eos>': 6, 'USER_STOP': 7, 'OBS_STOP': 8, '<unk>': 9}
        # Mixed valid/invalid pieces reproduce the GLM mask path; U+0100 decodes to NUL.
        for token in range(10, 64):
            piece = f'valid{token}' if token < 32 else f'\u0100invalid{token}'
            vocab[piece] = token
        tokenizer = Tokenizer(models.BPE(vocab=vocab, merges=[], unk_token='<unk>'))
        tokenizer.decoder = decoders.ByteLevel()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=tokenizer,
            eos_token='<eos>', unk_token='<unk>')
        generation = {} if model_eos is None else {'eos_token_id': model_eos}
        config = SimpleNamespace(
            model_config=SimpleNamespace(try_get_generation_config=lambda: generation),
            structured_outputs_config=SimpleNamespace(disable_any_whitespace=False),
            speculative_config=SimpleNamespace(num_speculative_tokens=2))
        compiler = backend.XgrammarBackend(config, tokenizer, len(vocab))
        stops = {6}
        if isinstance(model_eos, list):
            stops.update(model_eos)
        elif model_eos is not None:
            stops.add(model_eos)
        return compiler.compile_grammar(StructuredOutputOptions.JSON_OBJECT, '', stops)

    def allowed(self, grammar, token, row=0):
        mask = xgr.allocate_token_bitmask(3, grammar.vocab_size)
        grammar.fill_bitmask(mask, row)
        return bool((int(mask[row, token >> 5]) >> (token & 31)) & 1)

    def test_model_stop_tokens_cannot_leak_into_an_unfinished_json_string(self):
        for stop in (7, 8):
            with self.subTest(stop=stop):
                grammar = self.grammar([6, 7, 8])
                self.assertTrue(grammar.accept_tokens('synthetic', [0, 2, 3, 2, 4, 2]))
                self.assertFalse(grammar.matcher.is_completed())
                for row in range(3):
                    self.assertFalse(self.allowed(grammar, stop, row))
                self.assertFalse(grammar.matcher.accept_token(stop))

    def test_all_model_stop_tokens_remain_valid_after_json_completion(self):
        for stop in (6, 7, 8):
            with self.subTest(stop=stop):
                grammar = self.grammar([6, 7, 8])
                self.assertTrue(grammar.accept_tokens('synthetic', [0, 2, 3, 2, 4, 2, 5, 2, 1]))
                self.assertTrue(grammar.matcher.is_completed())
                self.assertTrue(self.allowed(grammar, stop))
                self.assertTrue(grammar.accept_tokens('synthetic', [stop]))
                self.assertTrue(grammar.is_terminated())

    def test_scalar_eos_is_combined_with_the_tokenizer_eos(self):
        grammar = self.grammar(7)
        self.assertTrue(grammar.accept_tokens('synthetic', [0, 2, 3, 2, 4, 2]))
        self.assertFalse(self.allowed(grammar, 6))
        self.assertFalse(self.allowed(grammar, 7))
        self.assertTrue(self.allowed(grammar, 8))

    def test_tokens_without_stop_semantics_remain_valid_string_content(self):
        grammar = self.grammar(None)
        self.assertTrue(grammar.accept_tokens('synthetic', [0, 2, 3, 2, 4, 2]))
        self.assertTrue(self.allowed(grammar, 7))
        self.assertTrue(grammar.accept_tokens('synthetic', [7, 2, 1, 6]))

    def test_speculative_validation_and_rollback_preserve_stop_masking(self):
        grammar = self.grammar([6, 7, 8])
        self.assertTrue(grammar.accept_tokens('synthetic', [0, 2, 3, 2, 4, 2, 5]))
        self.assertEqual(grammar.validate_tokens([2, 1]), [2, 1])
        self.assertFalse(self.allowed(grammar, 7))
        self.assertTrue(grammar.accept_tokens('synthetic', [2, 1]))
        self.assertTrue(self.allowed(grammar, 7))
        grammar.rollback(2)
        self.assertFalse(self.allowed(grammar, 7))


if __name__ == '__main__':
    unittest.main()
