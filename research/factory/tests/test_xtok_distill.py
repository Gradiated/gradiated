from __future__ import annotations

import importlib.util
import json
import os
import unittest
from pathlib import Path

from grad_research.xtok_distill import (
    DSML,
    AlignedSpan,
    FieldSpan,
    ParseError,
    align,
    coverage,
    offsets_from_pieces,
    parse_deepseek_output,
    render_k3_completion,
    token_advantages,
)

TOKENIZER_DIR = os.environ.get("XTOK_TOKENIZER_DIR")

K3_PATTERN = "|".join(
    [
        r"""[\p{Han}]+""",
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]*[\p{Ll}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]+[\p{Ll}\p{Lm}\p{Lo}\p{M}&&[^\p{Han}]]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
        r"""\p{N}{1,3}""",
        r""" ?[^\s\p{L}\p{N}]+[\r\n]*""",
        r"""\s*[\r\n]+""",
        r"""\s+(?!\S)""",
        r"""\s+""",
    ]
)
HOGQL = "SELECT count() FROM events WHERE event = '$pageview'\nAND timestamp > now() - INTERVAL 7 DAY"
QUERY = '{"kind":"TrendsQuery","series":[{"event":"$pageview","math":"dau"}]}'
STUDENT = (
    "Weekly pageviews first."
    "</think>"
    "Checking pageviews."
    f"\n\n<{DSML} calls>\n"
    f'<{DSML} invoke name="execute_sql">\n'
    f'<{DSML} parameter name="query" string="true">{HOGQL}</{DSML} parameter>\n'
    f'<{DSML} parameter name="limit" string="false">20</{DSML} parameter>\n'
    f"</{DSML} invoke>\n"
    f'<{DSML} invoke name="create_insight">\n'
    f'<{DSML} parameter name="query" string="false">{QUERY}</{DSML} parameter>\n'
    f"</{DSML} invoke>\n"
    f"</{DSML} calls>"
    "<｜end▁of▁sentence｜>"
)


def field_texts(text, fields):
    return {field.field: text[field.start : field.end] for field in fields}


class ParseAndRenderTests(unittest.TestCase):
    def test_fields_carry_identical_text_in_both_renderings(self):
        turn, student_fields = parse_deepseek_output(STUDENT, thinking=True)
        rendering = render_k3_completion(turn, thinking=True)
        student = field_texts(STUDENT, student_fields)
        teacher = field_texts(rendering.text, rendering.fields)
        self.assertEqual(student, teacher)
        self.assertEqual(HOGQL, student["call0.arg0.value"])
        self.assertEqual("create_insight", student["call1.name"])
        self.assertEqual(QUERY, student["call1.arg0.value"])

    def test_argument_types_follow_the_json_literal(self):
        turn, _ = parse_deepseek_output(STUDENT, thinking=True)
        text = render_k3_completion(turn, thinking=True).text
        self.assertIn('argument key="query" type="string"<|sep|>SELECT', text)
        self.assertIn('argument key="limit" type="number"<|sep|>20', text)
        self.assertIn('argument key="query" type="object"<|sep|>{"kind"', text)

    def test_answer_without_calls_or_thinking(self):
        turn, fields = parse_deepseek_output("Done.<｜end▁of▁sentence｜>", thinking=False)
        self.assertEqual(((), "Done."), (turn.calls, turn.content))
        self.assertEqual([FieldSpan("content", 0, 5)], list(fields))
        self.assertTrue(render_k3_completion(turn, thinking=False).text.startswith("Done.<|close|>response"))

    def test_malformed_call_block_is_rejected(self):
        broken = f"x</think>y\n\n<{DSML} calls>\n<{DSML} invoke name=\"a\">\njunk\n</{DSML} invoke>\n</{DSML} calls>"
        with self.assertRaises(ParseError):
            parse_deepseek_output(broken, thinking=True)

    def test_escaped_attribute_is_not_a_field(self):
        turn, _ = parse_deepseek_output(
            f'</think>\n\n<{DSML} calls>\n<{DSML} invoke name="a&b">\n\n</{DSML} invoke>\n</{DSML} calls>',
            thinking=True,
        )
        rendering = render_k3_completion(turn, thinking=True)
        self.assertNotIn("call0.name", {field.field for field in rendering.fields})


