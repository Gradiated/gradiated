import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("analyze_l2_residency.py")
SPEC = importlib.util.spec_from_file_location("l2_model", MODULE_PATH)
MODEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL)


class ResidencyModelTest(unittest.TestCase):
    def test_exact_cadence_and_geometry(self):
        geometry = MODEL.model_geometry()
        self.assertEqual(geometry["layers"], 60)
        self.assertEqual(len(geometry["local_layer_ids"]), 50)
        self.assertEqual(geometry["global_layer_ids"], list(range(5, 60, 6)))
        self.assertEqual(geometry["runtime_prefix_window_tokens"], 1023)
        self.assertEqual(geometry["local_kv_heads"], 16)
        self.assertEqual(geometry["local_head_dim"], 256)
        self.assertEqual(geometry["global_kv_heads"], 4)
        self.assertEqual(geometry["global_head_dim"], 512)

    def test_bound_rows_and_release_groups(self):
        requests = MODEL.request_geometry()
        self.assertEqual(requests["rows"], 1036)
        self.assertEqual(requests["prompt_tokens"], 4214)
        self.assertEqual(requests["completion_tokens"], 358)
        self.assertEqual(
            requests["release_group_size_histogram"], {"12": 1, "32": 32}
        )

    def test_full_batch_defeats_l2_residency(self):
        geometry = MODEL.model_geometry()
        row = MODEL.batch_working_set(geometry, 32, 50)
        self.assertEqual(
            row["local_prefix_hot_mib_per_request_per_layer"], 7.9921875
        )
        self.assertEqual(row["local_prefix_hot_mib_per_layer_batch"], 255.75)
        self.assertTrue(row["paired_query_head_reuse_fits_l2"])
        self.assertLess(
            row["ideal_persistence_plus_all_metadata_upper_fraction"], 0.01
        )

    def test_typed_none_is_reproducible_decision(self):
        result = MODEL.build_result()
        self.assertEqual(result["result"], "typed_none")
        self.assertTrue(result["falsifier"]["candidate_falsified"])
        self.assertFalse(result["typed_none"]["gate_pass"])


if __name__ == "__main__":
    unittest.main()
