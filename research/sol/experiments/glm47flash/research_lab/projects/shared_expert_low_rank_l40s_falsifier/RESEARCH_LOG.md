# Research log

## 2026-07-16 — Director opening handoff

Test only the always-on BF16 shared-expert matrices. Rank-512 joint gate/up plus down and independent rank-384 both save more than half of nominal component work, but the retained shared-path ceiling leaves little endpoint margin. Exact spectra and shared-MLP reconstruction should therefore promote one variant or close the line quickly at `$0`.

## 2026-07-16 — Deterministic exact-weight/proxy terminal

Question/action: screen all 46 layers of the exact BF16 always-on shared experts for the two admitted tile-aligned variants: joint gate/up plus down at rank 512 and independent gate/up/down at rank 384. The local checkpoint index and all four referenced safetensors shards were hashed before use; tensors were mmap-read one at a time, with deterministic randomized truncated spectra (seed `47047`) and 96 Gaussian plus 96 studentized heavy-tail hidden vectors per layer. No checkpoint, runtime, CUDA, provider, or paid resource was used.

Measured result: [`SHARED_FACTOR_FALSIFIER.json`](SHARED_FACTOR_FALSIFIER.json) (`5013e4ad544a733e46d772d2b4f7c9cfca4bccc45ac6111357b579587a997810`, 145,290 bytes). Joint rank 512 clears the nominal 52.7778% component reduction and 3.7478% optimistic shared-path ceiling, but max gate/up and down relative-Frobenius errors are `0.6724` and `0.6335`; shared-MLP proxy median cosine is `0.6258`, p05 `0.5083`, p95 relative-L2 `0.8631`, and max layer relative-L2 `0.8457`. Independent rank 384 clears 56.25% and 3.9943% nominal economics, but errors are `0.6578/0.7192`, median cosine `0.5393`, p05 `0.4150`, p95 relative-L2 `0.9115`, and max layer relative-L2 `0.9066`. Both fail every fidelity threshold by wide margins. The artifact also retains top-8 singular-value summaries and explicit launch accounting: stock 3 GEMMs, joint low-rank 4, independent low-rank 6.

Decision: `SHARED_FACTOR_CLOSE`. The exact shared path is not sufficiently low-rank at the admitted tile ranks; no proxy is nominated. This is quality-deferred architecture-cost evidence only and does not transfer to routed experts or another model/chip.
