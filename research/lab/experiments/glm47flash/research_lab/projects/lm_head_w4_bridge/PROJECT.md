# W4 output-head bridge

## Question

Can the exact stock-serving BF16 output head be converted alone to the checkpoint's native symmetric W4A16 group-32 representation and dispatched through the pinned vLLM Marlin path, strongly enough to earn one exact-shape L40S timing falsifier?

## Why it matters

The untied `lm_head.weight` is one `[154880, 2048]` BF16 tensor: 605.0 MiB and a retained 14.09% output-projection interval ceiling at c16. The residual-W4 screen already proves this tensor is group-32 and 128-tile legal; its projected packed payload is 170.156 MiB, saving 434.844 MiB. That screen closed only the all-residual scope because layer 0 contains an unrelated illegal `[576, 2048]` KV-A tensor and no measured residual transfer existed. A head-only bridge avoids that hazard and targets one measured hot component.

The economic window is narrow and therefore cheap to falsify. Against the campaign's 9.9551% wall-time reduction gate, a 14.09% head ceiling requires at least a 70.654% head-time reduction: candidate time no more than 29.346% of BF16, or at least `3.408x` component speedup. The ideal packed-byte ratio is 28.125% (`3.556x`) and yields only 0.172 percentage points of optimistic endpoint headroom. Any meaningful loader, dequantization, launch, or non-head attribution loss closes the cost path.

## Scope

At zero provider spend, bind the exact checkpoint `/root/.cache/glm47flash-awq-ab31d120` at revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, stock-serving layers 0–46, the pinned `glm-vllm:0.15.0-transformers-1618d44` runtime, and the existing compressed-tensors W4A16 group-32 scheme. Isolate only `lm_head.weight`; do not include shared experts, dense layer 0, MTP layer 47, embeddings, or any other tensor.

Create the smallest content-bound conversion/loader fixture that actually packs and unpacks the real head tensor, records hashes, exact packed tensor names/shapes/dtypes, aggregate and rowwise error/saturation summaries, and proves or falsifies exact derived-runtime loader selection and Marlin dispatch for `[M,2048] x [2048,154880]` at `M=1,8,16`. Do not rewrite the cached checkpoint in place. Large temporary packed bytes may be discarded after verification; retain a reproducible manifest, compact error evidence, and source hashes rather than duplicating the checkpoint in the repository.

Do not run a GPU, mutate a provider, edit the shared launcher, perform a full model conversion, train or evaluate quality, or transfer the BF16-head interval ceiling as wall time. If the exact mixed checkpoint/config cannot select W4 for the head while preserving the existing representation elsewhere, or if the pinned runtime falls back to BF16/non-Marlin execution, close immediately. Otherwise preregister only the smallest future L40S exact-shape BF16-versus-W4 component timing needed to test the `3.408x` threshold; that timing requires later director ownership after native-MTP cleanup.

## Resources

- Exact residual accounting and legal head shape: `../residual_w4_completion/`.
- Output-head trace and spectrum evidence: `../output_head_architecture/`.
- Current c16 control: `../nebius_current_awq_c16_direct/`.
- Pinned runtime and launcher sources: `/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/`.
- Shared tools: `/root/workspace/research/factory/tools` and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.

## Portfolio-changing result

Return one compact decision artifact with exact hashes, real pack/unpack error, mixed-loader and dispatch evidence, the `3.408x` component threshold, and a close-or-time recommendation. Nominate at most one later component microbenchmark only if the exact derived runtime selects Marlin for the isolated W4 head and the representation/error contract is internally valid. A component pass would still be architecture-cost evidence, not an endpoint or quality claim; a measured speedup below `3.408x` closes the line without a full-server arm.
