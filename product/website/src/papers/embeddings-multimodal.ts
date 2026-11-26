import type { PaperGuide } from "./types";

export const embeddingsMultimodalPapers: PaperGuide[] = [
  {
    slug: "matryoshka-colbert",
    shortTitle: "Matryoshka + ColBERT",
    title: "Matryoshka Representation Learning + ColBERT Multi-Vector Retrieval",
    authors: "Kusupati et al. / Khattab & Zaharia",
    year: 2022,
    arxivId: "2205.13147",
    arxivUrl: "https://arxiv.org/abs/2205.13147",
    category: "Embeddings, Calibration & Multimodal",
    oneLiner:
      "Train one retriever that supports both ultra-compact truncated dense vectors (64/128/256d) for fast ANN recall and full ColBERT token-level MaxSim reranking.",
    story:
      "Production retrieval stacks normally juggle two separate encoders: a cheap single-vector bi-encoder for vector-DB search and an expensive cross-encoder or ColBERT index for fine-grained token matching. Combining Matryoshka nested prefixes with ColBERT MaxSim trains a single encoder whose first 128 floats do fast coarse recall and whose full token vectors do exact late-interaction reranking.",
    insight:
      "Set pool='none' so the encoder outputs full per-token embeddings (L, D). Sum InfoNCE across truncated mean-pooled prefixes (128, 256, 384d) AND ColBERT token-level MaxSim sum_i max_j (q_i · d_j) in one joint backward pass.",
    whyGrad:
      "pool='none' returns full (L, D) token embeddings in forward_backward_custom, and at serving time Artifact.embed(pool='mean') or embed(pool='none') switches retrieval mode per request with zero re-export.",
    smoothness: {
      rating: "Clean",
      verdict:
        "pool='none' + 14-line joint Matryoshka/ColBERT loss in forward_backward_custom handles both coarse and late-interaction retrieval cleanly.",
    },
    walkthrough: [
      { title: "Configure ModelSpec with pool='none'", explanation: "Receive full (L, D) per-token representations instead of a single pooled vector.", gradCall: "ModelSpec(..., pool='none')" },
      { title: "Sum Matryoshka prefix InfoNCE + ColBERT MaxSim", explanation: "Optimize nested dimensions (128, 256, 384) jointly with token-level MaxSim.", gradCall: "trainer.forward_backward_custom(batch, outputs=['embeddings'], loss_fn=mrl_colbert_loss)" },
      { title: "Override pool per call at serving time", explanation: "Call embed(pool='mean')[:128] for fast vector search and embed(pool='none') for ColBERT reranking.", gradCall: "art.embed(inputs, pool='none')['embeddings']" },
    ],
    gotchas: [
      "L2-normalize every truncated Matryoshka prefix independently before dot products — normalizing only the full vector biases smaller slices.",
      "Mine hard negatives periodically with trainer.snapshot().embed() for +8–15 pts Recall@10.",
    ],
    linesOfCode: 31,
    typicalBaselineLoc: "~1,100 LOC custom ColBERT + MRL trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "BAAI/bge-small-en-v1.5", label: "BAAI/bge-small-en-v1.5 (fast, 384d)", estTokens: "~2.6M tokens", duration: "~8 min", estCost: "~$0.65" },
      { id: "BAAI/bge-base-en-v1.5", label: "BAAI/bge-base-en-v1.5 (768d)", estTokens: "~2.8M tokens", duration: "~14 min", estCost: "~$1.10" },
    ],
    datasets: [
      { id: "hf://sentence-transformers/msmarco-bm25", label: "MS MARCO Hard-Negative Triplets", source: "Hugging Face (public)", examples: "500k (query, pos, neg) triplets" },
    ],
    primitives: [
      { label: "Embeddings & rerankers guide", href: "/docs/training/recipes/embeddings/" },
      { label: "pool='none' token embeddings", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
import grad
from grad import Grad, ModelSpec

client = Grad()

def mrl_colbert_loss(datums, out, dims=(128, 256, 384)):
    losses = []
    for g in grad.by_group(datums, out):
        q_tok, p_tok, n_tok = g["anchor"].embeddings, g["positive"].embeddings, g["negative"].embeddings
        qm, pm, nm = q_tok.mean(0), p_tok.mean(0), n_tok.mean(0)
        # 1. Matryoshka nested-prefix dense InfoNCE
        mrl = sum(
            F.cross_entropy(torch.stack([
                F.normalize(qm[:d], dim=-1) @ F.normalize(pm[:d], dim=-1),
                F.normalize(qm[:d], dim=-1) @ F.normalize(nm[:d], dim=-1),
            ]).unsqueeze(0) / 0.05, torch.tensor([0]))
            for d in dims
        ) / len(dims)
        # 2. ColBERT token-level MaxSim late interaction
        qc, pc, nc = F.normalize(q_tok, dim=-1), F.normalize(p_tok, dim=-1), F.normalize(n_tok, dim=-1)
        s_pos, s_neg = (qc @ pc.T).max(dim=-1).values.sum(), (qc @ nc.T).max(dim=-1).values.sum()
        colbert = F.cross_entropy(torch.stack([s_pos, s_neg]).unsqueeze(0) / 0.1, torch.tensor([0]))
        losses.append(mrl + colbert)
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="BAAI/bge-small-en-v1.5", adapter="full", train_mode="full", pool="none"),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_triplet_batches("hf://sentence-transformers/msmarco-bm25", batch_size=32)):
        fb = trainer.forward_backward_custom(batch, outputs=["embeddings"], loss_fn=mrl_colbert_loss)
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} mrl_colbert={fb.result().loss:.4f}"); opt.result()
    retriever = trainer.export(name="mrl-colbert-retriever")`,
    paperYaml: `slug: matryoshka-colbert
