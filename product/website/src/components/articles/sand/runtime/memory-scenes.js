import { gsap } from "gsap";
import {
  MEMORY_MODEL,
  REGISTER_MODEL,
  dataChangePulse,
} from "./memory-model.js";
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
      selectLights = [];
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
    label(writeGates, 77, 106, "WE");
    const weValue = digit(writeGates, 77, 125, "0");
    const decoder = group({}, array);
    show(decoder, "memory-two", "memory-buses");
    const decoderOutline = box(decoder, 34, 166, 30, 98);
    key(decoderOutline, "memory-two", { attr: { height: 98 } });
    key(decoderOutline, "memory-array", { attr: { height: 194 } });
    const decoderLabel = label(decoder, 49, 290, "Decoder");
    key(decoderLabel, "memory-two", { attr: { y: 290 } });
    key(decoderLabel, "memory-array", { attr: { y: 386 } });
    const firstAddress = wire(decoder, "M14 130 V253");
    key(firstAddress, "memory-two", { attr: { d: "M14 130 V253" } });
    key(firstAddress, "memory-array", { attr: { d: "M14 130 V345" } });
    const secondAddress = wire(decoder, "M22 130 V353");
    key(secondAddress, "memory-array", {});
    label(decoder, 19, 106, "Addr");
    const addressValue = digit(decoder, 19, 125, "0");
    const inputDeck = group({}, array);
    show(inputDeck, "register", "memory-buses");
    const inputFlashes = [];
    const inputDigits = xs.map((x, i) => {
      label(inputDeck, x - 23, 106, `D${3 - i}`, { class: "tiny" });
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
      const rowAddress = label(row, 114, y + 18, bits(r, 2), {
        class: "tiny",
        "text-anchor": "end",
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
      selectLights.push(signal(readSignalRow, select));
      const write = `M88 ${y + 29} V${y + 36} H92 M78 ${y + 44} H92`;
      wire(writeRow, write);
      andGate(writeRow, 92, y + 40);
      const writeOut = `M106 ${y + 40} H${xs[3] - 5}`;
      wire(writeRow, writeOut);
      const writeRoute = group({}, writeSignalRow);
      signal(
        writeRoute,
        `M88 ${y + 29} V${y + 36} H92 M78 ${y + 44} H92`,
      ).setAttribute("opacity", "1");
      signal(writeRoute, writeOut).setAttribute("opacity", "1");
      writeLights.push(writeRoute);
      const readRoute = group({}, readSignalRow);
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
          wire(readRow, `M${x + 18} ${y + 29} V${y + 16} H${x + 20}`);
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
      label(outputDeck, x + 35, 435, `Q${3 - c}`, {
        class: "tiny",
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
    label(registerOnly, 68, 269, "WE", { "text-anchor": "end" });
    const registerWE = digit(registerOnly, 68, 287, "0", {
      "text-anchor": "end",
    });
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
    label(adder, 220, 38, "0011 + 0110 = 1001");
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
      key(link, "stored-answer", { attr: { d }, strokeWidth: 1.4 });
      key(link, "memory-buses", {
        attr: { d: "M220 129 V219" },
        strokeWidth: 3,
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
    label(compact, 185, 67, "4");
    label(compact, 283, 67, "4");
    digit(compact, 171, 46, "0011");
    digit(compact, 269, 46, "0110");
    box(compact, 117, 219, 254, 123);
    label(compact, 244, 253, "Memory");
    label(compact, 244, 276, "4 locations × 4 bits");
    const bus = (d, slash, x, y, width) => {
      path(d, { class: "memory-bus" }, compact);
      wire(compact, slash);
      label(compact, x, y, String(width));
    };
    bus("M220 129 V219", "M214 165 L226 155", 238, 164, 4);
    digit(compact, 254, 195, "1001");
    bus("M59 248 H117", "M80 254 L90 242", 86, 231, 2);
    label(compact, 49, 230, "Addr");
    const compactAddress = digit(compact, 49, 252, "00");
    wire(compact, "M59 302 H117");
    label(compact, 49, 284, "WE");
    const compactWE = digit(compact, 49, 306, "0");
    bus("M244 342 V395", "M238 372 L250 362", 263, 371, 4);
    const compactOutput = digit(compact, 244, 417, "0011");
    const compactReadLight = signal(compact, "M244 342 V395");
    const compactWriteLight = signal(compact, "M220 129 V219");
    const compactSelectLight = signal(compact, "M59 248 H117");
    const compactEnableLight = signal(compact, "M59 302 H117");
    const dynamic = { selected: [0, 0, 0, 0], writing: [0, 0, 0, 0] };
    const clock = gsap.timeline({ paused: true, repeat: -1 });
    clock.to({}, { duration: MEMORY_MODEL.PERIOD });
    demos.push(clock);
    const phaseLabels = [];
    for (const scene of ["memory-two", "memory-array", "stored-answer"]) {
      const phase = label(
        root,
        220,
        scene === "stored-answer" ? 17 : 66,
        "Read address 0",
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
    const compactPhase = label(compact, 244, 313, "Read");
    let lastTime = 0;
    let previousRows = 2;
    let initialWords = [3, 6, 0, 0];
    let wasRegister = true;
    let registerWord = 3;
    let lastState = MEMORY_MODEL.frame(0, previousRows, initialWords);
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
      if (active && !reduced) clock.play();
      else clock.pause();
      if (
        progress < index("register") - hold ||
        progress > index("timing") - hold
      )
        clock.pause(0);
      const rows = progress < index("memory-array") - hold ? 2 : 4;
      if (rows !== previousRows) {
        initialWords = [...lastState.words];
        clock.pause(0);
        lastTime = 0;
        previousRows = rows;
      }
      const register = progress < index("memory-two") - hold;
      if (register) registerWord = registerState.output;
      else if (wasRegister) {
        initialWords = [...lastState.words];
        initialWords[0] = registerWord;
        clock.pause(0);
        lastTime = 0;
      }
      wasRegister = register;
      const elapsed = reduced ? 8 : clock.totalTime();
      const state = MEMORY_MODEL.frame(elapsed, rows, initialWords);
      lastState = state;
      const delta = Math.min(0.05, Math.max(0, elapsed - lastTime));
      const blend = reduced ? 1 : Math.min(1, delta * 9);
      lastTime = elapsed;
      array.setAttribute("data-address", String(state.address));
      array.setAttribute("data-we", String(state.we));
      array.setAttribute("data-output", bits(state.output));
      setText(addressValue, bits(state.address, rows === 2 ? 1 : 2));
      setText(weValue, state.we);
      rowAddresses.forEach((element, r) =>
        setText(element, bits(r, rows === 2 ? 1 : 2)),
      );
      setText(compactAddress, bits(state.address, 2));
      setText(compactWE, state.we);
      setText(compactOutput, bits(state.output));
      phaseLabels.forEach((element) =>
        setText(
          element,
          `${state.action} address ${bits(state.address, rows === 2 ? 1 : 2)}`,
        ),
      );
      setText(
        compactPhase,
        `${state.action} address ${bits(state.address, 2)}`,
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
      }
      outputLights.forEach((element) => (element.style.opacity = 0.85));
      writeFeedLight.setAttribute("d", writeFeed.getAttribute("d"));
      writeFeedLight.style.opacity = state.we;
      adderLights.forEach(
        (element) => (element.style.opacity = dynamic.writing[2]),
      );
      compactReadLight.style.opacity = 0.9;
      compactSelectLight.style.opacity = 0.9;
      compactWriteLight.style.opacity = dynamic.writing[2];
      compactEnableLight.style.opacity = dynamic.writing[2];
    });
    return { demos };
  };
  return { build };
})();
