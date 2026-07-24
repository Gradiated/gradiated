from __future__ import annotations

import os


if os.environ.get("VARIABLE_NGRAM_COMPACTION") == "1":
    from variable_decode_lm_head import install

    install()
elif os.environ.get("CONTROL_DECODE_EQ_LM_HEAD") == "1":
    from decode_equivalent_lm_head import install

    install()
