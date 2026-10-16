import { gsap } from "gsap";
import {
  createMemoryDemo,
  createAdderMemoryDemo,
  ADDER_MEMORY_DURATION,
  MEMORY_TRANSFER_DURATION,
  REGISTER_MODEL,
  dataChangePulse,
} from "./memory-model.js";
import { mountMemoryControls } from "./memory-controls.js";
export const MEMORY_SCENES = (() => {
  const build = ({
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
    afterRender,
  }) => {
    const demos = [];
    const xs = [142, 216, 290, 364];
    const ys = [176, 224, 272, 320];
    const label = (parent, x, y, value, attrs = {}) =>
      text(x, y, value, { class: "caption", ...attrs }, parent);
    const portLabel = (parent, x, y, value, attrs = {}) =>
      text(x, y, value, { class: "memory-label tiny", ...attrs }, parent);
    const digit = (parent, x, y, value, attrs = {}) =>
      text(x, y, value, { class: "bit", ...attrs }, parent);
    const wire = (parent, d) => path(d, {}, parent);
    const junction = (parent, x, y) =>
      mk("circle", { cx: x, cy: y, r: 1.4, class: "dot" }, parent);
    const signal = (parent, d) =>
      path(d, { class: "memory-signal", opacity: 0 }, parent);
    const box = (parent, x, y, width, height) =>
      mk("rect", { x, y, width, height, rx: 2, class: "memory-box" }, parent);
    const bits = (number, width = 4) => number.toString(2).padStart(width, "0");
    const setText = (element, value) => {
      if (element.textContent !== String(value))
        element.textContent = String(value);
    };
    const andGate = (parent, x, y) =>
      path(
        `M${x} ${y - 7} H${x + 7} A7 7 0 0 1 ${x + 7} ${y + 7} H${x} Z`,
        { class: "memory-box" },
        parent,
      );
    const array = group({ "data-diagram": "memory-array" }, root, "220 250");
    key(array, "register", { scale: 1, y: 64 });
    key(array, "memory-two", { scale: 1, y: 24 });
    key(array, "memory-array", { scale: 1, y: 0 });
    key(array, "stored-answer", { scale: 0.82, y: 32 });
    key(
      array,
      "memory-buses",
      { scale: 0.42, y: 17, opacity: 0 },
      null,
      0,
      0.72,
    );
    const rowDigits = [],
      rowAddresses = [],
      readLights = [],
      writeLights = [],
      selectLights = [],
      writeInputLights = [];
    const signalLayer = group({ "data-memory-signals": "" }, array);
    const readSignals = group({}, signalLayer);
    show(readSignals, "memory-two", "memory-buses");
    const writeSignals = group({}, signalLayer);
    show(writeSignals, "memory-two", "memory-buses");
    const readGates = group({}, array);
    show(readGates, "memory-two", "memory-buses");
    const writeGates = group({}, array);
    show(writeGates, "memory-two", "memory-buses");
    const writeFeed = wire(writeGates, "M78 132 V268");
    key(writeFeed, "memory-two", { attr: { d: "M78 132 V268" } });
    key(writeFeed, "memory-array", { attr: { d: "M78 132 V364" } });
    const writeFeedLight = signal(writeSignals, writeFeed.getAttribute("d"));
    portLabel(writeGates, 78, 106, "WE");
    const weValue = digit(writeGates, 78, 125, "0");
    const decoder = group({}, array);
    show(decoder, "memory-two", "memory-buses");
    const decoderOutline = box(decoder, 28, 180, 36, 98);
    key(decoderOutline, "memory-two", { attr: { height: 98 } });
    key(decoderOutline, "memory-array", { attr: { height: 194 } });
    const decoderLabel = label(decoder, 46, 304, "Decoder");
    key(decoderLabel, "memory-two", { attr: { y: 304 } });
    key(decoderLabel, "memory-array", { attr: { y: 400 } });
    const firstAddress = wire(decoder, "M14 130 V253");
    key(firstAddress, "memory-two", { attr: { d: "M14 130 V253" } });
    key(firstAddress, "memory-array", { attr: { d: "M14 130 V345" } });
    const secondAddress = wire(decoder, "M22 130 V353");
    key(secondAddress, "memory-array", {});
    const addressLabel = portLabel(decoder, 14, 106, "ADDR");
    key(addressLabel, "memory-two", { attr: { x: 14 } });
    key(addressLabel, "memory-array", { attr: { x: 18 } });
    const addressValues = [14, 22].map((x) => digit(decoder, x, 125, "0"));
    key(addressValues[1], "memory-array", {});
    const inputDeck = group({}, array);
    show(inputDeck, "register", "memory-buses");
    const inputFlashes = [];
    const inputDigits = xs.map((x, i) => {
      portLabel(inputDeck, x - 23, 106, `D${3 - i}`);
      inputFlashes.push(
        mk(
          "rect",
          {
            x: x - 32,
            y: 109,
            width: 18,
            height: 21,
            rx: 4,
            class: "data-change-highlight",
          },
          inputDeck,
        ),
      );
      return digit(inputDeck, x - 23, 125, "0011"[i]);
    });
    inputDigits.forEach((element, c) => {
      key(element, "register", { attr: { x: xs[c] - 23 } });
      key(element, "stored-answer", { attr: { x: xs[c] - 11 } });
    });
    const inputNames = Array.from(inputDeck.querySelectorAll("text.tiny"));
    inputNames.forEach((element) => {
      key(element, "register", {});
      key(element, "stored-answer", { opacity: 0 });
    });
    const dataWires = group({}, array);
    show(dataWires, "register", "memory-buses");
    xs.forEach((x) => {
      const dataWire = wire(dataWires, `M${x - 23} 132 V184 H${x - 16}`);
      key(dataWire, "register", {});
      key(dataWire, "memory-two", {
        attr: { d: `M${x - 23} 132 V232 H${x - 16}` },
      });
      key(dataWire, "memory-array", {
        attr: { d: `M${x - 23} 132 V328 H${x - 16}` },
      });
    });
    ys.forEach((y, r) => {
      const row = group({ "data-memory-row": r }, array, `220 ${y + 12}`);
      if (r === 0) key(row, "register", {});
      else
        key(
          row,
          r === 1 ? "memory-two" : "memory-array",
          { y: 0 },
          { y: -48, opacity: 0 },
          0.25 + (r === 3 ? 0.15 : 0),
        );
      const rowAddress = portLabel(row, 46, y + 15, `ADDR ${bits(r, 2)}`, {
        class: "memory-label memory-row-address",
      });
      rowAddresses.push(rowAddress);
      show(rowAddress, r < 2 ? "memory-two" : "memory-array", "memory-buses");
      const readRow = group({}, readGates);
      const writeRow = group({}, writeGates);
      const decodeRow = group({}, decoder);
      const readSignalRow = group({}, readSignals);
      const writeSignalRow = group({}, writeSignals);
      for (const part of [
        readRow,
        writeRow,
        decodeRow,
        readSignalRow,
        writeSignalRow,
      ])
        key(part, r < 2 ? "memory-two" : "memory-array", {});
      const fourDecode = group({}, decodeRow);
      key(fourDecode, "memory-array", {});
      andGate(fourDecode, 39, y + 29);
      [0, 1].forEach((bit) => {
        const yy = y + 25 + bit * 8;
        wire(
          fourDecode,
          `M${bit === 0 ? 14 : 22} ${yy} H${bits(r, 2)[bit] === "0" ? 33 : 39}`,
        );
        if (bits(r, 2)[bit] === "0")
          mk(
            "circle",
            { cx: 36, cy: yy, r: 3, class: "memory-box" },
            fourDecode,
          );
      });
      wire(fourDecode, `M53 ${y + 29} H64`);
      if (r < 2) {
        const twoDecode = group({}, decodeRow);
        show(twoDecode, "memory-two", "memory-array");
        if (r === 0) {
          wire(twoDecode, `M14 ${y + 29} H38`);
          path(
            `M38 ${y + 22} L49 ${y + 29} L38 ${y + 36} Z`,
            { class: "memory-box" },
            twoDecode,
          );
          mk(
            "circle",
            { cx: 52, cy: y + 29, r: 3, class: "memory-box" },
            twoDecode,
          );
          wire(twoDecode, `M55 ${y + 29} H64`);
        } else wire(twoDecode, `M14 ${y + 29} H64`);
      }
      const select = `M64 ${y + 29} H${xs[3] + 18}`;
      wire(readRow, select);
      junction(readRow, 88, y + 29);
      junction(writeRow, 78, y + 44);
      const selectLight = signal(readSignalRow, select);
      key(selectLight, "memory-array", {
        attr: { d: `M53 ${y + 29} H${xs[3] + 18}` },
      });
      if (r < 2)
        key(selectLight, "memory-two", {
          attr: { d: `M${r === 0 ? 55 : 14} ${y + 29} H${xs[3] + 18}` },
        });
      selectLights.push(selectLight);
      const writeInput = signal(writeSignalRow, `M78 ${y + 44} H92`);
      writeInputLights.push(writeInput);
      const write = `M88 ${y + 29} V${y + 36} H92 M78 ${y + 44} H92`;
      wire(writeRow, write);
      andGate(writeRow, 92, y + 40);
      const writeOut = `M106 ${y + 40} H${xs[3] - 5}`;
      wire(writeRow, writeOut);
      const writeRoute = group({}, writeSignalRow);
      signal(writeRoute, writeOut).setAttribute("opacity", "1");
      writeLights.push(writeRoute);
      const readRoute = group({}, readSignalRow);
      signal(readRoute, `M88 ${y + 29} V${y + 36} H92`).setAttribute(
        "opacity",
        "1",
      );
      readLights.push(readRoute);
      rowDigits.push(
        xs.map((x, c) => {
          const cell = group({}, row, `${x} ${y + 12}`);
          if (r === 0)
            key(
              cell,
              "register",
              { x: 0, scale: 1 },
              { x: xs[0] - x, scale: 0.92, opacity: 0 },
              c === 0 ? 0.25 : 0.38 + c * 0.08,
            );
          box(cell, x - 16, y, 32, 24);
          label(cell, x - 11, y + 11, "D", { class: "memory-port" });
          label(cell, x + 11, y + 11, "Q", { class: "memory-port" });
          label(cell, x - 5, y + 22, "WE", { class: "memory-port" });
          const value = digit(cell, x + 2, y + 17, bits([3, 6, 0, 0][r])[c], {
            "data-memory-bit": `${r}-${c}`,
          });
          if (r === 0) key(value, "memory-two", {});
          wire(cell, `M${x - 23} ${y + 8} H${x - 16}`);
          const dataJunction = junction(cell, x - 23, y + 8);
          if (r === 0) key(dataJunction, "memory-two", {});
          if (c < xs.length - 1) {
            junction(readRow, x + 18, y + 29);
            junction(writeRow, x - 5, y + 40);
          }
          const enable = wire(cell, `M${x - 5} ${y + 24} V${y + 40}`);
          const q = `M${x + 16} ${y + 8} H${x + 20}`;
          wire(cell, q);
          if (r === 0) show(enable, "memory-two", "memory-buses");
          andGate(readRow, x + 20, y + 12);
          const readSelect = `M${x + 18} ${y + 29} V${y + 16} H${x + 20}`;
          wire(readRow, readSelect);
          signal(readRoute, readSelect).setAttribute("opacity", "1");
          const track = x + 47 - r * 4;
          const inputY = (top, offset) => {
            const position = (offset - 29) / 24;
            return (top + 14 * position * (1 - position)).toFixed(2);
          };
          const route = `M${x + 34} ${y + 12} H${track} V${inputY(386, track - x)}`;
          const readWire = wire(readRow, route);
          const readHighlight = signal(readRoute, q + route);
          readHighlight.setAttribute("opacity", "1");
          if (r < 2) {
            const shortTrack = x + (r === 0 ? 47 : 35);
            const shortRoute = `M${x + 34} ${y + 12} H${shortTrack} V${inputY(296, shortTrack - x)}`;
            key(readWire, "memory-two", { attr: { d: shortRoute } });
            key(readWire, "memory-array", { attr: { d: route } });
            key(readHighlight, "memory-two", { attr: { d: q + shortRoute } });
            key(readHighlight, "memory-array", { attr: { d: q + route } });
          }
          signal(writeRoute, `M${x - 5} ${y + 40} V${y + 24}`).setAttribute(
            "opacity",
            "1",
          );
          signal(
            writeRoute,
            `M${x - 23} 132 V${y + 8} H${x - 16}`,
          ).setAttribute("opacity", "1");
          return value;
        }),
      );
    });
    const outputDeck = group({}, array);
    key(outputDeck, "memory-two", { y: -90 });
    key(outputDeck, "memory-array", { y: 0 });
    key(outputDeck, "memory-buses", { y: 0, opacity: 0 });
    const outputDigits = xs.map((x, c) => {
      wire(
        outputDeck,
        `M${x + 29} 386 Q${x + 41} 393 ${x + 53} 386 Q${x + 51} 402 ${x + 41} 410 Q${x + 31} 402 ${x + 29} 386`,
      );
      wire(outputDeck, `M${x + 41} 410 V419`);
      portLabel(outputDeck, x + 35, 435, `Q${3 - c}`, {
        "text-anchor": "end",
      });
      return digit(outputDeck, x + 47, 435, "0011"[c]);
    });
    const outputLights = xs.map((x) =>
      signal(outputDeck, `M${x + 41} 410 V419`),
    );
    const registerOnly = group({ "data-diagram": "register" }, array);
    key(registerOnly, "register", {}, null, 0.65);
    key(registerOnly, "memory-two", { opacity: 0 }, null, 0, 0.35);
    label(registerOnly, 220, 72, "4-bit register");
    const enablePath =
      `M80 264 H${xs[3] - 5}` + xs.map((x) => ` M${x - 5} 264 V200`).join("");
    wire(registerOnly, enablePath);
    const registerEnableLight = signal(registerOnly, enablePath);
    registerEnableLight.classList.add("register-enable");
    portLabel(registerOnly, 62, 269, "WE");
    const registerWE = digit(registerOnly, 62, 287, "0");
    const registerOutputs = xs.map((x, c) => {
      wire(registerOnly, `M${x + 16} 184 H${x + 32} V228`);
      return digit(registerOnly, x + 32, 247, "0011"[c], {
        "data-register-output": c,
      });
    });
    const registerCopies = xs.map((x, c) =>
      digit(registerOnly, x - 23, 125, "0", {
        class: "bit register-copy",
        opacity: 0,
        "data-register-copy": c,
      }),
    );
    registerOnly.appendChild(registerEnableLight);
    array.appendChild(signalLayer);
    const registerClock = gsap.timeline({ paused: true, repeat: -1 });
    registerClock.to({}, { duration: REGISTER_MODEL.PERIOD });
    demos.push(registerClock);
    const copyPosition = (x, progress) => [
      x - 23 + 55 * (1 - (1 - progress) ** 3),
      125 + 122 * progress,
    ];
    const arrayTitle = label(root, 220, 46, "2 locations × 4 bits");
    show(arrayTitle, "memory-two", "memory-array");
    const biggerTitle = label(root, 220, 46, "4 locations × 4 bits");
    show(biggerTitle, "memory-array", "stored-answer");
    const adder = group({ "data-diagram": "memory-adder" }, root);
    show(adder, "stored-answer", "memory-buses");
    digit(adder, 220, 38, "0011 + 0110 = 1001");
    label(adder, 220, 53, "4-bit adder");
    const adderLinks = group({}, root);
    key(adderLinks, "stored-answer", {});
    key(adderLinks, "memory-buses", { opacity: 0 }, null, 0, 0.95);
    const adderLights = [];
    xs.forEach((x, c) => {
      const centre = 220 + (x - 23 - 220) * 0.82;
      box(adder, centre - 21, 90, 42, 30);
      label(adder, centre, 110, "+");
      wire(adder, `M${centre - 8} 80 V90 M${centre + 8} 80 V90`);
      digit(adder, centre - 8, 76, "0011"[c], { class: "tiny bit" });
      digit(adder, centre + 8, 76, "0110"[c], { class: "tiny bit" });
      if (c < 3) {
        const next = 220 + (xs[c + 1] - 23 - 220) * 0.82;
        wire(adder, `M${next - 21} 105 H${centre + 21}`);
      }
      const d = `M${centre} 120 V${250 + (132 - 250) * 0.82 + 32}`;
      const link = wire(adderLinks, d);
      key(link, "stored-answer", { attr: { d } });
      key(link, "memory-buses", {
        attr: { d: "M220 129 V219" },
      });
      const lit = signal(adderLinks, d);
      key(lit, "stored-answer", { attr: { d } });
      key(lit, "memory-buses", { attr: { d: "M220 129 V219" } });
      adderLights.push(lit);
    });
    const compact = group({ "data-diagram": "memory-buses" }, root);
    key(
      compact,
      "memory-buses",
      { scale: 1 },
      { opacity: 0, scale: 1.12 },
      0.28,
    );
    key(compact, "timing", { opacity: 0 }, null, 0, 0.6);
    box(compact, 134, 75, 172, 54);
    label(compact, 220, 106, "4-bit adder");
    path("M171 53 V75 M269 53 V75", { class: "memory-bus" }, compact);
    wire(compact, "M166 69 L176 59 M264 69 L274 59");
    portLabel(compact, 185, 67, "4");
    portLabel(compact, 283, 67, "4");
    digit(compact, 171, 46, "0011");
    digit(compact, 269, 46, "0110");
    box(compact, 117, 219, 254, 123);
    portLabel(compact, 220, 237, "D");
    portLabel(compact, 244, 333, "Q");
    label(compact, 244, 273, "Memory");
    label(compact, 244, 296, "4 locations × 4 bits");
    const bus = (d, slash, x, y, width) => {
      path(d, { class: "memory-bus" }, compact);
      wire(compact, slash);
      portLabel(compact, x, y, String(width));
    };
    bus("M220 129 V219", "M214 165 L226 155", 238, 164, 4);
    digit(compact, 254, 195, "1001");
    bus("M59 248 H117", "M80 254 L90 242", 86, 231, 2);
    portLabel(compact, 49, 230, "ADDR");
    const compactAddress = digit(compact, 49, 252, "00");
    wire(compact, "M59 302 H117");
    portLabel(compact, 49, 284, "WE");
    const compactWE = digit(compact, 49, 306, "0");
    bus("M244 342 V395", "M238 372 L250 362", 263, 371, 4);
    const compactOutput = digit(compact, 244, 417, "0011");
    const dynamic = { selected: [0, 0, 0, 0], writing: [0, 0, 0, 0] };
    const contexts = new Map();
    const contextFor = (scene, words) => {
      if (!contexts.has(scene)) {
        const adder = scene === "stored-answer";
        const model = adder
          ? createAdderMemoryDemo(words)
          : createMemoryDemo(words);
        const clock = gsap.timeline({ paused: true });
        clock.to(
          {},
          {
            duration: adder ? ADDER_MEMORY_DURATION : MEMORY_TRANSFER_DURATION,
          },
        );
        demos.push(clock);
        contexts.set(scene, { model, clock, visited: false });
      }
      return contexts.get(scene);
    };
    contextFor("memory-two", [3, 6]);
    contextFor("memory-array", [3, 6, 0, 0]);
    contextFor("stored-answer", [3, 6, 0, 0]);
    const controls = mountMemoryControls(
      root.closest(".stage"),
      (scene, action, address) => {
        const context = contexts.get(scene);
        if (!context || context.model.frame(context.clock.time()).busy) return;

        context.model.choose(action, address);
        context.clock.restart();
      },
    );
    const transfers = group({ "data-memory-transfers": "" }, array);
    const transferDigits = xs.map((x, c) =>
      digit(transfers, x - 23, 125, "0", {
        class: "bit register-copy",
        opacity: 0,
        "data-memory-copy": c,
      }),
    );
    const phaseLabels = [];
    for (const scene of ["memory-two", "memory-array", "stored-answer"]) {
      const phase = label(
        root,
        220,
        scene === "stored-answer" ? 17 : 66,
        "Read ADDR 0",
        { class: "memory-label" },
      );
      show(
        phase,
        scene,
        scene === "memory-two"
          ? "memory-array"
          : scene === "memory-array"
            ? "stored-answer"
            : "memory-buses",
      );
      phaseLabels.push(phase);
    }
    let lastTime = 0;
    let registerWord = 3;
    let previousContext = null;
    let adderActive = false;
    afterRender.push(() => {
      const progress = tl.time();
      const active = [
        "memory-two",
        "memory-array",
        "stored-answer",
        "memory-buses",
      ].find((scene) => Math.abs(progress - index(scene)) <= hold);
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const registerActive = Math.abs(progress - index("register")) <= hold;
      if (registerActive && !reduced) registerClock.play();
      else registerClock.pause();
      if (
        progress < index("register") - hold ||
        progress > index("memory-two") - hold
      )
        registerClock.pause(0);
      const registerState = REGISTER_MODEL.frame(
        reduced ? 0 : registerClock.totalTime(),
      );
      registerOnly.setAttribute("data-we", String(registerState.we));
      registerOnly.setAttribute("data-input", bits(registerState.input));
      registerOnly.setAttribute("data-output", bits(registerState.output));
      registerOnly.setAttribute(
        "data-loop-time",
        registerState.time.toFixed(3),
      );
      const change = registerState.inputChange;
      inputFlashes.forEach((element, c) => {
        const changed = change && bits(change.from)[c] !== bits(change.to)[c];
        element.style.opacity =
          registerActive && changed ? dataChangePulse(change.age) : 0;
      });
      setText(registerWE, registerState.we);
      registerEnableLight.style.opacity = registerState.we;
      registerCopies.forEach((element, c) => {
        const transfer = registerState.transfer;
        const changed =
          transfer && bits(transfer.from)[c] !== bits(transfer.to)[c];
        const p = transfer?.progress ?? 0;
        const opacity = changed ? Math.min(1, p / 0.12, (1 - p) / 0.12) : 0;
        element.style.opacity = opacity;
        registerOutputs[c].style.opacity = changed
          ? 1 - Math.min(1, Math.max(0, (p - 0.78) / 0.22))
          : 1;
        setText(registerOutputs[c], bits(registerState.output)[c]);
        if (changed) {
          setText(element, bits(transfer.to)[c]);
          const [x, y] = copyPosition(xs[c], p);
          element.setAttribute("x", x);
          element.setAttribute("y", y);
        }
      });
      const rows = progress < index("memory-array") - hold ? 2 : 4;
      const register = progress < index("memory-two") - hold;
      if (register) registerWord = registerState.output;
      const scene =
        progress < index("memory-array") - hold
          ? "memory-two"
          : progress < index("stored-answer") - hold
            ? "memory-array"
            : "stored-answer";
      const seed = [registerWord, 6, 0, 0];
      const earlier =
        scene === "memory-array"
          ? contexts.get("memory-two")
          : scene === "stored-answer"
            ? contexts.get("memory-array")
            : null;
      const context = contexts.get(scene);
      if (previousContext && previousContext !== context)
        previousContext.model.frame(Infinity);
      const previousWords = earlier?.model.frame(earlier.clock.time()).words;
      if (
        active &&
        (!context.visited || (active === "stored-answer" && !adderActive))
      ) {
        const adder = scene === "stored-answer";
        const words = (previousWords ?? seed).slice(
          0,
          scene === "memory-two" ? 2 : 4,
        );
        while (words.length < (scene === "memory-two" ? 2 : 4)) words.push(0);
        context.model = adder
          ? createAdderMemoryDemo(words)
          : createMemoryDemo(words);
        context.clock.pause(0);
        context.visited = true;
      }
      adderActive = active === "stored-answer";
      if (active === "memory-buses") context.clock.pause(ADDER_MEMORY_DURATION);
      for (const other of contexts.values())
        if (other !== context) other.clock.pause();
      if (active && active !== "memory-buses" && !reduced) context.clock.play();
      else context.clock.pause();
      const elapsed = reduced ? context.clock.duration() : context.clock.time();
      const state = context.model.frame(elapsed);
      const delta = Math.min(0.05, Math.max(0, elapsed - lastTime));
      const blend =
        reduced || previousContext !== context
          ? 1
          : Math.min(1, Math.max(delta, 1 / 60) * 9);
      lastTime = elapsed;
      previousContext = context;
      const controlScene =
        Math.abs(progress - index("memory-two")) < 0.5
          ? "memory-two"
          : Math.abs(progress - index("memory-array")) < 0.5
            ? "memory-array"
            : null;
      const controlOpacity = controlScene
        ? Math.max(
            0,
            Math.min(
              1,
              (0.5 - Math.abs(progress - index(controlScene))) / (0.5 - hold),
            ),
          )
        : 0;
      controls.update(controlScene, state, controlOpacity);
      transfers.style.opacity =
        active === "memory-two" ||
        active === "memory-array" ||
        active === "stored-answer"
          ? 1
          : 0;
      transferDigits.forEach((element, c) => {
        const transfer = state.transfer;
        const p = transfer?.progress ?? 0;
        element.style.opacity = transfer
          ? Math.min(1, p / 0.12, (1 - p) / 0.12)
          : 0;
        if (!transfer) return;

        setText(element, bits(transfer.value)[c]);
        const x = xs[c];
        const y = ys[state.address];
        if (transfer.kind === "Write") {
          const travel = 1 - (1 - p) ** 2;
          const startX = x - (scene === "stored-answer" ? 11 : 23);
          element.setAttribute("x", startX + (x + 2 - startX) * travel);
          element.setAttribute("y", 125 + (y + 17 - 125) * p);
        } else {
          const travel = p * p * (3 - 2 * p);
          element.setAttribute("x", x + 2 + 45 * travel);
          element.setAttribute(
            "y",
            y + 17 + ((rows === 2 ? 345 : 435) - y - 17) * p,
          );
        }
      });
      array.setAttribute("data-address", String(state.address));
      array.setAttribute("data-we", String(state.we));
      array.setAttribute("data-action", state.action);
      array.setAttribute("data-busy", String(state.busy));
      array.setAttribute("data-output", bits(state.output));
      const addressBits = bits(state.address, rows === 2 ? 1 : 2);
      addressValues.forEach((element, bit) =>
        setText(element, addressBits[bit] ?? "0"),
      );
      setText(weValue, state.we);
      rowAddresses.forEach((element, r) =>
        setText(element, `ADDR ${bits(r, rows === 2 ? 1 : 2)}`),
      );
      setText(compactAddress, bits(state.address, 2));
      setText(compactWE, state.we);
      setText(compactOutput, bits(state.output));
      phaseLabels.forEach((element) =>
        setText(
          element,
          `${state.action} ADDR ${bits(state.address, rows === 2 ? 1 : 2)}`,
        ),
      );
      inputDigits.forEach((element, c) =>
        setText(element, bits(register ? registerState.input : state.input)[c]),
      );
      rowDigits.forEach((row, r) =>
        row.forEach((element, c) =>
          setText(
            element,
            bits(
              register && r === 0
                ? registerState.output
                : (state.words[r] ?? 0),
            )[c],
          ),
        ),
      );
      outputDigits.forEach((element, c) =>
        setText(element, bits(state.output)[c]),
      );
      for (let r = 0; r < 4; r++) {
        const selected = r < rows && r === state.address ? 1 : 0;
        const writing = selected * state.we;
        dynamic.selected[r] += (selected - dynamic.selected[r]) * blend;
        dynamic.writing[r] += (writing - dynamic.writing[r]) * blend;
        readLights[r].style.opacity = dynamic.selected[r];
        selectLights[r].style.opacity = dynamic.selected[r];
        writeLights[r].style.opacity = dynamic.writing[r];
        writeInputLights[r].style.opacity = state.we;
      }
      outputLights.forEach((element) => (element.style.opacity = 0.85));
      writeFeedLight.setAttribute("d", writeFeed.getAttribute("d"));
      writeFeedLight.style.opacity = state.we;
      adderLights.forEach(
        (element) => (element.style.opacity = dynamic.writing[1]),
      );
    });
    return { demos, dispose: controls.dispose };
  };
  return { build };
})();
