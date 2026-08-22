from __future__ import annotations

import sys

import gated_activation_fp8_exact_rounding as revised_candidate


sys.modules["gated_activation_fp8_decode"] = revised_candidate

from h200_runner import main


if __name__ == "__main__":
    raise SystemExit(main())
