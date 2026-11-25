export type PaperCategory =
  | "Distillation"
  | "RL & Reasoning"
  | "Context Compression"
  | "Routing & Efficiency";

export type PaperModelOption = {
  id: string;
  label: string;
  compute: string;
  duration: string;
  estCost: string;
};

export type PaperDatasetOption = {
  id: string;
  label: string;
  source: string;
  examples: string;
};

export type PaperMetricRow = {
  benchmark: string;
  paperReported: string;
  templateSetup: string;
};

export type PaperGuide = {
  slug: string;
  shortTitle: string;
  title: string;
  authors: string;
  year: number;
  arxivId: string;
  arxivUrl: string;
  category: PaperCategory;
  oneLiner: string;
  whyGrad: string;
  linesOfCode: number;
  typicalBaselineLoc: string;
  mode: "Managed recipe" | "Custom loop";
  entrypoint: "train.py" | "recipe.yaml";
  models: PaperModelOption[];
  datasets: PaperDatasetOption[];
  primitives: Array<{ label: string; href: string }>;
  keyIdeas: string[];
  codeLabel: string;
  codeLanguage: "python" | "yaml";
  code: string;
  paperYaml: string;
  dryRunOutput: string;
  benchmarks: PaperMetricRow[];
  bibtex: string;
};

export const paperCategories: PaperCategory[] = [
  "Distillation",
  "RL & Reasoning",
  "Context Compression",
  "Routing & Efficiency",
];

export const papers: PaperGuide[] = [
  {
    slug: "sdft",
    shortTitle: "SDFT",
    title: "Self-Distillation Fine-Tuning (SDFT)",
    authors: "Shenfeld et al.",
    year: 2026,
    arxivId: "2601.19897",
    arxivUrl: "https://arxiv.org/abs/2601.19897",
    category: "Distillation",
    oneLiner:
      "Learn new skills from demonstrations without catastrophic forgetting by using the same base model conditioned on an in-context example as teacher.",
    whyGrad:
      "Artifact.score_logprobs() accepts split (prefix_tokens, response_tokens) and Trajectory.to_datum() aligns response_offset automatically — collapsing ~1,000 lines of shifted-token slicing into 22 lines with zero separate teacher deployment.",
    linesOfCode: 22,
    typicalBaselineLoc: "~1,100 LOC distributed PyTorch",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        compute: "1x H100",
        duration: "~18 min",
        estCost: "~$1.40",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        compute: "1x H100",
        duration: "~9 min",
        estCost: "~$0.70",
      },
      {
        id: "Qwen/Qwen3-32B",
        label: "Qwen/Qwen3-32B (LoRA rank 64)",
        compute: "4x H100",
        duration: "~38 min",
        estCost: "~$8.90",
      },
    ],
    datasets: [
      {
        id: "hf://sciknoweval/chemistry-demo",
        label: "SciKnowEval Chemistry",
        source: "Hugging Face (public)",
        examples: "1,200 demos + held-out eval",
      },
      {
        id: "hf://toolalpaca/eval",
        label: "ToolAlpaca Tool-Use",
        source: "Hugging Face (public)",
        examples: "2,400 tool demos",
      },
    ],
    primitives: [
      { label: "Trainer", href: "/docs/training/custom-loops/" },
      { label: "Artifact.score_logprobs", href: "/docs/training/recipes/distillation/" },
      { label: "topk_kl_distill", href: "/docs/reference/primitives/" },
    ],
    keyIdeas: [
      "The student generates completions on-policy seeing only the question.",
      "The frozen base model scores those exact student tokens while conditioning on (question + golden demonstration), returning compact top_k=20 logprob TensorRefs.",
      "Minimizing token-level forward KL updates the LoRA adapter where the student actually explores, preserving prior capabilities far better than offline SFT.",
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
teacher = client.artifacts.get(base_id)  # frozen base model, no extra deployment

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 64}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_sdft_batches("hf://sciknoweval/chemistry-demo")):
        # 1. Student samples on-policy seeing ONLY the question
        rollouts = [g[0] for g in trainer.snapshot().sample(batch.question_inputs, n=1, max_new_tokens=512)]

        # 2. Frozen teacher scores those exact tokens conditioned on (question + golden demo)
        t_refs = teacher.score_logprobs(
            prefix_tokens=batch.demo_prefix_tokens,
            response_tokens=[r.output["response_tokens"] for r in rollouts],
            top_k=20,
        )["topk_refs"]

        # 3. Pipelined top-k KL update (1 RTT)
        datums = [r.to_datum(teacher_topk=ref) for r, ref in zip(rollouts, t_refs)]
        fb = trainer.forward_backward(datums, loss={"kind": "topk_kl_distill"})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} kl_loss={fb.result().loss:.4f}"); opt.result()

    artifact = trainer.export(name="sdft-sciknoweval", merge_adapter=True)`,
    paperYaml: `slug: sdft
