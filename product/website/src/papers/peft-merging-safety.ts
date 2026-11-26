import type { PaperGuide } from "./types";

export const peftMergingSafetyPapers: PaperGuide[] = [
  {
    slug: "dora",
    shortTitle: "DoRA",
    title: "DoRA: Weight-Decomposed Low-Rank Adaptation",
    authors: "Liu et al. (NVIDIA)",
    year: 2024,
    arxivId: "2402.09353",
    arxivUrl: "https://arxiv.org/abs/2402.09353",
    category: "PEFT, Merging & Safety",
    oneLiner:
      "Decouple weight magnitude from low-rank directional updates to close the accuracy gap between LoRA and full fine-tuning with zero inference overhead.",
    story:
      "Standard LoRA forces weight magnitude and direction to move together inside one tiny low-rank subspace — whereas full fine-tuning freely rotates direction while barely changing magnitude. DoRA decomposes weights into a learned magnitude vector m and a unit-normalized directional matrix (W0 + BA), routinely beating full-rank LoRA at half the rank.",
    insight:
      "Parameterize W' = m * (W0 + BA) / ||W0 + BA||_c (column-norm detached during backprop), then fold W' back into a single standard linear layer at export for zero serving overhead.",
    whyGrad:
      "DoRA is a first-class adapter in grad's managed SFT recipe (adapter.kind: dora) with built-in merge_adapter: true — zero custom linear wrappers.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Switching adapter.kind from lora to dora in YAML enables full DoRA with zero custom Python.",
    },
    walkthrough: [
      {
        title: "Select adapter.kind: dora in managed SFT YAML",
        explanation:
          "Automatically allocates learned column magnitudes alongside low-rank directional updates.",
        gradCall: "adapter: { kind: dora, rank: 32, alpha: 64 }",
      },
      {
        title: "Run managed SFT with cosine warmup",
        explanation:
          "grad handles assistant-only masking and detached column-norm backprop automatically.",
        gradCall: "grad run papers/dora --wait",
      },
      {
        title: "Fold into standalone weights at export",
        explanation:
          "merge_adapter: true produces zero-latency-overhead merged weights.",
        gradCall: "merge_adapter: true",
      },
    ],
    gotchas: [
      "DoRA shines most at lower ranks (r=8–32) where LoRA's coupled geometry bottlenecks most.",
      "Keep weight_decay low (0.0–0.01) so AdamW doesn't shrink the magnitude vector m toward zero.",
    ],
    linesOfCode: 16,
    typicalBaselineLoc: "~850 LOC PEFT + custom Linear wrapper",
    mode: "Managed recipe",
    entrypoint: "recipe.yaml",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~4.6M tokens",
        duration: "~24 min",
        estCost: "~$1.85",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~3.6M tokens",
        duration: "~12 min",
        estCost: "~$0.90",
      },
    ],
    datasets: [
      {
        id: "hf://zwhe99/commonsense_170k",
        label: "Commonsense170K",
        source: "Hugging Face (public)",
        examples: "170,420 reasoning pairs",
      },
    ],
    primitives: [
      { label: "SFT recipe", href: "/docs/training/recipes/sft-dpo/" },
      { label: "ModelSpec adapters", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "recipe.yaml",
    codeLanguage: "yaml",
    code: `# Run with: grad run papers/dora --wait
dataset: hf://zwhe99/commonsense_170k
name: dora-commonsense-8b
recipe: sft
base: Qwen/Qwen3-8B
compute: gpu
adapter:
  kind: dora
  rank: 32
  alpha: 64
optimizer:
  kind: adamw
  lr: 2.0e-4
  weight_decay: 0.01
split: { strategy: random, eval_fraction: 0.05 }
merge_adapter: true`,
    paperYaml: `slug: dora
title: "DoRA: Weight-Decomposed LoRA"
arxiv: "https://arxiv.org/abs/2402.09353"
category: peft
public_dataset: "hf://zwhe99/commonsense_170k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: recipe.yaml`,
    dryRunOutput: `Template  papers/dora (arXiv:2402.09353)
Dataset   hf://zwhe99/commonsense_170k (161,899 train / 8,521 eval · public)
Model     Qwen/Qwen3-8B · adapter=dora (rank=32, alpha=64) · merge_adapter=true
Loss      cross_entropy · AdamW lr=2.0e-4
Estimate  ~4.6M tokens · ~24 min · ~$1.85 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Commonsense Reasoning (8 tasks)",
        paperReported:
          "+1.0% to +3.7% over LoRA across LLaMA-7B/8B with zero inference overhead",
        templateSetup: "Commonsense170K · DoRA rank 32",
      },
    ],
    bibtex: `@inproceedings{liu2024dora,
  title={DoRA: Weight-Decomposed Low-Rank Adaptation},
  author={Liu, Shih-Yang and others},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "lora-plus",
    shortTitle: "LoRA+",
    title: "LoRA+: Differential Learning Rates for Low-Rank Adaptation",
    authors: "Hayou et al.",
    year: 2024,
    arxivId: "2402.12354",
    arxivUrl: "https://arxiv.org/abs/2402.12354",
    category: "PEFT, Merging & Safety",
    oneLiner:
      "Train LoRA output projection B at 16x the learning rate of input projection A to double convergence speed at zero extra FLOPs.",
    story:
      "Nearly every LoRA script hands one learning rate to both A and B. Using maximal-update parameterization (muP), Hayou et al. proved that sharing one LR makes LoRA feature learning asymptotically inefficient as model width grows — simply setting lr_B = 16 * lr_A doubles convergence speed for free.",
    insight:
      "Assign differential learning rates eta_B = lambda * eta_A (lambda=16 for 7B+ transformers) so zero-initialized B rapidly aligns the output subspace while A stays stable.",
    whyGrad:
      "trainer.optim_step(param_groups=[...]) matches lora_A and lora_B server-side with two dict entries — zero custom optimizer hooks.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Two entries in optim_step(param_groups=...) implement full LoRA+ with zero model patching.",
    },
    walkthrough: [
      {
        title: "Run standard cross-entropy forward-backward",
        explanation:
          "Forward pass and LoRA architecture remain completely untouched.",
        gradCall:
          "trainer.forward_backward(datums, loss={'kind': 'cross_entropy'})",
      },
      {
        title: "Pass differential param_groups to optim_step",
        explanation:
          "Match lora_A at lr_a and lora_B at 16 * lr_a alongside a cosine decay schedule.",
        gradCall:
          "trainer.optim_step(param_groups=[{'match': 'lora_A', 'lr': lr_a}, {'match': 'lora_B', 'lr': lr_a * 16}])",
      },
      {
        title: "Export merged checkpoint",
        explanation:
          "Zero runtime overhead — merges identically to vanilla LoRA.",
        gradCall: "trainer.export(name='lora-plus-8b', merge_adapter=True)",
      },
    ],
    gotchas: [
      "Lower eta_A by 2–4x compared to your vanilla LoRA LR before multiplying eta_B by 16x.",
      "Keep grad_clip=1.0 during early warmup steps while B moves away from zero initialization.",
    ],
    linesOfCode: 21,
    typicalBaselineLoc: "~650 LOC HF Trainer + custom create_optimizer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~2.8M tokens",
        duration: "~14 min",
        estCost: "~$1.10",
      },
    ],
    datasets: [
      {
        id: "hf://tatsu-lab/alpaca",
        label: "Alpaca Instruction Tuning",
        source: "Hugging Face (public)",
        examples: "52,002 instruction pairs",
      },
    ],
    primitives: [
      {
        label: "param_groups in optim_step",
        href: "/docs/training/custom-loops/",
      },
      { label: "SFT recipe", href: "/docs/training/recipes/sft-dpo/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import math
from grad import Grad, ModelSpec

client = Grad()
base = client.artifacts.get("Qwen/Qwen3-8B")
BASE_LR_A, RATIO, TOTAL = 5e-5, 16.0, 400

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 16, "alpha": 32}),
    compute="gpu",
) as trainer:
    for step, batch_msgs in enumerate(load_chat_batches("hf://tatsu-lab/alpaca", steps=TOTAL)):
        scale = 0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * step / TOTAL))
        lr_a = BASE_LR_A * scale
        datums = [base.to_datum(messages=m) for m in batch_msgs]
        fb = trainer.forward_backward(datums, loss={"kind": "cross_entropy"})
        opt = trainer.optim_step(
            param_groups=[{"match": "lora_A", "lr": lr_a}, {"match": "lora_B", "lr": lr_a * RATIO}],
            grad_clip=1.0,
        )
        print(f"step={step} loss={fb.result().loss:.4f} lr_B={lr_a * RATIO:.2e}"); opt.result()
    artifact = trainer.export(name="lora-plus-8b", merge_adapter=True)`,
    paperYaml: `slug: lora-plus
