# Handover: "From sand to…" scroll-driven illustrated blog post

> Historical reference. Paths and instructions in this document may be obsolete. The [collection guide](../../README.md) describes the current workflow.

You are taking over a small, dependency-free web project from another agent. Read this whole file before touching code. The owner is Aidan (they/them). The project is a single blog post with a sticky, scroll-scrubbed line-art illustration on the left and prose on the right, Apple-product-page style, drawn in the "Hey Tea" look: thin uniform black line on cream paper, hollow circles for boron, filled dots for phosphorus, monochrome.

## Files (everything is plain HTML/CSS/JS, no build step, no node_modules)

- `index.html`: the prose. Each `<section class="scene-text" data-scene="…">` is one paragraph and one illustration state. Section order defines scene indices 0…18. Loads GSAP 3.13 + ScrollTrigger from jsDelivr and IBM Plex Sans from Google Fonts, so the machine needs internet.
- `style.css`: page layout, the `#d2` SVG text styles (IBM Plex Sans, `.caption`, `.tiny`, `.bit`, `.muted`, `.formula`), footnote styles.
- `main.js`: 3D line renderer for scenes 0–2 (quartz cluster, Czochralski ingot, wafer slice) with hidden-line removal and floor shadows, the scroll-to-progress mapping, the frame loop, the hand-off from 3D to 2D, the "tweak" debug panel. Exposes `window.__demo` (`state.progress`, `ctl`, `parts`, `d2`).
- `scenes2d.js`: all 2D diagrams for scenes 3–18 as one paused GSAP timeline built by `SCENES2D.build(svgRoot, hold)`. viewBox is 440×440, captions sit at y=380.
- `serve.js`: tiny static server. `node serve.js` → http://localhost:8080 (no-store caching, so a reload always picks up edits). With `SNAP_DIR=/some/dir node serve.js`, `POST /snap?name=foo` with a PNG body writes `foo.png` there (used for snapshot verification).
- `From_sand_to.txt`: the post as a single Markdown-style text document in the owner's original format, with illustration directions in <angle brackets>. It carries a few editorial fixes the live index.html does not yet have (see the open suggestions below), so treat it as the proposed next version of the prose, not as the current page.
- `.claude/launch.json`: attaches the Claude desktop browser pane to that URL. Not needed outside that app.

## Scene index

| idx | data-scene | what is drawn |
|---|---|---|
| 0 | quartz | 3D quartz crystal cluster (untouchable, see rules) |
| 1 | ingot | 3D ingot grown from the melt |
| 2 | wafer | 3D slice, wafer turns edge-on and zooms into 2D |
| 3 | boron | wafer cross-section, boron rings |
| 4 | implant | two phosphorus islands fired in from above |
| 5 | wires | three wires: source, drain, gate |
| 6 | voltages | elevation-map picture, electrons "downhill" (footnote 1 explains it is reversed) |
| 7 | blocked | gate at 0 V, hill between the islands |
| 8 | flowing | gate at 1 V, electrons flow, bulb lights (n-type MOSFET) |
| 9 | symbol | the same transistor as a circuit symbol (label "gate" only) |
| 10 | not | NOT gate: p-type (bubbled gate) above, n-type below, rails 1 and 0, A → Ā |
| 11 | nand | NAND gate, four transistors, A, B, out |
| 12 | nand-symbol | circuit shrinks and dims, D outline draws itself around it, bubble + stubs appear |
| 13 | adder | full adder box, aᵢ bᵢ cᵢ → sᵢ cᵢ₊₁, example 10110 + 01101, carry 1 |
| 14 | chain | ripple-carry chain, example 0011 + 0110 = 1001, carries 0 1 1 0, carry-in 0 |
| 15 | heat | "P ∝ C V² f" formula, caption "heating: capacitance × voltage² × clock" |
| 16 | latch | four-NAND gated D latch, inputs D and WE, output Q, feedback wires draw themselves |
| 17 | lut | 3-input LUT: eight memory bits (0 1 1 0 1 0 0 1 = 3-input XOR) → y |
| 18 | fpga | grid of LUTs wired through programmable switches |

The footer holds "To be continued" and footnote 1 (electrons really flow uphill).

## How the scroll drives everything

- ScrollTrigger (scrub 0.8, `gsap.matchMedia` at 640px) tweens `state.progress` from 0 to NSCENE−1 as the paragraph centres cross the viewport centre. Progress p = scene index, so p = 14.0 is scene 14 fully settled.
- `frame()` in main.js runs every tick: it works out the scene pair and a 0–1 transition value with a `hold` zone (`ctl.hold`, default 0.18) around each paragraph, renders the 3D parts, then calls `d2.tl.time(p, true)` and runs every function in `d2.afterRender`. It also toggles `.is-active` on the current section (inactive paragraphs are dimmed to 0.28 opacity).
- 3D parts (main.js) have per-scene `states`; a state may carry a `choreo(t, A, B)` returning `{ pose, opacity, shadow }`. `part.shadowOp` feeds the floor shadow separately from the line opacity.
- 2D DSL (scenes2d.js, inside `build`):
  - `mk(tag, attrs, parent)`, `path(d, attrs, parent)`, `text(x, y, str, attrs, parent)` (anchor middle), `sub(x, y, base, subscript, attrs, parent)`, `dot(x, y, r, parent)`, `group(attrs, parent, 'x y')` (sets svgOrigin).
  - `key(el, scene, props, from, late, span)`: the element's state at that scene (opacity defaults to 1). `from` = props to start from on first appearance, `late` = fraction of the transition to wait, `span` < 1 on a leaving key makes it go early.
  - `show(el, s0, s1, props, span)`: visible from scene s0, gone at s1.
  - `caption(scene, str, until)`: muted caption at y=380.
  - `hideAt0(el)`: hidden at timeline time 0.
  - `loop(scene, tween, reset)`: an idle loop that plays while that scene is settled; `reset` undoes it.
  - `draw(pathEl, t0, dur, ease)`: progressive path drawing by rebuilding geometry from samples (use this, not stroke-dasharray, see gotchas). `t0` is timeline time; `at(s) = s − 1 + hold` is when the change into scene s begins and `DUR = 1 − 2·hold` is its length.
  - `spread(n, pick, inside, min, place, retries)`: collision-free scatter for dopant dots (boron min 5.4, phosphorus min 4.7 with 6 retries). `rng(seed)` is a seeded generator, so the layout is deterministic.

