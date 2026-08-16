# Research log

## 2026-07-26T04:25Z — source gate

Decision: admit one profiler-off exact-c32 matched pair. The measured discovery
proxy contains `157856.863 us` of GPU-idle/host-gap time. Static source
localization found a distinct redundant post-verification transfer:
`NgramVerifyInput.verify` has already copied accepted counts to CPU and updated
`ScheduleBatch.seq_lens_cpu`, after which
`NGRAMWorker.forward_batch_generation` copies the same GPU count vector again.

The candidate derives the identical drafts-only count from the CPU sequence
length delta, predicting one fewer D2H synchronization per target-verify step
without changing graph replay, request ownership, tokens, cache allocation, or
serving features. `SOURCE_READY.json` binds the source, launchers, exact
geometry, quality gates, budget, deadline, and terminal contract.

## 2026-07-26T04:31Z — exact pair terminal

The durable owner claimed the named warm H200 at `04:25:58Z`, ran stock then
candidate once, retrieved both producer stages and the pair terminal, stopped
both servers, and released the bench ready at `04:30:47Z`. Conservative
cumulative exposure is `$0.19688220552777783`.

Both arms completed 32/32 with identical request hashes and valid
prompt/completion/cache accounting. The candidate measured
`0.6135780843437715 s/request` versus stock
`0.6183353098438147 s/request` (`-0.76936%`), but the required nonempty
scheduler-to-detokenizer token trace diverged: 17 control and 17 candidate
rows were unmatched by multiset. The apparent `sse_token_ids_exact=true` is
not decision-bearing because all rows returned zero SSE token IDs. Response
hashes also differed at all 32 indices.

Classification: `correctness_or_ownership_divergence`. The timing movement is
not promoted, the complete sample is not replayed, and this intervention is
closed. `C32_PAIR_INTERPRETATION.json` records the comparator caveat and exact
artifact hashes.

## 2026-07-26T04:36Z — zero-GPU trace localization

The immutable 3.3-MiB raw pair was retrieved without a claim, request, GPU
invocation, or provider mutation. `localize_trace_divergence.py` reconstructed
each arm independently. All 32 SSE response IDs join one-to-one to trace RIDs;
every scheduler completion counter equals the cumulative delta length; all
rows reconstruct exactly 358 token IDs; and each final trace delta matches
the last scheduler delta. The existing join is sound. The earlier
`sse_token_ids_exact=true` field remains vacuous because the API emitted zero
token IDs in that field.

The API-visible text differs for 18/32 request indices. The earliest
deterministically ordered mismatch is request index 0, request SHA
`f8558dbfd3cca6d46239961b85967f18960a19c1bace8cb9302cdcbb2edd3c95`,
at emitted token position 0: stock token `20416` versus candidate token
`61599`. Both are scheduler event 0 with width 1 and therefore precede the
first NGRAM TARGET_VERIFY call, padding decision, accepted-prefix compaction,
or candidate CPU-count derivation.

Final result: `semantic_divergence_reject`. The mismatch is real rather than
an observer defect, but its pre-intervention onset prevents causal attribution
to the graph-gap source change. The exact gate still forbids the timing claim.
`TRACE_DIVERGENCE_LOCALIZATION.json` preserves the original timing, hashes all
decision inputs and the constructor, and specifies the smallest future A/A
capture without authorizing it.
