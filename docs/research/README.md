# Research: Full-Stack Inference Co-Design (compiled 2026-07-11)

Distilled output of an 8-agent web research workflow covering model architectures, SOTA serving
performance, hardware economics, simulator prior art, custom silicon, model-side levers, and
market prices. Every number carries a source URL, as-of date, and confidence; conflicts are
flagged inline rather than resolved silently.

## [calibration-constants.md](calibration-constants.md)
The constants table for the simulator:
1. **Model architectures** — exact config.json params for GLM-4.5→5.2, DeepSeek-V3.x, Kimi-K2,
   Qwen3 MoE, MiniMax, and local lab models; derived KV bytes/token, expert GEMM shapes, MTP.
2. **Hardware economics** — GPU rental/purchase/TDP, memory $/GB and bandwidth by type,
   wafer/NRE/packaging, pJ/FLOP and pJ/bit, PUE, $/kWh, owned-hardware TCO anchor.
3. **SOTA serving anchors** — tok/s/GPU calibration targets (DeepSeek H800, SGLang H100/GB200,
   vLLM H200, InferenceMAX), utilization/overhead baselines, simulator pitfall magnitudes.
4. **Market prices** — $/Mtok tables, batch/cache pricing structure, agent workload shape.

## [strategy.md](strategy.md)
The synthesis: verdict on the 5-10x thesis (real, software-first, per-family not per-model),
12 stack-ranked levers with estimated gains, custom-silicon lessons (Groq/Cerebras/Etched/
TPU), model-side lever evidence, simulator design implications, open questions, and gaps.
