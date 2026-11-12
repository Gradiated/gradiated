import { Logo as PostHogLogo } from "@posthog/brand/logo";
import { useEffect, useState } from "react";
import type { CSSProperties, ReactElement } from "react";

/**
 * The bar under the wordmark: copyright and the GMT clock. (The theme
 * control lives in the rail now.)
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

export const FooterBar = (): ReactElement => (
  <div className="gr-footer-bar">
    <div className="gr-footer-ownership">
      <a
        aria-label="PostHog"
        className="gr-footer-parent-link"
        href="https://posthog.com/"
        rel="noreferrer"
        target="_blank"
      >
        <PostHogLogo className="gr-footer-parent-logo" variant="mono" />
      </a>
      <p className="gr-footer-parent-copy">
        Gradiated is a brand owned by PostHog.
      </p>
    </div>
    <Clock />
    {/* Its own cell: far right on desktop, last line on a phone. */}
    <p className="gr-footer-legal">© 2026 PostHog Inc.</p>
  </div>
);
