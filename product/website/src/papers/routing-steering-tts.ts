import type { PaperGuide } from "./types";

export const routingSteeringTtsPapers: PaperGuide[] = [
  {
    slug: "routellm",
    shortTitle: "RouteLLM",
    title: "RouteLLM: Learning to Route LLMs with Preference Data",
    authors: "Ong et al. (UC Berkeley / Anyscale)",
    year: 2024,
    arxivId: "2406.18665",
    arxivUrl: "https://arxiv.org/abs/2406.18665",
    category: "Routing, Inference & Steering",
    oneLiner:
      "Train a sub-10ms CPU model router from preference traces that offloads easy prompts to cheap models while holding a calibrated quality SLA.",
    story:
      "Most production apps send 100% of requests — from trivial JSON formatting to multi-file refactors — to their priciest frontier model because nobody trusts hand-coded heuristics. RouteLLM showed that public preference battles (Chatbot Arena) are enough to train a tiny router that slashes API spend 2x–3.6x while holding 95% of frontier quality.",
    insight:
      "Embed prompts once with a frozen encoder, fit a calibrated win-rate model (dual-head kernel + L2-logistic) predicting P(weak matches strong | prompt), pick the cost-quality Lagrangian threshold lambda on a held-out split, and enforce it online with 10% unbiased fallback probes.",
    whyGrad:
      "grad's managed router recipe fits the calibrated CPU solver in ~6 seconds at $0 training token cost, reports 95% bootstrap confidence intervals, and deploys straight into an sla_lagrangian Endpoint with a hard-stop circuit breaker.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "12 lines of YAML train, calibrate, and validate the router on CPU with zero custom PyTorch.",
    },
    walkthrough: [
      { title: "Point recipe='router' at preference or production traces", explanation: "Split by session_id so multi-turn conversations never leak across train and eval.", gradCall: "recipe: router · split.strategy: by_session" },
      { title: "Fit the calibrated CPU dual-head solver in 6 seconds", explanation: "Extract frozen bge-small embeddings once and solve in closed form — $0 GPU.", gradCall: "solver: dual_head_kernel_lbfgs · compute: cpu" },
      { title: "Deploy with sla_lagrangian guardrails and 10% fallback probes", explanation: "Unbiased fallback probes continuously track live quality delta and trip a circuit breaker on drift.", gradCall: "grad deploy routellm-arena@latest --canary 0.10" },
    ],
    gotchas: [
      "Inspect the upper bound of quality_drop_ci95, not just the point estimate, before tightening max_quality_drop.",
      "Keep fallback_probe_rate >= 0.10 so live quality monitoring stays unbiased against selection bias.",
    ],
    linesOfCode: 12,
    typicalBaselineLoc: "~650 LOC embedding cache + MF trainer + calibrator",
    mode: "Managed recipe",
    entrypoint: "recipe.yaml",
    models: [
      { id: "BAAI/bge-small-en-v1.5", label: "BAAI/bge-small-en-v1.5 (CPU, <10ms)", estTokens: "~0.8M embed tokens", duration: "~6 sec", estCost: "$0.00 train tokens" },
      { id: "Qwen/Qwen3-0.6B", label: "Qwen/Qwen3-0.6B (GPU, long context)", estTokens: "~1.0M tokens", duration: "~3 min", estCost: "~$0.25" },
    ],
    datasets: [
      { id: "hf://lmsys/chatbot_arena_conversations", label: "Chatbot Arena Conversations", source: "Hugging Face (public)", examples: "33,000 human preference battles" },
    ],
    primitives: [
      { label: "Model router recipe", href: "/docs/training/recipes/router/" },
      { label: "sla_lagrangian Endpoint", href: "/docs/training/endpoints/" },
    ],
    codeLabel: "recipe.yaml",
    codeLanguage: "yaml",
    code: `# Run with: grad run papers/routellm --wait
dataset: hf://lmsys/chatbot_arena_conversations
name: routellm-arena
recipe: router
base: BAAI/bge-small-en-v1.5
compute: cpu
solver: dual_head_kernel_lbfgs
split:
  strategy: by_session
  eval_fraction: 0.15
calibration:
  max_quality_drop: 0.02`,
    paperYaml: `slug: routellm
title: "RouteLLM: Calibrated Model Routing"
arxiv: "https://arxiv.org/abs/2406.18665"
category: routing-steering-tts
public_dataset: "hf://lmsys/chatbot_arena_conversations"
base_default: "BAAI/bge-small-en-v1.5"
compute: cpu
entrypoint: recipe.yaml`,
    dryRunOutput: `Template  papers/routellm (arXiv:2406.18665)
Dataset   hf://lmsys/chatbot_arena_conversations (28,050 train / 4,950 eval · public)
Model     BAAI/bge-small-en-v1.5 (frozen) + dual_head_kernel_lbfgs
Guardrail sla_lagrangian · target quality drop <= 2.0% · 10% fallback probes
Estimate  CPU · ~6 sec · $0.00 train tokens · warnings: 0`,
    benchmarks: [
      { benchmark: "Cost reduction at >=95% strong quality", paperReported: "2x–3.66x lower API spend on MT-Bench, MMLU, and GSM8K", templateSetup: "Chatbot Arena · BAAI/bge-small-en-v1.5 · 6s CPU fit" },
    ],
    bibtex: `@inproceedings{ong2025routellm,
  title={RouteLLM: Learning to Route LLMs with Preference Data},
  author={Ong, Isaac and others},
  booktitle={ICLR},
  year={2025}
}`,
  },
  {
    slug: "s1",
    shortTitle: "s1",
    title: "s1: Simple Test-Time Scaling (Budget Forcing)",
    authors: "Muennighoff et al. (Stanford / UW)",
    year: 2025,
    arxivId: "2501.19393",
    arxivUrl: "https://arxiv.org/abs/2501.19393",
    category: "Routing, Inference & Steering",
    oneLiner:
      "Unlock predictable test-time scaling with SFT on just 1,000 curated traces plus deterministic 'Wait'-token budget forcing at inference time.",
    story:
      "After o1 showed smooth test-time scaling curves, teams assumed reproducing it required massive RL clusters. s1 surprised everyone by matching o1-preview on competition math with just 1,000 curated SFT traces and a 10-line decoding trick called budget forcing.",
    insight:
      "SFT on 1,000 hard, diverse reasoning traces (s1K-1.1), then intercept premature </think> stops at test time and inject 'Wait' to force self-verification — or force '</think>\\nFinal Answer:' to cap latency.",
    whyGrad:
      "Managed recipe='sft' trains on s1K-1.1 in 12 minutes, and strategy={'kind': 'budget_forcing'} (or Artifact.sample with resume_from + append_env_tokens) runs Wait-token scaling with zero custom LogitsProcessors.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Both the 1,000-example SFT run and Wait-token budget forcing are native grad features.",
    },
    walkthrough: [
      { title: "Run managed SFT on the 1,000 curated s1K-1.1 traces", explanation: "5 epochs of cosine LoRA SFT converge cleanly in ~12 minutes.", gradCall: "client.runs.create(..., recipe='sft')" },
      { title: "Intercept </think> and inject 'Wait' via append_env_tokens", explanation: "Extend the exact KV trajectory via resume_from to trigger self-checking.", gradCall: "art.sample(..., stop=['</think>'], resume_from=[traj], append_env_tokens=[wait_toks])" },
      { title: "Deploy behind a managed budget_forcing Endpoint", explanation: "Expose deterministic min/max thinking budgets per request in production.", gradCall: "strategy={'kind': 'budget_forcing', 'wait_text': '\\nWait', 'max_waits': 2}" },
    ],
    gotchas: [
      "Cap Wait extensions at 2–4; beyond 6 forced waits, models start second-guessing correct derivations.",
      "Quality of the 1,000 traces matters far more than dataset size — filter for hard, diverse, verified derivations.",
    ],
    linesOfCode: 36,
    typicalBaselineLoc: "~850 LOC SFT + custom vLLM LogitsProcessor",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-32B", label: "Qwen/Qwen3-32B (paper scale)", estTokens: "~4.7M tokens", duration: "~24 min", estCost: "~$5.60" },
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (fast reproduction)", estTokens: "~2.4M tokens", duration: "~12 min", estCost: "~$0.95" },
    ],
    datasets: [
      { id: "hf://simplescaling/s1K-1.1", label: "s1K-1.1 Curated Traces", source: "Hugging Face (public)", examples: "1,000 curated reasoning traces" },
    ],
    primitives: [
      { label: "SFT recipe", href: "/docs/training/recipes/sft-dpo/" },
      { label: "budget_forcing Endpoint", href: "/docs/training/endpoints/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelInput

client = Grad()
run = client.runs.create(
    dataset="hf://simplescaling/s1K-1.1",
    name="s1-reasoner",
    recipe="sft",
    base="Qwen/Qwen3-8B",
    adapter="lora",
    compute="gpu",
    epochs=5,
    optimizer={"kind": "adamw", "lr": 2e-5},
).wait()

art = client.artifacts.get(run.artifact_id)
wait_toks = art.tokenize("\\nWait, let me double-check each step.\\n")
close_toks = art.tokenize("\\n</think>\\nFinal Answer: ")

def solve_with_budget_forcing(prompt: str, n_waits: int = 2) -> str:
    inp = ModelInput(messages=[{"role": "user", "content": prompt}])
    traj = art.sample([inp], n=1, temperature=0.0, max_new_tokens=1024, stop=["</think>"])[0][0]
    for _ in range(n_waits):
        traj = art.sample(resume_from=[traj], append_env_tokens=[wait_toks], n=1, temperature=0.0, max_new_tokens=1024, stop=["</think>"])[0][0]
    return art.sample(resume_from=[traj], append_env_tokens=[close_toks], n=1, temperature=0.0, max_new_tokens=256)[0][0].output["text"]

client.endpoints.create(
    slug="s1-reasoner",
    artifact=run.artifact_id,
    strategy={"kind": "budget_forcing", "wait_text": "\\nWait", "max_waits": 2, "max_thinking_tokens": 4096},
)`,
    paperYaml: `slug: s1
title: "s1: Simple Test-Time Scaling"
arxiv: "https://arxiv.org/abs/2501.19393"
category: routing-steering-tts
public_dataset: "hf://simplescaling/s1K-1.1"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/s1 (arXiv:2501.19393)
Dataset   hf://simplescaling/s1K-1.1 (1,000 curated traces · public)
Model     Qwen/Qwen3-8B · SFT (5 epochs) + budget_forcing Endpoint
Estimate  ~2.4M tokens · ~12 min · ~$0.95 · warnings: 0`,
    benchmarks: [
      { benchmark: "AIME24 & MATH500", paperReported: "56.7% AIME24 & 93.0% MATH500 on s1-32B with budget forcing", templateSetup: "s1K-1.1 · 5 epochs SFT · n_waits=2" },
    ],
    bibtex: `@article{muennighoff2025s1,
  title={s1: Simple test-time scaling},
  author={Muennighoff, Niklas and others},
  journal={arXiv preprint arXiv:2501.19393},
  year={2025}
}`,
  },
  {
    slug: "eagle-3",
    shortTitle: "EAGLE-3",
    title: "EAGLE-3: Speculative Draft Training via Multi-Layer Fusion",
    authors: "Li et al.",
    year: 2025,
    arxivId: "2503.01840",
    arxivUrl: "https://arxiv.org/abs/2503.01840",
    category: "Routing, Inference & Steering",
    oneLiner:
      "Fuse low-, mid-, and high-layer target hidden states into a 1-layer speculative draft head trained directly with top-k logit distillation for lossless 3x–6x decoding speedups.",
    story:
      "Earlier EAGLE draft heads hit a scaling ceiling because regressing top-layer hidden states via MSE lost low-level token detail and drifted during multi-step speculative rollouts. EAGLE-3 drops feature MSE completely, fuses three depths of target features, and trains with direct top-k logit distillation.",
    insight:
      "Extract GPU-resident TensorRefs for low, middle, and top target layers plus top-32 target logits, fuse them in an eagle3_draft adapter on a frozen target trunk, and optimize topk_kl_distill with training-time unrolling.",
    whyGrad:
      "target.score_logprobs(top_k=32, return_layers=[2, 18, 34]) + adapter='eagle3_draft' + built-in topk_kl_distill train the full speculative draft head in 34 lines with zero 152k-vocab HTTP traffic.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Multi-layer TensorRefs + eagle3_draft adapter + built-in topk_kl_distill eliminate custom draft-training forks.",
    },
    walkthrough: [
      { title: "Extract multi-layer features & top-32 logits in one pass", explanation: "Request return_layers=[2, 18, 34] and top_k=32 from the frozen target Artifact.", gradCall: "target.score_logprobs(..., top_k=32, return_layers=[2, 18, 34])" },
      { title: "Attach the frozen-trunk eagle3_draft adapter", explanation: "Set adapter='eagle3_draft', train_mode='frozen_head', and rollout_steps=4.", gradCall: "ModelSpec(..., adapter='eagle3_draft', train_mode='frozen_head')" },
      { title: "Distill with built-in topk_kl_distill and export", explanation: "Train directly on target logit distributions and export the lossless draft .grad bundle.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'topk_kl_distill'})" },
    ],
    gotchas: [
      "Train on target-generated completions rather than raw web text to boost accepted draft length by +1 token.",
      "Use a higher LR (3e-4) than LoRA because the draft fusion layer initializes from scratch.",
    ],
    linesOfCode: 34,
    typicalBaselineLoc: "~1,800 LOC multi-layer hook extractor + draft trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-32B", label: "Qwen/Qwen3-32B (highest speedup ROI)", estTokens: "~10.7M tokens", duration: "~55 min", estCost: "~$12.80" },
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (fast reproduction)", estTokens: "~4.7M tokens", duration: "~24 min", estCost: "~$1.90" },
    ],
    datasets: [
      { id: "hf://Aeala/ShareGPT_Vicuna_unfiltered", label: "ShareGPT Conversations", source: "Hugging Face (public)", examples: "68,000 dialogues" },
    ],
    primitives: [
      { label: "eagle3_draft adapter", href: "/docs/reference/primitives/" },
      { label: "topk_kl_distill", href: "/docs/training/recipes/distillation/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Datum, DatumTargets, Grad, ModelInput, ModelSpec

client = Grad()
target_id = "Qwen/Qwen3-8B"
target = client.artifacts.get(target_id)
fusion_layers = [2, 18, 34]

with client.trainers.create(
    ModelSpec(
        base=target_id, adapter="eagle3_draft", train_mode="frozen_head",
        params={"fusion_layers": fusion_layers, "rollout_steps": 4},
    ),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_chat_batches("hf://Aeala/ShareGPT_Vicuna_unfiltered", batch_size=16)):
        t_out = target.score_logprobs(
            prefix_tokens=batch.prompt_tokens, response_tokens=batch.response_tokens,
            top_k=32, return_layers=fusion_layers,
        )
        datums = [
            Datum(
                ModelInput(tokens=p + r),
                DatumTargets(response_offset=len(p), teacher_topk=t_out["topk_refs"][i]),
                metadata={"layer_refs": [t_out["layer_refs"][l][i] for l in fusion_layers]},
            )
            for i, (p, r) in enumerate(zip(batch.prompt_tokens, batch.response_tokens))
        ]
        fb = trainer.forward_backward(datums, loss={"kind": "topk_kl_distill"})
        opt = trainer.optim_step(lr=3e-4, grad_clip=1.0)
        print(f"step={step} eagle3_kl={fb.result().loss:.4f}"); opt.result()
    draft = trainer.export(name="qwen3-8b-eagle3-draft")`,
    paperYaml: `slug: eagle-3
title: "EAGLE-3 Speculative Draft Training"
arxiv: "https://arxiv.org/abs/2503.01840"
category: routing-steering-tts
public_dataset: "hf://Aeala/ShareGPT_Vicuna_unfiltered"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/eagle-3 (arXiv:2503.01840)
Dataset   hf://Aeala/ShareGPT_Vicuna_unfiltered (public chat slices)
Model     Qwen/Qwen3-8B (frozen) + eagle3_draft (layers=[2,18,34], rollout_steps=4)
Loss      topk_kl_distill (top_k=32) · AdamW lr=3.0e-4
Estimate  ~4.7M tokens · ~24 min · ~$1.90 · warnings: 0`,
    benchmarks: [
      { benchmark: "Lossless decoding speedup", paperReported: "3.0x–6.5x speedup over vanilla decoding (+1.4x over EAGLE-2)", templateSetup: "Qwen/Qwen3-8B · fusion_layers=[2,18,34] · rollout_steps=4" },
    ],
    bibtex: `@article{li2025eagle3,
  title={EAGLE-3: Scaling up Inference Acceleration of LLMs via Training-Time Test},
  author={Li, Yuhui and others},
  journal={arXiv preprint arXiv:2503.01840},
  year={2025}
}`,
  },
  {
    slug: "medusa",
    shortTitle: "Medusa",
    title: "Medusa: Multi-Head Parallel Decoding Without a Separate Draft Model",
    authors: "Cai et al.",
    year: 2024,
    arxivId: "2401.10774",
    arxivUrl: "https://arxiv.org/abs/2401.10774",
    category: "Routing, Inference & Steering",
    oneLiner:
      "Attach K parallel token-level decoding heads onto a frozen LLM backbone so a single forward pass proposes tokens t+2, t+3, and t+4 with zero separate draft model.",
    story:
      "Traditional speculative decoding forces you to maintain a matched draft model with an identical tokenizer and synchronized KV cache. Medusa removes the draft model completely by bolting K tiny heads directly onto the target LLM's last hidden state.",
    insight:
      "Freeze the backbone (Medusa-1) and attach K token_level=True heads predicting tokens t+k+1 with exponentially decayed cross-entropy weight 0.8^k — leaving the base distribution bit-for-bit untouched.",
    whyGrad:
      "ModelSpec.heads declares all K token-level decoding heads declaratively, and built-in cross_entropy(heads={...}) computes shifted multi-horizon loss directly on the GPU — zero 152k-vocab logits ever cross the network.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Server-side multi-horizon head CE (added after our 50-paper smell audit eliminated client-side 152k-vocab transfers!) shrinks Medusa to 21 clean lines.",
    },
    walkthrough: [
      { title: "Declare K=3 token-level decoding heads on a frozen trunk", explanation: "Set train_mode='frozen_head' and attach k1, k2, k3 heads.", gradCall: "heads={f'k{k}': {'dim': base.vocab_size, 'token_level': True} for k in (1, 2, 3)}" },
      { title: "Run server-side shifted t+k+1 cross-entropy with 0.8^k decay", explanation: "Pass heads={k1: {shift: 2, weight: 0.8}, ...} to built-in cross_entropy so 152k-vocab logits never leave the GPU.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'cross_entropy', 'heads': loss_heads})" },
      { title: "Export compact multi-head artifact", explanation: "Package only the Medusa head weights without duplicating the frozen backbone.", gradCall: "trainer.export(name='qwen3-8b-medusa-3h')" },
    ],
    gotchas: [
      "Self-distill training replies from the exact target model — off-distribution text lowers acceptance rate by 20–30%.",
      "Double-check the shift: the native LM head predicts t+1, so Medusa head k1 predicts t+2 (shift=2).",
    ],
    linesOfCode: 21,
    typicalBaselineLoc: "~1,100 LOC custom HF model subclass + Medusa trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~5.6M tokens", duration: "~28 min", estCost: "~$2.25" },
    ],
    datasets: [
      { id: "hf://Aeala/ShareGPT_Vicuna_unfiltered", label: "ShareGPT Conversations", source: "Hugging Face (public)", examples: "60,000 dialogues" },
    ],
    primitives: [
      { label: "Token-level heads", href: "/docs/reference/primitives/" },
      { label: "Multi-horizon cross_entropy", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
base = client.artifacts.get(base_id)

heads = {f"k{k}": {"dim": base.vocab_size, "token_level": True} for k in (1, 2, 3)}
loss_heads = {f"k{k}": {"shift": k + 1, "weight": 0.8 ** k} for k in (1, 2, 3)}

with client.trainers.create(
    ModelSpec(base=base_id, adapter="frozen_head", train_mode="frozen_head", heads=heads),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_sharegpt_batches("hf://Aeala/ShareGPT_Vicuna_unfiltered", batch_size=32)):
        datums = [base.to_datum(messages=m) for m in batch.conversations]
        # Computed strictly on the GPU worker — zero 152k-vocab logits over HTTP
        fb = trainer.forward_backward(datums, loss={"kind": "cross_entropy", "heads": loss_heads})
        opt = trainer.optim_step(lr=1e-3, grad_clip=1.0)
        print(f"step={step} medusa_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="qwen3-8b-medusa-3h")`,
    paperYaml: `slug: medusa
title: "Medusa Multi-Head Decoding"
arxiv: "https://arxiv.org/abs/2401.10774"
category: routing-steering-tts
public_dataset: "hf://Aeala/ShareGPT_Vicuna_unfiltered"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/medusa (arXiv:2401.10774)
Dataset   hf://Aeala/ShareGPT_Vicuna_unfiltered (public dialogues)
Model     Qwen/Qwen3-8B (frozen) + 3 token_level heads (k1, k2, k3)
Loss      built-in cross_entropy(heads={k1..k3, shift=2..4, decay=0.8^k})
Estimate  ~5.6M tokens · ~28 min · ~$2.25 · warnings: 0`,
    benchmarks: [
      { benchmark: "Lossless decoding speedup", paperReported: "2.2x–2.8x speedup on Vicuna-7B/13B/33B with zero separate draft model", templateSetup: "Qwen/Qwen3-8B frozen trunk · K=3 heads · decay=0.8" },
    ],
    bibtex: `@inproceedings{cai2024medusa,
  title={Medusa: Simple LLM Inference Acceleration Framework with Multiple Decoding Heads},
  author={Cai, Tianle and others},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "repe",
    shortTitle: "RepE",
    title: "Representation Engineering (RepE): Concept Reading & Steering Vectors",
    authors: "Zou et al. (CAIS)",
    year: 2023,
    arxivId: "2310.01405",
    arxivUrl: "https://arxiv.org/abs/2310.01405",
    category: "Routing, Inference & Steering",
    oneLiner:
      "Read and steer high-level behaviors like honesty or conciseness directly in middle-layer residual streams with zero gradient steps.",
    story:
      "Adjusting a model's honesty or sycophancy normally means collecting thousands of preference pairs and running hours of fine-tuning. RepE showed that high-level concepts already sit along clean linear directions inside middle transformer layers — extractable from 128 contrastive pairs in seconds with zero weight updates.",
    insight:
      "Extract middle-layer hidden states on matched positive/negative contrastive prompts via return_layers, compute unit-normalized mean-difference steering vectors v_l, and inject alpha * v_l at inference time.",
    whyGrad:
      "base.embed(..., return_layers=...) + trainer.fit_batch([], solver='mean_diff_steering') fits and bakes runtime steering hooks directly into a deployable .grad artifact in 25 lines with zero SGD.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Zero gradient loops and zero custom PyTorch forward hooks — fit_batch(solver='mean_diff_steering') exports a steered artifact in 2 minutes.",
    },
    walkthrough: [
      { title: "Extract middle-layer activations on contrastive pairs", explanation: "Run matched honest vs. untruthful prompts through base.embed(return_layers=[14, 16, 18, 20]).", gradCall: "base.embed(pos_inputs, return_layers=layers)['layer_refs']" },
      { title: "Solve steering vectors in closed form", explanation: "Pass pos_refs, neg_refs, and alpha into trainer.fit_batch([], solver='mean_diff_steering').", gradCall: "trainer.fit_batch([], solver='mean_diff_steering', params=...)" },
      { title: "Export & verify truthfulness lift", explanation: "Compare steered.sample() vs base.sample() on held-out probes before deploying.", gradCall: "trainer.export(name='qwen3-8b-honesty-repe')" },
    ],
    gotchas: [
      "Target middle layers (40%–60% depth) — early layers steer syntax, while top layers cause repetition.",
      "Sweep alpha (0.5–2.0) on a small fluency + truthfulness set so steering doesn't hurt coherence.",
    ],
    linesOfCode: 25,
    typicalBaselineLoc: "~700 LOC custom forward-hook + PCA extractor",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~350K tokens", duration: "~2 min", estCost: "~$0.15" },
    ],
    datasets: [
      { id: "hf://truthfulqa/truthful_qa", label: "TruthfulQA Honesty Pairs", source: "Hugging Face (public)", examples: "128 contrastive pairs + 817 eval" },
    ],
    primitives: [
      { label: "Closed-form fit_batch", href: "/docs/training/custom-loops/" },
      { label: "Artifact.embed", href: "/docs/training/recipes/embeddings/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelInput, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
base = client.artifacts.get(base_id)
layers = [14, 16, 18, 20]

pairs = load_contrastive_pairs("hf://truthfulqa/truthful_qa", limit=128)
pos_in = [ModelInput(messages=[{"role": "user", "content": f"Pretend you are an honest assistant. {s}"}]) for s in pairs]
neg_in = [ModelInput(messages=[{"role": "user", "content": f"Pretend you are an untruthful assistant. {s}"}]) for s in pairs]

pos_refs = base.embed(pos_in, pool="last", return_layers=layers)["layer_refs"]
neg_refs = base.embed(neg_in, pool="last", return_layers=layers)["layer_refs"]

with client.trainers.create(
    ModelSpec(base=base_id, adapter="frozen_head", train_mode="frozen_head"),
    compute="gpu",
) as trainer:
    trainer.fit_batch(
        datums=[],
        solver="mean_diff_steering",
        params={"pos_refs": pos_refs, "neg_refs": neg_refs, "layers": layers, "alpha": 1.25},
    )
    steered = trainer.export(name="qwen3-8b-honesty-repe")

probe = [ModelInput(messages=[{"role": "user", "content": "What happens if you crack your knuckles a lot?"}])]
print("Steered:", steered.sample(probe, n=1, temperature=0.0, max_new_tokens=96)[0][0].output["text"])`,
    paperYaml: `slug: repe
title: "RepE: Concept Reading & Steering Vectors"
arxiv: "https://arxiv.org/abs/2310.01405"
category: routing-steering-tts
public_dataset: "hf://truthfulqa/truthful_qa"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/repe (arXiv:2310.01405)
Dataset   hf://truthfulqa/truthful_qa (128 contrastive pairs · public)
Model     Qwen/Qwen3-8B (frozen) · layers=[14,16,18,20] · alpha=1.25
Solver    mean_diff_steering (zero-gradient closed-form)
Estimate  ~350K tokens · ~2 min · ~$0.15 · warnings: 0`,
    benchmarks: [
      { benchmark: "TruthfulQA MC1 lift", paperReported: "+10–18 pts truthfulness lift with zero weight updates", templateSetup: "Qwen/Qwen3-8B · 128 pairs · alpha=1.25" },
    ],
    bibtex: `@article{zou2023repe,
  title={Representation Engineering: A Top-Down Approach to AI Transparency},
  author={Zou, Andy and others},
  journal={arXiv preprint arXiv:2310.01405},
  year={2023}
}`,
  },
  {
    slug: "kimi-k1-5",
    shortTitle: "Kimi k1.5",
    title: "Kimi k1.5: Scaling RL with Length Penalty & Partial Rollouts",
    authors: "Kimi Team",
    year: 2025,
    arxivId: "2501.12599",
    arxivUrl: "https://arxiv.org/abs/2501.12599",
    category: "Routing, Inference & Steering",
    oneLiner:
      "Eliminate long-tail GPU bubbles and chain-of-thought overthinking via chunked partial rollout replay and group-normalized length rewards.",
    story:
      "Long-context reasoning RL suffers two killer bottlenecks: one 32k-token straggler leaves 95% of GPUs idling, and models quickly start padding simple questions into 8k-token essays. Kimi k1.5 solved both with chunked partial rollouts and a smooth group-relative length reward.",
    insight:
      "Cap each sampling chunk at 2,048 tokens; unfinished prefixes go into a replay buffer and resume next step via resume_from under updated weights, while finished groups receive Kimi's length-shaped reward favoring concise correct proofs.",
    whyGrad:
      "Artifact.sample(resume_from=partials) preserves per-chunk sampling_logprobs and weight_versions automatically, so built-in CISPO stays unbiased across multi-step partial rollouts.",
    smoothness: {
      rating: "Clean",
      verdict:
        "resume_from chunking + built-in CISPO handle mixed-version partial rollouts cleanly in 44 lines.",
    },
    walkthrough: [
      { title: "Sample fixed 2,048-token chunks and resume unfinished partials", explanation: "Cap worst-case step latency regardless of total CoT length.", gradCall: "snap.sample(inputs, max_new_tokens=2048, resume_from=partials)" },
      { title: "Shape rewards with Kimi's group length penalty", explanation: "Reward concise correct proofs highest and softly penalize verbose failures.", gradCall: "kimi_length_reward(ok, len_i, min_len, max_len, coef)" },
      { title: "Step across mixed weight versions with CISPO", explanation: "Each resumed chunk carries its exact generating sampling_logprobs.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'cispo', 'kl_beta': 0.01})" },
    ],
    gotchas: [
      "Ramp length penalty weight from 0.0 -> 0.5 after 30–50 warm-up steps so you don't suppress early long-CoT discovery.",
      "Drop any partial exceeding max_total_tokens=16384 with reward=0.0 so infinite loops don't clog the buffer.",
    ],
    linesOfCode: 36,
    typicalBaselineLoc: "~2,500 LOC async rollout manager + chunked KV server",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~8.8M tokens", duration: "~44 min", estCost: "~$3.50" },
    ],
    datasets: [
      { id: "hf://BytedTsinghua-SIA/DAPO-Math-17k", label: "DAPO-Math-17k", source: "Hugging Face (public)", examples: "17,000 math prompts" },
    ],
    primitives: [
      { label: "sample(resume_from=...)", href: "/docs/reference/primitives/" },
      { label: "CISPO off-policy RL", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from collections import defaultdict
import grad
from grad import Grad, ModelSpec

client = Grad()
CHUNK, MAX_TOTAL = 2048, 16384

def kimi_len_reward(ok: bool, length: int, lo: int, hi: int, coef: float) -> float:
    if hi == lo:
        return 1.0 if ok else 0.0
    lam = 0.5 - (length - lo) / (hi - lo)
    return (1.0 + coef * lam) if ok else (coef * min(0.0, lam))

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    partial_buf, completed = [], defaultdict(list)
    for step, batch in enumerate(load_math_batches("hf://BytedTsinghua-SIA/DAPO-Math-17k", batch_size=16)):
        snap = trainer.snapshot()
        resuming, partial_buf = partial_buf[:32], partial_buf[32:]
        fresh = snap.sample(batch.prompt_inputs, n=4, max_new_tokens=CHUNK, stop=["</answer>"])
        resumed = [g[0] for g in snap.sample(resume_from=[p[2] for p in resuming], n=1, max_new_tokens=CHUNK, stop=["</answer>"])] if resuming else []

        all_items = [(f"s{step}_{i}", gold, tr) for i, (grp, gold) in enumerate(zip(fresh, batch.answers)) for tr in grp]
        all_items += [(gid, gold, tr) for (gid, gold, _), tr in zip(resuming, resumed)]
        for gid, gold, tr in all_items:
            done = "</answer>" in tr.output["text"] or len(tr.output["token_ids"]) >= MAX_TOTAL
            (completed[gid] if done else partial_buf).append((gid, gold, tr) if not done else (gold, tr))

        coef = min(0.5, step / 50.0 * 0.5)
        ready_groups, ready_rewards = [], []
        for gid in [k for k, v in list(completed.items()) if len(v) >= 4]:
            items = completed.pop(gid)
            lens = [len(t.output["response_tokens"]) for _, t in items]
            ready_groups.append([t for _, t in items])
            ready_rewards.append([kimi_len_reward(grade_boxed(t.output["text"], g), l, min(lens), max(lens), coef) for (g, t), l in zip(items, lens)])

        datums = grad.group_datums(ready_groups, rewards=ready_rewards, norm="mean")
        fb = trainer.forward_backward(datums, loss={"kind": "cispo", "clip_low": 0.2, "clip_high": 0.2, "kl_beta": 0.01})
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        print(f"step={step} partials={len(partial_buf)} datums={len(datums)} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="kimi-k1-5-long-cot", merge_adapter=True)`,
    paperYaml: `slug: kimi-k1-5
title: "Kimi k1.5: Length Penalty & Partial Rollouts"
arxiv: "https://arxiv.org/abs/2501.12599"
category: routing-steering-tts
public_dataset: "hf://BytedTsinghua-SIA/DAPO-Math-17k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/kimi-k1-5 (arXiv:2501.12599)
Dataset   hf://BytedTsinghua-SIA/DAPO-Math-17k (17,000 math prompts · public)
Model     Qwen/Qwen3-8B · partial rollout chunks=2048 (max 16k)
Loss      cispo (kl_beta=0.01) + ramped group length penalty
Estimate  ~8.8M tokens · ~44 min · ~$3.50 · warnings: 0`,
    benchmarks: [
      { benchmark: "Long-CoT RL efficiency & accuracy", paperReported: "Matches o1 on AIME/MATH while cutting response length 40%+ via length rewards", templateSetup: "DAPO-Math-17k · chunk=2048 · CISPO + partial rollout replay" },
    ],
    bibtex: `@article{kimi2025k15,
  title={Kimi k1.5: Scaling Reinforcement Learning with LLMs},
  author={Kimi Team},
  journal={arXiv preprint arXiv:2501.12599},
  year={2025}
}`,
  },
];
