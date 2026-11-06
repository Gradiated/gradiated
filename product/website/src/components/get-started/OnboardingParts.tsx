import type { ReactNode } from "react";

export const OnboardingHelp = ({ step }: { step: string }) => (
  <p className="gs-help">
    Stuck?{" "}
    <a
      href={`mailto:help@gradiated.com?subject=${encodeURIComponent(`Help with Gradiated setup: ${step}`)}`}
    >
      Email us
    </a>
  </p>
);

export const Field = ({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) => (
  <label className="gs-field">
    <span>{label}</span>
    {children}
    {hint && <small>{hint}</small>}
  </label>
);

export const StepTitle = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) => (
  <div className="gs-step-title">
    <h1>{title}</h1>
    <p>{children}</p>
  </div>
);
