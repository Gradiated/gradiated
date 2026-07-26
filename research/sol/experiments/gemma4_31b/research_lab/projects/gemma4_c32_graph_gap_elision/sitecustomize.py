"""Install exactly one bound NGRAM LM-head intervention and token tracing."""

from __future__ import annotations

import os


if os.environ.get("GROUPED_LM_HEAD") == "1":
    from grouped_lm_head import install as _install_grouped

    _install_grouped()
elif os.environ.get("DECODE_EQ_LM_HEAD") == "1":
    from decode_equivalent_lm_head import install as _install_decode_equivalent

    _install_decode_equivalent()

if os.environ.get("TOKEN_TRACE_EVENTS"):
    from token_trace_hook import install as _install_token_trace

    _install_token_trace()
