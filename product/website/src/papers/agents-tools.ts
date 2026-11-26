import type { PaperGuide } from "./types";

export const agentsToolsPapers: PaperGuide[] = [
  {
    slug: "search-r1",
    shortTitle: "Search-R1",
    title: "Search-R1: Training LLMs to Reason and Leverage Search Engines with RL",
    authors: "Jin et al.",
    year: 2025,
    arxivId: "2503.09516",
    arxivUrl: "https://arxiv.org/abs/2503.09516",
    category: "Agents & Tool Use",
    oneLiner:
      "Teach an LLM when to stop thinking, issue multi-hop search queries, and read live retrieved passages using outcome-only RL with strict retrieved-token masking.",
    story:
      "Classic RAG runs retrieval once before generation and hopes the top-k passages cover every hop of a complex question. When teams first tried multi-turn search RL, policy gradients backpropagated straight through retrieved Wikipedia text — causing models to hallucinate fake documents and collapse within dozens of steps. Search-R1 showed outcome-only RL learns sharp multi-hop search strategies as long as retrieved tokens never enter the policy loss.",
    insight:
      "Put the search engine inside the rollout loop: alternate model-generated <think> and <search> spans with externally injected <information> passages, and set loss_mask = 0.0 on every retrieved token so GRPO reinforces only query formulation and final synthesis.",
    whyGrad:
      "Subclassing Environment keeps your search index on your own CPU box while Observation(text=...) automatically tokenizes retrieved passages on the server with loss_mask = 0.0 and sampling_logprobs = 0.0 — zero off-by-one masking bugs.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Environment.rollout_groups() handles stop-tag interruption, server-side observation masking, and bounded retrieval concurrency out of the box.",
    },
    walkthrough: [
      { title: "Wrap your retriever in a multi-turn Environment", explanation: "Parse <search>...</search>, query your local FAISS/BM25 index, and return Observation(text=...) wrapped in <information> tags.", gradCall: "Environment.step() -> Observation(text=..., done=...)" },
      { title: "Score only the final answer with a verifiable Rubric", explanation: "Attach an exact-match RubricTerm on <answer>...</answer> — no gold search queries required.", gradCall: "Rubric([RubricTerm('em', 1.0, exact_match)])" },
      { title: "Roll out multi-hop trajectories with auto-masked docs", explanation: "env.rollout_groups() stops at </search> or </answer> and injects retrieved text with loss_mask=0.0 automatically.", gradCall: "env.rollout_groups(snap, batch, group_size=8, max_turns=4)" },
      { title: "Pipeline the masked GRPO update", explanation: "Center group rewards, skip zero-variance groups, and step with built-in grpo.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'grpo', 'kl_beta': 0.001})" },
    ],
    gotchas: [
      "Always pass stop=['</search>', '</answer>'] — without hard stop delimiters the model hallucinates its own <information> block right after a query.",
      "Keep local retrieval latency under 50 ms so high-concurrency rollouts don't starve GPU training.",
      "Check metrics['kl_sample_train'] on step 0 to confirm zero tokenization drift across retrieved spans.",
    ],
    linesOfCode: 40,
    typicalBaselineLoc: "~1,900 LOC custom vLLM + multi-turn search worker",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~8.4M tokens", duration: "~42 min", estCost: "~$3.35" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", estTokens: "~6.0M tokens", duration: "~19 min", estCost: "~$1.50" },
    ],
    datasets: [
      { id: "hf://PeterJinGo/nq_hotpotqa_train", label: "NQ + HotpotQA Multi-Hop QA", source: "Hugging Face (public)", examples: "169,615 single & multi-hop QA pairs" },
    ],
    primitives: [
      { label: "Environment & Observation", href: "/docs/training/environments/" },
      { label: "GRPO for agents", href: "/docs/training/recipes/rl-agents/" },
      { label: "Custom loops", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import re, httpx
import grad
from grad import Environment, Grad, ModelSpec, Observation, Rubric, RubricTerm

SEARCH_RE = re.compile(r"<search>(.*?)</search>", re.DOTALL)
ANSWER_RE = re.compile(r"<answer>(.*?)</answer>", re.DOTALL)

def exact_match(traj) -> float:
    m = ANSWER_RE.search(traj.output["text"])
    pred = re.sub(r"\\W+", " ", m.group(1).lower()).strip() if m else ""
    gold = re.sub(r"\\W+", " ", traj.metadata["answer"].lower()).strip()
    return 1.0 if pred == gold and bool(gold) else 0.0

class WikiSearchEnv(Environment):
    def __init__(self, retriever_url: str, rubric: Rubric):
        super().__init__(rubric)
        self.http = httpx.Client(base_url=retriever_url, timeout=10.0)

    def step(self, handle, action) -> Observation:
        if ANSWER_RE.search(action.text):
            return Observation(done=True)
        match = SEARCH_RE.search(action.text)
        if not match:
            return Observation(text="\\n<information>Emit <search>query</search> or <answer>...</answer>.</information>\\n", done=False)
        docs = self.http.post("/retrieve", json={"query": match.group(1).strip(), "topk": 3}).json()["docs"]
        formatted = "\\n".join(f"Doc {i + 1}: {d['text']}" for i, d in enumerate(docs))
        return Observation(text=f"\\n<information>\\n{formatted}\\n</information>\\n", done=False)

client = Grad()
env = WikiSearchEnv("http://127.0.0.1:8000", Rubric([RubricTerm("em", 1.0, exact_match)]))

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_qa_batches("hf://PeterJinGo/nq_hotpotqa_train", batch_size=32)):
        groups = env.rollout_groups(
            artifact=trainer.snapshot(), tasks=batch, group_size=8, max_turns=4,
            max_new_tokens=384, stop=["</search>", "</answer>"], max_concurrency=32,
        )
        datums = grad.group_datums(groups, norm="std")

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2, "kl_beta": 0.001})
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        m = fb.result(); opt.result()
        print(f"step={step} datums={len(datums)} kl_st={m.metrics['kl_sample_train']:.5f}")
    artifact = trainer.export(name="search-r1-nq-hotpot", merge_adapter=True)`,
    paperYaml: `slug: search-r1
