# Research log

## 2026-07-25 — offline composition terminal

- Question: can the prior separate-storage E4M3 target head compose with pinned
  DFlash without changing BF16 embedding/draft ownership or graph/verification
  state?
- Action: verified the director input chain and archive members; checked out
  exact SGLang `588d1f7bc9424201f89957e145f9d5af633a3eb8`; traced target and
  draft logits, tied embedding, full-vocabulary indices, captured replay,
  verification, and sampling; ported a target-only overlay and a gated
  conditional launcher; ran deterministic CPU-safe fixtures.
- Evidence: `DFLASH_FP8_TIED_HEAD_STACK_FIXTURES.json` passes 1,048,576
  full-vocabulary logit comparisons, boundary/tie tokens, DFlash graph M
  `16..512`, lifecycle/acceptance/slot reuse, source anchors, and fail-closed
  mutation. `DIRECTOR_BINDING_VERIFICATION.json` passes 48/49 checks.
- Interpretation: the ownership seam is source-compatible offline, but the
  bound digest for pinned `dflash_accept_bonus.py` is wrong (`...6fd4e`
  declared versus `...6fdce` observed). This is a localized binding metadata
  defect, not GPU or scientific evidence.
- Next: director rebinds the exact source digest; rerun the mechanical verifier.
  Only after a fully passing binding and the real DFlash diagnostic gate may
  `conditional_fp8_stack_launcher.sh` enter a sequential existing-H200 run.
  No performance or quality claim was made.
- Invalid local attempt: the first manifest-builder invocation exited before
  writing an artifact because two Python booleans were lowercase. Corrected
  only that serializer defect and reran it; no producer or scientific sample
  was consumed.

## 2026-07-25 — director-authorized source-identity correction

- Question: does the unchanged source-complete stack pass after correcting only
  the false `dflash_accept_bonus.py` digest in a project-local identity?
- Action: restored every artifact bound by
  `DIRECTOR_SOURCE_IDENTITY_CORRECTION_BINDING.json` to its exact admitted
  bytes, preserved the active DFlash project's runtime binding unchanged,
  materialized `DRAFT_RUNTIME_BINDING_CORRECTED_LOCAL.json`, proved its object
  diff contains only the authorized digest leaf, and reran recursive
  verification plus the deterministic fixtures.
- Evidence: all seven correction-bound inputs match; all 49 recursive checks
  pass; the corrected fixture output is byte-identical to the original passing
  output (`964d31d...`); overlay, bootstrap, and conditional-launcher hashes are
  unchanged.
- Interpretation: the prior negative was exhausted by a localized metadata
  repair. The offline composition is source-complete and verified, with no GPU
  compatibility, performance, or quality claim.
- Next: wait for the active DFlash project's real diagnostic terminal. This
  project did not inspect its owner and does not nominate or execute an H200
  follow-up.
