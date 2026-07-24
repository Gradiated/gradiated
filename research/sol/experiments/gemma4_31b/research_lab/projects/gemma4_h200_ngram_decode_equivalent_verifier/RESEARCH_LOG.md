# Research log

## 2026-07-24 — director admission

- Native NGRAM's measured `0.5967508053 s/request` passes the H200 economic
  ceiling, but its exact-token failure is real at temperature zero and cannot
  be repaired through RNG accounting, output canonicalization, grammar
  routing, or a settings sweep.
- Admitted one materially new target-verifier mechanism: localize the first
  AR-versus-verification target-logit divergence, then make the verifier use a
  decode-equivalent numerical/cache/attention path while preserving NGRAM
  proposal amortization.
- Provisioning is director-gated until the `$20` reservation is durable. No
  H200 exists yet; prepare the source-bound discriminator and intervention
  offline without weakening the first CUDA call.

## 2026-07-24 — decode-shape verifier bound; pool has no H200

Question: can native NGRAM retain its 60-layer multi-token target-forward
amortization while making the target vocabulary projection numerically
decode-shaped?

Action: inspected the exact cached image source and materialized the admitted
runner, closed control/candidate traces, source files, and all eight checkpoint
files under this project. All `62,578,655,208` checkpoint bytes match the
admitted hashes. Bound one intervention: reshape request-major target-verify
hidden rows and run the tied BF16 LM head once per draft depth at shape
`[bs,5376] x [5376,262144]`, then restore request-major order. The discriminator
computes the native `[bs*12,5376]` projection as a shadow and records input IDs,
cache locations, positions, attention dispatch, graph use, top-two logits,
argmax, accepted indices, and exact symbols. It runs ordinary,
repeated-pattern, single-tool, and c32-row-00 first; only exact output admits
the ten-row suite and matched c32 pair.

Evidence: `INTERVENTION_BINDING.json`, `CHECKPOINT_MANIFEST.json`, and
`remote_experiment.py` are the durable contracts. Three containerized CPU tests
pass for row ordering, graph-buffer reuse, and fail-closed shapes; Python
compilation and `tools/devex/check.py` pass. The atomic H200 claim then exited
2 with `no available GPU bench matches this project`; the current inventory has
zero non-retired benches. `EXTERNAL_BLOCKER.json` preserves the command and
exact required bench. No provider or scientific invocation started and spend
is `$0`.

Interpretation/next: this is a typed external pool boundary, not verifier
evidence and not arm consumption. The director must provision/register one
preemptible 250-GiB `nvidia-h200-sxm` bench for the exact model. On registration,
claim it once, reconcile/stage the immutable local checkpoint and pinned image,
and run the frozen discriminator/conditional program.
