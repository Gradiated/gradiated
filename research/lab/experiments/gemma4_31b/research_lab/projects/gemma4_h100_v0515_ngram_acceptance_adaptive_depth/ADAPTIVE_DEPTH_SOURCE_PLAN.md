# Source-complete v0.5.15 adaptive-depth representation

This is one representation: a batch-uniform active verify depth selected by the
frozen `1..7 -> 12`, `8+ -> 6` rule, backed by exact-depth native corpus
instances and a ragged carrier for results from prior batches. It is not the
rejected fixed-depth-12 producer prefix.

The physical hypothesis is that at high load, eliminating six target rows per
request removes half of verifier row work and at least half of full-mask
attention elements. A future H100 component falsifies the mechanism if the
depth-6 producer, dynamic eager attention metadata, greedy acceptance, or KV
movement differs from a standalone depth-6 control.

## Required edits

`sglang.srt.speculative.ngram_worker.NGRAMWorker`

- `__init__`: retain 12 as immutable capacity; create native `NgramCorpus`
  instances configured at depths 12 and 6 from identical corpus arguments.
  Track active depth per request.
- `_init_preallocated_tensors`: allocate exact contiguous buffer banks for
  depths 12 and 6. Select a bank before target-row packing; never expose a
  width-6 view with a width-12 stride.
- `clear_cache_pool`, `add_external_corpus`, `commit_corpus_load`,
  `remove_external_corpus`, and `list_external_corpora`: apply mutations to
  both corpora and fail closed if their external-corpus counts diverge.
- `_prepare_draft_tokens`: select depth only from current running-request
  count; reset the selected producer's request match state when a request
  crosses depth; call only that exact-depth native producer; assert exact
  `(bs * depth,)` token and `(bs * depth * depth,)` mask shapes. Read prior
  accepted tokens through per-request offsets, not the new active depth.
- `_prepare_for_speculative_decoding`: use one active depth for contiguous
  draft rows, tree reconstruction, positions, full mask, cache allocation, and
  `NgramVerifyInput.draft_token_num`.
- `_update_ngram_corpus`: insert identical token tails into both native
  corpora, while reading prior accepted rows through their recorded offsets.
- `forward_batch_generation`: pass active depth to Mamba commit and logprob
  width; construct `next_draft_input` with offsets; return active depth in
  `GenerationBatchResult.speculative_num_draft_tokens`.

`sglang.srt.speculative.ngram_info.NgramVerifyInput`

- `__init__`: add `accept_token_offsets`, length `bs + 1`, for result-carrier
  instances. Verify-input instances remain batch-uniform and use
  `draft_token_num`.
- `filter_batch`: gather and rebase ragged accepted-token rows by request.
- `merge_batch`: concatenate and rebase ragged offsets. Reject duplicate
  request ownership or a missing offset carrier. This permits overlap
  filtering/merging across a 7-to-8 boundary without interpreting old
  width-12 rows at new width 6.
- `generate_attn_arg_prefill`: no algorithmic edit; retain its existing use of
  `self.draft_token_num` and add exact mask/row assertions before dispatch.

`sglang.srt.layers.attention.triton_backend.TritonAttnBackend`

- `init_forward_metadata`, target-verify branch: derive `depth` from
  `spec_info.draft_token_num`; build `qo_indptr`, `seq_mask_len`, and
  `max_extend_len` from that depth. Assert `input_ids.numel() == bs * depth`
  and exact custom-mask terminal length.
- `_update_target_verify_buffers`: apply the same active-depth derivation and
  assertions. Captured depth remains 12 in this candidate.

`sglang.srt.model_executor.runner.decode_cuda_graph_runner.DecodeCudaGraphRunner`

- `can_run_graph`: for NGRAM, require `spec_info.draft_token_num ==
  self.num_tokens_per_bs` and exact input, position, output-cache, and custom
  mask shapes. The existing depth-12 graph remains admitted. Depth 6 is
  deliberately rejected to the corrected eager path; no padding disguise or
  recapture is permitted in this candidate.

## Unchanged consumers

- `eagle_sample` consumes batch-uniform target rows and the active
  `NgramVerifyInput`.
- `move_accept_tokens_to_target_kvcache` already derives allocation width from
  `accept_index.shape[1]` and advances each request by accepted drafts plus its
  bonus.
- `BatchResultProcessor._resolve_spec_v2_tokens` already slices with the
  per-result `speculative_num_draft_tokens`; the worker must return the active
  width.
- `DecodeCudaGraphRunner.get_spec_info` remains depth 12 because only the
  existing depth-12 graph is captured.

## Future checkpoint-free H100 component

Using the pinned image/source and no model checkpoint, instantiate the native
depth-6 and depth-12 corpus producers plus the target-verify Triton attention
metadata path with synthetic paged KV. At batch sizes 7 and 8:

1. compare producer bytes against independent fixed-depth native producers;
2. consume every target row through the real eager attention kernel;
3. compare depth-6 row logits to the first six causally equivalent rows of a
   fixed-depth-12 call within the runtime's numerical tolerance;
4. run real greedy acceptance and KV movement, checking per-request source and
   destination slots;
5. prove depth 12 enters its existing graph and depth 6 fails closed to eager.

Any row, mask, position, accept-index, bonus ownership, or KV-slot discrepancy
rejects the component. This project does not authorize or claim that run.
