"""Project-local grammar-safe speculative routing hook for the pinned runtime."""

from __future__ import annotations

from sglang.srt.managers import schedule_batch


_original_init_new = schedule_batch.ScheduleBatch.init_new.__func__


def _init_new_with_grammar_fallback(cls, reqs, *args, **kwargs):
    spec_algorithm = kwargs.get("spec_algorithm")
    if spec_algorithm is None and len(args) >= 6:
        spec_algorithm = args[5]
    if any(getattr(req, "grammar", None) for req in reqs):
        if "spec_algorithm" in kwargs:
            kwargs["spec_algorithm"] = type(spec_algorithm).NONE
        elif len(args) >= 6:
            args = list(args)
            args[5] = type(spec_algorithm).NONE
        else:
            raise RuntimeError("grammar_route_missing_spec_algorithm")
    return _original_init_new(cls, reqs, *args, **kwargs)


schedule_batch.ScheduleBatch.init_new = classmethod(_init_new_with_grammar_fallback)

if __import__("os").environ.get("TOKEN_TRACE_EVENTS"):
    from token_trace_hook import install as _install_token_trace

    _install_token_trace()
