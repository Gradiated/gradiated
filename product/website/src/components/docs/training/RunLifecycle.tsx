import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactElement } from "react";
import { Link } from "react-router-dom";

import { useSdkLanguage } from "../DocsLanguage";
import { CodeSample } from "./CodeSample";
import type { SdkLanguage } from "./data";

type Station = {
  id: string;
  name: string;
  gives: string;
  what: string;
  cli: string;
  sdk: Record<Exclude<SdkLanguage, "CLI">, string>;
  output?: string;
  outputLabel?: string;
  href: string;
};

/* The plan output is print_plan's text form of grad's train_dry_run CLI
   snapshot (cli/tests/snapshots/train_dry_run.json). */
const STATIONS: Station[] = [
  {
    id: "traces",
    name: "Traces",
    gives: "records",
    what: "Production logs or labeled examples, as chat records. Push a file, import from Hugging Face, or sync Langfuse, LangSmith, Braintrust, PostHog or Phoenix on a schedule.",
    cli: "grad import ./traces.jsonl --dataset support-prod",
    sdk: {
      Python: 'client.datasets.push("support-prod", "./traces.jsonl")',
      TypeScript: 'await dataset.importFile("./traces.jsonl").wait();',
      Go: 'dataset.ImportFile(ctx, "./traces.jsonl").Wait(ctx)',
      Rust: 'client.datasets().push_file("support-prod", path, &opts, |_| {}).await?;',
    },
    href: "/docs/training/trajectories/",
  },
  {
    id: "dataset",
    name: "Dataset",
    gives: "@3, immutable",
    what: "Every push, import or sync adds an immutable version, and a run pins one, so you can always say what a model learned from. Preview which tokens will train before you pay for anything.",
    cli: "grad render support-prod --model qwen/qwen3-8b",
    sdk: {
      Python: 'client.datasets.render(dataset, model="qwen/qwen3-8b")',
      TypeScript: 'await dataset.render({ model: "qwen/qwen3-8b" });',
      Go: 'client.Datasets.Render(ctx, "support-prod", grad.RenderOptions{Model: "qwen/qwen3-8b"})',
      Rust: 'client.datasets().render("support-prod", &request).await?;',
    },
    href: "/docs/training/trajectories/",
  },
  {
    id: "plan",
    name: "Plan",
    gives: "$0 estimate",
    what: "A dry run resolves every default, checks your records, splits train and eval by session, and prices the run in tokens. Nothing starts and nothing is billed.",
    cli: "grad train --dataset support-prod --name support-router --recipe router --dry-run",
    sdk: {
      Python:
        'client.runs.plan(dataset=dataset, name="support-router", recipe=RouterRecipe())',
      TypeScript:
        'await grad.runs.plan({ dataset, name: "support-router", recipe: recipes.router() });',
      Go: "client.Runs.Plan(ctx, params)",
      Rust: "client.runs().plan(&request).await?;",
    },
    outputLabel: "Output",
    output: `Plan for support-router (router on qwen/qwen3-0.6b, dataset support-prod v3)
  records   : 4,820 usable of 4,820
  split     : 4,097 train / 723 eval (by_session, 15% held out)
  steps     : 33 (batch 128, 1 epoch)
  lr        : 5.0e-4 (auto)
  tokens    : ~1.1M (62.0% trained)
  est. cost : $0.17 at $0.15/1M tokens
  adapter   : kind=lora, rank=32
  warnings:
    - 3 records have no scores
  Start it by re-running without --dry-run (add --wait to follow it).`,
    href: "/docs/training/recipes/",
  },
  {
    id: "run",
    name: "Run",
    gives: "checkpoints",
    what: "The run waits for a GPU, trains, evaluates on the held-out split and checkpoints as it goes. If the worker is lost it requeues and resumes from the last checkpoint; at max_cost_usd it stops with stopped_budget and keeps a checkpoint.",
    cli: "grad train --dataset support-prod --name support-router --recipe router --max-cost-usd 20 --wait",
    sdk: {
      Python:
        "client.runs.create(dataset=dataset, name=..., recipe=..., max_cost_usd=20).wait()",
      TypeScript:
        "await grad.runs.create({ dataset, name, recipe, maxCostUsd: 20 }).wait();",
      Go: "client.Runs.Create(ctx, params).Wait(ctx)",
      Rust: "client.runs().wait(&run.id, &WaitOptions::default()).await?;",
    },
    href: "/docs/training/tuning-troubleshooting/",
  },
  {
    id: "artifact",
    name: "Artifact",
    gives: ".grad bundle",
    what: "The best checkpoint by held-out eval, as a versioned .grad bundle: a PEFT LoRA adapter, merged weights, or a task bundle for routers and decision models. Its manifest records the base model, template and training settings.",
    cli: "grad artifacts download support-router@latest --output ./support-router",
    sdk: {
      Python: 'run.download("./support-router")',
      TypeScript: 'await run.download("./support-router");',
      Go: 'run.Download(ctx, "./support-router")',
      Rust: 'client.artifacts().download("support-router@latest", &DownloadOptions::extract("./support-router")).await?;',
    },
    href: "/docs/training/artifacts/",
  },
  {
    id: "eval",
    name: "Evaluate",
    gives: "scorecard",
    what: "Score the artifact against its base and any other model on held-out tasks, with confidence intervals, pass@k and cost per thousand tasks.",
    cli: "grad eval --models qwen/qwen3-8b,support-sft@latest --dataset sql-eval-holdout --rubric ./rubric.yaml --wait",
    sdk: {
      Python:
        "client.evals.create(dataset=..., models=[...], rubric=...).wait()",
      TypeScript:
        "await grad.evals.create({ dataset, models, rubric }).wait();",
      Go: "client.Evals.Create(ctx, params).Wait(ctx)",
      Rust: "client.evals().create(&request).await?;",
    },
    href: "/docs/training/evaluations/",
  },
  {
    id: "serve",
    name: "Serve",
    gives: "next version",
    what: "Serve the adapter on your own vLLM or SGLang and log outcomes in your observability tool. A source sync turns them into the next dataset version, and the loop starts again. Hosted serving on Gradiated Cloud is coming soon.",
    cli: "vllm serve Qwen/Qwen3-8B --enable-lora --lora-modules support-sft=./support-sft",
    sdk: {
      Python: "source.sync().wait()  # traces + scores become support-prod@4",
      TypeScript:
        "await source.sync().wait(); // traces + scores become support-prod@4",
      Go: "source.Sync(ctx).Wait(ctx) // traces + scores become support-prod@4",
      Rust: "client.sources().sync(&source.id, false).await?; // support-prod@4",
    },
    href: "/docs/training/deploying/",
  },
];