## Adding or changing a scene

1. Add a `<section class="scene-text" data-scene="name"><p>…</p></section>` in index.html at the right position. Indices after it shift, so update later `key`/`show`/`caption` scene numbers in scenes2d.js.
2. In scenes2d.js, build the drawing into a group, give it `key`s or `show`, a `caption`, optional `loop`.
3. Captions must fit inside x ≈ 20…420 at 13.5px; the longest existing one is the FPGA caption.
4. Reload http://localhost:8080 and verify (recipe below).

## Owner's standing rules (do not violate)

- Scenes 0, 1, 2 (the 3D ones) are "perfect"; change them only if asked.
- Nothing may pop on or off abruptly. Every appearance is a fade or a draw; lines that join must join cleanly (no half-drawn then snap).
- Label only the terminals the prose names. Keep diagram text in IBM Plex Sans; captions ≤ 13.5px; the "current" digit in bit strings is weight 600 (`.bit`).
- Keep the "∝" in the heat formula; keep the bold digits; keep the hollow/filled monochrome dopant convention.
- Discuss approach before building anything creative or structural; small concrete fixes can just be done.
- When asked to audit, audit only; do not edit.
- British spelling in prose (visualisation, minimised).

## Gotchas learned the hard way

- Never position elements from an `onUpdate` inside the scrubbed 2D timeline. Tween a plain object and apply it from `afterRender`.
- The stroke-dasharray self-drawing trick breaks under `vector-effect: non-scaling-stroke` (dash lengths become screen px): paths half-draw then snap and wires stop short. Use `draw()`.
- Stroke width of the hero NAND symbol is tweened through the CSS variable `--k` on `.hero-nand` (`stroke-width: calc(var(--w) * var(--k, 1) * 1px)`), so the landed symbol matches the tiled copies after the scene 13 multiply loop.
- The wafer part is opacity 0 for the whole ingot scene and only appears from the wafer scene; its floor shadow fades separately via `shadow` in its choreo.
- `prime(tl)` nudges the paused timeline once at startup; otherwise every diagram shows at once before the first scroll.

## Verification recipe (headless-ish, in the page console or a browser-automation JS call)

```js
// 1. detach scrolling so you can pin a scene (a viewport resize re-runs matchMedia and
//    re-creates the ScrollTrigger, so kill it again after any resize)
ScrollTrigger.getAll().forEach(st => { gsap.killTweensOf(st.animation); st.kill(); });
// 2. pin a scene (integer = settled; 13.5 = halfway through the 13→14 transition)
__demo.state.progress = 14;
// 3. force a frame (rAF stops while a hidden browser pane is not painting)
gsap.ticker.tick();
// for real-time idle loops: gsap.ticker.lagSmoothing(0) then tick/wait/tick
```
Then screenshot the left column, or measure with `getBBox()` / `getComputedStyle(el).opacity`. For PNG snapshots, serialise a clone of `#d2` with style.css and a base64 woff2 `@font-face` inlined (Google Fonts text otherwise renders in a fallback), draw it to an 880px canvas, and `POST /snap?name=…` with `SNAP_DIR` set. Reload the page afterwards to restore live scrolling. Always check the console is clean.

## Open editorial suggestions (not done, owner's call)

- Prose says "islands" in the implant paragraph but "trenches" in the next two paragraphs and in the scene 7 caption; pick one.
- Adder paragraph says "three inputs" but names only aᵢ and bᵢ; the carry-in cᵢ appears a paragraph later.
- "Programs" heading covers LUTs and FPGA only; "Programmable logic" would match. Three developer-facing hooks were suggested: before the latch every circuit is a pure function and the loop adds state; a LUT is an array indexed by the input bits, built from the latches just shown; an FPGA is configured by loading a bitstream the way you load a program.
- Minor wording: "any ideating" (inference), "3-to-1 function" (function of three bits), "first melting process" (crystal growth), "Each silicon crystal is sparsely populated" (can be seeded).
- NAND caption could read "NAND gate: two p-type above, two n-type below" to mirror the NOT caption.

## Planned continuation

Processors, programs, and the thoughts of an LLM (see the footer). Aidan wants to revisit memory (a DRAM/SRAM/latch reel was built and removed) themselves.
