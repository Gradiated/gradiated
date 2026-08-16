#!/usr/bin/env python3
from __future__ import annotations

import unittest

import numpy as np

import awq_to_qserve as converter


def pack_awq(values: np.ndarray) -> np.ndarray:
    semantic_to_packed = np.argsort(converter.AWQ_ORDER)
    ordered = values.reshape(values.shape[0], values.shape[1] // 8, 8)[
        ..., semantic_to_packed
    ]
    packed = np.zeros(ordered.shape[:-1], dtype=np.uint32)
    for index in range(8):
        packed |= ordered[..., index].astype(np.uint32) << np.uint32(4 * index)
    return packed.view(np.int32)


def float32_to_bfloat16(values: np.ndarray) -> np.ndarray:
    return (values.astype(np.float32).view(np.uint32) >> np.uint32(16)).astype(np.uint16)


class ConverterTest(unittest.TestCase):
    def test_awq_unpack(self) -> None:
        values = np.arange(32, dtype=np.uint8).reshape(2, 16) & np.uint8(15)
        self.assertTrue(np.array_equal(converter.unpack_awq_words(pack_awq(values)), values))

    def test_qserve_pack_round_trip(self) -> None:
        values = (
            np.arange(64 * 128, dtype=np.uint32).reshape(64, 128) * 7 + 3
        ).astype(np.uint8) & np.uint8(15)
        packed = converter.qserve_pack_codes(values)
        self.assertTrue(np.array_equal(converter.qserve_unpack_codes(packed), values))

    def test_group_metadata_round_trip(self) -> None:
        values = np.arange(64 * 5, dtype=np.int16).reshape(64, 5)
        packed = converter.qserve_reorder_group_metadata(values)
        self.assertTrue(
            np.array_equal(converter.qserve_restore_group_metadata(packed), values)
        )

    def test_exact_progressive_factor(self) -> None:
        s1 = np.asarray((2**-10, 2**-9), dtype=np.float16)
        stage2 = np.asarray(((1, 2), (3, 4), (5, 6)), dtype=np.uint64)
        scales = s1.astype(np.float32)[None, :] * stage2.astype(np.float32)
        bits = float32_to_bfloat16(scales)
        observed_s1, observed_stage2, exact = converter.exact_progressive_factor(
            bits, np.ones_like(bits, dtype=bool)
        )
        self.assertTrue(exact.all())
        self.assertTrue(
            np.array_equal(
                observed_s1.astype(np.float64)[None, :]
                * observed_stage2.astype(np.float64),
                converter.bfloat16_to_float64(bits),
            )
        )

    def test_incompatible_progressive_factor(self) -> None:
        values = np.asarray((129, 131), dtype=np.float32) * np.float32(2**-15)
        bits = float32_to_bfloat16(values[:, None])
        _, ratios, exact = converter.exact_progressive_factor(
            bits, np.ones_like(bits, dtype=bool)
        )
        self.assertGreater(int(ratios.max()), 127)
        self.assertTrue(exact.all())


if __name__ == "__main__":
    unittest.main()
