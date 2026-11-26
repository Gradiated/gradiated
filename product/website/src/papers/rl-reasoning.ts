import type { PaperGuide } from "./types";

export const rlReasoningPapers: PaperGuide[] = [
  {
    slug: "grpo",
    shortTitle: "GRPO",
    title: "DeepSeekMath / GRPO: Group Relative Policy Optimization",
    authors: "Shao et al.",
    year: 2024,
    arxivId: "2402.03300",
    arxivUrl: "https://arxiv.org/abs/2402.03300",
    category: "RL & Reasoning",
    oneLiner:
      "Drop the giant PPO value critic completely — sample a group of G completions per prompt and normalize rewards against the group mean and standard deviation.",
    story:
      "Classic PPO for LLMs forces you to train and hold a second full-size critic network in GPU memory just to estimate per-token baselines, doubling compute and destabilizing training whenever the critic lags behind the policy. DeepSeekMath showed that for verifiable tasks like math and code, you can throw the critic away and use the prompt's own rollout group as a free, zero-parameter baseline.",
    insight:
      "For each prompt, sample G completions, grade them, and set each trajectory's advantage to (r_i - mean(r)) / (std(r) + eps). Combine that group-normalized advantage with a clipped importance ratio and an unbiased k3 KL penalty against the frozen reference policy.",
    whyGrad:
      "Artifact.sample(n=8) returns 1:1 token-aligned trajectories with exact sampling_logprobs, Trajectory.to_datum() attaches advantages with zero off-by-one slicing, and loss='grpo' executes clipped policy gradients + KL regularization in one built-in call.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Maps 1:1 onto grad's core RL loop — zero custom loss code needed, and kl_sample_train is logged automatically every step.",
    },
    walkthrough: [
      {
        title: "Snapshot weights and sample G rollouts per prompt",
        explanation:
          "Freeze the current policy weights into an immutable snapshot and sample n=8 rollouts per question with exact token IDs and sampling_logprobs.",
        gradCall: "trainer.snapshot().sample(prompts, n=8)",
      },
      {
        title: "Compute reference logprobs for KL regularization",
        explanation:
          "Score the sampled trajectories under the frozen initial artifact so the policy stays anchored near its starting distribution.",
        gradCall: "ref.score_logprobs(flat_trajs)['aligned_logprobs']",
      },
      {
        title: "Center rewards per group and convert to aligned Datums",
        explanation:
          "Normalize each rollout's reward against its prompt group mean and standard deviation while automatically skipping zero-variance groups and aligning reference logprobs.",
        gradCall:
          "grad.group_datums(groups, rewards=rewards, norm='std', ref_logprobs=ref_lps)",
      },
      {
        title: "Pipeline forward-backward and optimizer update",
        explanation:
          "Queue both calls before awaiting .result() so forward, backward, and AdamW run back-to-back in a single RTT.",
        gradCall:
          "trainer.forward_backward(datums, loss={'kind': 'grpo', 'kl_beta': 0.04})",
      },
    ],
    gotchas: [
      "grad.group_datums(..., skip_zero_var=True) skips all-pass and all-fail groups by default so zero-advantage tokens never waste GPU compute.",
      "Keep kl_beta small (0.01–0.04) on verifiable math/code tasks; high KL weights choke exploration.",
      "Watch metrics['kl_sample_train'] on step 0 — any spike on an on-policy step indicates a prompt rendering mismatch.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~1,800 LOC distributed PPO/GRPO stack",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~5.5M tokens",
        duration: "~28 min",
        estCost: "~$2.20",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~4.4M tokens",
        duration: "~14 min",
        estCost: "~$1.10",
      },
      {
        id: "Qwen/Qwen3-32B",
        label: "Qwen/Qwen3-32B (LoRA rank 32)",
        estTokens: "~10.7M tokens",
        duration: "~55 min",
        estCost: "~$12.80",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
      {
        id: "hf://hendrycks/competition_math",
        label: "MATH Benchmark",
        source: "Hugging Face (public)",
        examples: "7,500 train / 5,000 test",
      },
    ],
    primitives: [
      { label: "Trainer", href: "/docs/training/custom-loops/" },
      { label: "GRPO guide", href: "/docs/training/recipes/rl-agents/" },
      { label: "Primitives reference", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import grad
from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = trainer.snapshot().sample(
            batch.prompt_inputs, n=8, temperature=0.9, max_new_tokens=1024, stop=["</answer>"],
        )
        ref_lps = ref.score_logprobs([t for g in groups for t in g])["aligned_logprobs"]
        rewards = [[grade_boxed_math(t.output["text"], gold) for t in g] for g, gold in zip(groups, batch.answers)]
        datums = grad.group_datums(groups, rewards=rewards, norm="std", ref_logprobs=ref_lps)

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2, "kl_beta": 0.04})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        m = fb.result(); opt.result()
        print(f"step={step} datums={len(datums)} kl_st={m.metrics['kl_sample_train']:.5f}")

    artifact = trainer.export(name="grpo-gsm8k", merge_adapter=True)`,
    paperYaml: `slug: grpo
title: "DeepSeekMath / GRPO"
arxiv: "https://arxiv.org/abs/2402.03300"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py
hyperparams:
  group_size: 8
  clip_low: 0.2
  clip_high: 0.2
  kl_beta: 0.04
  lr: 2.0e-5`,
    dryRunOutput: `Template  papers/grpo (arXiv:2402.03300)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · group_size=8
Loss      grpo (clip=0.20, kl_beta=0.04 vs frozen base)
Estimate  ~5.5M tokens · ~28 min (80 steps) · ~$2.20 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "MATH pass@1",
        paperReported:
          "DeepSeekMath-RL 7B climbs from 46.8% -> 51.7% without a value network",
        templateSetup:
          "GSM8K default run · Qwen/Qwen3-8B · group_size=8 · kl_beta=0.04",
      },
      {
        benchmark: "Memory footprint",
        paperReported: "~50% less GPU memory than critic-based PPO",
        templateSetup: "Single LoRA trainer + frozen base reference logprobs",
      },
    ],
    bibtex: `@article{shao2024deepseekmath,
  title={DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models},
  author={Shao, Zhihong and others},
  journal={arXiv preprint arXiv:2402.03300},
  year={2024}
}`,
  },
  {
    slug: "dapo",
    shortTitle: "DAPO",
    title: "DAPO: An Open-Source LLM RL System at Scale",
    authors: "Yu et al.",
    year: 2025,
    arxivId: "2503.14476",
    arxivUrl: "https://arxiv.org/abs/2503.14476",
    category: "RL & Reasoning",
    oneLiner:
      "Fix GRPO's entropy collapse and noisy gradients with asymmetric Clip-Higher (0.28), dynamic zero-variance filtering, and soft overlong reward shaping.",
    story:
      "When open-source teams tried reproducing DeepSeek-R1 with vanilla GRPO, runs routinely collapsed into repetitive, low-entropy answers after a few dozen steps — and long reasoning chains got crushed by equal-per-sequence averaging. DAPO dissected the failure modes into four surgical fixes that halved training steps to 50 points on AIME.",
    insight:
      "Raise the upper clipping bound (clip_high=0.28 while keeping clip_low=0.20) so low-probability exploratory reasoning tokens can actually grow; drop the KL penalty on verifiable math; filter out zero-variance prompt groups; and apply a smooth length penalty near max_new_tokens instead of a hard cliff.",
    whyGrad:
      "Asymmetric clip_low/clip_high and token-level loss normalization are built directly into loss='grpo', and empty zero-variance batches are safe no-ops — the entire paper fits in 34 lines.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Every DAPO ingredient (clip_high, token-level averaging, zero-var filtering) is first-class in grad with zero custom loss code.",
    },
    walkthrough: [
      {
        title: "Sample reasoning groups with generous token budget",
        explanation:
          "Sample n=8 long reasoning rollouts per prompt so the model has room to explore backtracking.",
        gradCall: "snap.sample(prompts, n=8, max_new_tokens=2048)",
      },
      {
        title: "Apply soft overlong penalty in the reward function",
        explanation:
          "Penalize completions approaching the max length smoothly instead of assigning abrupt cliff penalties.",
        gradCall: "reward = base_score - overlong_penalty(len(tokens))",
      },
      {
        title: "Dynamic sampling: skip zero-variance groups",
        explanation:
          "Drop groups where std(rewards) < 1e-6 so every gradient step carries real relative signal.",
        gradCall: "if sd < 1e-6: continue",
      },
      {
        title: "Update with asymmetric Clip-Higher and kl_beta=0",
        explanation:
          "Pass clip_low=0.2, clip_high=0.28 into built-in grpo and pipeline optim_step.",
        gradCall:
          "trainer.forward_backward(datums, loss={'kind': 'grpo', 'clip_low': 0.2, 'clip_high': 0.28})",
      },
    ],
    gotchas: [
      "Clip-Higher is sensitive to learning rate — keep lr around 1e-5 to 2e-5 when raising clip_high to 0.28.",
      "If >70% of groups get filtered by dynamic sampling, your task pool is too easy or too hard; add intermediate-difficulty problems.",
      "Dropping kl_beta=0.0 works great for verifiable math/code, but re-enable a tiny kl_beta (0.005) if style drift appears.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~2,400 LOC Ray + vLLM + FSDP",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~7.0M tokens",
        duration: "~35 min",
        estCost: "~$2.80",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~5.0M tokens",
        duration: "~16 min",
        estCost: "~$1.25",
      },
      {
        id: "Qwen/Qwen3-32B",
        label: "Qwen/Qwen3-32B (LoRA rank 32)",
        estTokens: "~12.7M tokens",
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
      { label: "GRPO / DAPO guide", href: "/docs/training/recipes/rl-agents/" },
      { label: "Rubric", href: "/docs/training/environments/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import grad
from grad import Grad, ModelSpec

client = Grad()

def overlong_penalty(n_toks: int, max_toks: int = 2048, cache_len: int = 512) -> float:
    if n_toks <= max_toks - cache_len:
        return 0.0
    return min(1.0, (n_toks - (max_toks - cache_len)) / cache_len)

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = trainer.snapshot().sample(batch.prompt_inputs, n=8, temperature=1.0, max_new_tokens=2048)
        rewards = [
            [grade_boxed_math(t.output["text"], gold) - overlong_penalty(len(t.output["response_tokens"])) for t in g]
            for g, gold in zip(groups, batch.answers)
        ]
        datums = grad.group_datums(groups, rewards=rewards, norm="std", skip_zero_var=True)

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
Estimate  ~7.0M tokens · ~35 min (100 steps) · ~$2.80 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "AIME 2024 pass@1",
        paperReported:
          "50 pts on Qwen2.5-32B in 50% fewer steps than vanilla GRPO",
        templateSetup:
          "GSM8K default smoke run (or DAPO-Math-17k) · Qwen/Qwen3-8B",
      },
      {
        benchmark: "Entropy stability",
        paperReported:
          "Eliminates premature entropy collapse via clip_high=0.28",
        templateSetup: "Monitored via metrics.kl_sample_train every step",
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
    slug: "dr-grpo",
    shortTitle: "Dr. GRPO",
    title: "Understanding R1-Zero-Like Training (Dr. GRPO)",
    authors: "Liu et al.",
    year: 2025,
    arxivId: "2503.20783",
    arxivUrl: "https://arxiv.org/abs/2503.20783",
    category: "RL & Reasoning",
    oneLiner:
      "Remove two hidden biases in GRPO — response-length normalization and std-division — so models stop bloating wrong answers to dilute negative gradients.",
    story:
      "Why do GRPO-trained reasoning models suddenly start rambling for 4,000 tokens whenever they're stuck on a problem? Dr. GRPO caught two subtle math bugs baked into GRPO: dividing loss by sequence length rewards longer *wrong* responses (each bad token gets smaller penalty), and dividing advantage by std(r) overweights trivial/impossible questions.",
    insight:
      "Use unnormalized group-centered advantages A_i = r_i - mean(r) (no / std(r)) and normalize the policy gradient by a constant max-length denominator instead of each response's own token length.",
    whyGrad:
      "Passing unnormalized (r - mean) into traj.to_datum() plus a 10-line constant-denominator loss in forward_backward_custom reproduces Dr. GRPO verbatim.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Removing std-division is a 1-character change, and constant-length normalization is 8 clean lines in forward_backward_custom.",
    },
    walkthrough: [
      {
        title: "Sample prompt groups as usual",
        explanation: "Generate G=8 rollouts per prompt from the live snapshot.",
        gradCall: "trainer.snapshot().sample(prompts, n=8)",
      },
      {
        title: "Use unbiased mean-only advantages (no / std)",
        explanation:
          "Subtract group mean without dividing by standard deviation so every prompt carries equal weight.",
        gradCall: "traj.to_datum(advantage=r - mean)",
      },
      {
        title: "Normalize by constant max_tokens instead of response length",
        explanation:
          "Divide the summed clipped objective by a fixed constant so wrong answers cannot game length.",
        gradCall:
          "trainer.forward_backward_custom(datums, outputs=['logprobs'], loss_fn=dr_grpo_loss)",
      },
    ],
    gotchas: [
      "Set const_norm close to your typical max_new_tokens (e.g. 1024) so the effective gradient scale matches standard LR ranges.",
      "Track mean response length on *incorrect* vs *correct* rollouts separately — Dr. GRPO keeps incorrect traces much shorter.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~1,500 LOC modified GRPO trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~4.7M tokens",
        duration: "~24 min",
        estCost: "~$1.90",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~3.8M tokens",
        duration: "~12 min",
        estCost: "~$0.95",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
      {
        id: "hf://hendrycks/competition_math",
        label: "MATH Benchmark",
        source: "Hugging Face (public)",
        examples: "7,500 train / 5,000 test",
      },
    ],
    primitives: [
      {
        label: "forward_backward_custom",
        href: "/docs/training/custom-loops/",
      },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
import grad
from grad import Grad, ModelSpec

client = Grad()

def dr_grpo_loss(datums, out, eps=0.2, const_norm=1024.0):
    losses = []
    for lp, old_lp, adv, mask in zip(out["logprobs"], out["sampling_logprobs"], out["advantages"], out["masks"]):
        r = torch.exp(lp - old_lp)
        pg = -torch.minimum(r * adv, r.clamp(1.0 - eps, 1.0 + eps) * adv)
        losses.append((pg * mask).sum() / const_norm)  # constant denominator kills length bias
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = trainer.snapshot().sample(batch.prompt_inputs, n=8, max_new_tokens=1024)
        rewards = [[grade_boxed_math(t.output["text"], gold) for t in g] for g, gold in zip(groups, batch.answers)]
        datums = grad.group_datums(groups, rewards=rewards, norm="mean")  # no / std(r) bias

        fb = trainer.forward_backward_custom(datums, outputs=["logprobs"], loss_fn=dr_grpo_loss)
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="dr-grpo-math", merge_adapter=True)`,
    paperYaml: `slug: dr-grpo
title: "Dr. GRPO: Unbiased R1-Zero RL"
arxiv: "https://arxiv.org/abs/2503.20783"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/dr-grpo (arXiv:2503.20783)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · group_size=8
Loss      custom dr_grpo_loss (unnormalized advantage, const_norm=1024)
Estimate  ~4.7M tokens · ~24 min · ~$1.90 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Token efficiency & AIME accuracy",
        paperReported:
          "+3–5 pts higher accuracy with significantly shorter incorrect traces vs. GRPO",
        templateSetup: "GSM8K / MATH · Qwen/Qwen3-8B · const_norm=1024",
      },
    ],
    bibtex: `@article{liu2025drgrpo,
  title={Understanding R1-Zero-Like Training: A Critical Perspective},
  author={Liu, Zichen and others},
  journal={arXiv preprint arXiv:2503.20783},
  year={2025}
}`,
  },
  {
    slug: "gspo",
    shortTitle: "GSPO",
    title: "GSPO: Group Sequence Policy Optimization",
    authors: "Zheng et al. (Qwen Team)",
    year: 2025,
    arxivId: "2507.18071",
    arxivUrl: "https://arxiv.org/abs/2507.18071",
    category: "RL & Reasoning",
    oneLiner:
      "Replace noisy per-token importance ratios with a sequence-level geometric mean ratio so MoE models and long multi-turn RL runs stop diverging.",
    story:
      "When training Mixture-of-Experts models (like Qwen3-MoE) with token-level GRPO, tiny router flips between sampling and training cause individual token importance ratios to explode, destabilizing entire runs. The Qwen team discovered that lifting importance sampling to the *sequence* level — matching the sequence-level reward — makes MoE RL rock solid.",
    insight:
      "Compute one length-normalized geometric-mean importance ratio per response: s_i = exp(mean_{t in generated} (log pi(y_t) - log pi_old(y_t))), then clip s_i with a tight range (e.g. eps=3e-4 to 4e-4 on sequence scale, or 0.2 with step clamping) and multiply by sequence advantage A_i.",
    whyGrad:
      "Because every Datum carries exact 1:1 loss_mask and sampling_logprobs, computing the masked sequence geometric mean ratio takes 9 lines inside trainer.forward_backward_custom() with bit-exact gradients.",
    smoothness: {
      rating: "Clean",
      verdict:
        "9-line custom loss via forward_backward_custom(); zero server changes needed, and works identically on multi-turn trajectories where env tokens are masked to 0.",
    },
    walkthrough: [
      {
        title: "Sample group rollouts",
        explanation:
          "Collect G=8 trajectories per prompt with exact sampling_logprobs.",
        gradCall: "trainer.snapshot().sample(prompts, n=8)",
      },
      {
        title: "Compute sequence-level geometric mean log-ratio",
        explanation:
          "Average (lp - old_lp) strictly over generated tokens where loss_mask == 1.0, then exponentiate.",
        gradCall:
          "seq_r = torch.exp(((lp - old_lp) * mask).sum() / mask.sum())",
      },
      {
        title: "Apply sequence-level clipping via forward_backward_custom",
        explanation:
          "Clip the sequence ratio s_i against sequence advantage and send exact surrogate gradients to the GPU.",
        gradCall:
          "trainer.forward_backward_custom(datums, outputs=['logprobs'], loss_fn=gspo_loss)",
      },
    ],
    gotchas: [
      "Sequence-level ratios have much tighter variance than token ratios — start with tighter clipping (eps=3e-4 to 1e-2) when training MoE models.",
      "Always mask index 0 and all tool/observation tokens (mask[0] = 0.0) before computing the geometric mean.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~1,600 LOC custom MoE RL engine",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-30B-A3B",
        label: "Qwen/Qwen3-30B-A3B MoE (recommended)",
        estTokens: "~3.8M tokens",
        duration: "~30 min",
        estCost: "~$4.60",
      },
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (dense smoke run)",
        estTokens: "~4.0M tokens",
        duration: "~20 min",
        estCost: "~$1.60",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
      {
        id: "hf://HuggingFaceH4/MATH-500",
        label: "MATH-500",
        source: "Hugging Face (public)",
        examples: "500 competition problems",
      },
    ],
    primitives: [
      {
        label: "forward_backward_custom",
        href: "/docs/training/custom-loops/",
      },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
import grad
from grad import Grad, ModelSpec

client = Grad()

def gspo_loss(datums, out, eps_low=3e-4, eps_high=4e-4):
    losses = []
    for lp, old_lp, adv, mask in zip(out["logprobs"], out["sampling_logprobs"], out["advantages"], out["masks"]):
        # Length-normalized sequence geometric mean ratio over generated tokens only
        s = torch.exp(grad.masked_mean(lp - old_lp, mask))
        a_seq = grad.masked_mean(adv, mask)
        losses.append(-torch.minimum(s * a_seq, s.clamp(1.0 - eps_low, 1.0 + eps_high) * a_seq))
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-30B-A3B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = trainer.snapshot().sample(batch.prompt_inputs, n=8, max_new_tokens=1024)
        rewards = [[grade_boxed_math(t.output["text"], gold) for t in g] for g, gold in zip(groups, batch.answers)]
        datums = grad.group_datums(groups, rewards=rewards, norm="std")
        fb = trainer.forward_backward_custom(datums, outputs=["logprobs"], loss_fn=gspo_loss)
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        print(f"step={step} gspo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="gspo-moe", merge_adapter=True)`,
    paperYaml: `slug: gspo
title: "GSPO: Group Sequence Policy Optimization"
arxiv: "https://arxiv.org/abs/2507.18071"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-30B-A3B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/gspo (arXiv:2507.18071)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-30B-A3B · adapter=lora (rank=32) · group_size=8
Loss      custom gspo_loss (sequence geometric mean ratio, eps=[3e-4, 4e-4])
Estimate  ~11.5M tokens · ~30 min · ~$4.60 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "MoE RL stability (Qwen3-MoE)",
        paperReported:
          "Eliminates MoE routing-replay hacks and outperforms GRPO on AIME/LiveCodeBench",
        templateSetup: "Qwen3-30B-A3B · sequence-level geometric mean clipping",
      },
    ],
    bibtex: `@article{zheng2025gspo,
  title={Group Sequence Policy Optimization},
  author={Zheng, Chujie and others},
  journal={arXiv preprint arXiv:2507.18071},
  year={2025}
}`,
  },
  {
    slug: "cispo",
    shortTitle: "CISPO",
    title:
      "MiniMax-M1 / CISPO: Clipped Importance Sampling Policy Optimization",
    authors: "MiniMax Team",
    year: 2025,
    arxivId: "2506.13585",
    arxivUrl: "https://arxiv.org/abs/2506.13585",
    category: "RL & Reasoning",
    oneLiner:
      "Clip the importance weight with stop-gradient instead of zeroing out the policy gradient — keeping rare 'Aha!' reflection tokens alive under async off-policy rollouts.",
    story:
      "PPO and GRPO clip the *objective* via min(r*A, clip(r)*A), which sets the gradient to exactly zero on any token whose ratio crosses the clip boundary. MiniMax-M1 noticed that low-probability reasoning pivot tokens ('Wait', 'However', 'Let me double check') get clipped out early and stop learning — especially when rollouts arrive asynchronously from older weight snapshots.",
    insight:
      "Apply stop_grad(clip(r, 1 - eps_lo, 1 + eps_hi)) as a scalar weight multiplying advantage * log_pi(y_t). Every token still contributes a bounded gradient, making async rollout pools 2x faster without losing reasoning diversity.",
    whyGrad:
      "CISPO is a built-in loss ('cispo') in grad — pair it with a 1-slot background ThreadPoolExecutor or AsyncGrad rollout worker to overlap slow tool/Docker rollouts with GPU training steps.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Built-in loss='cispo' + immutable trainer.snapshot() handles stale off-policy async rollouts natively.",
    },
    walkthrough: [
      {
        title: "Prefetch next batch's rollouts asynchronously",
        explanation:
          "Submit rollouts against the current snapshot on a background thread while the GPU trains on the previous batch.",
        gradCall: "pool.submit(snap.sample, next_prompts, n=8)",
      },
      {
        title: "Train on slightly stale trajectories with built-in CISPO",
        explanation:
          "Pass loss={'kind': 'cispo', 'clip_low': 0.2, 'clip_high': 0.28} — stop-grad importance weights stabilize off-policy lag.",
        gradCall: "trainer.forward_backward(datums, loss={'kind': 'cispo'})",
      },
      {
        title: "Refresh snapshot every step",
        explanation:
          "Each step publishes a cheap pointer snapshot so rollouts lag by at most 1 weight version.",
        gradCall: "trainer.snapshot()",
      },
    ],
    gotchas: [
      "Keep off-policy staleness <= 2–4 weight versions; check traj.output['weight_version'] vs trainer step if workers stall.",
      "CISPO works especially well with Docker Compose environments where rollouts take 10–30s and would otherwise idle the GPU.",
    ],
    linesOfCode: 28,
    typicalBaselineLoc: "~2,000 LOC async rollout broker + custom PPO",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~4.0M tokens",
        duration: "~20 min",
        estCost: "~$1.60",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~3.2M tokens",
        duration: "~10 min",
        estCost: "~$0.80",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
    ],
    primitives: [
      { label: "Built-in cispo loss", href: "/docs/training/custom-loops/" },
      { label: "Async RL guide", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from concurrent.futures import ThreadPoolExecutor
import grad
from grad import Grad, ModelSpec

client = Grad()
batches = list(load_math_batches("hf://openai/gsm8k", batch_size=32))

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer, ThreadPoolExecutor(max_workers=1) as pool:
    # Kick off batch 0 rollouts immediately; overlap all subsequent sampling with GPU steps
    pending = pool.submit(trainer.snapshot().sample, batches[0].prompt_inputs, 8, 1024)

    for step, batch in enumerate(batches):
        groups = pending.result()
        if step + 1 < len(batches):
            pending = pool.submit(trainer.snapshot().sample, batches[step + 1].prompt_inputs, 8, 1024)

        rewards = [[grade_boxed_math(t.output["text"], gold) for t in g] for g, gold in zip(groups, batch.answers)]
        datums = grad.group_datums(groups, rewards=rewards, norm="std")
        fb = trainer.forward_backward(datums, loss={"kind": "cispo", "clip_low": 0.2, "clip_high": 0.28})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        m = fb.result(); opt.result()
        print(f"step={step} cispo_loss={m.loss:.4f} kl_st={m.metrics['kl_sample_train']:.5f}")

    artifact = trainer.export(name="cispo-async", merge_adapter=True)`,
    paperYaml: `slug: cispo
title: "MiniMax-M1 / CISPO"
arxiv: "https://arxiv.org/abs/2506.13585"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/cispo (arXiv:2506.13585)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · async lag=1 step
Loss      cispo (stop-grad clipped importance sampling [0.80, 1.28])
Estimate  ~4.0M tokens · ~20 min · ~$1.60 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Training speedup & reasoning score",
        paperReported:
          "~2x faster convergence vs. DAPO/GRPO while preserving reflection tokens",
        templateSetup: "1-step overlapped async pool · Qwen/Qwen3-8B",
      },
    ],
    bibtex: `@article{minimax2025m1,
  title={MiniMax-M1: Scaling Test-Time Compute Efficiently with Lightning Attention},
  author={MiniMax Team},
  journal={arXiv preprint arXiv:2506.13585},
  year={2025}
}`,
  },
  {
    slug: "rloo",
    shortTitle: "RLOO",
    title: "Back to Basics: REINFORCE Leave-One-Out (RLOO)",
    authors: "Ahmadian et al. (Cohere)",
    year: 2024,
    arxivId: "2402.14740",
    arxivUrl: "https://arxiv.org/abs/2402.14740",
    category: "RL & Reasoning",
    oneLiner:
      "When group size is small (K=2 or K=4), use the unbiased leave-one-out baseline instead of noisy group standard deviation.",
    story:
      "In GRPO, subtracting the group mean that *includes* sample i shrinks the advantage by (K-1)/K, and dividing by a 4-sample standard deviation injects huge variance. Cohere showed that classic REINFORCE with a leave-one-out baseline beats PPO while needing only K=4 completions per prompt and zero critic network.",
    insight:
      "For each completion i in a K-sample group, compute its baseline from the *other* K-1 samples: b_i = (sum(r) - r_i) / (K - 1), giving an unbiased advantage A_i = r_i - b_i, paired with built-in importance_sampling loss.",
    whyGrad:
      "A single 2-line Python comprehension computes exact leave-one-out advantages and feeds straight into grad's built-in importance_sampling loss.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Built-in importance_sampling loss + 2-line LOO baseline makes RLOO the cleanest small-group RL baseline in grad.",
    },
    walkthrough: [
      {
        title: "Sample small groups (K=4)",
        explanation:
          "RLOO shines when rollouts are expensive and you can only afford 4 samples per prompt.",
        gradCall: "snap.sample(prompts, n=4)",
      },
      {
        title: "Compute unbiased leave-one-out baseline",
        explanation:
          "Exclude r_i from its own baseline so E[A_i] stays strictly unbiased.",
        gradCall: "adv = r - (total - r) / (K - 1)",
      },
      {
        title: "Step with built-in importance_sampling loss",
        explanation:
          "Apply clean importance-weighted policy gradients with optional KL anchor.",
        gradCall:
          "trainer.forward_backward(datums, loss={'kind': 'importance_sampling', 'kl_beta': 0.02})",
      },
    ],
    gotchas: [
      "RLOO requires K >= 2; K=4 is the sweet spot between sampling cost and baseline variance.",
      "Pair with a small kl_beta (0.01–0.05) when grading with a learned reward model to prevent reward hacking.",
    ],
    linesOfCode: 20,
    typicalBaselineLoc: "~900 LOC TRL RLOO trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~3.6M tokens",
        duration: "~18 min",
        estCost: "~$1.45",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~2.8M tokens",
        duration: "~9 min",
        estCost: "~$0.70",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
    ],
    primitives: [
      {
        label: "importance_sampling loss",
        href: "/docs/training/custom-loops/",
      },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import grad
from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = trainer.snapshot().sample(batch.prompt_inputs, n=4, max_new_tokens=1024)
        ref_lps = ref.score_logprobs([t for g in groups for t in g])["aligned_logprobs"]
        rewards = [[grade_boxed_math(t.output["text"], gold) for t in g] for g, gold in zip(groups, batch.answers)]
        # Unbiased leave-one-out baseline via norm="rloo"
        datums = grad.group_datums(groups, rewards=rewards, norm="rloo", ref_logprobs=ref_lps)

        fb = trainer.forward_backward(datums, loss={"kind": "importance_sampling", "kl_beta": 0.02})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="rloo-gsm8k", merge_adapter=True)`,
    paperYaml: `slug: rloo
title: "RLOO: REINFORCE Leave-One-Out"
arxiv: "https://arxiv.org/abs/2402.14740"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/rloo (arXiv:2402.14740)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · K=4 samples/prompt
Loss      importance_sampling (kl_beta=0.02, LOO baseline)
Estimate  ~3.6M tokens · ~18 min · ~$1.45 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Win rate vs. PPO",
        paperReported:
          "Matches or outperforms critic-based PPO at K=4 with half the memory",
        templateSetup: "GSM8K · Qwen/Qwen3-8B · K=4",
      },
    ],
    bibtex: `@inproceedings{ahmadian2024rloo,
  title={Back to Basics: Revisiting REINFORCE Style Optimization for Learning from Human Feedback in LLMs},
  author={Ahmadian, Arash and others},
  booktitle={ACL},
  year={2024}
}`,
  },
  {
    slug: "reinforce-plus-plus",
    shortTitle: "REINFORCE++",
    title: "REINFORCE++: A Simple and Efficient Approach for Aligning LLMs",
    authors: "Hu et al.",
    year: 2025,
    arxivId: "2501.03262",
    arxivUrl: "https://arxiv.org/abs/2501.03262",
    category: "RL & Reasoning",
    oneLiner:
      "Stabilize critic-free RL even at group_size=1 by shaping per-token KL rewards and whitening advantages globally across the whole batch.",
    story:
      "GRPO needs 8–16 rollouts per prompt to estimate a group baseline, which gets painfully expensive when each rollout requires running a long coding sandbox or multi-turn agent. REINFORCE++ shows you can drop down to 1 rollout per prompt by folding per-token KL directly into the reward stream and whitening advantages across the entire batch.",
    insight:
      "At every generated token t, subtract beta * (log pi(y_t) - log pi_ref(y_t)), add the terminal outcome reward on the final token, compute backward cumulative returns, whiten all active token advantages globally across the batch, and step with PPO-style clipping.",
    whyGrad:
      "traj.to_datum(advantages=per_token_adv) accepts dense per-token advantage arrays (same length T as tokens!) and feeds straight into built-in loss='grpo' with zero custom backward code.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Per-token advantages=[...] on to_datum() + built-in clipped grpo makes REINFORCE++ work cleanly with n=1 rollouts per prompt.",
    },
    walkthrough: [
      {
        title: "Sample 1 rollout per prompt",
        explanation:
          "Generate a single completion per prompt across a wide batch (e.g. 64 prompts).",
        gradCall: "snap.sample(prompts, n=1)",
      },
      {
        title: "Shape per-token KL rewards against the reference model",
        explanation:
          "Score reference logprobs and subtract beta * (lp - ref_lp) at every generated token.",
        gradCall: "ref.score_logprobs(trajs)['aligned_logprobs']",
      },
      {
        title: "Whiten token advantages globally across the batch",
        explanation:
          "Standardize all active token returns across the full batch and pass advantages=[...] to to_datum().",
        gradCall: "traj.to_datum(advantages=whitened_tok_advs)",
      },
    ],
    gotchas: [
      "Whiten ONLY over tokens where loss_mask == 1.0 — including prompt padding zeros skews the batch mean and variance.",
      "Because group_size=1, use a larger prompt batch size (64–128) so global whitening has low variance.",
    ],
    linesOfCode: 37,
    typicalBaselineLoc: "~1,200 LOC OpenRLHF REINFORCE++",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~3.2M tokens",
        duration: "~16 min",
        estCost: "~$1.30",
      },
      {
        id: "Qwen/Qwen3-4B",
        label: "Qwen/Qwen3-4B (fast smoke run)",
        estTokens: "~2.6M tokens",
        duration: "~8 min",
        estCost: "~$0.65",
      },
    ],
    datasets: [
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
    ],
    primitives: [
      { label: "Trajectory.to_datum", href: "/docs/reference/primitives/" },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=64)):
        trajs = [g[0] for g in trainer.snapshot().sample(batch.prompt_inputs, n=1, max_new_tokens=1024)]
        ref_lps = ref.score_logprobs(trajs)["aligned_logprobs"]

        raw_advs, all_active = [], []
        for traj, gold, rlp in zip(trajs, batch.answers, ref_lps):
            mask = traj.output["loss_mask"]
            lps = traj.output["sampling_logprobs"]
            score = grade_boxed_math(traj.output["text"], gold)
            # Token-level KL penalty + terminal reward, accumulated backward
            ret, running = [0.0] * len(lps), score
            for i in range(len(lps) - 1, -1, -1):
                if mask[i] > 0:
                    running -= 0.01 * (lps[i] - rlp[i])
                    ret[i] = running
                    all_active.append(running)
            raw_advs.append(ret)

        t_all = torch.tensor(all_active)
        mu, sd = t_all.mean().item(), t_all.std().clamp(min=1e-6).item()
        datums = [
            traj.to_datum(advantages=[(a - mu) / sd if m > 0 else 0.0 for a, m in zip(ret, traj.output["loss_mask"])])
            for traj, ret in zip(trajs, raw_advs)
        ]

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="reinforce-pp", merge_adapter=True)`,
    paperYaml: `slug: reinforce-plus-plus
title: "REINFORCE++"
arxiv: "https://arxiv.org/abs/2501.03262"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/reinforce-plus-plus (arXiv:2501.03262)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · n=1 rollout/prompt
Loss      grpo with per-token KL shaping + global batch whitening
Estimate  ~3.2M tokens · ~16 min · ~$1.30 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "Stability vs. GRPO at n=1",
        paperReported:
          "Matches PPO stability with ~30% faster training and no value critic",
        templateSetup: "GSM8K · batch_size=64 · n=1 · kl_beta=0.01",
      },
    ],
    bibtex: `@article{hu2025reinforcepp,
  title={REINFORCE++: A Simple and Efficient Approach for Aligning Large Language Models},
  author={Hu, Jian},
  journal={arXiv preprint arXiv:2501.03262},
  year={2025}
}`,
  },
  {
    slug: "vapo",
    shortTitle: "VAPO",
    title: "VAPO: Value-Augmented Policy Optimization for Long Reasoning",
    authors: "Yue et al. (ByteDance Seed)",
    year: 2025,
    arxivId: "2504.05118",
    arxivUrl: "https://arxiv.org/abs/2504.05118",
    category: "RL & Reasoning",
    oneLiner:
      "Bring back a decoupled token-level value critic with length-adaptive GAE and positive-example SFT anchoring to outperform critic-free RL on long reasoning chains.",
    story:
      "While GRPO and DAPO ditched the value network, ByteDance Seed asked a contrarian question: on 16k-token reasoning chains, doesn't a token-level critic give far sharper credit assignment than a single outcome scalar? VAPO showed value-based PPO beats GRPO when you pretrain the value head first, decouple its GAE lambda from the policy's, and anchor positive traces with a small NLL term.",
    insight:
      "Attach a token_level=True value head to the model, train policy + value jointly with decoupled lambda_policy (length-adaptive) vs lambda_critic=1.0, add an NLL imitation term on passing trajectories, and use differential learning rates via param_groups so the value head adapts faster than the policy.",
    whyGrad:
      "ModelSpec.heads={'v': {'dim': 1, 'token_level': True}} gives you a per-token critic on the same backbone, forward_backward_custom computes joint policy + value + positive-NLL loss, and optim_step(param_groups=...) sets a higher LR on the value head.",
    smoothness: {
      rating: "Custom head / loop",
      verdict:
        "Token-level value head + param_groups make joint actor-critic PPO clean in ~42 lines without spinning up a second server.",
    },
    walkthrough: [
      {
        title: "Attach a token-level value head",
        explanation:
          "Declare heads={'v': {'dim': 1, 'token_level': True}} in ModelSpec so forward() returns (T, 1) per-token value predictions.",
        gradCall:
          "ModelSpec(..., heads={'v': {'dim': 1, 'token_level': True}})",
      },
      {
        title: "Compute decoupled GAE + positive-NLL loss",
        explanation:
          "Train the value head against Monte Carlo returns (lambda=1.0), policy with GAE + clip-higher, and add 0.1 * NLL on correct rollouts.",
        gradCall:
          "trainer.forward_backward_custom(datums, outputs=['logprobs', 'heads'], loss_fn=vapo_loss)",
      },
      {
        title: "Give the value head a faster learning rate",
        explanation:
          "Pass param_groups to optim_step() so extra_heads.v converges rapidly during early steps.",
        gradCall:
          "trainer.optim_step(lr=1e-5, param_groups=[{'match': 'extra_heads.v', 'lr': 1e-4}])",
      },
    ],
    gotchas: [
      "Warm-start the value head for 20–50 steps (setting policy loss weight to 0) before updating the actor so initial value errors don't corrupt the policy.",
      "Always detach value predictions when computing policy advantages (adv = ret - v.detach()) so policy gradients don't push the critic around.",
    ],
    linesOfCode: 36,
    typicalBaselineLoc: "~3,000 LOC actor-critic RL cluster",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      {
        id: "Qwen/Qwen3-8B",
        label: "Qwen/Qwen3-8B (recommended)",
        estTokens: "~7.5M tokens",
        duration: "~38 min",
        estCost: "~$3.00",
      },
      {
        id: "Qwen/Qwen3-32B",
        label: "Qwen/Qwen3-32B (LoRA rank 32)",
        estTokens: "~13.7M tokens",
        duration: "~70 min",
        estCost: "~$16.40",
      },
    ],
    datasets: [
      {
        id: "hf://BytedTsinghua-SIA/DAPO-Math-17k",
        label: "DAPO-Math-17k",
        source: "Hugging Face (public)",
        examples: "17,000 competition math prompts",
      },
      {
        id: "hf://openai/gsm8k",
        label: "GSM8K Math",
        source: "Hugging Face (public)",
        examples: "7,473 train / 1,319 test",
      },
    ],
    primitives: [
      { label: "Token-level heads", href: "/docs/training/custom-loops/" },
      { label: "param_groups LR", href: "/docs/training/custom-loops/" },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
import grad
from grad import Grad, ModelSpec

client = Grad()

def vapo_loss(datums, out, eps_lo=0.2, eps_hi=0.28, vf_coef=0.5, nll_coef=0.1):
    losses = []
    for lp, old_lp, v, mask, d in zip(out["logprobs"], out["sampling_logprobs"], out["heads"]["v"], out["masks"], datums):
        reward = float(d.targets.scalar)
        v_pred = v[:, 0]
        # Decoupled GAE: critic learns against MC return; policy uses residual advantage
        ret = torch.full_like(v_pred, reward)
        adv = ret - v_pred.detach()
        r = torch.exp(lp - old_lp)
        pg = -torch.minimum(r * adv, r.clamp(1.0 - eps_lo, 1.0 + eps_hi) * adv)
        vf = 0.5 * (v_pred - ret) ** 2
        nll = (-lp if reward > 0.5 else torch.zeros_like(lp)) * nll_coef
        losses.append(grad.masked_mean(pg + vf_coef * vf + nll, mask))
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(
        base="Qwen/Qwen3-8B",
        adapter="lora",
        train_mode="lora",
        params={"rank": 32},
        heads={"v": {"dim": 1, "token_level": True}},
    ),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = trainer.snapshot().sample(batch.prompt_inputs, n=4, max_new_tokens=1536)
        datums = [
            traj.to_datum(scalar=grade_boxed_math(traj.output["text"], gold))
            for group, gold in zip(groups, batch.answers)
            for traj in group
        ]
        fb = trainer.forward_backward_custom(datums, outputs=["logprobs", "heads"], loss_fn=vapo_loss)
        opt = trainer.optim_step(lr=1e-5, param_groups=[{"match": "extra_heads.v", "lr": 1e-4}], grad_clip=1.0)
        print(f"step={step} vapo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="vapo-math", merge_adapter=True)`,
    paperYaml: `slug: vapo
title: "VAPO: Value-Augmented Policy Optimization"
arxiv: "https://arxiv.org/abs/2504.05118"
category: rl
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/vapo (arXiv:2504.05118)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora + token_level value head 'v'
Loss      custom vapo_loss (clip=[0.20,0.28], vf=0.5, pos_nll=0.1)
Estimate  ~7.5M tokens · ~38 min · ~$3.00 · warnings: 0`,
    benchmarks: [
      {
        benchmark: "AIME 2024 pass@1",
        paperReported: "60.4 on Qwen2.5-32B (+10 pts over DAPO on long CoT)",
        templateSetup: "GSM8K / DAPO-Math-17k · Qwen/Qwen3-8B · actor+critic",
      },
    ],
    bibtex: `@article{yue2025vapo,
  title={VAPO: Efficient and Reliable Reinforcement Learning for Advanced Reasoning Models},
  author={Yue, Yu and others},
  journal={arXiv preprint arXiv:2504.05118},
  year={2025}
}`,
  },
];
