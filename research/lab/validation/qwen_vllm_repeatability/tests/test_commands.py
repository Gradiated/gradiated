import unittest
from pathlib import Path
from unittest.mock import patch

from validation.qwen_vllm_repeatability.commands import (
    build_benchmark_command,
    build_server_command,
)
from validation.qwen_vllm_repeatability.tests.test_schema import valid_mapping
from validation.qwen_vllm_repeatability.schema import CampaignSpec
from validation.qwen_vllm_repeatability.runner import _environment


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = CampaignSpec.from_mapping(valid_mapping())

    def test_server_command_is_argument_vector_with_frozen_cpu_controls(self) -> None:
        command = build_server_command(self.spec)

        self.assertEqual(command[0], "/tmp/venv/bin/python")
        self.assertIn("vllm.entrypoints.openai.api_server", command)
        self.assertIn("--enforce-eager", command)
        self.assertIn("--max-num-seqs", command)
        self.assertNotIn("--device", command)
        self.assertNotIn("sh", command)

    def test_benchmark_command_fixes_prompts_burst_and_detailed_output(self) -> None:
        command = build_benchmark_command(
            self.spec,
            concurrency=4,
            prompts_path=Path("/tmp/prompts.jsonl"),
            output_path=Path("/tmp/run.json"),
            request_id_prefix="fixed-c4-r2-warm-",
        )

        self.assertIn("custom", command)
        self.assertIn("--disable-shuffle", command)
        self.assertIn("--skip-chat-template", command)
        self.assertIn("--save-detailed", command)
        self.assertEqual(command[command.index("--max-concurrency") + 1], "4")
        self.assertEqual(command[command.index("--request-rate") + 1], "inf")
        self.assertEqual(
            command[command.index("--extra-body") + 1],
            '{"seed":0,"temperature":0}',
        )

    def test_runtime_environment_does_not_forward_credentials(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "HOME": "/tmp/home",
                "PATH": "/bin",
                "OPENAI_API_KEY": "secret",
                "HF_TOKEN": "secret",
            },
            clear=True,
        ):
            environment = _environment(self.spec)

        self.assertEqual(environment["HOME"], "/tmp/home")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("HF_TOKEN", environment)


if __name__ == "__main__":
    unittest.main()
