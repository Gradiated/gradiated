# Research log

Prior handoff: bound and implement one-way sequence-level late exit as an architecture-cost proxy; do not return a generic early-exit design survey or a training plan.

## 2026-07-15 — Exact c16 accounting and one-way proxy

Question: can one late sequence exit retain enough decode work to clear the 10% c16 cost bar after unchanged prefill?

Action: added [`sequence_early_exit_proxy.py`](sequence_early_exit_proxy.py), a source-bound, CPU-executable fixture bound to the stock 47-layer serving graph and hidden width 2,048. It always runs full-depth prefill, makes one per-sequence transition, invokes the auxiliary/reused head for each output, preserves the selected hidden shape, and rejects re-entry. Oracle decisions are intentional semantics-changing proxies; no quality claim or provider mutation was made.

Evidence: [`sequence_early_exit_bound.json`](sequence_early_exit_bound.json) uses the retained trace region wall mix (176.77 ms prefill, 1,015.15 ms decode; 14.83% / 85.17%) and exact tail accounting. With 2% per-switched-token overhead relative to full-depth decode, exit after layer 35 (12/47 tail layers) requires 49.90% switched output tokens/sequences for a 10% cost reduction; the resulting bound is $0.5136/M and 594.90 tok/s equivalent at a 50% switch rate. Exit 39 requires 78.16%; exit 43 cannot reach the target even at 100% switching. The 2% overhead case is explicit sensitivity, not measured runtime overhead.

Interpretation: nominate only exit-after-35 as a conditional candidate. It has a narrow but material analytical path if a learned confidence head can switch at least half of background sequences/tokens with <=2% decode-equivalent overhead. The result is not deployable evidence: the prefill/decode mix comes from a retained c8 trace, saved layer work is assumed to transfer linearly, and quality/recovery are unmeasured. The layer-39 path is too dependent on near-perfect switching; layer 43 is closed.

Next move: if the director later grants a matched L40S session, test stock control versus one-way exit-35 only, measuring per-sequence switch rate, head overhead, endpoint wall time, completion/re-entry violations, memory/KV residency, and compact quality diagnostics. Require >=50% switch rate, <=2% decode-equivalent head/switch overhead, and >=594.9 tok/s before any recovery-training investment; otherwise close the lane.

## Cycle 48 continuation pending

The director reactivated one zero-cost source/runtime falsifier: bind full-depth prefill plus forced all-sequence decode exit after layer 35 in the exact derived vLLM runtime. This is only a necessary cost-ceiling path for the later 50% policy; no provider, GPU, training, or quality claim is authorized.

## 2026-07-15 — Exit-35 phase contract passes locally

Question: can the required exit-35 behavior be represented at the pinned model-forward boundary without scheduler or attention-engine surgery?

Action: added [`source_bound_exit35_runtime_fixture.py`](source_bound_exit35_runtime_fixture.py), bound to runtime image `glm-vllm:0.15.0-transformers-1618d44`, Transformers revision `1618d44b9295361607ec74d7be860ba886aac039`, `Glm4MoeLiteForCausalLM`, 47 serving layers, and hidden width 2,048. The fixture emits [`exit35_runtime_binding.json`](exit35_runtime_binding.json).

Evidence: all checks pass. Exit mode runs all 47 layers and writes tail KV during prompt processing, then runs exactly layers 0–34 with no tail-layer decode/KV writes; hidden shape remains `[16, 2048]`; stock mode remains all-47-layer; final norm and vocabulary head each run once; and mixed prefill/decode metadata is rejected fail-closed. Python compilation and deterministic rerun passed.

Interpretation: the architecture is locally representable at the forward contract and does not, by itself, require scheduler or attention-engine surgery. This is only a source-bound CPU fixture: the pinned image was not executed, CUDA/KV allocator behavior and endpoint overhead remain unmeasured, and the forced all-sequence path changes semantics. The runtime feasibility falsifier therefore passes its necessary local gate but does not yet support a deployment or quality claim.

Next move: retain one later matched L40S stock-c16 versus forced-all-exit-35 ceiling arm only after the active W4-head allocation reaches terminal cleanup. Preserve separate prefill/decode timing and require the preregistered 594.466 tok/s equivalent ceiling before confidence-head or recovery work.

## 2026-07-15 — Exact vLLM layer-loop patch validated; paid run held

Question: can the forced exit be bound to the pinned vLLM model implementation without changing scheduler or attention code?

Action: added [`exit35_vllm_source_patch.py`](exit35_vllm_source_patch.py). Against the public vLLM 0.15.0 `glm4_moe_lite.py` source, its expected SHA-256 (`6a984f...556b4a9`) matched; it changed exactly one `islice(self.layers, self.start_layer, self.end_layer)` loop, compiled the patched source, and emitted a patch record. Exit mode is opt-in via `VLLM_EXIT35_MODE=1`; long prompt inputs retain `self.end_layer`, while short decode inputs stop at `start_layer + 35`.

Evidence: the patch is source-bound and fail-closed on source drift, missing `input_ids`, or an unexpected loop. The offline patched file compiled successfully. No provider or CUDA execution was performed.

Interpretation: model-forward integration is technically small, but the current shared launcher does not stage this patch, pass its mode, or run adjacent stock/exit arms in one allocation. A stock-only launch would not answer the question, so the paid cap remains unspent. The remaining work is bounded launcher/remote-arm integration; if that cannot be added without a second controller or mixed-phase ambiguity, close the paid route.

Next move: integrate this patch into the already-authorized shared launcher, run stock then exit-35 under one durable owner, and preserve separate phase telemetry. Do not launch until the staged patch and exact source hash are included in the immutable input manifest.

## 2026-07-15 — Paid route closed before provider creation

Action: integrated the opt-in exit patch into the named shared launcher and remote script. Focused Python compilation, shell syntax, stock command identity, exit-mode environment binding, and all 31 launcher tests passed. The no-mutation ownership gate also failed closed as required.

Execution: launched `glm47-exit35-l40s-20260715-r1` under an external systemd unit with the authorized L40S/c16 parameters. It terminated after 15.73 seconds with exit code 1 at local input validation: `batched vLLM inputs are incomplete`. The missing path was the newly added exit patch reference with one directory too few in the launcher; this path defect was corrected after capturing the diagnostic. Provider creation was never attempted. Authenticated instance and disk inventories were both empty; spend was `$0.00`.

Decision: this is the second pre-science failure (after the corrected launcher indentation), so the declared stop rule closes the paid route. [`PAID_RUN_DIAGNOSTIC.json`](PAID_RUN_DIAGNOSTIC.json) preserves the typed outcome. No retry or provider mutation is authorized in this project; the exact source patch and corrected shared integration remain offline evidence only.
