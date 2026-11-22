'use strict';
/* ------------------------------------------------------------------ */
/* 2D diagram scenes: everything after the wafer.                      */
/*                                                                     */
/* Every element gets a value set per paragraph ("key"). build() turns */
/* those into one scrubbed GSAP timeline whose time is the paragraph   */
/* index, with each change happening between (i + hold) and (i+1 -    */
/* hold). "loops" are idle animations that run while a paragraph is    */
/* the current one. Coordinates are viewBox units (440 x 440).         */
/* ------------------------------------------------------------------ */
window.SCENES2D = (function () {
  const NS = 'http://www.w3.org/2000/svg';
  const EASE = 'power2.inOut';

  function rng(seed) {
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }

  // Smooth curve through points. Same point count → same string shape, so GSAP can tween between them.
  function curve(pts) {
    let d = `M${pts[0][0]} ${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
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
    const afterRender = [];   // functions main.js runs after each scrub, for scenes positioned from a tweened value
    const keys = new Map();
    const DUR = Math.max(0.05, 1 - 2 * hold);
    const at = (s) => s - 1 + hold;                 // when the change INTO paragraph s begins

    const mk = (tag, attrs = {}, parent = root) => {
      const e = document.createElementNS(NS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      parent.appendChild(e);
      return e;
    };
    const text = (x, y, str, attrs = {}, parent = root) => {
      const e = mk('text', { x, y, 'text-anchor': 'middle', ...attrs }, parent);
      e.textContent = str;
      return e;
    };
    const path = (d, attrs = {}, parent = root) => mk('path', { d, ...attrs }, parent);
    // text with a real subscript (Unicode subscripts fall back to the wrong font sizes)
    const sub = (x, y, base, small, attrs = {}, parent = root) => {
      const e = mk('text', { x, y, 'text-anchor': 'middle', ...attrs }, parent);
      e.appendChild(document.createTextNode(base));
      const t = document.createElementNS(NS, 'tspan');
      t.setAttribute('dy', '3.5'); t.setAttribute('font-size', '78%'); t.textContent = small;
      e.appendChild(t);
      return e;
    };
    const dot = (x, y, r = 1.8, parent = root) => mk('circle', { cx: x, cy: y, r, class: 'dot' }, parent);
    const group = (attrs = {}, parent = root, origin) => { const g = mk('g', attrs, parent); if (origin) gsap.set(g, { svgOrigin: origin }); return g; };

    // late: fraction of the transition to wait before an element's first appearance begins
    const key = (el, s, p = {}, from = null, late = 0, span = 1) => { if (!keys.has(el)) keys.set(el, []); keys.get(el).push({ s, p: { opacity: 1, ...p }, from, late, span }); };
    // span < 1 on the leaving key makes the element go early in the transition
    const show = (el, s0, s1, p = {}, span = 1) => { key(el, s0, p); if (s1 !== undefined) key(el, s1, { ...p, opacity: 0 }, null, 0, span); };
    const loop = (scene, tween, reset) => { tween.pause(); loops.push({ scene, tween, reset }); };
    const hideAt0 = (el, vars = {}) => tl.set(el, { opacity: 0, ...vars }, 0);

    // Draw a path progressively from its start, between t0 and t0 + dur on the timeline.
    // The usual dash-offset trick is unusable here: with non-scaling strokes the dash lengths are
    // screen pixels, so a scaled path only ever half-draws and then snaps complete. Instead the
    // path's geometry is rebuilt from samples along it after every scrub, and the original `d`
    // is restored once it is complete so the final shape is exact.
    const drawn = [];
    const draw = (el, t0, dur, ease = 'power1.inOut') => {
      const full = el.getAttribute('d'), L = el.getTotalLength(), N = Math.max(40, Math.ceil(L / 0.5));
      const pts = [];
      for (let i = 0; i <= N; i++) { const q = el.getPointAtLength(L * i / N); pts.push([q.x, q.y]); }
      const st = { v: 0, last: -1 };
      tl.set(st, { v: 0 }, 0);
      tl.to(st, { v: 1, duration: dur, ease }, t0);
      drawn.push(() => {
        if (st.v === st.last) return;
        st.last = st.v;
        if (st.v >= 1) { el.setAttribute('d', full); return; }
        let d = `M${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)}`;
        if (st.v > 0) {
          const k = st.v * N, n = Math.floor(k), f = k - n;
          for (let i = 1; i <= n; i++) d += ` L${pts[i][0].toFixed(2)} ${pts[i][1].toFixed(2)}`;
          if (n < N) { const a = pts[n], b = pts[n + 1]; d += ` L${(a[0] + (b[0] - a[0]) * f).toFixed(2)} ${(a[1] + (b[1] - a[1]) * f).toFixed(2)}`; }
        }
        el.setAttribute('d', d);
      });
    };
    afterRender.push(() => { for (const f of drawn) f(); });

    const caption = (s, str, s1 = s + 1) => {
      const t = text(220, 380, str, { class: 'muted caption' });
      hideAt0(t);
      tl.to(t, { opacity: 1, duration: DUR * 0.35 }, at(s) + DUR * 0.65);
      tl.to(t, { opacity: 0, duration: DUR * 0.35 }, at(s1));
    };

    /* ================= 3 · cross-section seeded with boron ================= */
    const gSlab = group({}, root, '220 250');
    mk('rect', { x: 70, y: 200, width: 300, height: 100, rx: 3 }, gSlab);
    const r = rng(11);
    const trenches = [[100, 165], [275, 340]];
    const inTrench = (x, y) => y < 250 && trenches.some(([a, b]) => x > a - 4 && x < b + 4);
    const gBoron = mk('g', { class: 'hollow' }, gSlab);
    // Scatter the dopants, but never let two rings touch: a candidate that lands on a neighbour is
    // nudged straight away from it to a clear spacing, and dropped if it still collides or leaves
    // its region. Same random sequence as before, so the picture barely changes.
    const spread = (n, pick, inside, min, place, retries = 0) => {
      const placed = [];
      const clear = (x, y) => inside(x, y) && !placed.some(([px, py]) => Math.hypot(px - x, py - y) < min);
      for (let i = 0; i < n; i++) {
        for (let attempt = 0; attempt <= retries; attempt++) {
          let [x, y] = pick();
          if (!inside(x, y)) continue;
          for (let pass = 0; pass < 3; pass++) {
            const near = placed.find(([px, py]) => Math.hypot(px - x, py - y) < min);
            if (!near) break;
            const d = Math.hypot(x - near[0], y - near[1]) || 0.001;
            x = near[0] + (x - near[0]) / d * min; y = near[1] + (y - near[1]) / d * min;
          }
          if (!clear(x, y)) continue;
          placed.push([x, y]);
          place(x, y);
          break;
        }
      }
    };
    spread(70, () => [78 + r() * 284, 208 + r() * 84],
      (x, y) => !inTrench(x, y) && x > 76 && x < 364 && y > 206 && y < 294, 5.4,
      (x, y) => mk('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: 2 }, gBoron));
    key(gSlab, 3, { scale: 1 }, { scale: 1 }, 0.82);   // appears in place, once the wafer's rim fills the same rectangle
    key(gSlab, 9, { scale: 0.55, opacity: 0 });
    caption(3, 'cross-section of the wafer · ○ boron');

    /* ================= 4 · implant two trenches of phosphorus ================= */
    const gTrench = mk('g', { class: 'thin' }, gSlab);
    for (const [x0, x1] of trenches) mk('rect', { x: x0, y: 200, width: x1 - x0, height: 45, rx: 6 }, gTrench);
    show(gTrench, 4);
    const gPhos = mk('g', { class: 'dots' }, gSlab);
    const pdots = [];
    for (const [x0, x1] of trenches) spread(18, () => [x0 + 7 + r() * (x1 - x0 - 14), 207 + r() * 32],
      (x, y) => x > x0 + 5 && x < x1 - 5 && y > 205 && y < 241, 4.7,   // filled dots only need to stay clear
      (x, y) => pdots.push(mk('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: 2.1 }, gPhos)), 6);   // last user of the random sequence, so retries are free
    hideAt0(pdots, { y: -130 });
    tl.to(pdots, { y: 0, opacity: 1, duration: DUR * 0.6, ease: 'power2.in', stagger: { each: (DUR * 0.4) / pdots.length, from: 'random' } }, at(4));
    const gGuns = mk('g', { class: 'thin' }, gSlab);
    for (const [x0, x1] of trenches) { const cx = (x0 + x1) / 2; path(`M${cx - 11} 120 L${cx + 11} 120 L${cx + 5} 136 L${cx - 5} 136 Z`, {}, gGuns); }
    hideAt0(gGuns);
    tl.to(gGuns, { opacity: 1, duration: DUR * 0.15 }, at(4));
    tl.to(gGuns, { opacity: 0, duration: DUR * 0.15 }, at(4) + DUR * 0.85);
    caption(4, '● phosphorus, fired in from above');

    /* ================= 5 · three wires ================= */
    const gWires = mk('g', {}, gSlab);
    mk('line', { x1: 132, y1: 128, x2: 132, y2: 200 }, gWires);
    mk('line', { x1: 307, y1: 128, x2: 307, y2: 200 }, gWires);
    mk('line', { x1: 220, y1: 128, x2: 220, y2: 186 }, gWires);
    mk('rect', { x: 182, y: 186, width: 76, height: 7 }, gWires);                       // gate electrode
    mk('rect', { x: 182, y: 194, width: 76, height: 6, class: 'thin dashed' }, gWires);  // insulating gap
    key(gWires, 5, { y: 0 }, { y: -100 });

    /* ================= 6 · voltages, and the elevation metaphor ================= */
    const vL = text(132, 114, '1 V', {}, gSlab); show(vL, 6);
    const vR = text(398, 126, '0 V', { 'text-anchor': 'start' }, gSlab); show(vR, 6);
    const P_slope = [[165, 247], [190, 250], [205, 254], [220, 258], [235, 262], [250, 265], [275, 268]];
    const P_hill = [[165, 247], [190, 250], [205, 236], [220, 227], [235, 236], [250, 265], [275, 268]];
    const prof = path(curve(P_slope), { class: 'muted' }, gSlab);
    key(prof, 6, { attr: { d: curve(P_slope) } });
    key(prof, 7, { attr: { d: curve(P_hill) } });
    key(prof, 8, { attr: { d: curve(P_slope) } });
    caption(6, 'voltage as elevation: electrons roll downhill');

    /* ================= 7 · gate at 0 V: a hill blocks the way ================= */
    const vG0 = text(220, 114, '0 V', {}, gSlab); show(vG0, 7, 8);
    const vG1 = text(220, 114, '1 V', {}, gSlab); show(vG1, 8);
    const gE7 = mk('g', { class: 'dots' }, gSlab); show(gE7, 7, 8);
    const bounce = gsap.timeline({ repeat: -1 });
    [0, 1, 2].forEach((i) => {
      const e = mk('circle', { r: 2.9 }, gE7);
      gsap.set(e, { x: 132, y: 134, opacity: 0 });
      bounce.set(e, { x: 132, y: 134, opacity: 0 }, i * 1.3);
      bounce.to(e, { keyframes: [
        { opacity: 1, duration: 0.15 },
        { y: 214, duration: 0.7, ease: 'none' },
        { x: 168, y: 241, duration: 0.45, ease: 'none' },
        { x: 199, y: 244, duration: 0.45, ease: 'power1.out' },
        { x: 181, y: 243, duration: 0.45, ease: 'power1.in' },
        { x: 199, y: 244, duration: 0.45, ease: 'power1.out' },
        { x: 179, y: 243, duration: 0.45, ease: 'power1.in' },
        { opacity: 0, duration: 0.3 },
      ] }, i * 1.3);
    });
    loop(7, bounce);
    caption(7, 'the gate at 0 V leaves a hill between the islands');

    /* ================= 8 · gate at 1 V: electrons flow, bulb lights ================= */
    const gGlow = mk('g', {}, gSlab);                       // faint yellow fill, only while the bulb is on
    const glow = mk('circle', { cx: 362, cy: 122, r: 8.4, class: 'glow' }, gGlow);
    show(gGlow, 8, 9);
    const gBulb = mk('g', {}, gSlab);
    path('M307 128 L307 122 L353 122 M371 122 L392 122', {}, gBulb);   // drain wire, through the lamp, on to 0 V
    mk('circle', { cx: 362, cy: 122, r: 9 }, gBulb);
    path('M355.6 115.6 L368.4 128.4 M368.4 115.6 L355.6 128.4', { class: 'thin' }, gBulb);   // lamp symbol
    show(gBulb, 6);
    const gRays = mk('g', { class: 'thin' }, gSlab);
    for (let k = 0; k < 7; k++) {
      const a = -150 * Math.PI / 180 + k * (Math.PI * 1.1 / 6);
      mk('line', { x1: (362 + 13 * Math.cos(a)).toFixed(1), y1: (122 + 13 * Math.sin(a)).toFixed(1), x2: (362 + 19 * Math.cos(a)).toFixed(1), y2: (122 + 19 * Math.sin(a)).toFixed(1) }, gRays);
    }
    show(gRays, 8, 9);
    const gE8 = mk('g', { class: 'dots' }, gSlab); show(gE8, 8, 9);
    const flow = gsap.timeline({ repeat: -1 });
    [0, 1, 2, 3].forEach((i) => {
      const e = mk('circle', { r: 2.9 }, gE8);
      gsap.set(e, { x: 132, y: 134, opacity: 0 });
      flow.set(e, { x: 132, y: 134, opacity: 0 }, i * 0.9);
      flow.to(e, { keyframes: [
        { opacity: 1, duration: 0.12 },
        { y: 214, duration: 0.6, ease: 'none' },
        { x: 168, y: 242, duration: 0.4, ease: 'none' },
        { x: 220, y: 256, duration: 0.5, ease: 'none' },
        { x: 275, y: 266, duration: 0.5, ease: 'none' },
        { x: 307, y: 228, duration: 0.4, ease: 'none' },
        { x: 307, y: 122, duration: 0.6, ease: 'none' },
        { x: 352, y: 122, duration: 0.3, ease: 'none' },
        { opacity: 0, duration: 0.08 },
        { x: 372, y: 122, duration: 0.01 },
        { opacity: 1, duration: 0.08 },
        { x: 392, y: 122, duration: 0.2, ease: 'none' },
        { opacity: 0, duration: 0.12 },
      ] }, i * 0.9);
    });
    loop(8, flow);
    const pulse = gsap.to([gRays, glow], { opacity: 0.45, duration: 0.7, yoyo: true, repeat: -1, ease: 'sine.inOut' });
    loop(8, pulse);
    caption(8, 'n-type MOSFET: a switch with no moving parts');

    /* ================= 9 · the same transistor as a symbol ================= */
    // transistor symbol drawn around its own origin; 'p' adds the bubble
    const mos = (type, parent) => {
      const g = mk('g', {}, parent);
      mk('rect', { x: -22, y: -22, width: 44, height: 44, class: 'ghost' }, g);   // centres the bbox on (0, 0)
      gsap.set(g, { transformOrigin: '50% 50%' });
      path(type === 'p' ? 'M-22 0 L-14 0' : 'M-22 0 L-8 0', {}, g);
      if (type === 'p') mk('circle', { cx: -11, cy: 0, r: 2.6 }, g);
      path('M-8 -12 L-8 12 M-3 -12 L-3 12', {}, g);
      path('M-3 -8 L10 -8 L10 -22 M-3 8 L10 8 L10 22', {}, g);
      return g;
    };
    const nand = (parent) => {
      const g = mk('g', {}, parent);
      mk('rect', { x: -24, y: -12, width: 48, height: 24, class: 'ghost' }, g);
      path('M-16 -12 L-4 -12 A12 12 0 0 1 -4 12 L-16 12 Z', {}, g);
      mk('circle', { cx: 10.6, cy: 0, r: 2.4 }, g);
      path('M-24 -7 L-16 -7 M-24 7 L-16 7 M13 0 L22 0', {}, g);
      return g;
    };
    const gLogic = group({}, root, '220 250');
    const nHero = mos('n', gLogic);
    key(nHero, 9, { x: 220, y: 250, scale: 1.7 }, { scale: 0.8 });
    const symLabels = mk('g', { class: 'muted' }, gLogic);
    text(176, 254, 'gate', { 'text-anchor': 'end' }, symLabels);   // the only terminal the text names
    show(symLabels, 9, 10);
    caption(9, 'the same transistor, drawn as a symbol');

    /* ================= 10 · NOT gate: two transistors ================= */
    const pHero = mos('p', gLogic);
    key(pHero, 10, { x: 220, y: 210, scale: 1 }, { scale: 0.6 });
    key(nHero, 10, { x: 220, y: 290, scale: 1 });
    const wNot = mk('g', {}, gLogic);
    path('M196 172 L244 172 M230 172 L230 188 M230 232 L230 268 M230 312 L230 330 M196 330 L244 330', {}, wNot);
    path('M230 250 L268 250 M172 250 L198 250 M198 210 L198 290', {}, wNot);
    dot(230, 250, 1.8, wNot); dot(198, 250, 1.8, wNot);
    text(186, 176, '1', { 'text-anchor': 'end', class: 'muted' }, wNot);
    text(186, 334, '0', { 'text-anchor': 'end', class: 'muted' }, wNot);
    text(164, 254, 'A', { 'text-anchor': 'end' }, wNot);
    text(276, 254, 'Ā', { 'text-anchor': 'start' }, wNot);
    show(wNot, 10, 11);
    caption(10, 'NOT gate: p-type above, n-type below');

    /* ================= 11 · NAND gate: four transistors ================= */
    key(pHero, 11, { x: 190, y: 210, scale: 1 });
    key(nHero, 11, { x: 230, y: 275, scale: 1 });
    const p2 = mos('p', gLogic); key(p2, 11, { x: 260, y: 210, scale: 1 }, { scale: 0.6 });
    const n2 = mos('n', gLogic); key(n2, 11, { x: 230, y: 322, scale: 1 }, { scale: 0.6 });
    const wNand = mk('g', {}, gLogic);
    path('M170 172 L290 172 M200 172 L200 188 M270 172 L270 188 M200 232 L200 250 M270 232 L270 250 M200 250 L300 250', {}, wNand);
    path('M240 250 L240 253 M240 297 L240 300 M240 344 L240 356 M200 356 L280 356', {}, wNand);
    path('M150 210 L168 210 M150 210 L150 275 L208 275', {}, wNand);
    path('M150 322 L208 322 M176 322 L176 280 A4 4 0 0 1 176 270 L176 240 L196 240 A4 4 0 0 1 204 240 L238 240 L238 210', {}, wNand);
    dot(240, 250, 1.8, wNand); dot(176, 322, 1.8, wNand); dot(150, 210, 1.8, wNand);
    text(160, 176, '1', { 'text-anchor': 'end', class: 'muted' }, wNand);
    text(190, 360, '0', { 'text-anchor': 'end', class: 'muted' }, wNand);
    text(142, 214, 'A', { 'text-anchor': 'end' }, wNand);
    text(142, 326, 'B', { 'text-anchor': 'end' }, wNand);
    text(306, 254, 'out', { 'text-anchor': 'start' }, wNand);
    show(wNand, 11, 12);
    caption(11, 'NAND gate');

    /* ================= 12 · the NAND gate gets a symbol ================= */
    // The D outline draws itself around the circuit, which shrinks and dims inside it; then the
    // bubble, the two input stubs and the output stub appear. From here on this is how a NAND is drawn.
    const gSymOuter = group({}, root);                 // the adder's one-shot fade animates this wrapper
    const gSym = group({}, gSymOuter, '220 250');      // ...while the scroll timeline animates this
    const symG = nand(gSym);
    symG.setAttribute('class', 'hero-nand');   // its stroke width follows --k, so it can thin to match the tiled gates
    gsap.set(symG, { x: 220, y: 250, scale: 3.2, transformOrigin: '50% 50%' });
    const symD = symG.querySelectorAll('path')[0], symStubs = symG.querySelectorAll('path')[1], symBubble = symG.querySelector('circle');
    const nandLabels = mk('g', {}, gSym);
    text(134, 233, 'A', { 'text-anchor': 'end' }, nandLabels);
    text(134, 277, 'B', { 'text-anchor': 'end' }, nandLabels);
    text(296, 255, 'out', { 'text-anchor': 'start' }, nandLabels);
    // first the circuit shrinks and dims (span 0.4 of the transition)...
    key(gLogic, 12, { scale: 0.34, x: -15, y: -5, opacity: 0.35 }, null, 0, 0.4);   // encapsulated inside the symbol
    hideAt0(gSym);
    {
      // ...then the D outline draws itself around it, and finally the bubble, stubs and labels appear
      tl.set([symStubs, symBubble, nandLabels], { opacity: 0 }, 0);
      tl.to(gSym, { opacity: 1, duration: 0.01 }, at(12) + DUR * 0.42);
      draw(symD, at(12) + DUR * 0.42, DUR * 0.38);
      tl.to([symStubs, symBubble, nandLabels], { opacity: 1, duration: DUR * 0.2, ease: EASE }, at(12) + DUR * 0.8);
    }
    key(gSym, 12, { scale: 1, x: 0, y: 0 }, null, -1);   // entrance handled above
    caption(12, 'the NAND gate symbol');

    /* ================= 13full adder: NANDs in a black box ================= */
    key(gLogic, 3, { scale: 1 });
    key(gLogic, 13, { scale: 0.34, x: -15, y: -5, opacity: 0 });   // fades away inside the shrinking symbol
    key(gSym, 13, { scale: 0.125, x: -48, y: -30 });                 // the symbol lands in the box's top-left cell
    key(gSym, 14, { scale: 0.125, x: -48, y: -30, opacity: 0 });
    const gAdd = group({}, root, '220 250');
    mk('rect', { x: 160, y: 205, width: 120, height: 90, rx: 4 }, gAdd);
    // many more NAND gates inside the box (the centre is left clear for the "+")
    const gMany = mk('g', { class: 'faint-gates' }, gAdd);
    for (const cy of [220, 250, 280]) for (const cx of [172, 196, 220, 244, 268]) {
      if (cy === 250 && cx >= 196 && cx <= 244) continue;   // the centre stays clear for the "+"
      if (cy === 220 && cx === 172) continue;               // that cell is where the landed symbol sits
      gsap.set(nand(gMany), { x: cx, y: cy, scale: 0.4, transformOrigin: '50% 50%' });
    }
    gsap.set(gMany, { opacity: 0 });
    // a second after the symbol has settled into its cell, it fades to match and the rest tile in around it
    const multiply = gsap.timeline({ paused: true });
    multiply.set(gSymOuter, { opacity: 1 }, 0);
    multiply.set(gMany, { opacity: 0 }, 0);
    // the landed symbol also thins to the tiled gates' stroke width (--k is the same 0.5 factor
    // the .faint-gates rule uses), so afterwards they all look the same
    multiply.set(symG, { '--k': 1 }, 0);
    multiply.to(gSymOuter, { opacity: 0.35, duration: 0.8, ease: 'power1.inOut' }, 1);
    multiply.to(symG, { '--k': 0.5, duration: 0.8, ease: 'power1.inOut' }, 1);
    multiply.to(gMany, { opacity: 0.35, duration: 0.9, ease: 'power1.inOut' }, 1);
    loop(13, multiply, () => {
      gsap.to(gSymOuter, { opacity: 1, duration: 0.4, overwrite: 'auto' });
      gsap.to(symG, { '--k': 1, duration: 0.4, overwrite: 'auto' });
      gsap.to(gMany, { opacity: 0, duration: 0.4, overwrite: 'auto' });
    });
    path('M211.5 250 L228.5 250 M220 241.5 L220 258.5', { class: 'muted' }, gAdd);   // a drawn "+", exactly centred
    path('M122 225 L160 225 M122 250 L160 250 M122 275 L160 275 M280 238 L318 238 M280 266 L318 266', {}, gAdd);
    sub(116, 229, 'a', 'i', { 'text-anchor': 'end' }, gAdd);
    sub(116, 254, 'b', 'i', { 'text-anchor': 'end' }, gAdd);
    sub(116, 279, 'c', 'i', { 'text-anchor': 'end' }, gAdd);
    sub(324, 242, 's', 'i', { 'text-anchor': 'start' }, gAdd);
    sub(324, 270, 'c', 'i+1', { 'text-anchor': 'start' }, gAdd);
    // worked example, written as binary numbers: digit i (bold) is the one this block handles.
    // a = 10110, b = 01101, carry in 0 → sum digit 0, carry out 1
    const bits = (xc, y, digits) => digits.forEach((dgt, k) => text(xc + (k - 2) * 8, y, dgt, { class: 'tiny ' + (k === 2 ? 'bit' : 'faint') }, gAdd));
    bits(80, 229, ['1', '0', '1', '1', '0']);
    bits(80, 254, ['0', '1', '1', '0', '1']);
    text(80, 279, '0', { class: 'tiny bit' }, gAdd);
    bits(360, 242, ['0', '0', '0', '1', '1']);
    text(360, 270, '1', { class: 'tiny bit' }, gAdd);
    show(gAdd, 13, undefined, { scale: 1, x: 0, y: 0 });
    key(gAdd, 14, { scale: 0.52, x: 29, y: 0, opacity: 0 });
    caption(13, 'full adder: one digit, with carry');

    /* ================= 14chain of adders ================= */
    const gChain = group({}, root, '220 250');
    const BX = [46, 132, 218, 304];
    // worked example 0011 + 0110 = 1001 (3 + 6 = 9), arrays indexed by digit i (0 = least significant)
    const av = ['1', '1', '0', '0'], bv = ['0', '1', '1', '0'], sv = ['1', '0', '0', '1'];
    const cv = ['0', '0', '1', '1', '0'];   // cv[i] is the carry cᵢ; cv[0] is the carry-in
    BX.forEach((x, k) => {
      const i = 3 - k;   // digit index, least significant on the right
      mk('rect', { x, y: 227, width: 62, height: 46, rx: 3 }, gChain);
      path(`M${x + 27} 250 L${x + 35} 250 M${x + 31} 246 L${x + 31} 254`, { class: 'muted' }, gChain);
      path(`M${x + 19} 205 L${x + 19} 227 M${x + 43} 205 L${x + 43} 227 M${x + 31} 273 L${x + 31} 295`, {}, gChain);
      sub(x + 19, 200, 'a', i, { class: 'tiny muted' }, gChain);
      sub(x + 43, 200, 'b', i, { class: 'tiny muted' }, gChain);
      sub(x + 31, 308, 's', i, { class: 'tiny muted' }, gChain);
      text(x + 19, 186, av[i], { class: 'tiny bit' }, gChain);
      text(x + 43, 186, bv[i], { class: 'tiny bit' }, gChain);
      text(x + 31, 322, sv[i], { class: 'tiny bit' }, gChain);
      if (k < 3) {
        path(`M${x + 86} 250 L${x + 62} 250 M${x + 68} 246 L${x + 62} 250 L${x + 68} 254`, {}, gChain);
        sub(x + 74, 244, 'c', i, { class: 'tiny muted' }, gChain);
        text(x + 74, 264, cv[i], { class: 'tiny bit' }, gChain);
      }
    });
    path('M46 250 L24 250 M30 246 L24 250 L30 254', {}, gChain);
    sub(35, 244, 'c', 4, { class: 'tiny muted' }, gChain);
    text(35, 264, cv[4], { class: 'tiny bit' }, gChain);
    path('M390 250 L366 250', {}, gChain);
    text(396, 254, '0', { 'text-anchor': 'start', class: 'tiny muted' }, gChain);
    show(gChain, 14, 16);
    caption(14, 'ripple-carry adder: n blocks, n digits');

    /* ================= 15every switch leaks heat ================= */
    const gHeat = mk('g', { class: 'heat thin' }, root);
    const squiggles = [];
    BX.forEach((x) => [x + 14, x + 31, x + 48].forEach((sx, j) => {
      squiggles.push(path(`M${sx} 222 c -3 -4 3 -8 0 -12 c -3 -4 3 -8 0 -12`, { opacity: 0 }, gHeat));
    }));
    show(gHeat, 15, 16);
    const heat = gsap.timeline({ repeat: -1 });
    squiggles.forEach((s, i) => {
      const t0 = (i % 7) * 0.22 + Math.floor(i / 7) * 0.13;
      heat.set(s, { y: 8, opacity: 0 }, t0);
      heat.to(s, { keyframes: [{ y: -2, opacity: 0.9, duration: 0.9, ease: 'sine.out' }, { y: -11, opacity: 0, duration: 0.6, ease: 'sine.in' }] }, t0);
    });
    loop(15, heat);
    const formula = mk('text', { x: 220, y: 170, 'text-anchor': 'middle', class: 'formula' });
    formula.appendChild(document.createTextNode('P '));
    const propto = document.createElementNS(NS, 'tspan');
    propto.setAttribute('class', 'propto'); propto.textContent = '\u221d';   // the glyph is tiny in this font, so it gets its own size
    formula.appendChild(propto);
    formula.appendChild(document.createTextNode(' C V\u00b2 f'));
    show(formula, 15, 16);
    caption(15, 'heating: capacitance × voltage² × clock');

    /* ================= 16memory: a loop ================= */
    const gLatch = group({}, root, '220 250');
    [[150, 215], [150, 285], [270, 215], [270, 285]].forEach(([x, y]) => gsap.set(nand(gLatch), { x, y }));
    const wLatch = mk('g', {}, gLatch);
    path('M104 208 L126 208 M104 250 L114 250 M114 222 L114 278 M114 222 L126 222 M114 278 L126 278', {}, wLatch);
    path('M172 215 L200 215 L200 208 L246 208 M200 215 L200 262 L120 262 L120 292 L126 292', {}, wLatch);
    path('M172 285 L210 285 L210 292 L246 292 M292 215 L330 215', {}, wLatch);
    dot(114, 250, 1.8, wLatch); dot(200, 215, 1.8, wLatch); dot(306, 215, 1.8, wLatch);
    text(98, 212, 'D', { 'text-anchor': 'end' }, wLatch);
    text(98, 254, 'WE', { 'text-anchor': 'end' }, wLatch);
    text(336, 219, 'Q', { 'text-anchor': 'start' }, wLatch);
    const fb1 = path('M306 215 L306 250 L236 250 L236 278 L246 278', {}, gLatch);
    const fb2 = path('M292 285 L316 285 L316 240 L310 240 A4 4 0 0 0 302 240 L240 240 L240 222 L246 222', {}, gLatch);
    show(gLatch, 16, undefined, { scale: 1, x: 0, y: 0 });
    key(gLatch, 17, { scale: 0.2, x: 12, y: 0, opacity: 0 });
    for (const fb of [fb1, fb2]) draw(fb, at(16) + DUR * 0.55, DUR * 0.45);
    caption(16, 'a latch: the output feeds back into the inputs');

    /* ================= 17look-up table ================= */
    const gLut = group({}, root, '220 250');
    mk('rect', { x: 165, y: 195, width: 110, height: 110, rx: 4 }, gLut);
    text(220, 186, 'LUT', { class: 'muted' }, gLut);
    path('M125 225 L165 225 M125 250 L165 250 M125 275 L165 275 M275 250 L315 250', {}, gLut);
    sub(118, 229, 'x', '0', { 'text-anchor': 'end' }, gLut);
    sub(118, 254, 'x', '1', { 'text-anchor': 'end' }, gLut);
    sub(118, 279, 'x', '2', { 'text-anchor': 'end' }, gLut);
    text(321, 254, 'y', { 'text-anchor': 'start' }, gLut);
    const lutBits = ['0', '1', '1', '0', '1', '0', '0', '1'];
    lutBits.forEach((b, k) => {
      const y = 201 + k * 12.5;
      text(203, y + 8, k.toString(2).padStart(3, '0'), { class: 'tiny muted' }, gLut);
      mk('rect', { x: 226, y, width: 13, height: 10.5, class: 'thin' }, gLut);
      text(232.5, y + 8, b, { class: 'tiny' }, gLut);
    });
    show(gLut, 17, undefined, { scale: 1, x: 0, y: 0 });
    key(gLut, 18, { scale: 0.31, x: 45, y: 13, opacity: 0 });
    caption(17, 'look-up table: eight memory bits make any 3-to-1 function');

    /* ================= 18FPGA: many LUTs, programmable wiring ================= */
    const gFpga = group({}, root, '220 250');
    const VCH = [70, 148, 226, 304, 382];        // vertical routing channels
    const HCH = [238, 288];                        // horizontal routing channels
    const BW = 34, BH = 26;
    const bx = (c) => VCH[c] + 22, by = (rr) => 200 + 50 * rr;
    const gRoute = mk('g', { class: 'thin' }, gFpga);
    for (const x of VCH) path(`M${x} 186 L${x} 340`, {}, gRoute);
    for (const y of HCH) path(`M58 ${y} L394 ${y}`, {}, gRoute);
    // one programmed signal path: out of LUT(0,0), through LUT(1,2), through LUT(2,3)
    const used = new Set(['0,0,out', '1,2,in1', '1,2,out', '2,3,in1', '2,3,out']);
    const cellsEls = [];
    for (let rr = 0; rr < 3; rr++) for (let c = 0; c < 4; c++) {
      const x = bx(c), y = by(rr);
      cellsEls.push(mk('rect', { x, y, width: BW, height: BH, rx: 2 }, gFpga));
      // three inputs from the channel on the left, one output to the channel on the right.
      // Unused stubs stop just short of the channel; programmed ones touch it with a dot.
      [6, 13, 20].forEach((dy, k) => {
        const on = used.has(`${rr},${c},in${k}`);
        path(`M${VCH[c] + (on ? 0 : 4)} ${y + dy} L${x} ${y + dy}`, {}, gRoute);
        if (on) dot(VCH[c], y + dy, 1.8, gFpga);
      });
      const on = used.has(`${rr},${c},out`);
      path(`M${x + BW} ${y + 13} L${VCH[c + 1] - (on ? 0 : 4)} ${y + 13}`, {}, gRoute);
      if (on) dot(VCH[c + 1], y + 13, 1.8, gFpga);
    }
    dot(148, 238, 1.8, gFpga); dot(226, 238, 1.8, gFpga);   // programmed turns at channel crossings
    show(gFpga, 18);
    // cells start hidden (no snap when their entrance begins) and grow in, in a random order
    tl.set(cellsEls, { opacity: 0, scale: 0.6, transformOrigin: '50% 50%' }, 0);
    tl.to(cellsEls, { opacity: 1, scale: 1, duration: DUR * 0.5, ease: EASE, stagger: { each: DUR * 0.04, from: 'random' } }, at(18) + DUR * 0.3);
    // the signal: a dot that travels the channels and passes through the LUTs, which flash as it does
    const sig = dot(126, 213, 2.8, gFpga);
    gsap.set(sig, { opacity: 0 });
    const flashes = [[1, 2], [2, 3]].map(([rr, c]) => { const f = mk('rect', { x: bx(c), y: by(rr), width: BW, height: BH, rx: 2, class: 'flash' }, gFpga); gsap.set(f, { opacity: 0 }); return f; });
    const signal = gsap.timeline({ repeat: -1, repeatDelay: 0.7 });
    const SPEED = 95;
    let cur = [126, 213], tcur = 0;
    const go = (x, y) => { const d = Math.hypot(x - cur[0], y - cur[1]); signal.to(sig, { attr: { cx: x, cy: y }, duration: d / SPEED, ease: 'none' }, tcur); tcur += d / SPEED; cur = [x, y]; };
    const through = (flash, xOut) => {
      signal.to(sig, { opacity: 0, duration: 0.1 }, tcur);
      signal.to(flash, { opacity: 1, duration: 0.1 }, tcur);
      signal.to(flash, { opacity: 0, duration: 0.35 }, tcur + 0.2);
      tcur += 0.4;
      signal.set(sig, { attr: { cx: xOut, cy: cur[1] } }, tcur);
      signal.to(sig, { opacity: 1, duration: 0.1 }, tcur);
      tcur += 0.1; cur = [xOut, cur[1]];
    };
    signal.set(sig, { attr: { cx: 126, cy: 213 } }, 0);
    signal.to(sig, { opacity: 1, duration: 0.15 }, 0); tcur = 0.15;
    go(148, 213); go(148, 238); go(226, 238); go(226, 263); go(248, 263);
    through(flashes[0], 282);
    go(304, 263); go(304, 313); go(326, 313);
    through(flashes[1], 360);
    go(382, 313); go(382, 338);
    signal.to(sig, { opacity: 0, duration: 0.15 }, tcur);
    loop(18, signal);
    caption(18, 'FPGA: look-up tables wired together through programmable switches');

    /* ================= compile keys into the timeline ================= */
    for (const [el, ks] of keys) {
      ks.sort((a, b) => a.s - b.s);
      const first = ks[0];
      if (first.late >= 0) {
        const hidden = { ...first.p, opacity: 0, ...(first.from || {}) };
        tl.set(el, hidden, 0);
        tl.fromTo(el, hidden, { ...first.p, duration: DUR * (1 - first.late), ease: EASE, immediateRender: false }, at(first.s) + DUR * first.late);
      }
      for (let i = 1; i < ks.length; i++) {
        const a = ks[i - 1], b = ks[i];
        const from = {};
        for (const k in b.p) if (k in a.p) from[k] = a.p[k];
        Object.assign(from, b.from || {});
        tl.fromTo(el, from, { ...b.p, duration: DUR * b.span, ease: EASE, immediateRender: false }, at(b.s));
      }
    }
    return { tl, loops, afterRender };
  }

  return { build };
})();