title: "Self-Distillation Fine-Tuning (SDFT)"
arxiv: "https://arxiv.org/abs/2601.19897"
category: distillation
public_dataset: "hf://sciknoweval/chemistry-demo"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py
hyperparams:
  lora_rank: 64
  top_k: 20
  lr: 2.0e-5
  groups_per_batch: 32`,
    dryRunOutput: `Template  papers/sdft (arXiv:2601.19897)
Dataset   hf://sciknoweval/chemistry-demo (1,200 train / 200 eval · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=64) · teacher=Qwen/Qwen3-8B (shared base)
Loss      topk_kl_distill (top_k=20) · AdamW lr=2.0e-5
Estimate  1x H100 · ~18 min · ~$1.40 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "New-domain skill gain",
        paperReported: "Matches or exceeds SFT on target skill benchmarks",
        templateSetup: "SciKnowEval Chemistry · LoRA rank 64 · top_k=20",
      },
      {
        benchmark: "Prior-capability retention",
        paperReported: "Avoids SFT catastrophic forgetting across sequential tasks",
        templateSetup: "Evaluated on held-out general QA + target domain split",
      },
    ],
    bibtex: `@article{shenfeld2026sdft,
  title={Self-Distillation Enables Continual Learning},
  author={Shenfeld, Idan and others},
  journal={arXiv preprint arXiv:2601.19897},
  year={2026}
}`,
  },
  {
    slug: "dapo",
    shortTitle: "DAPO",
    title: "DAPO: Open-Source LLM RL at Scale",
    authors: "Yu et al.",
    year: 2025,
    arxivId: "2503.14476",
    arxivUrl: "https://arxiv.org/abs/2503.14476",
    category: "RL & Reasoning",
    oneLiner:
      "Stabilize reasoning RL with asymmetric clip-higher ratios, dynamic zero-variance group filtering, and token-level policy gradients.",
    whyGrad:
      "Clip-higher (clip_low=0.2, clip_high=0.28) is built straight into loss='grpo', empty zero-variance batches are safe no-ops, and every step logs kl_sample_train automatically to verify exact sampler/trainer numerics.",
    linesOfCode: 34,
    typicalBaselineLoc: "~2,400 LOC Ray + vLLM + FSDP",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        compute: "1x H100",
        duration: "~35 min",
        estCost: "~$2.80",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        compute: "1x H100",
        duration: "~16 min",
        estCost: "~$1.25",
      },
      {
        id: "Qwen/Qwen3-32B",
        label: "Qwen/Qwen3-32B (LoRA rank 32)",
        compute: "4x H100",
        duration: "~65 min",
        estCost: "~$15.20",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math Reasoning",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
      {
        id: "hf://BytedTsinghua-SIA/DAPO-Math-17k",
        label: "DAPO-Math-17k",
        source: "Hugging Face (public)",
        examples: "17,000 competition math prompts",
      },
    ],
    primitives: [
      { label: "Trainer", href: "/docs/training/custom-loops/" },
      { label: "GRPO / DAPO loss", href: "/docs/training/recipes/rl-agents/" },
      { label: "Rubric", href: "/docs/training/environments/" },
    ],
    keyIdeas: [
      "Asymmetric Clip-Higher (clip_high=0.28 > clip_low=0.20) prevents entropy collapse on long reasoning traces.",
      "Dynamic sampling drops prompt groups whose rollouts all pass or all fail (zero advantage variance).",
      "Universal 1:1 token alignment and pipelined forward_backward() + optim_step() keep GPU utilization high without distributed boilerplate.",
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import statistics
from grad import Grad, ModelSpec

client = Grad()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        snap = trainer.snapshot()
        groups = snap.sample(
            batch.prompt_inputs,
            n=8,
            temperature=1.0,
            max_new_tokens=1024,
            stop=["</answer>"],
        )

        datums = []
        for group, gold in zip(groups, batch.answers):
            rewards = [grade_boxed_math(t.output["text"], gold) for t in group]
            sd = statistics.pstdev(rewards)
            if sd < 1e-6:
                continue  # DAPO dynamic sampling: skip zero-variance groups

            mean = statistics.fmean(rewards)
            for traj, r in zip(group, rewards):
                datums.append(traj.to_datum(advantage=(r - mean) / (sd + 1e-6)))

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.28})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        m = fb.result(); opt.result()
        print(f"step={step} datums={len(datums)} kl_st={m.metrics['kl_sample_train']:.5f}")

    artifact = trainer.export(name="dapo-gsm8k", merge_adapter=True)`,
    paperYaml: `slug: dapo
