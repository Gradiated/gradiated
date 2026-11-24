import type { ReactElement, ReactNode } from "react";
import { PixelIcon } from "../design/PixelIcon";

const icons = {
  action: "list-checks",
  caution: "warning",
  fyi: "lightbulb",
} as const;

export const Callout = ({
  children,
  title,
  type = "fyi",
}: {
  children: ReactNode;
  title?: string;
  type?: keyof typeof icons;
}): ReactElement => {
  return (
    <aside className={`gr-callout gr-callout--${type}`}>
      <PixelIcon className="gr-callout__icon" name={icons[type]} />
      <div className="gr-callout__body">
        {title ? <p className="gr-callout__title">{title}</p> : null}
        {children}
      </div>
    </aside>
  );
};
