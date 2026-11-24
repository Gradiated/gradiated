import { Children, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";
import { PixelIcon } from "./PixelIcon";

// MDX hands the first line over as a <p>; its contents become the toggle.
const unwrap = (node: ReactNode): ReactNode =>
  isValidElement<{ children?: ReactNode }>(node) ? node.props.children : node;

export const Expandable = ({
  children,
}: {
  children: ReactNode;
}): ReactElement => {
  const [first, ...rest] = Children.toArray(children);

  return (
    <details className="gr-expandable">
      <summary className="gr-expandable__summary">
        <span>{unwrap(first)}</span>
        <PixelIcon className="gr-expandable__arrow" name="caret-right" />
      </summary>
      <div className="gr-expandable__body">{rest}</div>
    </details>
  );
};
