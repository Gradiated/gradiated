import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

try:
    import xgrammar as xgr
    from vllm.v1.structured_output import backend_xgrammar as backend
except ImportError:
    if os.environ.get('GRADIATED_REQUIRE_GLM_GRAMMAR') == '1':
        raise
    backend = None

if backend and os.environ.get('GRADIATED_GLM_GRAMMAR_BACKEND'):
    source = Path(os.environ['GRADIATED_GLM_GRAMMAR_BACKEND'])
    spec = importlib.util.spec_from_file_location('glm_grammar_candidate', source)
    backend = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = backend
    spec.loader.exec_module(backend)


@unittest.skipUnless(backend, 'requires the pinned vLLM and XGrammar runtime')
class GrammarDiagnosticsTest(unittest.TestCase):
    def grammar(self, *, additional_stop=True):
        vocab = ['{', '}', '"x"', ':', '[', ']', '1', '<eos>', '<user>']
        info = xgr.TokenizerInfo(vocab, xgr.VocabType.RAW, stop_token_ids=[7])
        ctx = xgr.GrammarCompiler(info).compile_json_schema('{"type":"object"}')
        stops = [7, 8] if additional_stop else None
        matcher = xgr.GrammarMatcher(ctx, override_stop_tokens=stops,
                                     max_rollback_tokens=2)
        return backend.XgrammarGrammar(vocab_size=len(vocab), matcher=matcher, ctx=ctx)

    def rejection(self, grammar, tokens):
        with patch.object(backend.logger, 'error') as error:
            self.assertFalse(grammar.accept_tokens('synthetic-request', tokens))
        error.assert_called_once()
        template, *args = error.call_args.args
        return template % tuple(args)

    def test_incomplete_json_reports_configured_stop_rejection(self):
        grammar = self.grammar()
        self.assertTrue(grammar.accept_tokens('synthetic-request', [0, 2, 3, 4]))
        message = self.rejection(grammar, [6, 8])
        self.assertIn('grammar_complete=False', message)
        self.assertIn('grammar_terminated=False', message)
        self.assertIn('configured_stop_token=True', message)
        self.assertIn('processed_tokens=5', message)
        self.assertIn('block_size=2 token_offset=1 caller=rejection', message)
        self.assertNotIn('{"type"', message)
        self.assertNotIn('"x"', message)

    def test_complete_json_distinguishes_a_missing_stop_override(self):
        grammar = self.grammar(additional_stop=False)
        self.assertTrue(grammar.accept_tokens('synthetic-request', [0, 2, 3, 4, 6, 5, 1]))
        message = self.rejection(grammar, [8])
        self.assertIn('grammar_complete=True', message)
        self.assertIn('configured_stop_token=False', message)

    def test_valid_stop_and_speculative_rollback_keep_existing_behavior(self):
        grammar = self.grammar()
        self.assertTrue(grammar.accept_tokens('synthetic-request', [0, 2, 3, 4, 6]))
        with patch.object(backend.logger, 'error') as error:
            self.assertEqual(grammar.validate_tokens([5, 1]), [5, 1])
            self.assertFalse(grammar.is_terminated())
            self.assertTrue(grammar.accept_tokens('synthetic-request', [5, 1]))
            grammar.rollback(2)
            self.assertTrue(grammar.accept_tokens('synthetic-request', [5, 1, 8]))
            self.assertTrue(grammar.is_terminated())
            self.assertTrue(grammar.accept_tokens('synthetic-request', [6]))
        error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
