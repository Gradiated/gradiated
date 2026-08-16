# AWQ channelwise-scale coarsening gate

## Question

Can the exact current-AWQ model's already-W4 majority tensors move from symmetric group-32 scales to one scale per output channel while remaining on supported SM89 WNA16/Marlin linear and fused-MoE paths, and does that representation have a conservative route to the campaign's robust economic gate?

## Why this matters

The current checkpoint spends roughly `0.5` byte/parameter on packed W4 codes plus `0.0625` byte/parameter on BF16 group-32 scales. Channelwise W4 can make scale metadata nearly negligible, reducing the ideal W4 representation by about 11% without changing depth, expert count/top-k, MLA state, scheduler, KV dtype, or the four-bit code family. Routed experts alone occupy about `14.871 GiB`; a supported channelwise route could reduce persistent bytes and scale/dequantization traffic across the dominant weight family. This is distinct from closed residual-W4 and selective-FP8 projects, which changed the checkpoint's currently BF16 ignored tensors. It is deliberately quality-changing architecture-cost evidence because requantizing many groupwise scales to one channel scale is not bit-identical.

## Fixed evidence

- Exact checkpoint `/root/.cache/glm47flash-awq-ab31d120`, revision `ab31d120fbe79988fe2a0259993cf3c222aa8881`, config/index identities used by the campaign, symmetric group-32 compressed-tensors W4A16.
- Exact serving geometry: 47 layers, 64 routed experts, top-4, hidden 2,048, expert width 1,536, BF16 KV, SM89 L40S. Preserve all model dimensions and execution counts.
- Current full-model r3 c16 is `552.171055` tok/s; robust nomination requires `606.355`, a `9.813%` throughput gain. Stock full-model c32 projects `46,875.7 MiB`; robust peak is `44,532 MiB`.
- Consume `../expert_count_geometry/`, `../residual_w4_completion/`, `../selective_fp8_residual_architecture/`, `../moe_dense_residual/`, and pinned/current compressed-tensors source as fixed evidence. Do not reopen expert-count, ignored-residual, FP8, or generic kernel work.
- Audit pinned vLLM `0.15.0` first and at most one current stable source already available locally. Bind both standard linear and fused-MoE dispatch; success on only one path is insufficient for the intended majority scope.
- Current GPU-price inventory is fresh; planning L40S is `$1.10/hour`, absolute/robust gates are `594.466/606.355` tok/s, and the background envelope is 300 seconds.

## Execution contract

Work offline at `$0` for at most 900 seconds, 8 GiB peak RSS, and 32 MiB of new artifacts. Parse exact W4 code/scale headers and account channelwise payload savings by tensor family. Prove or falsify exact compressed-tensors configuration, loader selection, Marlin/Marlin-MoE kernel support, group-size/channel strategy, and SM89 capability for both ordinary and routed-expert linears. Build at most one deterministic streaming requantization fixture over representative real tensors to measure reconstruction error and exact output tensor contracts; do not write a checkpoint.

Only after representation/dispatch survives, test both capacity and performance. Project full c16/c32 memory from exact saved bytes. Bound endpoint impact from retained scope-matched evidence without treating theoretical bandwidth, summed kernel time, or metadata bytes as wall-time. A bandwidth-only 12% ideal ceiling is not a nomination.

Return exactly one terminal result:

- `NOMINATE_CHANNELWISE_W4`: the intended tensor scope stays on exact supported SM89 kernels, deterministic representation/reconstruction is coherent, and a conservative endpoint path reaches `606.355` tok/s with either robust c32 admission or a strictly better c16 cost point; or
- `CHANNELWISE_W4_CLOSE`: loader/kernel, representation, reconstruction, capacity, endpoint, or identifiability evidence fails.

Do not use CUDA, network/provider resources, mutate checkpoints or shared code, build a custom kernel/runtime, prepare a controller, train, or run broad quality. Produce one compact machine-readable decision artifact, an optional fixture/source audit, and a concise research-log update. No successor.

## Available resources

Use the fixed local projects above, `hardware/L40S.md`, `/root/workspace/research/factory/tools`, and `/root/workspace/research/lab/experiments/glm47flash/campaign_100`.