title: "Matryoshka + ColBERT Retrieval"
arxiv: "https://arxiv.org/abs/2205.13147"
category: embeddings
public_dataset: "hf://sentence-transformers/msmarco-bm25"
base_default: "BAAI/bge-small-en-v1.5"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/matryoshka-colbert (arXiv:2205.13147)
Dataset   hf://sentence-transformers/msmarco-bm25 (triplets · public)
Model     BAAI/bge-small-en-v1.5 · pool=none (MRL 128/256/384d + ColBERT)
Loss      custom mrl_colbert_loss
Estimate  ~1.6M tokens · ~8 min · ~$0.65 · warnings: 0`,
    benchmarks: [
      { benchmark: "Storage vs. Recall@10", paperReported: "Up to 14x smaller vector index at 64–128d with ColBERT reranking recovering full precision", templateSetup: "MS MARCO triplets · BGE-small · dims=(128,256,384)" },
    ],
    bibtex: `@inproceedings{kusupati2022matryoshka,
  title={Matryoshka Representation Learning},
  author={Kusupati, Aditya and others},
  booktitle={NeurIPS},
  year={2022}
}`,
  },
  {
    slug: "bge-m3",
    shortTitle: "BGE-M3",
    title: "BGE-M3: Joint Dense, Lexical Sparse (SPLADE), and Multi-Vector Retrieval",
    authors: "Chen et al. (BAAI)",
    year: 2024,
    arxivId: "2402.03216",
    arxivUrl: "https://arxiv.org/abs/2402.03216",
    category: "Embeddings, Calibration & Multimodal",
    oneLiner:
      "Unify dense bi-encoder, learned lexical sparse weights (BM25/SPLADE-style), and ColBERT multi-vector retrieval inside one self-distilled model.",
    story:
      "Hybrid search beats pure dense retrieval on jargon, SKUs, and exact identifiers — but maintaining separate BM25, dense, and ColBERT pipelines doubles operational complexity. BGE-M3 trains all three retrieval heads jointly on one encoder and uses their ensemble score as an online self-distillation teacher.",
    insight:
      "Combine pooled dense cosine, token-level ColBERT MaxSim, and a token-level scalar lexical weight head (ReLU(W_lex h_t) + FLOPS sparsity penalty) in one forward pass, plus KL self-distillation from the ensemble score back into each individual head.",
    whyGrad:
      "pool='none' + heads={'lex': {'dim': 1, 'token_level': True}} exposes both token embeddings and per-token lexical weights simultaneously inside forward_backward_custom.",
    smoothness: {
      rating: "Custom head / loop",
      verdict:
        "Tri-objective hybrid retrieval (dense + ColBERT + lexical head with FLOPS regularization) fits in 38 lines.",
    },
    walkthrough: [
      { title: "Attach a token-level lexical importance head", explanation: "Add heads={'lex': {'dim': 1, 'token_level': True}} alongside pool='none' token embeddings.", gradCall: "ModelSpec(..., pool='none', heads={'lex': {'dim': 1, 'token_level': True}})" },
      { title: "Compute Dense + ColBERT + Lexical scores jointly", explanation: "Score triplets on all three retrieval modalities plus a FLOPS L1 sparsity regularizer on lexical weights.", gradCall: "trainer.forward_backward_custom(batch, outputs=['embeddings', 'heads'], loss_fn=bge_m3_loss)" },
      { title: "Self-distill from the combined ensemble score", explanation: "Match each modality's distribution to the detached ensemble score for free accuracy gains.", gradCall: "F.kl_div(..., target=ensemble.detach())" },
    ],
    gotchas: [
      "Include a small L1/FLOPS sparsity weight (1e-4) on ReLU(lex_weights) so lexical weights stay sparse and fast to invert.",
      "Normalize lexical scores by query length so long queries don't drown out dense cosine scores in the ensemble.",
    ],
    linesOfCode: 36,
    typicalBaselineLoc: "~1,600 LOC FlagEmbedding BGE-M3 trainer",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "BAAI/bge-m3", label: "BAAI/bge-m3 (recommended, 8k multilingual)", estTokens: "~3.6M tokens", duration: "~18 min", estCost: "~$1.45" },
      { id: "BAAI/bge-small-en-v1.5", label: "BAAI/bge-small-en-v1.5 (fast smoke run)", estTokens: "~2.6M tokens", duration: "~8 min", estCost: "~$0.65" },
    ],
    datasets: [
      { id: "hf://sentence-transformers/msmarco-bm25", label: "MS MARCO Hard Negatives", source: "Hugging Face (public)", examples: "500k (query, pos, neg) triplets" },
    ],
    primitives: [
      { label: "Embeddings & rerankers", href: "/docs/training/recipes/embeddings/" },
      { label: "Multi-head ModelSpec", href: "/docs/reference/primitives/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import torch, torch.nn.functional as F
import grad
from grad import Grad, ModelSpec

client = Grad()

def _lexical_score(q_toks, q_w, d_toks, d_w):
    q_map, d_map = {}, {}
    for t, w in zip(q_toks, F.relu(q_w[:, 0])):
        q_map[t] = torch.maximum(q_map.get(t, w * 0.0), w)
    for t, w in zip(d_toks, F.relu(d_w[:, 0])):
        d_map[t] = torch.maximum(d_map.get(t, w * 0.0), w)
    return sum((q_map[t] * d_map[t] for t in q_map if t in d_map), torch.tensor(0.0))

def bge_m3_loss(datums, out, temp=0.05):
    losses = []
    for g in grad.by_group(datums, out):
        a, p, n = g["anchor"], g["positive"], g["negative"]
        # 1. Dense cosine + 2. ColBERT MaxSim + 3. Lexical sparse score
        s_dense = torch.stack([F.normalize(a.embeddings.mean(0), dim=-1) @ F.normalize(p.embeddings.mean(0), dim=-1), F.normalize(a.embeddings.mean(0), dim=-1) @ F.normalize(n.embeddings.mean(0), dim=-1)]) / temp
        qc, pc, nc = F.normalize(a.embeddings, dim=-1), F.normalize(p.embeddings, dim=-1), F.normalize(n.embeddings, dim=-1)
        s_col = torch.stack([(qc @ pc.T).max(-1).values.mean(), (qc @ nc.T).max(-1).values.mean()]) / temp
        s_lex = torch.stack([_lexical_score(a.datum.model_input.tokens, a.heads["lex"], p.datum.model_input.tokens, p.heads["lex"]), _lexical_score(a.datum.model_input.tokens, a.heads["lex"], n.datum.model_input.tokens, n.heads["lex"])])
        ens_p = F.softmax((s_dense + s_col + s_lex).detach() / 3.0, dim=-1)
        ce = sum(F.cross_entropy(s.unsqueeze(0), torch.tensor([0])) + F.kl_div(F.log_softmax(s, dim=-1), ens_p, reduction="sum") for s in (s_dense, s_col, s_lex))
        sparsity = 1e-4 * sum(F.relu(v.heads["lex"]).mean() for v in (a, p, n))
        losses.append(ce / 3.0 + sparsity)
    return torch.stack(losses).mean()

with client.trainers.create(
    ModelSpec(base="BAAI/bge-m3", adapter="lora", train_mode="lora", pool="none", heads={"lex": {"dim": 1, "token_level": True}}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_triplet_batches("hf://sentence-transformers/msmarco-bm25", batch_size=16)):
        fb = trainer.forward_backward_custom(batch, outputs=["embeddings", "heads"], loss_fn=bge_m3_loss)
        opt = trainer.optim_step(lr=3e-5, grad_clip=1.0)
        print(f"step={step} bge_m3={fb.result().loss:.4f}"); opt.result()
    hybrid = trainer.export(name="bge-m3-hybrid", merge_adapter=True)`,
    paperYaml: `slug: bge-m3
title: "BGE-M3 Hybrid Retrieval"
arxiv: "https://arxiv.org/abs/2402.03216"
category: embeddings
public_dataset: "hf://sentence-transformers/msmarco-bm25"
base_default: "BAAI/bge-m3"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/bge-m3 (arXiv:2402.03216)
Dataset   hf://sentence-transformers/msmarco-bm25 (triplets · public)
Model     BAAI/bge-m3 · pool=none + token_level head 'lex'
Loss      custom tri-objective (dense + ColBERT + lexical + self-distillation)
Estimate  ~3.6M tokens · ~18 min · ~$1.45 · warnings: 0`,
    benchmarks: [
      { benchmark: "MIRACL & BEIR Hybrid nDCG@10", paperReported: "Outperforms dense-only & BM25 across 100+ languages using unified self-distilled retrieval", templateSetup: "MS MARCO triplets · BGE-M3 · dense + ColBERT + lexical" },
    ],
    bibtex: `@article{chen2024bgem3,
  title={BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation},
  author={Chen, Jianlv and others},
  journal={arXiv preprint arXiv:2402.03216},
  year={2024}
}`,
  },
  {
    slug: "setfit",
    shortTitle: "SetFit",
    title: "SetFit: Efficient Few-Shot Classification Without Prompts",
    authors: "Tunstall et al. (Hugging Face / Intel)",
    year: 2022,
    arxivId: "2209.11055",
    arxivUrl: "https://arxiv.org/abs/2209.11055",
    category: "Embeddings, Calibration & Multimodal",
    oneLiner:
      "Rival GPT-3 on text classification from just 8 labeled examples per class by fine-tuning a sentence encoder with contrastive pairs, then solving a convex logistic head on CPU.",
    story:
      "When you only have 8–16 labeled examples per class, standard fine-tuning overfits immediately and few-shot LLM prompting burns 100x more latency and dollars per request. SetFit turns N labeled examples into N*(N-1)/2 contrastive same/different-class pairs to adapt a tiny encoder, then fits a convex classifier head in milliseconds.",
    insight:
      "Stage 1 fine-tunes a compact encoder with built-in infonce over same-class positives and cross-class negatives; Stage 2 extracts cached embeddings via Artifact.embed() and fits a regularized classifier head in closed form via fit_batch().",
    whyGrad:
      "Stage 1 uses built-in loss='infonce' (zero custom loss!), Stage 2 uses fit_batch() on CPU, and the exported artifact runs in <5 ms behind a confidence_fallback Endpoint.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Zero custom loss math — combines built-in infonce + Artifact.embed() + CPU fit_batch() in 30 lines.",
    },
    walkthrough: [
      { title: "Generate contrastive triplets from 8 examples/class", explanation: "Pair same-class texts as positives and different-class texts as negatives to multiply training signal quadratically.", gradCall: "build_contrastive_triplets(few_shot_rows)" },
      { title: "Stage 1: Fine-tune the encoder with built-in infonce", explanation: "Pull same-class embeddings together and push different classes apart in ~1 minute.", gradCall: "trainer.forward_backward(triplets, loss={'kind': 'infonce', 'temp': 0.05})" },
      { title: "Stage 2: Fit a convex head on cached embeddings on CPU", explanation: "Extract embeddings with s1_art.embed() and solve L2-logistic via fit_batch().", gradCall: "cpu_trn.fit_batch(emb_datums, solver='dual_head_kernel_lbfgs')" },
    ],
    gotchas: [
      "Keep Stage-1 epochs small (1–2 epochs over generated pairs) so the encoder doesn't collapse on 8-shot data.",
      "Attach confidence_fallback on the deployed Endpoint so low-confidence edge cases escalate to an LLM.",
    ],
    linesOfCode: 30,
    typicalBaselineLoc: "~500 LOC SetFitTrainer + sentence-transformers glue",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "BAAI/bge-small-en-v1.5", label: "BAAI/bge-small-en-v1.5 (<5ms CPU)", estTokens: "~0.8M embed tokens", duration: "~2 min", estCost: "~$0.15" },
    ],
    datasets: [
      { id: "hf://SetFit/sst2", label: "SST-2 Few-Shot (8 examples/class)", source: "Hugging Face (public)", examples: "16 few-shot train / 872 eval" },
    ],
    primitives: [
      { label: "Built-in infonce loss", href: "/docs/training/recipes/embeddings/" },
      { label: "Classifiers & decisions", href: "/docs/training/recipes/classifier/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `from grad import Datum, DatumTargets, Grad, ModelInput, ModelSpec

client = Grad()
base_id = "BAAI/bge-small-en-v1.5"
base = client.artifacts.get(base_id)
rows = load_few_shot("hf://SetFit/sst2", shots_per_class=8)

# Stage 1: Contrastive encoder adaptation using built-in InfoNCE
with client.trainers.create(
    ModelSpec(base=base_id, adapter="full", train_mode="full", pool="mean"),
    compute="gpu",
) as trainer:
    for batch in build_contrastive_triplets(rows, base, batch_size=32):
        trainer.forward_backward(batch, loss={"kind": "infonce", "temp": 0.05}).result()
        trainer.optim_step(lr=2e-5, grad_clip=1.0).result()
    enc = trainer.export(name="setfit-encoder")

# Stage 2: Extract embeddings once and solve convex head on CPU in milliseconds
embs = enc.embed([ModelInput(tokens=enc.tokenize(r["text"])) for r in rows], pool="mean")["embeddings"]
emb_datums = [
    Datum(ModelInput(embedding=e.tolist()), DatumTargets(scalar=float(r["label"])), metadata={"action_id": "pos"})
    for e, r in zip(embs, rows)
]
with client.trainers.create(
    ModelSpec(base=enc.id, adapter="frozen_head", train_mode="frozen_head"),
    compute="cpu",
) as head_trn:
    head_trn.fit_batch(emb_datums, solver="dual_head_kernel_lbfgs", params={"l2": 0.1})
    classifier = head_trn.export(name="setfit-sst2-8shot")`,
    paperYaml: `slug: setfit
title: "SetFit Few-Shot Classification"
arxiv: "https://arxiv.org/abs/2209.11055"
category: embeddings
public_dataset: "hf://SetFit/sst2"
base_default: "BAAI/bge-small-en-v1.5"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/setfit (arXiv:2209.11055)
Dataset   hf://SetFit/sst2 (8 shots/class -> 112 contrastive pairs · public)
Model     BAAI/bge-small-en-v1.5 · Stage 1 InfoNCE (GPU) -> Stage 2 L-BFGS (CPU)
Estimate  ~2 min total · ~$0.15 · warnings: 0`,
    benchmarks: [
      { benchmark: "8-shot RAFT / SST-2 accuracy", paperReported: "Matches GPT-3 175B few-shot accuracy at 1,600x smaller model size", templateSetup: "SST-2 8-shot · BGE-small · InfoNCE + CPU L-BFGS" },
    ],
    bibtex: `@article{tunstall2022setfit,
  title={Efficient Few-Shot Learning Without Prompts},
  author={Tunstall, Lewis and others},
  journal={arXiv preprint arXiv:2209.11055},
  year={2022}
}`,
  },
  {
    slug: "sayself",
    shortTitle: "SaySelf",
    title: "SaySelf: Teaching LLMs Calibrated Verbalized Confidence via Brier RL",
    authors: "Xu et al.",
    year: 2024,
    arxivId: "2405.20974",
    arxivUrl: "https://arxiv.org/abs/2405.20974",
    category: "Embeddings, Calibration & Multimodal",
    oneLiner:
      "Eliminate LLM overconfidence by training the model with a strictly proper Brier-score RL reward so its stated confidence matches its true empirical accuracy.",
    story:
      "Ask any out-of-the-box LLM 'How confident are you (0–100%)?' and it answers '95%' whether it's right 95% of the time or 40% of the time. SaySelf trains models to emit calibrated verbalized confidence + brief uncertainty rationales using a strictly proper Brier reward — turning the LLM itself into an honest abstention gate.",
    insight:
      "Parse each rollout's predicted confidence p in [0, 1] and answer correctness y in {0, 1}, and assign the strictly proper Brier reward R = 1 - (p - y)^2 (maximized if and only if p equals the true probability of correctness) inside GRPO.",
    whyGrad:
      "A 4-line Brier reward function plugs straight into grad's standard GRPO loop — zero custom loss code, zero separate calibration model.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Strictly proper Brier reward + built-in GRPO turns calibration training into a 28-line loop.",
    },
    walkthrough: [
      { title: "Sample answers with verbalized confidence p in [0, 1]", explanation: "Prompt the model to output both its answer and calibrated confidence score.", gradCall: "snap.sample(prompts, n=8)" },
      { title: "Score every rollout with strictly proper Brier reward", explanation: "Compute r = 1 - (p - y)^2 (or -0.5 for malformed confidence format).", gradCall: "r = 1.0 - (p - y) ** 2" },
      { title: "Update with built-in GRPO", explanation: "Group-center Brier rewards and step with built-in loss='grpo'.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'grpo'})" },
    ],
    gotchas: [
      "Give a clear negative penalty (-0.5) for unparseable confidence tags so the model doesn't dodge calibration by omitting the score.",
      "Evaluate Expected Calibration Error (ECE) on a held-out temporal or domain split alongside accuracy.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~950 LOC two-stage calibration + PPO pipeline",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen3-8B", label: "Qwen/Qwen3-8B (recommended)", estTokens: "~4.0M tokens", duration: "~20 min", estCost: "~$1.60" },
    ],
    datasets: [
      { id: "hf://trivia_qa", label: "TriviaQA (Calibrated QA)", source: "Hugging Face (public)", examples: "15,000 factual QA prompts" },
    ],
    primitives: [
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
      { label: "Classifiers & calibration", href: "/docs/training/recipes/classifier/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import re
import grad
from grad import Grad, ModelSpec

client = Grad()
CONF_RE = re.compile(r"Confidence:\\s*(0?\\.\\d+|1(?:\\.0+)?)")

def brier_reward(text: str, gold: str) -> float:
    m = CONF_RE.search(text)
    if not m:
        return -0.5  # format penalty
    p = max(0.0, min(1.0, float(m.group(1))))
    y = 1.0 if gold.lower() in text.lower() else 0.0
    return 1.0 - (p - y) ** 2  # strictly proper scoring rule

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen3-8B", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_qa_batches("hf://trivia_qa", batch_size=32)):
        groups = trainer.snapshot().sample(batch.prompt_inputs, n=8, max_new_tokens=256)
        rewards = [[brier_reward(t.output["text"], gold) for t in g] for g, gold in zip(groups, batch.answers)]
        datums = grad.group_datums(groups, rewards=rewards, norm="std")

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.2})
        opt = trainer.optim_step(lr=2e-5, grad_clip=1.0)
        print(f"step={step} loss={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="sayself-calibrated-8b", merge_adapter=True)`,
    paperYaml: `slug: sayself
title: "SaySelf: Brier-Calibrated Confidence RL"
arxiv: "https://arxiv.org/abs/2405.20974"
category: embeddings
public_dataset: "hf://trivia_qa"
base_default: "Qwen/Qwen3-8B"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/sayself (arXiv:2405.20974)
Dataset   hf://trivia_qa (15,000 QA prompts · public)
Model     Qwen/Qwen3-8B · adapter=lora (rank=32) · group_size=8
Loss      grpo with strictly proper Brier reward 1 - (p - y)^2
Estimate  ~4.0M tokens · ~20 min · ~$1.60 · warnings: 0`,
    benchmarks: [
      { benchmark: "Expected Calibration Error (ECE)", paperReported: "Cuts verbalized ECE by >50% across HotpotQA & TriviaQA while holding QA accuracy", templateSetup: "TriviaQA · Qwen/Qwen3-8B · Brier GRPO" },
    ],
    bibtex: `@inproceedings{xu2024sayself,
  title={SaySelf: Teaching LLMs to Express Confidence with Self-Reflective Rationales},
  author={Xu, Tianyang and others},
  booktitle={EMNLP},
  year={2024}
}`,
  },
  {
    slug: "vlm-grpo",
    shortTitle: "Visual-RFT / VLM GRPO",
    title: "Visual-RFT: Multimodal Reinforcement Fine-Tuning with Verifiable IoU Rewards",
    authors: "Liu et al.",
    year: 2025,
    arxivId: "2503.01785",
    arxivUrl: "https://arxiv.org/abs/2503.01785",
    category: "Embeddings, Calibration & Multimodal",
    oneLiner:
      "Extend GRPO to Vision-Language Models using MediaRef inputs and verifiable IoU / classification rewards — improving open-vocab detection and UI grounding from tiny labeled sets.",
    story:
      "Multimodal fine-tuning normally relies on giant SFT datasets that overfit brittle bounding-box phrasing. Visual-RFT showed that applying GRPO directly to VLMs with verifiable Intersection-over-Union (IoU) and format rewards outperforms SFT by +10–24 points in few-shot visual grounding and fine-grained classification.",
    insight:
      "Pass images via MediaRef alongside prompt tokens, sample G=8 <think> + bounding-box rollouts per image, grade each rollout with verifiable IoU + format reward, and update the VLM LoRA adapter with built-in GRPO.",
    whyGrad:
      "ModelInput(tokens=..., media=[MediaRef(...)]) works identically across Artifact.sample() and Trainer.forward_backward() — zero client-side image processors or custom multimodal collators.",
    smoothness: {
      rating: "Effortless",
      verdict:
        "Server-side MediaRef handling makes VLM GRPO identical to text-only GRPO in 31 lines.",
    },
    walkthrough: [
      { title: "Attach images via MediaRef in ModelInput", explanation: "Pass S3/HTTP/HF image refs directly — the server handles vision encoding and token expansion.", gradCall: "ModelInput(messages=msgs, media=[MediaRef(kind='image', ref=img_url)])" },
      { title: "Sample G=8 multimodal reasoning + bbox rollouts", explanation: "Artifact.sample() preserves exact 1:1 token alignment across vision and text tokens.", gradCall: "trainer.snapshot().sample(vlm_inputs, n=8)" },
      { title: "Grade bounding boxes with verifiable IoU + step with GRPO", explanation: "Compute exact IoU against ground-truth boxes and run built-in grpo.", gradCall: "trainer.forward_backward(datums, loss={'kind': 'grpo'})" },
    ],
    gotchas: [
      "Keep a small format reward (0.1 for valid JSON/XML box coordinates) so early rollouts get non-zero variance even before IoU improves.",
      "Start with Qwen2.5-VL-7B or Qwen3-VL-8B and cap image resolution cleanly to keep HBM fast across group_size=8.",
    ],
    linesOfCode: 24,
    typicalBaselineLoc: "~1,900 LOC custom VLM processor + distributed GRPO",
    mode: "Custom loop",
    entrypoint: "train.py",
    models: [
      { id: "Qwen/Qwen2.5-VL-7B-Instruct", label: "Qwen2.5-VL-7B-Instruct (recommended)", estTokens: "~5.6M tokens", duration: "~28 min", estCost: "~$2.25" },
    ],
    datasets: [
      { id: "hf://laolao77/ViRFT_COCO_base65", label: "Visual-RFT COCO Few-Shot Grounding", source: "Hugging Face (public)", examples: "Few-shot object grounding + IoU boxes" },
    ],
    primitives: [
      { label: "Multimodal MediaRef", href: "/docs/training/custom-loops/" },
      { label: "RL for agents", href: "/docs/training/recipes/rl-agents/" },
    ],
    codeLabel: "train.py",
    codeLanguage: "python",
    code: `import grad
from grad import Grad, MediaRef, ModelInput, ModelSpec

client = Grad()

with client.trainers.create(
    ModelSpec(base="Qwen/Qwen2.5-VL-7B-Instruct", adapter="lora", train_mode="lora", params={"rank": 32}),
    compute="gpu",
) as trainer:
    for step, batch in enumerate(load_vlm_batches("hf://laolao77/ViRFT_COCO_base65", batch_size=16)):
        vlm_inputs = [
            ModelInput(
                messages=[{"role": "user", "content": f"Locate all {ex.category} and return JSON [x1,y1,x2,y2]."}],
                media=[MediaRef(kind="image", ref=ex.image_url)],
            )
            for ex in batch
        ]
        groups = trainer.snapshot().sample(vlm_inputs, n=8, temperature=0.9, max_new_tokens=384)
        rewards = [
            [0.9 * compute_bbox_iou(t.output["text"], ex.gt_boxes) + 0.1 * valid_box_json(t.output["text"]) for t in g]
            for g, ex in zip(groups, batch)
        ]
        datums = grad.group_datums(groups, rewards=rewards, norm="std")

        fb = trainer.forward_backward(datums, loss={"kind": "grpo", "clip_low": 0.2, "clip_high": 0.28})
        opt = trainer.optim_step(lr=1e-5, grad_clip=1.0)
        print(f"step={step} vlm_grpo={fb.result().loss:.4f}"); opt.result()
    artifact = trainer.export(name="visual-rft-coco", merge_adapter=True)`,
    paperYaml: `slug: vlm-grpo
title: "Visual-RFT: Multimodal VLM GRPO"
arxiv: "https://arxiv.org/abs/2503.01785"
category: embeddings
public_dataset: "hf://laolao77/ViRFT_COCO_base65"
base_default: "Qwen/Qwen2.5-VL-7B-Instruct"
compute: gpu
entrypoint: train.py`,
    dryRunOutput: `Template  papers/vlm-grpo (arXiv:2503.01785)
Dataset   hf://laolao77/ViRFT_COCO_base65 (multimodal grounding · public)
Model     Qwen/Qwen2.5-VL-7B-Instruct · adapter=lora (rank=32) · MediaRef images
Loss      grpo (clip=[0.20, 0.28]) with verifiable IoU + JSON format reward
Estimate  ~5.6M tokens · ~28 min · ~$2.25 · warnings: 0`,
    benchmarks: [
      { benchmark: "Few-shot COCO & LVIS mAP", paperReported: "+10 to +24 pts over multimodal SFT on 1-shot & few-shot grounding", templateSetup: "ViRFT_COCO_base65 · Qwen2.5-VL-7B · IoU GRPO" },
    ],
    bibtex: `@article{liu2025visualrft,
  title={Visual-RFT: Visual Reinforcement Fine-Tuning},
  author={Liu, Ziyu and others},
  journal={arXiv preprint arXiv:2503.01785},
  year={2025}
}`,
  },
];
