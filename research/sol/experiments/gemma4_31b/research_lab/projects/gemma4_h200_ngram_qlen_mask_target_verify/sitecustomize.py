from __future__ import annotations

import os


if os.environ.get("DECODE_EQ_LM_HEAD") == "1":
    from decode_equivalent_lm_head import install as _install_decode_equivalent

    _install_decode_equivalent()

