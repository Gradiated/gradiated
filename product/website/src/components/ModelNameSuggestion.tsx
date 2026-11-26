import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { MODEL_NAME_SUGGESTION_MAX_LENGTH } from "../model-roadmap";
import type { RoadmapEntry } from "../model-roadmap";
import "./model-name-suggestion.css";

const NAME_MAX = 80;
/* The API takes one string; the name and the reason are joined into it. */
const REASON_MAX = MODEL_NAME_SUGGESTION_MAX_LENGTH - NAME_MAX - 3;

/* "Suggest a name": a small centred modal over a blurred page, not a
   drawer. It scales in on open and out on close (the close waits for the
   exit animation, then closes the native dialog, which keeps Escape, focus
   return and the inert page for free). */
export const ModelNameSuggestion = ({
  entry,
  onClose,
}: {
  entry: RoadmapEntry;
  onClose: () => void;
}): ReactElement => {
  const dialog = useRef<HTMLDialogElement>(null);
  const [closing, setClosing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
  }, []);

  const close = () => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (still.matches) {
      dialog.current?.close();
      return;
    }
    setClosing(true);
    window.setTimeout(() => dialog.current?.close(), 180);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;

    const data = new FormData(event.currentTarget);
    const name = String(data.get("name") ?? "").trim();
    const reason = String(data.get("reason") ?? "").trim();
    if (!name) {
      setError("Add a name before sending.");
      return;
    }
    const suggestion = reason ? `${name} — ${reason}` : name;

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
      className="gr-name-modal"
      data-closing={closing || undefined}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      onClose={onClose}
      ref={dialog}
    >
      <div className="gr-name-modal-panel">
        <button
          aria-label="Close"
          className="gr-button gr-button--ghost gr-name-modal-close"
          onClick={close}
          type="button"
        >
          <svg aria-hidden="true" height="12" viewBox="0 0 12 12" width="12">
            <path
              d="m2.5 2.5 7 7m0-7-7 7"
              stroke="currentColor"
              strokeLinecap="round"
              strokeWidth="1.4"
            />
          </svg>
        </button>

        {submitted ? (
          <div className="gr-name-modal-done" role="status">
            <h2
              className="gr-heading gr-name-modal-title"
              id="model-name-suggestion-title"
            >
              Suggestion sent
            </h2>
            <p className="gr-body gr-muted gr-name-modal-lede">
              Thanks. We’ll review your suggestion.
            </p>
            <button
              className="gr-button gr-button--main gr-name-modal-submit"
              onClick={close}
              type="button"
            >
              Done
            </button>
          </div>
        ) : (
          <>
            <p className="gr-label">{entry.category}</p>
            <h2
              className="gr-heading gr-name-modal-title"
              id="model-name-suggestion-title"
            >
              Suggest a name
            </h2>
            <p className="gr-body gr-muted gr-name-modal-lede">
              What should we call our {entry.category.toLowerCase()} model, and
              why?
            </p>
            <form className="gr-name-modal-form" onSubmit={submit}>
              <label className="gr-name-modal-field">
                <span className="gr-label">Name</span>
                <input
                  autoComplete="off"
                  autoFocus
                  maxLength={NAME_MAX}
                  name="name"
                  placeholder="e.g. Juniper"
                  required
                />
              </label>
              <label className="gr-name-modal-field">
                <span className="gr-label">Why (optional)</span>
                <textarea maxLength={REASON_MAX} name="reason" rows={3} />
              </label>
              {error && (
                <p className="gr-name-modal-error" role="alert">
                  {error}
                </p>
              )}
              <button
                className="gr-button gr-button--main gr-name-modal-submit"
                disabled={submitting}
                type="submit"
              >
                {submitting ? "Sending…" : "Send suggestion"}
              </button>
            </form>
          </>
        )}
      </div>
    </dialog>
  );
};
