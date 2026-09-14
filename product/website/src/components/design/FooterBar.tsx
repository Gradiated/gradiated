import { useEffect, useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import {
  DEFAULT_THEME,
  THEMES,
  applyTheme,
  readStoredTheme,
  storeTheme,
} from "../../theme";
import type { ThemeId } from "../../theme";

/**
 * The bar under the wordmark: copyright, GMT clock, theme selector.
 *
 * Both live pieces render nothing on the server and fill in after mount. A
 * clock rendered during SSR is wrong by the time it reaches the browser, and a
 * theme read from storage is unknowable there — either would be a hydration
 * mismatch. The bar reserves its height regardless, so nothing shifts when
 * they arrive.
 */

/* The themes the site OFFERS live in ../../theme — Grove and Light are still
   defined in themes.css and still on the reference page, because Grove needs
   tuning before it can go live and that has to happen somewhere. */

const Clock = (): ReactElement => {
  const [time, setTime] = useState<string | null>(null);

  useEffect(() => {
    const format = new Intl.DateTimeFormat("en-GB", {
      hour: "2-digit",
      hour12: false,
      minute: "2-digit",
      second: "2-digit",
      timeZone: "UTC",
    });

    let timer: ReturnType<typeof setTimeout>;
    const tick = () => {
      setTime(format.format(new Date()));
      // Scheduled to the next whole second rather than a flat 1000ms interval:
      // an interval drifts against the clock it is displaying and will
      // eventually skip a second visibly.
      timer = setTimeout(tick, 1000 - (Date.now() % 1000));
    };
    tick();
    return () => clearTimeout(timer);
  }, []);

  return (
    <p className="gr-footer-clock">
      {/* Where the clock is, not just what it reads: a bare GMT time is a fact
          about a timezone, and the place is the point. */}
      Cambridge,{" "}
      {/* Monospace so the digits do not reflow the line every second. */}
      <span className="gr-code">{time ?? "--:--:--"}</span> GMT
    </p>
  );
};

const ThemeSelector = (): ReactElement => {
  const [theme, setTheme] = useState<ThemeId>(DEFAULT_THEME);

  /* Catch the indicator up with the stored choice. Only the indicator: the
     theme itself is already on the page by now, applied by Substrate before
     the first paint. The server cannot know the choice, so this starts at the
     default and corrects after mount. */
  useEffect(() => {
    setTheme(readStoredTheme());
  }, []);

  /* Applying and saving happen HERE, on the choice, rather than in an effect
     watching `theme`. That effect also ran on mount, with the initial state,
     so every page change wrote taupe over the reader's saved theme before the
     stored value had been read back — which is why the choice never survived
     a navigation. */
  const choose = (next: ThemeId): void => {
    setTheme(next);
    storeTheme(next);
    const root = document.querySelector<HTMLElement>(".gr-root");
    if (root) applyTheme(root, next);
  };

  const index = THEMES.findIndex(({ id }) => id === theme);

  return (
    <div
      aria-label="Theme"
      className="gr-swatches"
      role="radiogroup"
      style={{ "--active": index } as CSSProperties}
    >
      {/* One indicator that travels, rather than four independent states —
          which is what makes the change read as a single movement. */}
      <span aria-hidden className="gr-swatch-dot" />
      {THEMES.map((option) => (
        <button
          aria-checked={theme === option.id}
          className="gr-swatch"
          data-swatch={option.id}
          key={option.id}
          onClick={() => choose(option.id)}
          role="radio"
          title={option.label}
          type="button"
        >
          <span className="gr-visually-hidden">{option.label}</span>
        </button>
      ))}
    </div>
  );
};

export const FooterBar = (): ReactElement => (
  <div className="gr-footer-bar">
    <p className="gr-footer-legal">© 2026 Gradiated Ltd</p>
    <Clock />
    <ThemeSelector />
  </div>
);
