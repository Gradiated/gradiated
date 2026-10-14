# Production traces to RL environments: reading list

## Purpose and reading order

This list targets the workflow we want to investigate: collect production agent
traces, identify recurring failures, construct reproducible training tasks,
verify outcomes, and improve the agent. It includes **16 additional papers**
alongside TRACE and PRIME-RL, for **18 papers total**.

Read the first six recommendations in order, then choose from the remaining
papers according to the implementation question. Most adjacent papers do not
implement the entire production-trace-to-environment pipeline: some generate
environments without production traces, some train within existing environments,
and some adapt prompts or memory instead of weights. Each entry makes that
distinction explicit.

Evidence convention: descriptions below summarize author-reported methods.
Reasons to read, suggested applications, and proposed experiments are our
inferences; we have not reproduced these papers. Results on their benchmarks
do not establish effectiveness on our production workloads.

## Already read

### TRACE: Capability-Targeted Agentic Training

- Paper: <https://arxiv.org/abs/2604.05336>
- Original version: <https://arxiv.org/html/2604.05336v1>
- Revised version: <https://arxiv.org/html/2604.05336v2>

Contrasts successful and failed trajectories, identifies missing capabilities,
generates capability-specific synthetic environments, and trains LoRA adapters
with RL. This is the closest starting point for our desired pipeline.

**Version note:** the original April 2026 version uses the base model to select
an adapter from capability descriptions, matching the notes that prompted this
list. The July 2026 revision instead trains a mixture-of-experts model over the
capability adapters and changes the evaluation to include SWE-bench Verified.
Keep the version explicit when discussing routing or comparing results.

**Open question:** do isolated capability environments transfer to full workflows
better than training on realistic, compositional tasks with varied initial states?

### PRIME-RL: Async & Decentralized RL Training at Scale

- Paper: <https://openreview.net/pdf?id=yk3ICpEbv8>
- Local copy: [30_PRIME_RL_Async_Decentralize.pdf](30_PRIME_RL_Async_Decentralize.pdf)
- Implementation: <https://github.com/PrimeIntellect-ai/prime-rl>

A systems reference for asynchronous agentic RL, including multi-turn tool use
and environments defined separately from the training infrastructure. Use it
when designing rollout/trainer scheduling and handling policy lag. It does not
solve the problem of deriving useful environments from production failures.

## Read these six next

### 1. GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning

- Paper: <https://arxiv.org/abs/2507.19457>
- First submitted: 2025
- Relevance: adapting directly from execution traces; cheaper baseline.

GEPA reflects on trajectories and execution feedback, proposes prompt changes,
and selects or combines complementary candidates using a Pareto frontier.
The authors compare it with GRPO and report substantial rollout savings on
their evaluated tasks.

**Why read:** this directly addresses whether observed failures justify weight
updates. Inspect the feedback available to each method and the rollout-cost
accounting, rather than transferring the headline comparison to our workload.

**Question to carry forward:** how much improvement can the same failure traces
produce through prompt optimization before RL becomes worthwhile?

### 2. Agent World Model: Infinity Synthetic Environments for Agentic Reinforcement Learning

- Paper: <https://arxiv.org/abs/2602.10090>
- First submitted: 2026
- Relevance: executable, stateful tool environments; synthetic-to-real transfer.

AWM generates code-driven environments backed by databases, with tool interfaces,
consistent state transitions, and reward functions that can inspect state.
It evaluates agents trained in synthetic environments on separate benchmarks.

**Why read:** it offers a concrete alternative to an LLM inventing tool responses
on every step. For our pipeline, production traces could inform the environment
specification, while executable code determines transitions and outcomes.

**Question to carry forward:** what environment state and tool semantics must be
reconstructed from traces to make counterfactual rollouts credible?

### 3. EnvScaler: Scaling Tool-Interactive Environments for LLM Agent via Programmatic Synthesis

- Paper: <https://arxiv.org/abs/2601.05808>
- First submitted: 2026
- Relevance: separating reusable environments from task instances and validators.

EnvScaler builds environment skeletons, then generates multiple scenarios and
rule-based trajectory validation functions within each environment. It uses
the resulting data for both SFT and RL.

**Why read:** this is especially relevant to the concern that one environment
per capability is too granular. A reusable domain simulator can support many
failure families through different states, goals, and constraints.

**Question to carry forward:** should a failure generate a new simulator, or a
new task configuration within an existing simulator?

