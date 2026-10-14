import { gsap } from "gsap";
import { COMPUTER_SCENES } from "./computer-scenes.js";
/* ------------------------------------------------------------------ */
/* 2D diagram scenes: everything after the wafer.                      */
/*                                                                     */
/* Every element gets a value set per paragraph ("key"). build() turns */
/* those into one scrubbed GSAP timeline whose time is the paragraph   */
/* index, with each change happening between (i + hold) and (i+1 -    */
/* hold). "loops" are idle animations that run while a paragraph is    */
/* the current one. Coordinates are viewBox units (440 x 440).         */
/* ------------------------------------------------------------------ */
export const SCENES2D = (function () {
  const NS = "http://www.w3.org/2000/svg";
  const EASE = "power2.inOut";

  function rng(seed) {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Smooth curve through points. Same point count → same string shape, so GSAP can tween between them.
  function curve(pts) {
    let d = `M${pts[0][0]} ${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)],
        p1 = pts[i],
        p2 = pts[i + 1],
        p3 = pts[Math.min(pts.length - 1, i + 2)];
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
      const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0]} ${p2[1]}`;
    }
    return d;
  }

  function build(root, hold) {
    while (root.firstChild) root.removeChild(root.firstChild);
    const tl = gsap.timeline({ paused: true });
    const loops = [];
    const afterRender = []; // functions main.js runs after each scrub, for scenes positioned from a tweened value
    const keys = new Map();
    const DUR = Math.max(0.05, 1 - 2 * hold);
    const originalScenes = [
      "quartz",
      "ingot",
      "wafer",
      "boron",
      "implant",
      "wires",
      "voltages",
      "blocked",
      "flowing",
      "symbol",
      "not",
      "nand",
      "nand-symbol",
      "adder",
      "chain",
      "heat",
      "latch",
      "register",
      "stored-answer",
    ];
    const sceneKeys = Array.from(
      root.closest(".post").querySelectorAll(".scene-text"),
      (section) => section.dataset.scene,
    );
    // Original drawings retain their numbered keys when new sections are inserted.
    const index = (scene) =>
      sceneKeys.indexOf(
        typeof scene === "string" ? scene : originalScenes[scene],
      ) >= 0
        ? sceneKeys.indexOf(
            typeof scene === "string" ? scene : originalScenes[scene],
          )
        : sceneKeys.length;
    const at = (s) => index(s) - 1 + hold; // when the change INTO paragraph s begins

    const mk = (tag, attrs = {}, parent = root) => {
      const e = document.createElementNS(NS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      parent.appendChild(e);
      return e;
    };
    const text = (x, y, str, attrs = {}, parent = root) => {
      const e = mk("text", { x, y, "text-anchor": "middle", ...attrs }, parent);
      e.textContent = str;
      return e;
    };
    const path = (d, attrs = {}, parent = root) =>
      mk("path", { d, ...attrs }, parent);
    // text with a real subscript (Unicode subscripts fall back to the wrong font sizes)
    const sub = (x, y, base, small, attrs = {}, parent = root) => {
      const e = mk("text", { x, y, "text-anchor": "middle", ...attrs }, parent);
      e.appendChild(document.createTextNode(base));
      const t = document.createElementNS(NS, "tspan");
      t.setAttribute("dy", "3.5");
      t.setAttribute("font-size", "78%");
      t.textContent = small;
      e.appendChild(t);
      return e;
    };
    const dot = (x, y, r = 1.8, parent = root) =>
      mk("circle", { cx: x, cy: y, r, class: "dot" }, parent);
    const group = (attrs = {}, parent = root, origin) => {
      const g = mk("g", attrs, parent);
      if (origin) gsap.set(g, { svgOrigin: origin });
      return g;
    };

    // late: fraction of the transition to wait before an element's first appearance begins
    const key = (el, s, p = {}, from = null, late = 0, span = 1) => {
      if (!keys.has(el)) keys.set(el, []);
      keys.get(el).push({ s, p: { opacity: 1, ...p }, from, late, span });
    };
    // span < 1 on the leaving key makes the element go early in the transition
    const show = (el, s0, s1, p = {}, span = 1) => {
      key(el, s0, p);
      if (s1 !== undefined) key(el, s1, { ...p, opacity: 0 }, null, 0, span);
    };
    const loop = (scene, tween, reset) => {
      tween.pause();
      loops.push({ scene: index(scene), tween, reset });
    };
    const hideAt0 = (el, vars = {}) => tl.set(el, { opacity: 0, ...vars }, 0);

    // Draw a path progressively from its start, between t0 and t0 + dur on the timeline.
    // The usual dash-offset trick is unusable here: with non-scaling strokes the dash lengths are
    // screen pixels, so a scaled path only ever half-draws and then snaps complete. Instead the
    // path's geometry is rebuilt from samples along it after every scrub, and the original `d`
    // is restored once it is complete so the final shape is exact.
    const drawn = [];
    const draw = (el, t0, dur, ease = "power1.inOut") => {
      const full = el.getAttribute("d"),
        L = el.getTotalLength(),
        N = Math.max(40, Math.ceil(L / 0.5));
      const pts = [];
      for (let i = 0; i <= N; i++) {
        const q = el.getPointAtLength((L * i) / N);
        pts.push([q.x, q.y]);
      }
      const st = { v: 0, last: -1 };
      tl.set(st, { v: 0 }, 0);
      tl.to(st, { v: 1, duration: dur, ease }, t0);
      drawn.push(() => {
        if (st.v === st.last) return;
        st.last = st.v;
        if (st.v >= 1) {
          el.setAttribute("d", full);
          return;
        }
        let d = `M${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)}`;
        if (st.v > 0) {
          const k = st.v * N,
            n = Math.floor(k),
            f = k - n;
          for (let i = 1; i <= n; i++)
            d += ` L${pts[i][0].toFixed(2)} ${pts[i][1].toFixed(2)}`;
          if (n < N) {
            const a = pts[n],
              b = pts[n + 1];
            d += ` L${(a[0] + (b[0] - a[0]) * f).toFixed(2)} ${(a[1] + (b[1] - a[1]) * f).toFixed(2)}`;
          }
        }
        el.setAttribute("d", d);
      });
    };
    afterRender.push(() => {
      for (const f of drawn) f();
    });

    const caption = (s, str, s1 = s + 1, y = 380) => {
      const t = text(220, y, str, { class: "muted caption" });
      hideAt0(t);
      tl.to(t, { opacity: 1, duration: DUR * 0.35 }, at(s) + DUR * 0.65);
      tl.to(t, { opacity: 0, duration: DUR * 0.35 }, at(s1));
    };

    /* ================= 3 · cross-section seeded with boron ================= */
    const gSlab = group({}, root, "220 250");
    mk("rect", { x: 70, y: 200, width: 300, height: 100, rx: 3 }, gSlab);
    const r = rng(11);
    const trenches = [
      [100, 165],
      [275, 340],
    ];
    const inTrench = (x, y) =>
      y < 250 && trenches.some(([a, b]) => x > a - 4 && x < b + 4);
    const gBoron = mk("g", { class: "hollow" }, gSlab);
    // Scatter the dopants, but never let two rings touch: a candidate that lands on a neighbour is
    // nudged straight away from it to a clear spacing, and dropped if it still collides or leaves
    // its region. Same random sequence as before, so the picture barely changes.
    const spread = (n, pick, inside, min, place, retries = 0) => {
      const placed = [];
      const clear = (x, y) =>
        inside(x, y) &&
        !placed.some(([px, py]) => Math.hypot(px - x, py - y) < min);
      for (let i = 0; i < n; i++) {
        for (let attempt = 0; attempt <= retries; attempt++) {
          let [x, y] = pick();
          if (!inside(x, y)) continue;
          for (let pass = 0; pass < 3; pass++) {
            const near = placed.find(
              ([px, py]) => Math.hypot(px - x, py - y) < min,
            );
            if (!near) break;
            const d = Math.hypot(x - near[0], y - near[1]) || 0.001;
            x = near[0] + ((x - near[0]) / d) * min;
            y = near[1] + ((y - near[1]) / d) * min;
          }
          if (!clear(x, y)) continue;
          placed.push([x, y]);
          place(x, y);
          break;
        }
      }
    };
    spread(
      70,
      () => [78 + r() * 284, 208 + r() * 84],
      (x, y) => !inTrench(x, y) && x > 76 && x < 364 && y > 206 && y < 294,
      5.4,
      (x, y) =>
        mk("circle", { cx: x.toFixed(1), cy: y.toFixed(1), r: 2 }, gBoron),
    );
    key(gSlab, 3, { scale: 1 }, { scale: 1 }, 0.82); // appears in place, once the wafer's rim fills the same rectangle
    key(gSlab, 9, { scale: 0.55, opacity: 0 });
    caption(3, "cross-section of the wafer · boron ○");

    /* ================= 4 · implant two trenches of phosphorus ================= */
    const gTrench = mk("g", { class: "thin" }, gSlab);
    for (const [x0, x1] of trenches)
      mk("rect", { x: x0, y: 200, width: x1 - x0, height: 45, rx: 6 }, gTrench);
    show(gTrench, 4);
    const gPhos = mk("g", { class: "dots" }, gSlab);
    const pdots = [];
    for (const [x0, x1] of trenches)
      spread(
        18,
        () => [x0 + 7 + r() * (x1 - x0 - 14), 207 + r() * 32],
        (x, y) => x > x0 + 5 && x < x1 - 5 && y > 205 && y < 241,
        4.7, // filled dots only need to stay clear
        (x, y) =>
          pdots.push(
            mk("circle", { cx: x.toFixed(1), cy: y.toFixed(1), r: 2.1 }, gPhos),
          ),
        6,
      ); // last user of the random sequence, so retries are free
    hideAt0(pdots, { y: -130 });
    tl.to(
      pdots,
      {
        y: 0,
        opacity: 1,
        duration: DUR * 0.6,
        ease: "power2.in",
        stagger: { each: (DUR * 0.4) / pdots.length, from: "random" },
      },
      at(4),
    );
    caption(4, "phosphorus ●, fired in from above");

    /* ================= 5 · three wires ================= */
    const gWires = mk("g", {}, gSlab);
    mk("line", { x1: 132, y1: 128, x2: 132, y2: 200 }, gWires);
    mk("line", { x1: 307, y1: 128, x2: 307, y2: 200 }, gWires);
    mk("line", { x1: 220, y1: 128, x2: 220, y2: 186 }, gWires);
    mk("rect", { x: 182, y: 186, width: 76, height: 7 }, gWires); // gate electrode
    mk(
      "rect",
      { x: 182, y: 194, width: 76, height: 6, class: "thin dashed" },
      gWires,
    ); // insulating gap
    text(220, 90, "Gate", { class: "caption", "data-gate-label": "" }, gWires);
    key(gWires, 5, { y: 0 }, { y: -100 });

    /* ================= 6 · voltages and electron potential energy ================= */
    const vL = text(132, 114, "0 V", {}, gSlab);
    show(vL, 6);
    const vR = text(307, 114, "1 V", {}, gSlab);
    show(vR, 6);
    // The energy landscape is overlaid inside the silicon as a visual analogy, not physical height.
    // Positive electrical potential lowers electron potential energy (U = -e V).
    const gEnergy = group({ "data-diagram": "electron-energy" }, gSlab);
    show(gEnergy, 6);
    text(
      220,
      325,
      "Electron potential energy",
      { class: "muted caption" },
      gEnergy,
    );
    const P_slope = [
      [165, 247],
      [190, 250],
      [205, 254],
      [220, 258],
      [235, 262],
      [250, 265],
      [275, 268],
    ];
    const P_hill = [
      [165, 247],
      [190, 250],
      [205, 236],
      [220, 227],
      [235, 236],
      [250, 265],
      [275, 268],
    ];
    const prof = path(
      curve(P_hill),
      { class: "muted", "data-energy-profile": "" },
      gEnergy,
    );
    key(prof, 6, { attr: { d: curve(P_hill) } });
    key(prof, 7, { attr: { d: curve(P_hill) } });
    key(prof, 8, { attr: { d: curve(P_slope) } });
    caption(6, "higher voltage · lower electron potential energy");

    /* ================= 7 · gate at 0 V: a hill blocks the way ================= */
    const gateVoltageHighlight = mk(
      "rect",
      {
        x: 198,
        y: 97,
        width: 44,
        height: 24,
        rx: 8,
        class: "voltage-highlight",
        "data-gate-voltage-highlight": "",
      },
      gSlab,
    );
    hideAt0(gateVoltageHighlight);
    tl.to(
      gateVoltageHighlight,
      { opacity: 1, duration: DUR * 0.4, ease: "sine.out" },
      at(8) + DUR * 0.25,
    );
    tl.to(
      gateVoltageHighlight,
      { opacity: 0, duration: DUR * 0.4, ease: "sine.in" },
      at(8) + DUR * 0.75,
    );
    const vG0 = text(220, 114, "0 V", {}, gSlab);
    show(vG0, 6, 8);
    const vG1 = text(220, 114, "1 V", {}, gSlab);
    show(vG1, 8);
    const gE7 = mk("g", { class: "dots", "data-electrons": "blocked" }, gSlab);
    show(gE7, 7, 8);
    const bounce = gsap.timeline({ repeat: -1 });
    [0, 1, 2].forEach((i) => {
      const e = mk("circle", { r: 2.9 }, gE7);
      gsap.set(e, { x: 132, y: 134, opacity: 0 });
      bounce.set(e, { x: 132, y: 134, opacity: 0 }, i * 1.3);
      bounce.to(
        e,
        {
          keyframes: [
            { opacity: 1, duration: 0.15 },
            { y: 214, duration: 0.7, ease: "none" },
            { x: 168, y: 241, duration: 0.45, ease: "none" },
            { x: 199, y: 244, duration: 0.45, ease: "power1.out" },
            { x: 181, y: 243, duration: 0.45, ease: "power1.in" },
            { x: 199, y: 244, duration: 0.45, ease: "power1.out" },
            { x: 179, y: 243, duration: 0.45, ease: "power1.in" },
            { opacity: 0, duration: 0.3 },
          ],
        },
        i * 1.3,
      );
    });
    loop(7, bounce);
    caption(7, "gate at 0 V · an energy barrier limits electron flow");

    /* ================= 8 · gate at 1 V: electrons flow, bulb lights ================= */
    const gGlow = mk("g", {}, gSlab); // faint yellow fill, only while the bulb is on
    const glow = mk(
      "circle",
      { cx: 362, cy: 122, r: 8.4, class: "glow" },
      gGlow,
    );
    show(gGlow, 8, 9);
    const gBulb = mk("g", {}, gSlab);
    path("M307 128 L307 122 L353 122 M371 122 L392 122", {}, gBulb); // drain connection through the lamp to the external supply
    mk("circle", { cx: 362, cy: 122, r: 9 }, gBulb);
    path(
      "M355.6 115.6 L368.4 128.4 M368.4 115.6 L355.6 128.4",
      { class: "thin" },
      gBulb,
    ); // lamp symbol
    show(gBulb, 6);
    const gRays = mk("g", { class: "thin" }, gSlab);
    for (let k = 0; k < 7; k++) {
      const a = (-150 * Math.PI) / 180 + k * ((Math.PI * 1.1) / 6);
      mk(
        "line",
        {
          x1: (362 + 13 * Math.cos(a)).toFixed(1),
          y1: (122 + 13 * Math.sin(a)).toFixed(1),
          x2: (362 + 19 * Math.cos(a)).toFixed(1),
          y2: (122 + 19 * Math.sin(a)).toFixed(1),
        },
        gRays,
      );
    }
    show(gRays, 8, 9);
    const gE8 = mk("g", { class: "dots", "data-electrons": "flowing" }, gSlab);
    show(gE8, 8, 9);
    const flow = gsap.timeline({ repeat: -1 });
    [0, 1, 2, 3].forEach((i) => {
      const e = mk("circle", { r: 2.9 }, gE8);
      gsap.set(e, { x: 132, y: 134, opacity: 0 });
      flow.set(e, { x: 132, y: 134, opacity: 0 }, i * 0.9);
      flow.to(
        e,
        {
          keyframes: [
            { opacity: 1, duration: 0.12 },
            { y: 214, duration: 0.6, ease: "none" },
            { x: 168, y: 242, duration: 0.4, ease: "none" },
            { x: 220, y: 256, duration: 0.5, ease: "none" },
            { x: 275, y: 266, duration: 0.5, ease: "none" },
            { x: 307, y: 228, duration: 0.4, ease: "none" },
            { x: 307, y: 122, duration: 0.6, ease: "none" },
            { x: 352, y: 122, duration: 0.3, ease: "none" },
            { opacity: 0, duration: 0.08 },
            { x: 372, y: 122, duration: 0.01 },
            { opacity: 1, duration: 0.08 },
            { x: 392, y: 122, duration: 0.2, ease: "none" },
            { opacity: 0, duration: 0.12 },
          ],
        },
        i * 0.9,
      );
    });
    loop(8, flow);
    const pulse = gsap.to([gRays, glow], {
      opacity: 0.45,
      duration: 0.7,
      yoyo: true,
      repeat: -1,
      ease: "sine.inOut",
    });
    loop(8, pulse);
    caption(8, "n-type MOSFET: a switch with no moving parts");

    /* ================= 9 · the same transistor as a symbol ================= */
    // transistor symbol drawn around its own origin; 'p' adds the bubble
    const mos = (type, parent) => {
      const g = mk("g", {}, parent);
      mk("rect", { x: -22, y: -22, width: 44, height: 44, class: "ghost" }, g); // centres the bbox on (0, 0)
      gsap.set(g, { transformOrigin: "50% 50%" });
      path(type === "p" ? "M-22 0 L-14 0" : "M-22 0 L-8 0", {}, g);
      if (type === "p") mk("circle", { cx: -11, cy: 0, r: 2.6 }, g);
      path("M-8 -12 L-8 12 M-3 -12 L-3 12", {}, g);
      path("M-3 -8 L10 -8 L10 -22 M-3 8 L10 8 L10 22", {}, g);
      return g;
    };
    const nand = (parent) => {
      const g = mk("g", {}, parent);
      mk("rect", { x: -24, y: -12, width: 48, height: 24, class: "ghost" }, g);
      path("M-16 -12 L-4 -12 A12 12 0 0 1 -4 12 L-16 12 Z", {}, g);
      mk("circle", { cx: 10.6, cy: 0, r: 2.4 }, g);
      path("M-24 -7 L-16 -7 M-24 7 L-16 7 M13 0 L22 0", {}, g);
      return g;
    };
    const gLogic = group({}, root, "220 250");
    const logicDemos = [];
    const nHero = mos("n", gLogic);
    key(nHero, "symbol", { x: 110, y: 250, scale: 1.5 }, { scale: 0.8 });
    const symLabels = group({}, gLogic);
    text(67, 254, "gate", { "text-anchor": "end", class: "muted" }, symLabels);
    key(symLabels, "symbol", {}, null, 0.55);
    key(symLabels, "switch-types", { opacity: 0 }, null, 0, 0.35);

    const wireSwitch = (type, x, y, on, parent) => {
      const g = group({ "data-switch": type, "data-on": on }, parent);
      path(`M${x - 34} ${y} H${x - 14} M${x - 8} ${y - 12} V${y + 12}`, {}, g);
      if (type === "p") mk("circle", { cx: x - 11, cy: y, r: 2.6 }, g);
      else path(`M${x - 14} ${y} H${x - 8}`, {}, g);
      const d = on
        ? `M${x + 10} ${y - 26} V${y + 26}`
        : `M${x + 10} ${y - 26} V${y - 8} M${x + 10} ${y + 8} V${y + 26}`;
      path(d, {}, g);
      if (on) path(d, { class: "logic-connection" }, g);
      return g;
    };
    const equivalents = group({ "data-diagram": "switch-equivalents" }, gLogic);
    wireSwitch("n", 300, 190, true, equivalents);
    wireSwitch("n", 300, 305, false, equivalents);
    text(285, 148, "gate at 1 V", { class: "caption" }, equivalents);
    text(285, 263, "gate at 0 V", { class: "caption" }, equivalents);
    text(
      343,
      195,
      "ON",
      { "text-anchor": "start", class: "caption" },
      equivalents,
    );
    text(
      343,
      310,
      "OFF",
      { "text-anchor": "start", class: "caption" },
      equivalents,
    );
    path(
      "M178 190 H221 M215 186 L221 190 L215 194 M178 305 H221 M215 301 L221 305 L215 309",
      { class: "muted thin" },
      equivalents,
    );
    key(equivalents, "symbol", {}, null, 0.55);
    key(equivalents, "switch-types", { opacity: 0 }, null, 0, 0.35);
    caption(9, "one transistor · two possible connections", "switch-types");

    const pHero = mos("p", gLogic);
    key(nHero, "switch-types", { x: 110, y: 195, scale: 1.3 });
    key(pHero, "switch-types", { x: 110, y: 300, scale: 1.3 }, { scale: 0.6 });
    const types = group({ "data-diagram": "switch-types" }, gLogic);
    text(110, 148, "n-type", { class: "caption" }, types);
    text(110, 253, "p-type", { class: "caption" }, types);
    text(238, 133, "gate at 0 V", { class: "caption" }, types);
    text(340, 133, "gate at 1 V", { class: "caption" }, types);
    for (const [type, y] of [
      ["n", 195],
      ["p", 300],
    ]) {
      for (const [value, x] of [
        [0, 238],
        [1, 340],
      ]) {
        const on = type === "n" ? value === 1 : value === 0;
        wireSwitch(type, x, y, on, types);
        text(x + 10, y + 47, on ? "ON" : "OFF", { class: "caption" }, types);
      }
    }
    key(types, "switch-types", {}, null, 0.55);
    key(types, "not", { opacity: 0 }, null, 0, 0.35);
    caption(
      "switch-types",
      "opposite responses to the same gate voltage",
      "not",
    );

    const channel = (x, y, up = false) =>
      up
        ? `M${x + 10} ${y + 22} V${y + 8} H${x - 3} V${y - 8} H${x + 10} V${y - 22}`
        : `M${x + 10} ${y - 22} V${y - 8} H${x - 3} V${y + 8} H${x + 10} V${y + 22}`;
    const logicCases = (scene, parent, cases, ports, before, after) => {
      const layers = cases.map(({ inputs, output, connection }) => {
        const layer = group(
          { "data-logic-state": inputs.join(""), "data-output": output },
          parent,
        );
        if (connection) path(connection, { class: "logic-connection" }, layer);
        ports.forEach(({ x, y, anchor }, i) => {
          const value = i < inputs.length ? inputs[i] : output;
          text(
            x,
            y,
            String(value),
            { class: "logic-value", "text-anchor": anchor },
            layer,
          );
        });
        return layer;
      });
      gsap.set(layers, { opacity: 0 });
      gsap.set(layers[0], { opacity: 1 });
      const demo = gsap.timeline({ paused: true, repeat: -1 });
      const step = 3;
      layers.forEach((layer, i) => {
        const next = layers[(i + 1) % layers.length];
        demo.to(
          layer,
          { opacity: 0, duration: 0.25, ease: "sine.inOut" },
          i * step + 2.4,
        );
        demo.to(
          next,
          { opacity: 1, duration: 0.35, ease: "sine.inOut" },
          i * step + 2.65,
        );
      });
      demo.time(0.001, true).time(0, true);
      logicDemos.push(demo);
      afterRender.push(() => {
        const progress = tl.time();
        if (progress <= index(before) + hold || progress >= index(after) - hold)
          demo.pause(0);
        else if (
          Math.abs(progress - index(scene)) <= hold &&
          !matchMedia("(prefers-reduced-motion: reduce)").matches
        )
          demo.play();
        else demo.pause();
      });
    };

    key(pHero, "not", { x: 220, y: 210, scale: 1 });
    key(nHero, "not", { x: 220, y: 290, scale: 1 });
    const wNot = group({ "data-diagram": "not" }, gLogic);
    path(
      "M196 172 H244 M230 172 V188 M230 232 V268 M230 312 V330 M196 330 H244",
      {},
      wNot,
    );
    path("M230 250 H268 M172 250 H198 M198 210 V290", {}, wNot);
    dot(230, 250, 1.8, wNot);
    dot(198, 250, 1.8, wNot);
    text(186, 176, "1 V", { "text-anchor": "end", class: "muted" }, wNot);
    text(186, 334, "0 V", { "text-anchor": "end", class: "muted" }, wNot);
    text(164, 234, "A", { "text-anchor": "end" }, wNot);
    text(280, 234, "Ā", { "text-anchor": "start" }, wNot);
    logicCases(
      "not",
      wNot,
      [
        {
          inputs: [0],
          output: 1,
          connection: `M230 172 V188 ${channel(220, 210)} V250 H268`,
        },
        {
          inputs: [1],
          output: 0,
          connection: `M230 330 V312 ${channel(220, 290, true)} V250 H268`,
        },
      ],
      [
        { x: 164, y: 256, anchor: "end" },
        { x: 280, y: 256, anchor: "start" },
      ],
      "switch-types",
      "nor",
    );
    key(wNot, "not", {}, null, 0.55);
    key(wNot, "nor", { opacity: 0 }, null, 0, 0.35);
    caption(10, "NOT · the opposite of A", "nor");

    key(pHero, "nor", { x: 220, y: 175, scale: 1 });
    key(nHero, "nor", { x: 180, y: 305, scale: 1 });
    const p2 = mos("p", gLogic);
    const n2 = mos("n", gLogic);
    key(p2, "nor", { x: 220, y: 230, scale: 1 }, { scale: 0.6 });
    key(n2, "nor", { x: 280, y: 305, scale: 1 }, { scale: 0.6 });
    const wNor = group({ "data-diagram": "nor" }, gLogic);
    path(
      "M196 138 H264 M230 138 V153 M230 197 V208 M230 252 V267 M190 267 H338 M190 267 V283 M290 267 V283 M190 327 V350 M290 327 V350 M166 350 H314",
      {},
      wNor,
    );
    path("M116 175 H198 M138 175 V305 H158", {}, wNor);
    path(
      "M116 230 H133 A5 5 0 0 1 143 230 H198 M168 230 V253 H225 A5 5 0 0 1 235 253 H250 V262 A5 5 0 0 1 250 272 V305 H258",
      {},
      wNor,
    );
    for (const [x, y] of [
      [138, 175],
      [168, 230],
      [190, 267],
      [230, 267],
      [290, 267],
    ])
      dot(x, y, 1.8, wNor);
    text(186, 142, "1 V", { "text-anchor": "end", class: "muted" }, wNor);
    text(156, 354, "0 V", { "text-anchor": "end", class: "muted" }, wNor);
    text(108, 163, "A", { "text-anchor": "end" }, wNor);
    text(108, 218, "B", { "text-anchor": "end" }, wNor);
    text(346, 253, "out", { "text-anchor": "start" }, wNor);
    const inputs = [
      [0, 0],
      [0, 1],
      [1, 0],
      [1, 1],
    ];
    logicCases(
      "nor",
      wNor,
      inputs.map(([a, b]) => ({
        inputs: [a, b],
        output: Number(!a && !b),
        connection:
          !a && !b
            ? `M230 138 V153 ${channel(220, 175)} V208 ${channel(220, 230)} V267 H338`
            : [
                a ? `M190 350 V327 ${channel(180, 305, true)} V267 H338` : "",
                b ? `M290 350 V327 ${channel(280, 305, true)} V267 H338` : "",
              ]
                .filter(Boolean)
                .join(" "),
      })),
      [
        { x: 108, y: 185, anchor: "end" },
        { x: 108, y: 240, anchor: "end" },
        { x: 346, y: 275, anchor: "start" },
      ],
      "not",
      "nand",
    );
    key(wNor, "nor", {}, null, 0.55);
    key(wNor, "nand", { opacity: 0 }, null, 0, 0.35);
    caption("nor", "NOR · neither A nor B", "nand", 395);

    key(pHero, "nand", { x: 190, y: 210, scale: 1 });
    key(nHero, "nand", { x: 230, y: 275, scale: 1 });
    key(p2, "nand", { x: 260, y: 210, scale: 1 });
    key(n2, "nand", { x: 230, y: 322, scale: 1 });
    const wNand = group({ "data-diagram": "nand" }, gLogic);
    path(
      "M170 172 H290 M200 172 V188 M270 172 V188 M200 232 V250 M270 232 V250 M200 250 H300",
      {},
      wNand,
    );
    path("M240 250 V253 M240 297 V300 M240 344 V356 M200 356 H280", {}, wNand);
    path("M150 210 H168 M150 210 V275 H208", {}, wNand);
    path(
      "M150 322 H208 M176 322 V280 A4 4 0 0 1 176 270 V240 H196 A4 4 0 0 1 204 240 H238 V210",
      {},
      wNand,
    );
    for (const [x, y] of [
      [240, 250],
      [270, 250],
      [176, 322],
      [150, 210],
    ])
      dot(x, y, 1.8, wNand);
    text(160, 176, "1 V", { "text-anchor": "end", class: "muted" }, wNand);
    text(190, 360, "0 V", { "text-anchor": "end", class: "muted" }, wNand);
    text(142, 198, "A", { "text-anchor": "end" }, wNand);
    text(142, 310, "B", { "text-anchor": "end" }, wNand);
    text(310, 236, "out", { "text-anchor": "start" }, wNand);
    logicCases(
      "nand",
      wNand,
      inputs.map(([a, b]) => ({
        inputs: [a, b],
        output: Number(!(a && b)),
        connection:
          a && b
            ? `M240 356 V344 ${channel(230, 322, true)} V297 ${channel(230, 275, true)} V250 H300`
            : [
                !a ? `M200 172 V188 ${channel(190, 210)} V250 H300` : "",
                !b ? `M270 172 V188 ${channel(260, 210)} V250 H300` : "",
              ]
                .filter(Boolean)
                .join(" "),
      })),
      [
        { x: 142, y: 220, anchor: "end" },
        { x: 142, y: 332, anchor: "end" },
        { x: 310, y: 258, anchor: "start" },
      ],
      "nor",
      "adder",
    );
    key(wNand, "nand", {}, null, 0.55);
    key(wNand, "nand-symbol", { opacity: 0 }, null, 0, 0.35);
    caption(11, "NAND · not both A and B", 12, 398);

    /* ================= 12 · the NAND gate gets a symbol ================= */
    // The D outline draws itself around the circuit, which shrinks and dims inside it; then the
    // bubble, the two input stubs and the output stub appear. From here on this is how a NAND is drawn.
    const gSymOuter = group({}, root); // the adder's one-shot fade animates this wrapper
    const gSym = group({}, gSymOuter, "220 250"); // ...while the scroll timeline animates this
    const symG = nand(gSym);
    symG.setAttribute("class", "hero-nand"); // its stroke width follows --k, so it can thin to match the tiled gates
    gsap.set(symG, { x: 220, y: 250, scale: 3.2, transformOrigin: "50% 50%" });
    const symD = symG.querySelectorAll("path")[0],
      symStubs = symG.querySelectorAll("path")[1],
      symBubble = symG.querySelector("circle");
    const nandLabels = mk("g", { "data-nand-labels": "" }, gSym);
    text(134, 233, "A", { "text-anchor": "end" }, nandLabels);
    text(134, 277, "B", { "text-anchor": "end" }, nandLabels);
    text(296, 255, "out", { "text-anchor": "start" }, nandLabels);
    // first the circuit shrinks and dims (span 0.4 of the transition)...
    key(
      gLogic,
      12,
      { scale: 0.34, x: -15, y: -5, opacity: 0.35 },
      null,
      0,
      0.4,
    ); // encapsulated inside the symbol
    hideAt0(gSym);
    {
      // ...then the D outline draws itself around it, and finally the bubble, stubs and labels appear
      tl.set([symStubs, symBubble, nandLabels], { opacity: 0 }, 0);
      tl.to(gSym, { opacity: 1, duration: 0.01 }, at(12) + DUR * 0.42);
      draw(symD, at(12) + DUR * 0.42, DUR * 0.38);
      tl.to(
        [symStubs, symBubble, nandLabels],
        { opacity: 1, duration: DUR * 0.2, ease: EASE },
        at(12) + DUR * 0.8,
      );
    }
    key(gSym, 12, { scale: 1, x: 0, y: 0 }, null, -1); // entrance handled above
    caption(12, "the NAND gate symbol");

    /* ================= 13full adder: NANDs in a black box ================= */
    // The terminal names belong to the large NAND symbol, not the tiny building block.
    tl.to(nandLabels, { opacity: 0, duration: DUR * 0.35, ease: EASE }, at(13));
    key(gLogic, 3, { scale: 1 });
    key(gLogic, 13, { scale: 0.34, x: -15, y: -5, opacity: 0 }); // fades away inside the shrinking symbol
    key(gSym, 13, { scale: 0.125, x: -48, y: -30 }); // the symbol lands in the box's top-left cell
    key(gSym, "chain", { scale: 0.125, x: -48, y: -30, opacity: 0 });
    const gAdd = group({}, root, "220 250");
    mk("rect", { x: 160, y: 205, width: 120, height: 90, rx: 4 }, gAdd);
    // many more NAND gates inside the box (the centre is left clear for the "+")
    const gMany = mk("g", { class: "faint-gates" }, gAdd);
    for (const cy of [220, 250, 280])
      for (const cx of [172, 196, 220, 244, 268]) {
        if (cy === 250 && cx >= 196 && cx <= 244) continue; // the centre stays clear for the "+"
        if (cy === 220 && cx === 172) continue; // that cell is where the landed symbol sits
        gsap.set(nand(gMany), {
          x: cx,
          y: cy,
          scale: 0.4,
          transformOrigin: "50% 50%",
        });
      }
    gsap.set(gMany, { opacity: 0 });
    // a second after the symbol has settled into its cell, it fades to match and the rest tile in around it
    const multiply = gsap.timeline({ paused: true });
    multiply.set(gSymOuter, { opacity: 1 }, 0);
    multiply.set(gMany, { opacity: 0 }, 0);
    // the landed symbol also thins to the tiled gates' stroke width (--k is the same 0.5 factor
    // the .faint-gates rule uses), so afterwards they all look the same
    multiply.set(symG, { "--k": 1 }, 0);
    multiply.to(
      gSymOuter,
      { opacity: 0.35, duration: 0.8, ease: "power1.inOut" },
      1,
    );
    multiply.to(symG, { "--k": 0.5, duration: 0.8, ease: "power1.inOut" }, 1);
    multiply.to(
      gMany,
      { opacity: 0.35, duration: 0.9, ease: "power1.inOut" },
      1,
    );
    loop(13, multiply, () => {
      gsap.to(gSymOuter, { opacity: 1, duration: 0.4, overwrite: "auto" });
      gsap.to(symG, { "--k": 1, duration: 0.4, overwrite: "auto" });
      gsap.to(gMany, { opacity: 0, duration: 0.4, overwrite: "auto" });
    });
    path(
      "M211.5 250 L228.5 250 M220 241.5 L220 258.5",
      { class: "muted" },
      gAdd,
    ); // a drawn "+", exactly centred
    path(
      "M122 225 L160 225 M122 250 L160 250 M122 275 L160 275 M280 238 L318 238 M280 266 L318 266",
      {},
      gAdd,
    );
    sub(116, 229, "a", "i", { "text-anchor": "end" }, gAdd);
    sub(116, 254, "b", "i", { "text-anchor": "end" }, gAdd);
    sub(116, 279, "c", "i", { "text-anchor": "end" }, gAdd);
    sub(324, 242, "s", "i", { "text-anchor": "start" }, gAdd);
    sub(324, 270, "c", "i+1", { "text-anchor": "start" }, gAdd);
    // worked example, written as binary numbers: digit i (bold) is the one this block handles.
    // a = 10110, b = 01101, carry in 0 → sum digit 0, carry out 1
    const bits = (xc, y, digits) =>
      digits.forEach((dgt, k) =>
        text(
          xc + (k - 2) * 8,
          y,
          dgt,
          { class: "tiny " + (k === 2 ? "bit" : "faint") },
          gAdd,
        ),
      );
    bits(80, 229, ["1", "0", "1", "1", "0"]);
    bits(80, 254, ["0", "1", "1", "0", "1"]);
    text(80, 279, "0", { class: "tiny bit" }, gAdd);
    bits(360, 242, ["0", "0", "0", "1", "1"]);
    text(360, 270, "1", { class: "tiny bit" }, gAdd);
    show(gAdd, 13, undefined, { scale: 1, x: 0, y: 0 });
    key(gAdd, "chain", { scale: 0.52, x: 29, y: 0, opacity: 0 });
    caption(13, "full adder: one digit, with carry", "chain");

    /* ================= 14chain of adders ================= */
    const gChain = group({}, root, "220 250");
    const BX = [46, 132, 218, 304];
    // worked example 0011 + 0110 = 1001 (3 + 6 = 9), arrays indexed by digit i (0 = least significant)
    const av = ["1", "1", "0", "0"],
      bv = ["0", "1", "1", "0"],
      sv = ["1", "0", "0", "1"];
    const cv = ["0", "0", "1", "1", "0"]; // cv[i] is the carry cᵢ; cv[0] is the carry-in
    BX.forEach((x, k) => {
      const i = 3 - k; // digit index, least significant on the right
      mk("rect", { x, y: 227, width: 62, height: 46, rx: 3 }, gChain);
      path(
        `M${x + 27} 250 L${x + 35} 250 M${x + 31} 246 L${x + 31} 254`,
        { class: "muted" },
        gChain,
      );
      path(
        `M${x + 19} 205 L${x + 19} 227 M${x + 43} 205 L${x + 43} 227 M${x + 31} 273 L${x + 31} 295`,
        {},
        gChain,
      );
      sub(x + 19, 200, "a", i, { class: "tiny muted" }, gChain);
      sub(x + 43, 200, "b", i, { class: "tiny muted" }, gChain);
      sub(x + 31, 308, "s", i, { class: "tiny muted" }, gChain);
      text(x + 19, 186, av[i], { class: "tiny bit" }, gChain);
      text(x + 43, 186, bv[i], { class: "tiny bit" }, gChain);
      text(x + 31, 322, sv[i], { class: "tiny bit" }, gChain);
      if (k < 3) {
        path(
          `M${x + 86} 250 L${x + 62} 250 M${x + 68} 246 L${x + 62} 250 L${x + 68} 254`,
          {},
          gChain,
        );
        sub(x + 74, 244, "c", i, { class: "tiny muted" }, gChain);
        text(x + 74, 264, cv[i], { class: "tiny bit" }, gChain);
      }
    });
    path("M46 250 L24 250 M30 246 L24 250 L30 254", {}, gChain);
    sub(35, 244, "c", 4, { class: "tiny muted" }, gChain);
    text(35, 264, cv[4], { class: "tiny bit" }, gChain);
    path("M390 250 L366 250", {}, gChain);
    text(
      396,
      254,
      "0",
      { "text-anchor": "start", class: "tiny muted" },
      gChain,
    );
    show(gChain, 14, 16);
    caption(14, "n full adder blocks, n digit addition");

    /* ================= 15every switch leaks heat ================= */
    const gHeat = mk("g", { class: "heat thin" }, root);
    const squiggles = [];
    BX.forEach((x) =>
      [x + 14, x + 31, x + 48].forEach((sx, j) => {
        squiggles.push(
          path(
            `M${sx} 222 c -3 -4 3 -8 0 -12 c -3 -4 3 -8 0 -12`,
            { opacity: 0 },
            gHeat,
          ),
        );
      }),
    );
    show(gHeat, 15, 16);
    const heat = gsap.timeline({ repeat: -1 });
    squiggles.forEach((s, i) => {
      const t0 = (i % 7) * 0.22 + Math.floor(i / 7) * 0.13;
      heat.set(s, { y: 8, opacity: 0 }, t0);
      heat.to(
        s,
        {
          keyframes: [
            { y: -2, opacity: 0.9, duration: 0.9, ease: "sine.out" },
            { y: -11, opacity: 0, duration: 0.6, ease: "sine.in" },
          ],
        },
        t0,
      );
    });
    loop(15, heat);
    const formula = mk("text", {
      x: 220,
      y: 150,
      "text-anchor": "middle",
      class: "formula",
    });
    formula.appendChild(document.createTextNode("P "));
    const propto = document.createElementNS(NS, "tspan");
    propto.setAttribute("class", "propto");
    propto.textContent = "\u221d"; // the glyph is tiny in this font, so it gets its own size
    formula.appendChild(propto);
    formula.appendChild(document.createTextNode(" C V\u00b2 f"));
    show(formula, 15, 16);
    caption(15, "heating: capacitance × voltage² × clock");

    /* ================= 16memory: a loop ================= */
    const gLatch = group({ "data-diagram": "latch" }, root, "220 250");
    [
      [150, 215],
      [150, 285],
      [270, 215],
      [270, 285],
    ].forEach(([x, y]) => gsap.set(nand(gLatch), { x, y }));
    const wLatch = mk("g", {}, gLatch);
    path(
      "M104 208 L126 208 M104 250 L114 250 M114 222 L114 278 M114 222 L126 222 M114 278 L126 278",
      {},
      wLatch,
    );
    path(
      "M172 215 L200 215 L200 208 L246 208 M200 215 L200 262 L120 262 L120 292 L126 292",
      {},
      wLatch,
    );
    path("M172 285 L210 285 L210 292 L246 292 M292 215 L330 215", {}, wLatch);
    dot(114, 250, 1.8, wLatch);
    dot(200, 215, 1.8, wLatch);
    dot(306, 215, 1.8, wLatch);
    text(98, 212, "D", { "text-anchor": "end" }, wLatch);
    text(98, 254, "WE", { "text-anchor": "end" }, wLatch);
    text(336, 219, "Q", { "text-anchor": "start" }, wLatch);
    const latchValues = group({ "data-latch-values": "" }, gLatch);
    logicCases(
      "latch",
      latchValues,
      [
        { inputs: [0, 1], output: 0 },
        { inputs: [1, 1], output: 1 },
        { inputs: [1, 0], output: 1 },
        { inputs: [0, 0], output: 1 },
        { inputs: [0, 1], output: 0 },
        { inputs: [0, 0], output: 0 },
        { inputs: [1, 0], output: 0 },
        { inputs: [1, 1], output: 1 },
      ],
      [
        { x: 98, y: 234, anchor: "end" },
        { x: 98, y: 276, anchor: "end" },
        { x: 336, y: 241, anchor: "start" },
      ],
      "heat",
      "register",
    );
    show(latchValues, "latch", "register", {}, 0.35);
    const fb1 = path(
      "M306 215 L306 250 L236 250 L236 278 L246 278",
      {},
      gLatch,
    );
    const fb2 = path(
      "M292 285 L316 285 L316 240 L310 240 A4 4 0 0 0 302 240 L240 240 L240 222 L246 222",
      {},
      gLatch,
    );
    show(gLatch, 16, undefined, { scale: 1, x: 0, y: 0 });
    // Keep the actual circuit visible as it shrinks into the first register cell.
    // Its geometry and feedback remain unchanged at the settled latch scene.
    tl.to(
      gLatch,
      { scale: 0.18, x: -120, y: -4, duration: DUR * 0.48, ease: EASE },
      at(17),
    );
    tl.to(
      gLatch,
      { opacity: 0, duration: DUR * 0.22, ease: EASE },
      at(17) + DUR * 0.38,
    );
    for (const fb of [fb1, fb2]) draw(fb, at(16) + DUR * 0.55, DUR * 0.45);
    caption(16, "a latch: the output feeds back into the inputs");

    /* ================= 17 · one latch becomes a four-bit register ================= */
    const gRegister = group({ "data-diagram": "register" }, root, "220 250");
    // Children stage their entrances; this parent handles only the later exit.
    tl.set(gRegister, { opacity: 1 }, 0);
    tl.to(gRegister, { y: 32, duration: DUR * 0.55, ease: EASE }, at(18));
    const cellLabels = [],
      dataLabels = [],
      outputLabels = [];
    const cellCentres = [100, 180, 260, 340];
    cellCentres.forEach((cx, i) => {
      const cell = group({ "data-register-cell": i }, gRegister, `${cx} 246`);
      const box = path(
        `M${cx - 28} 213 H${cx + 28} V279 H${cx - 28} Z`,
        {},
        cell,
      );
      const ports = group({}, cell);
      path(`M${cx} 195 V213 M${cx} 279 V301`, {}, ports);
      dataLabels.push(text(cx, 230, "D", { class: "tiny" }, ports));
      outputLabels.push(text(cx, 271, "Q", { class: "tiny" }, ports));
      cellLabels.push(text(cx, 251, "1 bit", { class: "caption" }, ports));
      if (i === 0) {
        hideAt0(cell);
        tl.to(cell, { opacity: 1, duration: DUR * 0.2 }, at(17) + DUR * 0.26);
        draw(box, at(17) + DUR * 0.26, DUR * 0.28);
        hideAt0(ports);
        tl.to(ports, { opacity: 1, duration: DUR * 0.2 }, at(17) + DUR * 0.48);
      } else {
        // Repeated cells emerge from the first block, then spread into an aligned row.
        hideAt0(cell, { x: 100 - cx, scale: 0.92 });
        tl.to(
          cell,
          { x: 0, scale: 1, opacity: 1, duration: DUR * 0.3, ease: EASE },
          at(17) + DUR * (0.48 + i * 0.045),
        );
      }
    });
    const sharedWrite = group({ "data-shared-write": "" }, gRegister);
    hideAt0(sharedWrite);
    tl.to(sharedWrite, { opacity: 1, duration: DUR * 0.1 }, at(17) + DUR * 0.8);
    const bus = path("M48 330 H322", {}, sharedWrite);
    draw(bus, at(17) + DUR * 0.8, DUR * 0.2);
    cellCentres.forEach((cx) => {
      const branch = path(`M${cx - 18} 330 V279`, {}, sharedWrite);
      draw(branch, at(17) + DUR * 0.86, DUR * 0.14);
      const junction = dot(cx - 18, 330, 1.8, sharedWrite);
      hideAt0(junction);
      tl.to(
        junction,
        { opacity: 1, duration: DUR * 0.08 },
        at(17) + DUR * 0.92,
      );
    });
    const writeLabel = text(
      39,
      334,
      "WE",
      { "text-anchor": "end" },
      sharedWrite,
    );
    const registerTitle = text(
      220,
      166,
      "4-bit register",
      { class: "caption" },
      gRegister,
    );
    hideAt0(registerTitle);
    tl.to(
      registerTitle,
      { opacity: 1, duration: DUR * 0.18 },
      at(17) + DUR * 0.82,
    );
    caption(17, "four one-bit latches · one shared write-enable");

    /* ================= 18 · copy the answer, then hold it ================= */
    // Keep the same four register cells on screen; make room above for the adder.
    tl.to(
      [registerTitle, ...cellLabels],
      { opacity: 0, duration: DUR * 0.3 },
      at(18),
    );
    const gStored = group({ "data-diagram": "stored-answer" }, root);
    key(gStored, 18, {}, null, 0.35);
    text(
      220,
      70,
      "0011 + 0110 = 1001",
      { class: "caption", "data-calculation": 0 },
      gStored,
    );
    text(220, 92, "4-bit adder", { class: "caption" }, gStored);
    const savedDigits = [];
    cellCentres.forEach((cx, i) => {
      mk("rect", { x: cx - 28, y: 128, width: 56, height: 46, rx: 3 }, gStored);
      path(
        `M${cx - 5} 151 H${cx + 5} M${cx} 146 V156`,
        { class: "muted" },
        gStored,
      );
      path(`M${cx - 10} 116 V128 M${cx + 10} 116 V128`, {}, gStored);
      text(
        cx - 10,
        111,
        "0011"[i],
        { class: "tiny bit", "data-operand-a": i },
        gStored,
      );
      text(
        cx + 10,
        111,
        "0110"[i],
        { class: "tiny bit", "data-operand-b": i },
        gStored,
      );
      if (i < 3)
        path(
          `M${cx + 52} 151 H${cx + 28} M${cx + 34} 147 L${cx + 28} 151 L${cx + 34} 155`,
          {},
          gStored,
        );
      const link = path(`M${cx} 174 V227`, { "data-answer-wire": i }, gStored);
      draw(link, at(18) + DUR * 0.5, DUR * 0.4);
      // Put each live value beside its terminal rather than floating on the wire.
      tl.to(
        dataLabels[i],
        { attr: { x: cx - 9, y: 229 }, duration: DUR * 0.55, ease: EASE },
        at(18),
      );
      tl.to(
        outputLabels[i],
        { attr: { x: cx - 9, y: 270 }, duration: DUR * 0.55, ease: EASE },
        at(18),
      );
      text(
        cx + 9,
        262,
        "1001"[i],
        { class: "bit", "data-answer-bit": i },
        gStored,
      );
      savedDigits.push(
        text(
          cx + 9,
          303,
          "1001"[i],
          { class: "bit", "data-saved-bit": i },
          gStored,
        ),
      );
    });
    path("M72 151 H50 M56 147 L50 151 L56 155 M390 151 H368", {}, gStored);
    text(
      397,
      155,
      "0",
      { class: "tiny muted", "text-anchor": "start" },
      gStored,
    );
    // Keep the enable value on the same baseline as WE, before the wire starts.
    tl.to(
      writeLabel,
      { attr: { x: 24 }, duration: DUR * 0.55, ease: EASE },
      at(18),
    );
    const writeValues = ["1", "0"].map((value) =>
      text(
        38,
        366,
        value,
        { class: "bit", "data-write-value": value },
        gStored,
      ),
    );
    const copyPulse = cellCentres.map((cx) => dot(cx, 176, 2.5, gStored));
    // One deliberate demonstration per visit. It finishes on the retained answer.
    // Pause during scroll transitions and reset only once the entire overlay is hidden.
    // This avoids a visible reset when the user reverses scroll or leaves mid-demonstration.
    const storeDemo = gsap.timeline({ paused: true });
    storeDemo.set(
      [writeValues[1], ...copyPulse, ...savedDigits],
      { opacity: 0 },
      0,
    );
    storeDemo.set(writeValues[0], { opacity: 1 }, 0);
    storeDemo.set(copyPulse, { attr: { cy: 176 } }, 0);
    storeDemo.to(copyPulse, { opacity: 1, duration: 0.25 }, 0.3);
    storeDemo.to(
      copyPulse,
      { attr: { cy: 245 }, duration: 0.9, ease: "none" },
      0.5,
    );
    storeDemo.to(savedDigits, { opacity: 1, duration: 0.4 }, 1.1);
    storeDemo.to(copyPulse, { opacity: 0, duration: 0.25 }, 1.3);
    storeDemo.to(writeValues[0], { opacity: 0, duration: 0.3 }, 2.5);
    storeDemo.to(writeValues[1], { opacity: 1, duration: 0.3 }, 2.8);
    storeDemo.time(0.001, true).time(0, true);
    afterRender.push(() => {
      const progress = tl.time();
      if (progress <= index(17) + hold) storeDemo.pause(0);
      else if (Math.abs(progress - index(18)) <= hold) storeDemo.play();
      else storeDemo.pause();
    });

    key(gRegister, 17, { opacity: 1 }, null, -1);
    key(gRegister, "timing", { opacity: 0, scale: 0.7, y: 32 }, null, 0, 0.6);
    key(gStored, "timing", { opacity: 0 }, null, 0, 0.6);
    const computer = COMPUTER_SCENES.build({
      root,
      tl,
      hold,
      at,
      index,
      DUR,
      EASE,
      mk,
      group,
      path,
      text,
      key,
      show,
      draw,
      caption,
      hideAt0,
      afterRender,
    });
    tl.to({}, { duration: hold }, index("computer") - hold);

    /* ================= compile keys into the timeline ================= */
    for (const [el, ks] of keys) {
      ks.sort((a, b) => index(a.s) - index(b.s));
      const first = ks[0];
      if (first.late >= 0) {
        const hidden = { ...first.p, opacity: 0, ...(first.from || {}) };
        tl.set(el, hidden, 0);
        tl.fromTo(
          el,
          hidden,
          {
            ...first.p,
            duration: DUR * (1 - first.late),
            ease: EASE,
            immediateRender: false,
          },
          at(first.s) + DUR * first.late,
        );
      }
      for (let i = 1; i < ks.length; i++) {
        const a = ks[i - 1],
          b = ks[i];
        const from = {};
        for (const k in b.p) if (k in a.p) from[k] = a.p[k];
        Object.assign(from, b.from || {});
        tl.fromTo(
          el,
          from,
          {
            ...b.p,
            duration: DUR * b.span,
            ease: EASE,
            immediateRender: false,
          },
          at(b.s),
        );
      }
    }
    return {
      tl,
      loops,
      afterRender,
      storeDemo,
      ...computer,
      demos: [...logicDemos, ...computer.demos],
    };
  }

  return { build };
})();
