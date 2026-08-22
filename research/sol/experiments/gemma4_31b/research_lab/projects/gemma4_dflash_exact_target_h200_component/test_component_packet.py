#!/usr/bin/env python3

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


def module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


observer = module("component_observer_under_test", ROOT / "component_observer.py")
worker = module("component_worker_under_test", ROOT / "dflash_component_worker.py")


class PacketTest(unittest.TestCase):
    def test_interval_union(self):
        rows = [
            {"start_ms": 0.0, "end_ms": 4.0},
            {"start_ms": 3.0, "end_ms": 6.0},
            {"start_ms": 8.0, "end_ms": 9.5},
        ]
        self.assertEqual(observer.interval_union_ms(rows), 7.5)

    def test_server_commands_preserve_block_and_controls(self):
        args = tuple(pathlib.Path(f"/x/{index}") for index in range(5))
        for arm in ("ar", "dflash", "ngram"):
            command = worker.server_command(arm, *args, "generation")
            self.assertIn("--page-size", command)
            self.assertEqual(command[command.index("--page-size") + 1], "16")
            if arm == "dflash":
                self.assertIn("--speculative-dflash-block-size", command)
                self.assertEqual(
                    command[command.index("--speculative-dflash-block-size") + 1],
                    "16",
                )
            elif arm == "ngram":
                self.assertIn("NGRAM", command)
            else:
                self.assertNotIn("--speculative-algorithm", command)

    def test_owner_uses_pool_show_and_generation_fenced_release(self):
        source = (ROOT / "dflash_component_owner.py").read_text()
        self.assertIn('pool("show", "--bench", binding["bench_id"])', source)
        self.assertIn('"--expected-claimed-at"', source)
        self.assertNotIn('load(LAB / "runtime" / "gpus.json")', source)
        self.assertIn("repair_wait(", source)

    def test_observer_uses_fixture_validated_mapping(self):
        source = (ROOT / "component_observer.py").read_text()
        self.assertIn('"ForwardBatch.rids[row]"', source)
        self.assertIn('"ForwardBatch.req_pool_indices[row]"', source)
        self.assertIn(
            '"target_worker.model_runner.req_to_token_pool.req_to_token"', source
        )
        self.assertNotIn("forward.req_to_token_pool", source)

    def test_python_files_parse(self):
        for path in ROOT.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))

    def test_contract_excludes_consumed_request_25(self):
        contract = json.loads((ROOT / "EXPERIMENT_CONTRACT.json").read_text())
        workload = contract["workload"]
        self.assertFalse(workload["historical_request_25_replayed"])
        self.assertFalse(workload["historical_request_25_used_as_evidence"])
        self.assertEqual(workload["draft_block_tokens_including_current"], 16)

    def test_summarizer_consumes_complete_matched_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            outputs = [1000 + index for index in range(358)]
            for arm in ("ar", "dflash", "ngram"):
                arm_root = root / arm
                (arm_root / "results").mkdir(parents=True)
                (arm_root / "observer").mkdir()
                rows = [
                    {
                        "index": index,
                        "error": None,
                        "prompt_tokens": 4214,
                        "completion_tokens": 358,
                        "output_token_ids": outputs,
                    }
                    for index in range(32)
                ]
                (arm_root / "results" / "TERMINAL.json").write_text(
                    json.dumps(
                        {
                            "complete_requests": 32,
                            "workload": {"request_sha256": [f"request-{i}" for i in range(32)]},
                            "rows": rows,
                        }
                    )
                )
                (root / f"{arm}.SCIENCE_STARTED.json").write_text("{}")
                phases = {
                    "ar": ["target_decode"],
                    "dflash": ["draft", "target_verify", "acceptance", "kv_commit"],
                    "ngram": [
                        "ngram_proposal",
                        "target_verify",
                        "acceptance",
                        "kv_commit",
                    ],
                }[arm]
                observer_rows = []
                for index in range(32):
                    accepted = index % 16 if arm != "ar" else 0
                    row = {
                        "arm": arm,
                        "round_index": 1,
                        "row_index": index,
                        "logical_request_id": f"fresh-{index}",
                        "accepted_drafts": accepted,
                        "commit_len": accepted + 1,
                        "cuda_intervals_ms": [
                            {
                                "phase": phase,
                                "start_ms": offset,
                                "end_ms": offset + 0.5,
                                "duration_ms": 0.5,
                            }
                            for offset, phase in enumerate(phases)
                        ],
                        "cuda_interval_union_ms": len(phases) * 0.5,
                        "host_outer_seconds": 0.01,
                    }
                    if arm == "dflash":
                        row.update(
                            {
                                "logical_request_id_source": "ForwardBatch.rids[row]",
                                "physical_request_pool_index_source": "ForwardBatch.req_pool_indices[row]",
                                "kv_table_source": "target_worker.model_runner.req_to_token_pool.req_to_token",
                                "block_size_including_current": 16,
                                "next_round_audit": {
                                    "prior_acceptance_category": (
                                        "zero"
                                        if index == 0
                                        else "full"
                                        if index == 15
                                        else "partial"
                                    ),
                                    "pending_bonus_is_current": True,
                                    "committed_length_continuity": True,
                                    "kv_prefix_stable": True,
                                },
                            }
                        )
                    observer_rows.append(json.dumps(row))
                (arm_root / "observer" / "observer-1.jsonl").write_text(
                    "\n".join(observer_rows) + "\n"
                )
            terminal = root / "terminal.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "summarize_component.py"),
                    "--root",
                    str(root),
                    "--terminal",
                    str(terminal),
                    "--generation",
                    "fixture",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(terminal.read_text())
            self.assertTrue(value["evidence_complete"])
            self.assertTrue(value["correctness"]["semantic_pass"])
            self.assertFalse(value["historical_request_25"]["replayed"])


if __name__ == "__main__":
    unittest.main()
