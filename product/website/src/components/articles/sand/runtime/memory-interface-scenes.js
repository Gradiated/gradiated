import { gsap } from "gsap";
import {
  createMemoryAccessModel,
  MEMORY_ACCESS_DURATION,
} from "./memory-access-model.js";

export const MEMORY_INTERFACE_SCENES = {
  build({
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
    afterRender,
    controls,
  }) {
    const demos = [];
    const label = (parent, x, y, value, attrs = {}) =>
      text(x, y, value, { class: "caption", ...attrs }, parent);
    const value = (parent, x, y, content, attrs = {}) =>
      text(x, y, content, { class: "bit", ...attrs }, parent);
    const box = (parent, x, y, width, height) =>
      mk("rect", { x, y, width, height, rx: 2, class: "memory-box" }, parent);
    const binary = (n, width) => n.toString(2).padStart(width, "0");
    const word = (n, width = 16) =>
      binary(n, width).replace(/(.{8})(?=.)/g, "$1 ");
    const updateText = (element, content) => {
      if (element.textContent !== String(content))
        element.textContent = String(content);
    };
    const bus = (parent, d, width, x, y) => {
      path(d, { class: "interface-bus" }, parent);
      path(`M${x - 3} ${y + 4} L${x + 3} ${y - 4}`, { class: "thin" }, parent);
      return value(parent, x + 10, y - 4, width, { class: "tiny bit" });
    };
    const rowValues = [3, 6, 0, 0];
    const rowFrames = group({ "data-part": "memory-row-collapse" }, root);
    show(rowFrames, "memory-width", "working-registers");
    for (let row = 0; row < 4; row++) {
      const frame = box(rowFrames, 145, 155 + row * 45, 225, 26);
      key(frame, "memory-width", {
        opacity: 0,
        attr: { x: 145, y: 155 + row * 45, width: 225, height: 26 },
      });
      key(frame, "memory-interface", {
        opacity: 1,
        attr: { x: 135, y: 145 + row * 45, width: 250, height: 45 },
      });
    }
    const detailed = group({ "data-diagram": "memory-width" }, root);
    show(detailed, "memory-width", "memory-interface", {}, 0.95);
    const oldTitle = label(detailed, 220, 45, "4 locations × 4 bits");
    const newTitle = label(detailed, 220, 45, "4 locations × 8 bits");
    gsap.set(newTitle, { opacity: 0 });
    const routing = group({}, detailed);
    key(routing, "memory-width");
    key(routing, "memory-interface", { opacity: 0 }, null, 0, 0.4);
    box(routing, 28, 203, 39, 52);
    label(routing, 47.5, 225, "address", { class: "tiny" });
    label(routing, 47.5, 239, "decoder", { class: "tiny" });
    label(routing, 17, 95, "ADDR", { class: "tiny bit" });
    bus(routing, "M17 103 V229 H28", "2", 17, 145);
    label(routing, 91, 95, "WE", { class: "tiny bit" });
    path("M91 103 V287", { class: "thin muted" }, routing);
    const widening = gsap.timeline({ paused: true });
    const additions = group({}, detailed);
    gsap.set(additions, { opacity: 0 });
    for (let row = 0; row < 4; row++) {
      const y = 155 + row * 45;
      const portY = 213 + row * 10;
      const elbowX = 74 + row * 3;
      path(
        `M67 ${portY} H${elbowX} V${y - 10} H110 M91 ${y - 3} H110`,
        { class: "thin muted" },
        routing,
      );
      path(
        `M110 ${y - 12} H116 A6 6 0 0 1 116 ${y} H110 Z`,
        { class: "memory-box" },
        routing,
      );
      path(`M122 ${y - 6} H363`, { class: "thin muted" }, routing);
      mk("circle", { cx: 91, cy: y - 3, r: 1.3, class: "dot" }, routing);
      value(routing, 102, y + 23, binary(row, 2), { class: "tiny bit" });
      for (let bit = 0; bit < 8; bit++) {
        const low = bit >= 4;
        const x = 155 + bit * 29;
        const growth = group({}, low ? detailed : additions);
        const cell = group({}, growth);
        path(`M${x - 14} ${y + 12} H${x - 9}`, { class: "thin muted" }, cell);
        path(`M${x + 5} ${y - 6} V${y}`, { class: "thin muted" }, cell);
        box(cell, x - 9, y, 18, 26);
        value(cell, x, y + 18, binary(rowValues[row], 8)[bit], {
          class: "tiny bit",
        });
        key(cell, "memory-width", { x: 0, scaleX: 1 });
        key(cell, "memory-interface", {
          x: 260 + (bit - 3.5) * 8 - x,
          scaleX: 0.7,
          opacity: 0,
        });
        const feed = group({}, growth);
        key(feed, "memory-width");
        key(feed, "memory-interface", { opacity: 0 }, null, 0, 0.4);
        if (row === 0) {
          value(feed, x - 14, 112, `D${7 - bit}`, { class: "tiny bit" });
          path(`M${x - 14} 120 V302`, { class: "thin muted" }, feed);
        }
        if (low) {
          const offset = 159 + (bit - 4) * 65 - x;
          gsap.set(growth, { x: offset });
          widening.to(
            growth,
            { x: 0, duration: 1.7, ease: "power2.inOut" },
            1.2,
          );
        }
      }
    }
    widening.to(oldTitle, { opacity: 0, duration: 0.4 }, 1.2);
    widening.to(newTitle, { opacity: 1, duration: 0.5 }, 2.1);
    widening.to(additions, { opacity: 1, duration: 0.8 }, 2.2);
    const byteLabel = label(detailed, 262, 385, "one byte per location");
    gsap.set(byteLabel, { opacity: 0 });
    widening.to(byteLabel, { opacity: 1, duration: 0.5 }, 2.9);
    widening.to({}, { duration: 0.6 });
    demos.push(widening);
    let widthActive = false;
    afterRender.push(() => {
      const active = Math.abs(tl.time() - index("memory-width")) <= hold;
      if (active && !widthActive) widening.restart();
      if (!active) {
        if (tl.time() > index("memory-width") && widening.progress() < 1)
          widening.progress(1);
        widening.pause();
      }
      widthActive = active;
    });

    const diagram = group({ "data-diagram": "memory-interface" }, root);
    key(diagram, "memory-interface", {}, null, 0.55);
    key(diagram, "working-registers", { opacity: 0 }, null, 0, 0.8);
    const eight = group({}, diagram);
    const sixteen = group({}, diagram);
    const labels = group({}, diagram);
    box(diagram, 85, 145, 50, 180);
    for (let r = 1; r < 4; r++)
      path(`M85 ${145 + r * 45} H135`, { class: "thin muted" }, diagram);
    const chosenRow = mk(
      "rect",
      { x: 87, y: 192, width: 296, height: 41, rx: 2, class: "computer-glow" },
      diagram,
    );
    gsap.set(chosenRow, { opacity: 0 });
    label(diagram, 260, 132, "memory");
    label(diagram, 110, 132, "Address", { class: "tiny" });
    const addresses = [];
    const eightValues = [];
    const sixteenValues = [];
    for (let r = 0; r < 4; r++) {
      const y = 173 + r * 45;
      addresses.push(
        value(labels, 110, y, binary(r, 2), { class: "tiny bit" }),
      );
      eightValues.push(
        value(eight, 260, y, word(rowValues[r], 8), {
          class: "interface-value bit",
        }),
      );
      sixteenValues.push(
        value(sixteen, 260, y, word(rowValues[r]), {
          class: "interface-value bit",
        }),
      );
    }
    show(eight, "memory-interface", "memory-word");
    show(sixteen, "memory-word", "working-registers");
    label(eight, 235, 24, "4 locations × 1 byte");
    const dataWidthTitle = label(
      sixteen,
      235,
      24,
      "16 bits = 2 bytes per location",
    );
    show(dataWidthTitle, "memory-word", "memory-address-space");
    const twoAddressBits = value(diagram, 54, 141, "2", { class: "tiny bit" });
    show(twoAddressBits, "memory-interface", "memory-address-space");
    const fullAddressBits = value(diagram, 54, 141, "16", {
      class: "tiny bit",
    });
    show(fullAddressBits, "memory-address-space", "working-registers");
    box(diagram, 54, 43, 145, 56);
    label(diagram, 126, 61, "MAR", { class: "caption bit" });
    const marSmall = value(diagram, 126, 83, "01", {
      class: "interface-value bit",
    });
    show(marSmall, "memory-interface", "memory-address-space");
    const marWide = value(diagram, 126, 83, word(1), {
      class: "interface-value bit",
    });
    show(marWide, "memory-address-space", "working-registers");
    const addressD = "M126 99 V112 H62 V168 H85";
    path(addressD, { class: "interface-bus" }, diagram);
    path("M59 147 L65 139", { class: "thin" }, diagram);
    value(diagram, 34, 123, "ADDR", { class: "tiny bit" });
    box(diagram, 169, 374, 170, 52);
    label(diagram, 254, 393, "MDR", { class: "caption bit" });
    value(eight, 254, 414, word(9, 8), {
      class: "interface-value bit",
    });
    const mdrWide = value(sixteen, 254, 414, word(9), {
      class: "interface-value bit",
    });
    const writeD = "M220 374 V325";
    const readD = "M292 325 V374";
    bus(diagram, writeD, "8", 220, 350);
    bus(diagram, readD, "8", 292, 350);
    for (const marker of diagram.querySelectorAll("text.tiny")) {
      if (marker.textContent === "8") {
        show(marker, "memory-interface", "memory-word");
        const replacement = value(
          diagram,
          Number(marker.getAttribute("x")),
          Number(marker.getAttribute("y")),
          "16",
          { class: "tiny bit" },
        );
        show(replacement, "memory-word", "working-registers");
      }
    }
    path(
      "M216 333 L220 325 L224 333 M288 366 L292 374 L296 366",
      { class: "thin" },
      diagram,
    );
    value(diagram, 202, 351, "D", { class: "tiny bit" });
    value(diagram, 318, 351, "Q", { class: "tiny bit" });
    const enableD = "M37 284 H85";
    path(enableD, {}, diagram);
    value(diagram, 55, 274, "WE", { class: "tiny bit" });
    const weDigit = value(diagram, 55, 303, "0", { class: "tiny bit" });
    const addressLight = path(addressD, { class: "computer-signal" }, diagram);
    const writeLight = path(writeD, { class: "computer-signal" }, diagram);
    const readLight = path(readD, { class: "computer-signal" }, diagram);
    const enableLight = path(enableD, { class: "computer-signal" }, diagram);
    gsap.set([addressLight, writeLight, readLight, enableLight], {
      opacity: 0,
    });
    const moreRows = group({}, diagram);
    label(moreRows, 260, 263, "…");
    value(moreRows, 110, 263, "…", { class: "tiny bit" });
    show(moreRows, "memory-address-space", "working-registers");
    show(addresses[2], "memory-interface", "memory-address-space");
    show(sixteenValues[2], "memory-word", "memory-address-space");
    const decimalAddresses = group({}, diagram);
    for (const r of [0, 1])
      value(decimalAddresses, 110, 173 + r * 45, String(r), {
        class: "tiny bit",
      });
    show(decimalAddresses, "memory-address-space", "working-registers");
    for (const r of [0, 1])
      show(addresses[r], "memory-interface", "memory-address-space");
    const lastAddress = value(diagram, 110, 308, "65535", {
      class: "tiny bit",
    });
    show(lastAddress, "memory-address-space", "working-registers");
    show(addresses[3], "memory-interface", "memory-address-space");
    const addressCaption = label(
      diagram,
      235,
      24,
      "65,536 locations · 16 bits at each ADDR",
      { class: "tiny" },
    );
    show(addressCaption, "memory-address-space", "working-registers");
    const access = group({ "data-part": "memory-access-transfers" }, diagram);
    show(access, "memory-access", "working-registers");
    const flyingWord = value(access, 254, 414, word(9), {
      class: "interface-value bit",
      "data-access-flight": "",
    });
    const incomingAddress = value(access, 126, 19, word(1), {
      class: "interface-value bit",
    });
    const incomingData = value(access, 254, 437, word(9), {
      class: "interface-value bit",
    });
    const status = label(access, 235, 111, "", {
      class: "tiny",
      "data-access-phase": "",
    });
    gsap.set([flyingWord, incomingAddress, incomingData], { opacity: 0 });
    const model = createMemoryAccessModel();
    const time = { value: 0 };
    const animation = gsap.timeline({ paused: true }).to(time, {
      value: MEMORY_ACCESS_DURATION,
      duration: MEMORY_ACCESS_DURATION,
      ease: "none",
    });
    demos.push(animation);
    controls.register(
      "memory-access",
      {
        addresses: [1],
        rows: 65536,
        addressWidth: 16,
        dataWidth: 16,
        compact: true,
      },
      (_scene, action) => {
        if (model.frame(time.value).busy) return;
        model.choose(action);
        animation.restart();
      },
    );
    const lit = new Map();
    const fadeSignal = (element, target) => {
      const opacity =
        (lit.get(element) ?? 0) + (target - (lit.get(element) ?? 0)) * 0.2;
      lit.set(element, opacity);
      element.style.opacity = opacity;
    };
    let activeBefore = false;
    afterRender.push(() => {
      const p = tl.time();
      const nearAccess = Math.abs(p - index("memory-access")) < 0.5;
      const active = Math.abs(p - index("memory-access")) <= hold;
      if (active && !activeBefore && model.frame(time.value).busy)
        animation.play();
      if (!active) animation.pause();
      activeBefore = active;

      if (!nearAccess) {
        for (const el of [
          addressLight,
          writeLight,
          readLight,
          enableLight,
          chosenRow,
        ])
          el.style.opacity = 0;
        lit.clear();
        updateText(marWide, word(1));
        updateText(mdrWide, word(9));
        updateText(weDigit, "0");
        return;
      }
      const state = model.frame(time.value);
      diagram.setAttribute("data-action", state.action);
      diagram.setAttribute("data-mar", state.mar);
      diagram.setAttribute("data-mdr", state.mdr);
      diagram.setAttribute("data-we", state.we);
      diagram.setAttribute("data-busy", state.busy);
      for (const [r, n] of state.words.entries())
        if (n !== null) updateText(sixteenValues[r], word(n));
      updateText(marWide, word(state.mar));
      updateText(mdrWide, word(state.mdr));
      updateText(weDigit, state.we);
      fadeSignal(addressLight, state.selected ? 1 : 0);
      fadeSignal(chosenRow, state.selected ? 0.65 : 0);
      fadeSignal(writeLight, state.we);
      fadeSignal(
        readLight,
        state.action === "Read" && state.time >= 1.4 ? 1 : 0,
      );
      fadeSignal(enableLight, state.we);
      const t = state.time;
      const load = Math.max(0, Math.min(1, t / 0.9));
      const loadOpacity =
        state.busy && t < 0.9 ? Math.min(1, load / 0.15, (1 - load) / 0.15) : 0;
      incomingAddress.style.opacity = loadOpacity;
      incomingAddress.setAttribute("y", 19 + 64 * load);
      incomingData.style.opacity = state.action === "Write" ? loadOpacity : 0;
      incomingData.setAttribute("y", 437 - 23 * load);
      const transfer = state.transfer;
      flyingWord.style.opacity = transfer
        ? Math.min(1, transfer.progress / 0.15, (1 - transfer.progress) / 0.15)
        : 0;
      if (transfer) {
        updateText(flyingWord, word(transfer.value));
        const points =
          transfer.kind === "Write"
            ? [
                [254, 414],
                [220, 374],
                [220, 325],
                [260, 218],
              ]
            : [
                [260, 218],
                [292, 325],
                [292, 374],
                [254, 414],
              ];
        const segments =
          transfer.kind === "Write" ? [0, 0.2, 0.35, 1] : [0, 0.65, 0.8, 1];
        const segment = Math.min(
          2,
          segments.findIndex((end, i) => i > 0 && transfer.progress < end) - 1,
        );
        const f =
          (transfer.progress - segments[segment]) /
          (segments[segment + 1] - segments[segment]);
        const start = points[segment],
          end = points[segment + 1];
        flyingWord.setAttribute("x", start[0] + (end[0] - start[0]) * f);
        flyingWord.setAttribute("y", start[1] + (end[1] - start[1]) * f);
      }
      updateText(
        status,
        !state.busy
          ? state.action === "Ready"
            ? "choose Read or Write"
            : `${state.action} complete`
          : t < 0.9
            ? "load the interface registers"
            : t < 1.6
              ? "select the location"
              : state.action === "Read"
                ? "memory → MDR"
                : "MDR → memory",
      );
      const opacity = Math.max(
        0,
        Math.min(
          1,
          (0.5 - Math.abs(p - index("memory-access"))) / (0.5 - hold),
        ),
      );
      controls.update("memory-access", state, opacity);
    });
    diagram.append(eight, sixteen, labels, decimalAddresses, moreRows, access);
    return { demos };
  },
};
