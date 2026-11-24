import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Band, Module } from "../components/design";

type Model = {
  id: string;
  title: string;
  description: string;
  status?: "In progress";
  release?: { api: string; weights: string };
};

const models: readonly Model[] = [
  {
    id: "task-routing",
    title: "Model router",
    status: "In progress",
    description:
      "Choose a model for each request. Send routine work to open models and reserve frontier calls for work that needs them.",
  },
  {
    id: "security-review",
    title: "Security review",
    description:
      "Flag likely vulnerabilities in first-party diffs and point reviewers to the code that needs attention.",
  },
  {
    id: "code-review",
    title: "Code review",
    description:
      "Review pull requests for regressions, missed edge cases, and gaps in test coverage.",
  },
  {
    id: "diff-merging",
    title: "Diff merging",
    description:
      "Reconcile conflicting edits and surface the decisions that still need a human.",
  },
  {
    id: "context-compaction",
    title: "Context compaction",
    description:
      "Compress long agent sessions while preserving decisions, constraints, and unfinished work.",
  },
  {
    id: "ci-triage",
    title: "CI failure triage",
    description:
      "Find the first meaningful failure in noisy CI logs and distinguish flakes from likely regressions.",
  },
  {
    id: "error-triage",
    title: "Production error triage",
    description:
      "Group related errors and use traces, stack frames, and release context to suggest where to look first.",
  },
  {
    id: "product-analytics",
    title: "Product analytics queries",
    description:
      "Turn questions about funnels, retention, and feature adoption into queries against your event schema.",
  },
];

type RoadmapState = {
  votes: Partial<Record<Model["id"], boolean>>;
};

const storageKey = "gradiated:model-roadmap-preview:v1";
const emptyState: RoadmapState = { votes: {} };

const readRoadmap = (): RoadmapState => {
  try {
    const saved = localStorage.getItem(storageKey);
    return saved ? (JSON.parse(saved) as RoadmapState) : emptyState;
  } catch {
    return emptyState;
  }
};

export const ModelRoadmap = (): ReactElement => {
  const [roadmap, setRoadmap] = useState(emptyState);
  const [feedback, setFeedback] = useState("");

  useEffect(() => {
    setRoadmap(readRoadmap());

    const sync = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null)
        setRoadmap(readRoadmap());
    };

    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const save = (next: RoadmapState) => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      return false;
    }

    setRoadmap(next);
    return true;
  };

  const toggleVote = (model: Model) => {
    const current = readRoadmap();
    const voted = !current.votes[model.id];
    const saved = save({
      ...current,
      votes: { ...current.votes, [model.id]: voted },
    });

    setFeedback(
      saved
        ? `${voted ? "Vote saved" : "Vote removed"} for ${model.title}.`
        : "This browser could not save your vote.",
    );
  };

  return (
    <Band>
      <Module id="model-roadmap" index={1}>
        <div className="gr-prose">
          <header>
            <h2 className="gr-heading" id="model-roadmap-title">
              Model roadmap
            </h2>
          </header>
          <p>Every model on this roadmap will be open source.</p>
          <table
            aria-labelledby="model-roadmap-title"
            className="gr-roadmap-table"
          >
            <thead>
              <tr>
                <th scope="col">Model</th>
                <th scope="col">Description</th>
                <th scope="col">Access</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => {
                const voted = Boolean(roadmap.votes[model.id]);

                return (
                  <tr key={model.id}>
                    <th scope="row">
                      {model.title}
                      <br />
                      <small className="gr-muted">
                        {model.status ?? "Roadmap"}
                      </small>
                    </th>
                    <td>{model.description}</td>
                    <td>
                      {model.release ? (
                        <>
                          <a className="gr-link" href={model.release.api}>
                            API
                          </a>
                          {" · "}
                          <a className="gr-link" href={model.release.weights}>
                            Weights
                          </a>
                        </>
                      ) : (
                        <button
                          aria-label={`Upvote ${model.title}`}
                          aria-pressed={voted}
                          className="gr-link"
                          onClick={() => toggleVote(model)}
                          type="button"
                        >
                          {voted ? "Voted" : "Upvote"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="gr-muted">Preview votes are saved in this browser.</p>
          <span className="gr-visually-hidden" role="status">
            {feedback}
          </span>
        </div>
      </Module>
    </Band>
  );
};
