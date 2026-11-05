import { useState } from "react";
import type { CSSProperties, ReactElement } from "react";
import { Arrow } from "./icons";
import { Tabs } from "./Tabs";

/**
 * The theme gallery: every theme rendered in itself, filterable by family.
 *
 * All four show by default, because with four the useful comparison is the
 * whole set at once — a light taupe against a dark grove is exactly the
 * judgement being made. The family tabs narrow that to one ground when the
 * question is finer. (This was tabbed WITHOUT an "All" when there were eight;
 * at that size the set could not be read in one glance and the tabs were the
 * only way in. Four changed the answer.)
 *
 * Each card leads with a band of its second surface. A theme's two surfaces
 * are the part hardest to judge from a rendered card — the ground is
 * everywhere and the second surface may not appear at all — so it is shown as
 * itself rather than left to be inferred.
 *
 * Every card can also apply itself to the whole page. Nothing special happens
 * when it does: the same data-theme the card carries goes on .gr-root, and
 * because roles are inherited custom properties, the page re-themes for free.
 * A theme on a section and a theme on the page are one declaration in two
 * places — which is the whole reason there is a single construct.
 */

/**
 * Each theme's gradient, named, and how its label is coloured.
 *
 * Two treatments, because the pairings divide in two. Ember, Tide and
 * Shallows start on a saturated stop, and a `difference` blend there inverts
 * to that colour's COMPLEMENT — the label came out pink on Tide and salmon on
 * Ember. Those take a flat light ink instead, which reads at 5.35 / 5.19 /
 * 5.19 against their dark ends.
 *
 * Terrace's stops are near-neutral, so inverting them gives neutral dark ink
 * and the blend does exactly what it should. It keeps it, which also means it
 * is legible on the pale end where no light ink could be.
 */
const GRADIENTS: Record<string, { blend?: boolean; name: string }> = {
  dark: { name: "Shallows" },
  grove: { name: "Ember" },
  light: { name: "Tide" },
  taupe: { blend: true, name: "Terrace" },
};

const FAMILIES = [
  { label: "All", themes: ["taupe", "grove", "light", "dark"] },
  { label: "Taupe", themes: ["taupe"] },
  { label: "Grove", themes: ["grove"] },
  { label: "Neutral", themes: ["light", "dark"] },
] as const;

/** Put the theme on the root. */
const applyToPage = (theme: string) => {
  document.querySelectorAll<HTMLElement>(".gr-root").forEach((root) => {
    root.dataset.theme = theme;
  });
};

export const ThemeGallery = (): ReactElement => {
  const [family, setFamily] = useState<string>(FAMILIES[0].label);
  const shown = FAMILIES.find((f) => f.label === family) ?? FAMILIES[0];

  return (
    <div className="gr-theme-gallery">
      <Tabs
        label="Theme family"
        onChange={setFamily}
        options={FAMILIES.map((option) => option.label)}
        value={family}
      />

      {/* Two across at most: these cards carry a full specimen — heading,
          copy, both buttons, a rule, a link and the gradient — and four in a
          row would shrink every one of those below the size it is judged at.
          A lone card takes the full width rather than sitting at half. */}
      <div
        className="gr-cols gr-theme-cards"
        style={
          { "--gr-cols": Math.min(shown.themes.length, 2) } as CSSProperties
        }
      >
        {shown.themes.map((theme) => (
          <article className="gr-theme-card" data-theme={theme} key={theme}>
            {/* the second surface, shown as itself */}
            <div aria-hidden className="gr-theme-surface" />

            <div className="gr-theme-body">
              <p className="gr-label">{theme}</p>
              <h3 className="gr-heading" style={{ marginBlockStart: "0.5rem" }}>
                The research lab focused on inference.
              </h3>
              <p className="gr-body gr-muted">
                We co-design hardware and software to provide the world&rsquo;s
                most affordable inference.
              </p>
              <div className="gr-theme-actions">
                <span className="gr-button gr-button--main">Get API key</span>
                <span className="gr-button gr-button--secondary">
                  View docs
                  <Arrow />
                </span>
              </div>
              <hr className="gr-theme-rule" />

              {/* The band names its own pairing. */}
              <div className="gr-theme-gradient">
                <span
                  className={`gr-theme-gradient-name${
                    GRADIENTS[theme].blend
                      ? " gr-theme-gradient-name--blend"
                      : ""
                  }`}
                >
                  {GRADIENTS[theme].name}
                </span>
              </div>

              <button
                className="gr-link"
                onClick={() => applyToPage(theme)}
                type="button"
              >
                Apply this theme
                <Arrow />
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
};
