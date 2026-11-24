import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { SectionFab } from "./SectionFab";

export type SectionNavigationItem = {
  href: string;
  label: string;
};

export type SectionNavigationGroup = {
  /** Left out when the list needs no heading, as for a single group. */
  heading?: string;
  items: SectionNavigationItem[];
};

export const SectionNavigation = ({
  ariaLabel,
  current,
  groups,
}: {
  ariaLabel: string;
  current: string;
  groups: SectionNavigationGroup[];
}): ReactElement => (
  <nav aria-label={ariaLabel} className="gr-doc-nav">
    {groups.map((group, index) => (
      <div className="gr-doc-nav-group" key={group.heading ?? index}>
        {group.heading ? (
          <p className="gr-doc-nav-heading gr-label">{group.heading}</p>
        ) : null}
        {group.items.map((item) => (
          <Link
            aria-current={item.href === current ? "page" : undefined}
            className="gr-doc-nav-link"
            key={item.href}
            to={item.href}
          >
            {item.label}
          </Link>
        ))}
      </div>
    ))}
  </nav>
);

export const SectionNavigationFab = ({
  current,
  groups,
  label,
}: {
  current: string;
  groups: SectionNavigationGroup[];
  label: string;
}): ReactElement => (
  <SectionFab label={label}>
    {groups.map((group, index) => (
      <div className="gr-fab-group" key={group.heading ?? index}>
        {group.heading ? (
          <p className="gr-fab-heading gr-label">{group.heading}</p>
        ) : null}
        {group.items.map((item) => (
          <Link
            aria-current={item.href === current ? "page" : undefined}
            className="gr-fab-link"
            key={item.href}
            to={item.href}
          >
            {item.label}
          </Link>
        ))}
      </div>
    ))}
  </SectionFab>
);
