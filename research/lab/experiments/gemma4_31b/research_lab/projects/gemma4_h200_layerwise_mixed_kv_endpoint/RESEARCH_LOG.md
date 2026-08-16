# Research log

## 2026-07-23 — exact layerwise mixed-KV component and c32 endpoint

**Question.** Does keeping the ten global Gemma 4 layers on FP8-E5M2 while storing the 50 local layers as FP8-E4M3 remove the measured uniform-E4M3 endpoint regression?

**Action.** Bound the pinned SGLang v0.5.13 `SWAKVPool`, `MHATokenToKVPool`, layer mapping, scale path, CUDA graphs, and Triton extend/decode consumers. Reused the existing two-subpool architecture, retained the wrapper/control convention as E5M2, and overrode only the local subpool factory to E4M3. Page size 1, token capacity, QKV path, scheduler, graphs, workload, and both Triton consumers were unchanged. Claimed `h200-sync-linear-e00vhh6h29fj68x91g`, ran one component/path check, then one conditional c32 candidate.

**Evidence.**

- Measured component/path: all 50 local layers mapped to distinct E4M3 K/V buffers with geometry 16×256; all ten global layers mapped to distinct E5M2 buffers with geometry 4×512. The 120 allocations were alias-free. All 60 real extend producers and all 60 unchanged Triton consumers matched pool, layer index, pointer, slot route, scale/descale, finite stored sample, and finite output. CUDA graphs `[1,2,4,8,12,16,24,32]` captured successfully. The initial validator incorrectly required Python decode callbacks after capture; the retained-session repair accepted the already-persisted component evidence because decode replay bypasses those Python wrappers. No component or endpoint replay occurred.
- Measured endpoint: 32/32 complete, finite, nonempty responses; exact request identities and 4,214/358 token usage passed; cache accounting was exactly 17,120 cached and 117,728 fresh prompt tokens. Batch time was `22.472748879 s`, or `0.702273402469 s/request` and `509.772973 output tok/s`.
- Derived comparison: mixed KV is `27.947543 ms/request` (`4.144516%`) slower than the persisted E5M2 control `0.674325859031 s/request`. It is only `10.876 µs/request` (`0.001549%`) faster than uniform E4M3 `0.702284278594 s/request`, too small for a causal performance claim from one endpoint observation.
- Analytical preregistered bound: perfect removal of the measured 15.312032% local-attention boundary would yield `0.594741074355 s/request`, below the control, so classification is `retain_mixed` solely as the comparator for the dependent local-FA3 arm.
- Conservative provider exposure through release: `1270.259453 s`, `$0.8680106262`.

**Interpretation.** Preserving E5M2 on the global layers did not recover the uniform-E4M3 regression. This falsifies global E4M3 storage as the material cause at endpoint resolution and localizes the recoverable mechanism to the local E4M3 path or a representation effect it induces. The mixed stack is not an endpoint winner by itself.

**Next move.** Do not replay this endpoint. The dependent `gemma4_h200_e4m3_local_fa3_hybrid` project may use `artifacts/layerwise-mixed-kv-20260723/FINAL_TERMINAL.json` as the exact comparator and claim the released warm H200 for its one admitted local-FA3 component and conditional endpoint.
