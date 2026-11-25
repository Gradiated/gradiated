import { Fragment, useEffect, useState } from "react";
import type { ReactElement } from "react";
import { Band, Module } from "../components/design";
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

    setFeedback(
      saved
        ? `${voted ? "Vote saved" : "Vote removed"} for ${entry.name ?? entry.category}.`
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
          <p>Every model we release will be open source.</p>
          <table
            aria-labelledby="model-roadmap-title"
            className="gr-roadmap-table"
          >
            <thead>
              <tr>
                <th scope="col">Project</th>
                <th scope="col">Description</th>
                <th scope="col">Access</th>
              </tr>
            </thead>
            <tbody>
              {roadmapEntries.map((entry) => {
                const voted = Boolean(roadmap.votes[entry.id]);

                return (
                  <tr key={entry.id}>
                    <th scope="row">
                      {entry.name ?? entry.category}
                      <br />
                      <small className="gr-muted">
                        {entry.name ? entry.category : "Model"} ·{" "}
                        {entry.release ? (
                          <time dateTime={entry.release.date}>
                            {releaseDate.format(new Date(entry.release.date))}
                          </time>
                        ) : (
                          (entry.status ?? "Roadmap")
                        )}
                      </small>
                    </th>
                    <td>{entry.description}</td>
                    <td>
                      {entry.release ? (
                        entry.release.links.map(({ label, href }, index) => (
                          <Fragment key={href}>
                            {index > 0 && " · "}
                            <a className="gr-link" href={href}>
                              {label}
                            </a>
                          </Fragment>
                        ))
                      ) : (
                        <button
                          aria-label={`Upvote ${entry.name ?? entry.category}`}
                          aria-pressed={voted}
                          className="gr-link"
                          onClick={() => toggleVote(entry)}
                          type="button"
                        >
                          {voted ? "Voted" : "Upvote"}
                        </button>
                      )}
                      {canSuggestName(entry) && (
                        <>
                          <br />
                          <button
                            aria-haspopup="dialog"
                            aria-label={`Suggest a name for ${entry.category}`}
                            className="gr-link"
                            onClick={() => setSuggestion(entry)}
                            type="button"
                          >
                            Suggest a name
                          </button>
                        </>
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
      {suggestion && (
        <ModelNameSuggestion
          entry={suggestion}
          onClose={() => setSuggestion(undefined)}
        />
      )}
    </Band>
  );
};
