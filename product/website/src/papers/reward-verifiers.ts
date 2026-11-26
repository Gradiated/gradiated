import type { PaperGuide } from "./types";

export const rewardVerifiersPapers: PaperGuide[] = [
  {
    slug: "math-shepherd",
    shortTitle: "Math-Shepherd",
    title: "Math-Shepherd: Verify and Reinforce LLMs Step-by-Step (PRM)",
    authors: "Wang et al.",
    year: 2024,
    arxivId: "2312.08935",
    arxivUrl: "https://arxiv.org/abs/2312.08935",
    category: "Reward Models & Verifiers",
    oneLiner:
      "Auto-label every intermediate reasoning step via Monte Carlo rollouts — zero human step annotators — and train a token-level Process Reward Model for best-of-N verification.",
    story:
      "Step-level Process Reward Models crush outcome-only verifiers on math and reasoning, but hiring humans to label 800,000 intermediate steps (like PRM800K) costs a fortune. Math-Shepherd replaced human annotators with Monte Carlo tree rollouts: if sampling N completions from step k ever reaches the right answer, step k gets labeled good.",
    insight:
      "Place a binary head at the end-of-step delimiter tokens (positions=[p_1, p_2, ...]) with labels=[y_1, y_2, ...] from Monte Carlo rollout accuracy, train via built-in bce_sparse_positions, and deploy inside a best_of_n or cascade Endpoint.",
    whyGrad:
      "heads={'prm': {'dim': 1, 'token_level': True}} + built-in loss='bce_sparse_positions' trains all steps of a trajectory in a single forward pass, and exports straight into a best_of_n Endpoint.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Built-in sparse-position BCE + token_level head + best_of_n Endpoint strategy handle training and test-time verification end-to-end.",
    },
    walkthrough: [
      { title: "Mark step-boundary token indices in DatumTargets", explanation: "Store the token index of each step boundary in positions=[...] alongside Monte Carlo labels.", gradCall: "DatumTargets(positions=[42, 98, 151], labels=[1.0, 1.0, 0.0])" },
      { title: "Train the token-level PRM head in one forward pass", explanation: "Built-in bce_sparse_positions computes BCE strictly at the marked step indices.", gradCall: "trainer.forward_backward(batch, loss={'kind': 'bce_sparse_positions', 'head': 'prm'})" },
      { title: "Deploy as a best-of-N verifier endpoint", explanation: "Export the .grad PRM artifact and attach it to a best_of_n or cascade production endpoint.", gradCall: "client.endpoints.create(slug='math-verified', strategy={'kind': 'best_of_n', 'verifier': prm.id, 'n': 8})" },
    ],
    gotchas: [
      "Use the minimum step score (min_k p_k) rather than the mean when ranking full reasoning chains — one bad algebra step ruins the answer.",
      "Soft Monte Carlo labels (pass rate in [0, 1]) calibrate much better than hard binary {0, 1} labels.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~900 LOC custom step-masking PRM trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~3.2M tokens", duration: "~16 min", estCost: "~$1.30" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast verifier)", estTokens: "~2.6M tokens", duration: "~8 min", estCost: "~$0.65" },
    ],
    datasets: [
      { id: "hf://peiyi9979/Math-Shepherd", label: "Math-Shepherd Step Labels", source: "Hugging Face (public)", examples: "445k step-annotated trajectories" },
    ],
    primitives: [
      { label: "Reward models guide", href: "/docs/training/recipes/reward-models/" },
      { label: "bce_sparse_positions", href: "/docs/reference/primitives/" },
      { label: "best_of_n Endpoint", href: "/docs/training/endpoints/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()

with client.trainers.create(
    ModelSpec(
        base="Qwen/Qwen3-8B",
        adapter="lora",
        train_mode="lora",
        params={"rank": 32},
        heads={"prm": {"dim": 1, "token_level": True}},
    ),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_prm_batches("hf://peiyi9979/Math-Shepherd", batch_size=32)):
        fb = trainer.forward_backward(batch, loss={"kind": "bce_sparse_positions", "head": "prm"})
        opt = trainer.optim_step(lr=1e-4, grad_clip=1.0)
        print(f"step={step} prm_bce={fb.result().loss:.4f}"); opt.result()
    prm = trainer.export(name="math-shepherd-prm", merge_adapter=True)

client.endpoints.create(
    slug="math-best-of-8",
    artifact="Qwen/Qwen3-8B",
    strategy={"kind": "best_of_n", "verifier": prm.id, "n_samples": 8},
)`,
    paperYaml: `slug: math-shepherd
title: "Math-Shepherd Process Reward Model"
arxiv: "https://arxiv.org/abs/2312.08935"
category: verifiers
public_dataset: "hf://peiyi9979/Math-Shepherd"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/math-shepherd (arXiv:2312.08935)
Dataset   hf://peiyi9979/Math-Shepherd (step-level MC labels · public)
Model     Qwen/Qwen3-8B · adapter=lora + token_level head 'prm'
Loss      bce_sparse_positions (built-in)
Estimate  ~3.2M tokens · ~16 min · ~$1.30 · warnings: 0`,
    benchmarks: [
      { benchmark: "GSM8K / MATH Best-of-N", paperReported: "Boosts Mistral-7B from 77.9% -> 84.1% on GSM8K via PRM verification", templateSetup: "Math-Shepherd public labels · Qwen/Qwen3-8B · Best-of-8" },
    ],
    bibtex: `@inproceedings{wang2024mathshepherd,
  title={Math-Shepherd: Verify and Reinforce LLMs Step-by-step without Human Annotations},
  author={Wang, Peiyi and others},
  booktitle={ACL},
  year={2024}
}`,
  },
  {
    slug: "prime",
    shortTitle: "PRIME",
    title: "PRIME: Process Reinforcement through Implicit Rewards",
    authors: "Cui et al. (Tsinghua / OpenBMB)",
    year: 2025,
    arxivId: "2502.01456",
    arxivUrl: "https://arxiv.org/abs/2502.01456",
    category: "Reward Models & Verifiers",
    oneLiner:
      "Train an online Implicit Process Reward Model from outcome labels alone — getting dense per-token credit assignment during RL with zero step annotations.",
    story:
      "Training a PRM offline (like Math-Shepherd) suffers distribution shift as the RL policy evolves, while pure outcome rewards give zero signal about *which* step went wrong. PRIME trains a second LLM online using only outcome pass/fail labels — and its per-token log-ratio beta * (log pi_prm - log pi_ref) automatically acts as a dense process reward!",
    insight:
      "Run two Trainers side by side: an Implicit PRM updated online with BCE on sigmoid(beta * sum(log pi_prm - log pi_ref)) against binary outcome labels, and a Policy updated with dense per-token advantages combining outcome reward + the PRM's token-level log-ratios.",
    whyGrad:
      "Opening two independent Trainers in one Python `with` block lets the online PRM and Policy co-evolve cleanly with 1:1 aligned per-token advantages — billed per token processed, never idle GPU time.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Two co-evolving Trainers in one script work smoothly with zero distributed orchestration; 38 lines total.",
    },
    walkthrough: [
      { title: "Open two Trainers: policy + online implicit PRM", explanation: "Both share the same frozen reference artifact for computing log-ratios.", gradCall: "with client.trainers.create(...) as policy, client.trainers.create(...) as prm:" },
      { title: "Update the implicit PRM on outcome labels", explanation: "Compute implicit sequence reward beta * sum(lp_prm - lp_ref) and fit BCE against binary task success.", gradCall: "prm.forward_backward_custom(datums, outputs=['logprobs'], loss_fn=implicit_prm_loss)" },
      { title: "Extract per-token process rewards and update the policy", explanation: "Score dense token-level log-ratios from prm.snapshot() and pass per-token advantages into policy.forward_backward().", gradCall: "policy.forward_backward(pol_datums, loss={'kind': 'grpo'})" },
    ],
    gotchas: [
      "Keep PRM beta small (0.05) and clip per-token implicit rewards to [-2, 2] so outlier tokens don't hijack policy updates.",
      "Training two models doubles token spend per rollout; start with a compact 4B PRM paired with an 8B policy.",
    ],
    linesOfCode: 38,
    typicalBaselineLoc: "~2,200 LOC dual-trainer RL cluster",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B policy + 4B PRM", estTokens: "~12.2M tokens", duration: "~32 min", estCost: "~$4.90" },
    ],
    datasets: [
      { id: "hf://openai/gsm8k", label: "GSM8K Math", source: "Hugging Face (public)", examples: "7,473 train / 1,319 test" },
    ],
    primitives: [
      { label: "Multi-trainer custom loops", href: "/docs/training/custom-loops/" },
      { label: "Reward models guide", href: "/docs/training/recipes/reward-models/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
from grad import Grad, ModelSpec

client = Grad()
ref = client.artifacts.get("Qwen/Qwen3-8B")

def implicit_prm_loss(datums, out, beta=0.05):
    losses = []
    for lp, rlp, m, d in zip(out["logprobs"], out["ref_logprobs"], out["masks"], datums):
        r_seq = beta * ((lp - rlp) * m).sum()
        losses.append(F.binary_cross_entropy_with_logits(r_seq, torch.tensor(float(d.targets.scalar))))
    return torch.stack(losses).mean()

spec = ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32})
with client.trainers.create(spec, compute="gpu") as policy, client.trainers.create(spec, compute="gpu") as prm:
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=32)):
        groups = policy.snapshot().sample(batch.prompt_inputs, n=4, max_new_tokens=1024)
        flat = [t for g in groups for t in g]
        ref_lps = ref.score_logprobs(flat)["aligned_logprobs"]
        outcomes = [grade_boxed_math(t.output["text"], gold) for g, gold in zip(groups, batch.answers) for t in g]

        # 1. Update online implicit PRM from outcome pass/fail labels
        prm_datums = [t.to_datum(scalar=y, ref_logprobs=rlp) for t, y, rlp in zip(flat, outcomes, ref_lps)]
        prm.forward_backward_custom(prm_datums, outputs=["logprobs"], loss_fn=implicit_prm_loss).result()
        prm.optim_step(lr=5e-5, grad_clip=1.0).result()

        # 2. Extract dense per-token implicit process rewards -> update policy
        prm_lps = prm.snapshot().score_logprobs(flat)["aligned_logprobs"]
        pol_datums = []
        for t, y, rlp, plp in zip(flat, outcomes, ref_lps, prm_lps):
            tok_adv = [
                (y + 0.05 * (p - r)) if m > 0 else 0.0
                for p, r, m in zip(plp, rlp, t.output["loss_mask"])
            ]
            pol_datums.append(t.to_datum(advantages=tok_adv, ref_logprobs=rlp))

        fb = policy.forward_backward(pol_datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2})
        opt = policy.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} pol_loss={fb.result().loss:.4f}"); opt.result()
    artifact = policy.export(name="prime-policy", merge_adapter=True)`,
    paperYaml: `slug: prime
title: "PRIME: Implicit Process Reward RL"
arxiv: "https://arxiv.org/abs/2502.01456"
category: verifiers
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/prime (arXiv:2502.01456)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     2x Trainers (Qwen/Qwen3-8B policy + online implicit PRM)
Loss      online implicit_prm_loss + per-token grpo
Estimate  ~12.2M tokens · ~32 min · ~$4.90 · warnings: 0`,
    benchmarks: [
      { benchmark: "Sample efficiency on math/code", paperReported: "2.5x sample efficiency & +6.9% average gain over outcome-only RLOO", templateSetup: "GSM8K · dual LoRA trainers · beta=0.05" },
    ],
    bibtex: `@article{cui2025prime,
  title={Process Reinforcement through Implicit Rewards},
  author={Cui, Ganqu and others},
  journal={arXiv preprint arXiv:2502.01456},
  year={2025}
}`,
  },
  {
    slug: "armorm",
    shortTitle: "ArmoRM",
    title: "ArmoRM: Interpretable Multi-Objective Reward Model with MoE Gating",
    authors: "Wang et al. (Princeton / NVIDIA)",
    year: 2024,
    arxivId: "2406.12845",
    arxivUrl: "https://arxiv.org/abs/2406.12845",
    category: "Reward Models & Verifiers",
    oneLiner:
      "Train an interpretable 2-stage reward model: Stage 1 predicts K human-readable rubric attributes, Stage 2 learns a context-dependent gating network over those attributes.",
    story:
      "Black-box scalar reward models are notorious for length bias and opaque failure modes. ArmoRM topped RewardBench with an 8B model by splitting reward modeling into two clean stages: first predict multi-dimensional scores (helpfulness, honesty, verbosity, safety, code quality), then freeze them and learn a lightweight prompt-conditioned gating network.",
    insight:
      "Stage 1 trains a K-dim attribute head with MSE on multi-attribute ratings; Stage 2 freezes the attribute head (trainable=False) and trains a K-dim softmax gating head with Bradley-Terry preference loss over w(x) · attrs(x, y).",
    whyGrad:
      "Per-head trainable: False in ModelSpec.heads + init_from stage chaining implement exact 2-stage ArmoRM with zero manual parameter freezing boilerplate.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Per-head trainable: False (which we added specifically after hitting this smell!) makes Stage-2 head freezing 1 line.",
    },
    walkthrough: [
      { title: "Stage 1: Train the K-dimensional attribute regression head", explanation: "Fit heads={'attrs': {'dim': 5}} on HelpSteer2 multi-attribute ratings.", gradCall: "ModelSpec(..., heads={'attrs': {'dim': 5}})" },
      { title: "Stage 2: Freeze attrs and add the MoE gating head", explanation: "Warm-start with init_from=stage1.id, set attrs.trainable=False, and attach gate.trainable=True.", gradCall: "heads={'attrs': {'dim': 5, 'trainable': False}, 'gate': {'dim': 5, 'trainable': True}}" },
      { title: "Optimize gated Bradley-Terry preference loss", explanation: "Compute scalar score = (softmax(gate) * attrs).sum(-1) for chosen and rejected pairs.", gradCall: "trainer.forward_backward_custom(pairs, outputs=['heads'], loss_fn=gated_bt_loss)" },
    ],
    gotchas: [
      "Subtracting a verbosity correction coefficient from the final gated score eliminates length bias on RewardBench.",
      "Always verify Stage-1 attribute R^2 before starting Stage 2 — weak attribute heads bottleneck the gating network.",
    ],
    linesOfCode: 34,
    typicalBaselineLoc: "~850 LOC two-stage PyTorch head-freezing scripts",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~2.8M tokens", duration: "~14 min", estCost: "~$1.10" },
    ],
    datasets: [
      { id: "hf://nvidia/HelpSteer2", label: "NVIDIA HelpSteer2 (5 attributes)", source: "Hugging Face (public)", examples: "21,362 multi-attribute ratings" },
    ],
    primitives: [
      { label: "Multi-stage head freezing", href: "/docs/training/custom-loops/" },
      { label: "Reward models guide", href: "/docs/training/recipes/reward-models/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
import grad
from grad import Grad, ModelSpec

client = Grad()

# Stage 1: Train K=5 interpretable attribute head on HelpSteer2
with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="frozen_head", train_mode="frozen_head", heads={"attrs": {"dim": 5}}),
    compute="gpu",
) as s1:
    for batch in load_helpsteer_batches("hf://nvidia/HelpSteer2"):
        s1.forward_backward_custom(
            batch, outputs=["heads"],
            loss_fn=lambda ds, o: torch.stack([F.mse_loss(h, torch.tensor(d.metadata["attrs"])) for h, d in zip(o["heads"]["attrs"], ds)]).mean(),
        ).result()
        s1.optim_step(lr=1e-3).result()
    stage1 = s1.export(name="armorm-stage1")

