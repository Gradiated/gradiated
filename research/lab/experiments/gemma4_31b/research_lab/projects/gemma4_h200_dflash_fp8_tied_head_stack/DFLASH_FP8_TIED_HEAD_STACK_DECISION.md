# DFlash plus FP8 tied-head stack decision

Decision: do not nominate the H200 follow-up from the current binding.

The source trace found a narrow composition seam. DFlash draft proposals read
the tied BF16 `lm_head.weight` directly, while target verification reaches
`LogitsProcessor._compute_lm_head` inside the captured target forward. The
overlay therefore keeps `embed_tokens` and draft projection BF16, adds a
separate E4M3 target-only projection, returns BF16 full-vocabulary logits, and
owns no request or slot state. CUDA replay slices logits and captured hidden
states to `raw_bs * 16` before verification, so padded rows are not consumers.

The deterministic offline fixtures pass ownership, full-vocabulary
boundary/tie, softcap, padded-shape, cancellation, completion, empty/partial
acceptance, slot-reuse, conditional-launch, and fail-closed cases. They are
offline contract evidence only: no CUDA path, performance result, quality
result, checkpoint, or remote owner was used.

The terminal is nevertheless a localized negative because the recursive
binding audit found one false digest. The exact pinned commit hashes
`dflash_accept_bonus.py` to
`422ffbd00b54913f3d9c14d2596ffd79e51800b6565dc0de78603a36dbd6fdce`;
`DRAFT_RUNTIME_BINDING.json` declares the value ending in `6fd4e`. The other
48 file and archive-member checks pass. Under the required fail-closed
contract, the runnable conditional launcher remains preserved but
non-nominatable until the director rebinds that source identity and the real
DFlash diagnostic gate passes.
