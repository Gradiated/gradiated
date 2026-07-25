import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().with_name("analyze_transactions.py")
SPEC = importlib.util.spec_from_file_location("analyze_transactions", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TransactionModelTest(unittest.TestCase):
    def test_exact_request_geometry(self):
        geometry = MODULE.request_geometry()
        self.assertEqual(geometry["rows"], 1036)
        self.assertEqual(
            geometry["release_group_size_histogram"], {"12": 1, "32": 32}
        )

    def test_payload_mapping_is_permutation_invariant(self):
        oracle = MODULE.payload_mapping_oracle()
        for row in oracle["payload_rows"]:
            self.assertEqual(row["sectors_per_k_or_v"], MODULE.WINDOW * 8)
            self.assertEqual(row["transactions_per_k_or_v"], MODULE.WINDOW * 2)

    def test_index_alignment_boundary_waste(self):
        group_32 = MODULE.release_group_alignment(32)
        self.assertEqual(
            group_32["sector_counts_by_request_lane"], {256: 16, 257: 16}
        )
        self.assertEqual(
            group_32["transaction_counts_by_request_lane"], {64: 4, 65: 28}
        )

    def test_result_is_metadata_only_typed_none(self):
        result = MODULE.build_result()
        self.assertEqual(result["result"], "typed_none")
        self.assertIsNone(result["typed_none"]["candidate"])
        for phase in result["transaction_model"]["phases"]:
            reduction = phase["predicted_reduction"]
            self.assertEqual(reduction["payload_sectors_32b"], 0)
            self.assertGreater(reduction["metadata_sectors_32b"], 0)
            self.assertLess(
                reduction["fraction_of_stock_requested_sectors"], 0.016
            )


if __name__ == "__main__":
    unittest.main()
