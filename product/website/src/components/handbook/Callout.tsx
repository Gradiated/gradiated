import { Lightbulb, ListChecks, TriangleAlert } from "lucide-react";
import type { ReactElement, ReactNode } from "react";

const icons = {
  action: ListChecks,
  caution: TriangleAlert,
  fyi: Lightbulb,
};

export const Callout = ({
  children,
  title,
  type = "fyi",
}: {
  children: ReactNode;
  title?: string;
  type?: keyof typeof icons;
}): ReactElement => {
  const Icon = icons[type];

  return (
    <aside className={`gr-callout gr-callout--${type}`}>
      <Icon aria-hidden="true" className="gr-callout__icon" />
      <div className="gr-callout__body">
        {title ? <p className="gr-callout__title">{title}</p> : null}
        {children}
      </div>
    </aside>
  );
};
