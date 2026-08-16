# Research log

## 2026-07-23 — director admission

The all-layer rank-256 recovery passed isolated held-out reconstruction but failed all four served coherence rows. Its layer evidence is strongly depth-dependent: layers 30–59 are all finite rank-256 fits with more than 91% residual energy recovered, while early layers contain the weakest and two negative fits. This project fixes the cutoff at layer 30, retains exact early MLPs, and measures one coherence-gated endpoint. The analytical `0.6341206863 s/request` projection assumes half of the measured all-layer width delta and is not treated as endpoint evidence.

## 2026-07-23 — staged, awaiting assigned H200

Question: whether keeping layers 0–29 at width 21,504 and restricting the exact 16,384 selection plus rank-256 merged correction to layers 30–59 restores the four-row coherence gate.

Action: verified `DIRECTOR_BINDING.json` (`30` finite late-layer rank-256 rows), materialized the admitted factor archive, selection, runner, and comparator under this project, and implemented the per-layer load-time placement. The remote audit requires `90` original-width projection rows and `90` recovered-width rows, `30` merged `down_proj` corrections, no runtime adapter, and the inherited 50-local/10-global ring proof before one coherence discriminator; c32 remains conditional on its pass.

Evidence: the project-local factor archive SHA-256 is `6c9760dfc4d05186336f0bc2618218a1d6a83ac02611f1c28e2b03a9dcf92021`. The first owner exited before claim with `GpuPoolError: no available GPU bench matches this project`; pool evidence shows `h200-sync-linear-e00vhh6h29fj68x91g` is atomically claimed by `gemma4_h200_fp8_tied_head_endpoint`. No remote invocation, CUDA work, or provider spend occurred.

Interpretation: this is a typed in-scope capacity boundary, not a result for the placement; retain the staged immutable snapshot and run unchanged when the director-assigned H200 returns.

## 2026-07-23 — fixed late-30 placement closes on coherence

Question: can exact early layers plus the fixed late 16,384-wide rank-256 merged recovery restore basic served coherence?

Action: after the binding and 19-file local GPU manifest reverified, the retained H200 loaded the project-local archive without refitting. A stale terminal tied-head server initially held `122250 MiB`; its pre-invocation OOM was repaired in the retained claim after that terminal server was quiesced. The unchanged second attempt loaded and executed the single four-row coherence discriminator.

Measured evidence: path audit passed exactly: `180` MLP projection rows, `30` original-width layers, `30` recovered-width layers, `30` merged rank-256 `down_proj` corrections, no runtime adapter/extra GEMM, and inherited 50-local/10-global E5M2 ring construction. All four coherence transports succeeded but all four semantic rows failed (`json`, `READY`, `4`, then post-prefix `json`) with repetitive gibberish. The coherence invocation marker is true; c32 remains unstarted. Conservative project exposure is `$0.2498002818`.

Interpretation: preserving the early half does not repair the semantic failure of this fixed recovered late-half representation. The coherence gate closes the placement; no c32 endpoint was consumed. Terminal: `artifacts/FINAL_TERMINAL.json`.
