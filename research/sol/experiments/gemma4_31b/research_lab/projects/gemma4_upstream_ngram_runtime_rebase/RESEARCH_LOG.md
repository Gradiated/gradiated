# Research log

## 2026-07-25 — one upstream runtime nominated

**Question.** Does official upstream contain one newer unmodified runtime with
a causal NGRAM/tree-verification/cache-position change that retains the bound
Gemma 4 31B native FP8 depth-12 path?

**Action.** Mechanically verified all five `DIRECTOR_BINDING.json` inputs,
fetched official SGLang HEAD and stable releases v0.5.14–v0.5.16, traced the
bound Triton NGRAM proposal → tree reconstruction → target verify → accepted-KV
move/commit → request cleanup → Gemma local/global attention → CUDA-graph path,
and froze v0.5.15 plus a 171-request execution packet. No GPU was claimed and
no provider or paid resource was mutated.

**Evidence.**

- Measured/bound: all director input hashes match; the retained support-two
  endpoint is economically positive at `$0.1393159641142523/M` but semantically
  rejects at request 790.
- Source-derived: pinned v0.5.13 uses NGRAM spec-v1, where
  `NgramVerifyInput._free_cache` owns accepted-KV selection/move, request KV
  watermarks, and request-to-token mapping. Upstream commit
  `111009ea542e3430d8eed6e8e99dd8558982699f` replaces that state transition
  with NGRAM spec-v2. Commit
  `854c688121ed29f49bc862fe19357eecd6c72b30` makes the scheduler the single
  owner of full accepted-run KV settlement and adds an ownership guard motivated
  by premature SWA eviction.
- Content identity: selected release commit
  `f63458b5beaceabbd9d749b9fc956370e1b649e6`; official CUDA 12.9 amd64 image
  `docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd`.
  Registry labels bind that image to the selected commit.
- Source support: the frozen source retains native NGRAM with default draft
  depth 12, FP8 quantization, FP8 E5M2 KV, Gemma sliding/global attention,
  Triton target verification, and NGRAM CUDA-graph capture. The packet manifest
  verifies 27 files with zero failures.

**Interpretation.** Nominate exactly v0.5.15. It is the first stable release
with the complete causal state-transition replacement and single-owner
settlement. v0.5.14 is an intermediate bookkeeping state; v0.5.16 and current
HEAD retain the repair but add unrelated drift. This is source-backed
capability, not a claim that semantics or economics transfer across runtimes.

**Next move.** Await separate director spend/bench authorization after the
priority-8500 predecessor releases. Then stage the immutable packet, launch the
digest-pinned image with unchanged bound flags, and run only requests 0–170 at
bound arrivals. Require exact semantics, zero failures, bounded release drift,
and observed native NGRAM acceptance. Only a full pass admits one unmodified
791-request endpoint under the existing `$0.14/M` and queue gates.

Artifacts:

- `DIRECTOR_BINDING_VERIFIED.json`
- `artifacts/candidate-v0.5.15/CANDIDATE_RUNTIME.json`
- `artifacts/candidate-v0.5.15/SOURCE_PATH_CAUSAL_MAP.json`
- `artifacts/candidate-v0.5.15/UPSTREAM_AUDIT.json`
- `artifacts/candidate-v0.5.15/SHA256SUMS.json`
- `remote_runtime_discriminator.py`
