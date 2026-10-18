import { gsap } from "gsap";
import { MEMORY_INTERFACE_SCENES } from "./memory-interface-scenes.js";
import { INSTRUCTION_CYCLE_SCENES } from "./instruction-cycle-scenes.js";
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
    let processingHandoff;
    const iconGeometry =
      "M70 160 H180 V290 H70 Z M70 192 H180 M70 224 H180 M70 256 H180 M180 190 H238 V208 H270 M180 258 H250 V248 H276 M270 180 H298 L310 195 L322 180 H365 L350 285 H285 Z M315 285 V322 H45 V176 H70";
    const box = (parent, x, y, w, h, label, attrs = {}) => {
      const g = group(attrs, parent, `${x + w / 2} ${y + h / 2}`);
      const outline = path(`M${x} ${y} H${x + w} V${y + h} H${x} Z`, {}, g);
      if (label) text(x + w / 2, y + h / 2 + 5, label, { class: "caption" }, g);
      return { g, outline };
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
      const bankTitle = text(
        88,
        110,
        "fast storage registers",
        { class: "caption" },
        bank,
      );
      key(bankTitle, "working-registers", { x: 0, y: 0 }, null, -1);
      key(bankTitle, "instruction-control", { x: 0, y: 253 });
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
            x: 14.61 + 285.39 * slide - 220 * grow,
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
          x: 300 * shrink - 285.39 * slide,
          y: 91 * (1 - scale) - 80.62 * stack,
        });
        gsap.set(root.querySelector('[data-part="memory-building-block"]'), {
          y: 10 + 58 * stack,
        });
        gsap.set(root.querySelector(".memory-block-name"), { y: 58 * stack });
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
      key(processing, "instruction", { scale: 0.18, x: 14.61, y: -6 });
      key(processing, "instruction-control", { scale: 0.82, x: 80, y: 102 });
      const miniName = text(
        51.6,
        61,
        "PU",
        { class: "processing-block-name" },
        root,
      );
      key(miniName, "instruction", {}, null, 0.9);
      key(miniName, "addressed-memory", { opacity: 0 }, null, 0, 0.5);
      const miniature = group(
        { "data-part": "processing-miniature" },
        root,
        "0 0",
      );
      mk(
        "rect",
        {
          x: 15.15,
          y: 10.38,
          width: 72.9,
          height: 56.88,
          rx: 2,
          class: "processing-block-tint",
        },
        miniature,
      );
      path(
        "M17.15 10.38 H86.05 Q88.05 10.38 88.05 12.38 V65.26 Q88.05 67.26 86.05 67.26 H17.15 Q15.15 67.26 15.15 65.26 V12.38 Q15.15 10.38 17.15 10.38 Z",
        { class: "processing-block-frame" },
        miniature,
      );
      const smallIcon = group({}, miniature, "0 0");
      gsap.set(smallIcon, { scale: 0.18, x: 14.61, y: -6 });
      path(iconGeometry, { class: "processing-block-icon" }, smallIcon);
      show(miniature, "instruction-control", "addressed-memory", {}, 0.45);
      processingHandoff = {
        processing,
        detail,
        silhouette,
        miniature,
        miniName,
      };

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
      text(
        264.5,
        12,
        "0001 000 000 0 00 011",
        { class: "bit control-encoding" },
        control,
      );
      path("M267 42 V58", { class: "control-wire" }, control);
      box(control, 157, 58, 221, 47, "Control unit");
      const controlRoutes = [
        "M264 105 V223.36 H256.3",
        "M238 105 V150 H232 V237.4 Q240 241.4 232 245.4 V297.98 H256.3",
        "M378 82 H425 V287.32 H393.33",
        "M180 105 V166 H152.16 V208.6",
      ].map((d) => {
        path(d, { class: "control-wire" }, control);
        return path(d, { class: "control-wire control-active" }, control);
      });

      text(
        418,
        280,
        "ADD",
        { class: "tiny bit", "text-anchor": "end" },
        control,
      );
      const controlTime = { value: 0 };
      const controlDemo = gsap.timeline({ paused: true, repeat: -1 });
      controlDemo.to(controlTime, { value: 12, duration: 12, ease: "none" });
      demos.push(controlDemo);
      let controlActive = false;
      afterRender.push(() => {
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
        controlRoutes.forEach((node, i) => {
          const on =
            i < 2
              ? clamp((t - 0.8) * 3)
              : i === 2
                ? clamp((t - 1.6) * 3)
                : Math.min(clamp((t - 6.9) * 10), clamp((8.1 - t) * 10));
          node.style.opacity = String(fade * on);
        });
        fields.forEach((node, i) => {
          const [start, end] = [
            [3.8, 4.8],
            [7, 8],
            [0.8, 4],
            [0.8, 4],
          ][i];
          node.style.opacity = active
            ? String(
                fade * Math.min(clamp((t - start) * 10), clamp((end - t) * 10)),
              )
            : "0";
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
    const overviewBlock = (x, y, width, height, className) =>
      mk("rect", { x, y, width, height, rx: 4, class: className }, overview);
    const overviewLink = (d) => path(d, { class: "io-link" }, overview);

    overviewBlock(100, 144, 240, 126, "fetch-cpu-frame");
    text(124, 163, "CPU", { class: "caption" }, overview);

    overviewBlock(132, 179, 72.9, 56.88, "processing-block-tint");
    overviewBlock(132, 179, 72.9, 56.88, "processing-block-frame");
    const overviewProcessingIcon = group({}, overview, "0 0");
    gsap.set(overviewProcessingIcon, { scale: 0.18, x: 131.46, y: 162.62 });
    path(
      iconGeometry,
      { class: "processing-block-icon" },
      overviewProcessingIcon,
    );
    text(168.45, 229.62, "PU", { class: "processing-block-name" }, overview);

    overviewBlock(235.1, 179, 72.9, 56.88, "fetch-control-frame");
    path(
      "M247 193 H259 V204 H247 Z M282 193 H294 V204 H282 Z M259 198 H282 M253 204 V211 H288 V204",
      { class: "thin muted" },
      overview,
    );
    text(271.55, 229.62, "CU", { class: "control-block-name" }, overview);
    overviewLink(
      "M204.9 207 H235.1 M209.9 203 L204.9 207 L209.9 211 M230.1 203 L235.1 207 L230.1 211",
    );

    overviewBlock(182.56, 318, 74.88, 62.64, "memory-block-tint");
    overviewBlock(182.56, 318, 74.88, 62.64, "memory-block-frame");
    const overviewMemoryIcon = group({}, overview, "0 0");
    gsap.set(overviewMemoryIcon, { scale: 0.18, x: 180.4, y: 309.36 });
    path(
      "M70 90 H370 V270 H70 Z M120 90 V270 M70 135 H370 M70 180 H370 M70 225 H370",
      { class: "memory-block-icon" },
      overviewMemoryIcon,
    );
    text(220, 372.36, "MEMORY", { class: "memory-block-name" }, overview);
    overviewLink(
      "M220 270 V318 M216 275 L220 270 L224 275 M216 313 L220 318 L224 313",
    );

    overviewBlock(192, 80, 56, 26, "io-block-frame");
    text(220, 98, "I/O", { class: "io-block-name" }, overview);
    overviewLink(
      "M220 106 V144 M216 111 L220 106 L224 111 M216 139 L220 144 L224 139",
    );
    show(overview, "computer-overview", "memory-width", {}, 0.65);

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

    const io = group({ "data-part": "io-building-block" }, root, "0 0");
    const ioContents = group({}, io);
    mk(
      "rect",
      { x: -28, y: 0, width: 56, height: 26, rx: 3, class: "io-block-frame" },
      ioContents,
    );
    text(0, 18, "I/O", { class: "io-block-name caption" }, ioContents);
    key(io, "processing-block", { x: 378, y: 10 }, null, 0.65);
    key(io, "instruction", { x: 51.6, y: 149 });
    key(io, "addressed-memory", { x: 52, y: 78 });
    key(io, "computer", { x: 220, y: 12 });
    const ioTransitions = [
      "processing-block",
      "instruction",
      "instruction-control",
      "instruction-fetch",
      "control",
    ].map(index);
    afterRender.push(() => {
      const p = tl.time();
      const start = Math.floor(p);
      const transition = Math.max(
        0,
        Math.min(1, (p - start - hold) / (1 - 2 * hold)),
      );
      const opacity = ioTransitions.includes(start)
        ? Math.max(0, 1 - transition / 0.12) +
          Math.max(0, (transition - 0.88) / 0.12)
        : 1;
      gsap.set(ioContents, { opacity });
    });
    const ioLink = group({ "data-part": "io-cpu-link" }, root);
    path(
      "M220 38 V57 M216 42 L220 38 L224 42 M216 53 L220 57 L224 53",
      { class: "io-link" },
      ioLink,
    );
    key(ioLink, "computer", {}, null, 0.85);

    const instructionCycle = INSTRUCTION_CYCLE_SCENES.build({
      root,
      tl,
      hold,
      index,
      group,
      mk,
      path,
      text,
      key,
      show,
      afterRender,
    });
    demos.push(...instructionCycle.demos);
    const memoryModule = root.querySelector(
      '[data-part="memory-building-block"]',
    );
    const memoryFrame = root.querySelector('[data-part="memory-green-frame"]');
    const memoryName = root.querySelector(".memory-block-name");
    const memorySilhouette = root.querySelector(
      '[data-part="memory-block-silhouette"]',
    );
    key(memorySilhouette, "addressed-memory", { opacity: 0 });
    const easeHandoff = gsap.parseEase("power2.inOut");
    afterRender.push(() => {
      const p = tl.time();
      if (
        p < index("instruction-control") - hold ||
        p > index("addressed-memory") + hold
      )
        return;
      const t = Math.max(
        0,
        Math.min(1, (p - index("instruction-control") - hold) / (1 - 2 * hold)),
      );
      const clamp = (n) => Math.max(0, Math.min(1, n));
      const shrink = easeHandoff(clamp(t / 0.26));
      const slide = easeHandoff(clamp((t - 0.26) / 0.22));
      const scale = 0.82 + (0.18 - 0.82) * shrink;
      const swapPu = easeHandoff(clamp((t - 0.44) / 0.08));
      const growMemory = easeHandoff(clamp((t - 0.5) / 0.5));
      const swapMemory = easeHandoff(clamp((t - 0.78) / 0.22));
      gsap.set(processingHandoff.processing, {
        scale,
        x: 248.51 + (51.6 - 248.51) * slide - 205.5 * scale,
        y: 306.18 + (38.82 - 306.18) * slide - 249 * scale,
        opacity: 1 - swapPu,
      });
      gsap.set(processingHandoff.detail, { opacity: 1 - shrink });
      gsap.set(processingHandoff.silhouette, { opacity: shrink });
      gsap.set(processingHandoff.miniature, { opacity: 1 - clamp(t / 0.12) });
      gsap.set(processingHandoff.miniName, { opacity: 1 - clamp(t / 0.12) });
      const frameScaleY = 348 / 428 + (80 / 428) * growMemory;
      const frameY = (48 - (8 * 348) / 428) * (1 - growMemory);
      gsap.set(memoryFrame, { scaleY: frameScaleY, y: frameY });
      const memoryScaleX = 0.18 + (314 / 416 - 0.18) * growMemory;
      const memoryScaleY = 0.18 + (138 / 428 - 0.18) * growMemory;
      const memoryX = 12 + (106 - (12 * 314) / 416 - 12) * growMemory;
      const memoryY = 68 + (256 - (8 * 138) / 428 - 68) * growMemory;
      gsap.set(memoryModule, {
        scaleX: memoryScaleX,
        scaleY: memoryScaleY,
        x: memoryX,
        y: memoryY,
        opacity: 1 - swapMemory,
      });
      const tableScaleX = (416 * memoryScaleX) / 314;
      const tableScaleY = (428 * frameScaleY * memoryScaleY) / 138;
      gsap.set(instructionCycle.handoff.memory, {
        scaleX: tableScaleX,
        scaleY: tableScaleY,
        x: memoryX + 12 * memoryScaleX - 106 * tableScaleX,
        y:
          memoryY +
          (8 * frameScaleY + frameY) * memoryScaleY -
          296 * tableScaleY,
        opacity: swapMemory,
      });
      gsap.set(memorySilhouette, { opacity: 1 - growMemory });
      gsap.set(memoryName, { opacity: 1 - clamp((t - 0.5) / 0.16) });
      gsap.set(instructionCycle.handoff.diagram, { opacity: 1 });
      gsap.set(instructionCycle.handoff.signals, { opacity: t < 1 ? 0 : 1 });
      gsap.set(instructionCycle.handoff.pu, { opacity: swapPu });
      gsap.set(instructionCycle.handoff.puName, { opacity: swapPu });
      gsap.set(instructionCycle.handoff.programNames, { opacity: swapMemory });
    });

    return { demos, timingDemo };
  };

  return { build };
})();
