import { Lock } from "lucide-react";
import { useId } from "react";
import type { ReactElement, ReactNode } from "react";

export const PrivateLink = ({
  children,
  href,
}: {
  children: ReactNode;
  href: string;
}): ReactElement => {
  const tip = useId();

  return (
    <span className="gr-private-link-wrap">
      <a
        aria-describedby={tip}
        className="gr-private-link"
        href={href}
        rel="nofollow noreferrer"
      >
        <Lock aria-hidden="true" className="gr-private-link__icon" />
        {children}
      </a>
      <span className="gr-private-link__tip" id={tip} role="tooltip">
        Internal only
      </span>
    </span>
  );
};