title: "DAPO: Open-Source LLM RL at Scale"
arxiv: "https://arxiv.org/abs/2503.14476"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py
hyperparams:
  group_size: 8
  clip_low: 0.20
  clip_high: 0.28
  lr: 2.0e-5`,
    dryRunOutput: `Template  papers/dapo (arXiv:2503.14476)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · group_size=8
Loss      grpo (clip_low=0.20, clip_high=0.28, dynamic zero-var skip)
Estimate  1x H100 · ~35 min (100 steps) · ~$2.80 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Reasoning pass@1 (AIME / GSM8K)",
        paperReported: "50 pts on AIME 2024 with Qwen2.5-32B (50% fewer steps than vanilla GRPO)",
        templateSetup: "GSM8K default smoke run (or DAPO-Math-17k) · Qwen/Qwen3-8B · group_size=8",
      },
      {
        benchmark: "Entropy & KL stability",
        paperReported: "Eliminates premature entropy collapse via clip_high=0.28",
        templateSetup: "Logged every step via metrics.kl_sample_train",
      },
    ],
    bibtex: `@article{yu2025dapo,
  title={DAPO: An Open-Source LLM Reinforcement Learning System at Scale},
  author={Yu, Qiying and others},
  journal={arXiv preprint arXiv:2503.14476},
  year={2025}
}`,
  },
  {
    slug: "cartridges",
    shortTitle: "Cartridges",
    title: "Context Cartridges (prefix_kv Compression)",
    authors: "Eyuboglu et al.",
    year: 2025,
    arxivId: "2506.06266",
    arxivUrl: "https://arxiv.org/abs/2506.06266",
    category: "Context Compression",
    oneLiner:
      "Compress a 50k–100k token static corpus into a tiny trainable KV-cache prefix (prefix_kv) on a frozen base model and swap cartridges per request.",
    whyGrad:
      "prefix_kv is a first-class adapter in grad's managed cartridge recipe — 12 lines of YAML or Python train the KV prefix against the full-context teacher and export a deployable .grad Cartridge.",
    linesOfCode: 12,
    typicalBaselineLoc: "~900 LOC custom attention & KV-cache hooks",
    mode: "Managed recipe",
    entrypoint: "recipe.yaml",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        compute: "1x H100",
        duration: "~14 min",
        estCost: "~$1.10",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        compute: "1x H100",
        duration: "~7 min",
        estCost: "~$0.55",
      },
    ],
    datasets: [
      {
        id: "hf://hazyresearch/cartridges-longhealth",
        label: "LongHealth Clinical Corpus",
        source: "Hugging Face (public)",
        examples: "60k-token corpus + QA probes",
      },
      {
        id: "hf://nyu-mll/quality",
        label: "QuALITY Long-Context QA",
        source: "Hugging Face (public)",
        examples: "Long stories + multiple-choice QA",
      },
    ],
    primitives: [
      { label: "recipe='cartridge'", href: "/docs/training/recipes/distillation/" },
      { label: "prefix_kv adapter", href: "/docs/reference/primitives/" },
      { label: "Endpoint deploy", href: "/docs/training/endpoints/" },
    ],
    keyIdeas: [
      "Freezes 100% of base model weights and trains only 128–512 virtual KV prefix tokens via top-k KL distillation against the full-context teacher.",
      "Eliminates repeated 30k–100k token system-prompt prefill latency and KV-cache memory on every user request.",
      "Exports as a small .grad artifact you can hot-swap per tenant or repository on a single shared base model deployment.",
    ],
    codeLabel: "recipe.yaml",
    codeLanguage: "yaml",
    code: `# Run with: grad run papers/cartridges --wait
dataset: hf://hazyresearch/cartridges-longhealth
name: longhealth-cartridge
recipe: cartridge
base: Qwen/Qwen3-8B
teacher: Qwen/Qwen3-8B
context_ref: hf://hazyresearch/cartridges-longhealth/corpus.md
adapter:
  kind: prefix_kv
  num_tokens: 256
loss:
  kind: topk_kl_distill
  top_k: 20
optimizer:
  kind: adamw
  lr: 2.0e-2`,
    paperYaml: `slug: cartridges
title: "Context Cartridges (prefix_kv Compression)"
arxiv: "https://arxiv.org/abs/2506.06266"
category: context-compression
public_dataset: "hf://hazyresearch/cartridges-longhealth"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: recipe.yaml
hyperparams:
  num_tokens: 256
  top_k: 20
  lr: 2.0e-2`,
    dryRunOutput: `Template  papers/cartridges (arXiv:2506.06266)
Dataset   hf://hazyresearch/cartridges-longhealth (corpus: 58,420 tokens · 640 QA prompts)
Model     Qwen/Qwen3-8B (frozen) + prefix_kv (256 virtual tokens -> 228x KV compression)
Loss      topk_kl_distill (top_k=20) · AdamW lr=2.0e-2
Estimate  1x H100 · ~14 min · ~$1.10 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "KV-cache memory & throughput",
        paperReported: "38.6x smaller KV memory & up to 26.4x higher throughput vs. in-context prompting",
        templateSetup: "256 virtual prefix tokens compressing ~58k-token LongHealth corpus",
      },
      {
        benchmark: "Task QA accuracy",
        paperReported: "Matches within ~2–3 pts of full-context prompting on LongHealth",
        templateSetup: "EvalReport compares cartridge vs. full-context teacher automatically",
      },
    ],
    bibtex: `@article{eyuboglu2025cartridges,
  title={Cartridges: Lightweight and general-purpose long context representations via self-study},
  author={Eyuboglu, Sabri and others},
  journal={arXiv preprint arXiv:2506.06266},
  year={2025}
}`,
  },
  {
    slug: "routellm",
    shortTitle: "RouteLLM",
    title: "Calibrated Model Routing (RouteLLM + SLA-Lagrangian)",
    authors: "Ong et al.",
    year: 2024,
    arxivId: "2406.18665",
    arxivUrl: "https://arxiv.org/abs/2406.18665",
    category: "Routing & Efficiency",
    oneLiner:
      "Train a sub-10ms CPU model router from public preference traces that offloads easy prompts to cheaper models with a calibrated quality SLA.",
    whyGrad:
      "Runs on CPU in ~6 seconds for $0 GPU cost via grad's managed router recipe, outputs held-out Pareto curves with 95% bootstrap CIs, and deploys straight into an sla_lagrangian endpoint with 10% fallback probes.",
    linesOfCode: 10,
    typicalBaselineLoc: "~600 LOC embedding pipeline + custom threshold tuner",
    mode: "Managed recipe",
    entrypoint: "recipe.yaml",
    models: [
      {
        id: "BAAI/bge-small-en-v1.5",
        label: "BAAI/bge-small-en-v1.5 (CPU, <10ms)",
        compute: "CPU",
        duration: "~6 sec",
        estCost: "$0.00 GPU",
      },
      {
        id: "Qwen/Qwen3-0.6B",
        label: "Qwen/Qwen3-0.6B (GPU, long context)",
        compute: "1x L4 / H100",
        duration: "~3 min",
        estCost: "~$0.25",
      },
    ],
    datasets: [
      {
        id: "hf://lmsys/chatbot_arena_conversations",
        label: "Chatbot Arena Conversations",
        source: "Hugging Face (public)",
        examples: "33,000 multi-model traces",
      },
    ],
    primitives: [
      { label: "recipe='router'", href: "/docs/training/recipes/router/" },
      { label: "fit_batch solver", href: "/docs/training/custom-loops/" },
      { label: "sla_lagrangian Endpoint", href: "/docs/training/endpoints/" },
    ],
    keyIdeas: [
      "Extracts frozen embeddings once and solves a calibrated dual-head kernel + L2-logistic objective on CPU in seconds.",
      "Computes an offline cost-vs-quality Pareto frontier with 95% bootstrap confidence intervals before shipping.",
      "Deploys with 10% unbiased fallback probes and a primal-dual λ controller that holds live quality drop within budget.",
    ],
    codeLabel: "recipe.yaml",
    codeLanguage: "yaml",
    code: `# Run with: grad run papers/routellm --wait
