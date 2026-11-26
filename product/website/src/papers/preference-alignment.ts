import type { PaperGuide } from "./types";

export const preferenceAlignmentPapers: PaperGuide[] = [
  {
    slug: "dpo",
    shortTitle: "DPO",
    title: "Direct Preference Optimization (DPO)",
    authors: "Rafailov et al.",
    year: 2023,
    arxivId: "2305.18290",
    arxivUrl: "https://arxiv.org/abs/2305.18290",
    category: "Preference Alignment",
    oneLiner:
      "Turn RLHF into a single supervised binary cross-entropy pass over (chosen, rejected) pairs — no reward model and no RL sampling loop.",
    story:
      "Before DPO, aligning a model to human preferences meant training a separate reward model and wrestling with a fragile 4-model PPO cluster. Rafailov et al. proved that the KL-constrained RLHF objective has a closed-form optimal policy, letting you optimize preferences directly with log-probability ratios.",
    insight:
      "Define the implicit reward r(x, y) = beta * (log pi(y|x) - log pi_ref(y|x)) and minimize -log sigmoid(r(x, y_w) - r(x, y_l)) over paired trajectories sharing a group_id.",
    whyGrad:
      "DPO is both a first-class managed recipe (recipe='dpo') and a built-in Trainer loss — 11 lines of YAML handle pair-atomic splitting, reference logprobs, and LoRA merging.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Zero training-loop code required via managed recipe='dpo', and group_id keeps chosen/rejected pairs atomic across splits.",
    },
    walkthrough: [
      { title: "Store preference pairs with shared group_id", explanation: "Tag each pair with the same group_id and role='chosen' or role='rejected'.", gradCall: "group_id='pair_19', role='chosen' | 'rejected'" },
      { title: "Warm-start from an SFT checkpoint (optional)", explanation: "Pass init_from to inherit the SFT weights as both starting policy and frozen reference.", gradCall: "init_from: assistant@sft-v1" },
      { title: "Launch managed DPO run", explanation: "Set loss.beta (0.05–0.2) and let grad handle reference scoring, splitting, and held-out reward-accuracy eval.", gradCall: "grad run papers/dpo --wait" },
    ],
    gotchas: [
      "Keep DPO learning rates 5–10x lower than SFT (1e-5 to 5e-5 for LoRA) or the policy will quickly overfit and emit repetitive text.",
      "Always inspect held-out chosen/rejected margin in eval_report — if both logprobs drop together while margin rises, lower lr or increase beta.",
    ],
    linesOfCode: 11,
    typicalBaselineLoc: "~500 LOC TRL DPOTrainer + ref model wrapper",
    mode: "Managed recipe",
    entrypoint: "recipe.yaml",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~12 min", estCost: "~$0.95" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", compute: "1x H100", duration: "~6 min", estCost: "~$0.48" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/ultrafeedback_binarized", label: "UltraFeedback Binarized", source: "Hugging Face (public)", examples: "61,135 preference pairs" },
    ],
    primitives: [
      { label: "recipe='dpo'", href: "/docs/training/recipes/sft-dpo/" },
      { label: "Trajectories & group_id", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "recipe.yaml",
    codeLanguage: "yaml",
    code: `# Run with: grad run papers/dpo --wait
dataset: hf://HuggingFaceH4/ultrafeedback_binarized
name: ultrafeedback-dpo
recipe: dpo
base: Qwen/Qwen3-8B
adapter: { kind: lora, rank: 32 }
compute: gpu
loss: { kind: dpo, beta: 0.1 }
optimizer: { kind: adamw, lr: 5.0e-5 }
split: { strategy: by_group, eval_fraction: 0.05 }
merge_adapter: true`,
    paperYaml: `slug: dpo
title: "Direct Preference Optimization (DPO)"
arxiv: "https://arxiv.org/abs/2305.18290"
category: preference
public_dataset: "hf://HuggingFaceH4/ultrafeedback_binarized"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: recipe.yaml`,
    dryRunOutput: `Template  papers/dpo (arXiv:2305.18290)
Dataset   hf://HuggingFaceH4/ultrafeedback_binarized (58,078 train / 3,057 eval pairs)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · merge_adapter=true
Loss      dpo (beta=0.10) · AdamW lr=5.0e-5
Estimate  1x H100 · ~12 min · ~$0.95 · warnings: 0`,
    benchmarks: [
      { benchmark: "MT-Bench / AlpacaEval", paperReported: "Matches or exceeds PPO-based RLHF with far higher stability", templateSetup: "UltraFeedback Binarized · Qwen/Qwen3-8B · beta=0.1" },
    ],
    bibtex: `@inproceedings{rafailov2023dpo,
  title={Direct Preference Optimization: Your Language Model is Secretly a Reward Model},
  author={Rafailov, Rafael and others},
  booktitle={NeurIPS},
  year={2023}
}`,
  },
  {
    slug: "simpo",
    shortTitle: "SimPO",
    title: "SimPO: Simple Preference Optimization with a Reference-Free Reward",
    authors: "Meng et al.",
    year: 2024,
    arxivId: "2405.14734",
    arxivUrl: "https://arxiv.org/abs/2405.14734",
    category: "Preference Alignment",
    oneLiner:
      "Eliminate the frozen reference model altogether by using length-normalized average log-probability plus a target margin gamma.",
    story:
      "DPO still needs a frozen reference model to score every pair (doubling forward passes), and its summed log-probability reward favors verbose responses over concise ones. SimPO noticed that average per-token log-probability aligns directly with beam/length-normalized decoding and needs no reference model at all.",
    insight:
      "Replace DPO's reference log-ratio with r_SimPO(x, y) = (beta / |y|) * sum log pi(y_t | x, y_<t) and enforce a margin gamma: -log sigmoid(r(y_w) - r(y_l) - gamma).",
    whyGrad:
      "Zero reference scoring calls — one 9-line PyTorch loss passed to trainer.forward_backward_custom(outputs=['logprobs']) computes exact masked mean logprobs and updates the LoRA weights.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Reference-free SimPO is 9 lines of PyTorch in forward_backward_custom with bit-exact gradients.",
    },
    walkthrough: [
      { title: "Pack (chosen, rejected) pairs with assistant loss_mask", explanation: "Let base.tokenize(..., return_loss_mask=True) mask out the shared prompt automatically.", gradCall: "base.tokenize(messages=pair, return_loss_mask=True)" },
      { title: "Compute length-normalized logprobs with target margin gamma", explanation: "Divide masked logprobs by mask.sum() for chosen and rejected, then apply logsigmoid(beta * diff - gamma).", gradCall: "trainer.forward_backward_custom(batch, outputs=['logprobs'], loss_fn=simpo_loss)" },
      { title: "Export merged artifact", explanation: "No reference model ever touched the GPU — merge LoRA and deploy.", gradCall: "trainer.export(name='simpo-aligned', merge_adapter=True)" },
    ],
    gotchas: [
      "SimPO uses a MUCH larger beta (2.0–2.5) than DPO (0.1) because logprobs are averaged instead of summed.",
      "Tune gamma_ratio = gamma / beta between 0.3 and 0.6; too large a gamma causes degenerate repetition.",
    ],
    linesOfCode: 19,
    typicalBaselineLoc: "~450 LOC forked DPOTrainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~8 min", estCost: "~$0.65" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", compute: "1x H100", duration: "~4 min", estCost: "~$0.35" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/ultrafeedback_binarized", label: "UltraFeedback Binarized", source: "Hugging Face (public)", examples: "61,135 preference pairs" },
    ],
    primitives: [
      { label: "forward_backward_custom", href: "/docs/training/custom-loops/" },
      { label: "SFT & DPO guide", href: "/docs/training/recipes/sft-dpo/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
import grad
from grad import Grad, ModelSpec

client = Grad()

def simpo_loss(datums, out, beta=2.0, gamma=0.5):
    losses = []
    for g in grad.by_group(datums, out):
        c, r = g["chosen"], g["rejected"]
        margin = grad.masked_mean(c.logprobs, c.mask) - grad.masked_mean(r.logprobs, r.mask)
        losses.append(-F.logsigmoid(beta * margin - gamma))
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_pair_batches("hf://HuggingFaceH4/ultrafeedback_binarized", batch_size=32)):
        fb = trainer.forward_backward_custom(batch, outputs=["logprobs"], loss_fn=simpo_loss)
        opt = trainer.optim_step(lr=3e-5, grad_clip=1.0)
        print(f"step={step} simpo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="simpo-ultrafeedback", merge_adapter=True)`,
    paperYaml: `slug: simpo
title: "SimPO: Simple Preference Optimization"
arxiv: "https://arxiv.org/abs/2405.14734"
category: preference
public_dataset: "hf://HuggingFaceH4/ultrafeedback_binarized"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/simpo (arXiv:2405.14734)
Dataset   hf://HuggingFaceH4/ultrafeedback_binarized (61,135 pairs · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · reference-free
Loss      custom simpo_loss (beta=2.0, gamma=0.5)
Estimate  1x H100 · ~8 min · ~$0.65 · warnings: 0`,
    benchmarks: [
      { benchmark: "AlpacaEval 2 LC Win Rate", paperReported: "+6.4 pts over DPO on Llama-3-8B without a reference model", templateSetup: "UltraFeedback · Qwen/Qwen3-8B · beta=2.0, gamma=0.5" },
    ],
    bibtex: `@inproceedings{meng2024simpo,
  title={SimPO: Simple Preference Optimization with a Reference-Free Reward},
  author={Meng, Yu and Xia, Mengzhou and Chen, Danqi},
  booktitle={NeurIPS},
  year={2024}
}`,
  },
  {
    slug: "orpo",
    shortTitle: "ORPO",
    title: "ORPO: Monolithic Preference Optimization without Reference Model",
    authors: "Hong et al.",
    year: 2024,
    arxivId: "2403.07691",
    arxivUrl: "https://arxiv.org/abs/2403.07691",
    category: "Preference Alignment",
    oneLiner:
      "Collapse SFT and preference alignment into a single stage by adding a log-odds ratio penalty directly onto standard cross-entropy loss.",
    story:
      "Standard alignment runs two separate stages — SFT first, then DPO with a reference copy — because plain SFT accidentally boosts the probability of *rejected* completions alongside chosen ones. ORPO eliminates the SFT-then-DPO split by attaching an odds-ratio term directly to SFT.",
    insight:
      "Combine standard NLL on chosen responses with -lambda * log sigmoid(log(odds_w / odds_l)), where log odds = avg_logp - log(1 - exp(avg_logp)). One pass teaches both instruction format and preference separation.",
    whyGrad:
      "One 10-line loss function in trainer.forward_backward_custom() fuses SFT NLL and log-odds preference alignment in a single GPU pass.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "10 lines of PyTorch in forward_backward_custom — no reference model and no two-stage checkpoint handoff.",
    },
    walkthrough: [
      { title: "Compute mean log-probability for chosen and rejected", explanation: "Use each datum's 1:1 loss_mask to average logprobs over assistant tokens.", gradCall: "avg_w = (lp_w * mc).sum() / mc.sum()" },
      { title: "Convert probabilities to numerically stable log-odds", explanation: "Clamp exp(avg_lp) below 1-1e-6 before taking log(p / (1 - p)).", gradCall: "log_odds = avg_lp - torch.log1p(-avg_lp.exp().clamp(max=1-1e-6))" },
      { title: "Add lambda * odds-ratio loss to chosen SFT NLL", explanation: "Optimize both terms jointly in one pass with AdamW.", gradCall: "trainer.forward_backward_custom(batch, outputs=['logprobs'], loss_fn=orpo_loss)" },
    ],
    gotchas: [
      "Clamp exp(avg_lp) strictly below 1.0 - 1e-6 to avoid NaN gradients inside log1p(-p) on very confident sequences.",
      "Start with lam=0.1; values above 0.5 can under-train the SFT language modeling objective.",
    ],
    linesOfCode: 22,
    typicalBaselineLoc: "~500 LOC ORPOTrainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~9 min", estCost: "~$0.70" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", compute: "1x H100", duration: "~5 min", estCost: "~$0.40" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/ultrafeedback_binarized", label: "UltraFeedback Binarized", source: "Hugging Face (public)", examples: "61,135 preference pairs" },
    ],
    primitives: [
      { label: "forward_backward_custom", href: "/docs/training/custom-loops/" },
      { label: "SFT & DPO guide", href: "/docs/training/recipes/sft-dpo/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
import grad
from grad import Grad, ModelSpec

client = Grad()

def _log_odds(avg_lp: torch.Tensor) -> torch.Tensor:
    return avg_lp - torch.log1p(-avg_lp.exp().clamp(max=1.0 - 1e-6))

def orpo_loss(datums, out, lam=0.1):
    losses = []
    for g in grad.by_group(datums, out):
        c, r = g["chosen"], g["rejected"]
        avg_w, avg_l = grad.masked_mean(c.logprobs, c.mask), grad.masked_mean(r.logprobs, r.mask)
        losses.append(-avg_w - lam * F.logsigmoid(_log_odds(avg_w) - _log_odds(avg_l)))
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_pair_batches("hf://HuggingFaceH4/ultrafeedback_binarized", batch_size=32)):
        fb = trainer.forward_backward_custom(batch, outputs=["logprobs"], loss_fn=orpo_loss)
        opt = trainer.optim_step(lr=1e-4, grad_clip=1.0)
        print(f"step={step} orpo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="orpo-monolithic", merge_adapter=True)`,
    paperYaml: `slug: orpo
title: "ORPO: Monolithic Preference Optimization"
arxiv: "https://arxiv.org/abs/2403.07691"
category: preference
public_dataset: "hf://HuggingFaceH4/ultrafeedback_binarized"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/orpo (arXiv:2403.07691)
Dataset   hf://HuggingFaceH4/ultrafeedback_binarized (61,135 pairs · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · single-stage SFT+preference
Loss      custom orpo_loss (lam=0.10)
Estimate  1x H100 · ~9 min · ~$0.70 · warnings: 0`,
    benchmarks: [
      { benchmark: "AlpacaEval 2.0", paperReported: "Outperforms 2-stage SFT+DPO on Mistral-7B in a single training run", templateSetup: "UltraFeedback · Qwen/Qwen3-8B · lam=0.1" },
    ],
    bibtex: `@inproceedings{hong2024orpo,
  title={ORPO: Monolithic Preference Optimization without Reference Model},
  author={Hong, Jiwoo and Lee, Noah and Thorne, James},
  booktitle={EMNLP},
  year={2024}
}`,
  },
  {
    slug: "kto",
    shortTitle: "KTO",
    title: "KTO: Kahneman-Tversky Optimization on Unpaired Thumbs Up/Down",
    authors: "Ethayarajh et al. (Contextual AI)",
    year: 2024,
    arxivId: "2402.01306",
    arxivUrl: "https://arxiv.org/abs/2402.01306",
    category: "Preference Alignment",
    oneLiner:
      "Align models directly from real-world unpaired thumbs-up / thumbs-down production feedback using prospect-theoretic loss aversion.",
    story:
      "Most production apps don't have side-by-side (chosen, rejected) pairs — they have millions of single thumbs-up / thumbs-down clicks or pass/fail checks. KTO draws on Kahneman & Tversky's prospect theory to align directly on unpaired binary feedback, even when classes are heavily imbalanced.",
    insight:
      "Compute each example's KL-shifted reward r = beta * sum(log pi - log pi_ref) against the detached batch mean KL baseline z_0, then apply asymmetric loss-aversion weights (lambda_D for desirable, lambda_U for undesirable) inside 1 - sigmoid(sign * (r - z_0)).",
    whyGrad:
      "Datum.role supports 'desirable' and 'undesirable' natively, ref.score_logprobs() computes reference logprobs in one call, and the prospect-theoretic loss is 12 lines in forward_backward_custom.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Unpaired trajectories with role='desirable'|'undesirable' plug straight into forward_backward_custom with zero pair matching.",
    },
    walkthrough: [
      { title: "Tag unpaired examples as desirable or undesirable", explanation: "Set role='desirable' for thumbs-up traces and role='undesirable' for thumbs-down traces.", gradCall: "Datum(..., role='desirable' | 'undesirable')" },
      { title: "Score reference logprobs once", explanation: "Compute aligned reference logprobs against the frozen starting checkpoint.", gradCall: "ref.score_logprobs(trajs)['aligned_logprobs']" },
      { title: "Optimize prospect-theoretic KTO loss with detached z_0", explanation: "Estimate the KL baseline z_0 across the batch (detached) and weight desirable vs undesirable examples.", gradCall: "trainer.forward_backward_custom(datums, outputs=['logprobs'], loss_fn=kto_loss)" },
    ],
    gotchas: [
      "Always .detach() z_0 (the mean batch KL baseline) — backpropagating through z_0 destabilizes training.",
      "Set lam_d / lam_u inversely proportional to class counts (aiming for n_D * lam_d ~ 1.33 * n_U * lam_u per the paper).",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~700 LOC TRL KTOTrainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~11 min", estCost: "~$0.88" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", compute: "1x H100", duration: "~6 min", estCost: "~$0.48" },
    ],
    datasets: [
      { id: "hf://trl-lib/kto-mix-14k", label: "KTO Mix 14k (unpaired)", source: "Hugging Face (public)", examples: "13,500 binary-labeled examples" },
    ],
    primitives: [
      { label: "forward_backward_custom", href: "/docs/training/custom-loops/" },
      { label: "Trajectories & feedback", href: "/docs/training/trajectories/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)

def kto_loss(datums, out, beta=0.1, lam_d=1.0, lam_u=1.33):
    kls = [((lp - rlp) * m).sum() for lp, rlp, m in zip(out["logprobs"], out["ref_logprobs"], out["masks"])]
    z0 = torch.stack(kls).detach().mean().clamp(min=0.0)
    losses = [
        lam_d * (1.0 - torch.sigmoid(beta * (kl - z0))) if d.role == "desirable"
        else lam_u * (1.0 - torch.sigmoid(beta * (z0 - kl)))
        for kl, d in zip(kls, datums)
    ]
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_kto_batches("hf://trl-lib/kto-mix-14k", ref=ref, batch_size=32)):
        fb = trainer.forward_backward_custom(batch, outputs=["logprobs"], loss_fn=kto_loss)
        opt = trainer.optim_step(lr=3e-5, grad_clip=1.0)
        print(f"step={step} kto_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="kto-aligned", merge_adapter=True)`,
    paperYaml: `slug: kto
title: "KTO: Kahneman-Tversky Optimization"
arxiv: "https://arxiv.org/abs/2402.01306"
category: preference
public_dataset: "hf://trl-lib/kto-mix-14k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/kto (arXiv:2402.01306)
Dataset   hf://trl-lib/kto-mix-14k (13,500 unpaired examples · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32)
Loss      custom kto_loss (beta=0.10, lam_d=1.0, lam_u=1.33)
Estimate  1x H100 · ~11 min · ~$0.88 · warnings: 0`,
    benchmarks: [
      { benchmark: "Unpaired alignment vs. DPO", paperReported: "Matches or exceeds DPO at 1B–30B scale using only binary thumbs-up/down labels", templateSetup: "kto-mix-14k · Qwen/Qwen3-8B · beta=0.1" },
    ],
    bibtex: `@inproceedings{ethayarajh2024kto,
  title={KTO: Model Alignment as Prospect Theoretic Optimization},
  author={Ethayarajh, Kawin and others},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "ipo",
    shortTitle: "IPO",
    title: "IPO: Identity Preference Optimization",
    authors: "Azar et al. (Google DeepMind)",
    year: 2023,
    arxivId: "2310.12036",
    arxivUrl: "https://arxiv.org/abs/2310.12036",
    category: "Preference Alignment",
    oneLiner:
      "Replace DPO's unbounded logsigmoid with a squared hinge target 1/(2*tau) so deterministic preferences never cause the policy to overfit and collapse KL.",
    story:
      "DeepMind showed a subtle pathology in DPO: whenever preference data is near-deterministic (annotators always pick A over B), DPO drives the log-probability gap toward infinity, completely ignoring KL regularization and overfitting the dataset. IPO replaces the Bradley-Terry logsigmoid with a bounded quadratic objective.",
    insight:
      "Minimize ((log_ratio_w - log_ratio_l) - 1 / (2 * tau))^2 — once the log-ratio margin reaches 1/(2*tau), the gradient drops cleanly to zero instead of pushing probabilities to extreme values.",
    whyGrad:
      "Swap a single line inside the preference loss function in trainer.forward_backward_custom() — 10 lines total.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Swapping logsigmoid for the bounded IPO squared target is a 1-line edit in forward_backward_custom.",
    },
    walkthrough: [
      { title: "Score reference logprobs on (chosen, rejected) pairs", explanation: "Cache aligned reference logprobs from the starting SFT artifact.", gradCall: "ref.score_logprobs(pairs)['aligned_logprobs']" },
      { title: "Regress the log-ratio margin toward 1/(2*tau)", explanation: "Compute delta = (lp_w - ref_w) - (lp_l - ref_l) and minimize (delta - 0.5 / tau) ** 2.", gradCall: "((delta - 0.5 / tau) ** 2).mean()" },
      { title: "Step and export", explanation: "IPO stays well-regularized even over multiple epochs on small preference datasets.", gradCall: "trainer.export(name='ipo-aligned', merge_adapter=True)" },
    ],
    gotchas: [
      "IPO is especially strong on small, high-agreement domain preference sets (500–3,000 pairs) where DPO overfits after 1 epoch.",
      "Typical tau values sit around 0.1–0.25 (giving a target log-ratio margin of 2.0–5.0).",
    ],
    linesOfCode: 21,
    typicalBaselineLoc: "~450 LOC TRL DPOTrainer config",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~11 min", estCost: "~$0.88" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/ultrafeedback_binarized", label: "UltraFeedback Binarized", source: "Hugging Face (public)", examples: "61,135 preference pairs" },
    ],
    primitives: [
      { label: "forward_backward_custom", href: "/docs/training/custom-loops/" },
      { label: "SFT & DPO guide", href: "/docs/training/recipes/sft-dpo/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
import grad
from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)

def ipo_loss(datums, out, tau=0.1):
    losses = []
    for g in grad.by_group(datums, out):
        c, r = g["chosen"], g["rejected"]
        rw = ((c.logprobs - c.ref_logprobs) * c.mask).sum()
        rl = ((r.logprobs - r.ref_logprobs) * r.mask).sum()
        losses.append(((rw - rl) - 0.5 / tau) ** 2)
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_pair_batches("hf://HuggingFaceH4/ultrafeedback_binarized", ref=ref, batch_size=32)):
        fb = trainer.forward_backward_custom(batch, outputs=["logprobs"], loss_fn=ipo_loss)
        opt = trainer.optim_step(lr=3e-5, grad_clip=1.0)
        print(f"step={step} ipo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="ipo-aligned", merge_adapter=True)`,
    paperYaml: `slug: ipo
title: "IPO: Identity Preference Optimization"
arxiv: "https://arxiv.org/abs/2310.12036"
category: preference
public_dataset: "hf://HuggingFaceH4/ultrafeedback_binarized"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/ipo (arXiv:2310.12036)
Dataset   hf://HuggingFaceH4/ultrafeedback_binarized (61,135 pairs · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32)
Loss      custom ipo_loss (tau=0.10, bounded quadratic target=5.0)
Estimate  1x H100 · ~11 min · ~$0.88 · warnings: 0`,
    benchmarks: [
      { benchmark: "Overfitting resistance", paperReported: "Eliminates DPO late-epoch degradation on deterministic preference sets", templateSetup: "UltraFeedback · Qwen/Qwen3-8B · tau=0.1" },
    ],
    bibtex: `@inproceedings{azar2024ipo,
  title={A General Theoretical Paradigm to Understand Learning from Human Preferences},
  author={Azar, Mohammad Gheshlaghi and others},
  booktitle={AISTATS},
  year={2024}
}`,
  },
  {
    slug: "online-dpo",
    shortTitle: "Online DPO",
    title: "Online DPO: Direct Alignment from On-Policy AI Feedback",
    authors: "Guo et al. (Google DeepMind)",
    year: 2024,
    arxivId: "2402.04792",
    arxivUrl: "https://arxiv.org/abs/2402.04792",
    category: "Preference Alignment",
    oneLiner:
      "Close the distribution gap between offline DPO and RLHF by sampling fresh pairs from the live policy every step and ranking them online.",
    story:
      "Offline DPO trains on static completions generated by an older model, so the policy wastes capacity penalizing mistakes it no longer makes while never seeing its own new failure modes. Online DPO bridges DPO and RLHF: sample 2 fresh responses from the current policy, score them with a judge or reward model, and run DPO on the live winner/loser pair.",
    insight:
      "Alternate trainer.snapshot().sample(prompts, n=2), rank each pair with a Rubric or reward Artifact, score reference logprobs on the winning/losing trajectories, and step with built-in loss='dpo'.",
    whyGrad:
      "Built-in snapshot().sample(n=2) + ref.score_logprobs() + built-in loss='dpo' run the entire online preference loop in 28 lines with zero custom loss math.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Combines three built-in primitives (snapshot.sample, ref.score_logprobs, loss='dpo') with zero custom loss code.",
    },
    walkthrough: [
      { title: "Sample two live candidates per prompt", explanation: "Generate on-policy pairs directly from the current trainer snapshot.", gradCall: "trainer.snapshot().sample(prompts, n=2)" },
      { title: "Rank winner vs. loser with a reward model or judge", explanation: "Score both completions with a trained RM artifact or deterministic rubric to assign chosen/rejected.", gradCall: "rm.infer_batch(candidates)" },
      { title: "Update with built-in DPO loss", explanation: "Attach reference logprobs and shared group_id, then step with built-in loss='dpo'.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'dpo', 'beta': 0.1})" },
    ],
    gotchas: [
      "Skip pairs where the reward difference |r_a - r_b| is near zero (ties) so noisy judge flips don't corrupt gradients.",
      "Online DPO needs far fewer steps than offline DPO — evaluate every 20 steps to catch reward-model over-optimization early.",
    ],
    linesOfCode: 28,
    typicalBaselineLoc: "~1,100 LOC OnlineDPOTrainer + vLLM sampler",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~22 min", estCost: "~$1.75" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/ultrafeedback_binarized", label: "UltraFeedback Prompts", source: "Hugging Face (public)", examples: "Prompts only (on-policy pairs)" },
    ],
    primitives: [
      { label: "trainer.snapshot()", href: "/docs/training/custom-loops/" },
      { label: "Built-in dpo loss", href: "/docs/reference/primitives/" },
      { label: "Reward models", href: "/docs/training/recipes/reward-models/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)
rm = client.artifacts.get("helpful-verifier@v1")

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, prompts in enumerate(load_prompt_batches("hf://HuggingFaceH4/ultrafeedback_binarized", batch_size=32)):
        pairs = trainer.snapshot().sample(prompts, n=2, temperature=0.8, max_new_tokens=512)
        flat = [t for p in pairs for t in p]
        scores = [r["logits"][0].item() for r in rm.infer_batch(flat)]
        ref_lps = ref.score_logprobs(flat)["aligned_logprobs"]

        datums = []
        for idx in range(0, len(flat), 2):
            a, b = flat[idx], flat[idx + 1]
            sa, sb = scores[idx], scores[idx + 1]
            if abs(sa - sb) < 0.05:
                continue  # skip ties
            w, l, rw, rl = (a, b, ref_lps[idx], ref_lps[idx + 1]) if sa > sb else (b, a, ref_lps[idx + 1], ref_lps[idx])
            gid = f"s{step}_p{idx}"
            datums.append(w.to_datum(ref_logprobs=rw, group_id=gid, role="chosen"))
            datums.append(l.to_datum(ref_logprobs=rl, group_id=gid, role="rejected"))

        fb = trainer.forward_backward(datums, loss={"kind": "dpo", "beta": 0.1})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} pairs={len(datums)//2} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="online-dpo", merge_adapter=True)`,
    paperYaml: `slug: online-dpo
title: "Online DPO (OAIF)"
arxiv: "https://arxiv.org/abs/2402.04792"
category: preference
public_dataset: "hf://HuggingFaceH4/ultrafeedback_binarized"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/online-dpo (arXiv:2402.04792)
Dataset   hf://HuggingFaceH4/ultrafeedback_binarized (prompts · on-policy n=2)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · online RM ranking
Loss      dpo (beta=0.10) on live snapshot pairs
Estimate  1x H100 · ~22 min · ~$1.75 · warnings: 0`,
    benchmarks: [
      { benchmark: "Human/LLM win rate", paperReported: "Consistently beats offline DPO and matches online RLHF without a critic", templateSetup: "UltraFeedback prompts · Qwen/Qwen3-8B · n=2 online ranking" },
    ],
    bibtex: `@article{guo2024online_dpo,
  title={Direct Language Model Alignment from Online AI Feedback},
  author={Guo, Shangmin and others},
  journal={arXiv preprint arXiv:2402.04792},
  year={2024}
}`,
  },
  {
    slug: "spin",
    shortTitle: "SPIN",
    title: "SPIN: Self-Play Fine-Tuning Converts Weak Models to Strong LLMs",
    authors: "Chen et al. (UCLA)",
    year: 2024,
    arxivId: "2401.01335",
    arxivUrl: "https://arxiv.org/abs/2401.01335",
    category: "Preference Alignment",
    oneLiner:
      "Keep improving past SFT using only your original gold dataset — pit the model against its own previous-iteration generations as synthetic negatives.",
    story:
      "Once SFT converges on a fixed human dataset, you normally have to collect brand-new preference annotations to push quality higher. SPIN turns the SFT dataset itself into an adversarial self-play game: the model generates synthetic answers, and the next iteration learns to distinguish real human answers from its own previous generations.",
    insight:
      "At round t, freeze pi_{t-1} as the opponent/reference, sample y_hat ~ pi_{t-1}(x) as 'rejected' against gold human y as 'chosen', and minimize the SPIN logistic loss -log sigmoid(beta * (log(pi_t/pi_{t-1})(y) - log(pi_t/pi_{t-1})(y_hat))).",
    whyGrad:
      "Because SPIN's objective is mathematically identical to iterative DPO where the reference model updates each round to trainer.snapshot(), it takes 26 lines using built-in loss='dpo'.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Refreshing opponent = trainer.snapshot() each outer round + built-in loss='dpo' implements exact SPIN in 26 lines.",
    },
    walkthrough: [
      { title: "Snapshot the current model as round-t opponent", explanation: "At the start of each self-play round, capture an immutable snapshot to serve as both generator and reference.", gradCall: "opponent = trainer.snapshot()" },
      { title: "Generate synthetic negatives on your existing SFT prompts", explanation: "Sample one completion per prompt from opponent and pair it against the gold human response.", gradCall: "opponent.sample(prompts, n=1)" },
      { title: "Train with built-in DPO against the opponent reference", explanation: "Push gold human answers up and previous-round synthetic answers down, then repeat for 3 rounds.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'dpo', 'beta': 0.1})" },
    ],
    gotchas: [
      "Stop after 2–3 self-play rounds — once the policy matches human distribution closely, extra rounds overfit stylistic artifacts.",
      "Start from an SFT-warmed checkpoint (init_from) rather than a raw base model so round-0 generations aren't trivial to separate.",
    ],
    linesOfCode: 26,
    typicalBaselineLoc: "~800 LOC multi-round SPIN pipeline",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", compute: "1x H100", duration: "~19 min", estCost: "~$1.50" },
    ],
    datasets: [
      { id: "hf://HuggingFaceH4/ultrachat_200k", label: "UltraChat 200k (subset)", source: "Hugging Face (public)", examples: "50,000 gold SFT conversations" },
    ],
    primitives: [
      { label: "trainer.snapshot()", href: "/docs/training/custom-loops/" },
      { label: "Built-in dpo loss", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Datum, DatumTargets, Grad, ModelInput, ModelSpec

client = Grad()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for rnd in range(3):
        opponent = trainer.snapshot()  # previous iteration acts as both generator & reference
        for step, batch in enumerate(load_sft_batches("hf://HuggingFaceH4/ultrachat_200k", batch_size=32)):
            synth = [g[0] for g in opponent.sample(batch.prompt_inputs, n=1, max_new_tokens=512)]
            gold_refs = opponent.score_logprobs(batch.gold_tokens)["aligned_logprobs"]

            datums = []
            for idx, (g_toks, g_mask, g_rlp, s_traj) in enumerate(zip(batch.gold_tokens, batch.gold_masks, gold_refs, synth)):
                gid = f"r{rnd}_s{step}_{idx}"
                datums.append(Datum(ModelInput(tokens=g_toks), DatumTargets(loss_mask=g_mask, ref_logprobs=g_rlp), group_id=gid, role="chosen"))
                datums.append(s_traj.to_datum(ref_logprobs=s_traj.output["sampling_logprobs"], group_id=gid, role="rejected"))

            fb = trainer.forward_backward(datums, loss={"kind": "dpo", "beta": 0.1})
            opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
            print(f"round={rnd} step={step} spin_loss={fb.result().loss:.4f}"); opt.result()

    artifact = trainer.export(name="spin-selfplay", merge_adapter=True)`,
    paperYaml: `slug: spin
title: "SPIN: Self-Play Fine-Tuning"
arxiv: "https://arxiv.org/abs/2401.01335"
category: preference
public_dataset: "hf://HuggingFaceH4/ultrachat_200k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/spin (arXiv:2401.01335)
Dataset   hf://HuggingFaceH4/ultrachat_200k (gold SFT only · 3 self-play rounds)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32)
Loss      iterative dpo (beta=0.10) vs previous-round snapshot
Estimate  1x H100 · ~19 min · ~$1.50 · warnings: 0`,
    benchmarks: [
      { benchmark: "Open LLM Leaderboard", paperReported: "+6 pts average gain over SFT without any extra preference data", templateSetup: "UltraChat subset · 3 self-play rounds · Qwen/Qwen3-8B" },
    ],
    bibtex: `@inproceedings{chen2024spin,
  title={Self-Play Fine-Tuning Converts Weak Language Models to Strong Language Models},
  author={Chen, Zixiang and others},
  booktitle={ICML},
  year={2024}
}`,
  },
];
