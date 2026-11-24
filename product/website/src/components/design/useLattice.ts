import { useEffect, useRef, useState } from "react";

/**
 * Resolves the lattice unit against the element's real width.
 *
 * CSS can derive the unit (see tokens.css) but not well enough to be the
 * source of truth, for two reasons:
 *
 *   1. `100vw` includes the scrollbar; `margin-inline: auto` centres within
 *      the content box, which does not. On any scrolling page the module and
 *      the lattice are computed against widths that differ by ~15px, so they
 *      drift out of phase — exactly the alignment the whole system depends on.
 *
 *   2. Choosing the unit well is a search, not an expression: we want the
 *      largest integer unit inside a comfortable range such that a module of
 *      N units fits the available width, where N has good divisors. CSS can
 *      clamp and round but it cannot pick N.
 *
 * The unit is an integer, keeping the lattice pixel-exact, except on phones.
 */

/** Unit counts per tier. Each divides cleanly by 2, 3, 4, 6 and 12. */
/* A tier must end where its unit would exceed U_MAX, or the module stops
   growing and the extra width becomes margin instead. 16 units hits 24px at
   16 * 24 + 48 = 432, and 36 units hits it at 912 — just under the wide tier's
   900. There was no rung between 432 and 620, so a 600px viewport held a
   384px module inside 108px margins. `compact` fills it: 24 units hit U_MAX at
   624, which is where mid begins. */
const TIERS = [
  { margin: 24, minWidth: 900, moduleU: 48, name: "wide" },
  { margin: 24, minWidth: 620, moduleU: 36, name: "mid" },
  /* Phones: exactly 36px a side. The unit goes fractional to fit, so the
     gutter does not vary with the leftover of whole units. */
  { exact: true, margin: 36, minWidth: 432, moduleU: 24, name: "compact" },
  { exact: true, margin: 36, minWidth: 0, moduleU: 16, name: "narrow" },
] as const;

export type Tier = (typeof TIERS)[number]["name"];

const U_MAX = 24;
const U_MIN = 12;
const MIN_MARGIN = 24;

export type Lattice = {
  moduleU: number;
  /**
   * Which size tier the element resolved to. Published as data-tier so CSS can
   * key off the ELEMENT's width rather than the window's — a media query
   * cannot see a constrained container, so the device preview would otherwise
   * shrink the layout while leaving its responsive behaviour untouched.
   */
  tier: Tier;
  /**
   * Horizontal displacement of the opening, in px: how far every lattice line
   * is shoved aside as the cell expands from one unit wide to the full
   * viewport — (width - u) / 2, so the cell's own edge lines ride exactly to
   * the viewport edges and every other line exits beyond them.
   */
  shift: number;
  u: number;
  /** The root's clientWidth the above was resolved against. */
  width: number;
};

const EMPTY: Lattice = {
  moduleU: 48,
  shift: 0,
  tier: "wide",
  u: U_MAX,
  width: 0,
};

export const resolveLattice = (width: number): Lattice => {
  const tier = TIERS.find(({ minWidth }) => width >= minWidth) ?? TIERS.at(-1)!;
  const usable = width - (tier.margin ?? MIN_MARGIN) * 2;
  const fit = usable / tier.moduleU;
  const u = Math.min(
    U_MAX,
    Math.max(U_MIN, "exact" in tier ? fit : Math.floor(fit)),
  );

  return {
    moduleU: tier.moduleU,
    shift: Math.round((width - u) / 2),
    tier: tier.name,
    u,
    width,
  };
};

export const useLattice = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  const [lattice, setLattice] = useState<Lattice>(EMPTY);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    let previous = "";

    const apply = () => {
      // clientWidth excludes the scrollbar — this is the whole point.
      const next = resolveLattice(node.clientWidth);
      node.style.setProperty("--u", `${next.u}px`);
      node.style.setProperty("--module-u", `${next.moduleU}`);
      node.style.setProperty("--shift-x", `${next.shift}px`);
      node.dataset.tier = next.tier;

      // Only re-render when the geometry actually changes; a resize drag fires
      // continuously and each render rebuilds every line element.
      const key = `${next.u}:${next.width}:${next.tier}`;
      if (key === previous) return;
      previous = key;
      setLattice(next);
    };

    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { lattice, ref };
};
