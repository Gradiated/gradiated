# Gemma 4 H200 DFlash endpoint

Issue: #26

Bound SGLang PR #23000 at `588d1f7bc9424201f89957e145f9d5af633a3eb8` and
the DFlash draft at `eabd648301ce28583cc14757912e5e0f84e152e1`. The project
contains a pinned build/launch script, exact c4/c32 AR/DFlash runner, and
token-ID reconciler. Local shell/Python/schema checks pass.

Contract: one independent H200 only; $28 cumulative ceiling; diagnostic then
conditional c32 pair; greedy tokens, request ownership, KV/position state, and
32/32 completion gate acceptance. Waiting only for director registration of an
independent bench; never claim the NGRAM-reserved H200.
