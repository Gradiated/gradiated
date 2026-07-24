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

## 2026-07-24 — director provisioning

The durable `$20` reservation is fulfilled by registered bench
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`: preemptible Nebius H200 instance
`computeinstance-e00kcm9nfhwt7e7gbc`, 250-GiB disk
`computedisk-e00yvdxaa48q0t115t`, and independent cleanup watchdog
`gemma4-ngram-verifier-h200-20260724t1700-watchdog.service` through `17:00Z`.
The director did not wait for guest readiness or begin setup, CUDA, or a
scientific arm. Claim this exact bench once and retain the claim through
ordinary setup, API, runtime, and retrieval repairs; release by `16:45Z`.

## 2026-07-24 — measured discriminator rejects decode-equivalent LM head

Question: does request-major, draft-depth-sliced tied-LM-head projection make
NGRAM target verification exact while retaining the multi-token verifier?

Action: claimed the dedicated H200, staged and remotely hash-verified all
`62,578,655,208` checkpoint bytes plus the frozen runner/hooks, and pulled the
pinned SGLang image. A first monitoring attempt misparsed unordered systemd
fields and interrupted a control container while it was still Docker
`Created`; retrieved `INVOCATION_STATE.json` was all false with zero request
rows and zero candidate events. The same claim and resident state were kept,
the monitor alone was repaired, and the unchanged workload ran once. Compact
artifacts were retrieved before release. The bench is ready with the exact
checkpoint/image resident and no container or worker active.

Measured evidence: the required candidate symbol and four audit records are
present. `ordinary`, `repeated_pattern`, and `single_tool` were output-token exact
(2/2, 2/2, and 24/24 tokens). `c32_row_00` first diverged at output token 8:
control stopped at 8 tokens while candidate continued to 258 tokens. Therefore
`DISCRIMINATOR_TERMINAL.json` failed and the conditional ten-row token/tool
suite plus matched c32 pair did not start.

Decision: reject the single decode-equivalent tied-LM-head intervention and do
not replay it. This falsifies the hypothesis that projection shape alone
restores exact target verification under the bound cache/position/attention
path. A post-terminal trace audit corrects one non-decision-bearing summary
flag: six unshadowed decode events were counted as candidate/native
disagreements because the native field was null. Across all 54 actual
target-verification events with a native shadow, candidate and native argmax
were exact at all 12 rows. The c32 divergence therefore survives an
argmax-equivalent projection and lies elsewhere in the bound verifier path;
`TRACE_INTERPRETATION.json` preserves the correction. Conservative project exposure is `$1.78`, rounded up from the full
project-specific provider interval `09:27:00Z`–`10:10:11.413128Z`, including
provisioning, setup, the non-scientific integration repair, execution,
retrieval, and resident-metadata handoff.