dataset: hf://lmsys/chatbot_arena_conversations
name: arena-router
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
title: "Calibrated Model Routing (RouteLLM + SLA-Lagrangian)"
arxiv: "https://arxiv.org/abs/2406.18665"
category: routing
public_dataset: "hf://lmsys/chatbot_arena_conversations"
base_default: "BAAI/bge-small-en-v1.5"
compute: cpu
entrypoint: recipe.yaml
hyperparams:
  solver: dual_head_kernel_lbfgs
  max_quality_drop: 0.02`,
    dryRunOutput: `Template  papers/routellm (arXiv:2406.18665)
Dataset   hf://lmsys/chatbot_arena_conversations (28,050 train / 4,950 eval · public)
Model     BAAI/bge-small-en-v1.5 (frozen) + dual_head_kernel_lbfgs
Guardrail sla_lagrangian · target quality drop <= 2.0% · 10% fallback probes
Estimate  CPU · ~6 sec · $0.00 GPU · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Cost reduction at >=95% strong-model quality",
        paperReported: "2x–3.6x cost reduction on MT-Bench / MMLU / GSM8K in RouteLLM",
        templateSetup: "Chatbot Arena public split · BAAI/bge-small-en-v1.5 · 6s CPU fit",
      },
      {
        benchmark: "Serving latency",
        paperReported: "Sub-10ms router overhead before LLM dispatch",
        templateSetup: "ONNX CPU runtime + optional zero-hop Gradiated gateway mode",
      },
    ],
    bibtex: `@article{ong2024routellm,
  title={RouteLLM: Learning to Route LLMs with Preference Data},
  author={Ong, Isaac and Almahairi, Amjad and Wu, Vincent and Chiang, Wei-Lin and Wu, Tianhao and Gonzalez, Joseph E. and Kadous, M. Waleed and Stoica, Ion},
  journal={arXiv preprint arXiv:2406.18665},
  year={2024}
}`,
  },
];

export const paperBySlug = (slug: string): PaperGuide | undefined =>
  papers.find((p) => p.slug === slug);
