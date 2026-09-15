# Gradiated design system

The visual system for gradiated.com. Currently the **monochrome edition**: the
structure, layout, and motion are final-shape; colour is a later layer that
lands by editing one file.

The metaphor is silicon, and it is load-bearing, not decorative. The page is a
wafer: a lattice of cells. The entrance pries one cell open — its vertical
edges pulled to the viewport sides, its top and bottom edges to the fold — and
what the cell housed is the first fold of the page. Modules rest on the opened
surface like dies; the lattice draws itself in as you scroll.

Reference implementation: `/style/` (`src/pages/StylePage.tsx`).

## Files

```
src/styles/
  index.css        the only stylesheet a page imports; ordered @imports
  tokens.css       every raw value in the system — and nothing else
  base.css         element defaults and type roles, scoped to .gr-root
  substrate.css    lattice, band, module, plate, entrance, scroll draw

src/components/design/
  index.ts         public surface — import components from here only
  Substrate.tsx    the wafer: root, lattices, the entrance plate
  Module.tsx       Band / Module / Columns
  useLattice.ts    resolves the unit against the element's real width
```

## The layout model in one paragraph

The module is always a **whole number of units** (`--module-u`: 48 / 36 / 16
per tier), and the **unit** (`--u`) is derived to fit the device — largest
integer ≤ 24px that fits the tier's count. Because the unit is an integer and
the module is a whole multiple of it, lattice/module alignment is true by
construction at every viewport; there is no phase to maintain. Each tier count
divides cleanly by 2, 3, 4 and 6, so `<Columns count={n}>` is correct at every
breakpoint with no special-casing. CSS derives all of this as a pre-hydration
fallback; `useLattice` re-resolves it against the element's real `clientWidth`
(which excludes the scrollbar — `100vw` does not) and is the source of truth.

## Using it

```tsx
import { Band, Columns, Module, Substrate } from "../components/design";
import "../styles/index.css";

<Substrate>
  <Band>
    <Module bleed height="viewport" index={0}>
      …hero…
    </Module>
    <Module index={1} title="Principles">
      <Columns count={2}>…</Columns>
    </Module>
  </Band>
</Substrate>;
```

- `Substrate` — the wafer. One per page, owns the lattices and the entrance.
- `Band` — holds module width and centring. Modules carry no outer margin.
- `Module` — one swappable section. `bleed` extends the surface to the
  viewport (content stays on the band grid); `height="viewport"` pins it to
  the first fold — the region the entrance reveals; `index` is its position in
  the entrance stagger, equal to visual order.
- `Columns` — zero-gap column grid; boundaries land on lattice lines.

Type roles from `base.css`: `gr-hero`, `gr-section-title`, `gr-heading`,
`gr-body`, `gr-muted`, `gr-label`, `gr-code`, `gr-glass`.

## The entrance

One cell of the lattice is pried open until it is the full 100vw × 100vh first
fold. It is driven end to end by two registered custom properties:

- `--t` — horizontal opening, 0 (one cell) → 1 (full viewport width)
- `--v` — vertical opening, 0 (one cell) → 1 (full fold)

The plate's clip and every lattice line's displacement read the same two
values, which is what keeps the opening's edges and the lines riding them in
exact lockstep — the grid is physically shoved out of the viewport, never
covered. Their registered `initial-value` is 1, so the resting page is simply
open. **Page transitions are the same pair run backwards**: closing a page is
`--t`/`--v` animating back to 0. Build transitions on these; do not invent a
second mechanism.

The resting lattice is a separate scroll-driven layer (`animation-timeline:
scroll()`), invisible at scroll zero and drawing downward just behind the
viewport. Entrance and resting grid never coexist, so there is no hand-off to
hide. Timeline and all tuning values live in the entrance section of
`tokens.css`.

## Rules of engagement

These apply to every human and agent working in this system. They exist
because the previous CSS was nine files defining the same twenty selectors,
where load order silently decided which declaration won.

1. **`tokens.css` holds every raw value, and nothing else.** No selectors
   below `.gr-root`; no literal px/hex/ms in any other style file or inline in
   JSX. To change how the system looks or moves, edit tokens. Tokens marked
   _reserved_ (ambient/assembly motion, `--color-emphasis`) are the agreed
   vocabulary for designed-but-unbuilt work: do not delete them, and do not
   invent parallels when building those features.
2. **Dependencies point one direction.** tokens → base → substrate →
   `pages/*.css`. A file may reference tokens from above it, never siblings'
   selectors. No file redefines a selector that lives in another file.
3. **Components reference colour ROLES, never the ramp, never literals.**
   `var(--color-module)`, not `var(--n-100)`, not `#e6e4e0`. This is the whole
   monochrome-to-colour plan: the palette lands by repointing roles in one
   file, with zero component changes.
4. **Spacing lives in the band and module chrome, never in content.** A module
   has no outer margin; content declares columns, not widths. Breaking this
   breaks section reorderability, which is the point of the module system.
5. **All sizes derive from `--u`.** Positions and dimensions in whole units
   (`calc(2 * var(--u))`); module edges land on units; type baselines float
   free (deliberately — snapping baselines to the grid dictates line-height
   from the wrong master and breaks on wrap).
6. **Hairlines scale, they don't size.** A 1px box thinned by `scale`
   (`--hair-scale`), because layout boxes snap to whole device pixels and
   transforms don't. On lattice lines, `scale` (draw) and `translate`
   (displacement) stay separate properties — combined into one `transform`,
   the two animations would overwrite each other.
7. **Motion belongs to a family** — response / ambient / assembly, plus the
   one-off entrance. Take values from the family's tokens; no inline
   durations or easings. New one-off choreography gets named tokens.
8. **`prefers-reduced-motion` is part of every animation, not a later pass.**
   The reduced path shows the settled end state immediately. The registered
   `initial-value: 1` on `--t`/`--v` is what makes this free for the entrance
   — keep that property when extending it.
9. **The `gr-` prefix and `.gr-root` scope stay** until the legacy CSS
   (`src/legacy.css` and the eight root-level files it imports) is deleted.
   New-system pages must not import `legacy.css`; legacy pages must not use
   `gr-` classes. When the last legacy page is migrated: `.gr-root` becomes
   `:root`, prefixes drop, legacy files are deleted in the same change.
10. **Verify like it will be measured, because it was.** Layout claims in this
    system were established by measurement (pixel-sampling rendered output,
    reading computed styles mid-animation), not by eyeballing. If you change
    the lattice, the opening, or the hairline mechanics, verify the same way:
    lines one device pixel, uniform darkness, exact `u` spacing, cell edges
    landing on the viewport edges.

## Known deferred work

- **Colour**: palette derives from Plato's Academy (limestone/stone/earth/
  olive/ink) but is explicitly unfinished. Weathered olive `#72745A` fails
  WCAG AA (4.08:1) as text-size interaction colour on limestone — the ramp
  needs a darker interaction step before colour ships.
- **Type scale**: provisional, extracted from Figma, not yet tuned in browser.
- **Glass**: token values are placeholders until there is a chromatic backdrop
  to tune against.
- **Wafer-field**: chip-assembly spot graphics (see the `wafer-field` repo);
  the assembly motion tokens are reserved for it.
- **Entrance gating**: currently plays on every load of `/style/`. Before
  production, gate to first visit per session so returning visitors get the
  open state immediately (LCP).
- **Scroll-drawn lattice** requires `animation-timeline: scroll()`; browsers
  without it show the lines statically. This is the intended fallback, not a
  bug.
