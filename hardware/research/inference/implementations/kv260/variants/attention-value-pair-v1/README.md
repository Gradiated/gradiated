# Paired attention value coordinates

[Experiment 23](../../../../experiments/kv260-attention-value-pair-v1.md) uses the exact `projections-read-ahead-v1` circuit as its control. The materializer verifies all eleven inherited RTL files. The candidate adds scoped cache, frontend and attention modules in the existing source files and selects them in `transformer.sv`. The original standalone RTL module interfaces and top-level AXI interface remain available. The candidate exposes both values in one internal cache response and exposes the mate's debug product and sum beside the primary stream.

## Port use and arithmetic

The 8,192 × 16 key array uses its original address and synchronous read. The value array contains one stored copy of each word, split by address parity into two 4,096 × 16 banks. A write updates one bank. A scalar read activates one bank and returns the addressed K and V with its original coordinate. A pair read accepts an even base coordinate and activates both V banks at the same position and pair index. It retains one K word and returns the base coordinate and pair bit. The cache accepts a new request only when the previous response has retired. A partial row is invisible until its final append commits all 32 coordinates. The logical value storage is 16 KiB. Actual memory primitive assignment is established by the routed build.

Each value lane accumulates one coordinate in increasing position order. The original path forms the probability as a signed 17-bit number by zero-extending the unsigned Q15 word, so 0x8000 gives +32,768. Both signed products use the same probability and their own signed 16-bit values. The two signed 48-bit accumulators add in the original order. A 256-term sum of absolute products bounded by 2^30 fits in 48 signed bits. The shared scalar rounds the even coordinate, then the odd coordinate, with the original signed ties-to-even shift and clipping. Accepting the even result starts the odd rounding. Backpressure holds either result in place. Reset cancels both lanes and invalidates cache commit and pending-response state.

One 16-coordinate head uses eight coordinate pairs with the same probability and V terms as 16 scalar coordinates. At depth D, the ready-cache value phase across both heads takes 32(2D+4) clocks in the control and 16(2D+7) in the candidate. The requantization and ordered retirement clocks are the same. The candidate removes 16 initial request clocks, 16D response clocks and 16D MAC clocks. The direct scored-step sweep measures final-prefix-token admission through acceptance of its last vocabulary score. At depth D, the independent whole-position saving is 32D+16. Through n positions the cumulative saving is 16n(n+2).

## Reproduce or resume locally

Run from the hardware research worktree with Python 3.11+ and the pinned Verilator 5.052 distribution. The following commands generate a new output directory and preserve existing evidence. The runtime paths identify local Mac artifacts.

```sh
variant=hardware/research/inference/implementations/kv260/variants/attention-value-pair-v1
verilator=/Users/aidanmcconnell/dev/gradiated/.agents/runtime/hardware/inference/toolchains/verilator-5.052/verilator/5.052
baseline=.agents/runtime/hardware/inference/outputs/projections-read-ahead-v1-rtl-20261119T192912Z/simulation.tar.gz
work="$(mktemp -d /private/tmp/exp23-replay.XXXXXX)"
mise exec -- python -B "$variant/replay_value_pair.py" --repo . --verilator "$verilator" --archive "$baseline" --output "$work/replay"
mise exec -- python -B "$variant/test_directed.py" --repo . --verilator "$verilator" --model "$work/replay/gold/replay/gold/replay/gold/model.hex" --output "$work/directed"
mise exec -- python -B "$variant/seal_gate.py" --repo . --replay "$work/replay" --directed "$work/directed" --output "$work/qualification"
```

The full replay covers seven frozen fixtures and adds fixed-sequence prefixes at occupied depths 1, 16, 64, 128 and 256. Cache read values are matched independently against accepted append writes and exact pinned cache checkpoints. The raw traces retain physical transaction order, bank enables and both weighted products and running sums. The directed suite reads every stored word through scalar and pair ports and checks refused and delayed transfers, held outputs, signed ties, clipping, tag corruption and reset. The archive member ledger verifies each logical artifact, including content-identical files stored as tar hard links.
