import { gsap } from "gsap";
export const COMPUTER_SCENES = (function () {
  const build = ({
    includeComputer,
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
  }) => {
    const demos = [];
    const box = (parent, x, y, w, h, label, attrs = {}) => {
      const g = group(attrs, parent, `${x + w / 2} ${y + h / 2}`);
      const outline = path(`M${x} ${y} H${x + w} V${y + h} H${x} Z`, {}, g);
      if (label) text(x + w / 2, y + h / 2 + 5, label, { class: "caption" }, g);
      return { g, outline };
    };
    const lightPath = (d, parent) => {
      path(d, { class: "muted" }, parent);
      const line = path(d, { class: "computer-signal" }, parent);
      const contours = d.match(/M[^M]+/g).map((part) => {
        const probe = path(part, { class: "ghost" }, parent);
        const length = probe.getTotalLength(),
          count = Math.max(40, Math.ceil(length));
        const points = Array.from({ length: count + 1 }, (_, i) => {
          const point = probe.getPointAtLength((length * i) / count);
          return [point.x, point.y];
        });
        probe.remove();
        return { part, length, count, points };
      });
      const totalLength = contours.reduce(
        (sum, contour) => sum + contour.length,
        0,
      );
      const state = { amount: 0, last: -1 };
      gsap.set(line, { opacity: 0 });
      afterRender.push(() => {
        if (state.amount === state.last) return;
        state.last = state.amount;
        let remaining = Math.max(0, Math.min(1, state.amount)) * totalLength;
        let geometry = "";
        // Separate branches must not acquire a diagonal joining their endpoints.
        for (const { part, length, count, points } of contours) {
          if (remaining >= length) {
            geometry += part;
            remaining -= length;
            continue;
          }
          const extent = (remaining / length) * count,
            completed = Math.floor(extent);
          geometry += `M${points[0][0]} ${points[0][1]}`;
          for (let i = 1; i <= completed; i++)
            geometry += ` L${points[i][0]} ${points[i][1]}`;
          if (completed < count && extent > completed) {
            const a = points[completed],
              b = points[completed + 1],
              fraction = extent - completed;
            geometry += ` L${a[0] + (b[0] - a[0]) * fraction} ${a[1] + (b[1] - a[1]) * fraction}`;
          }
          break;
        }
        line.setAttribute("d", state.amount >= 1 ? d : geometry);
      });
      return { line, state };
    };
    const illuminate = (demo, route, time, duration = 0.65) => {
      demo.to(route.line, { opacity: 1, duration: 0.2 }, time);
      demo.to(route.state, { amount: 1, duration, ease: "none" }, time);
    };
    const glow = (x, y, parent, radius = 20) => {
      const circle = mk(
        "circle",
        { cx: x, cy: y, r: radius, class: "computer-glow" },
        parent,
      );
      gsap.set(circle, { opacity: 0 });
      return circle;
    };
    const playInScene = (scene, demo, before, finalScene) => {
      demo.pause().time(0.001, true).time(0, true);
      demos.push(demo);
      afterRender.push(() => {
        const p = tl.time();
        if (p <= index(before) + hold) demo.pause(0);
        else if (finalScene && p >= index(finalScene) - hold)
          demo.progress(1).pause();
        else if (
          Math.abs(p - index(scene)) <= hold &&
          !matchMedia("(prefers-reduced-motion: reduce)").matches
        )
          demo.play();
        else if (Math.abs(p - index(scene)) <= hold) demo.progress(1).pause();
        else demo.pause();
      });
    };

    if (includeComputer) {
      const selector = group(
        { "data-diagram": "select-values" },
        root,
        "220 220",
      );
      text(
        220,
        112,
        "four wires carry each value",
        { class: "caption" },
        selector,
      );
      path("M175 155 L255 180 V265 L175 290 Z", {}, selector);
      const upper = lightPath("M88 185 H175 L255 222 H353", selector);
      const lower = lightPath("M88 260 H175 L255 222 H353", selector);
      for (const [x, y] of [
        [135, 185],
        [135, 260],
        [309, 222],
      ]) {
        path(
          `M${x - 3} ${y + 4} L${x + 3} ${y - 4}`,
          { class: "muted thin" },
          selector,
        );
        text(x, y - 9, "4", { class: "tiny muted" }, selector);
      }
      text(74, 190, "3", { class: "caption bit" }, selector);
      text(74, 265, "6", { class: "caption bit" }, selector);
      text(216, 228, "MUX", { class: "caption" }, selector);
      path("M215 306 V278", {}, selector);
      text(215, 330, "select", { class: "caption muted" }, selector);
      const selectZero = text(236, 305, "0", { class: "bit" }, selector);
      const selectOne = text(236, 305, "1", { class: "bit" }, selector);
      const selectedThree = text(
        374,
        227,
        "3",
        { class: "caption bit" },
        selector,
      );
      const selectedSix = text(
        374,
        227,
        "6",
        { class: "caption bit" },
        selector,
      );
      gsap.set([selectOne, selectedSix], { opacity: 0 });
      show(selector, "select-values", "working-registers", {}, 0.65);
      caption(
        "select-values",
        "a control signal chooses the value",
        "working-registers",
      );
      gsap.set(upper.line, { opacity: 1 });
      upper.state.amount = 1;
      const selectDemo = gsap.timeline({ paused: true, repeat: -1 });
      selectDemo.to(
        [upper.line, selectZero, selectedThree],
        { opacity: 0, duration: 0.4 },
        2,
      );
      selectDemo.to(selectOne, { opacity: 1, duration: 0.4 }, 2.4);
      selectDemo.to(selectedSix, { opacity: 1, duration: 0.4 }, 3.1);
      illuminate(selectDemo, lower, 2.4);
      selectDemo.to(
        [lower.line, selectOne, selectedSix],
        { opacity: 0, duration: 0.4 },
        4.5,
      );
      selectDemo.set([upper.state, lower.state], { amount: 0 }, 4.9);
      selectDemo.to(selectZero, { opacity: 1, duration: 0.4 }, 5);
      selectDemo.to(selectedThree, { opacity: 1, duration: 0.4 }, 5.65);
      illuminate(selectDemo, upper, 5);
      selectDemo.to({}, { duration: 1.2 }, 5.65);
      playInScene("select-values", selectDemo, "timing");
    }

    const timing = group({ "data-diagram": "timing" }, root);
    const timingDemo = gsap.timeline({ paused: true });
    const wireGrid = group({}, timing);
    const pulses = group({}, timing);
    const values = group({}, timing);
    const initialBits = [
      0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0, 1, 1, 0,
    ];
    const nodes = initialBits.map((initial, i) => {
      const row = Math.floor(i / 5),
        column = i % 5;
      const x = 64 + column * 78,
        y = 116 + row * 65;
      const arrival =
        0.75 + column * 0.62 + row * 0.82 + ((row + 2 * column) % 3) * 0.08;
      const final = i % 4 === 3 ? initial : 1 - initial;
      const node = group({ "data-timing-node": i }, values);
      mk("circle", { cx: x, cy: y, r: 13, class: "timing-paper" }, node);
      const bit = (value) => {
        const g = group(
          { class: `timing-${value ? "one" : "zero"}`, "data-value": value },
          node,
        );
        mk("circle", { cx: x, cy: y, r: 13, class: "timing-highlight" }, g);
        text(x, y + 5, String(value), { class: "caption bit" }, g);
        return g;
      };
      const before = bit(initial);
      if (final !== initial) {
        const after = bit(final);
        gsap.set(after, { opacity: 0 });
        timingDemo.to(before, { opacity: 0, duration: 0.24 }, arrival - 0.04);
        timingDemo.to(after, { opacity: 1, duration: 0.24 }, arrival - 0.04);
      }
      return { x, y, arrival };
    });
    const pulse = (from, to, start, finish) => {
      const d = `M${from.x} ${from.y} L${to.x} ${to.y}`;
      path(d, { class: "muted thin" }, wireGrid);
      const line = path(d, { class: "timing-pulse" }, pulses);
      const state = { progress: 0 };
      gsap.set(line, { opacity: 0 });
      afterRender.push(() => {
        const head = Math.min(1, state.progress),
          tail = Math.max(0, state.progress - 0.45);
        const point = (fraction) =>
          `${from.x + (to.x - from.x) * fraction} ${from.y + (to.y - from.y) * fraction}`;
        line.setAttribute("d", `M${point(tail)} L${point(head)}`);
      });
      timingDemo.to(line, { opacity: 1, duration: 0.12 }, start);
      timingDemo.to(
        state,
        { progress: 1, duration: finish - start, ease: "none" },
        start,
      );
      timingDemo.to(line, { opacity: 0, duration: 0.25 }, finish - 0.1);
    };
    pulse({ x: 35, y: 116 }, nodes[0], 0.35, nodes[0].arrival);
    nodes.forEach((node, i) => {
      if (i % 5 < 4)
        pulse(node, nodes[i + 1], node.arrival + 0.05, nodes[i + 1].arrival);
      if (i < 15)
        pulse(node, nodes[i + 5], node.arrival + 0.05, nodes[i + 5].arrival);
    });
    timingDemo.to({}, { duration: 1.2 }, 7);
    show(timing, "timing", "select-values", {}, 0.65);
    playInScene("timing", timingDemo, "stored-answer");

    if (!includeComputer) return { demos, timingDemo };

    const machine = group(
      { "data-diagram": "computer-machine" },
      root,
      "220 210",
    );
    const registerBank = group(
      { "data-part": "register-bank" },
      machine,
      "107 195",
    );
    path("M48 120 H166 V264 H48 Z", {}, registerBank);
    const registerValues = [];
    for (let i = 0; i < 8; i++) {
      const y = 120 + i * 18;
      if (i) path(`M48 ${y} H166`, { class: "muted thin" }, registerBank);
      text(
        69,
        y + 13,
        `R${i}`,
        { class: i > 2 ? "muted" : "bit" },
        registerBank,
      );
      registerValues.push(
        text(
          132,
          y + 13,
          String(i === 1 ? 3 : i === 2 ? 6 : 0),
          { class: i > 2 ? "muted" : "bit", "data-register-value": i },
          registerBank,
        ),
      );
    }
    text(107, 110, "8 registers", { class: "caption" }, registerBank);
    text(107, 282, "16 bits each", { class: "caption muted" }, registerBank);
    const registerNine = text(
      132,
      133,
      "9",
      { class: "bit", "data-register-result": "9" },
      registerBank,
    );
    gsap.set(registerNine, { opacity: 0 });
    key(
      registerBank,
      "working-registers",
      { x: 113, y: 0, scale: 1.25 },
      { x: 113, y: 0, scale: 0.6 },
    );
    key(registerBank, "alu", { x: 0, y: 0, scale: 1 });
    key(registerBank, "addressed-memory", { opacity: 0 });
    key(registerBank, "program", { opacity: 1 });
    const bitExpansion = group({ "data-part": "bit-expansion" }, root);
    text(
      220,
      58,
      "0011 → 0000 0000 0000 0011",
      { class: "caption bit" },
      bitExpansion,
    );
    show(bitExpansion, "working-registers", "alu");
    caption(
      "working-registers",
      "more storage, built from familiar parts",
      "alu",
    );

    const alu = group({ "data-part": "alu" }, machine, "301 186");
    const aluShape = path(
      "M246 148 H288 L301 161 L314 148 H362 L345 224 H263 Z",
      {},
      alu,
    );
    text(303, 185, "ALU", { class: "caption" }, alu);
    text(303, 205, "ADD", { class: "bit" }, alu);
    text(303, 242, "ADD · AND · NOT", { class: "tiny muted" }, alu);
    key(alu, "alu", { scale: 1, x: 0, y: 0 }, { scale: 0.55, x: -70, y: 30 });
    key(alu, "addressed-memory", { opacity: 0 });
    key(alu, "program", { opacity: 1 });
    draw(aluShape, at("alu") + DUR * 0.15, DUR * 0.7);
    const datapath = group({ "data-part": "datapath" }, machine);
    const readOne = lightPath("M166 147 H195 V170 H251", datapath);
    const readTwo = lightPath("M166 165 H207 V202 H258", datapath);
    const write = lightPath("M353 188 H393 V251 H184 V129 H166", datapath);
    text(185, 140, "16", { class: "tiny muted" }, datapath);
    path("M182 151 L187 143", { class: "muted thin" }, datapath);
    text(226, 200, "16", { class: "tiny muted" }, datapath);
    path("M221 207 L226 199", { class: "muted thin" }, datapath);
    show(datapath, "alu", undefined);
    key(datapath, "addressed-memory", { opacity: 0 });
    key(datapath, "program", { opacity: 1 });
    caption(
      "alu",
      "selected values enter · an answer returns",
      "addressed-memory",
    );

    const memory = group({ "data-part": "memory" }, machine, "294 320");
    path("M220 273 H370 V361 H220 Z", {}, memory);
    const memoryTitle = text(295, 267, "memory", { class: "caption" }, memory);
    tl.to(
      memoryTitle,
      { attr: { y: 295 }, duration: DUR * 0.7, ease: EASE },
      at("program"),
    );
    const memoryTable = group({}, memory);
    text(244, 290, "address", { class: "tiny muted" }, memoryTable);
    text(326, 290, "contents", { class: "tiny muted" }, memoryTable);
    path("M220 297 H370 M271 273 V361", { class: "muted thin" }, memoryTable);
    const rowGlows = [];
    for (const [row, address, value] of [
      [0, "100", "3"],
      [1, "101", "6"],
      [2, "…", "…"],
    ]) {
      const y = 310 + row * 20;
      rowGlows.push(
        mk(
          "rect",
          { x: 222, y: y - 13, width: 146, height: 19, class: "computer-glow" },
          memoryTable,
        ),
      );
      text(246, y, address, { class: "tiny" }, memoryTable);
      text(326, y, value, { class: "bit" }, memoryTable);
    }
    gsap.set(rowGlows, { opacity: 0 });
    const memoryLabel = text(
      295,
      323,
      "program + data",
      { class: "caption" },
      memory,
    );
    gsap.set(memoryLabel, { opacity: 0 });
    key(
      memory,
      "addressed-memory",
      { scale: 1.75, x: -74, y: -110 },
      { scale: 0.7, x: -74, y: -110 },
    );
    key(memory, "program", { scale: 1, x: 0, y: 0 });
    tl.to(memoryTable, { opacity: 0, duration: DUR * 0.65 }, at("program"));
    tl.to(
      memoryLabel,
      { opacity: 1, duration: DUR * 0.65 },
      at("program") + DUR * 0.3,
    );
    caption(
      "addressed-memory",
      "the address selects a location · its contents are data",
      "program",
    );
    const memoryDemo = gsap.timeline({ paused: true });
    memoryDemo.to(rowGlows[0], { opacity: 1, duration: 0.6 }, 0.3);
    memoryDemo.to(rowGlows[0], { opacity: 0, duration: 0.5 }, 2);
    memoryDemo.to(rowGlows[1], { opacity: 1, duration: 0.6 }, 2.5);
    playInScene("addressed-memory", memoryDemo, "alu");

    const command = group({ "data-part": "instruction-registers" }, machine);
    box(command, 48, 55, 58, 36, "PC");
    box(command, 118, 55, 90, 36, "IR");
    const pcZero = text(77, 44, "0", { class: "bit", "data-pc": 0 }, command);
    const pcOne = text(77, 44, "1", { class: "bit", "data-pc": 1 }, command);
    const irEmpty = text(163, 44, "0000…", { class: "tiny muted" }, command);
    const irFetched = text(
      163,
      44,
      "ADD",
      { class: "bit", "data-ir": "ADD" },
      command,
    );
    gsap.set([pcOne, irFetched], { opacity: 0 });
    const fetchAddress = lightPath("M77 91 V102 H22 V300 H220", command);
    const fetchInstruction = lightPath(
      "M220 338 H205 V291 H10 V28 H196 V55",
      command,
    );
    text(77, 292, "address", { class: "tiny muted" }, command);
    text(286, 346, "0 · ADD R0, R1, R2", { class: "tiny" }, command);
    show(command, "program", undefined);
    caption(
      "program",
      "PC holds an address · IR holds the instruction",
      "control",
    );

    const controller = group({ "data-part": "controller" }, machine, "296 83");
    box(controller, 228, 58, 137, 50, "");
    const controlName = text(
      297,
      87,
      "control",
      { class: "caption" },
      controller,
    );
    const controlParts = group({}, controller);
    box(controlParts, 236, 68, 51, 30, "state");
    box(controlParts, 314, 68, 43, 30, "logic");
    path(
      "M287 83 H314 M308 79 L314 83 L308 87 M337 98 V104 H262 V98",
      { class: "thin muted" },
      controlParts,
    );
    gsap.set(controlName, { opacity: 0 });
    const controlDemo = gsap.timeline({ paused: true });
    controlDemo.to(controlParts, { opacity: 0, duration: 0.65 }, 2);
    controlDemo.to(controlName, { opacity: 1, duration: 0.65 }, 2.5);
    playInScene("control", controlDemo, "program", "execute");
    const controlLinks = group(
      { class: "thin", "data-part": "control-signals" },
      machine,
    );
    path(
      "M208 74 H228 M295 108 V148 M228 90 H213 V116 H69 V120 M353 108 H409 V114 H132 V120",
      { class: "dashed muted" },
      controlLinks,
    );
    text(298, 135, "operation", { class: "tiny muted" }, controlLinks);
    show(controller, "control", undefined, {}, 1);
    show(controlLinks, "control", undefined, {}, 1);
    draw(controller.querySelector("path"), at("control"), DUR * 0.8);
    caption(
      "control",
      "stored state + logic coordinate the next step",
      "execute",
    );

    const trace = group({ "data-part": "instruction-trace" }, machine);
    text(220, 14, "ADD R0, R1, R2", { class: "caption bit" }, trace);
    text(220, 420, "0001 000 001 0 00 010", { class: "tiny bit" }, trace);
    const phases = [
      "fetch",
      "decode",
      "read R1 and R2",
      "calculate 3 + 6",
      "capture 9 in R0",
    ];
    const phaseLabels = phases.map((label, i) =>
      text(
        220,
        397,
        label,
        { class: "caption", "data-instruction-phase": i },
        trace,
      ),
    );
    gsap.set(phaseLabels.slice(1), { opacity: 0 });
    show(trace, "execute", "computer");
    caption(
      "execute",
      "one instruction directs the familiar calculation",
      "computer",
    );
    const rowOneGlow = mk(
      "rect",
      { x: 49, y: 139, width: 116, height: 17, class: "computer-glow" },
      registerBank,
    );
    const rowTwoGlow = mk(
      "rect",
      { x: 49, y: 157, width: 116, height: 17, class: "computer-glow" },
      registerBank,
    );
    const resultGlow = mk(
      "rect",
      { x: 49, y: 121, width: 116, height: 17, class: "computer-glow" },
      registerBank,
    );
    const aluGlow = glow(303, 187, alu, 38);
    gsap.set([rowOneGlow, rowTwoGlow, resultGlow], { opacity: 0 });
    const computerDemo = gsap.timeline({ paused: true });
    const phase = (i, time) => {
      if (i)
        computerDemo.to(
          phaseLabels[i - 1],
          { opacity: 0, duration: 0.25 },
          time,
        );
      computerDemo.to(
        phaseLabels[i],
        { opacity: 1, duration: 0.25 },
        time + (i ? 0.25 : 0),
      );
    };
    illuminate(computerDemo, fetchAddress, 0.3, 0.8);
    computerDemo.to([pcZero, irEmpty], { opacity: 0, duration: 0.3 }, 1.2);
    computerDemo.to(pcOne, { opacity: 1, duration: 0.3 }, 1.5);
    illuminate(computerDemo, fetchInstruction, 1.5, 1);
    computerDemo.to(irFetched, { opacity: 1, duration: 0.35 }, 2.55);
    phase(1, 3);
    computerDemo.to(
      controller,
      { opacity: 0.7, duration: 0.35, yoyo: true, repeat: 1 },
      3.4,
    );
    phase(2, 4);
    computerDemo.to(
      [rowOneGlow, rowTwoGlow],
      { opacity: 1, duration: 0.4 },
      4.3,
    );
    illuminate(computerDemo, readOne, 4.3);
    illuminate(computerDemo, readTwo, 4.5);
    phase(3, 5.5);
    computerDemo.to(aluGlow, { opacity: 1, duration: 0.5 }, 5.8);
    phase(4, 6.6);
    illuminate(computerDemo, write, 6.8, 1);
    computerDemo.to(registerValues[0], { opacity: 0, duration: 0.3 }, 7.8);
    computerDemo.to(
      [registerNine, resultGlow],
      { opacity: 1, duration: 0.4 },
      8.1,
    );
    computerDemo.to({}, { duration: 1.2 }, 8.5);
    playInScene("execute", computerDemo, "control", "computer");

    const computer = group({ "data-part": "computer-outline" }, machine);
    const cpuOutline = path(
      "M31 34 H419 V267 H31 Z",
      { class: "muted thin" },
      computer,
    );
    text(396, 53, "CPU", { class: "caption" }, computer);
    box(computer, 48, 313, 60, 34, "input");
    box(computer, 128, 313, 64, 34, "output");
    path("M78 313 V267 M159 313 V267", { class: "muted" }, computer);
    show(computer, "computer", undefined);
    draw(cpuOutline, at("computer") + DUR * 0.1, DUR * 0.8);
    key(machine, "working-registers", { scale: 1, x: 0, y: 0 }, null, -1);
    key(machine, "computer", { scale: 0.95, x: 0, y: 0 });
    caption(
      "computer",
      "a processor, memory and connections to the world",
      "end",
    );

    return { demos, timingDemo, computerDemo };
  };

  return { build };
})();
