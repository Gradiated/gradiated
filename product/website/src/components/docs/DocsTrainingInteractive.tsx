import { Suspense, lazy, useEffect, useState } from "react";
import type { ComponentType, ReactElement, ReactNode } from "react";

/* A note in the margin of the text, not a banner: a rule, a label, the words.
   "Coming soon" labels get their own quiet tone so unbuilt features read the
   same way on every page. */
export const DocsCallout = ({
  children,
  label = "Note",
  tone,
}: {
  children: ReactNode;
  label?: string;
  tone?: "note" | "tip" | "warn";
}): ReactElement => {
  const soon = /^coming soon/i.test(label);
  const resolved = soon ? "soon" : (tone ?? "note");

  return (
    <aside className={`gr-doc-callout gr-doc-callout--${resolved}`}>
      <p className="gr-doc-callout-label">{label}</p>
      <div className="gr-doc-callout-body">{children}</div>
    </aside>
  );
};

/* A command and what it printed, as one object. */
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
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => setCopied(false));
  };

  return (
    <figure className="gr-doc-terminal">
      {command ? (
        <div className="gr-doc-terminal-cmd">
          <span aria-hidden="true" className="gr-doc-terminal-prompt">
            $
          </span>
          <code>{command}</code>
          <button
            className="gr-doc-terminal-copy"
            onClick={copyCommand}
            type="button"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      ) : null}
      <figcaption className="gr-doc-terminal-title">{title}</figcaption>
      <div className="gr-doc-terminal-out">{children}</div>
    </figure>
  );
};

/* The widgets load on demand: none of them is needed to read the page, and the
   docs shouldn't pay for every widget on every page. The placeholder holds the
   widget's height so the text under it doesn't jump when it arrives. */
const deferred = <P extends object>(
  load: () => Promise<{ default: ComponentType<P> }>,
  minHeight: number,
) => {
  const Widget = lazy(load);

  /* Mounted after hydration: a lazy component suspending during the server
     render makes React give up on the boundary (error #419) and log it. */
  const Deferred = (props: P): ReactElement => {
    const [mounted, setMounted] = useState(false);
    useEffect(() => setMounted(true), []);

    const placeholder = (
      <div
        aria-hidden="true"
        className="gr-dx gr-dx-placeholder"
        style={{ minHeight }}
      />
    );
    if (!mounted) return placeholder;

    return (
      <Suspense fallback={placeholder}>
        <Widget {...props} />
      </Suspense>
    );
  };

  return Deferred;
};

export const DocsRunLifecycle = deferred(
  () => import("./training/RunLifecycle"),
  520,
);

export const DocsRecipeFinder = deferred(
  () => import("./training/RecipeFinder"),
  640,
);

export const DocsCostEstimator = deferred(
  () => import("./training/CostEstimator"),
  560,
);

export const DocsTokenMask = deferred(
  () => import("./training/TokenMask"),
  480,
);

export const DocsRunReplay = deferred(
  () => import("./training/RunReplay"),
  560,
);

export const DocsRouterFrontier = deferred(
  () => import("./training/RouterFrontier"),
  520,
);

export const DocsPipelineSchematic = deferred<object>(
  () =>
    import("./training/Schematics").then((module) => ({
      default: module.PipelineSchematic,
    })),
  260,
);

export const DocsDatumAnatomy = deferred<object>(
  () =>
    import("./training/Schematics").then((module) => ({
      default: module.DatumAnatomy,
    })),
  260,
);
