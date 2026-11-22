# Where a shorter scalar multiply would save time on the KV260

**A five-cycle multiply in the feed-forward scalar cut complete-request cycles by 7.23–8.71% across the three standard prompts in simulation.** The replay kept the products, final scores, output bytes, cache and stopping points exact. The measured opportunity clears the 1% threshold in the Experiment 19 preparation. It supports qualifying and routing the single feed-forward change. [Experiment 19 preparation](../kv260-scalar-product-opportunity-v1.md)

## Five cycles in the feed-forward scalar

| Prompt | First output, clocks saved | Decode, clocks saved | Completion, control → five-cycle clocks | Completion reduction |
| --- | ---: | ---: | ---: | ---: |
| Hello | 46,464 | 375,936 | 4,895,722 → 4,469,098 | 8.71% |
| Six bytes | 54,912 | 511,104 | 7,034,455 → 6,464,215 | 8.11% |
| 48 bytes | 409,728 | 435,072 | 11,742,409 → 10,893,385 | 7.23% |

First output runs from internal request start to the first useful output byte. Decode runs from the first to the last useful output byte, with one interval fewer than output bytes. Completion includes the final processing needed to detect the stop. The feed-forward intervention changed the internal decode rate at an assumed 50 MHz from 1,006.01 to 1,099.45, 934.03 to 1,014.05, and 720.82 to 767.57 output bytes per second respectively. These are conversions of simulated FPGA counters. Board-side time to first token also includes host work.

The feed-forward scalar makes **384 products at every processed position** in these fixtures. There are 256 direct products in gating and hidden activations and 128 products inside exponential interpolation. The control spends 16 recurrence clocks on each. The five-cycle simulation removes 11 per product, or **4,224 clocks per processed position**. All of that saving reaches completion. The archived control and timing variant agree on every enclosing phase except feed-forward wait. In this range, existing overlap with the gate/up projections absorbs none of the removed cycles. Early prompt positions also run feed-forward when they skip final scoring.

The five-cycle forecast covers both the direct and exponential products in this scalar. If a routed candidate speeds up only the direct products, or adds a launch or retirement cycle, it needs a revised forecast. The comparison assumes the new circuit still meets 50 MHz. Check the actual partial-product and carry paths, mapped DSP/LUT/register counts, setup and hold coverage, and exact signed and overflow behaviour. The replay groups arithmetic steps in software, so it provides cycle evidence and no routed resource or power estimates.

## Other callers and overlap

| Scalar intervention | Hello completion reduction | Six bytes | 48 bytes |
| --- | ---: | ---: | ---: |
| Three normalisations, 16 → 8 cycles | 5.05% | 4.70% | 4.19% |
| Feed-forward only, 16 → 8 cycles | 6.34% | 5.90% | 5.26% |
| Both attention exponentials, 16 → 8 cycles | 0.84% | 1.04% | 1.37% |
| All six scalar instances, 16 → 8 cycles | 12.23% | 11.64% | 10.81% |
| All six scalar instances, 16 → 1 cycle | 22.93% | 21.82% | 20.28% |

The three normalisation blocks each perform 96 direct products and six products inside reciprocal square root per processed position. Their waits are serial in the model and the 2,448 clocks removed per position reached completion in the eight-cycle replay. The feed-forward scalar is a single instance and yields the larger improvement at the same eight-cycle latency.

In attention, the two exponential lanes already work concurrently. For Hello, halving both multiplier latencies removes 81,216 lane busy cycles. In the matched replay the attention phase shrinks by only 41,288 clocks. The remaining 39,928 cycles equal the reduction in time that both lanes spend multiplying together. The same accounting holds for the six-byte prompt (144,992 lane cycles removed, 73,472 request clocks saved) and the 48-byte prompt (314,720 removed, 160,384 saved). The separate eight-cycle comparisons sum exactly to the all-eight-cycle comparison. The all-one-cycle result is an idealised limit for shortening these recurrences within the existing schedule.

The feed-forward operand trace observed maximum absolute widths of 14 and 31 bits for direct products, and 23 and 16 bits for interpolation. These maxima describe the three replayed inputs. A design that relies on narrower operands needs a supported-domain proof or a full-width fallback. For this comparison keep the agreed 64-bit operation and the baseline overflow checks.

## Evidence and reproduction

[Metrics CSV](metrics.csv) gives first, last, decode and completion counters for all 21 replays. [Results JSON](results.json) includes the prefix and completion phase counters, scalar calls, observed operand maxima, and per-caller operand/product digests. Each caller has three bins in the order direct, exponential and reciprocal square root.

The [Experiment 18 RTL run](../../results/probability-div-v1-rtl-20261119T160135Z/run.json) pins the input archive. [Replay script](replay.py) checks the archive SHA-256 and byte size, checks the archived candidate RTL against its member manifest, and verifies the Verilator 5.052 runtime tree. It applies the diagnostic only to temporary copies of the three scalar module definitions. For fixed latency (L), each simulated edge runs the difference of two adjacent cumulative digit counts, so exactly 16 original radix-16 digit steps still run even at (L=5). The signed-magnitude input, product width, overflow test and retirement logic are unchanged. The [monitor](monitor.svh) observes the simulation without affecting its state or time.

The 16-cycle control reproduced the archived Experiment 18 candidate phase counters and cache snapshots byte for byte. Every arm passed the archived token sequence, all scored values, output and stop checks, and matched the control’s cache values, accepted KV addresses, probability/division values and scalar operand/product digests. The diagnosis changes the timing of the dependent work. It checks that no unrelated enclosing phase changes at the prefix or completion boundary.

From the repository root, with the pinned macOS Verilator installation available:

```sh
mise exec -- python hardware/research/inference/experiments/kv260-scalar-multiply-opportunity-v1/replay.py \
  --repo "$PWD" \
  --verilator /path/to/toolchains/verilator-5.052/verilator/5.052 \
  --output /private/tmp/kv260-scalar-multiply-recheck
```

Choose a fresh output directory. Compare its `results.json` and `metrics.csv` with the saved copies. The 50 MHz assumption is for converting model cycles to time. Synthesis, FPGA programming and physical measurements are outside this diagnostic.