title: "LoRA+ Differential Learning Rates"
arxiv: "https://arxiv.org/abs/2402.12354"
category: peft
public_dataset: "hf://tatsu-lab/alpaca"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/lora-plus (arXiv:2402.12354)
Dataset   hf://tatsu-lab/alpaca (52,002 train · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=16) · param_groups 16x ratio
Loss      cross_entropy · AdamW lora_A=5e-5, lora_B=8e-4
Estimate  ~2.8M tokens · ~14 min · ~$1.10 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Convergence speed & accuracy",
        paperReported:
          "Up to 2x faster convergence & +1–2% accuracy on MNLI/FLAN-v2 at identical FLOPs",
        templateSetup: "Alpaca · Qwen/Qwen3-8B · lambda=16",
      },
    ],
    bibtex: `@inproceedings{hayou2024loraplus,
  title={LoRA+: Efficient Low Rank Adaptation of Large Models},
  author={Hayou, Soufiane and Ghosh, Nikhil and Yu, Bin},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "loreft",
    shortTitle: "LoReFT",
    title: "ReFT / LoReFT: Representation Finetuning for Language Models",
    authors: "Wu et al. (Stanford)",
    year: 2024,
    arxivId: "2404.03592",
    arxivUrl: "https://arxiv.org/abs/2404.03592",
    category: "PEFT, Merging & Safety",
    oneLiner:
      "Freeze 100% of model weights and learn tiny low-rank orthogonal interventions directly on residual-stream activations — matching LoRA with 15x–65x fewer parameters.",
    story:
      "Even LoRA modifies millions of parameters across dozens of projection matrices. Drawing on mechanistic interpretability, LoReFT freezes every single weight and intervenes directly on tiny rank-4 subspaces of intermediate hidden states — producing sub-2 MB adapters that rival or beat LoRA.",
    insight:
      "Apply Phi(h) = h + R^T(Wh + b - Rh) with orthonormal R across 5 middle layers at prefix/suffix token positions, leaving 100% of base weights frozen.",
    whyGrad:
      "adapter='loreft' is native to ModelSpec — grad handles orthonormal parameterization and runtime activation hooks automatically in 22 lines.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Zero pyvene hook boilerplate — configure layers, rank, and prefix/suffix positions in ModelSpec.",
    },
    walkthrough: [
      {
        title: "Configure LoReFT layers and rank in ModelSpec",
        explanation:
          "Target 5 middle layers with rank=4 and p7+s7 prefix/suffix positions.",
        gradCall:
          "ModelSpec(..., adapter='loreft', train_mode='loreft', params={...})",
      },
      {
        title: "Train with standard cross-entropy at high LR (4e-3)",
        explanation:
          "Small subspace vectors expect 10–20x higher LR than LoRA.",
        gradCall: "trainer.optim_step(lr=4e-3)",
      },
      {
        title: "Export sub-2 MB representation intervention artifact",
        explanation: "Hot-swaps cheaply onto a shared frozen base model.",
        gradCall: "trainer.export(name='loreft-commonsense-8b')",
      },
    ],
    gotchas: [
      "Use a much higher LR (1e-3 to 4e-3) than LoRA.",
      "Do not set merge_adapter=True — LoReFT acts on token-position activations rather than static weight deltas.",
    ],
    linesOfCode: 16,
    typicalBaselineLoc: "~900 LOC pyvene + HF Trainer intervention loop",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~2.9M tokens",
        duration: "~15 min",
        estCost: "~$1.15",
      },
    ],
    datasets: [
      {
        id: "hf://zwhe99/commonsense_170k",
        label: "Commonsense170K",
        source: "Hugging Face (public)",
        examples: "170,420 reasoning pairs",
      },
    ],
    primitives: [
      {
        label: "ModelSpec loreft adapter",
        href: "/docs/reference/primitives/",
      },
      { label: "Custom loops", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()
base = client.artifacts.get("Qwen/Qwen3-8B")

spec = ModelSpec(
    base="Qwen/Qwen3-8B",
    adapter="loreft",
    train_mode="loreft",
    params={"layers": [8, 12, 16, 20, 24], "rank": 4, "prefix_positions": 7, "suffix_positions": 7},
)

with client.trainers.create(spec, compute="gpu") as trainer:
    for step, batch in enumerate(load_chat_batches("hf://zwhe99/commonsense_170k", steps=500)):
        datums = [base.to_datum(messages=m) for m in batch]
        fb = trainer.forward_backward(datums, loss={"kind": "cross_entropy"})
        opt = trainer.optim_step(lr=4e-3, grad_clip=1.0)
        print(f"step={step} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="loreft-commonsense-8b")`,
    paperYaml: `slug: loreft
title: "LoReFT Representation Finetuning"
arxiv: "https://arxiv.org/abs/2404.03592"
category: peft
public_dataset: "hf://zwhe99/commonsense_170k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/loreft (arXiv:2404.03592)
Dataset   hf://zwhe99/commonsense_170k (170,420 train · public)
Model     Qwen/Qwen3-8B · adapter=loreft (5 layers, rank=4, 0.028% params)
Loss      cross_entropy · AdamW lr=4.0e-3
Estimate  ~2.9M tokens · ~15 min · ~$1.15 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Commonsense Reasoning",
        paperReported:
          "Beats LoRA and DoRA with 15x–65x fewer trainable parameters",
        templateSetup: "Qwen/Qwen3-8B · 5 layers · rank=4 · p7+s7",
      },
    ],
    bibtex: `@inproceedings{wu2024reft,
  title={ReFT: Representation Finetuning for Language Models},
  author={Wu, Zhengxuan and others},
  booktitle={NeurIPS},
  year={2024}
}`,
  },
  {
    slug: "ties-merging",
    shortTitle: "TIES-Merging",
    title: "TIES-Merging: Resolving Interference When Merging Models",
    authors: "Yadav et al. (UNC Chapel Hill)",
    year: 2023,
    arxivId: "2306.01708",
    arxivUrl: "https://arxiv.org/abs/2306.01708",
    category: "PEFT, Merging & Safety",
    oneLiner:
      "Merge multiple fine-tuned specialist checkpoints into one model with zero training GPUs by trimming noisy weight deltas and electing consensus signs.",
    story:
      "Naive parameter averaging across specialist checkpoints routinely drops 10–30 points because 80%+ of fine-tuning deltas are tiny noise and opposing signs cancel each other out. TIES-Merging trims small deltas, elects a consensus sign per parameter, and averages only agreeing values.",
    insight:
      "Extract task vectors tau_k = theta_k - theta_base, Trim to top density %, Elect Sign by largest total magnitude, and Disjoint-Merge matching signs — collapsing K specialists into 1 zero-overhead checkpoint.",
    whyGrad:
      "client.artifacts.merge(..., method='ties', density=d) runs the entire zero-GPU merge directly in artifact storage so you can sweep densities in seconds.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Single SDK call (client.artifacts.merge) with built-in lineage tracking and zero training GPUs.",
    },
    walkthrough: [
      {
        title: "Train or pin specialists sharing one base checkpoint",
        explanation:
          "Ensure all merged artifacts share the exact same base model and tokenizer.",
        gradCall: "artifacts=[math_id, code_id]",
      },
      {
        title: "Sweep TIES density with zero training GPUs",
        explanation:
          "Run client.artifacts.merge(method='ties', density=d) across 0.2, 0.4, 0.6.",
        gradCall: "client.artifacts.merge(..., method='ties', density=0.4)",
      },
      {
        title: "Deploy the winning multi-skill checkpoint",
        explanation: "Serve one merged artifact instead of K separate models.",
        gradCall:
          "client.endpoints.create(slug='math-code-merged', artifact=best.id)",
      },
    ],
    gotchas: [
      "All merged artifacts MUST share the exact same base model initialization.",
      "Density 0.2–0.5 is the sweet spot; >0.7 lets sign noise leak back in.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~700 LOC mergekit config + manual sharding",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (2 specialists)",
        estTokens: "0 train tokens (eval only)",
        duration: "~6 min",
        estCost: "~$0.45",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K + HumanEval Multi-Skill Eval",
        source: "Hugging Face (public)",
        examples: "1,319 math + 164 code eval probes",
      },
    ],
    primitives: [
      { label: "Artifact merging", href: "/docs/training/custom-loops/" },
      { label: "Artifacts & endpoints", href: "/docs/training/endpoints/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelInput

client = Grad()
base = client.artifacts.get("Qwen/Qwen3-8B")
math_id = "specialist-math@v1"
code_id = "specialist-code@v1"
math_probes, code_probes = load_eval_probes("hf://openai/gsm8k", "hf://bigcode/humanevalpack")

best_score, best_art = -1.0, None
for density in (0.2, 0.4, 0.6):
    merged = client.artifacts.merge(
        name=f"ties-math-code-d{int(density * 100)}",
        artifacts=[math_id, code_id],
        weights=[0.5, 0.5],
        method="ties",
        density=density,
    )
    m_acc = eval_math(merged, [ModelInput(tokens=base.tokenize(p)) for p in math_probes])
    c_acc = eval_code(merged, [ModelInput(tokens=base.tokenize(p)) for p in code_probes])
    joint = 0.5 * (m_acc + c_acc)
    print(f"density={density:.1f} math={m_acc:.3f} code={c_acc:.3f}")
    if joint > best_score:
        best_score, best_art = joint, merged

client.endpoints.create(slug="math-code-merged", artifact=best_art.id)`,
    paperYaml: `slug: ties-merging
title: "TIES-Merging Zero-GPU Weight Merge"
arxiv: "https://arxiv.org/abs/2306.01708"
category: peft
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: cpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/ties-merging (arXiv:2306.01708)
Dataset   hf://openai/gsm8k + hf://bigcode/humanevalpack (eval · public)
Model     Qwen/Qwen3-8B · 2 specialists -> TIES density sweep (0.2/0.4/0.6)
Merge     client.artifacts.merge(method="ties") · 0 training tokens
Estimate  0 train tokens · ~1.1M eval tokens (~$0.45) · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Multi-task merging gain",
        paperReported:
          "+4.4% to +11.2% average accuracy over Task Arithmetic and simple averaging",
        templateSetup: "Qwen/Qwen3-8B · math + code · TIES density sweep",
      },
    ],
    bibtex: `@inproceedings{yadav2023ties,
  title={TIES-Merging: Resolving Interference When Merging Models},
  author={Yadav, Prateek and others},
  booktitle={NeurIPS},
  year={2023}
}`,
  },
  {
    slug: "rmu",
    shortTitle: "RMU",
    title: "RMU: Representation Misdirection for Unlearning (WMDP)",
    authors: "Li et al. (CAIS)",
    year: 2024,
    arxivId: "2403.03218",
    arxivUrl: "https://arxiv.org/abs/2403.03218",
    category: "PEFT, Merging & Safety",
    oneLiner:
      "Erase hazardous dual-use capabilities by scrambling layer-7 hidden states on forget corpora toward a fixed random direction while anchoring retain activations.",
    story:
      "Naive gradient-ascent unlearning either collapses the model into gibberish or only hides surface tokens while leaving latent knowledge intact. RMU targets internal layer-7 activations directly: push forget-set representations into an uninformative random direction while keeping retain-set representations locked to the base model.",
    insight:
      "Minimize MSE(h_l(forget), c * u_rand) + alpha * MSE(h_l(retain), h_l_ref(retain)) at layer l=7 — scrubbing WMDP bio/cyber recall down to random chance while keeping MMLU within ~1%.",
    whyGrad:
      "ref.score_logprobs(return_layers=[7]) + forward_backward_custom(outputs=['layers'], return_layers=[7]) run exact activation-level unlearning in 36 lines with zero custom PyTorch hooks.",
    smoothness: {
      rating: "Clean",
      verdict:
        "return_layers=[7] in both Artifact.score_logprobs and Trainer.forward_backward_custom eliminates dual-model GPU hooks.",
    },
    walkthrough: [
      {
        title: "Cache frozen retain activations at layer 7",
        explanation:
          "Fetch retain-set layer-7 activations from the frozen base Artifact.",
        gradCall: "ref.score_logprobs(..., return_layers=[7])['layer_refs'][7]",
      },
      {
        title: "Compute forget misdirection + retain preservation MSE",
        explanation:
          "Drive forget activations toward c * u_rand while anchoring retain activations with alpha=1200.",
        gradCall:
          "trainer.forward_backward_custom(datums, outputs=['layers'], return_layers=[7], loss_fn=rmu_loss)",
      },
      {
        title: "Audit WMDP drop vs. MMLU retention",
        explanation:
          "Stop around 150 steps once WMDP nears chance (~25%) and MMLU stays flat.",
        gradCall:
          "trainer.export(name='rmu-wmdp-unlearned', merge_adapter=True)",
      },
    ],
    gotchas: [
      "Target early-to-mid layers (5–8 in a 32-layer model) — late layers fail to erase latent knowledge.",
      "Unlearning converges in ~150 steps; over-training erodes retain fluency even with large alpha.",
    ],
    linesOfCode: 36,
    typicalBaselineLoc: "~1,100 LOC dual-model hook trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~1.7M tokens",
        duration: "~9 min",
        estCost: "~$0.70",
      },
    ],
    datasets: [
      {
        id: "hf://cais/wmdp-corpora",
        label: "WMDP Bio/Cyber Forget + WikiText Retain",
        source: "Hugging Face (public)",
        examples: "Forget chunks + WikiText retain pairs",
      },
    ],
    primitives: [
      {
        label: "forward_backward_custom",
        href: "/docs/training/custom-loops/",
      },
      {
        label: "return_layers TensorRefs",
        href: "/docs/reference/primitives/",
      },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
from grad import Datum, Grad, ModelInput, ModelSpec

BASE_ID, LAYER, C_STEER, ALPHA = "Qwen/Qwen3-8B", 7, 6.5, 1200.0
client = Grad()
ref = client.artifacts.get(BASE_ID)
torch.manual_seed(42)
rand_target = None

with client.trainers.create(
    ModelSpec(base=BASE_ID, adapter="lora", train_mode="lora", params={"rank": 16}),
    compute="gpu",
) as trainer:
    for step, (forget_texts, retain_texts) in enumerate(load_wmdp_pairs("hf://cais/wmdp-corpora", steps=150)):
        f_toks = [ref.tokenize(t)[:512] for t in forget_texts]
        r_toks = [ref.tokenize(t)[:512] for t in retain_texts]
        l_refs = ref.score_logprobs(r_toks, return_layers=[LAYER])["layer_refs"][LAYER]
        ref_h = client.tensors.fetch_batch(l_refs)  # single batched RPC
        if rand_target is None:
            rand_target = F.normalize(torch.randn(ref_h[0].shape[-1]), dim=-1) * C_STEER

        datums = [Datum(ModelInput(tokens=t), role="forget") for t in f_toks] + [Datum(ModelInput(tokens=t), role="retain") for t in r_toks]

        def rmu_loss(ds, out):
            hs = out["layers"][LAYER]
            f_loss = torch.stack([F.mse_loss(h, rand_target.expand_as(h)) for h in hs[: len(f_toks)]]).mean()
            r_loss = torch.stack([F.mse_loss(h, rh) for h, rh in zip(hs[len(f_toks) :], ref_h)]).mean()
            return f_loss + ALPHA * r_loss

        fb = trainer.forward_backward_custom(datums, outputs=["layers"], return_layers=[LAYER], loss_fn=rmu_loss)
        opt = trainer.optim_step(lr=5e-5, grad_clip=1.0)
        print(f"step={step} rmu_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="rmu-wmdp-unlearned", merge_adapter=True)`,
    paperYaml: `slug: rmu
title: "RMU Representation Unlearning"
arxiv: "https://arxiv.org/abs/2403.03218"
category: peft
public_dataset: "hf://cais/wmdp-corpora"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/rmu (arXiv:2403.03218)
Dataset   hf://cais/wmdp-corpora (forget + WikiText retain · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=16) · target_layer=7
Loss      custom rmu_loss (forget MSE + 1200x retain MSE)
Estimate  ~1.7M tokens · ~9 min · ~$0.70 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "WMDP-Bio / Cyber vs. MMLU",
        paperReported:
          "Drops WMDP-Bio 63.7% -> 31.0% while keeping MMLU within ~1% of base",
        templateSetup: "Qwen/Qwen3-8B · layer=7 · c=6.5 · alpha=1200",
      },
    ],
    bibtex: `@inproceedings{li2024wmdp,
  title={The WMDP Benchmark: Measuring and Reducing Malicious Use With Unlearning},
  author={Li, Nathaniel and others},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "npo",
    shortTitle: "NPO",
    title: "NPO: Negative Preference Optimization for Unlearning",
    authors: "Zhang et al.",
    year: 2024,
    arxivId: "2404.05868",
    arxivUrl: "https://arxiv.org/abs/2404.05868",
    category: "PEFT, Merging & Safety",
    oneLiner:
      "Replace explosive gradient ascent with the negative-only branch of DPO so unlearning gradients automatically dampen once target facts are forgotten.",
    story:
      "Plain gradient ascent drives log-probabilities toward negative infinity even after a model has already forgotten a target fact — wrecking general language fluency within one epoch. NPO keeps only DPO's rejected branch so gradients self-dampen exponentially once a forget example drops below the reference policy.",
    insight:
      "Minimize -(2 / beta) * log sigmoid(-beta * sum(log pi - log pi_ref)) on forget examples alongside retain NLL and optional L2 weight_anchor to the original checkpoint.",
    whyGrad:
      "ref.score_logprobs() + 11-line NPO loss in forward_backward_custom + optim_step(weight_anchor=...) implement collapse-free unlearning in 35 lines.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Self-dampening NPO + retain NLL + weight_anchor compose cleanly in forward_backward_custom.",
    },
    walkthrough: [
      {
        title: "Score reference logprobs on forget and retain sets",
        explanation:
          "Fetch aligned reference logprobs from the frozen starting checkpoint.",
        gradCall: "ref.score_logprobs(seqs)['aligned_logprobs']",
      },
      {
        title: "Apply NPO on forget datums and NLL on retain datums",
        explanation:
          "Use role='forget' vs role='retain' inside a single combined batch.",
        gradCall:
          "trainer.forward_backward_custom(datums, outputs=['logprobs'], loss_fn=npo_loss)",
      },
      {
        title: "Anchor weights gently via weight_anchor",
        explanation:
          "Add L2-SP anchoring to BASE_ID in optim_step() to prevent fluency drift.",
        gradCall:
          "trainer.optim_step(lr=2e-5, weight_anchor={'artifact_id': BASE_ID, 'strength': 0.01})",
      },
    ],
    gotchas: [
      "Always pair forget batches 1:1 with retain batches to keep general utility flat.",
      "Mask prompt tokens cleanly so NPO forgets the answer rather than question syntax.",
    ],
    linesOfCode: 28,
    typicalBaselineLoc: "~950 LOC custom DPO/TOFU unlearning fork",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~2.8M tokens",
        duration: "~14 min",
        estCost: "~$1.10",
      },
    ],
    datasets: [
      {
        id: "hf://locuslab/TOFU",
        label: "TOFU Fictitious Unlearning (10% forget)",
        source: "Hugging Face (public)",
        examples: "400 forget / 3,600 retain QA",
      },
    ],
    primitives: [
      {
        label: "forward_backward_custom",
        href: "/docs/training/custom-loops/",
      },
      { label: "weight_anchor", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
import grad
from grad import Grad, ModelSpec

BASE_ID = "Qwen/Qwen3-8B"
client = Grad()
ref = client.artifacts.get(BASE_ID)

def npo_loss(datums, out, beta=0.1, retain_w=1.0):
    f_losses, r_losses = [], []
    for lp, rlp, m, d in zip(out["logprobs"], out["ref_logprobs"], out["masks"], datums):
        if d.role == "forget":
            f_losses.append(-(2.0 / beta) * F.logsigmoid(-beta * ((lp - rlp) * m).sum()))
        else:
            r_losses.append(-grad.masked_mean(lp, m))
    return torch.stack(f_losses).mean() + retain_w * torch.stack(r_losses).mean()

with client.trainers.create(
    ModelSpec(base=BASE_ID, adapter="lora", train_mode="lora", params={"rank": 16}),
    compute="gpu",
) as trainer:
    for step, (f_msgs, r_msgs) in enumerate(load_tofu_batches("hf://locuslab/TOFU", batch_size=16)):
        f_ds = [ref.to_datum(messages=m, role="forget") for m in f_msgs]
        for d, rlp in zip(f_ds, ref.score_logprobs([d.model_input.tokens for d in f_ds])["aligned_logprobs"]):
            d.targets.ref_logprobs = rlp
        r_ds = [ref.to_datum(messages=m, role="retain") for m in r_msgs]
        fb = trainer.forward_backward_custom(f_ds + r_ds, outputs=["logprobs"], loss_fn=npo_loss)
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0, weight_anchor={"artifact_id": BASE_ID, "strength": 0.01})
        print(f"step={step} npo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="npo-tofu-unlearned", merge_adapter=True)`,
    paperYaml: `slug: npo
title: "NPO: Negative Preference Optimization"
arxiv: "https://arxiv.org/abs/2404.05868"
category: peft
public_dataset: "hf://locuslab/TOFU"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/npo (arXiv:2404.05868)
Dataset   hf://locuslab/TOFU (400 forget / 3,600 retain · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=16) · weight_anchor=0.01
Loss      custom npo_loss (beta=0.10) + retain NLL
Estimate  ~2.8M tokens · ~14 min · ~$1.10 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "TOFU 10% Forget Quality vs. Utility",
        paperReported:
          "Avoids catastrophic collapse of Gradient Ascent while cutting forget accuracy sharply",
        templateSetup: "TOFU 10% forget · Qwen/Qwen3-8B · beta=0.1",
      },
    ],
    bibtex: `@article{zhang2024npo,
  title={Negative Preference Optimization: From Catastrophic Collapse to Effective Unlearning},
  author={Zhang, Ruiqi and others},
  journal={arXiv preprint arXiv:2404.05868},
  year={2024}
}`,
  },
];
