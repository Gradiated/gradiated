import type { ReactNode } from "react";

type SiteLinkProps = {
  href: string;
  children: ReactNode;
};

export const SiteLink = ({ href, children }: SiteLinkProps): ReactNode => (
  <a className="site-link" href={href}>
    {children}
  </a>
);