title: "Search-R1: Multi-Turn Search RL"
arxiv: "https://arxiv.org/abs/2503.09516"
category: agents-tools
public_dataset: "hf://PeterJinGo/nq_hotpotqa_train"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/search-r1 (arXiv:2503.09516)
Dataset   hf://PeterJinGo/nq_hotpotqa_train (169,615 QA tasks · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · group_size=8 · max_turns=4
Loss      grpo (clip=0.2, kl_beta=0.001) · retrieved <information> tokens auto-masked
Estimate  ~8.4M tokens · ~42 min · ~$3.35 · warnings: 0`,
    benchmarks: [
      { benchmark: "7-Dataset QA Average EM", paperReported: "+26% relative EM gain over single-shot RAG and IRCoT on Qwen2.5-7B", templateSetup: "Qwen/Qwen3-8B · group_size=8 · max_turns=4 · topk=3" },
    ],
    bibtex: `@article{jin2025searchr1,
  title={Search-R1: Training LLMs to Reason and Leverage Search Engines with Reinforcement Learning},
  author={Jin, Bowen and others},
  journal={arXiv preprint arXiv:2503.09516},
  year={2025}
}`,
  },
  {
    slug: "score",
    shortTitle: "SCoRe",
    title: "SCoRe: Training LLMs to Self-Correct via Multi-Turn RL",
    authors: "Kumar et al. (Google DeepMind)",
    year: 2024,
    arxivId: "2409.12917",
    arxivUrl: "https://arxiv.org/abs/2409.12917",
    category: "Agents & Tool Use",
    oneLiner:
      "Train genuine intrinsic self-correction without sandbagging Turn 1 by applying turn-dependent KL penalties and a Turn-2 progress bonus across two-turn RL rollouts.",
    story:
      "Naive two-turn self-correction RL suffers an infamous reward hack: if you reward improvement from Turn 1 to Turn 2, the policy intentionally flunks Turn 1 just to harvest the self-correction bonus on Turn 2. SCoRe stops sandbagging cold by decoupling KL regularization per turn.",
    insight:
      "Pin Turn 1 tightly to the reference policy (beta_t1 = 0.20) while giving Turn 2 freedom to adapt (beta_t2 = 0.01), and shape reward as r2 + alpha * (r2 - r1) so Turn 2 genuinely repairs real Turn-1 slips.",
    whyGrad:
      "Artifact.sample(resume_from=t1, append_env_tokens=...) stitches both turns atomically while populating exact per-token turn_ids — letting a 12-line forward_backward_custom loss apply distinct beta_t1 and beta_t2 KL weights.",
    smoothness: {
      rating: "Clean",
      verdict:
        "turn_ids on Datum + resume_from continuation make turn-dependent KL penalties 12 clean lines in forward_backward_custom.",
    },
    walkthrough: [
      { title: "Sample Turn 1 and stitch Turn 2 via resume_from", explanation: "Inject the masked self-correction cue via append_env_tokens so Turn 2 automatically gets turn_ids=1.", gradCall: "snap.sample(..., resume_from=t1, append_env_tokens=[retry_toks])" },
      { title: "Score reference logprobs across both turns at once", explanation: "Pass the stitched Trajectory objects straight to ref.score_logprobs(t2).", gradCall: "ref.score_logprobs(t2)['aligned_logprobs']" },
      { title: "Apply per-turn KL weights using d.model_input.turn_ids", explanation: "Use torch.where(turn_ids == 0, 0.20, 0.01) inside a 12-line surrogate loss.", gradCall: "trainer.forward_backward_custom(datums, ['logprobs'], score_loss)" },
    ],
    gotchas: [
      "Always log Turn-1 accuracy and Turn-2 accuracy separately — Turn-1 must never drop while Turn-2 rises.",
      "Warm up for 50 steps with alpha=0.0 before enabling alpha=2.0 on weaker base models.",
    ],
    linesOfCode: 34,
    typicalBaselineLoc: "~1,400 LOC two-stage multi-turn PPO pipeline",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~7.6M tokens", duration: "~38 min", estCost: "~$3.05" },
    ],
    datasets: [
      { id: "hf://hendrycks/competition_math", label: "MATH Competition Problems", source: "Hugging Face (public)", examples: "7,500 train / 5,000 test" },
    ],
    primitives: [
      { label: "forward_backward_custom", href: "/docs/training/custom-loops/" },
      { label: "Multi-turn per-turn KL", href: "/docs/training/recipes/rl-agents/" },
      { label: "Trajectory turn_ids", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch
import grad
from grad import Grad, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
ref = client.artifacts.get(base_id)
retry_toks = ref.tokenize("\\nReview your previous attempt, fix any mistakes, and write the final boxed answer.\\n")

def score_loss(datums, out, beta_t1=0.20, beta_t2=0.01):
    losses = []
    for lp, old_lp, rlp, adv, mask, tids in zip(
        out["logprobs"], out["sampling_logprobs"], out["ref_logprobs"], out["advantages"], out["masks"], out["turn_ids"],
    ):
        kl_beta = torch.where(tids == 0, beta_t1, beta_t2)
        kl = torch.exp(rlp - lp) - (rlp - lp) - 1.0
        w = torch.exp(lp - old_lp).clamp(0.8, 1.2).detach()
        losses.append(grad.masked_mean(-w * adv * lp + kl_beta * kl, mask))
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_math_batches("hf://hendrycks/competition_math", batch_size=16)):
        snap = trainer.snapshot()
        t1_groups = snap.sample(batch.prompt_inputs, n=4, max_new_tokens=512)
        flat_t1 = [tr for g in t1_groups for tr in g]
        t2_flat = [g[0] for g in snap.sample(resume_from=flat_t1, append_env_tokens=[retry_toks] * len(flat_t1), n=1, max_new_tokens=512)]
        ref_lps = ref.score_logprobs(t2_flat)["aligned_logprobs"]

        t2_groups = [t2_flat[i * 4 : (i + 1) * 4] for i in range(len(batch.answers))]
        rewards = [
            [(r2 := grade_boxed(t2.output["text"], gold)) + 2.0 * (r2 - grade_boxed(t1.output["text"], gold)) for t1, t2 in zip(g1, g2)]
            for g1, g2, gold in zip(t1_groups, t2_groups, batch.answers)
        ]
        datums = grad.group_datums(t2_groups, rewards=rewards, norm="mean", ref_logprobs=ref_lps)
        fb = trainer.forward_backward_custom(datums, outputs=["logprobs"], loss_fn=score_loss)
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        print(f"step={step} score_loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="score-self-correct", merge_adapter=True)`,
    paperYaml: `slug: score
title: "SCoRe: Multi-Turn Self-Correction RL"
arxiv: "https://arxiv.org/abs/2409.12917"
category: agents-tools
public_dataset: "hf://hendrycks/competition_math"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/score (arXiv:2409.12917)
Dataset   hf://hendrycks/competition_math (7,500 train / 5,000 test · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · 2-turn self-correction
Loss      custom per-turn KL (beta_t1=0.20, beta_t2=0.01) + progress bonus
Estimate  ~7.6M tokens · ~38 min · ~$3.05 · warnings: 0`,
    benchmarks: [
      { benchmark: "MATH intrinsic self-correction", paperReported: "+15.6% absolute self-correction gain on MATH without sandbagging", templateSetup: "Qwen/Qwen3-8B · beta_t1=0.20, beta_t2=0.01, alpha=2.0" },
    ],
    bibtex: `@article{kumar2024score,
  title={Training Language Models to Self-Correct via Reinforcement Learning},
  author={Kumar, Aviral and others},
  journal={arXiv preprint arXiv:2409.12917},
  year={2024}
}`,
  },
  {
    slug: "absolute-zero",
    shortTitle: "Absolute Zero",
    title: "Absolute Zero: Reinforced Self-Play Reasoning with Zero Data (AZR)",
    authors: "Zhao et al. (Tsinghua / BIGAI)",
    year: 2025,
    arxivId: "2505.03335",
    arxivUrl: "https://arxiv.org/abs/2505.03335",
    category: "Agents & Tool Use",
    oneLiner:
      "Bootstrap coding and math reasoning from zero human data by having one policy play both Task Proposer and Solver against a deterministic Python executor.",
    story:
      "Even 'zero-SFT' RL runs still depend on tens of thousands of curated human math or coding questions. Absolute Zero threw away the training dataset completely — letting a single model invent its own curriculum of verifiable Python programs and solve them to surpass models trained on curated human datasets.",
    insight:
      "Split one policy into a Proposer (invents deterministic Python puzzles, rewarded with learnability 1 - |2p - 1| peaking at 50% solver pass rate) and a Solver (predicts exact outputs, binary reward), then normalize advantages separately per role (TRR++).",
    whyGrad:
      "One Trainer.snapshot() serves both roles from a single weight version and built-in CISPO accepts the combined per-role normalized batch cleanly — 50 lines, zero external dataset.",
    smoothness: {
      rating: "Clean",
      verdict:
        "One shared Trainer drives both Proposer and Solver cleanly via a single snapshot and built-in CISPO.",
    },
    walkthrough: [
      { title: "Propose executable Python puzzles from the live snapshot", explanation: "Generate candidate (program, input) puzzles and validate determinism in an isolated 2-second Python sandbox.", gradCall: "snap.sample(proposer_prompts, n=1)" },
      { title: "Roll out G=8 Solver attempts per valid puzzle", explanation: "Score solver pass rate p to reward the Proposer with learnability peaking at p=0.5.", gradCall: "snap.sample(solver_prompts, n=8)" },
      { title: "Apply TRR++ per-role advantage normalization", explanation: "Normalize Proposer and Solver advantages independently, concatenate Datums, and step with CISPO.", gradCall: "trainer.forward_backward(prop_ds + sol_ds, loss={'kind': 'cispo'})" },
    ],
    gotchas: [
      "Block random, time, network, and disk writes inside the sandbox — non-deterministic proposals inject unlearnable noise.",
      "Seed the buffer with 4–8 minimal Python functions on step 0 so early proposals stay diverse.",
    ],
    linesOfCode: 37,
    typicalBaselineLoc: "~2,600 LOC multi-role Ray + sandboxed code-RL stack",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~9.0M tokens", duration: "~45 min", estCost: "~$3.60" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", estTokens: "~6.4M tokens", duration: "~20 min", estCost: "~$1.60" },
    ],
    datasets: [
      { id: "synthetic://azr-zero-data", label: "Zero Human Data (Self-Generated Python Buffer)", source: "Generated online by policy + sandbox", examples: "0 static rows (infinite self-play)" },
    ],
    primitives: [
      { label: "Trainer & snapshot()", href: "/docs/training/custom-loops/" },
      { label: "CISPO loss", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import grad
from grad import Grad, ModelInput, ModelSpec

client = Grad()
task_buffer = [("def f(x): return sum(i * i for i in range(x))", "5", "30")]

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step in range(200):
        snap = trainer.snapshot()
        prop_inputs = [ModelInput(messages=build_proposer_prompt(task_buffer)) for _ in range(16)]
        proposals = [g[0] for g in snap.sample(prop_inputs, n=1, temperature=1.0, max_new_tokens=384)]

        valid_props, solver_inputs, golds = [], [], []
        for p in proposals:
            parsed = run_sandboxed_python(p.output["text"], timeout_s=2.0)
            if parsed is None:
                p.scores["reward"] = -1.0
                continue
            code, inp, out = parsed
            valid_props.append(p); golds.append((code, inp, out))
            solver_inputs.append(ModelInput(messages=build_solver_prompt(code, inp)))

        solver_trajs = []
        if solver_inputs:
            for p, grp, (code, inp, gold) in zip(valid_props, snap.sample(solver_inputs, n=8, max_new_tokens=512), golds):
                passes = [1.0 if extract_output(s.output["text"]) == gold else 0.0 for s in grp]
                rate = sum(passes) / len(passes)
                p.scores["reward"] = 0.0 if rate in (0.0, 1.0) else 1.0 - abs(2.0 * rate - 1.0)
                if 0.0 < rate < 1.0:
                    task_buffer.append((code, inp, gold))
                for s, r in zip(grp, passes):
                    s.scores["reward"] = r; solver_trajs.append(s)

        # TRR++ per-role advantage normalization via grad.group_datums
        datums = grad.group_datums([proposals], norm="std") + grad.group_datums([solver_trajs], norm="std")
        fb = trainer.forward_backward(datums, loss={"kind": "cispo", "clip_low": 0.2, "clip_high": 0.2})
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        print(f"step={step} valid={len(valid_props)}/16 buf={len(task_buffer)} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="azr-zero-data-8b", merge_adapter=True)`,
    paperYaml: `slug: absolute-zero
title: "Absolute Zero (AZR) Zero-Data Self-Play"
arxiv: "https://arxiv.org/abs/2505.03335"
category: agents-tools
public_dataset: "synthetic://azr-zero-data"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/absolute-zero (arXiv:2505.03335)
Dataset   synthetic://azr-zero-data (self-play Python buffer · 0 static rows)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · dual-role Proposer + Solver
Loss      cispo with TRR++ per-role advantage normalization
Estimate  ~9.0M tokens · ~45 min · ~$3.60 · warnings: 0`,
    benchmarks: [
      { benchmark: "Coding + Math Average (Zero Human Data)", paperReported: "50.4% avg on Qwen2.5-7B-Coder, surpassing RLVR models trained on 50k+ human tasks", templateSetup: "Qwen/Qwen3-8B · 16 proposals x 8 solver rollouts · Python sandbox" },
    ],
    bibtex: `@article{zhao2025absolutezero,
  title={Absolute Zero: Reinforced Self-Play Reasoning with Zero Data},
  author={Zhao, Andrew and others},
  journal={arXiv preprint arXiv:2505.03335},
  year={2025}
}`,
  },
  {
    slug: "archer",
    shortTitle: "ArCHer",
    title: "ArCHer: Hierarchical Multi-Turn RL for Language Agents",
    authors: "Zhou et al. (UC Berkeley)",
    year: 2024,
    arxivId: "2402.19446",
    arxivUrl: "https://arxiv.org/abs/2402.19446",
    category: "Agents & Tool Use",
    oneLiner:
      "Make multi-turn agent RL 10x more sample-efficient by separating an off-policy utterance-level Q/V critic from a token-level actor.",
    story:
      "Flat on-policy PPO throws away every expensive multi-turn episode after one update and struggles to assign credit across 6 turns. ArCHer separates timescales: treat each entire agent utterance as one action in a short 6-step off-policy MDP for the critic, then pass turn-level advantages down to the token-level actor.",
    insight:
      "Train a dual-head (Q, V) utterance critic off-policy from a replay buffer via expectile IQL + Bellman TD backups, then broadcast A_t = Q(s_t, u_t) - V(s_t) onto turn t's tokens for the actor's CISPO update.",
    whyGrad:
      "Two side-by-side Trainers (LoRA actor + small dual-head q/v critic) plus critic.snapshot().infer_batch() run full hierarchical off-policy agent RL in ~55 lines.",
    smoothness: {
      rating: "Custom head / loop",
      verdict:
        "Dual (q, v) heads and two Trainers compose cleanly without distributed actor-critic glue.",
    },
    walkthrough: [
      { title: "Open an Actor Trainer and a dual-head (q, v) Critic Trainer", explanation: "Use a compact 0.6B backbone for the utterance critic so off-policy Bellman steps are fast.", gradCall: "ModelSpec(base='Qwen/Qwen3-0.6B', heads={'q': {'dim': 1}, 'v': {'dim': 1}})" },
      { title: "Train Critic off-policy via IQL expectile + Bellman TD", explanation: "Sample utterance transitions from a replay deque and run 2 critic steps per actor step.", gradCall: "critic.forward_backward_custom(c_datums, ['heads'], archer_critic_loss)" },
      { title: "Broadcast utterance advantages A_t = Q - V to the token Actor", explanation: "Attach A_t to turn t's generated tokens and update the actor with CISPO.", gradCall: "actor.forward_backward(actor_datums, loss={'kind': 'cispo'})" },
    ],
    gotchas: [
      "Clip utterance advantages to [-5, 5] so early Bellman bootstrap errors don't destabilize the token actor.",
      "Keep expectile tau in [0.7, 0.8] so V tracks optimistic high-reward actions rather than average behavior.",
    ],
    linesOfCode: 54,
    typicalBaselineLoc: "~2,200 LOC custom hierarchical IQL + PPO trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B Actor + 0.6B Critic", estTokens: "~10.8M tokens", duration: "~34 min", estCost: "~$2.70" },
    ],
    datasets: [
      { id: "hf://gradiated/archer-twenty-questions", label: "Twenty Questions & Interactive Tasks", source: "Hugging Face (public)", examples: "2,000 multi-turn episodes" },
    ],
    primitives: [
      { label: "Multi-head ModelSpec", href: "/docs/reference/primitives/" },
      { label: "Stateful Environment", href: "/docs/training/environments/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from collections import deque
import random, torch, torch.nn.functional as F
from grad import Datum, DatumTargets, Grad, ModelInput, ModelSpec

client = Grad()
replay = deque(maxlen=4096)

def archer_critic_loss(datums, out, tau=0.75):
    losses = []
    for d, q_pred, v_pred in zip(datums, out["heads"]["q"], out["heads"]["v"]):
        q_loss = F.mse_loss(q_pred.squeeze(), torch.tensor(d.targets.scalar, dtype=torch.float32))
        diff = q_pred.squeeze().detach() - v_pred.squeeze()
        v_loss = (torch.where(diff > 0, tau, 1.0 - tau) * diff.pow(2)).mean()
        losses.append(q_loss + v_loss)
    return torch.stack(losses).mean()

with (
    client.trainers.create(ModelSpec(base="Qwen/Qwen3-4B", adapter="lora", train_mode="lora"), compute="gpu") as actor,
    client.trainers.create(ModelSpec(base="Qwen/Qwen3-0.6B", adapter="lora", train_mode="lora", heads={"q": {"dim": 1}, "v": {"dim": 1}}), compute="gpu") as critic,
):
    for step, tasks in enumerate(load_interactive_tasks("hf://gradiated/archer-twenty-questions", batch_size=16)):
        groups = env.rollout_groups(actor.snapshot(), tasks, group_size=2, max_turns=6, max_new_tokens=128)
        for tr in [t for g in groups for t in g]:
            replay.extend(split_utterance_transitions(tr))

        # 1. Off-policy Critic Bellman TD + IQL steps
        c_snap = critic.snapshot()
        for _ in range(2):
            mb = random.sample(replay, min(64, len(replay)))
            next_v = c_snap.infer_batch([ModelInput(tokens=x.next_state_toks) for x in mb])
            c_ds = [Datum(ModelInput(tokens=x.state_utt_toks), DatumTargets(scalar=x.r_t + (0.0 if x.done else 0.95 * float(nv["heads"]["v"])))) for x, nv in zip(mb, next_v)]
            c_fb = critic.forward_backward_custom(c_ds, outputs=["heads"], loss_fn=archer_critic_loss)
            critic.optim_step(lr=5e-5, grad_clip=1.0).result()

        # 2. Token-level Actor CISPO step using utterance advantages A_t = Q - V
        c_snap = critic.snapshot()
        a_ds = []
        for tr in [t for g in groups for t in g]:
            turns = split_utterance_transitions(tr)
            qs = [float(o["heads"]["q"]) for o in c_snap.infer_batch([ModelInput(tokens=x.state_utt_toks) for x in turns])]
            vs = [float(o["heads"]["v"]) for o in c_snap.infer_batch([ModelInput(tokens=x.state_toks) for x in turns])]
            a_ds.append(tr.to_datum(advantages=broadcast_turn_advantages(tr, [max(-5.0, min(5.0, q - v)) for q, v in zip(qs, vs)])))

        a_fb = actor.forward_backward(a_ds, loss={"kind": "cispo", "clip_low": 0.2, "clip_high": 0.2})
        actor.optim_step(lr=1e-5, grad_clip=1.0).result()
        print(f"step={step} critic={c_fb.result().loss:.4f} actor={a_fb.result().loss:.4f}")
    artifact = actor.export(name="archer-agent-4b", merge_adapter=True)`,
    paperYaml: `slug: archer
title: "ArCHer: Hierarchical Multi-Turn RL"
arxiv: "https://arxiv.org/abs/2402.19446"
category: agents-tools
public_dataset: "hf://gradiated/archer-twenty-questions"
base_default: "Qwen/Qwen3-4B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/archer (arXiv:2402.19446)
Dataset   hf://gradiated/archer-twenty-questions (2,000 multi-turn tasks · public)
Model     Actor Qwen/Qwen3-4B + Critic Qwen/Qwen3-0.6B (heads: q, v)
Loss      Critic expectile-IQL Bellman TD + Actor CISPO
Estimate  ~6.8M tokens · ~34 min · ~$2.70 · warnings: 0`,
    benchmarks: [
      { benchmark: "Multi-turn sample efficiency", paperReported: "~100x fewer environment steps than flat on-policy PPO on 20 Questions & WebShop", templateSetup: "Qwen/Qwen3-4B actor + 0.6B critic · replay=4,096" },
    ],
    bibtex: `@inproceedings{zhou2024archer,
  title={ArCHer: Training Language Model Agents via Hierarchical Multi-Turn RL},
  author={Zhou, Yifei and others},
  booktitle={ICML},
  year={2024}
}`,
  },
  {
    slug: "toolformer",
    shortTitle: "Toolformer",
    title: "Toolformer: Language Models Can Teach Themselves to Use Tools",
    authors: "Schick et al. (Meta AI)",
    year: 2023,
    arxivId: "2302.04761",
    arxivUrl: "https://arxiv.org/abs/2302.04761",
    category: "Agents & Tool Use",
    oneLiner:
      "Bootstrap API-calling skills from raw unlabeled text by executing model-proposed tool calls and keeping only calls that lower perplexity on future tokens.",
    story:
      "Hiring humans to annotate thousands of tool-use dialogues breaks every time an API changes. Toolformer showed an LLM can bootstrap its own tool dataset from plain Wikipedia text by keeping only those self-proposed API calls whose executed result genuinely reduces cross-entropy on the rest of the sentence.",
    insight:
      "Score continuation tokens under three prefixes via score_logprobs — no call (L_none), empty call (L_empty), and executed call (L_result) — keep insertions where min(L_none, L_empty) - L_result > tau, and run masked SFT.",
    whyGrad:
      "Batched base.score_logprobs(prefix_tokens, response_tokens) scores all three prefixes cleanly on the exact same continuation slice, making the full self-supervised filter + SFT loop 42 lines.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Batched split-prefix score_logprobs() + standard cross_entropy SFT implement Toolformer with zero custom loss code.",
    },
    walkthrough: [
      { title: "Sample & execute candidate tool insertions on raw text", explanation: "Generate candidate [Calculator(...)] calls and run them in a safe Python executor.", gradCall: "base.sample(prompts, n=4, stop=[')'])" },
      { title: "Filter by exact future-token NLL reduction", explanation: "Score continuation logprobs under no-call, empty-call, and executed-call prefixes; keep only calls beating tau=0.15.", gradCall: "base.score_logprobs(prefixes, conts)['response_logprobs']" },
      { title: "Fine-tune with masked tool-result tokens", explanation: "Set loss_mask=0.0 on externally returned tool outputs so the model trains on calls and synthesis.", gradCall: "trainer.forward_backward(kept_datums, loss={'kind': 'cross_entropy'})" },
    ],
    gotchas: [
      "Always compare against min(L_none, L_empty) so spurious formatting changes don't pass the filter.",
      "Mix 50% plain unaugmented text into SFT so the model doesn't over-trigger tools on simple prose.",
    ],
    linesOfCode: 42,
    typicalBaselineLoc: "~1,300 LOC custom multi-pass scoring & filtering pipeline",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~4.4M tokens", duration: "~22 min", estCost: "~$1.75" },
    ],
    datasets: [
      { id: "hf://wikimedia/wikipedia", label: "Wikipedia Raw Text (subset)", source: "Hugging Face (public)", examples: "25,000 unlabeled passages" },
    ],
    primitives: [
      { label: "Artifact.score_logprobs", href: "/docs/reference/primitives/" },
      { label: "SFT custom loop", href: "/docs/training/custom-loops/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Datum, DatumTargets, Grad, ModelInput, ModelSpec

client = Grad()
base_id = "Qwen/Qwen3-8B"
base = client.artifacts.get(base_id)

def weighted_nll(lps: list[float]) -> float:
    ws = [max(0.0, 1.0 - 0.2 * t) for t in range(len(lps))]
    return -sum(w * lp for w, lp in zip(ws, lps)) / max(sum(ws), 1e-6)

candidates = []
for doc in load_unlabeled_passages("hf://wikimedia/wikipedia", limit=4000):
    for prop in base.sample([ModelInput(text=build_tool_proposal_prompt(doc))], n=4, max_new_tokens=48, stop=[")"])[0]:
        parsed = split_and_execute_tool(doc, prop.output["text"])
        if parsed is not None:
            p, cl, res, cont = parsed
            candidates.append((base.tokenize(p), base.tokenize(f"[{cl}"), base.tokenize(f" -> {res}]"), base.tokenize(cont)[:32]))

conts = [c for _, _, _, c in candidates]
lp_none = base.score_logprobs([p for p, _, _, _ in candidates], conts)["response_logprobs"]
lp_empty = base.score_logprobs([p + cl + base.tokenize("]") for p, cl, _, _ in candidates], conts)["response_logprobs"]
lp_res = base.score_logprobs([p + cl + r for p, cl, r, _ in candidates], conts)["response_logprobs"]

kept = []
for (p, cl, r, c), l0, le, lr_ in zip(candidates, lp_none, lp_empty, lp_res):
    if min(weighted_nll(l0), weighted_nll(le)) - weighted_nll(lr_) > 0.15:
        mask = [1.0] * len(p) + [1.0] * len(cl) + [0.0] * len(r) + [1.0] * len(c)
        kept.append(Datum(ModelInput(tokens=p + cl + r + c), DatumTargets(loss_mask=mask)))

with client.trainers.create(
    ModelSpec(base=base_id, adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, mb in enumerate(chunk(kept, batch_size=32)):
        fb = trainer.forward_backward(mb, loss={"kind": "cross_entropy"})
        opt = trainer.optim_step(lr=1e-4, grad_clip=1.0)
        print(f"step={step} nll={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="toolformer-8b", merge_adapter=True)`,
    paperYaml: `slug: toolformer
title: "Toolformer: Self-Supervised Tool Use"
arxiv: "https://arxiv.org/abs/2302.04761"
category: agents-tools
public_dataset: "hf://wikimedia/wikipedia"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/toolformer (arXiv:2302.04761)
Dataset   hf://wikimedia/wikipedia (4,000 unlabeled passages · public)
Model     Qwen/Qwen3-8B · self-filtered tool SFT (tau_f=0.15)
Loss      cross_entropy (tool return tokens masked to 0.0)
Estimate  ~4.4M tokens · ~22 min · ~$1.75 · warnings: 0`,
    benchmarks: [
      { benchmark: "Zero-shot arithmetic & QA", paperReported: "6.7B Toolformer beats 175B GPT-3 on ASDiv, SVAMP, and WebQS via self-learned APIs", templateSetup: "Wikipedia subset · Qwen/Qwen3-8B · tau_f=0.15" },
    ],
    bibtex: `@inproceedings{schick2023toolformer,
  title={Toolformer: Language Models Can Teach Themselves to Use Tools},
  author={Schick, Timo and others},
  booktitle={NeurIPS},
  year={2023}
}`,
  },
  {
    slug: "spiral",
    shortTitle: "SPIRAL",
    title: "SPIRAL: Self-Play on Zero-Sum Games Incentivizes Reasoning",
    authors: "Liu et al. (Sea AI Lab)",
    year: 2025,
    arxivId: "2506.24119",
    arxivUrl: "https://arxiv.org/abs/2506.24119",
    category: "Agents & Tool Use",
    oneLiner:
      "Train multi-turn strategic reasoning with zero external labels by pitting a model against itself in zero-sum games (Kuhn Poker, Tic-Tac-Toe) using Role-Conditioned Advantage Estimation.",
    story:
      "Supervised math datasets eventually saturate and teach narrow pattern matching. SPIRAL showed that playing zero-sum multi-turn games against yourself — where every win by Player 0 is a loss by Player 1 — creates an automatically escalating opponent curriculum that transfers surprisingly strongly to general math and logic benchmarks.",
    insight:
      "Run self-play episodes where snap plays both Player 0 and Player 1; track separate running baselines b_0 and b_1 per seat (Role-Conditioned Advantage Estimation, RAE) so first-mover advantage doesn't skew gradients, and update the shared policy on both players' trajectories.",
    whyGrad:
      "Both players sample from the same trainer.snapshot() with opponent moves injected via append_env_tokens (loss_mask=0.0), and both trajectories update the same Trainer via built-in CISPO.",
    smoothness: {
      rating: "Clean",
      verdict:
        "Self-play multi-agent episodes require zero special multi-agent coordinator framework — just two Trajectory objects updated on one Trainer.",
    },
    walkthrough: [
      { title: "Play two-player zero-sum episodes from one snapshot", explanation: "Alternate Player 0 and Player 1 moves using trainer.snapshot().sample(); inject opponent moves into each player's trajectory with loss_mask=0.0.", gradCall: "play_zero_sum_game(snap, game)" },
      { title: "Compute Role-Conditioned Advantages (RAE)", explanation: "Normalize Player 0 and Player 1 returns against separate per-seat baselines to cancel first-player bias.", gradCall: "adv = r - seat_baseline[player_id]" },
      { title: "Update the shared policy jointly on both seats", explanation: "Feed both players' Datums into built-in CISPO and export the improved reasoning model.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'cispo'})" },
    ],
    gotchas: [
      "Keep a small pool (20%) of older historical snapshots as opponents to prevent cyclic rock-paper-scissors forgetting.",
      "Assign an immediate -1.0 penalty and terminate the episode on illegal moves so the model learns valid game syntax within the first 10 steps.",
    ],
    linesOfCode: 40,
    typicalBaselineLoc: "~1,700 LOC multi-agent game coordinator + RL trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~7.1M tokens", duration: "~36 min", estCost: "~$2.85" },
      { id: "Qwen/Qwen3-4B", label: "Qwen/Qwen3-4B (fast smoke run)", estTokens: "~5.2M tokens", duration: "~16 min", estCost: "~$1.30" },
    ],
    datasets: [
      { id: "synthetic://spiral-zero-sum", label: "Zero-Sum Game Suite (Kuhn Poker / Tic-Tac-Toe)", source: "Deterministic Python game simulators", examples: "Unlimited self-play episodes" },
    ],
    primitives: [
      { label: "Trainer & snapshot()", href: "/docs/training/custom-loops/" },
      { label: "Multi-turn Environments", href: "/docs/training/environments/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Grad, ModelSpec

client = Grad()
seat_baseline = {0: 0.0, 1: 0.0}  # Role-Conditioned Advantage Estimation (RAE)

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step in range(200):
        snap = trainer.snapshot()
        # Play 32 zero-sum games (Kuhn Poker / Tic-Tac-Toe); returns (p0_traj, p1_traj, r0, r1)
        episodes = [play_zero_sum_game(snap, seed=step * 32 + i) for i in range(32)]

        datums = []
        r0s = [ep.r0 for ep in episodes]
        r1s = [ep.r1 for ep in episodes]
        # Update EMA seat baselines so first-player advantage never biases gradients
        seat_baseline[0] = 0.9 * seat_baseline[0] + 0.1 * (sum(r0s) / len(r0s))
        seat_baseline[1] = 0.9 * seat_baseline[1] + 0.1 * (sum(r1s) / len(r1s))

        for ep in episodes:
            datums.append(ep.p0_traj.to_datum(advantage=ep.r0 - seat_baseline[0]))
            datums.append(ep.p1_traj.to_datum(advantage=ep.r1 - seat_baseline[1]))

        fb = trainer.forward_backward(datums, loss={"kind": "cispo", "clip_low": 0.2, "clip_high": 0.2})
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        print(f"step={step} b0={seat_baseline[0]:+.2f} b1={seat_baseline[1]:+.2f} loss={fb.result().loss:.4f}")
        opt.result()
    artifact = trainer.export(name="spiral-selfplay-8b", merge_adapter=True)`,
    paperYaml: `slug: spiral
title: "SPIRAL: Zero-Sum Self-Play RL"
arxiv: "https://arxiv.org/abs/2506.24119"
category: agents-tools
public_dataset: "synthetic://spiral-zero-sum"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/spiral (arXiv:2506.24119)
Dataset   synthetic://spiral-zero-sum (Kuhn Poker + Tic-Tac-Toe self-play)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · RAE per-seat baselines
Loss      cispo over both seats' masked trajectories
Estimate  ~7.1M tokens · ~36 min · ~$2.85 · warnings: 0`,
    benchmarks: [
      { benchmark: "Zero-shot transfer to MATH / GPQA", paperReported: "+8.6% math & +8.4% general reasoning gain purely from zero-sum game self-play", templateSetup: "Qwen/Qwen3-8B · 32 games/step · RAE baselines" },
    ],
    bibtex: `@article{liu2025spiral,
  title={SPIRAL: Self-Play on Zero-Sum Games Incentivizes Reasoning via Multi-Agent Multi-Turn Reinforcement Learning},
  author={Liu, Bo and others},
  journal={arXiv preprint arXiv:2506.24119},
  year={2025}
}`,
  },
];
