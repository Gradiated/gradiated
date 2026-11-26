import { useState } from "react";
import { Link } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";

import { OPUS_MODEL, SONNET_MODEL } from "../../docs/models";

/* ---------------------------------------------------------------------------
   Engineering callout: one hairline left trace + uppercase mono label.
   No filled alert banners; respects the site's visual restraint.
   --------------------------------------------------------------------------- */

export const DocsCallout = ({
  children,
  label = "Note",
  tone = "note",
}: {
  children: ReactNode;
  label?: string;
  tone?: "note" | "tip" | "warn";
}): ReactElement => (
  <aside className={`gr-doc-callout gr-doc-callout--${tone}`}>
    <div className="gr-doc-callout-label">{label}</div>
    <div className="gr-doc-callout-body">{children}</div>
  </aside>
);

/* ---------------------------------------------------------------------------
   Terminal output preview: shows real CLI stdout alongside the command so
   the docs feel tangible before the reader even installs the CLI.
   --------------------------------------------------------------------------- */

export const DocsTerminal = ({
  children,
  command,
  title = "Output",
}: {
  children: ReactNode;
  command?: string;
  title?: string;
}): ReactElement => {
  const [copied, setCopied] = useState(false);

  const copyCommand = () => {
    if (!command) return;
    void navigator.clipboard
      .writeText(command)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="gr-doc-terminal">
      <div className="gr-doc-terminal-head">
        <span className="gr-doc-terminal-title">{title}</span>
        {command ? (
          <button
            className="gr-doc-terminal-copy"
            onClick={copyCommand}
            type="button"
          >
            {copied ? "Copied" : "Copy command"}
          </button>
        ) : null}
      </div>
      {command ? (
        <div className="gr-doc-terminal-cmd">
          <span aria-hidden="true" className="gr-doc-terminal-prompt">
            $
          </span>
          <code>{command}</code>
        </div>
      ) : null}
      <div className="gr-doc-terminal-out">{children}</div>
    </div>
  );
};

/* ---------------------------------------------------------------------------
   1. Interactive 5-Primitive Flywheel Schematic (Training Overview)
   --------------------------------------------------------------------------- */

type PrimitiveNode = {
  id: string;
  index: string;
  name: string;
  role: string;
  href: string;
  summary: string;
  ops: string[];
  detail: string;
};

const PRIMITIVES: PrimitiveNode[] = [
  {
    id: "trajectory",
    index: "01",
    name: "Trajectory",
    role: "Data & logs",
    href: "/docs/training/trajectories/",
    summary: "One shared format stored in a Dataset for production logs, labeled examples, and agent runs.",
    ops: ["dataset.push()", "dataset.import_file()", "dataset.score()", "dataset.filter()", "dataset.add_source()"],
    detail: "Filled automatically from Gradiated inference, pushed from your DB, or synced from OTel, Langfuse, and Braintrust.",
  },
  {
    id: "environment",
    index: "02",
    name: "Rubric & Environment",
    role: "Grading & tools",
    href: "/docs/training/rubrics/",
    summary: "Grade answers with Python checks or a Judge, or run multi-turn agents against your own containers and tools.",
    ops: ["Rubric()", "Judge()", "setup()", "step()", "evaluate()"],
    detail: "Environments run in Gradiated sandboxes, or on your own machines with grad env serve. evaluate() checks live containers before teardown() cleans up.",
  },
  {
    id: "trainer",
    index: "03",
    name: "Trainer",
    role: "Model training",
    href: "/docs/training/recipes/",
    summary: "Managed training engine (billed per million tokens) driven by a built-in Recipe or your own Python loop.",
    ops: ["runs.create()", "forward_backward()", "optim_step()", "save_state()", "snapshot()"],
    detail: "Runs forward, backward, and optimizer steps back-to-back and supports built-in losses or custom PyTorch CustomLoss classes.",
  },
  {
    id: "artifact",
    index: "04",
    name: "Artifact & Deploy",
    role: "Cloud or self-host",
    href: "/docs/training/deploying/",
    summary: "A versioned .grad artifact (PEFT LoRA or merged Safetensors) you can host on Gradiated Cloud or download for vLLM / SGLang.",
    ops: ["run.deploy()", "grad artifacts download", "artifacts.merge()", "feedback.record()"],
    detail: "Deploy on Gradiated Cloud in one command via the OpenAI, Anthropic, or SystemOne SDK, or serve the LoRA weights on your own GPUs.",
  },
];

