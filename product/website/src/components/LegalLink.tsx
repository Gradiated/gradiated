import type { ReactNode } from "react";

type LegalLinkProps = {
  href: string;
  children: ReactNode;
};

export const LegalLink = ({ href, children }: LegalLinkProps): ReactNode => (
  <a className="legal-link" href={href}>
    {children}
  </a>
);
