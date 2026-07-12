from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import run_task_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--dataset-script", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--validation-jsonl", type=Path, required=True)
    parser.add_argument("--validation-labels", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, required=True)
    arguments = parser.parse_args()
    summary = run_task_validation(
        config_path=arguments.config,
        dataset_script_path=arguments.dataset_script,
        archive_path=arguments.archive,
        validation_jsonl_path=arguments.validation_jsonl,
        validation_labels_path=arguments.validation_labels,
        raw_output_path=arguments.raw_output,
    )
    arguments.summary_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.summary_output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