class AlignTests(unittest.TestCase):
    def test_spans_merge_until_both_boundaries_agree(self):
        student_fields = [FieldSpan("content", 2, 11)]
        teacher_fields = [FieldSpan("content", 5, 14)]
        student = offsets_from_pieces(["<>", "abc", "de", "f", "ghi", "</"])
        teacher = offsets_from_pieces(["<tpl>", "ab", "cde", "fg", "hi", "<"])
        spans = align(student, student_fields, teacher, teacher_fields)
        self.assertEqual(
            [AlignedSpan("content", range(1, 3), range(1, 3)), AlignedSpan("content", range(3, 5), range(3, 5))],
            spans,
        )

    def test_token_straddling_a_field_edge_is_left_out(self):
        student_fields = [FieldSpan("content", 0, 6)]
        teacher_fields = [FieldSpan("content", 0, 6)]
        student = offsets_from_pieces(["abc", "def<"])
        teacher = offsets_from_pieces(["abc", "def", "<"])
        spans = align(student, student_fields, teacher, teacher_fields)
        self.assertEqual([AlignedSpan("content", range(0, 1), range(0, 1))], spans)
        self.assertAlmostEqual(0.5, coverage(spans, 2))

    def test_advantage_splits_span_reverse_kl_over_student_tokens(self):
        spans = [AlignedSpan("content", range(0, 2), range(0, 1))]
        advantages = token_advantages(spans, [-1.0, -0.5, -9.0], [-2.5])
        self.assertEqual([-0.5, -0.5, None], advantages)


@unittest.skipUnless(TOKENIZER_DIR, "set XTOK_TOKENIZER_DIR to the downloaded K3 and DeepSeek tokenizer files")
class RealTokenizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import base64

        import tiktoken
        from tokenizers import Tokenizer

        root = Path(TOKENIZER_DIR)
        ranks = {}
        for line in (root / "kimi.tiktoken.model").read_bytes().splitlines():
            if line.strip():
                token, rank = line.split()
                ranks[base64.b64decode(token)] = int(rank)
        cls.kimi = tiktoken.Encoding("kimi", pat_str=K3_PATTERN, mergeable_ranks=ranks, special_tokens={})
        cls.deepseek = Tokenizer.from_file(str(root / "deepseek-ai_DeepSeek-V4.1-Flash.tokenizer.json"))

    def teacher_offsets(self, rendering):
        offsets, position = [], 0
        for segment in rendering.segments:
            if segment.special:
                offsets.append((position, position + len(segment.text)))
            else:
                data, consumed, start = segment.text.encode(), 0, position
                for token in self.kimi.encode_ordinary(segment.text):
                    consumed += len(self.kimi.decode_single_token_bytes(token))
                    end = position + len(data[:consumed].decode(errors="ignore"))
                    offsets.append((start, end))
                    start = end
            position += len(segment.text)
        return offsets

    @unittest.skipUnless(os.environ.get("XTOK_RUN_K3_ENCODER"), "set XTOK_RUN_K3_ENCODER=1 to execute K3's encoding_k3.py")
    def test_rendering_matches_reference_encoder(self):
        spec = importlib.util.spec_from_file_location("encoding_k3", Path(TOKENIZER_DIR) / "kimi.encoding_k3.py")
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
        turn, _ = parse_deepseek_output(STUDENT, thinking=True)
        rendering = render_k3_completion(turn, thinking=True)
        message = {
            "role": "assistant",
            "reasoning_content": turn.reasoning,
            "content": turn.content,
            "tool_calls": [
                {
                    "function": {
                        "name": call.name,
                        "arguments": "{" + ",".join(
                            json.dumps(argument.key) + ":" + (json.dumps(argument.text) if argument.is_string else argument.text)
                            for argument in call.arguments
                        ) + "}",
                    }
                }
                for call in turn.calls
            ],
        }
        prompt = reference.build_chat_segments([{"role": "user", "content": "q"}], add_generation_prompt=True)
        full = reference.build_chat_segments([{"role": "user", "content": "q"}, message], add_generation_prompt=False)
        prompt_text = "".join(segment.text for segment in prompt)
        full_text = "".join(segment.text for segment in full)
        self.assertTrue(full_text.startswith(prompt_text))
        self.assertEqual(full_text[len(prompt_text) :], rendering.text)

    def test_most_student_tokens_get_teacher_signal(self):
        turn, student_fields = parse_deepseek_output(STUDENT, thinking=True)
        rendering = render_k3_completion(turn, thinking=True)
        encoding = self.deepseek.encode(STUDENT, add_special_tokens=False)
        spans = align(encoding.offsets, student_fields, self.teacher_offsets(rendering), rendering.fields)
        content_tokens = [
            index
            for index, (start, end) in enumerate(encoding.offsets)
            if any(field.start <= start < end <= field.end for field in student_fields)
        ]
        self.assertGreater(len(spans), 0)
        self.assertGreater(coverage(spans, len(content_tokens)), 0.85)


if __name__ == "__main__":
    unittest.main()