const RUN_PHASES = [
  { id: "queued", label: "Waiting for a GPU" },
  { id: "training", label: "Training, eval every 10% of steps" },
  { id: "checkpoint", label: "Checkpoint saved" },
  { id: "lost", label: "Worker lost: attempt 2 requeued" },
  { id: "resume", label: "Resumed from the last checkpoint" },
  { id: "completed", label: "Completed: best checkpoint selected" },
];

export const RunLifecycle = ({
  start = "plan",
}: {
  start?: string;
}): ReactElement => {
  const initial = Math.max(
    0,
    STATIONS.findIndex((station) => station.id === start),
  );
  const [active, setActive] = useState(initial);
  const [phase, setPhase] = useState(0);
  const [playing, setPlaying] = useState(false);
  const language = useSdkLanguage();
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  const panelId = useId();
  const station = STATIONS[active];

  useEffect(() => {
    if (!playing) return;

    const timer = window.setTimeout(
      () => {
        if (station.id === "run" && phase < RUN_PHASES.length - 1) {
          setPhase(phase + 1);
          return;
        }
        if (active === STATIONS.length - 1) {
          setPlaying(false);
          return;
        }
        setActive(active + 1);
        setPhase(0);
      },
      station.id === "run" ? 1100 : 2600,
    );
    return () => window.clearTimeout(timer);
  }, [playing, active, phase, station.id]);

  const select = (index: number) => {
    setActive(index);
    setPhase(STATIONS[index].id === "run" ? 0 : phase);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const keys: Record<string, number> = {
      ArrowRight: active + 1,
      ArrowLeft: active - 1,
      Home: 0,
      End: STATIONS.length - 1,
    };
    const next = keys[event.key];
    if (next === undefined) return;

    event.preventDefault();
    const index = (next + STATIONS.length) % STATIONS.length;
    setPlaying(false);
    select(index);
    tabs.current[index]?.focus();
  };

  const sdkLine =
    language === "CLI" ? null : { code: station.sdk[language], lang: language };

  return (
    <figure className="gr-dx gr-dx-life">
      <div className="gr-dx-life-track">
        <div
          aria-label="Training lifecycle"
          className="gr-dx-life-stations"
          role="tablist"
        >
          {STATIONS.map((item, index) => (
            <button
              aria-controls={panelId}
              aria-selected={index === active}
              className="gr-dx-life-station"
              data-past={index < active ? "true" : undefined}
              key={item.id}
              onClick={() => {
                setPlaying(false);
                select(index);
              }}
              onKeyDown={onKeyDown}
              ref={(element) => {
                tabs.current[index] = element;
              }}
              role="tab"
              tabIndex={index === active ? 0 : -1}
              type="button"
            >
              <span aria-hidden="true" className="gr-dx-life-mark" />
              <span className="gr-dx-life-name">{item.name}</span>
              <span className="gr-dx-life-gives">{item.gives}</span>
            </button>
          ))}
        </div>
        <div aria-hidden="true" className="gr-dx-life-loop">
          <span>next sync: support-prod@4</span>
        </div>
      </div>

      <div className="gr-dx-life-panel" id={panelId} role="tabpanel">
        <div className="gr-dx-life-copy">
          <p className="gr-dx-life-step">
            {active + 1} / {STATIONS.length}
          </p>
          <h3>{station.name}</h3>
          <p>{station.what}</p>

          {station.id === "run" ? (
            <ol className="gr-dx-life-phases">
              {RUN_PHASES.map((item, index) => (
                <li
                  data-state={
                    index < phase ? "done" : index === phase ? "now" : undefined
                  }
                  data-tone={item.id === "lost" ? "warn" : undefined}
                  key={item.id}
                >
                  <button
                    onClick={() => {
                      setPlaying(false);
                      setPhase(index);
                    }}
                    type="button"
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ol>
          ) : null}

          <div className="gr-dx-life-nav">
            <button
              className="gr-dx-button"
              onClick={() => {
                if (playing) {
                  setPlaying(false);
                  return;
                }
                if (active === STATIONS.length - 1) {
                  setActive(0);
                  setPhase(0);
                }
                setPlaying(true);
              }}
              type="button"
            >
              {playing ? "Pause" : "Walk through it"}
            </button>
            <Link className="gr-dx-more" to={station.href}>
              {station.name}: read more
            </Link>
          </div>
        </div>

        <div className="gr-dx-life-code">
          <CodeSample
            code={station.cli}
            lang="bash"
            label={station.id === "serve" ? "Shell" : "CLI"}
          />
          {sdkLine ? (
            <CodeSample
              code={sdkLine.code}
              lang={
                {
                  Python: "python",
                  TypeScript: "typescript",
                  Go: "go",
                  Rust: "rust",
                }[sdkLine.lang]
              }
              label={sdkLine.lang}
            />
          ) : null}
          {station.output ? (
            <div className="gr-dx-output">
              <span className="gr-dx-small-label">{station.outputLabel}</span>
              <pre>{station.output}</pre>
            </div>
          ) : null}
        </div>
      </div>
    </figure>
  );
};

export default RunLifecycle;
