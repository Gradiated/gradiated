import unittest

import global_kv_host_prefetch as model


class GlobalKVHostPrefetchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geometry = model.geometry()
        cls.trace = model.build_trace(cls.geometry)
        cls.memory = model.build_memory(cls.geometry)

    def test_exact_model_geometry(self):
        self.assertEqual(
            self.geometry["global_layer_ids"],
            [5, 11, 17, 23, 29, 35, 41, 47, 53, 59],
        )
        self.assertEqual(self.geometry["row_bytes"], 4096)
        self.assertEqual(self.geometry["peak_physical_rows"], 129687)

    def test_exact_decode_steps_and_endpoints(self):
        rows = [row for row in self.trace["rows"] if row["phase"] == "decode"]
        self.assertEqual(self.geometry["decode_forwards"], 357)
        self.assertEqual(rows[0]["cached_rows_h2d"], 118263)
        self.assertEqual(rows[-1]["cached_rows_h2d"], 129655)

    def test_decode_byte_sum(self):
        self.assertEqual(
            self.trace["totals"]["decode_h2d_bytes_exact"],
            1_812_617_748_480,
        )
        self.assertEqual(
            self.trace["totals"]["decode_d2h_bytes_exact"],
            467_927_040,
        )

    def test_fixed_two_buffer_layer_ahead_assignment(self):
        for row in self.trace["rows"]:
            self.assertEqual(row["buffer"], row["global_layer_rank"] % 2)
            self.assertTrue(row["consumer_waits_for_h2d_event"])

    def test_memory_reconciliation(self):
        self.assertEqual(self.memory["global_padding_bytes"], 40_960)
        self.assertEqual(self.memory["two_staging_buffers_bytes"], 1_062_404_096)
        self.assertEqual(
            self.memory["device_bytes_saved_before_new_metadata"],
            4_249_616_384,
        )

    def test_absolute_payload_ceiling_still_fails(self):
        seconds = (
            self.trace["totals"]["decode_h2d_bytes_exact"]
            / model.PCIE_PAYLOAD_CEILING_BYTES_S
            / self.geometry["concurrency"]
        )
        self.assertAlmostEqual(seconds, 1.797792871875)
        self.assertGreater(seconds, model.SERVICE_BOUNDARY_S)


if __name__ == "__main__":
    unittest.main()
