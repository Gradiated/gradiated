from __future__ import annotations

import functools

from torch.profiler import record_function


def _wrap(owner: object, name: str, label: str) -> None:
    original = getattr(owner, name)

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        with record_function(label):
            return original(*args, **kwargs)

    setattr(owner, name, wrapped)


def install() -> None:
    from sglang.srt.managers.tp_worker import TpModelWorker
    from sglang.srt.speculative.ngram_info import NgramVerifyInput
    from sglang.srt.speculative.ngram_worker import NGRAMWorker

    _wrap(NGRAMWorker, "_prepare_draft_tokens", "ngram.cpu_corpus_lookup")
    _wrap(
        NGRAMWorker,
        "_prepare_for_speculative_decoding",
        "ngram.draft_mask_and_indices",
    )
    _wrap(NgramVerifyInput, "prepare_for_verify", "ngram.cache_slot_prepare")
    _wrap(NgramVerifyInput, "verify", "ngram.accept_bookkeeping_and_cache")
    _wrap(NGRAMWorker, "_update_ngram_corpus", "ngram.cpu_corpus_update")

    original_forward = TpModelWorker.forward_batch_generation

    @functools.wraps(original_forward)
    def forward_with_verify_range(*args, **kwargs):
        label = (
            "ngram.target_forward_verify"
            if kwargs.get("is_verify", False)
            else "ngram.target_forward_other"
        )
        with record_function(label):
            return original_forward(*args, **kwargs)

    TpModelWorker.forward_batch_generation = forward_with_verify_range
