// Saved animation fragment. See programmable-logic.md for integration notes.
    /* ================= 19look-up table ================= */
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
    key(gLut, 19, { scale: 1, x: 0, y: 0 }, null, 0.4);
    key(gLut, 20, { scale: 0.31, x: 45, y: 13, opacity: 0 });
    caption(19, 'look-up table: eight memory bits make any 3-to-1 function');

    /* ================= 20FPGA: many LUTs, programmable wiring ================= */
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
    show(gFpga, 20);
    // cells start hidden (no snap when their entrance begins) and grow in, in a random order
    tl.set(cellsEls, { opacity: 0, scale: 0.6, transformOrigin: '50% 50%' }, 0);
    tl.to(cellsEls, { opacity: 1, scale: 1, duration: DUR * 0.5, ease: EASE, stagger: { each: DUR * 0.04, from: 'random' } }, at(20) + DUR * 0.3);
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
    loop(20, signal);
    caption(20, 'FPGA: look-up tables wired together through programmable switches');

