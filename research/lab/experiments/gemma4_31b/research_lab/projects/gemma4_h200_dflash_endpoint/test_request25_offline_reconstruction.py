#!/usr/bin/env python3

import unittest

import request25_offline_reconstruction as reconstruction


class RequestPoolOwnershipTest(unittest.TestCase):
    def test_logical_row_maps_to_physical_slot(self) -> None:
        row, slot = reconstruction.select_request_row(
            ["other", "request-25"], [3, 41], "request-25"
        )
        self.assertEqual((row, slot), (1, 41))

    def test_pool_prefix_uses_slot_not_logical_row(self) -> None:
        pool = [[row * 10 + col for col in range(5)] for row in range(45)]
        self.assertEqual(
            reconstruction.read_request_prefix(pool, slot=41, seq_len=3),
            [410, 411, 412],
        )

    def test_ambiguous_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            reconstruction.select_request_row(["request-25", "request-25"], [1, 2], "request-25")

    def test_mismatched_vectors_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "equal length"):
            reconstruction.select_request_row(["request-25"], [1, 2], "request-25")

    def test_request_driver_does_not_persist_raw_stream(self) -> None:
        source = (reconstruction.PROJECT_ROOT / "request25_single_request.py").read_text()
        self.assertFalse(reconstruction.request_driver_retains_raw_bytes(source))

    def test_repaired_observer_compiles_and_uses_owner_pool(self) -> None:
        source = (
            reconstruction.RETRIEVED / "observer" / "sitecustomize.py"
        ).read_text()
        repaired = reconstruction.build_repaired_observer(source)
        self.assertNotIn(
            "forward.req_to_token_pool.req_to_token",
            repaired,
        )
        self.assertIn(
            "worker.target_worker.model_runner.req_to_token_pool.req_to_token",
            repaired,
        )


if __name__ == "__main__":
    unittest.main()
