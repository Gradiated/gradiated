# Research log

## 2026-07-23 — director admission

Admitted one independent incremental representation lane. Historical exact H200 evidence at `M=12, K=5,376, N=262,144` shows E4M3 `_scaled_mm` reduced the tied-head median from `0.680032` to `0.360256 ms` with a passing kernel oracle and `0.999301` representation cosine. Because the current BF16 head is only about `0.01087 s/request`, the task is a short actual-consumer component followed by an endpoint only when its complete bound is positive. The BF16 embedding and every non-head path remain unchanged.

## 2026-07-23 — graph-bound continuation

Preserved the original terminal (`1cc0eedd…`) and 106-file attempt tree (`6fe3854d…`) byte-for-byte and ran the continuation only under `iterations/graph-bound-endpoint-20260723t1930z`. The settled E4M3 representation matched every admitted field, no component replay occurred, BF16 embedding/output and softcap 30 remained intact, zero BF16-head fallback was observed, and all three semantic-smoke rows passed.

The replacement graph gate is impossible in the pinned runtime for a different source-bound reason than the old `is_current_stream_capturing` gate. CUDA graphs captured `Gemma4ForConditionalGeneration.forward` at all admitted batch sizes and replayed at M=1, but replay returned `LogitsProcessorOutput`, not hidden states. The exact runtime `gemma4_causal.py` hash (`d95c5224…`, reconstructed from pinned `bc8bc948…` plus the admitted QKV patch) calls `self.logits_processor` inside `Gemma4ForCausalLM.forward`. The E4M3 head therefore belongs to the captured model forward; there is no post-replay `LogitsProcessor._compute_lm_head` boundary to prove without an unadmitted decode-topology change. The c32 endpoint marker and request both remained false. Terminal evidence is in `iterations/graph-bound-endpoint-20260723t1930z/artifacts/PINNED_TOPOLOGY_DECISION.json`; cumulative spend is `$1.057481635`.
