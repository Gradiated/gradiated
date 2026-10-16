import { gsap } from "gsap";
import { MEMORY_INTERFACE_SCENES } from "./memory-interface-scenes.js";
export const COMPUTER_SCENES = (function () {
  const build = ({
    includeComputer,
    controls,
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
    const signalLayers = new Map();
    const box = (parent, x, y, w, h, label, attrs = {}) => {
      const g = group(attrs, parent, `${x + w / 2} ${y + h / 2}`);
      const outline = path(`M${x} ${y} H${x + w} V${y + h} H${x} Z`, {}, g);
      if (label) text(x + w / 2, y + h / 2 + 5, label, { class: "caption" }, g);
      return { g, outline };
    };
    const lightPath = (d, parent) => {
      path(d, { class: "muted" }, parent);
      if (!signalLayers.has(parent))
        signalLayers.set(parent, group({ "data-wire-highlights": "" }, parent));
      const line = path(
        d,
        { class: "computer-signal" },
        signalLayers.get(parent),
      );
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
      const processing = group(
        { "data-diagram": "processing-unit" },
        root,
        "0 0",
      );
      const detail = group({ "data-part": "processing-detail" }, processing);
      key(processing, "working-registers", {}, null, 0.55);
      key(processing, "addressed-memory", { opacity: 0 }, null, 0, 0.6);
      const bank = group({ "data-part": "working-storage" }, detail, "88 238");
      key(bank, "working-registers", { x: 15, y: 16, scale: 1.1 });
      key(bank, "select-values", { x: 0, y: 0, scale: 1 });
      text(88, 110, "fast storage registers", { class: "caption" }, bank);
      const registerSize = text(
        88,
        363,
        "16 bits / 2 bytes each",
        { class: "tiny muted" },
        bank,
      );
      show(registerSize, "working-registers", "select-values", {}, 0.45);
      const binaryHeading = text(
        250,
        110,
        "binary",
        { class: "caption muted" },
        bank,
      );
      show(binaryHeading, "working-registers", "select-values", {}, 0.45);
      const registerNumbers = [],
        selectedRows = [];
      for (let i = 0; i < 8; i++) {
        const y = 130 + i * 27;
        const row = group({ "data-working-register": i }, bank);
        path(`M28 ${y} H148 V${y + 27} H28 Z`, {}, row);
        selectedRows.push(
          mk(
            "rect",
            {
              x: 29,
              y: y + 1,
              width: 118,
              height: 25,
              class: "computer-glow",
            },
            row,
          ),
        );
        text(52, y + 18, `R${i}`, { class: "bit" }, row);
        registerNumbers.push(
          text(
            120,
            y + 18,
            String([0, 3, 6, 2][i] || 0),
            {
              class: "bit processing-number",
              "data-working-value": i,
            },
            row,
          ),
        );
        const binaryColumn = group({ "data-register-binary": i }, row);
        path(
          `M148 ${y} H352 V${y + 27} H148`,
          { class: "processing-binary-outline" },
          binaryColumn,
        );
        const binary = ([0, 3, 6, 2][i] || 0)
          .toString(2)
          .padStart(16, "0")
          .match(/.{4}/g)
          .join(" ");
        text(
          250,
          y + 18,
          binary,
          { class: "bit processing-binary" },
          binaryColumn,
        );
        show(binaryColumn, "working-registers", "select-values", {}, 0.45);
        key(row, "working-registers", { y: 0 }, { y: -i * 27 }, 0.55);
      }
      const selection = group({ "data-part": "register-selection" }, detail);
      show(selection, "select-values", undefined);
      const routes = [];
      const route = (d) => {
        const base = path(d, { class: "interface-bus" }, selection);
        const lit = path(d, { class: "computer-signal" }, selection);
        routes.push(lit);
        return { base, lit };
      };
      const firstInput = route("M148 170.5 H160 V188 H195");
      const secondInput = route("M148 197.5 H185 V261 H195");
      const nextFirstInput = route("M148 143.5 H178 V170 H195");
      const nextSecondInput = route("M148 224.5 H172 V280 H195");
      for (const y of [160, 251]) {
        path(
          `M195 ${y} L235 ${y + 9} V${y + 29} L195 ${y + 38} Z`,
          {},
          selection,
        );
        text(214, y + 23, "MUX", { class: "caption" }, selection);
        path(`M215 ${y - 12} V${y + 4.5}`, {}, selection);
      }
      const selectA = text(215, 136, "R1", { class: "tiny bit" }, selection);
      const selectB = text(215, 227, "R2", { class: "tiny bit" }, selection);
      const outputA = route("M235 179 H281 V190 H305");
      const outputB = route("M235 270 H281 V250 H305");
      for (const [x, y] of [
        [259, 179],
        [259, 270],
      ]) {
        path(`M${x - 3} ${y + 4} L${x + 3} ${y - 4}`, {}, selection);
        text(x, y - 10, "16", { class: "tiny muted" }, selection);
      }
      const inputValues = [
        text(
          300,
          181,
          "3",
          { class: "bit processing-number", "text-anchor": "end" },
          selection,
        ),
        text(
          300,
          241,
          "6",
          { class: "bit processing-number", "text-anchor": "end" },
          selection,
        ),
      ];
      const calculation = group(
        { "data-part": "processing-calculation" },
        selection,
      );
      const adder = group({}, calculation);
      path("M305 168 H390 V278 H305 Z", {}, adder);
      text(348, 228, "adder", { class: "caption" }, adder);
      path("M348 278 V309", { class: "interface-bus" }, adder);
      const adderResult = text(
        348,
        278,
        "9",
        { class: "bit processing-number", "data-part": "adder-result" },
        adder,
      );
      show(adder, "select-values", "alu", {}, 0.55);
      const arithmetic = group({}, calculation);
      path(
        "M305 165 H337 L349 181 L361 165 H390 L375 281 H320 Z",
        {},
        arithmetic,
      );
      text(349, 215, "ALU", { class: "caption" }, arithmetic);
      text(349, 241, "ADD", { class: "bit" }, arithmetic);
      show(arithmetic, "alu", undefined);
      const answerRoute = group({ "data-part": "result-return" }, selection);
      const returnGeometry = "M348 281 V394 H12 V143.5 H28";
      path(returnGeometry, { class: "interface-bus" }, answerRoute);
      const returnLight = path(
        returnGeometry,
        { class: "computer-signal" },
        answerRoute,
      );
      show(answerRoute, "alu", undefined, {}, 0.55);
      const outputValue = text(
        367,
        345,
        "9",
        { class: "bit processing-number", "text-anchor": "start" },
        answerRoute,
      );
      const equation = text(
        349,
        143,
        "3 + 6",
        { class: "caption bit" },
        selection,
      );
      const transfers = group(
        { "data-part": "processing-transfers" },
        selection,
      );
      const flying = [0, 1, 2].map((i) =>
        text(
          0,
          0,
          "",
          {
            class: "bit processing-number",
            "data-processing-transfer": i,
          },
          transfers,
        ),
      );
      const time = { value: 0 };
      let activeProcessingScene = null;
      let heldStart = 11,
        heldEnd = 11;
      const processingDemo = gsap.timeline({ paused: true, repeat: -1 });
      processingDemo.to(time, { value: 14, duration: 14, ease: "none" });
      demos.push(processingDemo);
      const clamp = (n) => Math.max(0, Math.min(1, n));
      const setText = (node, value) => {
        if (node.textContent !== String(value))
          node.textContent = String(value);
      };
      const move = (node, geometry, progress, value) => {
        setText(node, value);
        const point = geometry.getPointAtLength(
          geometry.getTotalLength() * clamp(progress),
        );
        node.setAttribute("x", point.x);
        node.setAttribute("y", point.y - 9);
        node.style.opacity =
          progress > 0 && progress < 1
            ? String(Math.min(1, progress * 8, (1 - progress) * 8))
            : "0";
      };
      const firstTravel = path(
        "M148 170.5 H172 V179 H281 V190 H305",
        { class: "ghost" },
        transfers,
      );
      const secondTravel = path(
        "M148 197.5 H160 V270 H281 V250 H305",
        { class: "ghost" },
        transfers,
      );
      const easeBlock = gsap.parseEase("power2.inOut");
      afterRender.push(() => {
        const p = tl.time();
        if (
          p > index("instruction") + hold &&
          p < index("instruction-control") - hold
        ) {
          const progress = (p - index("instruction") - hold) / (1 - 2 * hold);
          const slide = easeBlock(clamp(progress / 0.3));
          const descend = easeBlock(clamp((progress - 0.3) / 0.25));
          const grow = easeBlock(clamp((progress - 0.55) / 0.45));
          gsap.set(processing, {
            scale: 0.18 + 0.64 * grow,
            x: 12 + 288 * slide - 220 * grow,
            y: -6 + 166.24 * descend - 58.24 * grow,
          });
          gsap.set(detail, { opacity: grow });
          gsap.set(silhouette, { opacity: 1 - grow });
          return;
        }
        if (
          p <= index("processing-block") + hold ||
          p >= index("instruction") - hold
        )
          return;
        const progress =
          (p - index("processing-block") - hold) / (1 - 2 * hold);
        const shrink = easeBlock(clamp(progress / 0.45));
        const stack = easeBlock(clamp((progress - 0.45) / 0.25));
        const slide = easeBlock(clamp((progress - 0.7) / 0.3));
        const scale = 1 - 0.82 * shrink;
        gsap.set(processing, {
          scale,
          x: 300 * shrink - 288 * slide,
          y: 91 * (1 - scale) - 80.62 * stack,
        });
        gsap.set(root.querySelector('[data-part="memory-building-block"]'), {
          y: 10 + 70 * stack,
        });
        gsap.set(root.querySelector(".memory-block-name"), { y: 70 * stack });
      });
      const redFrame = group(
        { "data-part": "processing-red-frame" },
        processing,
      );
      processing.insertBefore(redFrame, detail);
      mk(
        "rect",
        {
          x: 3,
          y: 91,
          width: 405,
          height: 316,
          rx: 8,
          class: "processing-block-tint",
        },
        redFrame,
      );
      const redOutline = path(
        "M11 91 H400 Q408 91 408 99 V399 Q408 407 400 407 H11 Q3 407 3 399 V99 Q3 91 11 91 Z",
        { class: "processing-block-frame" },
        redFrame,
      );
      key(redFrame, "processing-block");
      draw(redOutline, at("processing-block"), (1 - 2 * hold) * 0.95);
      const redTitle = text(
        205,
        79,
        "processing unit",
        { class: "caption" },
        processing,
      );
      show(redTitle, "processing-block", "instruction", {}, 0.5);
      const iconGeometry =
        "M70 160 H180 V290 H70 Z M70 192 H180 M70 224 H180 M70 256 H180 M180 190 H238 V208 H270 M180 258 H250 V248 H276 M270 180 H298 L310 195 L322 180 H365 L350 285 H285 Z M315 285 V322 H45 V176 H70";
      const silhouette = path(
        iconGeometry,
        { class: "processing-block-icon" },
        processing,
      );
      key(silhouette, "instruction", {}, null, 0.15);
      key(silhouette, "instruction-control", { opacity: 0 }, null, 0, 0.45);
      key(detail, "working-registers");
      key(detail, "instruction", { opacity: 0 }, null, 0, 0.5);
      key(detail, "instruction-control", {}, null, 0.55);
      key(processing, "instruction", { scale: 0.18, x: 12, y: -6 });
      key(processing, "instruction-control", { scale: 0.82, x: 80, y: 102 });
      const miniName = text(
        49,
        61,
        "PU",
        { class: "processing-block-name" },
        root,
      );
      key(miniName, "instruction", {}, null, 0.9);
      const miniature = group(
        { "data-part": "processing-miniature" },
        root,
        "0 0",
      );
      mk(
        "rect",
        {
          x: 12.54,
          y: 10.38,
          width: 72.9,
          height: 56.88,
          rx: 2,
          class: "processing-block-tint",
        },
        miniature,
      );
      path(
        "M14.54 10.38 H83.44 Q85.44 10.38 85.44 12.38 V65.26 Q85.44 67.26 83.44 67.26 H14.54 Q12.54 67.26 12.54 65.26 V12.38 Q12.54 10.38 14.54 10.38 Z",
        { class: "processing-block-frame" },
        miniature,
      );
      const smallIcon = group({}, miniature, "0 0");
      gsap.set(smallIcon, { scale: 0.18, x: 12, y: -6 });
      path(iconGeometry, { class: "processing-block-icon" }, smallIcon);
      show(miniature, "instruction-control", undefined, {}, 0.45);

      const instruction = group({ "data-diagram": "instruction-fields" }, root);
      key(instruction, "instruction", {}, null, 0.7);
      key(instruction, "addressed-memory", { opacity: 0 }, null, 0, 0.5);
      const fields = [];
      const brace = (parent, width) => {
        const edge = width / 2;
        path(
          `M${-edge} 26 C${-edge} 18 -6 26 -3 18 Q0 11 3 18 C6 26 ${edge} 18 ${edge} 26`,
          { class: "instruction-brace" },
          parent,
        );
        path(
          `M${-edge} 58 C${-edge} 66 -6 58 -3 66 Q0 73 3 66 C6 58 ${edge} 66 ${edge} 58`,
          { class: "instruction-brace" },
          parent,
        );
      };
      for (const [i, token, role, bits, x, alternatives] of [
        [0, "ADD", "operation", "0001", 149, ["AND", "NOT"]],
        [1, "R0", "destination", "000", 230, ["R7", "R6"]],
        [2, "R0", "input 1", "000", 297, ["R7", "R6"]],
        [3, "R3", "input 2", "011", 413, ["R2", "R1"]],
      ]) {
        const field = group(
          { "data-instruction-field": i },
          instruction,
          "0 0",
        );
        const tint = mk(
          "rect",
          {
            x: -24,
            y: -20,
            width: 48,
            height: 29,
            rx: 4,
            class: "computer-glow",
          },
          field,
        );
        fields.push(tint);
        text(0, 0, token, { class: "bit instruction-token" }, field);
        const annotation = group(
          { "data-part": "instruction-encoding" },
          field,
        );
        alternatives.forEach((alternative, level) => {
          text(
            0,
            -36 - level * 30,
            alternative,
            {
              class: `bit instruction-alternative instruction-alternative-${level}`,
            },
            annotation,
          );
        });
        text(0, 46, bits, { class: "bit instruction-bits" }, annotation);
        brace(annotation, bits.length * 10 + 4);
        text(0, 96, role, { class: "instruction-field-name" }, annotation);
        key(field, "instruction", { x, y: 210 });
        key(field, "instruction-control", { x: 185 + i * 53, y: 32 });
        show(annotation, "instruction", "instruction-control", {}, 0.25);
      }
      const format = group({ "data-part": "instruction-format" }, instruction);
      text(347, 256, "0 00", { class: "bit instruction-bits" }, format);
      const formatBrace = group({}, format, "0 0");
      gsap.set(formatBrace, { x: 347, y: 210 });
      brace(formatBrace, 44);
      text(347, 306, "format", { class: "instruction-field-name" }, format);
      text(347, 320, "bits", { class: "instruction-field-name" }, format);
      show(format, "instruction", "instruction-control", {}, 0.25);
      const control = group({ "data-diagram": "simple-control" }, root);
      key(control, "instruction-control", {}, null, 0.6);
      key(control, "addressed-memory", { opacity: 0 }, null, 0, 0.5);
      path("M267 42 V58", { class: "control-wire" }, control);
      box(control, 157, 58, 221, 47, "Control unit");
      const controlRoutes = [
        "M264 105 V223.36 H256.3",
        "M238 105 V150 H232 V237.4 Q240 241.4 232 245.4 V297.98 H256.3",
        "M378 82 H425 V287.32 H393.33",
        "M157 94 H99 V416 H137.4 V385.72",
      ].map((d) => {
        path(d, { class: "control-wire" }, control);
        return path(d, { class: "control-wire control-active" }, control);
      });

      text(
        418,
        262,
        "ADD",
        { class: "tiny bit", "text-anchor": "end" },
        control,
      );
      text(184, 406, "write R0", { class: "tiny bit" }, control);
      const writeTint = mk(
        "rect",
        {
          x: 100,
          y: 390,
          width: 45,
          height: 18,
          rx: 3,
          class: "computer-glow",
        },
        control,
      );
      text(112, 403, "WE", { class: "tiny bit" }, control);
      const writeValue = text(131, 403, "0", { class: "tiny bit" }, control);
      const controlTime = { value: 0 };
      const controlDemo = gsap.timeline({ paused: true, repeat: -1 });
      controlDemo.to(controlTime, { value: 12, duration: 12, ease: "none" });
      demos.push(controlDemo);
      const instructionTime = { value: 0 };
      const instructionDemo = gsap.timeline({ paused: true, repeat: -1 });
      instructionDemo.to(instructionTime, {
        value: 8,
        duration: 8,
        ease: "none",
      });
      demos.push(instructionDemo);
      let instructionActive = false;
      let controlActive = false;
      afterRender.push(() => {
        const showFields = Math.abs(tl.time() - index("instruction")) <= hold;
        if (showFields && !instructionActive) instructionDemo.restart();
        if (!showFields) instructionDemo.pause(0);
        else if (matchMedia("(prefers-reduced-motion: reduce)").matches)
          instructionDemo.pause(0);
        else instructionDemo.play();
        instructionActive = showFields;
        const active =
          Math.abs(tl.time() - index("instruction-control")) <= hold;
        if (active && !controlActive) controlDemo.restart();
        if (!active) controlDemo.pause();
        else if (matchMedia("(prefers-reduced-motion: reduce)").matches)
          controlDemo.pause(9);
        else controlDemo.play();
        controlActive = active;
        const t = controlTime.value;
        const fade = Math.min(clamp(t * 3), clamp((12 - t) * 2));
        const we = t >= 7 && t < 8;
        setText(writeValue, we ? 1 : 0);
        writeTint.style.opacity = String(
          fade * Math.min(clamp((t - 6.9) * 10), clamp((8.1 - t) * 10)),
        );
        controlRoutes.forEach((node, i) => {
          const on =
            i < 2
              ? clamp((t - 0.8) * 3)
              : i === 2
                ? clamp((t - 1.6) * 3)
                : clamp((t - 2.2) * 3);
          node.style.opacity = String(fade * on);
        });
        fields.forEach((node, i) => {
          const now = active ? t : instructionTime.value;
          const order = active ? [1.6, 2.2, 0.8, 0.8][i] : 0.5 + i * 1.6;
          node.style.opacity = String(
            Math.min(clamp((now - order) * 3), clamp((order + 1.4 - now) * 3)),
          );
        });
      });
      afterRender.push(() => {
        const p = tl.time(),
          isAlu = p >= index("alu") - hold,
          controlled =
            p > index("instruction") + hold &&
            p < index("addressed-memory") - hold;
        const controlBlend = clamp(
          (p - index("instruction-control") + 1 - hold) / (1 - 2 * hold),
        );
        firstInput.base.style.opacity = secondInput.base.style.opacity = String(
          1 - controlBlend,
        );
        const aluBlend = clamp((p - index("alu") + 1 - hold) / (1 - 2 * hold));
        const inputAPath = `M235 179 H281 V190 H${305 + (15 * 25 * aluBlend) / 116}`;
        const inputBPath = `M235 270 H281 V250 H${305 + (15 * 85 * aluBlend) / 116}`;
        for (const node of [outputA.base, outputA.lit])
          node.setAttribute("d", inputAPath);
        for (const node of [outputB.base, outputB.lit])
          node.setAttribute("d", inputBPath);
        const activeScene =
          Math.abs(p - index("select-values")) <= hold
            ? "select-values"
            : Math.abs(p - index("alu")) <= hold
              ? "alu"
              : null;
        if (activeScene !== activeProcessingScene) {
          if (activeProcessingScene === "alu" && p > index("alu") + hold) {
            heldStart = processingDemo.totalTime();
            heldEnd = Math.max(heldStart, Math.floor(heldStart / 6) * 6 + 5);
          }
          processingDemo.pause(0);
          activeProcessingScene = activeScene;
        }
        if (
          activeScene &&
          !matchMedia("(prefers-reduced-motion: reduce)").matches
        )
          processingDemo.play();
        else if (!activeScene) processingDemo.pause(0);
        else processingDemo.pause(5);
        const held = p > index("alu") + hold;
        const t = controlled
          ? controlTime.value
          : held
            ? heldStart +
              (heldEnd - heldStart) * clamp((p - index("alu") - hold) / 0.4)
            : isAlu
              ? processingDemo.totalTime()
              : time.value;
        const step = controlled ? 1 : isAlu ? Math.floor(t / 6) : 0;
        const second = step > 0;
        const elapsed = controlled ? t : isAlu ? t % 6 : t >= 13 ? 0 : t;
        const reading = clamp((elapsed - (controlled ? 2.6 : 1)) / 1.2);
        const writing = isAlu
          ? clamp(
              (elapsed - (controlled ? 4.4 : 2.7)) / (controlled ? 1.8 : 1.5),
            )
          : 0;
        const readOpacity = controlled
          ? reading * clamp((11 - elapsed) * 2)
          : reading * (writing < 1 ? 1 : clamp(1 - (elapsed - 4.2) * 3));
        const left = second ? (9 + 2 * (step - 1)) % 65536 : 3,
          right = second ? 2 : 6,
          answer = (left + right) % 65536;
        const captured = controlled ? elapsed >= 7.4 : writing >= 1;
        const saved = !isAlu ? 0 : captured ? answer : second ? left : 0;
        processing.setAttribute(
          "data-write-enabled",
          controlled && elapsed >= 7 && elapsed < 8 ? "1" : "0",
        );
        const fade = controlled
          ? Math.min(clamp(elapsed * 3), clamp((12 - elapsed) * 2))
          : isAlu
            ? Math.min(clamp(elapsed * 2), clamp((6 - elapsed) * 2))
            : t >= 12
              ? t < 13
                ? clamp(13 - t)
                : clamp(t - 13)
              : 1;
        const resultProgress = clamp((elapsed - 2.2) / 0.8);
        adderResult.setAttribute(
          "y",
          278 + 58 * (1 - (1 - resultProgress) ** 3),
        );
        adderResult.style.opacity = String(fade * clamp(resultProgress * 4));
        transfers.style.opacity = String(fade);
        registerNumbers[0].style.opacity = controlled
          ? String(fade)
          : isAlu
            ? "1"
            : String(fade);
        setText(registerNumbers[0], saved);
        processing.setAttribute("data-saved-result", saved);
        processing.setAttribute("data-processing-step", String(step));
        setText(selectA, second ? "R0" : "R1");
        setText(selectB, second ? "R3" : "R2");
        setText(equation, isAlu ? `${left} + ${right} = ${answer}` : "");
        setText(outputValue, answer);
        setText(inputValues[0], left);
        setText(inputValues[1], right);
        inputValues.forEach((node) => {
          node.style.opacity = String(fade * readOpacity);
        });
        outputValue.style.opacity =
          isAlu && elapsed >= (controlled ? 3.8 : 2.2)
            ? String(fade * clamp((elapsed - (controlled ? 3.8 : 2.2)) * 3))
            : "0";
        const geometryA = second ? nextFirstInput.base : firstInput.base;
        const geometryB = second ? nextSecondInput.base : secondInput.base;
        firstTravel.setAttribute(
          "d",
          `${geometryA.getAttribute("d")} L${inputAPath.slice(1)}`,
        );
        secondTravel.setAttribute(
          "d",
          `${geometryB.getAttribute("d")} L${inputBPath.slice(1)}`,
        );
        const labelsFade = controlled
          ? fade * clamp((elapsed - 0.8) * 3)
          : fade;
        for (const node of [selectA, selectB, equation])
          node.style.opacity = String(labelsFade);
        for (let i = 0; i < selectedRows.length; i++) {
          selectedRows[i].style.opacity =
            (i === 0 && captured) ||
            i === (second ? 0 : 1) ||
            i === (second ? 3 : 2)
              ? String(fade * readOpacity)
              : "0";
        }
        for (const line of routes) line.style.opacity = "0";
        for (const line of [
          geometryA === firstInput.base ? firstInput.lit : nextFirstInput.lit,
          geometryB === secondInput.base
            ? secondInput.lit
            : nextSecondInput.lit,
          outputA.lit,
          outputB.lit,
        ])
          line.style.opacity = String(fade * readOpacity);
        returnLight.style.opacity = String(
          fade *
            clamp(writing * 4) *
            (controlled
              ? clamp((9 - elapsed) * 2)
              : writing < 1
                ? 1
                : clamp(1 - (elapsed - 4.2) * 3)),
        );
        move(flying[0], firstTravel, reading, left);
        move(flying[1], secondTravel, reading, right);
        move(flying[2], returnLight, writing, answer);
      });
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
    show(timing, "timing", "latch", {}, 0.65);
    playInScene("timing", timingDemo, "heat");

    if (!includeComputer) return { demos, timingDemo };

    const overview = group({ "data-diagram": "computer-overview" }, root);
    box(overview, 67, 61, 306, 190, "");
    text(220, 87, "CPU", { class: "caption" }, overview);
    box(overview, 88, 106, 112, 53, "calculate");
    box(overview, 240, 106, 112, 53, "registers");
    box(overview, 164, 189, 112, 40, "control");
    path(
      "M200 132 H240 M185 189 V176 H144 V159 M255 189 V176 H296 V159",
      { class: "muted" },
      overview,
    );
    path(
      "M204 251 V294 M236 251 V294 M29 175 H67 M373 175 H411",
      { class: "muted" },
      overview,
    );
    box(overview, 111, 294, 218, 69, "");
    text(220, 318, "memory", { class: "caption" }, overview);
    text(220, 344, "instructions + data", { class: "caption" }, overview);
    text(29, 162, "input", { class: "tiny" }, overview);
    text(404, 162, "output", { class: "tiny" }, overview);
    show(overview, "computer-overview", "memory-width", {}, 0.65);
    caption(
      "computer-overview",
      "the same circuits, directed by a stored program",
      "memory-width",
    );

    const memoryInterface = MEMORY_INTERFACE_SCENES.build({
      root,
      tl,
      hold,
      at,
      index,
      mk,
      group,
      path,
      text,
      key,
      show,
      draw,
      afterRender,
      controls,
    });
    demos.push(...memoryInterface.demos);

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
    key(registerBank, "addressed-memory", { opacity: 1 });
    key(registerBank, "program", { opacity: 1 });

    const alu = group({ "data-part": "alu" }, machine, "301 186");
    path("M246 148 H288 L301 161 L314 148 H362 L345 224 H263 Z", {}, alu);
    text(303, 185, "ALU", { class: "caption" }, alu);
    text(303, 205, "ADD", { class: "bit" }, alu);
    text(303, 242, "ADD · AND · NOT", { class: "tiny muted" }, alu);
    key(alu, "addressed-memory", { opacity: 1 });
    key(alu, "program", { opacity: 1 });
    const datapath = group({ "data-part": "datapath" }, machine);
    const readOne = lightPath("M166 147 H195 V170 H251", datapath);
    const readTwo = lightPath("M166 165 H207 V202 H258", datapath);
    const write = lightPath("M353 188 H393 V251 H184 V129 H166", datapath);
    text(185, 140, "16", { class: "tiny muted" }, datapath);
    path("M182 151 L187 143", { class: "muted thin" }, datapath);
    text(226, 200, "16", { class: "tiny muted" }, datapath);
    path("M221 207 L226 199", { class: "muted thin" }, datapath);
    show(datapath, "addressed-memory", undefined);
    key(datapath, "addressed-memory", { opacity: 1 });
    key(datapath, "program", { opacity: 1 });

    const memory = group({ "data-part": "memory" }, machine, "294 320");
    path("M220 273 H370 V361 H220 Z", {}, memory);
    const memoryTitle = text(295, 267, "memory", { class: "caption" }, memory);
    tl.to(
      memoryTitle,
      { attr: { y: 295 }, duration: DUR * 0.7, ease: EASE },
      at("program"),
    );
    const memoryTable = group({}, memory);
    text(244, 290, "ADDR", { class: "tiny muted bit" }, memoryTable);
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
      { scale: 1, x: 0, y: 0 },
      { scale: 0.7, x: 0, y: 0 },
    );
    key(memory, "program", { scale: 1, x: 0, y: 0 });
    tl.to(memoryTable, { opacity: 0, duration: DUR * 0.65 }, at("program"));
    tl.to(
      memoryLabel,
      { opacity: 1, duration: DUR * 0.65 },
      at("program") + DUR * 0.3,
    );
    caption("addressed-memory", "MAR selects · MDR transfers", "program", 430);
    const memoryDemo = gsap.timeline({ paused: true });
    memoryDemo.to(rowGlows[0], { opacity: 1, duration: 0.6 }, 0.3);
    memoryDemo.to(rowGlows[0], { opacity: 0, duration: 0.5 }, 2);
    memoryDemo.to(rowGlows[1], { opacity: 1, duration: 0.6 }, 2.5);
    playInScene("addressed-memory", memoryDemo, "alu");

    const memoryPorts = group(
      { "data-part": "memory-interface-registers" },
      machine,
    );
    box(memoryPorts, 48, 299, 80, 47, "MAR");
    box(memoryPorts, 137, 319, 65, 42, "MDR");
    path(
      "M128 324 H132 V300 H220 M202 338 H220",
      { class: "muted" },
      memoryPorts,
    );
    show(memoryPorts, "addressed-memory", undefined);
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
    const fetchAddress = lightPath(
      "M77 91 V102 H22 V324 H48 M128 324 H132 V300 H220",
      command,
    );
    const fetchInstruction = lightPath(
      "M220 338 H202 M137 338 H132 V365 H10 V28 H196 V55",
      command,
    );
    text(77, 292, "ADDR", { class: "tiny muted bit" }, command);
    text(286, 346, "0 · ADD R0, R1, R2", { class: "tiny" }, command);
    show(command, "program", undefined);
    caption(
      "program",
      "PC holds ADDR · IR holds the instruction",
      "control",
      430,
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
      430,
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
      435,
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
      "M4 18 H419 V267 H212 V373 H4 Z",
      { class: "muted thin" },
      computer,
    );
    text(396, 53, "CPU", { class: "caption" }, computer);
    box(computer, 48, 390, 60, 27, "input");
    box(computer, 128, 390, 64, 27, "output");
    path("M78 390 V373 M159 390 V373", { class: "muted" }, computer);
    show(computer, "computer", undefined);
    draw(cpuOutline, at("computer") + DUR * 0.1, DUR * 0.8);
    key(machine, "working-registers", { scale: 1, x: 0, y: 0 }, null, -1);
    key(machine, "addressed-memory", { scale: 0.7, x: 80, y: 70 });
    key(machine, "computer", { scale: 0.7, x: 80, y: 70 });
    caption(
      "computer",
      "a processor, memory and connections to the world",
      "end",
      435,
    );

    for (const [parent, layer] of signalLayers) parent.appendChild(layer);

    return { demos, timingDemo, computerDemo };
  };

  return { build };
})();
