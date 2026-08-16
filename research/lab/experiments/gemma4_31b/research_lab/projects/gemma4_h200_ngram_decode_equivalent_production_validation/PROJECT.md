# Decode-equivalent NGRAM production validation

## Question

Does the exact H200 decode-equivalent NGRAM endpoint preserve GPQA-Diamond
accuracy and TauBench task success relative to a fresh same-stack
autoregressive control while retaining its measured c32 economic win?

## Evidence and interpretation

The bound endpoint completed 32/32 campaign requests at
`0.625149101968745 s/request`, below the H200 frontier ceiling of
`0.6381105231 s/request`. Its four-row internal discriminator was exact after
cumulative token events were reconstructed, and all 54 native-shadow target
comparisons were argmax-exact.

The ten-row feature suite exposed one representation difference: the
single-tool control emitted compact JSON in 24 token IDs while NGRAM emitted
the same parsed function and arguments as whitespace-formatted JSON in 41
token IDs. Function name, parsed arguments, finish reason, normalized tool
payload, request bytes, and all other rows matched. This closes raw-token
identity for that row, but it is not a semantic product failure. The campaign
requires GPQA-Diamond, TauBench, and production tool behavior before
promotion, and explicitly ranks cost per completed request above byte-level
serialization identity.

`EVIDENCE_BINDING.json` binds the performance terminal, exact launch, licensed
quality request sets, scorer/consumer code, parser bridge, checkpoint, and
runtime identities. Historical FP8 quality scores are context only and must
not be transferred to this NGRAM stack.

## Experiment

After this project's reservation is durable, atomically claim
`h200-ngram-verifier-e00kcm9nfhwt7e7gbc`. Reuse the resident exact checkpoint
and pinned image. Freeze one immutable paid packet before the claim.

Run sequential servers, never concurrent residency:

1. Launch a fresh non-speculative control with byte-identical checkpoint,
   precision, KV cache, attention backends, chunking, graph, parser, and
   request settings. Capture the 198 bound GPQA-Diamond rows and 165 bound
   TauBench rows through the real chat/tool path.
2. Stop and remove the control, require zero accelerator processes and zero
   used HBM, then launch the exact persisted NGRAM candidate and capture the
   same requests once.
3. Score both arms with the bound normalizer and task consumers. Persist raw
   responses, multi-turn state, parsed tool calls, finish reasons, usage,
   output-token counts, per-row latency, failures, reloads, and scorer
   identities before producing one atomic terminal.

The feature gate is parsed semantics and task behavior, not JSON whitespace.
Record raw token and completion-token inflation as economic evidence. Do not
canonicalize candidate output before scoring, suppress whitespace in the
server, change NGRAM settings, tune prompts, alter sampling, or replay the
consumed discriminator/c32 pair.

## Decision gate

Promote the measured NGRAM endpoint as the production candidate only if:

- both arms use the exact bound model, runtime, parser, requests, and scorer;
- all requests are finite and accounted, streaming/non-streaming assembly,
  stop behavior, parser identity, tool arguments, and multi-turn state are
  valid;
- GPQA-Diamond accuracy and TauBench task success show no statistically
  credible material regression in paired bootstrap analysis; use a
  preregistered 3 percentage-point absolute non-inferiority margin for each;
- no candidate-specific critical feature or reliability failure occurs; and
- actual output inflation and observed completion costs do not erase the
  persisted `0.625149101968745 s/request` economic advantage.

A valid regression closes this candidate for production without invalidating
the performance measurement. A control, scorer, parser, retrieval, or
consumer defect is operational evidence to repair in the same uninterrupted
claim without replaying completed captures.

## Resources

- Priority: `6800`
- Researcher profile: `execution`
- Authorized cumulative spend: `$12`
- Compute: one retained H200, at most 150 claimed GPU-minutes
- Wall clock: complete by `2026-07-24T14:45:00Z`
- Storage: at most 18 GiB of new project-local artifacts
- Provider mutation: forbidden
- Release the bench ready with useful caches retained

