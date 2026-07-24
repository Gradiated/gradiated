#!/usr/bin/env python3
from __future__ import annotations

import unittest

import numpy as np

import prepare_exact_inputs as producer


class ExactInputProducerTest(unittest.TestCase):
    def test_qserve_pack_round_trip_nonperiodic(self) -> None:
        generator = np.random.default_rng(20260724)
        values = generator.integers(
            0,
            16,
            size=(64, 256),
            dtype=np.uint8,
        )
        packed = producer.qserve_pack_codes(values)
        restored = producer.qserve_unpack_codes(packed)
        self.assertTrue(np.array_equal(restored, values))

    def test_group_metadata_round_trip(self) -> None:
        generator = np.random.default_rng(20260725)
        values = generator.integers(
            0,
            16,
            size=(64, 17),
            dtype=np.uint8,
        )
        packed = producer.qserve_reorder_group_metadata(values)
        restored = producer.qserve_restore_group_metadata(packed)
        self.assertTrue(np.array_equal(restored, values))


if __name__ == "__main__":
    unittest.main()
