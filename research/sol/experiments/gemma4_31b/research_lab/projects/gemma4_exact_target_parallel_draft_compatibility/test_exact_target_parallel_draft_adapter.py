from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from exact_target_parallel_draft_adapter import (
    ContractError,
    atomic_write_json,
    consume_exact_greedy_chain,
    run_fixture,
)


ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT / "fixtures/dflash_chain_fixture.json").read_text())


class ExactTargetParallelDraftAdapterTest(unittest.TestCase):
    def test_fixture_executes_acceptance_and_kv_consumer(self) -> None:
        payload = run_fixture(copy.deepcopy(FIXTURE))
        self.assertTrue(payload["all_checks_pass"])
        rows = payload["result"]["rows"]
        self.assertEqual([row["accepted_drafts"] for row in rows], [15, 0, 2, 7])
        self.assertEqual([row["commit_length"] for row in rows], [16, 1, 3, 8])
        self.assertEqual(rows[1]["emitted_tokens"], [299])
        self.assertEqual(rows[2]["emitted_tokens"], [301, 302, 303])
        self.assertEqual(rows[2]["committed_input_tokens"], [300, 301, 302])
        self.assertEqual(rows[2]["committed_verify_kv_slots"], [3000, 3001, 3002])
        self.assertEqual(rows[2]["freed_verify_kv_slots"][0], 3003)
        self.assertEqual(rows[2]["new_kv_committed_length"], 4303)

    def test_unaccepted_suffix_cannot_change_output_or_commit(self) -> None:
        original = run_fixture(copy.deepcopy(FIXTURE))
        mutated = copy.deepcopy(FIXTURE)
        mutated["proposals"][2][4:] = list(range(250000, 250012))
        changed = run_fixture(mutated)
        self.assertEqual(
            original["result"]["rows"][2],
            changed["result"]["rows"][2],
        )

    def test_every_block16_acceptance_boundary(self) -> None:
        for accepted in range(16):
            proposal = [1000 + i for i in range(16)]
            target = [1001 + i for i in range(16)]
            if accepted < 15:
                proposal[accepted + 1] = 2000 + accepted
            result = consume_exact_greedy_chain(
                proposals=[proposal],
                target_top1=[target],
                current_tokens=[1000],
                prefix_kv_lengths=[4214],
                verify_kv_slots=[list(range(5000, 5016))],
                target_vocab_size=262144,
                required_block_size=16,
            )
            row = result.rows[0]
            self.assertEqual(row.accepted_drafts, accepted)
            self.assertEqual(row.commit_length, accepted + 1)
            self.assertEqual(len(row.emitted_tokens), accepted + 1)
            self.assertEqual(row.emitted_tokens[-1], target[accepted])
            self.assertEqual(
                row.committed_verify_kv_slots,
                tuple(range(5000, 5000 + accepted + 1)),
            )
            self.assertEqual(
                row.freed_verify_kv_slots,
                tuple(range(5000 + accepted + 1, 5016)),
            )

    def test_first_target_mismatch_replaces_draft_with_bonus(self) -> None:
        result = consume_exact_greedy_chain(
            proposals=[[10, 11, 12, 13]],
            target_top1=[[99, 98, 97, 96]],
            current_tokens=[10],
            prefix_kv_lengths=[5],
            verify_kv_slots=[[50, 51, 52, 53]],
            target_vocab_size=262144,
            required_block_size=4,
        )
        row = result.rows[0]
        self.assertEqual(row.accepted_drafts, 0)
        self.assertEqual(row.emitted_tokens, (99,))
        self.assertEqual(row.committed_input_tokens, (10,))
        self.assertEqual(row.committed_verify_kv_slots, (50,))
        self.assertEqual(row.freed_verify_kv_slots, (51, 52, 53))

    def test_rejects_current_token_identity_mutation(self) -> None:
        mutated = copy.deepcopy(FIXTURE)
        mutated["current_tokens"][0] += 1
        with self.assertRaisesRegex(ContractError, "is not current token"):
            run_fixture(mutated)

    def test_rejects_shape_mutation(self) -> None:
        mutated = copy.deepcopy(FIXTURE)
        mutated["target_top1"][0].pop()
        with self.assertRaisesRegex(ContractError, "width"):
            run_fixture(mutated)

    def test_rejects_vocab_mutation(self) -> None:
        mutated = copy.deepcopy(FIXTURE)
        mutated["proposals"][0][3] = 262144
        with self.assertRaisesRegex(ContractError, "outside"):
            run_fixture(mutated)

    def test_rejects_aliasing_verify_slots(self) -> None:
        mutated = copy.deepcopy(FIXTURE)
        mutated["verify_kv_slots"][0][1] = mutated["verify_kv_slots"][0][0]
        with self.assertRaisesRegex(ContractError, "must be unique"):
            run_fixture(mutated)

    def test_atomic_output_is_parseable(self) -> None:
        payload = run_fixture(copy.deepcopy(FIXTURE))
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "result.json"
            atomic_write_json(output, payload)
            self.assertEqual(json.loads(output.read_text()), payload)
            self.assertFalse(output.with_suffix(".json.part").exists())


if __name__ == "__main__":
    unittest.main()