export const DocsTrainingFlywheel = (): ReactElement => {
  const [activeId, setActiveId] = useState<string>("trainer");
  const active = PRIMITIVES.find((p) => p.id === activeId) ?? PRIMITIVES[0];

  return (
    <figure className="gr-doc-widget" aria-label="The four grad stages and feedback loop">
      <div className="gr-doc-widget-head">
        <span className="gr-doc-widget-kicker">Architecture · 4 stages</span>
        <span className="gr-doc-widget-hint">Select a stage to inspect its API</span>
      </div>

      <div className="gr-doc-flywheel-grid gr-doc-flywheel-grid--4" role="tablist" aria-label="Training stages">
        {PRIMITIVES.map((node, idx) => {
          const isSelected = node.id === active.id;
          return (
            <button
              key={node.id}
              aria-selected={isSelected}
              className="gr-doc-die"
              data-active={isSelected ? "true" : undefined}
              onClick={() => setActiveId(node.id)}
              role="tab"
              type="button"
            >
              <span className="gr-doc-die-num">{node.index}</span>
              <strong className="gr-doc-die-name">{node.name}</strong>
              <span className="gr-doc-die-role">{node.role}</span>
              {idx < PRIMITIVES.length - 1 ? (
                <span aria-hidden="true" className="gr-doc-die-arrow">
                  →
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="gr-doc-flywheel-loop" aria-hidden="true">
        <span>↩ live traffic + feedback.record() feeds back into 01 Trajectory</span>
      </div>

      <div className="gr-doc-inspector" role="tabpanel">
        <div className="gr-doc-inspector-top">
          <div>
            <div className="gr-doc-inspector-title">
              <span>{active.index}</span> {active.name}
            </div>
            <p className="gr-doc-inspector-summary">{active.summary}</p>
          </div>
          <Link className="gr-doc-inspector-link" to={active.href}>
            Read guide →
          </Link>
        </div>
        <p className="gr-doc-inspector-detail">{active.detail}</p>
        <div className="gr-doc-chips">
          {active.ops.map((op) => (
            <code key={op} className="gr-doc-chip">
              {op}
            </code>
          ))}
        </div>
      </div>
    </figure>
  );
};

/* ---------------------------------------------------------------------------
   2. Interactive Recipe Chooser ("What are you building?")
   --------------------------------------------------------------------------- */

type RecipeChoice = {
  id: string;
  goal: string;
  recipe: string;
  profile: string;
  typicalWin: string;
  dataNeeded: string;
  href: string;
  snippet: string;
};

const RECIPE_CHOICES: RecipeChoice[] = [
  {
    id: "router",
    goal: "Cut LLM spend without losing quality",
    recipe: "RouterRecipe",
    profile: "Fine-tuned Qwen3-0.6B router",
    typicalWin: "45–70% cost drop within your quality bar",
    dataNeeded: "Prompts + a Judge (or existing scores); model pricing is built in",
    href: "/docs/training/recipes/router/",
    snippet: `dataset = client.datasets.get("support-traces")
run = client.runs.create(
    dataset=dataset,
    name="support-router",
    recipe=RouterRecipe(
        models=["qwen/qwen3-8b", "${OPUS_MODEL}"],
        score=Judge(name="resolved", model="${SONNET_MODEL}", prompt="Did the assistant solve the issue?"),
        max_quality_drop=0.02,
    ),
).wait()
endpoint = run.deploy()`,
  },
  {
    id: "decision-model",
    goal: "Train a decision model (Choice, Noul, Score)",
    recipe: "DecisionModelRecipe",
    profile: "linden-1 or Qwen3-0.6B (SystemOne SDK)",
    typicalWin: "Drop-in replacement for linden-1 in TypeSafeClient",
    dataNeeded: "SystemOne state + questions + expected_output",
    href: "/docs/training/recipes/decision-model/",
    snippet: `dataset = client.datasets.get("ticket-triage")
run = client.runs.create(
    dataset=dataset,
    name="ticket-triage",
    recipe=DecisionModelRecipe(model="gradiated/linden-1"),
).wait()
endpoint = run.deploy()`,
  },
  {
    id: "sft-dpo",
    goal: "Fine-tune a fast 8B specialist (SFT → DPO)",
    recipe: "SFTRecipe + DPORecipe",
    profile: "LoRA adapter (rank 32)",
    typicalWin: "5–10x lower latency on structured edits & SQL",
    dataNeeded: "Logs filtered with a Judge (or chosen/rejected pairs)",
    href: "/docs/training/recipes/sft/",
    snippet: `judge = Judge(name="clean", model="${SONNET_MODEL}", prompt="Is this answer accurate?")
clean = client.datasets.get("diff-merge-prod").score(judge).wait().filter(
    lambda t: t.scores["clean"] >= 0.8,
)
sft = client.runs.create(
    dataset=clean,
    name="fast-diff-merge",
    recipe=SFTRecipe(model="qwen/qwen3-8b"),
).wait()`,
  },
  {
    id: "grpo",
    goal: "RL-train an agent against real tests or tools",
    recipe: "GRPORecipe",
    profile: "LoRA + Rubric, Harbor, or Docker env",
    typicalWin: "Learns error recovery & multi-turn tool use",
    dataNeeded: "Task prompts + Rubric (Judge / validators) or Environment",
    href: "/docs/training/recipes/rl-agents/",
    snippet: `dataset = client.datasets.get("sql-tasks")
sft_art = client.artifacts.get("sql-agent@sft-v1")
run = client.runs.create(
    dataset=dataset,
    name="sql-agent",
    recipe=GRPORecipe(
        model=sft_art,
        rubric=Rubric([
            Scorer("valid_sql", weight=0.3, fn=validators.SQL()),
            Judge(name="correct", model="${SONNET_MODEL}", prompt="Verify SQL accuracy.", weight=0.7),
        ]),
        group_size=8,
    ),
).wait()`,
  },
  {
    id: "distill",
    goal: "Shrink a 32B/frontier teacher into a 4B student",
    recipe: "DistillRecipe",
    profile: "On-policy top-k KL distillation",
    typicalWin: "Matches teacher quality on your prompts only",
    dataNeeded: "1,000+ unlabelled prompts (no gold answers needed)",
    href: "/docs/training/recipes/distillation/",
    snippet: `dataset = client.datasets.get("support-prompts")
run = client.runs.create(
    dataset=dataset,
    name="support-4b",
    recipe=DistillRecipe(
        model="qwen/qwen3-4b",
        teacher="qwen/qwen3-32b",
        rollout=OnPolicy(max_new_tokens=512),
    ),
).wait()`,
  },
  {
    id: "cartridge",
    goal: "Eliminate a 50k-token repeated system prompt",
    recipe: "CartridgeRecipe",
    profile: "adapters.PrefixKV (frozen base)",
    typicalWin: "Pay to encode docs once; swap per tenant",
    dataNeeded: "Static docs corpus (Context) + QA prompts",
    href: "/docs/training/recipes/cartridges/",
    snippet: `dataset = client.datasets.get("api-docs-qa")
run = client.runs.create(
    dataset=dataset,
    name="api-docs-cartridge",
    recipe=CartridgeRecipe(
        model="qwen/qwen3-8b",
        context=Context.from_file("./api-docs.md"),
        num_tokens=256,
    ),
).wait()`,
  },
];

export const DocsRecipeChooser = (): ReactElement => {
  const [selectedId, setSelectedId] = useState<string>("router");
  const [copied, setCopied] = useState(false);
  const current =
    RECIPE_CHOICES.find((c) => c.id === selectedId) ?? RECIPE_CHOICES[0];

  const copySnippet = () => {
    void navigator.clipboard
      .writeText(current.snippet)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <figure className="gr-doc-widget" aria-label="Interactive recipe selector">
      <div className="gr-doc-widget-head">
        <span className="gr-doc-widget-kicker">Recipe selector</span>
        <span className="gr-doc-widget-hint">Pick what you are building</span>
      </div>

      <div className="gr-doc-pill-grid" role="tablist" aria-label="Training goals">
        {RECIPE_CHOICES.map((item) => {
          const isSelected = item.id === current.id;
          return (
            <button
              key={item.id}
              aria-selected={isSelected}
              className="gr-doc-pill"
              data-active={isSelected ? "true" : undefined}
              onClick={() => {
                setSelectedId(item.id);
                setCopied(false);
              }}
              role="tab"
              type="button"
            >
              <span className="gr-doc-pill-tag">{item.recipe}</span>
              <span className="gr-doc-pill-text">{item.goal}</span>
            </button>
          );
        })}
      </div>

      <div className="gr-doc-inspector" role="tabpanel">
        <div className="gr-doc-spec-strip">
          <div>
            <span className="gr-doc-spec-k">Recipe</span>
            <code className="gr-doc-spec-v">{current.recipe}</code>
          </div>
          <div>
            <span className="gr-doc-spec-k">Profile</span>
            <span className="gr-doc-spec-v">{current.profile}</span>
          </div>
          <div>
            <span className="gr-doc-spec-k">Typical result</span>
            <span className="gr-doc-spec-v">{current.typicalWin}</span>
          </div>
        </div>
        <p className="gr-doc-inspector-detail">
          <strong>Data needed:</strong> {current.dataNeeded}
        </p>
        <div className="gr-doc-mini-code">
          <button
            className="gr-doc-copy gr-doc-copy--visible"
            onClick={copySnippet}
            type="button"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <pre>
            <code>{current.snippet}</code>
          </pre>
        </div>
        <div className="gr-doc-inspector-foot">
          <Link className="gr-doc-inspector-link" to={current.href}>
            Open full {current.recipe} guide →
          </Link>
        </div>
      </div>
    </figure>
  );
};

/* ---------------------------------------------------------------------------
   3. Interactive 1:1 Token-Alignment Visualizer (Custom Loops)
   --------------------------------------------------------------------------- */

type TokenCell = {
  idx: number;
  text: string;
  tokenId: number;
  role: "user" | "assistant" | "tool";
  turnId: number;
  lossMask: number;
  logprob: number;
  advantage: number;
};

const ALIGNMENT_TOKENS: TokenCell[] = [
  { idx: 0, text: "<bos>", tokenId: 151644, role: "user", turnId: 0, lossMask: 0.0, logprob: 0.0, advantage: 0.0 },
  { idx: 1, text: "Count", tokenId: 7812, role: "user", turnId: 0, lossMask: 0.0, logprob: 0.0, advantage: 0.0 },
  { idx: 2, text: "users", tokenId: 3847, role: "user", turnId: 0, lossMask: 0.0, logprob: 0.0, advantage: 0.0 },
  { idx: 3, text: "sql(", tokenId: 19204, role: "assistant", turnId: 0, lossMask: 1.0, logprob: -0.18, advantage: 1.14 },
  { idx: 4, text: "SELECT", tokenId: 4921, role: "assistant", turnId: 0, lossMask: 1.0, logprob: -0.04, advantage: 1.14 },
  { idx: 5, text: "COUNT", tokenId: 14122, role: "assistant", turnId: 0, lossMask: 1.0, logprob: -0.09, advantage: 1.14 },
  { idx: 6, text: ")", tokenId: 8, role: "assistant", turnId: 0, lossMask: 1.0, logprob: -0.02, advantage: 1.14 },
  { idx: 7, text: "rows:", tokenId: 10942, role: "tool", turnId: 1, lossMask: 0.0, logprob: 0.0, advantage: 0.0 },
  { idx: 8, text: "42", tokenId: 2983, role: "tool", turnId: 1, lossMask: 0.0, logprob: 0.0, advantage: 0.0 },
  { idx: 9, text: "There", tokenId: 3869, role: "assistant", turnId: 1, lossMask: 1.0, logprob: -0.31, advantage: 1.14 },
  { idx: 10, text: "are", tokenId: 525, role: "assistant", turnId: 1, lossMask: 1.0, logprob: -0.06, advantage: 1.14 },
  { idx: 11, text: "42.", tokenId: 2983, role: "assistant", turnId: 1, lossMask: 1.0, logprob: -0.03, advantage: 1.14 },
];

export const DocsTokenAlignment = (): ReactElement => {
  const [selectedIdx, setSelectedIdx] = useState<number>(3);
  const tok = ALIGNMENT_TOKENS[selectedIdx] ?? ALIGNMENT_TOKENS[3];

  return (
    <figure className="gr-doc-widget" aria-label="Interactive 1:1 token alignment inspector">
      <div className="gr-doc-widget-head">
        <span className="gr-doc-widget-kicker">Token inspector · 12 tokens</span>
        <span className="gr-doc-widget-hint">Click any token to see its values</span>
      </div>

      <div className="gr-doc-token-legend">
        <span>
          <i className="gr-doc-swatch gr-doc-swatch--muted" /> prompt / tool (loss_mask = 0.0)
        </span>
        <span>
          <i className="gr-doc-swatch gr-doc-swatch--ink" /> generated (loss_mask = 1.0)
        </span>
      </div>

      <div className="gr-doc-token-strip" role="listbox" aria-label="Aligned token sequence">
        {ALIGNMENT_TOKENS.map((t) => {
          const isSelected = t.idx === tok.idx;
          const isContext = t.idx < tok.idx;
          return (
            <button
              key={t.idx}
              aria-selected={isSelected}
              className="gr-doc-tok"
              data-active={isSelected ? "true" : undefined}
              data-context={isContext ? "true" : undefined}
              data-trained={t.lossMask > 0 ? "true" : "false"}
              onClick={() => setSelectedIdx(t.idx)}
              role="option"
              type="button"
            >
              <span className="gr-doc-tok-idx">{t.idx}</span>
              <span className="gr-doc-tok-txt">{t.text}</span>
              <span className="gr-doc-tok-role">{t.role}</span>
            </button>
          );
        })}
      </div>

      <div className="gr-doc-inspector">
        <div className="gr-doc-spec-strip gr-doc-spec-strip--5">
          <div>
            <span className="gr-doc-spec-k">tokens[{tok.idx}]</span>
            <code className="gr-doc-spec-v">
              {tok.tokenId} ({tok.text})
            </code>
          </div>
          <div>
            <span className="gr-doc-spec-k">turn_ids[{tok.idx}]</span>
            <code className="gr-doc-spec-v">{tok.turnId}</code>
          </div>
          <div>
            <span className="gr-doc-spec-k">loss_mask[{tok.idx}]</span>
            <code className="gr-doc-spec-v">{tok.lossMask.toFixed(1)}</code>
          </div>
          <div>
            <span className="gr-doc-spec-k">sampling_logprobs[{tok.idx}]</span>
            <code className="gr-doc-spec-v">{tok.logprob.toFixed(2)}</code>
          </div>
          <div>
            <span className="gr-doc-spec-k">advantages[{tok.idx}]</span>
            <code className="gr-doc-spec-v">{tok.advantage.toFixed(2)}</code>
          </div>
        </div>
        <p className="gr-doc-inspector-detail">
          {tok.idx === 0
            ? "Token 0 is the start of the sequence, so it has no preceding tokens and loss_mask[0] is always 0.0."
            : tok.lossMask > 0
              ? `Token ${tok.idx} ("${tok.text}") is predicted from tokens[0..${tok.idx - 1}]. Training updates weights here because loss_mask[${tok.idx}] = 1.0.`
              : `Token ${tok.idx} ("${tok.text}") came from the ${tok.role}, so loss_mask[${tok.idx}] = 0.0: the model sees it as context, but training does not update weights on it.`}
        </p>
      </div>
    </figure>
  );
};

/* ---------------------------------------------------------------------------
   4. Pipelined vs. Sequential GPU Execution Timeline (Custom Loops)
   --------------------------------------------------------------------------- */

export const DocsPipelineDiagram = (): ReactElement => {
  const [mode, setMode] = useState<"pipelined" | "sequential">("pipelined");

  return (
    <figure className="gr-doc-widget" aria-label="Pipelined vs sequential trainer execution">
      <div className="gr-doc-widget-head">
        <span className="gr-doc-widget-kicker">Execution pipelining</span>
        <div className="gr-doc-seg" role="tablist" aria-label="Execution mode">
          <button
            aria-selected={mode === "pipelined"}
            className="gr-doc-seg-btn"
            data-active={mode === "pipelined" ? "true" : undefined}
            onClick={() => setMode("pipelined")}
            role="tab"
            type="button"
          >
            Pipelined (1 RTT)
          </button>
          <button
            aria-selected={mode === "sequential"}
            className="gr-doc-seg-btn"
            data-active={mode === "sequential" ? "true" : undefined}
            onClick={() => setMode("sequential")}
            role="tab"
            type="button"
          >
            Sequential (3 RTTs)
          </button>
        </div>
      </div>

      <div className="gr-doc-timeline">
        {mode === "pipelined" ? (
          <>
            <div className="gr-doc-lane">
              <span className="gr-doc-lane-label">Client</span>
              <div className="gr-doc-lane-track">
                <span className="gr-doc-bar gr-doc-bar--muted" style={{ width: "20%" }}>
                  queue fb + opt
                </span>
                <span className="gr-doc-bar gr-doc-bar--ghost" style={{ width: "68%" }}>
                  wait once (fb.result(), opt.result())
                </span>
                <span className="gr-doc-bar gr-doc-bar--muted" style={{ width: "12%" }}>
                  metrics
                </span>
              </div>
            </div>
            <div className="gr-doc-lane">
              <span className="gr-doc-lane-label">GPU worker</span>
              <div className="gr-doc-lane-track">
                <span className="gr-doc-bar gr-doc-bar--gap" style={{ width: "14%" }} />
                <span className="gr-doc-bar gr-doc-bar--ink" style={{ width: "56%" }}>
                  forward + backward (no idle gap)
                </span>
                <span className="gr-doc-bar gr-doc-bar--accent" style={{ width: "22%" }}>
                  optim_step
                </span>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="gr-doc-lane">
              <span className="gr-doc-lane-label">Client</span>
              <div className="gr-doc-lane-track">
                <span className="gr-doc-bar gr-doc-bar--muted" style={{ width: "18%" }}>
                  fb().result()
                </span>
                <span className="gr-doc-bar gr-doc-bar--gap" style={{ width: "36%" }} />
                <span className="gr-doc-bar gr-doc-bar--muted" style={{ width: "20%" }}>
                  opt().result()
                </span>
              </div>
            </div>
            <div className="gr-doc-lane">
              <span className="gr-doc-lane-label">GPU worker</span>
              <div className="gr-doc-lane-track">
                <span className="gr-doc-bar gr-doc-bar--gap" style={{ width: "14%" }} />
                <span className="gr-doc-bar gr-doc-bar--ink" style={{ width: "36%" }}>
                  fwd + bwd
                </span>
                <span className="gr-doc-bar gr-doc-bar--warn" style={{ width: "24%" }}>
                  idle RTT stall
                </span>
                <span className="gr-doc-bar gr-doc-bar--accent" style={{ width: "18%" }}>
                  optim_step
                </span>
              </div>
            </div>
          </>
        )}
      </div>

      <p className="gr-doc-widget-caption">
        {mode === "pipelined"
          ? "Call forward_backward() and optim_step() before awaiting .result() so the server executes both back-to-back on the GPU without an idle network round trip."
          : "Awaiting forward_backward().result() before issuing optim_step() leaves the GPU idle across the network round trip on every single step."}
      </p>
    </figure>
  );
};

/* ---------------------------------------------------------------------------
   5. Stateful Rollout Lifecycle Schematic (Environments & Rubrics)
   --------------------------------------------------------------------------- */

const ENV_STAGES = [
  {
    id: "setup",
    step: "01",
    name: "setup(task, rollout_id)",
    where: "Your machine / Docker host",
    mask: "None",
    detail:
      "Starts an isolated Docker Compose stack (or leases a warm-pool slot and resets Postgres from a template DB in ~50 ms). Returns a handle holding API/DB URLs.",
  },
  {
    id: "step",
    step: "02",
    name: "snap.sample() ↔ step(handle, action)",
    where: "GPU snapshot + your tools",
    mask: "1.0 model / 0.0 tool",
    detail:
      "Model tokens get loss_mask = 1.0 and exact sampling_logprobs. Returning Observation(text=...) auto-tokenizes tool output on the server and appends it with loss_mask = 0.0.",
  },
  {
    id: "evaluate",
    step: "03",
    name: "evaluate(handle, trajectory)",
    where: "Live containers (pre-teardown)",
    mask: "Scores attached",
    detail:
      "Runs your Rubric BEFORE teardown so stateful checks can query live Postgres rows, Redis keys, or HTTP endpoints and write sub-scores into trajectory.scores.",
  },
  {
    id: "teardown",
    step: "04",
    name: "finally: teardown(handle)",
    where: "Guaranteed cleanup",
    mask: "Returns Trajectory",
    detail:
      "Always executes in a finally block, even on exceptions or timeout_s expiry, so containers, volumes, and warm-pool slots never leak across thousands of rollouts.",
  },
];

export const DocsEnvLifecycle = (): ReactElement => {
  const [stageId, setStageId] = useState<string>("evaluate");
  const active = ENV_STAGES.find((s) => s.id === stageId) ?? ENV_STAGES[0];

  return (
    <figure className="gr-doc-widget" aria-label="Stateful environment rollout lifecycle">
      <div className="gr-doc-widget-head">
        <span className="gr-doc-widget-kicker">Rollout lifecycle · 4 hooks</span>
        <span className="gr-doc-widget-hint">Select a hook to inspect guarantees</span>
      </div>

      <div className="gr-doc-flywheel-grid gr-doc-flywheel-grid--4" role="tablist">
        {ENV_STAGES.map((stage, idx) => {
          const isSelected = stage.id === active.id;
          return (
            <button
              key={stage.id}
              aria-selected={isSelected}
              className="gr-doc-die"
              data-active={isSelected ? "true" : undefined}
              onClick={() => setStageId(stage.id)}
              role="tab"
              type="button"
            >
              <span className="gr-doc-die-num">{stage.step}</span>
              <strong className="gr-doc-die-name">{stage.id}()</strong>
              <span className="gr-doc-die-role">{stage.where}</span>
              {idx < ENV_STAGES.length - 1 ? (
                <span aria-hidden="true" className="gr-doc-die-arrow">
                  →
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="gr-doc-inspector" role="tabpanel">
        <div className="gr-doc-spec-strip">
          <div>
            <span className="gr-doc-spec-k">Hook</span>
            <code className="gr-doc-spec-v">{active.name}</code>
          </div>
          <div>
            <span className="gr-doc-spec-k">Runs on</span>
            <span className="gr-doc-spec-v">{active.where}</span>
          </div>
          <div>
            <span className="gr-doc-spec-k">Loss mask / output</span>
            <code className="gr-doc-spec-v">{active.mask}</code>
          </div>
        </div>
        <p className="gr-doc-inspector-detail">{active.detail}</p>
      </div>
    </figure>
  );
};

/* ---------------------------------------------------------------------------
   6. Interactive Deployment Options Diagram (Cloud vs. Self-hosted vLLM/SGLang)
   --------------------------------------------------------------------------- */

type DeployOption = {
  id: string;
  label: string;
  where: string;
  path: string[];
  detail: string;
  useCase: string;
};

const DEPLOY_OPTIONS: DeployOption[] = [
  {
    id: "cloud",
    label: "Gradiated Cloud",
    where: "Managed GPUs + gateway",
    path: ["Artifact (@v2)", "run.deploy()", "OpenAI / Anthropic / SystemOne SDK", "Active @v2 (1-cmd rollback)", "Auto capture + feedback"],
    detail: "Call your-org/<name> from your existing SDK with zero GPU management and 1-command rollback.",
    useCase: "Teams that want hosted serving, automatic trace capture, and safe rollouts out of the box.",
  },
  {
    id: "self_hosted",
    label: "Your vLLM / SGLang",
    where: "Your GPUs + gateway",
    path: ["Artifact (@v2)", "grad artifacts download", "PEFT LoRA Safetensors", "vLLM / SGLang (--lora-modules)", "Push traces & feedback back"],
    detail: "Standard HuggingFace LoRA or merged weights run on your own servers with your existing load balancer and feature flags.",
    useCase: "Enterprises with strict data residency or an existing vLLM / SGLang inference fleet.",
  },
];

export const DocsDeployFlow = (): ReactElement => {
  const [optionId, setOptionId] = useState<string>("cloud");
  const active = DEPLOY_OPTIONS.find((s) => s.id === optionId) ?? DEPLOY_OPTIONS[0];

  return (
    <figure className="gr-doc-widget" aria-label="Interactive deployment options">
      <div className="gr-doc-widget-head">
        <span className="gr-doc-widget-kicker">Serving options</span>
        <div className="gr-doc-seg" role="tablist" aria-label="Deployment target">
          {DEPLOY_OPTIONS.map((s) => (
            <button
              key={s.id}
              aria-selected={s.id === active.id}
              className="gr-doc-seg-btn"
              data-active={s.id === active.id ? "true" : undefined}
              onClick={() => setOptionId(s.id)}
              role="tab"
              type="button"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="gr-doc-flow" aria-label="Deployment flow">
        {active.path.map((hop, idx) => (
          <div key={hop} className="gr-doc-flow-item">
            <span className="gr-doc-flow-box">{hop}</span>
            {idx < active.path.length - 1 ? (
              <span aria-hidden="true" className="gr-doc-flow-arrow">
                →
              </span>
            ) : null}
          </div>
        ))}
      </div>

      <div className="gr-doc-inspector">
        <div className="gr-doc-spec-strip gr-doc-spec-strip--2">
          <div>
            <span className="gr-doc-spec-k">Runs on</span>
            <span className="gr-doc-spec-v">{active.where}</span>
          </div>
          <div>
            <span className="gr-doc-spec-k">Best for</span>
            <span className="gr-doc-spec-v">{active.useCase}</span>
          </div>
        </div>
        <p className="gr-doc-inspector-detail">
          <strong>How it works:</strong> {active.detail}
        </p>
      </div>
    </figure>
  );
};
