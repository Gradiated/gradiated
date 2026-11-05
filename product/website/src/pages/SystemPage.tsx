import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  Copy,
  Cpu,
  Download,
  ExternalLink,
  Menu,
  Search,
  Settings,
  X,
  Zap,
} from "lucide-react";
import { DocRail } from "../components/design/DocRail";
import { Icon } from "../components/design/Icon";
import "../styles/index.css";
import "./system.css";

/* /design — the system of record.
 *
 * Every primitive the relaunch builds with, as live specimens drawn from
 * the REAL tokens — this page declares nothing of its own, which is the
 * test: if a specimen here looks wrong, the system is wrong, not the page.
 * Storybook discipline: nothing ships that is not on this page first.
 */

/* -- the palette, restated for specimens -----------------------------------
   Values mirror brand.css. The page reads live CSS for the ROLES; these
   literals exist only to label chips and compute temperaments. */

const ZINC: readonly (readonly [string, string])[] = [
  ["zinc-50", "#fafafa"],
  ["zinc-100", "#f4f4f5"],
  ["zinc-200", "#e4e4e7"],
  ["zinc-300", "#d4d4d8"],
  ["zinc-400", "#a1a1aa"],
  ["zinc-500", "#71717a"],
  ["zinc-600", "#52525b"],
  ["zinc-700", "#3f3f46"],
  ["zinc-800", "#27272a"],
  ["zinc-900", "#18181b"],
  ["zinc-950", "#09090b"],
];

const FAMILIES: readonly (readonly [
  string,
  readonly (readonly [string, string])[],
])[] = [
  [
    "Hardware",
    [
      ["green-deep", "#1d4b38"],
      ["teal", "#09b99e"],
      ["green", "#4cbd79"],
      ["pcb", "#65c132"],
      ["green-pale", "#c9e89f"],
    ],
  ],
  [
    "Energy",
    [
      ["red", "#e4504e"],
      ["yellow", "#f4ce56"],
      ["light", "#ffffff"],
      ["sand", "#efe3c3"],
    ],
  ],
  [
    "Cloud",
    [
      ["aubergine", "#472f96"],
      ["blue", "#2a55e4"],
      ["azure", "#009fd9"],
      ["lavender", "#a28fe9"],
      ["pink", "#f66ae2"],
      ["sky", "#8ed3f2"],
      ["ice", "#dce7f5"],
    ],
  ],
];

const SIGNAL = "#2fd655";

/* -- colour math: temperaments + contrast ----------------------------------- */

const hexToHsl = (hex: string): [number, number, number] => {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255;
  const g = ((n >> 8) & 255) / 255;
  const b = (n & 255) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h =
    max === r
      ? (g - b) / d + (g < b ? 6 : 0)
      : max === g
        ? (b - r) / d + 2
        : (r - g) / d + 4;
  h *= 60;
  return [h, s, l];
};

const hslToHex = (h: number, s: number, l: number): string => {
  const f = (k: number) => {
    const x = (k + h / 30) % 12;
    const c =
      l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(x - 3, 9 - x, 1));
    return Math.round(c * 255)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
};

/* The three temperaments: cool (-16deg, x0.75), base, hot (+16deg, x1.25). */
const temperament = (hex: string, dir: -1 | 0 | 1): string => {
  if (dir === 0) return hex;
  const [h, s, l] = hexToHsl(hex);
  const nh = (h + dir * 16 + 360) % 360;
  const ns = Math.max(0, Math.min(1, s * (dir === 1 ? 1.25 : 0.75)));
  return hslToHex(nh, ns, l);
};

const luminance = (hex: string): number => {
  const n = parseInt(hex.slice(1), 16);
  const ch = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return (
    0.2126 * ch((n >> 16) & 255) +
    0.7152 * ch((n >> 8) & 255) +
    0.0722 * ch(n & 255)
  );
};

