# Research log

## 2026-07-15 — exact 34-layer student and pinned-runtime closure

Question: can the corrected 34-layer physical AWQ student be made reproducibly enough to nominate one later c32 cost arm without changing the paid launcher?

Action and evidence: ran `build_student34_checkpoint.py` against the pinned `ab31d120` source, then reran it against the existing contract root to prove idempotent reuse. It wrote the content-addressed `/root/.cache/glm47flash-awq-student34-183b4521333e` checkpoint: 19,815 exact index/header keys, serving layers `0..33`, no MTP/layer-47 keys, 13,687,865,528 safetensors bytes, source/output config/index and all shard hashes in `student34_checkpoint_manifest.json`. Corrected bounds apply the omitted 4,601.160 MiB removed AWQ payload at all concurrencies: c16/c24/c32 peaks are 31,752.680/33,624.680/41,249.840 MiB, leaving 13.980/12.151/4.705 GiB respectively. The fixed endpoint bound remains 711.032 output tok/s and `$0.429735/M` at the shared `$1.10/h` committed L40S rate.

Pinned runtime: the exact local `glm-vllm:0.15.0-transformers-1618d44` image source contract passes registry (`Glm4MoeLiteForCausalLM`), `AutoWeightsLoader`, 34-layer config, and pack-quantized W4A16/group-32 route checks. The executable `vllm serve --device cpu` dry-load reaches vLLM then exits before model instantiation: Triton reports zero active drivers and vLLM cannot infer a device. Therefore loader consumed/missing/unexpected key sets are **unmeasured**; structural index/header closure is not a loader pass. Raw bounded diagnostics and hashes are retained in `student34_pinned_runtime_*.json`.

Interpretation: exact content and the offline c32 capacity/economic gates pass. This nominates at most one future stock-vLLM L40S c32 cost arm only under a separately authorized derived-checkpoint transfer/launcher path; the frozen paid launcher remains untouched and rejects its smaller weight-byte geometry. GPU loader consumption, throughput, quality/recovery, and production economics beyond the fixed-cost bound remain open. Provider create attempts/spend: zero.
