import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from night import train_arm


class NightTest(unittest.TestCase):
    def test_partial_training_is_retained_without_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            job = work / "qwen-4b"
            job.mkdir()
            metadata = job / "train_meta.json"
            metadata.write_text(
                json.dumps(
                    {
                        "complete": False,
                        "step": 25,
                        "config": {"steps": 50},
                        "tokens": 1000,
                    }
                ),
            )
            with (
                patch("night.run") as run,
                patch("night.s3_copy") as upload,
                patch("night.log"),
            ):
                passed = train_arm(
                    "python",
                    work,
                    "4",
                    0,
                    work / "train.jsonl",
                    [],
                    "s3://fixture/partial",
                    100,
                    50,
                )

            self.assertFalse(passed)
            run.assert_called_once()
            upload.assert_called_once_with(
                metadata,
                "s3://fixture/partial/train_meta.json",
                100,
            )