const ratio = (a: string, b: string): number => {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
};

const grade = (r: number): string =>
  r >= 7 ? "AAA" : r >= 4.5 ? "AA" : r >= 3 ? "AA-large" : "fail";

/* -- shared chrome ----------------------------------------------------------- */

const Swatch = ({
  hex,
  name,
  onCopy,
}: {
  hex: string;
  name: string;
  onCopy: (hex: string) => void;
}): ReactElement => (
  <div className="gr-sys-swatch">
    <div className="gr-sys-tri">
      {([-1, 0, 1] as const).map((dir) => {
        const value = temperament(hex, dir);
        return (
          <button
            key={dir}
            onClick={() => onCopy(value)}
            style={{ background: value }}
            title={`${value} — ${dir === 0 ? "base" : dir < 0 ? "cool" : "hot"}`}
            type="button"
          />
        );
      })}
    </div>
    <span className="gr-sys-swatch-name">{name}</span>
    <code>{hex}</code>
  </div>
);

const SECTIONS: readonly (readonly [string, string])[] = [
  ["marks", "Marks"],
  ["palette", "Palette"],
  ["families", "Families"],
  ["roles", "Roles & themes"],
  ["spacing", "Spacing"],
  ["radius", "Radius"],
  ["type", "Type"],
  ["icons", "Icons"],
  ["buttons", "Buttons"],
  ["forms", "Forms"],
  ["contrast", "Contrast"],
];

/* Role names, as declared in tokens.css. The page reads their LIVE values. */
const ROLE_NAMES = [
  "--color-substrate",
  "--color-module",
  "--color-panel",
  "--color-overlay",
  "--color-grid",
  "--color-rule",
  "--color-text",
  "--color-text-muted",
  "--color-interactive",
  "--color-interactive-fill",
  "--color-emphasis",
  "--color-inverse",
  "--color-button-main",
  "--color-button-main-ink",
  "--color-button-secondary",
  "--color-signal-green",
] as const;

const SPACE_STEPS = [
  ["--space-1", "0.25u"],
  ["--space-2", "0.5u"],
  ["--space-3", "0.75u"],
  ["--space-4", "1u"],
  ["--space-5", "1.5u"],
  ["--space-6", "2u"],
  ["--space-7", "3u"],
  ["--space-8", "4u"],
] as const;

const RADIUS_STEPS = [
  "--radius-none",
  "--radius-sm",
  "--radius-md",
  "--radius-brand",
  "--radius-lg",
  "--radius-xl",
  "--radius-2xl",
] as const;

const TYPE_STEPS = [
  {
    label: "Display",
    v: "--text-display",
    style: {
      fontFamily: "var(--font-title)",
      fontSize: "var(--text-display)",
      fontWeight: 650,
      lineHeight: "var(--leading-display)",
      letterSpacing: "var(--tracking-hero)",
    },
    sample: "Sand to thought",
  },
  {
    label: "Hero",
    v: "--text-hero",
    style: {
      fontFamily: "var(--font-title)",
      fontSize: "var(--text-hero)",
      fontWeight: 650,
      lineHeight: "var(--leading-hero)",
      letterSpacing: "var(--tracking-hero)",
    },
    sample: "The research lab focused on inference.",
  },
  {
    label: "Section",
    v: "--text-section",
    style: {
      fontFamily: "var(--font-title)",
      fontSize: "var(--text-section)",
      fontWeight: 650,
      lineHeight: 1.05,
    },
    sample: "Silicon, owned end to end",
  },
  {
    label: "Heading",
    v: "--text-heading",
    style: {
      fontFamily: "var(--font-title)",
      fontSize: "var(--text-heading)",
      fontWeight: "var(--weight-heading)" as never,
      letterSpacing: "var(--tracking-heading)",
    },
    sample: "Open-model inference",
  },
  {
    label: "Lede",
    v: "--text-lede",
    style: {
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-lede)",
      fontWeight: "var(--weight-lede)" as never,
      letterSpacing: "var(--tracking-lede)",
    },
    sample:
      "Bring your existing code, change your base URL, and start sending requests.",
  },
  {
    label: "Body",
    v: "--text-body",
    style: {
      fontFamily: "var(--font-body)",
      fontSize: "var(--text-body)",
      letterSpacing: "var(--tracking-body)",
    },
    sample:
      "Gradiated is a small research and engineering team making open-model inference radically more efficient.",
  },
  {
    label: "UI",
    v: "--text-ui",
    style: { fontFamily: "var(--font-body)", fontSize: "var(--text-ui)" },
    sample: "Interface copy sits a step under body.",
  },
  {
    label: "Caps",
    v: "--text-caps",
    style: {
      fontFamily: "var(--font-caps)",
      fontSize: "var(--text-caps)",
      fontWeight: "var(--weight-caps)" as never,
      letterSpacing: "var(--tracking-caps)",
      textTransform: "uppercase" as const,
    },
    sample: "Flex tier · Beta · See open roles",
  },
  {
    label: "Code",
    v: "--font-code",
    style: { fontFamily: "var(--font-code)", fontSize: "0.9375rem" },
    sample: 'client.base_url = "https://api.gradiated.com/v1"',
  },
] as const;