# Stage 2: Freeze attrs head, train context-dependent MoE gating head with Bradley-Terry
def gated_bt_loss(datums, out):
    losses = []
    for g in grad.by_group(datums, out):
        sc = (torch.softmax(g["chosen"].heads["gate"], dim=-1) * g["chosen"].heads["attrs"]).sum()
        sr = (torch.softmax(g["rejected"].heads["gate"], dim=-1) * g["rejected"].heads["attrs"]).sum()
        losses.append(-F.logsigmoid(sc - sr))
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(
        base="Qwen/Qwen3-8B", adapter="frozen_head", train_mode="frozen_head", init_from=stage1.id,
        heads={"attrs": {"dim": 5, "trainable": False}, "gate": {"dim": 5, "trainable": True}},
    ),
    compute="gpu",
) as s2:
    for pairs in load_pair_batches("hf://HuggingFaceH4/ultrafeedback_binarized"):
        s2.forward_backward_custom(pairs, outputs=["heads"], loss_fn=gated_bt_loss).result()
        s2.optim_step(lr=5e-3).result()
    armorm = s2.export(name="armorm-v1")`,
    paperYaml: `slug: armorm
title: "ArmoRM: Multi-Objective Gated Reward Model"
arxiv: "https://arxiv.org/abs/2406.12845"
category: verifiers
public_dataset: "hf://nvidia/HelpSteer2"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/armorm (arXiv:2406.12845)
Dataset   hf://nvidia/HelpSteer2 (5 attributes) + UltraFeedback pairs
Model     Qwen/Qwen3-8B · 2-stage frozen_head (attrs[frozen] + gate[trainable])
Loss      Stage 1 MSE -> Stage 2 gated Bradley-Terry
Estimate  ~2.8M tokens · ~14 min · ~$1.10 · warnings: 0`,
    benchmarks: [
      { benchmark: "RewardBench overall", paperReported: "90.4 overall with Llama-3-8B (top 8B reward model at release)", templateSetup: "HelpSteer2 + UltraFeedback · 2-stage frozen_head" },
    ],
    bibtex: `@inproceedings{wang2024armorm,
  title={Interpretable Preferences via Multi-Objective Reward Modeling and Mixture-of-Experts},
  author={Wang, Haoxiang and others},
  booktitle={EMNLP},
  year={2024}
}`,
  },
  {
    slug: "genrm",
    shortTitle: "GenRM",
    title: "Generative Verifiers (GenRM): Reward Modeling as Next-Token Prediction",
    authors: "Zhang et al. (Google DeepMind)",
    year: 2024,
    arxivId: "2408.15240",
    arxivUrl: "https://arxiv.org/abs/2408.15240",
    category: "Reward Models & Verifiers",
    oneLiner:
      "Train a verifier to write a brief chain-of-thought critique before emitting 'Yes'/'No', then scale accuracy at test time via majority vote over K critiques.",
    story:
      "Linear scalar reward heads cannot 'think' before judging a tricky code diff or multi-step math proof — they compress an entire verification problem into one matrix multiply. GenRM trains the LLM itself with next-token SFT to critique the solution first, then emit a verdict token whose probability acts as a calibrated verifier score.",
    insight:
      "Fine-tune a 4B–8B model on (problem, solution -> critique + 'Verdict: Yes/No') using managed recipe='sft', then deploy behind a majority_vote Endpoint (or score candidate_tokens=['Yes', 'No'] in one pass).",
    whyGrad:
      "Managed recipe='sft' trains the critique-and-verdict model in 9 lines, and strategy={'kind': 'majority_vote', 'n_samples': 5} gives test-time scaling out of the box.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Managed SFT + built-in majority_vote Endpoint strategy — zero custom training or serving loop required.",
    },
    walkthrough: [
      { title: "Format verification traces as (critique + verdict)", explanation: "Store problem, candidate answer, short critique, and final Yes/No verdict in expected_output.", gradCall: "expected_output: {'content': critique + '\\nVerdict: Yes'}" },
      { title: "Train with managed SFT recipe", explanation: "Fine-tune Qwen3-8B with LoRA and merge_adapter=True for low serving latency.", gradCall: "client.runs.create(recipe='sft', ...)" },
      { title: "Deploy with majority_vote test-time scaling", explanation: "Sample 5 independent critiques at test time and aggregate the verdict automatically.", gradCall: "strategy={'kind': 'majority_vote', 'n_samples': 5}" },
    ],
    gotchas: [
      "Balance positive and negative solutions 50/50 in your training set so the verifier doesn't default to 'Yes'.",
      "Use temperature=0.7 during majority_vote sampling so the 5 critiques explore distinct error checks.",
    ],
    linesOfCode: 16,
    typicalBaselineLoc: "~650 LOC SFT + custom majority-vote serving proxy",
    mode: "Managed recipe",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~2.4M tokens", duration: "~12 min", estCost: "~$0.95" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast verifier)", estTokens: "~1.9M tokens", duration: "~6 min", estCost: "~$0.48" },
    ],
    datasets: [
      { id: "hf://openai/gsm8k", label: "GSM8K Critique Verifier Set", source: "Hugging Face (public)", examples: "Synthesized correct + faulty solutions" },
    ],
    primitives: [
      { label: "Reward models guide", href: "/docs/training/recipes/reward-models/" },
      { label: "majority_vote Endpoint", href: "/docs/training/endpoints/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad

client = Grad()

run = client.runs.create(
    dataset="gsm8k-critique-verdicts",
    name="math-genrm",
    recipe="sft",
    base="Qwen/Qwen3-8B",
    adapter={"kind": "lora", "rank": 32},
    compute="gpu",
    optimizer={"kind": "adamw", "lr": 2e-4},
    merge_adapter=True,
).wait()

client.endpoints.create(
    slug="math-genrm-judge",
    artifact=run.artifact_id,
    strategy={"kind": "majority_vote", "n_samples": 5},
)`,
    paperYaml: `slug: genrm
title: "Generative Verifiers (GenRM)"
arxiv: "https://arxiv.org/abs/2408.15240"
category: verifiers
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/genrm (arXiv:2408.15240)
Dataset   gsm8k-critique-verdicts (critique + Yes/No verdict pairs)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · majority_vote n=5
Loss      cross_entropy (managed sft)
Estimate  ~2.4M tokens · ~12 min · ~$0.95 · warnings: 0`,
    benchmarks: [
      { benchmark: "GSM8K verification accuracy", paperReported: "+16–64% relative gain over discriminative scalar reward models with majority voting", templateSetup: "Qwen/Qwen3-8B SFT + majority_vote n=5" },
    ],
    bibtex: `@inproceedings{zhang2025genrm,
  title={Generative Verifiers: Reward Modeling as Next-Token Prediction},
  author={Zhang, Lunjun and others},
  booktitle={ICLR},
  year={2025}
}`,
  },
  {
    slug: "vineppo",
    shortTitle: "VinePPO",
    title: "VinePPO: Unlocking RL Potential via Monte Carlo Value Estimation",
    authors: "Kazemnejad et al. (Mila)",
    year: 2024,
    arxivId: "2410.01679",
    arxivUrl: "https://arxiv.org/abs/2410.01679",
    category: "Reward Models & Verifiers",
    oneLiner:
      "Replace noisy learned value critics with unbiased Monte Carlo value estimates computed by branching K rollouts from every intermediate reasoning step.",
    story:
      "Value networks in PPO are chronically inaccurate on reasoning tasks because small algebraic errors flip a problem's value from 0.9 to 0.0 instantaneously. VinePPO replaces the value network with exact Monte Carlo branching: pause at each reasoning step s_t, branch K rollouts using resume_from, and estimate V(s_t) as the empirical pass rate.",
    insight:
      "For each reasoning step s_t along a trajectory, estimate V(s_t) via K Monte Carlo rollouts branched from s_t, compute step advantage A_t = V(s_{t+1}) - V(s_t), broadcast to that step's tokens, and update with clipped PPO/GRPO.",
    whyGrad:
      "Artifact.sample(resume_from=step_prefix, n=K) branches directly from any intermediate token prefix while preserving exact 1:1 token alignment, and to_datum(advantages=tok_adv) feeds straight into built-in loss='grpo'.",
    smoothness: {
      rating: "Clean",
      verdict:
        "resume_from prefix branching + dense per-token advantages=[...] make VinePPO's tree-structured credit assignment 32 lines.",
    },
    walkthrough: [
      { title: "Sample an initial reasoning trajectory", explanation: "Generate a full multi-step solution from trainer.snapshot().", gradCall: "traj = snap.sample([prompt], n=1)[0][0]" },
      { title: "Branch K Monte Carlo rollouts from each step prefix", explanation: "Slice the trajectory at each step boundary and call snap.sample(resume_from=prefix, n=4) to estimate V(s_t).", gradCall: "snap.sample([prompt], resume_from=[prefix], n=4)" },
      { title: "Assign step-level advantage V(s_{t+1}) - V(s_t) per token", explanation: "Broadcast each step's exact advantage onto its tokens and step with built-in grpo.", gradCall: "traj.to_datum(advantages=tok_adv)" },
    ],
    gotchas: [
      "Only branch at natural step delimiters (e.g. double newlines) — branching every token is prohibitively expensive.",
      "Cache shared KV prefixes on the server: all K branches from step t share the exact same prefix tokens.",
    ],
    linesOfCode: 32,
    typicalBaselineLoc: "~1,400 LOC tree-rollout PPO framework",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~7.1M tokens", duration: "~36 min", estCost: "~$2.85" },
    ],
    datasets: [
      { id: "hf://openai/gsm8k", label: "GSM8K Math", source: "Hugging Face (public)", examples: "7,473 train / 1,319 test" },
    ],
    primitives: [
      { label: "sample(resume_from=...)", href: "/docs/reference/primitives/" },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
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
    for step, batch in enumerate(load_math_batches("hf://openai/gsm8k", batch_size=16)):
        snap = trainer.snapshot()
        trajs = [g[0] for g in snap.sample(batch.prompt_inputs, n=1, max_new_tokens=1024)]

        datums = []
        for prompt, traj, gold in zip(batch.prompt_inputs, trajs, batch.answers):
            step_spans = find_step_token_spans(traj)  # list of (start_idx, end_idx)
            # Estimate V(s_k) by branching K=4 Monte Carlo rollouts from each step prefix
            prefixes = [traj.slice_prefix(start) for start, _ in step_spans]
            branches = snap.sample(resume_from=prefixes, n=4, max_new_tokens=512)
            v_est = [statistics.fmean(grade_boxed_math(b.output["text"], gold) for b in br) for br in branches]
            v_est.append(grade_boxed_math(traj.output["text"], gold))  # terminal value

            tok_adv = [0.0] * len(traj.output["token_ids"])
            for k, (start, end) in enumerate(step_spans):
                step_a = v_est[k + 1] - v_est[k]
                for i in range(start, end):
                    tok_adv[i] = step_a
            datums.append(traj.to_datum(advantages=tok_adv))

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} vineppo_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="vineppo-math", merge_adapter=True)`,
    paperYaml: `slug: vineppo
