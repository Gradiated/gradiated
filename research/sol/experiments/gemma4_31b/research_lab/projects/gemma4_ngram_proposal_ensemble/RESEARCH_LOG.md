# Research log

## 2026-07-25 — admitted

The director admitted a zero-cost causal replay because the current NGRAM
candidate is quality-qualified and a 20% additional endpoint gain is more
likely to require fewer target passes than another isolated micro-kernel tweak.
No provider or GPU is authorized in this stage.

## 2026-07-25 — measured causal proposal surface; close

**Question.** Can prompt lookup, current-output multi-order NGRAM, or a
deterministic causal selector remove at least 20% of native depth-12 target
work on both the endpoint geometry and a captured quality scope?

**Action.** Hashed both named primary inputs, reconstructed 198 exact GPQA
prompt/output token rows from the captured response file and the bound Gemma 4
tokenizer (all prompt and completion counts equal captured usage), implemented
the four-method chronological replay, and compiled the pinned v0.5.15 C++ trie
against four branch fixtures. The Python native emulator matched C++ accepted
depths `11, 4, 2, 4`. Proposal functions receive only prompt tokens and the
already-emitted output prefix; target suffixes enter only the verifier.

**Evidence.** On endpoint rows 0..790, native used `23,733` target passes for
`283,178` emitted tokens (`1.005714` fixed target rows/token). Its accepted
draft histogram was `{0:1, 1:1, 3:1, 7:2, 10:790, 11:22938}`: the shared trie
is effectively already at the 11-draft ceiling. The ensemble produced the
identical histogram and target work, while lookup rose from `6.67` to `72.04`
microseconds/token and estimated working set from `117.47` to `871.00` KiB.
Prompt-only regressed to `12.0` fixed rows/token; output-history-only regressed
by `6.65%`.

On 198 captured GPQA rows (`1,158` output tokens), native used `710` passes and
the ensemble `692`, a measured `2.535%` reduction, far below 20%. Ensemble
lookup was `81.05` microseconds/token versus native `33.08`, and estimated
working set was `3.44` MiB versus `3.25` MiB. The complete distributions,
logical/fixed rows, no-match rates, source selections, and per-row arrays are
in `PROPOSAL_ENSEMBLE_RESULT.json` and `artifacts/replay/`.

Two observer-only defects were amended before the canonical consumer: slot
fields were initially omitted from working-set sizing, then sizing was
accidentally included in the lookup timer. Proposal logic and the negative
pass/acceptance surface did not change. Exact attempt hashes and the causal
amendment are retained in `OBSERVER_AMENDMENTS.json`.

**Interpretation and next move.** The synthetic endpoint is repetitive, but
that bias favors output-history proposals and still yields zero gain because
native NGRAM saturates. The independent GPQA surface shows only a small prompt
selector benefit. Close without a runtime patch or GPU spend; preserve the
measured surface as the bound for future workload-specific proposal ideas.
