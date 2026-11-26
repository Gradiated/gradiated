import { useEffect, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import { Arrow, Band, Module, PixelIcon } from "../components/design";
import { ModelNameSuggestion } from "../components/ModelNameSuggestion";
import { canSuggestName, roadmapEntries } from "../model-roadmap";
import type { RoadmapEntry } from "../model-roadmap";

type RoadmapState = {
  votes: Partial<Record<RoadmapEntry["id"], boolean>>;
};

const releaseDate = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeZone: "UTC",
});

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
  const [suggestion, setSuggestion] = useState<RoadmapEntry>();

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

  const toggleVote = (entry: RoadmapEntry) => {
    const current = readRoadmap();
    const voted = !current.votes[entry.id];
    const saved = save({
      ...current,
      votes: { ...current.votes, [entry.id]: voted },
    });
    // Each upvote goes to the team's Slack; removing one is local only.
    if (voted)
      void fetch("/api/model-name-suggestions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelId: entry.id, vote: "up" }),
      }).catch(() => undefined);

    setFeedback(
      saved
        ? `${voted ? "Vote saved" : "Vote removed"} for ${entry.name ?? entry.category}.`
        : "This browser could not save your vote.",
    );
  };

  return (
    <Band>
      <Module id="model-roadmap" index={1}>
        {/* As designed (Figma "New Home"): a small capitals eyebrow over the
            promise, centred. The eyebrow names the table. */}
        <header className="gr-roadmap-head">
          <p className="gr-roadmap-eyebrow" id="model-roadmap-title">
            Model roadmap
          </p>
          <h2 className="gr-display gr-roadmap-title">
            Every model we release will be open source.
          </h2>
        </header>
        <div className="gr-roadmap">
          <table
            aria-labelledby="model-roadmap-title"
            className="gr-roadmap-table"
          >
            <thead>
              <tr>
                <th className="gr-label" scope="col">
                  Model
                </th>
                <th className="gr-label" scope="col">
                  What it does
                </th>
                <th className="gr-label" scope="col">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {roadmapEntries.map((entry) => {
                const voted = Boolean(roadmap.votes[entry.id]);
                const title = entry.name ?? entry.category;

                return (
                  <tr key={entry.id}>
                    <th scope="row">
                      <span className="gr-roadmap-name">{title}</span>
                      <span className="gr-roadmap-meta">
                        {entry.name ? entry.category : "Model"}
                      </span>
                    </th>
                    <td>
                      <div className="gr-roadmap-desc">
                        {/* The status sits over the description, so the row's
                            weight is spread across both text columns. */}
                        <span
                          className={`gr-badge${entry.status ? " gr-badge--emphasis" : ""}`}
                        >
                          {entry.release ? (
                            <>
                              {/* The badge is a flex box, which trims edge spaces: the
                                  one before the date is non-breaking. */}
                              {"Released ·\u00a0"}
                              <time dateTime={entry.release.date}>
                                {releaseDate.format(
                                  new Date(entry.release.date),
                                )}
                              </time>
                            </>
                          ) : (
                            (entry.status ?? "Roadmap")
                          )}
                        </span>
                        <span className="gr-roadmap-copy">
                          {entry.description}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="gr-roadmap-actions">
                        {entry.release ? (
                          entry.release.links.map(({ label, href }) => (
                            <a
                              className="gr-button gr-button--secondary"
                              href={href}
                              key={href}
                            >
                              {label} <Arrow />
                            </a>
                          ))
                        ) : (
                          <button
                            aria-label={`Upvote ${title}`}
                            aria-pressed={voted}
                            className={`gr-button ${voted ? "gr-button--main" : "gr-button--secondary"}`}
                            onClick={() => toggleVote(entry)}
                            type="button"
                          >
                            {voted ? (
                              <PixelIcon name="check" />
                            ) : (
                              <svg
                                aria-hidden="true"
                                className="gr-pixel-icon gr-roadmap-plus"
                                fill="currentColor"
                                shapeRendering="crispEdges"
                                style={{ "--cells": 11 } as CSSProperties}
                                viewBox="0 0 11 11"
                              >
                                <path d="M4 0h3v4h4v3H7v4H4V7H0V4h4z" />
                              </svg>
                            )}
                            {voted ? "Upvoted" : "Upvote"}
                          </button>
                        )}
                        {canSuggestName(entry) && (
                          <button
                            aria-haspopup="dialog"
                            aria-label={`Suggest a name for ${entry.category}`}
                            className="gr-button gr-button--ghost"
                            onClick={() => setSuggestion(entry)}
                            type="button"
                          >
                            <PixelIcon name="lightbulb" />
                            Name it
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <span className="gr-visually-hidden" role="status">
            {feedback}
          </span>
        </div>
      </Module>
      {suggestion && (
        <ModelNameSuggestion
          entry={suggestion}
          onClose={() => setSuggestion(undefined)}
        />
      )}
    </Band>
  );
};
