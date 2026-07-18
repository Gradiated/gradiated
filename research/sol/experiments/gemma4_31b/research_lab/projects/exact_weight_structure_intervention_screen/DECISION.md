# Decision: no weight-structure candidate

Typed result: `none`.

The exact read-only inventory contains 410 in-scope text-transformer projection tensors (29,286,727,680 BF16 elements). The deterministic sample covers 18 early/middle/late class-layer aggregates across all six architectural classes, backed by 30 exact tensors.

- Measured natural zero density and natural 2:4 compliance are exactly zero in every sampled aggregate under both contraction layouts.
- Synthetic magnitude 2:4 retains only 86.29–88.75% energy along input groups and 86.60–89.09% along output groups (relative Frobenius error 0.330–0.370). Removing the highest-energy 0.1% of rows does not remove the error.
- The bounded 384-column full-output sketches retain 41.03–73.97% energy at rank 128 and 73.59–92.87% at rank 256. The worst representative matrix therefore misses the preregistered 95% consistency gate.
- Analytical representation ceilings are large—43.75% projection-weight-byte reduction for BF16 2:4, and 94.11% at rank 256—but these are weight-byte upper bounds only. They are not quality, H200 speed, or request-cost evidence.

Both intervention lines fail their structure/error gate, so neither earns a later quality-aware H200 experiment. One exact layout correction is also durable: full-attention layers have `q_proj [16384,5376]` and `k_proj [2048,5376]`, but no standalone `v_proj`; the screen does not impute the synthetic packet's logical 20,480-wide QKV shape.

Evidence: `WEIGHT_STRUCTURE_SCREEN.json`. Reproduce with pinned `requirements.txt` and `run_screen.py`; CUDA/provider mutation are forbidden and were not used.
