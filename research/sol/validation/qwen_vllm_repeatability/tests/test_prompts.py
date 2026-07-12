import tempfile
import unittest
from pathlib import Path

from validation.qwen_vllm_repeatability.prompts import (
    build_prompt_manifest,
    write_prompt_fixture,
)


class PromptTests(unittest.TestCase):
    def test_content_identity_covers_order_and_exact_text(self) -> None:
        prompts = [("alpha", 128, 32), ("beta", 128, 32)]

        first = build_prompt_manifest(prompts, seed=0, generator_revision="a" * 40)
        second = build_prompt_manifest(prompts, seed=0, generator_revision="a" * 40)
        reversed_manifest = build_prompt_manifest(
            list(reversed(prompts)), seed=0, generator_revision="a" * 40
        )

        self.assertEqual(first.content_id, second.content_id)
        self.assertNotEqual(first.content_id, reversed_manifest.content_id)
        self.assertEqual(first.requests[0].request_id, "qwen-fixed-0")
        self.assertEqual(len(first.requests[0].prompt_sha256), 64)

    def test_fixture_is_jsonl_and_roundtrips_exact_prompts(self) -> None:
        manifest = build_prompt_manifest(
            [("line one\nline two", 128, 32)],
            seed=0,
            generator_revision="a" * 40,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.jsonl"

            write_prompt_fixture(manifest, path)

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{"output_tokens":32,"prompt":"line one\\nline two"}\n',
            )


if __name__ == "__main__":
    unittest.main()