const ICON_SET = [
  ["ArrowUpRight", ArrowUpRight],
  ["Check", Check],
  ["ChevronRight", ChevronRight],
  ["Copy", Copy],
  ["Cpu", Cpu],
  ["Download", Download],
  ["ExternalLink", ExternalLink],
  ["Menu", Menu],
  ["Search", Search],
  ["Settings", Settings],
  ["X", X],
  ["Zap", Zap],
] as const;

const TypeRow = ({
  step,
}: {
  step: (typeof TYPE_STEPS)[number];
}): ReactElement => {
  const ref = useRef<HTMLDivElement>(null);
  const [resolved, setResolved] = useState("");
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const cs = getComputedStyle(el);
      setResolved(
        `${Math.round(parseFloat(cs.fontSize))}px · ${cs.fontFamily.split(",")[0].replace(/"/g, "")}`,
      );
    };
    read();
    window.addEventListener("resize", read);
    return () => window.removeEventListener("resize", read);
  }, []);
  return (
    <div className="gr-sys-typerow">
      <div className="gr-sys-typerow-meta">
        <h3 className="gr-sys-sub">{step.label}</h3>
        <code>{step.v}</code>
        <span className="gr-sys-typerow-size">{resolved}</span>
      </div>
      <div ref={ref} style={step.style as React.CSSProperties}>
        {step.sample}
      </div>
    </div>
  );
};

