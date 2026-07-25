# Semantic divergence decision

Decision: `indeterminate_missing_actual_artifact`.

Every hash in `DIRECTOR_BINDING.json` matches. The bound endpoint proves that
the first non-exact row was request 277 and that raw `output_ids` first
differed at zero-based position 19, or ended after a 19-token equal prefix.
It does not preserve request 277's actual response row. The expected row is
358 repetitions of token 51935 with a length finish and 4,572 total tokens.

The observer performs no text or whitespace normalization. It binds request
and expected row 277 in one future, compares raw integer `output_ids`, then
compares exactly `output_ids`, `finish_reason`, and `usage`. This rules out a
finish-only, usage-only, whitespace, or text-normalization mismatch. Because
the terminal reduces the row to the mismatch index, actual-token versus
short-list/serialization mismatch cannot be determined.

The frozen v0.5.15 chain exposes no source-proven ownership defect. Corpus
proposals are shared, but incremental match state is keyed by request `rid`.
Batch filter and merge transform request rows, accepted-token tensors,
lengths, and future indices together. Greedy verification takes target
argmax, accepted KV moves by per-row accept index, and scheduler settlement
slices accepted tokens with the same depth-12 stride before extending that
request's output. CUDA-graph replay pads inputs but returns logits only for
the raw request-token count.

That makes a cross-request leak less supported, but does not prove runtime
behavior. The actual token/length, target logits and margin, accept index, KV
transition, per-`rid` scheduler trace, and exact endpoint batch membership
are absent. The 171-request pass is not an A/A repetition of request 277's
state. Batch-dependent target numerics, runtime ownership/verification, and
response serialization therefore remain observationally equivalent.

The one future discriminator is
`per_rid_target_accept_settlement_conservation`: on one separately authorized
exact replay through request 277, record `rid`, row/pool slot, raw/padded
batch size, pre-verify sequence length, drafts, target argmax and top-two
margin, accept index/length, accepted tokens, committed-KV delta,
scheduler-emitted tokens, and serialized response IDs. Require the same
`rid`'s target-verified chain, accepted chain, KV delta, scheduler extension,
and response to agree, with no padded row admitted. A first difference at
target argmax identifies target numerics; after argmax identifies
verification/ownership; after scheduler emission identifies response
observation. No replay is authorized in this project.

The structured evidence and source identities are in
`SEMANTIC_DIVERGENCE_RESULT.json`.
