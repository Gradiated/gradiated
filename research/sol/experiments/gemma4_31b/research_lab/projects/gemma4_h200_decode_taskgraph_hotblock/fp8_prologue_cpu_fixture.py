#!/usr/bin/env python3
"""Lifecycle-pure scalar fixture for row-scale/indexing/saturation semantics."""

from __future__ import annotations

import json
import math

FP8_MAX = 448.0


def scale(row):
    return max(max(abs(float(x)) for x in row), 1.0e-12) / FP8_MAX


def quant(row, row_scale):
    return [max(-FP8_MAX, min(FP8_MAX, float(x) / row_scale)) for x in row]


def main() -> None:
    rows = [
        [0.0, 0.0, 0.0, 0.0, 0.0],
        [1.0e-8, -2.0e-8, 3.0e-8, -4.0e-8, 5.0e-8],
        [1.0, -2.0, 3.0, -4.0, 5.0],
    ]
    scales = [scale(row) for row in rows]
    encoded = [quant(row, scales[i]) for i, row in enumerate(rows)]
    assert all(math.isfinite(v) for row in encoded for v in row)
    assert encoded[0] == [0.0] * 5
    assert max(abs(v) for v in encoded[1]) == FP8_MAX
    assert max(abs(v) for v in encoded[2]) == FP8_MAX
    wrong = [quant(row, scales[(i + 1) % len(rows)]) for i, row in enumerate(rows)]
    assert wrong != encoded
    print(
        json.dumps(
            {
                "pass": True,
                "rows": len(rows),
                "columns": len(rows[0]),
                "scales": scales,
                "zero_guard": True,
                "saturation": FP8_MAX,
                "negative_control_wrong_row_scale_diverged": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
