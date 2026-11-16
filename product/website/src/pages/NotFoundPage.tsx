import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import {
  Arrow,
  Band,
  Footer,
  Module,
  Nav,
  Reveal,
  Substrate,
} from "../components/design";
import "../styles/index.css";

/**
 * The 404.
 *
 * On the centred fold, at hero size rather than display size: the homepage
 * says the one thing the company does and earns the larger type, and this
 * page is an apology with three ways out of it.
 *
 * It was the last route wrapped in the legacy SiteLayout, which meant a
 * mistyped URL was the one place a visitor could still meet the old nav, the
 * old footer, and the legacy ThemeToggle — which writes its own storage key
 * and could still hand out a theme that has been retired.
 */

/* Both internal, so both are router links — the first is the way out, the
   second is somewhere worth going instead. */
const WAYS_OUT = [
  { href: "/", label: "Return home", tone: "main" },
  { href: "/library/our-thesis/", label: "Read the thesis", tone: "secondary" },
] as const;

export const NotFoundPage = (): ReactElement => (
  <Substrate>
    <Nav />

    <Band>
      <Module bleed className="gr-module--fold" index={0}>
        <div className="gr-fold-centred">
          <h1 className="gr-hero gr-notfound-title">
            <Reveal by="word">What were you looking for?</Reveal>
          </h1>
          <p className="gr-lede gr-muted gr-notfound-lede">
            The path ended here.
          </p>
          <div className="gr-home-actions">
            {WAYS_OUT.map(({ href, label, tone }) => (
              <Link
                className={`gr-button gr-button--${tone}`}
                key={href}
                to={href}
              >
                {label}
                <Arrow />
              </Link>
            ))}
          </div>
        </div>
      </Module>
    </Band>

    <Band>
      <Footer index={1} />
    </Band>
  </Substrate>
);
