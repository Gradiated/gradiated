import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { MODEL_NAME_SUGGESTION_MAX_LENGTH } from "../model-roadmap";
import type { RoadmapEntry } from "../model-roadmap";
import "./waitlist.css";

export const ModelNameSuggestion = ({
  entry,
  onClose,
}: {
  entry: RoadmapEntry;
  onClose: () => void;
}): ReactElement => {
  const dialog = useRef<HTMLDialogElement>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    const suggestion = String(
      new FormData(event.currentTarget).get("suggestion"),
    ).trim();
    if (!suggestion) {
      setError("Add a name before submitting.");
      return;
    }

    setError("");
    setSubmitting(true);
    try {
      const response = await fetch("/api/model-name-suggestions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modelId: entry.id, suggestion }),
      });

      if (response.status !== 204) {
        setError(
          response.status === 429
            ? "Too many suggestions. Please wait a minute and try again."
            : "We couldn’t send your suggestion. Please try again later.",
        );
        return;
      }

      setSubmitted(true);
    } catch {
      setError("We couldn’t send your suggestion. Please try again later.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <dialog
      aria-labelledby="model-name-suggestion-title"
      className="gr-waitlist-drawer"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close();
      }}
      ref={dialog}
    >
      <div className="gr-waitlist-body">
        {submitted ? (
          <div className="gr-waitlist-done" role="status">
            <h2 className="gr-heading" id="model-name-suggestion-title">
              Suggestion sent
            </h2>
            <p className="gr-body gr-muted">
              Thanks. We’ll review your suggestion.
            </p>
            <button
              className="gr-button gr-button--main gr-waitlist-submit"
              onClick={() => dialog.current?.close()}
              type="button"
            >
              Done
            </button>
          </div>
        ) : (
          <>
            <header className="gr-waitlist-head">
              <h2 className="gr-heading" id="model-name-suggestion-title">
                Suggest a name
              </h2>
              <p className="gr-body gr-muted">
                We’ll review your suggestion for {entry.category}.
              </p>
            </header>
            <form className="gr-waitlist-form" onSubmit={submit}>
              <label>
                What should we call it, and why?
                <textarea
                  maxLength={MODEL_NAME_SUGGESTION_MAX_LENGTH}
                  name="suggestion"
                  required
                  rows={4}
                />
              </label>
              {error && (
                <p className="gr-waitlist-error" role="alert">
                  {error}
                </p>
              )}
              <button
                className="gr-button gr-button--main gr-waitlist-submit"
                disabled={submitting}
                type="submit"
              >
                {submitting ? "Sending…" : "Send suggestion"}
              </button>
              <button
                className="gr-button gr-button--secondary"
                onClick={() => dialog.current?.close()}
                type="button"
              >
                Cancel
              </button>
            </form>
          </>
        )}
      </div>
    </dialog>
  );
};