title: "VinePPO: Monte Carlo Value Estimation RL"
arxiv: "https://arxiv.org/abs/2410.01679"
category: verifiers
public_dataset: "hf://openai/gsm8k"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/vineppo (arXiv:2410.01679)
Dataset   hf://openai/gsm8k (7,473 train / 1,319 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · K=4 MC branches/step
Loss      grpo with Monte Carlo step advantages V(s_{t+1}) - V(s_t)
Estimate  ~7.1M tokens · ~36 min · ~$2.85 · warnings: 0`,
    benchmarks: [
      { benchmark: "MATH & GSM8K accuracy", paperReported: "Outperforms PPO and RLOO with 9x lower value estimation error", templateSetup: "GSM8K · Qwen/Qwen3-8B · K=4 branches per reasoning step" },
    ],
    bibtex: `@article{kazemnejad2024vineppo,
  title={VinePPO: Unlocking RL Potential For LLM Reasoning Through Refined Credit Assignment},
  author={Kazemnejad, Amirhossein and others},
  journal={arXiv preprint arXiv:2410.01679},
  year={2024}
}`,
  },
  {
    slug: "safe-rlhf",
    shortTitle: "Safe RLHF",
    title: "Safe RLHF: Primal-Dual Lagrangian Constrained Alignment",
    authors: "Dai et al. (PKU-Alignment)",
    year: 2024,
    arxivId: "2310.12773",
    arxivUrl: "https://arxiv.org/abs/2310.12773",
    category: "Reward Models & Verifiers",
    oneLiner:
      "Decouple helpfulness and safety into separate reward and cost models, then dynamically balance them during RL with an online Lagrangian multiplier lambda.",
    story:
      "Stuffing helpfulness and harmlessness into a single reward model forces an awkward trade-off: models either become sycophantically unsafe or refuse benign requests. Safe RLHF separates helpfulness (reward R) from harmfulness (cost C <= 0) and uses dual gradient ascent on a Lagrange multiplier lambda to enforce safety strictly.",
    insight:
      "Score every rollout with both a Reward Artifact R(x,y) and a Cost Artifact C(x,y), train the policy on shaped reward R(x,y) - lambda * C(x,y), and update log(lambda) += lr_lam * mean(C(x,y) - cost_limit) after each step.",
    whyGrad:
      "Scoring rollouts with two pinned Artifacts (rm.infer_batch and cm.infer_batch) + updating scalar lambda in 2 lines of Python implements full primal-dual Safe RLHF cleanly.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Two read-only Artifact handles + 2-line dual update on lambda plug directly into built-in loss='grpo'.",
    },
    walkthrough: [
      { title: "Pin separate Reward and Cost verifier Artifacts", explanation: "Keep helpfulness and safety scores independent so you can inspect both curves live.", gradCall: "rm.infer_batch(inputs), cm.infer_batch(inputs)" },
      { title: "Form Lagrangian shaped reward R - lam * C", explanation: "Group-normalize the Lagrangian utility and pass advantages into built-in GRPO.", gradCall: "util = r_help - lam * c_harm" },
      { title: "Update Lagrange multiplier lambda via dual ascent", explanation: "Increase lambda whenever mean batch cost exceeds your threshold; decay it when safely below.", gradCall: "log_lam = clamp(log_lam + lr_lam * (mean_cost - cost_limit))" },
    ],
    gotchas: [
      "Clamp log_lam (e.g. [-4, 4]) so early unsafe batches don't explode lambda and cause total refusal collapse.",
      "Log mean_reward, mean_cost, and lam together — healthy runs show mean_cost converging smoothly to <= 0 while reward climbs.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~1,500 LOC PKU-SafeRLHF primal-dual PPO",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~4.7M tokens", duration: "~24 min", estCost: "~$1.90" },
    ],
    datasets: [
      { id: "hf://PKU-Alignment/PKU-SafeRLHF", label: "PKU-SafeRLHF", source: "Hugging Face (public)", examples: "83,417 helpfulness + safety prompts" },
    ],
    primitives: [
      { label: "Artifact.infer_batch", href: "/docs/training/endpoints/" },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import math, statistics
import grad
from grad import Grad, ModelSpec

client = Grad()
rm = client.artifacts.get("helpful-rm@v1")
cm = client.artifacts.get("safety-cost-rm@v1")
log_lam, cost_limit = 0.0, 0.0

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, prompts in enumerate(load_prompt_batches("hf://PKU-Alignment/PKU-SafeRLHF", batch_size=32)):
        groups = trainer.snapshot().sample(prompts, n=4, max_new_tokens=512)
        flat = [t for g in groups for t in g]
        r_vals = [o["logits"][0].item() for o in rm.infer_batch(flat)]
        c_vals = [o["logits"][0].item() for o in cm.infer_batch(flat)]

        lam = math.exp(log_lam)
        u_groups = [[r - lam * c for r, c in zip(r_vals[i:i+4], c_vals[i:i+4])] for i in range(0, len(flat), 4)]
        datums = grad.group_datums(groups, rewards=u_groups, norm="std")

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        fb.result(); opt.result()
        # Dual ascent on Lagrange multiplier lambda
        mean_cost = statistics.fmean(c_vals)
        log_lam = max(-4.0, min(4.0, log_lam + 0.05 * (mean_cost - cost_limit)))
        print(f"step={step} mean_cost={mean_cost:.3f} lam={math.exp(log_lam):.3f}")
    artifact = trainer.export(name="safe-rlhf-8b", merge_adapter=True)`,
    paperYaml: `slug: safe-rlhf
title: "Safe RLHF: Primal-Dual Constrained Alignment"
arxiv: "https://arxiv.org/abs/2310.12773"
category: verifiers
public_dataset: "hf://PKU-Alignment/PKU-SafeRLHF"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/safe-rlhf (arXiv:2310.12773)
Dataset   hf://PKU-Alignment/PKU-SafeRLHF (public safety + helpfulness prompts)
Model     Qwen/Qwen3-8B · dual reward/cost artifacts + online lambda
Loss      grpo with Lagrangian utility R - lam * C
Estimate  ~4.7M tokens · ~24 min · ~$1.90 · warnings: 0`,
    benchmarks: [
      { benchmark: "Harmlessness + helpfulness Pareto", paperReported: "Reduces harmful responses from 53% -> <3% while improving helpfulness", templateSetup: "PKU-SafeRLHF · Qwen/Qwen3-8B · cost_limit=0.0" },
    ],
    bibtex: `@inproceedings{dai2024saferlhf,
  title={Safe RLHF: Safe Reinforcement Learning from Human Feedback},
  author={Dai, Josef and others},
  booktitle={ICLR},
  year={2024}
}`,
  },
];
