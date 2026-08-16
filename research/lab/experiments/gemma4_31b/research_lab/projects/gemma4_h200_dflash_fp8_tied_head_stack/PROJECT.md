# DFlash plus captured FP8 tied-head stack

## Question

Can the measured captured-graph E4M3 target vocabulary head be composed with
the pinned Gemma 4 DFlash runtime without changing tied BF16 embedding,
full-vocabulary greedy semantics, draft/target ownership, or graph replay
state?

## Why this matters

The current campaign target is at most `0.500119281574996 s/request` from the
quality-qualified `0.625149101968745 s/request` denominator. The active
DFlash experiment is the main 20%-class route, but its fresh H200
materialization is long. An independent researcher can prepare a likely
stackable follow-up without delaying or inspecting that owner.

The prior exact H200 target-head endpoint was positive: its real
`M=32, K=5,376, N=262,144` consumer reduced median head latency from
`0.7148479819` to `0.4155679941 ms`, preserved BF16 embedding and logits,
used every required padded CUDA-graph shape with zero BF16 fallback, and
measured `0.6518282820` versus `0.6556567115 s/request` at c32, a `0.5839%`
endpoint reduction. This is an incremental candidate, not a standalone 20%
claim. Its current value is cheap composition with DFlash, not replay of its
settled endpoint.

## Bound evidence

Mechanically verify `DIRECTOR_BINDING.json` and every named hash before work.
The authoritative inputs are:

- the current DFlash fresh-H200 director binding and its pinned target, draft,
  SGLang commit, adapter packet, and launcher;
- the immutable compact archive and typed terminal of the positive captured
  E4M3 tied-head endpoint;
- the current campaign denominator and target.

Do not inspect the live DFlash owner directory, remote H200, H100 project, or
provider state.

## Scope

Trace the exact pinned DFlash target and draft logits consumers, tied
`embed_tokens` alias, full-vocabulary shard indices, CUDA-graph capture and
replay outputs, target-verification ownership, and greedy sampling boundary.
Port only the prior separate-storage E4M3 target-head representation into a
project-local immutable source overlay.

Pass deterministic source and CPU-safe fixtures proving:

- BF16 target embedding remains unchanged and tied;
- E4M3 projection storage is separate and target-only;
- draft-head adapter and target-head ownership cannot alias;
- full-vocabulary indices, boundary tokens, and ties are preserved;
- BF16 logits, softcap, sampler inputs, and padded graph shapes remain valid;
- cancellation, completion, empty/partial acceptance, and slot reuse cannot
  retain stale head or graph state;
- unsupported source topology fails closed.

Persist `DFLASH_FP8_TIED_HEAD_STACK_RESULT.json`,
`DFLASH_FP8_TIED_HEAD_STACK_DECISION.md`, and a content-addressed source and
fixture manifest. A positive result must include one runnable conditional
overlay/launcher amendment for later use on the existing H200 only after the
active DFlash diagnostic passes. A localized incompatibility is also a valid
terminal.

## Limits

- Priority: 8470.
- Researcher profile: `deep`.
- Spend: `$0`; no provider, GPU, checkpoint, or remote bench access.
- Local storage: at most 3 GiB.
- Deadline: `2026-07-25T17:00:00Z`.
- Do not replay any old component or endpoint, and do not create a readiness-
  only successor.
