from __future__ import annotations

import os


if os.environ.get("SGLANG_DFLASH_FP8_TIED_HEAD") == "1":
    from dflash_fp8_tied_head_stack import install

    install()