### 4. Agent Lightning v1.0: Towards Harnessed Agentic RL

- Paper: <https://arxiv.org/abs/2608.17528>
- First submitted: 2026
- Background: [Agent Lightning: Train ANY AI Agents with Reinforcement Learning](https://arxiv.org/abs/2508.03680) (2025).
- Relevance: keeping the deployment harness in the training loop.

The agent harness owns tools, context, control flow, and environment interaction;
the trainer observes LLM request-response pairs through a proxy. The paper
examines retokenization, sample merging, advantage calculation, loss normalization,
and scheduling in that setting.

**Why read:** useful for connecting an existing production agent to training
without creating a separate agent implementation whose behavior differs from
deployment. Read v1.0 first; the original paper is optional architectural background
and is not counted as a separate entry in this list.

**Question to carry forward:** what trace metadata is necessary to reconstruct
the actual model decisions when the harness changes or truncates context?

### 5. EnvGen: Generating and Adapting Environments via LLMs for Training Embodied Agents

- Paper: <https://arxiv.org/abs/2403.12014>
- First submitted: 2024
- Relevance: failure-informed environment configuration and curriculum.

EnvGen uses an LLM to generate simulator configurations, trains an RL agent
on a mixture of original and generated environments, then uses performance
feedback to adapt the configurations toward weak skills.

**Why read:** a clear earlier example of the feedback-to-environment loop.
It adapts an existing simulator rather than generating a separate codebase
for every deficit. Its evidence concerns embodied/game agents, not production
LLM tool agents; the reusable contribution is the experimental design.

**Question to carry forward:** can failure clusters drive initial-state and
scenario changes while preserving the real environment's mechanics?

### 6. SWE-smith: Scaling Data for Software Engineering Agents

- Paper: <https://arxiv.org/abs/2504.21798>
- First submitted: 2025
- Relevance: task generation grounded in real systems and executable tests.

SWE-smith constructs execution environments from repositories and synthesizes
task instances by introducing changes that break existing tests. It releases
tasks, trajectories, environments, and trained models.

**Why read:** a practical example of converting real software into a scalable
source of verifiable tasks. It is a task/data-generation reference, not evidence
that RL is always preferable to supervised training.

**Question to carry forward:** can real production incidents seed mutations
whose success conditions are checked by existing tests or state invariants?

## Then read according to the implementation question

### 7. RAGEN: Understanding Self-Evolution in LLM Agents via Multi-Turn Reinforcement Learning

- Paper: <https://arxiv.org/abs/2504.20073>
- First submitted: 2025
- Relevance: training dynamics after the environment exists.

Studies trajectory-level agent RL and failure modes such as reasoning collapse,
along with rollout filtering, initial-state diversity, interaction granularity,
and reward design. Read for diagnostics that distinguish a poor training task
from unstable optimization. Its stylized environments limit direct transfer
of conclusions to our deployment.

### 8. Safe and Scalable Web Agent Learning via Recreated Websites (VeriEnv)

- Paper: <https://proceedings.mlr.press/v306/chae26a.html>
- Published: 2026
- Relevance: reconstructing real interfaces as resettable environments.

VeriEnv clones real websites into executable environments, exposes internal
state through a Python SDK, and generates tasks with programmatically verified
rewards. Read for a concrete approach to turning a real interaction surface
into a training sandbox. Website recreation is adjacent to trace-driven
reconstruction; the paper does not establish that a trace alone is sufficient.

### 9. Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models

- Paper: <https://arxiv.org/abs/2510.04618>
- First submitted: 2025
- Relevance: another low-cost way to learn from execution feedback.

ACE maintains a structured playbook through generation, reflection, and curation,
using incremental updates to preserve accumulated lessons. Read alongside GEPA
to compare prompt evolution with reusable memory. For us, it suggests a baseline
that stores lessons from recurring failures without training an adapter.

### 10. SWE-RL: Advancing LLM Reasoning via Reinforcement Learning on Open Software Evolution

- Paper: <https://arxiv.org/abs/2502.18449>
- First submitted: 2025
- Relevance: using historical artifacts as training supervision.

SWE-RL derives tasks from software evolution history and uses a lightweight
solution-similarity reward. Read to understand what can be extracted from
historical changes without a full interactive simulator. This is RL on tasks
derived from historical data, not offline RL over logged production actions,
and its reward is not equivalent to passing executable tests.

### 11. Toward Training Superintelligent Software Agents through Self-Play SWE-RL

- Paper: <https://arxiv.org/abs/2512.18552>
- First submitted: 2025
- Relevance: generating additional tasks after the initial failure corpus.

Self-play SWE-RL trains an agent to inject and repair bugs in sandboxed real
repositories, specifying bugs with test patches. Read after SWE-smith to compare
a task-generation pipeline with a learned generator/solver curriculum.
For our workflow, the question is whether trace-seeded task families can expand
usefully without drifting away from production-relevant failures.

### 12. Tau²-Bench: Evaluating Conversational Agents in a Dual-Control Environment

- Paper: <https://arxiv.org/abs/2506.07982>
- First submitted: 2025
- Relevance: environment fidelity, user simulation, and compositional tasks.

Both agent and user can act in a shared environment. The benchmark includes
a compositional task generator, state-constrained user simulation, and analyses
that separate reasoning failures from communication/coordination failures.
Read as an environment-design reference: a failure in a production trace may
depend on the user's actions, not only on the agent's tool calls.

### 13. Environment Evolution for Terminal Agents

- Paper: <https://arxiv.org/abs/2609.04128>
- First submitted: 2026
- Relevance: maintaining useful task difficulty as the agent improves.

Proposes incrementally increasing environment difficulty off-policy and scheduling
evolved generations during training, addressing the loss of learning signal as
fixed tasks become too easy. Read for curriculum design after an initial set of
trace-derived tasks works. This is a recent preprint; treat it as a candidate
design to test rather than an established production recipe.

## Three foundations worth including

These papers study broader RL settings rather than LLM agents. Read them for
the underlying problem formulations, not as drop-in implementations for GRPO.

### 14. Emergent Complexity and Zero-shot Transfer via Unsupervised Environment Design (PAIRED)

- Paper: <https://arxiv.org/abs/2012.02096>
- First submitted: 2020
- Relevance: generating tasks that are difficult but solvable.

PAIRED trains an environment generator using regret between a protagonist and
an antagonist agent, avoiding the tendency of pure adversarial difficulty to
produce unsolvable tasks. This gives a useful framework for asking whether a
generated failure variant offers learnable signal rather than merely low reward.

### 15. Prioritized Level Replay

- Paper: <https://arxiv.org/abs/2010.03934>
- First submitted: 2020; ICML 2021
- Relevance: selecting which tasks to revisit.

PLR samples levels according to estimated learning potential rather than
uniformly. Read for the distinction between generating more tasks and making
better use of the existing task pool. A production analogue would prioritize
reproducible failure cases that the current policy can still learn from;
the paper's TD-error scoring does not directly apply to critic-free GRPO.

### 16. Conservative Q-Learning for Offline Reinforcement Learning

- Paper: <https://arxiv.org/abs/2006.04779>
- First submitted: 2020
- Relevance: limitations of learning directly from fixed logged traces.

CQL addresses value overestimation under distribution shift when training from
a static dataset without new environment interaction. Read to distinguish two
projects: learning from the logged actions themselves, and using logs to build
an environment in which fresh rollouts can explore different actions. It is
background on offline RL, not a recommended replacement for agentic GRPO.

## What this suggests testing

Our starting hypothesis should be that recurring production failures can be
represented as task families within a small number of faithful, executable
domain environments. Capability-specific environments and adapters are one
alternative to compare, rather than a requirement of the pipeline.

An initial comparison should use the same trace corpus and held-out task families:

1. Base agent and existing harness.
2. GEPA prompt optimization using execution feedback.
3. ACE-style curated lessons or memory from those failures.
4. SFT on verified successful trajectories.
5. GRPO in reconstructed domain environments.
6. Capability-targeted training if it adds value over the simpler shared setup.

Measure held-out task success, regressions on unaffected tasks, end-to-end
adaptation cost, and serving cost. Report rollout counts alongside token usage,
environment construction/validation cost, optimizer-model calls, GPU time, and
inference overhead. Equal rollout counts alone do not establish equal cost.

Split by task/failure family and source system where possible, so near-duplicate
trace variants do not leak across training and evaluation. Evaluate synthetic
training gains in a separate, production-representative environment. When
diagnosing capabilities, contrast comparable successes and failures: a capability
correlated with success is a hypothesis, not proof that its absence caused the
failure. Some failures will require tool or harness fixes rather than training.
