# Research log

## 2026-07-30T10:29Z — exact-shape CPU/reference cross-operator result

Question: can request-owned tasks cross normalization/FP8, QK
normalization/RoPE, and provisional-KV/commit boundaries without changing
their explicit numerical or ownership contracts?

Action: implemented an independent stage-separated stock path and
request-major executor in `crossop_hotblock.rs`. The fixture executes all 384
rows (32 requests x 12 rows), the bound local `[384, 16384]` and global
`[384, 20480]` QKV shapes, and a `[384, 8192]` norm-to-dynamic-E4M3 boundary.
It preserves explicit BF16 round-to-nearest-even cutpoints, FP8 scales/codes,
and provisional-versus-committed KV ownership. The first run exposed an
observer weakness that checked only non-finite rejected rows; the amended
consumer zeros all rejected K/V bytes and checks their full visibility.

Evidence: the amended run has zero scale/code mismatches, zero Q/K/V
mismatches, zero maximum absolute error, and zero exposed rejected rows.
CPU elapsed times are descriptive only. The two bound source artifacts do not
contain the target-head scorer, RNG/logit-processor contract, acceptance
predicate, or commit implementation, so crossing that seam is a typed source
boundary rather than an admitted semantics-preserving candidate.

Interpretation: QK RMSNorm-to-RoPE is a concrete candidate and eliminates an
analytical 18,874,368 local or 28,311,552 global BF16 intermediate bytes per
layer if stock materializes that cut. Across the bound 50 local and 10 global
layers the source-only quantity is 1,226,833,920 bytes per full M=384 wave.
This is not measured HBM traffic or latency. The norm-to-FP8 implementation
also works at exact row/width geometry but remains conditional on confirming
the production scale granularity. A full target-head-to-acceptance persistent
executor is not source-admissible from the two bound artifacts.

Next: run only the exact H200 discriminator in `MECHANISM_TERMINAL.json` after
the director supplies a source binding for the production FP8 convention and,
separately, the target scorer/acceptance seam. Do not infer endpoint gain from
the CPU timings.

## 2026-07-30T12:01Z — production FP8 ABI bound through qkv_proj

Question: does the request-owned RMSNorm-to-FP8 candidate emit the exact
activation representation consumed by the first pinned Gemma linear?

Action: traced only the v0.5.13 dynamic-FP8 path and
`Gemma4Attention.qkv_proj`. H200 uses per-token activation quantization:
contiguous E4M3FN `[384,8192]`, contiguous FP32 `[384,1]` scales equal to each
row's BF16 absmax divided by 448, and the SM90 FP8 GEMM consumes column-major
E4M3FN `[8192,N]` weights with FP32 per-output-channel scales and emits BF16.
At M=384 the producer dispatches 384 one-token CTAs of 256 threads with vec16
loads and no shared-memory retention.

Evidence: extended `crossop_hotblock.rs` with a source-equivalent producer and
full-layout sparse-weight consumer adapter. Stock and request-owned paths had
zero activation code/scale mismatches. The local `[384,16384]` output had
0/6,291,456 mismatches; the global `[384,20480]` output had 0/7,864,320.
The source-specific all-zero row produced scale bits `0` and code `0x7e`;
consumer output remained zero because the row scale is zero.

Interpretation: the prior scale/consumer uncertainty is closed at source and
CPU-reference scope. A fused producer must preserve per-token FP32 scales,
row-major E4M3FN bytes, the M=384 small-batch zero-scale behavior, and the
unchanged qkv GEMM ABI. The separate producer rereads 12,582,912 BF16 bytes
and writes 3,145,728 FP8 bytes plus 1,536 scale bytes; a fused boundary can
avoid the normalized BF16 materialization, but H200 traffic and latency remain
unmeasured.

Next: use the exact component discriminator in `FP8_ABI_TERMINAL.json` only
under a future director-authorized H200 session. No endpoint or target-head
claim follows.
