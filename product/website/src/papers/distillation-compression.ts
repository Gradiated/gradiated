import type { PaperGuide } from "./types";

export const distillationCompressionPapers: PaperGuide[] = [
  {
    slug: "sdft",
    shortTitle: "SDFT",
    title: "Self-Distillation Fine-Tuning (SDFT)",
    authors: "Shenfeld et al.",
    year: 2026,
    arxivId: "2601.19897",
    arxivUrl: "https://arxiv.org/abs/2601.19897",
    category: "Distillation & Compression",
    oneLiner:
      "Learn new skills from demonstrations without catastrophic forgetting by using the same frozen base model conditioned on an in-context golden demo as teacher.",
    story:
      "Fine-tuning a model on a new domain with SFT almost always degrades its existing general skills — because offline cross-entropy forces the model onto somebody else's exact wording. SDFT solves continual learning with a disarmingly simple twist: let the base model teach itself on-policy using the golden answer as an in-context hint.",
    insight:
      "Sample completions on-policy from the student seeing only the question. Then ask the frozen base model (seeing question + golden demo) for its top-20 token logprobs on those exact student tokens, and minimize forward KL.",
    whyGrad:
      "Artifact.score_logprobs() accepts split (prefix_tokens, response_tokens) and Trajectory.to_datum() aligns response_offset automatically — collapsing ~1,100 lines of shifted-token slicing into 22 lines with zero separate teacher deployment.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Split prefix/response score_logprobs + built-in topk_kl_distill make SDFT absurdly clean — 22 lines total.",
    },
    walkthrough: [
      { title: "Pin the frozen base model as self-teacher", explanation: "Grab a read-only Artifact handle to the exact same base model — no second model deployment required.", gradCall: "teacher = client.artifacts.get(base_id)" },
      { title: "Sample on-policy from the student without the demo", explanation: "Generate completions seeing only the bare question so training stays strictly on-policy.", gradCall: "trainer.snapshot().sample(batch.question_inputs, n=1)" },
      { title: "Score student tokens under the demo-conditioned teacher", explanation: "Pass demo_prefix_tokens separately from response_tokens and request compact top_k=20 TensorRefs.", gradCall: "teacher.score_logprobs(prefix_tokens=demo_prefixes, response_tokens=resps, top_k=20)" },
      { title: "Step with built-in topk_kl_distill", explanation: "Attach each TensorRef via to_datum(teacher_topk=ref) and pipeline forward_backward + optim_step.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'topk_kl_distill'})" },
    ],
    gotchas: [
      "Keep the teacher frozen (or EMA-synced every 50 steps) — updating the teacher every step creates a moving target.",
      "Use top_k=20 to 32; capturing the top 20 tokens recovers >99% of full-vocabulary KL at <0.02% of the network payload.",
    ],
    linesOfCode: 22,
    typicalBaselineLoc: "~1,100 LOC distributed self-distillation stack",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~3.5M tokens", duration: "~18 min", estCost: "~$1.40" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", estTokens: "~2.8M tokens", duration: "~9 min", estCost: "~$0.70" },
      { id: "Qwen/Qwen3-32B", label: "Qwen/Qwen3-32B (LoRA rank 64)", estTokens: "~7.4M tokens", duration: "~38 min", estCost: "~$8.90" },
    ],
    datasets: [
      { id: "hf://sciknoweval/chemistry-demo", label: "SciKnowEval Chemistry", source: "Hugging Face (public)", examples: "1,200 demos + held-out eval" },
      { id: "hf://toolalpaca/eval", label: "ToolAlpaca Tool-Use", source: "Hugging Face (public)", examples: "2,400 tool demos" },
    ],
    primitives: [
      { label: "Artifact.score_logprobs", href: "/docs/training/recipes/distillation/" },
      { label: "topk_kl_distill", href: "/docs/reference/primitives/" },
      { label: "Trainer", href: "/docs/training/custom-loops/" },
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
entrypoint: train.py`,
    dryRunOutput: `Template  papers/sdft (arXiv:2601.19897)
Dataset   hf://sciknoweval/chemistry-demo (1,200 train / 200 eval · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=64) · shared base teacher
Loss      topk_kl_distill (top_k=20) · AdamW lr=2.0e-5
Estimate  ~3.5M tokens · ~18 min · ~$1.40 · warnings: 0`,
    benchmarks: [
      { benchmark: "Continual skill acquisition", paperReported: "Matches or exceeds SFT while preserving prior benchmark accuracy", templateSetup: "SciKnowEval Chemistry · LoRA rank 64 · top_k=20" },
    ],
    bibtex: `@article{shenfeld2026sdft,
  title={Self-Distillation Enables Continual Learning},
  author={Shenfeld, Idan and others},
  journal={arXiv preprint arXiv:2601.19897},
  year={2026}
}`,
  },
  {
    slug: "cartridges",
    shortTitle: "Cartridges",
    title: "Context Cartridges: Long-Context KV Compression via Self-Study",
    authors: "Eyuboglu et al. (Stanford / Hazy Research)",
    year: 2025,
    arxivId: "2506.06266",
    arxivUrl: "https://arxiv.org/abs/2506.06266",
    category: "Distillation & Compression",
    oneLiner:
      "Compress a 50k–100k token static corpus into 256 trainable KV-cache prefix tokens on a frozen base model and hot-swap cartridges per tenant.",
    story:
      "Prepending a 60k-token API manual or clinical dossier to every request burns massive KV-cache RAM and prefill compute on every single call. Cartridges showed you can train a tiny 256-token KV prefix offline via self-study distillation — shrinking KV memory 38x while leaving the base model 100% frozen.",
    insight:
      "Freeze all LLM weights and optimize only the prepended prefix_kv tensors (layers x 2 x num_tokens x d_head) using top-k KL distillation against the same model reading the full corpus in context.",
    whyGrad:
      "prefix_kv is a built-in adapter and recipe='cartridge' is a managed recipe — 14 lines of YAML train, evaluate against the full-context teacher, and export a deployable .grad Cartridge.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "First-class managed recipe='cartridge' + prefix_kv adapter — deployable on any Endpoint in one line.",
    },
    walkthrough: [
      { title: "Point context_ref at your static corpus", explanation: "Provide a document bundle or Hugging Face corpus plus representative QA prompts.", gradCall: "context_ref: hf://hazyresearch/cartridges-longhealth/corpus.md" },
      { title: "Train only the 256-token prefix_kv adapter", explanation: "Keep base weights frozen and train prefix KV tensors with a high LR (2e-2) using top_k=20 KL.", gradCall: "adapter: { kind: prefix_kv, num_tokens: 256 }" },
      { title: "Deploy and serve without the 60k prompt", explanation: "Export a tiny prefix_kv.safetensors .grad bundle and serve user queries directly.", gradCall: "grad deploy longhealth-cartridge@latest" },
    ],
    gotchas: [
      "Prefix KV parameters need ~100x higher learning rate (1e-2 to 2e-2) than LoRA adapters — using 1e-4 will barely move loss.",
      "Pick num_tokens=128–256 for 10k–30k token docs and 512–1024 for 100k+ token repositories.",
    ],
    linesOfCode: 14,
    typicalBaselineLoc: "~900 LOC custom attention & KV-cache hooks",
    mode: "Managed recipe",
    entrypoint: "recipe.yaml",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~2.8M tokens", duration: "~14 min", estCost: "~$1.10" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", estTokens: "~2.2M tokens", duration: "~7 min", estCost: "~$0.55" },
    ],
    datasets: [
      { id: "hf://hazyresearch/cartridges-longhealth", label: "LongHealth Clinical Corpus", source: "Hugging Face (public)", examples: "60k-token corpus + QA probes" },
      { id: "hf://nyu-mll/quality", label: "QuALITY Long-Context QA", source: "Hugging Face (public)", examples: "Long stories + QA" },
    ],
    primitives: [
      { label: "recipe='cartridge'", href: "/docs/training/recipes/distillation/" },
      { label: "prefix_kv adapter", href: "/docs/reference/primitives/" },
      { label: "Endpoint deploy", href: "/docs/training/endpoints/" },
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
title: "Context Cartridges (prefix_kv)"
arxiv: "https://arxiv.org/abs/2506.06266"
category: distillation
public_dataset: "hf://hazyresearch/cartridges-longhealth"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: recipe.yaml`,
    dryRunOutput: `Template  papers/cartridges (arXiv:2506.06266)
Dataset   hf://hazyresearch/cartridges-longhealth (corpus: 58,420 tokens · 640 QA prompts)
Model     Qwen/Qwen3-8B (frozen) + prefix_kv (256 virtual tokens -> 228x KV compression)
Loss      topk_kl_distill (top_k=20) · AdamW lr=2.0e-2
Estimate  ~2.8M tokens · ~14 min · ~$1.10 · warnings: 0`,
    benchmarks: [
      { benchmark: "KV memory & throughput", paperReported: "38.6x smaller KV memory & up to 26.4x higher throughput vs. in-context prompting", templateSetup: "256 virtual prefix tokens compressing ~58k-token corpus" },
    ],
    bibtex: `@article{eyuboglu2025cartridges,
  title={Cartridges: Lightweight and general-purpose long context representations via self-study},
  author={Eyuboglu, Sabri and others},
  journal={arXiv preprint arXiv:2506.06266},
  year={2025}
}`,
  },
  {
    slug: "gkd",
    shortTitle: "GKD",
    title: "On-Policy Distillation of Language Models (GKD)",
    authors: "Agarwal et al. (Google DeepMind)",
    year: 2024,
    arxivId: "2306.13649",
    arxivUrl: "https://arxiv.org/abs/2306.13649",
    category: "Distillation & Compression",
    oneLiner:
      "Fix exposure bias in model distillation by training the student on its own generated rollouts using generalized Jensen-Shannon divergence against a larger teacher.",
    story:
      "Classic distillation fine-tunes a small student on static completions generated by a big teacher — but at inference time, the student conditions on its *own* earlier tokens and immediately drifts off distribution. GKD fixes this by sampling rollouts from the student and minimizing generalized Jensen-Shannon divergence (JSD) against the teacher.",
    insight:
      "Mix student-generated rollouts with teacher scoring, and minimize JSD_beta(p_teacher || p_student) over top-K token distributions so the student balances mode-covering (forward KL) and mode-seeking (reverse KL).",
    whyGrad:
      "Managed recipe='distill' handles standard on-policy top-k KL out of the box, and swapping to GKD's exact JSD divergence takes 12 lines via gather_indices=t_refs so full 152k-vocab logits never cross the network.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "gather_indices keeps JSD network traffic to (T_resp, 32) tensors and auto-batch-fetches out['teacher_topk_logprobs'] in one RPC — zero inner-loop fetches.",
    },
    walkthrough: [
      { title: "Sample rollouts on-policy from the student", explanation: "Generate completions from trainer.snapshot() on unlabeled prompts.", gradCall: "trainer.snapshot().sample(prompts, n=1)" },
      { title: "Fetch teacher's top-32 logprob TensorRefs", explanation: "Ask the 32B teacher to score the student's exact sequences and return opaque top-k refs.", gradCall: "teacher.score_logprobs(prefixes, resps, top_k=32)['topk_refs']" },
      { title: "Optimize generalized JSD via gather_indices", explanation: "Pass gather_indices=t_refs so both out['topk_logprobs'] and batched out['teacher_topk_logprobs'] arrive aligned.", gradCall: "trainer.forward_backward_custom(datums, outputs=['topk_logprobs'], gather_indices=t_refs, loss_fn=jsd_loss)" },
    ],
    gotchas: [
      "Always pass gather_indices=t_refs for custom distillation — pulling raw logits on a 152k vocabulary is ~5,000x larger.",
      "Set beta=0.5 for symmetric JSD; push toward 0.1 for sharper mode-seeking generation on code/math.",
    ],
    linesOfCode: 28,
    typicalBaselineLoc: "~950 LOC TRL GKDTrainer + teacher server",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B student <- 32B teacher", estTokens: "~5.2M tokens", duration: "~16 min", estCost: "~$1.30" },
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B student <- 32B teacher", estTokens: "~4.7M tokens", duration: "~24 min", estCost: "~$1.90" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/no_robots", label: "No Robots Prompts", source: "Hugging Face (public)", examples: "9,500 diverse prompts" },
    ],
    primitives: [
      { label: "Distillation guide", href: "/docs/training/recipes/distillation/" },
      { label: "gather_indices", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
from grad import Grad, ModelSpec

client = Grad()
teacher = client.artifacts.get("Qwen/Qwen3-32B")

def jsd_loss(datums, out, beta=0.5):
    losses = []
    for slp, tlp in zip(out["topk_logprobs"], out["teacher_topk_logprobs"]):
        pt, ps = torch.softmax(tlp, dim=-1), torch.softmax(slp, dim=-1)
        m = beta * pt + (1.0 - beta) * ps
        kl_t = (pt * (torch.log(pt + 1e-9) - torch.log(m + 1e-9))).sum(-1)
        kl_s = (ps * (torch.log(ps + 1e-9) - torch.log(m + 1e-9))).sum(-1)
        losses.append((beta * kl_t + (1.0 - beta) * kl_s).mean())
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-4B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, prompts in enumerate(load_prompt_batches("hf://HuggingFaceH4/no_robots", batch_size=32)):
        rollouts = [g[0] for g in trainer.snapshot().sample(prompts, n=1, max_new_tokens=256)]
        t_refs = teacher.score_logprobs(
            [r.input["tokens"] for r in rollouts],
            [r.output["response_tokens"] for r in rollouts],
            top_k=32,
        )["topk_refs"]
        datums = [r.to_datum(teacher_topk=ref) for r, ref in zip(rollouts, t_refs)]
        fb = trainer.forward_backward_custom(datums, outputs=["topk_logprobs"], gather_indices=t_refs, loss_fn=jsd_loss)
        opt = trainer.optim_step(lr=1e-4, grad_clip=1.0)
        print(f"step={step} jsd={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="gkd-4b-from-32b", merge_adapter=True)`,
    paperYaml: `slug: gkd
title: "GKD: On-Policy Generalized Knowledge Distillation"
arxiv: "https://arxiv.org/abs/2306.13649"
category: distillation
public_dataset: "hf://HuggingFaceH4/no_robots"
base_default: "Qwen/Qwen3-4B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/gkd (arXiv:2306.13649)
Dataset   hf://HuggingFaceH4/no_robots (9,500 prompts · public)
Model     Qwen/Qwen3-4B student <- Qwen/Qwen3-32B teacher
Loss      custom jsd_loss (beta=0.5, top_k=32 gather_indices)
Estimate  ~3.2M tokens · ~16 min · ~$1.30 · warnings: 0`,
    benchmarks: [
      { benchmark: "Summarization & instruction following", paperReported: "Outperforms sequence-level KD & forward KL across T5/Gemma students", templateSetup: "No Robots prompts · 32B -> 4B · JSD beta=0.5" },
    ],
    bibtex: `@inproceedings{agarwal2024gkd,
  title={On-Policy Distillation of Language Models: Learning from Self-Generated Mistakes},
  author={Agarwal, Rishabh and others},
  booktitle={ICLR},
  year={2024}
}`,
  },
  {
    slug: "minillm",
    shortTitle: "MiniLLM",
    title: "MiniLLM: Knowledge Distillation with Reverse KL",
    authors: "Gu et al. (Microsoft Research)",
    year: 2024,
    arxivId: "2306.08543",
    arxivUrl: "https://arxiv.org/abs/2306.08543",
    category: "Distillation & Compression",
    oneLiner:
      "Stop small students from smearing probability mass over hallucinated tails — minimize reverse KL on-policy so the student locks onto the teacher's sharpest modes.",
    story:
      "A 4B student simply does not have enough capacity to match every mode of a 32B teacher's distribution. Standard forward KL punishes the student for missing *any* teacher mode, forcing it to spread thin probability everywhere and hallucinate. MiniLLM flips the KL direction to reverse KL so the student focuses cleanly on high-probability teacher responses.",
    insight:
      "Sample y ~ student(x), score exact token logprobs under the teacher, and minimize KL(pi_student || pi_teacher) using grad's built-in reverse_kl_distill objective (or policy-gradient advantage A_t = log p_teacher - log p_student).",
    whyGrad:
      "reverse_kl_distill is a built-in forward_backward loss in grad — 19 lines total, zero custom loss math.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Built-in reverse_kl_distill + teacher.score_logprobs(rollouts) turns MiniLLM into a 19-line loop.",
    },
    walkthrough: [
      { title: "Sample student completions on-policy", explanation: "Generate rollouts from the live student snapshot.", gradCall: "trainer.snapshot().sample(prompts, n=1)" },
      { title: "Score student sequences with the teacher", explanation: "Get 1:1 aligned teacher logprobs on every student token.", gradCall: "teacher.score_logprobs(rollouts)['aligned_logprobs']" },
      { title: "Step with built-in reverse_kl_distill", explanation: "Attach ref_logprobs=teacher_lp and call built-in reverse_kl_distill.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'reverse_kl_distill'})" },
    ],
    gotchas: [
      "Reverse KL can narrow diversity if run too long — pair with a 10% teacher-SFT anchor batch if creative variety matters.",
      "Always verify student and teacher share the same tokenizer (e.g. Qwen3-4B and Qwen3-32B) before token-level distillation.",
    ],
    linesOfCode: 19,
    typicalBaselineLoc: "~1,300 LOC policy-gradient reverse-KL trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B <- Qwen/Qwen3-32B", estTokens: "~4.4M tokens", duration: "~14 min", estCost: "~$1.10" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/no_robots", label: "No Robots Prompts", source: "Hugging Face (public)", examples: "9,500 prompts" },
    ],
    primitives: [
      { label: "reverse_kl_distill", href: "/docs/reference/primitives/" },
      { label: "Distillation guide", href: "/docs/training/recipes/distillation/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()
teacher = client.artifacts.get("Qwen/Qwen3-32B")

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-4B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, prompts in enumerate(load_prompt_batches("hf://HuggingFaceH4/no_robots", batch_size=32)):
        rollouts = [g[0] for g in trainer.snapshot().sample(prompts, n=1, max_new_tokens=256)]
        t_lps = teacher.score_logprobs(rollouts)["aligned_logprobs"]
        datums = [r.to_datum(ref_logprobs=tlp) for r, tlp in zip(rollouts, t_lps)]

        fb = trainer.forward_backward(datums, loss={"kind": "reverse_kl_distill"})
        opt = trainer.optim_step(lr=5e-5, grad_clip=1.0)
        print(f"step={step} rkl_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="minillm-4b", merge_adapter=True)`,
    paperYaml: `slug: minillm
title: "MiniLLM: Reverse-KL Distillation"
arxiv: "https://arxiv.org/abs/2306.08543"
category: distillation
public_dataset: "hf://HuggingFaceH4/no_robots"
base_default: "Qwen/Qwen3-4B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/minillm (arXiv:2306.08543)
Dataset   hf://HuggingFaceH4/no_robots (9,500 prompts · public)
Model     Qwen/Qwen3-4B <- Qwen/Qwen3-32B
Loss      reverse_kl_distill (built-in)
Estimate  ~2.8M tokens · ~14 min · ~$1.10 · warnings: 0`,
    benchmarks: [
      { benchmark: "Hallucination & Rouge-L", paperReported: "Consistently beats forward KD on GPT-2/OPT/LLaMA students with lower exposure bias", templateSetup: "No Robots · 32B -> 4B · reverse_kl_distill" },
    ],
    bibtex: `@inproceedings{gu2024minillm,
  title={MiniLLM: Knowledge Distillation of Large Language Models},
  author={Gu, Yuxian and others},
  booktitle={ICLR},
  year={2024}
}`,
  },
  {
    slug: "distillm",
    shortTitle: "DistiLLM",
    title: "DistiLLM: Skew-KL Distillation with Adaptive Off-Policy Replay",
    authors: "Ko et al.",
    year: 2024,
    arxivId: "2402.03898",
    arxivUrl: "https://arxiv.org/abs/2402.03898",
    category: "Distillation & Compression",
    oneLiner:
      "Cut on-policy distillation wall-clock time 3x with a skew-KL mixture objective and an adaptive replay buffer that skips redundant student sampling.",
    story:
      "Pure on-policy distillation (GKD / MiniLLM) is slow because generating fresh rollouts every single step dominates GPU wall-clock time, while pure reverse KL suffers noisy gradients when student probabilities are tiny. DistiLLM introduces Skew KL (smooth gradients everywhere) plus a replay buffer that reuses fresh rollouts whenever validation loss is still falling.",
    insight:
      "Minimize D_KL(p_t || alpha * p_t + (1 - alpha) * p_s) over top-K tokens (guaranteed bounded gradients even when p_s -> 0) and recycle buffered rollouts on alternating steps.",
    whyGrad:
      "Skew KL over top-32 tokens is 7 lines in forward_backward_custom(gather_indices=t_refs), and a plain Python deque handles the adaptive replay buffer.",
    smoothness: {
      rating: "Clean",
      verdict:
        "7-line skew-KL objective + standard Python replay deque; zero custom serving infrastructure needed.",
    },
    walkthrough: [
      { title: "Maintain a rolling replay buffer of student rollouts", explanation: "Generate fresh rollouts every other step and sample from the deque on alternating steps to cut sampling overhead in half.", gradCall: "buf.extend(datums)" },
      { title: "Score top-32 teacher logprobs once per rollout", explanation: "Cache teacher TensorRefs alongside each buffered datum so replayed steps cost zero teacher calls.", gradCall: "teacher.score_logprobs(prefixes, resps, top_k=32)" },
      { title: "Optimize Skew Forward KL with gather_indices", explanation: "Mix alpha * pt + (1 - alpha) * ps in the denominator for bounded, low-variance gradients.", gradCall: "trainer.forward_backward_custom(batch, outputs=['topk_logprobs'], gather_indices=refs, loss_fn=skew_kl)" },
    ],
    gotchas: [
      "Keep buffer size small (2–4 batches) so replayed rollouts stay close to the current student policy.",
      "alpha=0.1 gives the best trade-off between reverse-KL sharpness and forward-KL stability.",
    ],
    linesOfCode: 28,
    typicalBaselineLoc: "~1,100 LOC custom DistiLLM framework",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B <- Qwen/Qwen3-32B", estTokens: "~3.2M tokens", duration: "~10 min", estCost: "~$0.80" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/no_robots", label: "No Robots Prompts", source: "Hugging Face (public)", examples: "9,500 prompts" },
    ],
    primitives: [
      { label: "gather_indices", href: "/docs/training/custom-loops/" },
      { label: "Distillation guide", href: "/docs/training/recipes/distillation/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from collections import deque
import torch
from grad import Grad, ModelSpec

client = Grad()
teacher = client.artifacts.get("Qwen/Qwen3-32B")

def skew_kl_loss(datums, out, alpha=0.1):
    losses = []
    for slp, tlp in zip(out["topk_logprobs"], out["teacher_topk_logprobs"]):
        pt, ps = torch.softmax(tlp, dim=-1), torch.softmax(slp, dim=-1)
        mix = alpha * pt + (1.0 - alpha) * ps
        losses.append((pt * (torch.log(pt + 1e-9) - torch.log(mix + 1e-9))).sum(-1).mean())
    return torch.stack(losses).mean()

buf = deque(maxlen=128)
with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-4B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, prompts in enumerate(load_prompt_batches("hf://HuggingFaceH4/no_robots", batch_size=32)):
        if step % 2 == 0 or not buf:  # adaptive replay skips half of sampling calls
            rollouts = [g[0] for g in trainer.snapshot().sample(prompts, n=1, max_new_tokens=256)]
            t_refs = teacher.score_logprobs([r.input["tokens"] for r in rollouts], [r.output["response_tokens"] for r in rollouts], top_k=32)["topk_refs"]
            buf.extend([r.to_datum(teacher_topk=ref) for r, ref in zip(rollouts, t_refs)])
        batch = list(buf)[-32:]
        refs = [d.targets.teacher_topk for d in batch]
        fb = trainer.forward_backward_custom(batch, outputs=["topk_logprobs"], gather_indices=refs, loss_fn=skew_kl_loss)
        opt = trainer.optim_step(lr=1e-4, grad_clip=1.0)
        print(f"step={step} skew_kl={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="distillm-4b", merge_adapter=True)`,
    paperYaml: `slug: distillm
title: "DistiLLM: Skew-KL + Replay Distillation"
arxiv: "https://arxiv.org/abs/2402.03898"
category: distillation
public_dataset: "hf://HuggingFaceH4/no_robots"
base_default: "Qwen/Qwen3-4B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/distillm (arXiv:2402.03898)
Dataset   hf://HuggingFaceH4/no_robots (9,500 prompts · public)
Model     Qwen/Qwen3-4B <- Qwen/Qwen3-32B (2x replay reuse)
Loss      custom skew_kl_loss (alpha=0.1, top_k=32)
Estimate  ~2.0M tokens · ~10 min · ~$0.80 · warnings: 0`,
    benchmarks: [
      { benchmark: "Speed & quality vs. MiniLLM", paperReported: "Up to 4.3x faster training than on-policy reverse KL with higher Rouge-L", templateSetup: "No Robots · 32B -> 4B · skew alpha=0.1" },
    ],
    bibtex: `@inproceedings{ko2024distillm,
  title={DistiLLM: Towards Streamlined Distillation for Large Language Models},
  author={Ko, Jongwoo and others},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "llmlingua-2",
    shortTitle: "LLMLingua-2",
    title: "LLMLingua-2: Data Distillation for Efficient Prompt Compression",
    authors: "Pan et al. (Microsoft Research)",
    year: 2024,
    arxivId: "2403.12968",
    arxivUrl: "https://arxiv.org/abs/2403.12968",
    category: "Distillation & Compression",
    oneLiner:
      "Train a fast token-level keep/drop classifier on encoder representations that compresses prompts 2–5x before sending them to an expensive frontier LLM.",
    story:
      "Autoregressive perplexity-based prompt compressors are slow and can only look left-to-right, dropping critical context that appears later in the sentence. LLMLingua-2 reframes prompt compression as bidirectional token classification trained on GPT-4 distilled keep/drop labels — running 3–6x faster on CPU/small GPUs.",
    insight:
      "Attach a token_level=True binary head ('keep') to a fast encoder (e.g. XLM-RoBERTa / BGE), train with built-in bce_sparse_positions over per-token keep/drop labels, and at inference time drop tokens below threshold tau.",
    whyGrad:
      "token_level=True heads + built-in loss='bce_sparse_positions' + Artifact.infer() returning full (L, 1) per-token logits make training AND serving a prompt compressor 23 lines.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Built-in token_level head + bce_sparse_positions covers training and serving identically with zero custom loss.",
    },
    walkthrough: [
      { title: "Attach a token_level binary head to an encoder", explanation: "Set heads={'keep': {'dim': 1, 'token_level': True}} on a compact bidirectional encoder.", gradCall: "ModelSpec(base='FacebookAI/xlm-roberta-base', heads={'keep': {'dim': 1, 'token_level': True}})" },
      { title: "Train with built-in bce_sparse_positions", explanation: "Pass per-token positions and 0/1 keep labels directly in DatumTargets.", gradCall: "trainer.forward_backward(batch, loss={'kind': 'bce_sparse_positions', 'head': 'keep'})" },
      { title: "Compress prompts in milliseconds via Artifact.infer()", explanation: "Score all tokens in one forward pass and drop tokens whose sigmoid keep-probability falls below threshold.", gradCall: "compressor.infer({'tokens': toks})['heads']['keep']" },
    ],
    gotchas: [
      "Protect special tokens, JSON keys, and code identifiers from dropping by forcing keep=1.0 on structural punctuation.",
      "Tune threshold tau per workload (0.35 for aggressive 4x RAG compression, 0.55 for lossless 2x compression).",
    ],
    linesOfCode: 23,
    typicalBaselineLoc: "~750 LOC token-classification + chunking pipeline",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "FacebookAI/xlm-roberta-base", label: "XLM-RoBERTa Base (recommended, fast)", estTokens: "~1.6M tokens", duration: "~6 min", estCost: "~$0.40" },
      { id: "BAAI/bge-small-en-v1.5", label: "BGE-Small-EN (ultra-fast CPU serving)", estTokens: "~800K tokens", duration: "~3 min", estCost: "~$0.20" },
    ],
    datasets: [
      { id: "hf://microsoft/MeetingBank-LLMCompressed", label: "MeetingBank LLM-Compressed", source: "Hugging Face (public)", examples: "Distilled token-level keep/drop labels" },
    ],
    primitives: [
      { label: "bce_sparse_positions", href: "/docs/reference/primitives/" },
      { label: "Token-level heads", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
from grad import Datum, DatumTargets, Grad, ModelInput, ModelSpec

client = Grad()

with client.trainers.create(
    ModelSpec(
        base="FacebookAI/xlm-roberta-base",
        adapter="full",
        train_mode="full",
        heads={"keep": {"dim": 1, "token_level": True}},
    ),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_compression_batches("hf://microsoft/MeetingBank-LLMCompressed", batch_size=32)):
        fb = trainer.forward_backward(batch, loss={"kind": "bce_sparse_positions", "head": "keep"})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} bce={fb.result().loss:.4f}"); opt.result()
    compressor = trainer.export(name="prompt-compressor")

# Compress any prompt in one forward pass
toks = compressor.tokenize(long_context)
keep_probs = torch.sigmoid(compressor.infer({"tokens": toks})["heads"]["keep"][:, 0])
compressed_toks = [t for t, p in zip(toks, keep_probs) if p.item() >= 0.45]`,
    paperYaml: `slug: llmlingua-2
title: "LLMLingua-2: Prompt Compression"
arxiv: "https://arxiv.org/abs/2403.12968"
category: distillation
public_dataset: "hf://microsoft/MeetingBank-LLMCompressed"
base_default: "FacebookAI/xlm-roberta-base"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/llmlingua-2 (arXiv:2403.12968)
Dataset   hf://microsoft/MeetingBank-LLMCompressed (public token-keep labels)
Model     FacebookAI/xlm-roberta-base + token_level head 'keep'
Loss      bce_sparse_positions (built-in)
Estimate  ~1.0M tokens · ~6 min · ~$0.40 · warnings: 0`,
    benchmarks: [
      { benchmark: "Compression ratio & latency", paperReported: "2x–5x prompt compression at 3–6x lower latency than perplexity compressors", templateSetup: "MeetingBank-LLMCompressed · XLM-RoBERTa · keep threshold 0.45" },
    ],
    bibtex: `@inproceedings{pan2024llmlingua2,
  title={LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression},
  author={Pan, Zhuoshi and others},
  booktitle={ACL Findings},
  year={2024}
}`,
  },
];