export const SystemPage = (): ReactElement => {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [copied, setCopied] = useState<string | null>(null);
  const [active, setActive] = useState("marks");
  const [roles, setRoles] = useState<Record<string, string>>({});
  const rootRef = useRef<HTMLDivElement>(null);

  const copyHex = (hex: string) => {
    void navigator.clipboard?.writeText(hex);
    setCopied(hex);
    window.setTimeout(() => setCopied(null), 1400);
  };

  /* Read the LIVE role values off the themed root — the page documents
     what the CSS actually resolves, never a parallel list. */
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const cs = getComputedStyle(root);
    const next: Record<string, string> = {};
    for (const name of ROLE_NAMES)
      next[name] = cs.getPropertyValue(name).trim();
    setRoles(next);
    /* The body sits OUTSIDE the themed root and paints the legacy
       --paper; snapshot the theme's substrate onto it (Substrate.tsx
       does the same) so the page edges follow the toggle. */
    document.body.style.background = next["--color-substrate"];
  }, [theme]);

  useEffect(() => {
    const previous = document.body.style.background;
    return () => {
      document.body.style.background = previous;
    };
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: "-20% 0px -70% 0px" },
    );
    document
      .querySelectorAll(".gr-sys-section")
      .forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="gr-root" data-theme={theme} ref={rootRef}>
      <DocRail
        active={active}
        backLabel="Back to Gradiated"
        footer={
          <div className="gr-sys-theme">
            {(["light", "dark"] as const).map((t) => (
              <button
                data-on={t === theme || undefined}
                key={t}
                onClick={() => setTheme(t)}
                type="button"
              >
                {t}
              </button>
            ))}
          </div>
        }
        groups={[
          {
            label: "Foundations",
            items: SECTIONS.slice(0, 6).map(([id, label]) => ({ id, label })),
          },
          {
            label: "Elements",
            items: SECTIONS.slice(6).map(([id, label]) => ({ id, label })),
          },
        ]}
        title="Design"
      >
        <div className="gr-sys-main">
          <header>
            <h1 className="gr-sys-h1">The system</h1>
            <p className="gr-sys-note">
              Every primitive the site builds with, rendered live from the real
              tokens. If a specimen here looks wrong, the tokens are wrong —
              this page declares no colours, sizes or spacing of its own.
              Nothing ships that is not on this page first.
            </p>
          </header>

          <section className="gr-sys-section" id="marks">
            <h2 className="gr-sys-h2">Marks</h2>
            <p className="gr-sys-note">
              The rule the whole system hangs off: the logo appears only in
              monochrome — ink on light grounds, inverse on dark. Colour belongs
              to the families, never to the mark. The wordmark runs vertical on
              the rail; this is the same artwork turned.
            </p>
            <div className="gr-sys-markplate">
              <img alt="Gradiated mark" src="/brand/mark-solid.svg" />
              <img
                alt="Gradiated wordmark"
                className="gr-sys-wordmark"
                src="/brand/wordmark-hx-h.svg"
              />
            </div>
            <div className="gr-sys-markplate gr-sys-markplate--ink">
              <img
                alt="Gradiated mark, inverse"
                src="/brand/mark-solid.svg"
                style={{ filter: "invert(1)" }}
              />
              <img
                alt="Gradiated wordmark, inverse"
                className="gr-sys-wordmark"
                src="/brand/wordmark-hx-h.svg"
                style={{ filter: "invert(1)" }}
              />
            </div>
          </section>

          <section className="gr-sys-section" id="palette">
            <h2 className="gr-sys-h2">Palette</h2>
            <p className="gr-sys-note">
              Zinc carries every neutral — Tailwind&apos;s scale adopted whole,
              so we never mint another grey. Click any chip to copy.
            </p>
            <div className="gr-sys-ramp">
              {ZINC.map(([name, hex]) => (
                <button
                  className="gr-sys-ramp-step"
                  key={name}
                  onClick={() => copyHex(hex)}
                  style={{ background: hex }}
                  type="button"
                >
                  <span
                    style={{
                      color: luminance(hex) > 0.45 ? "#09090b" : "#fafafa",
                    }}
                  >
                    {name.replace("zinc-", "")}
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className="gr-sys-section" id="families">
            <h2 className="gr-sys-h2">Families</h2>
            <p className="gr-sys-note">
              Three chromatic families on the zinc backbone. Every colour has
              three temperaments — cool (−16° / ×0.75), base, hot (+16° /
              ×1.25); the segments of each chip are click-to-copy. Signal green
              is an LED, not a pigment: the same on every theme.
            </p>
            {FAMILIES.map(([family, colors]) => (
              <div className="gr-sys-family" key={family}>
                <h3 className="gr-sys-sub">{family}</h3>
                <div className="gr-sys-chips">
                  {colors.map(([name, hex]) => (
                    <Swatch hex={hex} key={name} name={name} onCopy={copyHex} />
                  ))}
                </div>
                <div
                  aria-hidden
                  className="gr-sys-familybar"
                  style={{
                    background: `linear-gradient(90deg, ${colors
                      .map(([, hex]) => hex)
                      .join(", ")})`,
                  }}
                />
              </div>
            ))}
            <div className="gr-sys-family">
              <h3 className="gr-sys-sub">Signal</h3>
              <div className="gr-sys-chips">
                <Swatch hex={SIGNAL} name="signal-green" onCopy={copyHex} />
              </div>
            </div>
          </section>

          <section className="gr-sys-section" id="roles">
            <h2 className="gr-sys-h2">Roles &amp; themes</h2>
            <p className="gr-sys-note">
              Components reference roles, never ramps and never literals. These
              are the LIVE values of the current theme — flip the toggle in the
              rail and watch the whole page restate itself. Taupe and grove
              remain as legacy aliases of light and dark until the page rejig
              renames their usages.
            </p>
            <div className="gr-sys-roles">
              {ROLE_NAMES.map((name) => (
                <button
                  className="gr-sys-role"
                  key={name}
                  onClick={() => copyHex(roles[name] ?? "")}
                  type="button"
                >
                  <i style={{ background: `var(${name})` }} />
                  <code>{name}</code>
                  <span>{roles[name]}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="gr-sys-section" id="spacing">
            <h2 className="gr-sys-h2">Spacing</h2>
            <p className="gr-sys-note">
              The unit is the parameter: --u resolves to at most 24px and tracks
              the viewport, so every step below breathes with the module grid.
              Prefer a named step; compose rarer sizes from the unit directly.
              Never hardcode a pixel gap.
            </p>
            <div className="gr-sys-spaces">
              {SPACE_STEPS.map(([token, mult]) => (
                <div className="gr-sys-space" key={token}>
                  <code>{token}</code>
                  <span className="gr-sys-space-mult">{mult}</span>
                  <i style={{ width: `var(${token})` }} />
                </div>
              ))}
            </div>
          </section>

          <section className="gr-sys-section" id="radius">
            <h2 className="gr-sys-h2">Radius</h2>
            <p className="gr-sys-note">
              The scale is the vocabulary; --radius is the setting, and the
              relaunch sets it to --radius-brand (5px) — sharper than the old
              12px, short of the square the silicon metaphor argues for.
              Containers take the setting; drawn geometry (lattice, seams) takes
              none; circles are marks and stay 50%.
            </p>
            <div className="gr-sys-radii">
              {RADIUS_STEPS.map((token) => (
                <div className="gr-sys-radiusbox" key={token}>
                  <i
                    data-on={token === "--radius-brand" || undefined}
                    style={{ borderRadius: `var(${token})` }}
                  />
                  <code>{token}</code>
                </div>
              ))}
            </div>
          </section>

          <section className="gr-sys-section" id="type">
            <h2 className="gr-sys-h2">Type</h2>
            <p className="gr-sys-note">
              Instrument Sans carries titles, Barlow carries body and caps,
              JetBrains Mono carries code. Sizes are clamp()-based — each
              row&apos;s readout is what this viewport resolved.
            </p>
            <div className="gr-sys-typesheet">
              {TYPE_STEPS.map((step) => (
                <TypeRow key={step.label} step={step} />
              ))}
            </div>
          </section>

          <section className="gr-sys-section" id="icons">
            <h2 className="gr-sys-h2">Icons</h2>
            <p className="gr-sys-note">
              Lucide geometry in the Gradiated voice: butt caps and miter joins
              — a system with no round corners draws no round strokes — weighted
              by --icon-stroke and sized in em so icons track their type. Always
              through the Icon component, never raw Lucide.
            </p>
            <div className="gr-sys-icons">
              {ICON_SET.map(([name, glyph]) => (
                <div className="gr-sys-iconcell" key={name}>
                  <Icon glyph={glyph} />
                  <code>{name}</code>
                </div>
              ))}
            </div>
            <p className="gr-sys-note">
              In context, beside type:&nbsp;
              <a className="gr-link" href="#icons">
                Open the console <Icon glyph={ArrowUpRight} />
              </a>
            </p>
          </section>

          <section className="gr-sys-section" id="buttons">
            <h2 className="gr-sys-h2">Buttons</h2>
            <p className="gr-sys-note">
              The full set on the current theme&apos;s grounds. Buttons follow
              the theme: a primary action stays findable on any ground.
            </p>
            <div className="gr-sys-row">
              <button className="gr-button gr-button--main" type="button">
                Primary
              </button>
              <button className="gr-button gr-button--secondary" type="button">
                Secondary
              </button>
              <button className="gr-button" type="button">
                Default
              </button>
              <button className="gr-button gr-button--ghost" type="button">
                Ghost
              </button>
            </div>
          </section>

          <section className="gr-sys-section" id="forms">
            <h2 className="gr-sys-h2">Forms</h2>
            <p className="gr-sys-note">
              Inputs on the role tokens: rule for edges, panel for fills,
              interactive for focus. If a control needs its own colour, the
              roles are wrong.
            </p>
            <div className="gr-sys-formsheet">
              <label className="gr-sys-field">
                <span>Email</span>
                <input
                  className="gr-sys-input"
                  placeholder="you@company.com"
                  type="email"
                />
              </label>
              <label className="gr-sys-field">
                <span>Latency tier</span>
                <select className="gr-sys-input" defaultValue="flex">
                  <option value="realtime">Realtime</option>
                  <option value="flex">Flex</option>
                  <option value="batch">Batch</option>
                </select>
              </label>
              <label className="gr-sys-field gr-sys-field--wide">
                <span>Workload notes</span>
                <textarea
                  className="gr-sys-input"
                  placeholder="Tell us about your traffic shape…"
                  rows={3}
                />
              </label>
              <div className="gr-sys-field">
                <span>Options</span>
                <label className="gr-sys-check">
                  <input defaultChecked type="checkbox" /> Stream responses
                </label>
                <label className="gr-sys-check">
                  <input type="checkbox" /> Log prompts
                </label>
              </div>
              <label className="gr-sys-field">
                <span>Max batch window</span>
                <input defaultValue={60} max={120} min={0} type="range" />
              </label>
            </div>
          </section>

          <section className="gr-sys-section" id="contrast">
            <h2 className="gr-sys-h2">Contrast</h2>
            <p className="gr-sys-note">
              The pairings that carry meaning, measured live on the current
              theme. Anything below AA does not ship.
            </p>
            <ul className="gr-sys-checks">
              {(
                [
                  ["Body ink / substrate", "--color-text", "--color-substrate"],
                  [
                    "Muted ink / substrate",
                    "--color-text-muted",
                    "--color-substrate",
                  ],
                  [
                    "Interactive / substrate",
                    "--color-interactive",
                    "--color-substrate",
                  ],
                  ["Body ink / panel", "--color-text", "--color-panel"],
                  [
                    "Button ink / button",
                    "--color-button-main-ink",
                    "--color-button-main",
                  ],
                ] as const
              ).map(([label, fgRole, bgRole]) => {
                const fg =
                  roles[fgRole] ??
                  (rootRef.current
                    ? getComputedStyle(rootRef.current)
                        .getPropertyValue(fgRole)
                        .trim()
                    : "");
                const bg = roles[bgRole] ?? "";
                const r = fg && bg ? ratio(fg, bg) : 0;
                return (
                  <li key={label}>
                    <span
                      className="gr-sys-check-chip"
                      style={{ background: bg, color: fg }}
                    >
                      Aa
                    </span>
                    <span>{label}</span>
                    <code>{r ? `${r.toFixed(2)}:1 · ${grade(r)}` : "…"}</code>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      </DocRail>

      {copied && <div className="gr-sys-toast">Copied {copied}</div>}
    </div>
  );
};
