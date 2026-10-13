import { useEffect, useState } from "react";
import type { FormEvent, ReactElement } from "react";
import { Arrow } from "./design";

/**
 * The application form at the foot of a job posting.
 *
 * The questions come from the job's application form in Ashby, so adding or
 * changing a question there needs no change here. Answers go to /api/apply,
 * which hands them to Ashby. Built on the design system's field components
 * (gr-field, gr-input, ...) and laid out by .gr-apply-form in pages.css.
 */

type AshbyField = {
  path: string;
  title: string;
  type: string;
  required: boolean;
  description: string;
  options: { label: string; value: string }[];
};

const MAX_FILE_BYTES = 4 * 1024 * 1024;
const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];
/** Short answers sit two to a row on wide screens; these always take the full row. */
const FULL_WIDTH = new Set(["LongText", "File", "MultiValueSelect", "Boolean"]);

const inputType = (type: string): string =>
  ({ Email: "email", Phone: "tel", Number: "number", Date: "date", SocialLink: "url" })[type] ??
  "text";

const Control = ({ field }: { field: AshbyField }): ReactElement => {
  const shared = { id: field.path, name: field.path, required: field.required };

  switch (field.type) {
    case "LongText":
      return <textarea {...shared} className="gr-textarea" rows={6} />;
    case "File":
      return <input {...shared} className="gr-input" type="file" accept=".pdf,.doc,.docx" />;
    case "ValueSelect":
      return (
        <select {...shared} className="gr-select" defaultValue="">
          <option disabled value="">
            Select
          </option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    case "Boolean":
      return (
        <div className="gr-apply-choices" role="radiogroup" aria-labelledby={`${field.path}-label`}>
          <label>
            <input name={`${field.path}::boolean`} required={field.required} type="radio" value="true" /> Yes
          </label>
          <label>
            <input name={`${field.path}::boolean`} type="radio" value="false" /> No
          </label>
        </div>
      );
    case "MultiValueSelect":
      return (
        <div className="gr-apply-choices" aria-labelledby={`${field.path}-label`}>
          {field.options.map((option) => (
            <label key={option.value}>
              <input name={`${field.path}[]`} type="checkbox" value={option.value} /> {option.label}
            </label>
          ))}
        </div>
      );
    default:
      return <input {...shared} className="gr-input" type={inputType(field.type)} />;
  }
};

export const ApplyForm = ({ jobPostingId }: { jobPostingId: string }): ReactElement => {
  const [fields, setFields] = useState<AshbyField[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const [blockedHtml, setBlockedHtml] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/ashby-form?jobPostingId=${encodeURIComponent(jobPostingId)}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: { fields: AshbyField[] }) => setFields(data.fields))
      .catch(() => setLoadFailed(true));
  }, [jobPostingId]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);

    for (const value of form.values()) {
      if (typeof value !== "string" && value.size > MAX_FILE_BYTES) {
        setError("That file is a bit big, please keep it under 4MB.");
        return;
      }
    }

    form.append("jobPostingId", jobPostingId);
    const params = new URLSearchParams(window.location.search);
    for (const key of UTM_KEYS) {
      const value = params.get(key);
      if (value) form.append(key, value);
    }

    setState("sending");
    setError(null);
    try {
      const res = await fetch("/api/apply", { method: "POST", body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.success) throw new Error(String(res.status));
      if (data.blocked && data.blockMessageForCandidateHtml) {
        setBlockedHtml(data.blockMessageForCandidateHtml);
      }
      setState("done");
    } catch {
      setState("idle");
      setError("Something went wrong sending that. Please try again.");
    }
  };

  if (loadFailed) {
    return (
      <p className="gr-job-apply-body gr-muted">
        The application form didn&apos;t load. Please refresh the page or try again shortly.
      </p>
    );
  }

  if (!fields) {
    return <p className="gr-job-apply-body gr-muted">Loading the application form</p>;
  }

  if (state === "done") {
    return blockedHtml ? (
      <div className="gr-job-apply-body gr-muted" dangerouslySetInnerHTML={{ __html: blockedHtml }} />
    ) : (
      <p className="gr-job-apply-body">Thanks, we&apos;ve got your application. We&apos;ll be in touch soon.</p>
    );
  }

  return (
    <form className="gr-apply-form" onSubmit={onSubmit}>
      {fields.map((field) => (
        <div
          className={`gr-field${FULL_WIDTH.has(field.type) ? " gr-apply-form-wide" : ""}`}
          key={field.path}
        >
          <label className="gr-label" htmlFor={field.path} id={`${field.path}-label`}>
            {field.title}
            {field.required ? " *" : ""}
          </label>
          <Control field={field} />
          {field.description ? <span className="gr-field-hint">{field.description}</span> : null}
        </div>
      ))}

      {error ? <p className="gr-field-error gr-apply-form-wide">{error}</p> : null}

      <div className="gr-apply-form-wide gr-apply-form-submit">
        <button className="gr-button gr-button--main" disabled={state === "sending"} type="submit">
          {state === "sending" ? "Sending" : "Send application"}
          <Arrow />
        </button>
      </div>
    </form>
  );
};
