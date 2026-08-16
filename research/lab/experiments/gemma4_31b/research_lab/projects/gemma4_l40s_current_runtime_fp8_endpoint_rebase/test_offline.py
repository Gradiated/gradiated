#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


consumer = load("exact_c32_consumer")


class OfflineContractTest(unittest.TestCase):
    def test_exact_workload_identity(self) -> None:
        workload = json.loads(
            (
                HERE.parent
                / "gemma4_prefill_cuda_graph_padding_rebase/inputs/workload/WORKLOAD.json"
            ).read_text()
        )
        self.assertEqual(
            consumer.canonical(consumer.workload_identity(consumer.request_bodies())),
            consumer.canonical(workload),
        )

    def test_exact_shape_and_generation_contract(self) -> None:
        bodies = consumer.request_bodies()
        self.assertEqual(len(bodies), 32)
        self.assertTrue(all(len(body["prompt"]) == 4214 for body in bodies))
        self.assertTrue(all(body["max_tokens"] == 358 for body in bodies))
        self.assertTrue(all(body["min_tokens"] == 358 for body in bodies))
        self.assertTrue(all(body["ignore_eos"] for body in bodies))
        self.assertTrue(all(body["add_special_tokens"] is False for body in bodies))
        self.assertEqual(
            len({tuple(body["prompt"][:535]) for body in bodies}),
            1,
        )

    def test_owner_has_required_claim_lifecycle_and_repair_contract(self) -> None:
        source = (HERE / "l40s_endpoint_owner.py").read_text()
        for fragment in (
            '"claim"',
            '"heartbeat"',
            '"release"',
            '"--expected-claimed-at"',
            '"--condition"',
            '"maintenance"',
            '"SCIENCE_STARTED.json"',
            '"TERMINAL.json"',
            "repair-handshake",
            '"consumer_and_retrieval_only"',
            "checkpoint_must_be_immutable_project_local_snapshot",
            "deadline_must_equal_2400_seconds",
        ):
            self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
