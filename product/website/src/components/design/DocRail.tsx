import type { ReactElement, ReactNode } from "react";
import { Arrow } from "./icons";
import "../../styles/docrail.css";

/* The doc rail — the rail nav's document mode, as a shell any doc-style
 * page wears (the handbook, /design, future references).
 *
 * LAYER 1: an ink rail on the left. Up top, the glyph with a back arrow
 * (the site's chevron-to-arrow, turned); below, the page's own contents
 * as grouped links; at the foot, whatever the page needs (a theme
 * toggle, a version). LAYER 2: the content, on the page ground beside
 * it. The rail is ALWAYS ink, whatever theme the content wears — it is
 * the base layer showing through, as on the home rail.
 */

export type DocRailGroup = {
  /** Caps group label; omit for an ungrouped run of links. */
  label?: string;
  items: readonly { id: string; label: string }[];
};

export const DocRail = ({
  active,
  backHref = "/",
  backLabel = "Back",
  children,
  footer,
  groups,
  title,
}: {
  active?: string;
  backHref?: string;
  backLabel?: string;
  children: ReactNode;
  footer?: ReactNode;
  groups: readonly DocRailGroup[];
  title: string;
}): ReactElement => (
  <div className="gr-docrail-page">
    <aside className="gr-docrail">
      <a aria-label={backLabel} className="gr-docrail-back" href={backHref}>
        <Arrow />
        <img alt="" src="/brand/mark-glyph.svg" />
      </a>
      <span className="gr-docrail-title">{title}</span>
      <nav className="gr-docrail-nav">
        {groups.map((group, index) => (
          <div className="gr-docrail-group" key={group.label ?? index}>
            {group.label && (
              <span className="gr-docrail-group-title">{group.label}</span>
            )}
            {group.items.map((item) => (
              <a
                data-active={item.id === active || undefined}
                href={`#${item.id}`}
                key={item.id}
              >
                {item.label}
              </a>
            ))}
          </div>
        ))}
      </nav>
      {footer && <div className="gr-docrail-footer">{footer}</div>}
    </aside>
    <main className="gr-docrail-main">{children}</main>
  </div>
);
