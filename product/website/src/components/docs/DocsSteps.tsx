import { Children, isValidElement, useEffect, useState } from "react";
import type { ReactElement, ReactNode } from "react";

type StepProps = { children: ReactNode; title: string };

export const DocsStep = ({ children }: StepProps): ReactElement => (
  <>{children}</>
);

const slugify = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

/* Numbered steps a reader can tick off. Progress is kept in this browser
   only, per page, so coming back to a tutorial shows where they stopped. */
export const DocsSteps = ({
  children,
  id,
}: {
  children: ReactNode;
  id: string;
}): ReactElement => {
  const steps = Children.toArray(children).filter(
    (child): child is ReactElement<StepProps> =>
      isValidElement<StepProps>(child),
  );
  const key = `gradiated.docs.steps.${id}`;
  const [done, setDone] = useState<string[]>([]);

  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(
        window.localStorage.getItem(key) ?? "[]",
      );
      if (Array.isArray(saved))
        setDone(saved.filter((v) => typeof v === "string"));
    } catch {
      // Storage blocked or unreadable: start with nothing ticked.
    }
  }, [key]);

  const save = (next: string[]) => {
    setDone(next);
    try {
      window.localStorage.setItem(key, JSON.stringify(next));
    } catch {
      // Not remembered, but the page still ticks.
    }
  };

  const count = steps.filter((step) => done.includes(step.props.title)).length;

  return (
    <div className="gr-doc-steps">
      <p aria-live="polite" className="gr-doc-steps-progress">
        <span>
          {count} of {steps.length} done
        </span>
        <span
          aria-hidden="true"
          className="gr-doc-steps-bar"
          style={{ ["--done" as string]: `${(count / steps.length) * 100}%` }}
        />
        {count ? (
          <button onClick={() => save([])} type="button">
            Start over
          </button>
        ) : null}
      </p>
      <ol className="gr-doc-steps-list">
        {steps.map((step, index) => {
          const { title } = step.props;
          const checked = done.includes(title);
          const anchor = slugify(title);
          return (
            <li
              className="gr-doc-step"
              data-done={checked || undefined}
              key={title}
            >
              <h3 className="gr-doc-heading gr-doc-step-title" id={anchor}>
                <span className="gr-doc-step-number">{index + 1}</span>
                {title}
                <a
                  aria-label={`Link to ${title}`}
                  className="gr-doc-anchor"
                  href={`#${anchor}`}
                >
                  #
                </a>
              </h3>
              <div className="gr-doc-step-body">{step.props.children}</div>
              <label className="gr-doc-step-check">
                <input
                  checked={checked}
                  onChange={() =>
                    save(
                      checked
                        ? done.filter((value) => value !== title)
                        : [...done, title],
                    )
                  }
                  type="checkbox"
                />
                {checked ? "Done" : "Mark as done"}
              </label>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
