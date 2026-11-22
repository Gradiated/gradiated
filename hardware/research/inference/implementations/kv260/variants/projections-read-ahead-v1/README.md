# Read ahead in three on-chip projections

[Experiment 22](../../../../experiments/kv260-projections-read-ahead-v1.md) uses the exact `norm-mul-shared-v1` circuit as control. Its eleven source files are verified before each variant is generated. The materializer adds scoped projections and binds them at the selected sites. Generic `mac32.sv` and `dense.sv`, the existing feed-forward down projection and final logits pipeline retain their baseline source.

| Arm | Read-ahead sites | Changed source |
| --- | --- | --- |
| `control` | None | None |
| `qkv-read-ahead-v1` | Front-end Q/K/V projection | `frontend.sv` |
| `attention-output-read-ahead-v1` | Attention output projection | `transformer.sv` |
| `ff-gate-up-read-ahead-v1` | Feed-forward gate and up projections | `feedforward.sv` |
| `qkv-attention-output-read-ahead-v1` | Q/K/V and attention output projections | `frontend.sv`, `transformer.sv` |
| `projections-read-ahead-v1` | All three scopes | All three scoped files |

One synchronous read primes coordinate zero in each row. In each nonfinal MAC cycle the accumulator consumes the previous pair of registers and the read port loads the next pair. At coordinate 31 the engine retains the last product and enters rounding without issuing a read. Output backpressure holds the finished row until retirement. The next row begins with its own prime. The operand registers, per-row addition order, rounding, clipping and result handshakes follow the same numerical contract.

The base lane spends two clocks per coordinate, followed by rounding and retirement. The candidate spends a prime clock, 32 MAC clocks, rounding and retirement. One 32-term row takes 66 clocks in the control and 35 in the candidate with an accepting consumer. Every row still issues 32 operand reads. Q/K/V saves 2,976 clocks across 96 rows per position. Attention output saves 992 across 32 rows.

Gate and up are two concurrent lanes. Each can calculate a row 31 clocks sooner, while the feed-forward scalar requests the pair in order. The replay observes 65 → 34 first-pair wait clocks and zero later wait clocks per position. Both lanes spend the other 3,937 calculated savings waiting longer for an accepting consumer. The three changes together save 3,999 clocks per processed position. The Q/K/V plus output arm saves 3,968 and isolates the marginal gate/up effect.

## Reproduction

Use Python 3.11+ and the pinned Verilator 5.052 toolchain. `materialise_projections.py --arm <ID>` writes a complete source set with a deterministic manifest. `test_directed.py` checks the actual four lanes using signed integer operand, sum and output oracles with ties and clipping. It also resets at the initial prime, first, penultimate and last MAC, held result and next-row prime. `replay_projections.py` takes the pinned Experiment 21 simulation archive. It runs the control, the three single changes, then the two combinations on all seven cases. It checks ordered physical read issues, equal projection rows and intermediates, unchanged cache and outputs, and full stage-cycle reconciliation.
