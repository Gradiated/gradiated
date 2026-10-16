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
    const detailed = group({ "data-diagram": "memory-width" }, root);
    show(detailed, "memory-width", "memory-interface", {}, 0.8);
    const oldTitle = label(detailed, 220, 45, "4 locations × 4 bits");
    const newTitle = label(detailed, 220, 45, "4 locations × 8 bits");
    gsap.set(newTitle, { opacity: 0 });
    box(detailed, 29, 122, 45, 207);
    label(detailed, 51, 353, "decoder", { class: "tiny" });
    label(detailed, 25, 82, "ADDR", { class: "tiny bit" });
    path("M24 89 V141 H29", {}, detailed);
    label(detailed, 89, 82, "WE", { class: "tiny bit" });
    path("M89 90 V310", {}, detailed);
    const rowValues = [3, 6, 0, 0];
    const widening = gsap.timeline({ paused: true });
    const additions = group({}, detailed);
    gsap.set(additions, { opacity: 0 });
    for (let row = 0; row < 4; row++) {
      const y = 128 + row * 48;
      value(detailed, 51, y + 10, binary(row, 2), { class: "tiny bit" });
      path(
        `M74 ${y + 15} H101 M89 ${y + 25} H101`,
        { class: "thin muted" },
        detailed,
      );
      path(
        `M101 ${y + 13} H108 A7 7 0 0 1 108 ${y + 27} H101 Z`,
        { class: "memory-box" },
        detailed,
      );
      path(`M115 ${y + 20} H360`, { class: "thin muted" }, detailed);
      mk("circle", { cx: 89, cy: y + 25, r: 1.3, class: "dot" }, detailed);
      for (let bit = 0; bit < 8; bit++) {
        const low = bit >= 4;
        const x = 164 + bit * 25;
        const cell = group({}, low ? detailed : additions);
        path(`M${x - 13} ${y + 5} H${x - 9}`, { class: "thin muted" }, cell);
        box(cell, x - 9, y, 18, 25);
        value(cell, x, y + 17, binary(rowValues[row], 8)[bit], {
          class: "tiny bit",
        });
        if (row === 0) {
          value(cell, x, 103, `D${7 - bit}`, { class: "tiny bit" });
          path(`M${x - 13} 110 V277`, { class: "thin muted" }, cell);
        }
        if (low) {
          const offset = 144 + (bit - 4) * 67 - x;
          gsap.set(cell, { x: offset });
          widening.to(cell, { x: 0, duration: 1.7, ease: "power2.inOut" }, 1.2);
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
      if (!active) widening.pause();
      widthActive = active;
    });

    const diagram = group({ "data-diagram": "memory-interface" }, root);
    show(diagram, "memory-interface", "working-registers", {}, 0.8);
    const eight = group({}, diagram);
    const sixteen = group({}, diagram);
    const labels = group({}, diagram);
    box(diagram, 85, 145, 300, 180);
    path("M135 145 V325", { class: "thin muted" }, diagram);
    for (let r = 1; r < 4; r++)
      path(`M85 ${145 + r * 45} H385`, { class: "thin muted" }, diagram);
    const chosenRow = mk(
      "rect",
      { x: 87, y: 192, width: 296, height: 41, rx: 2, class: "computer-glow" },
      diagram,
    );
    gsap.set(chosenRow, { opacity: 0 });
    label(diagram, 235, 132, "memory");
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
    label(sixteen, 235, 24, "16 bits = 2 bytes per location");
    const twoAddressBits = value(diagram, 95, 126, "2", { class: "tiny bit" });
    show(twoAddressBits, "memory-interface", "memory-address-space");
    const fullAddressBits = value(diagram, 95, 126, "16", {
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
    const addressD = "M126 99 V116 H62 V168 H85";
    path(addressD, { class: "interface-bus" }, diagram);
    path("M90 120 L96 112", { class: "thin" }, diagram);
    value(diagram, 36, 153, "ADDR", { class: "tiny bit" });
    box(diagram, 169, 345, 170, 58);
    label(diagram, 254, 363, "MDR", { class: "caption bit" });
    value(eight, 254, 389, word(9, 8), {
      class: "interface-value bit",
    });
    const mdrWide = value(sixteen, 254, 389, word(9), {
      class: "interface-value bit",
    });
    const writeD = "M235 345 V325";
    const readD = "M285 325 V345";
    bus(diagram, writeD, "8", 235, 335);
    bus(diagram, readD, "8", 285, 335);
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
      "M231 333 L235 325 L239 333 M281 337 L285 345 L289 337",
      { class: "thin" },
      diagram,
    );
    value(diagram, 217, 340, "D", { class: "tiny bit" });
    value(diagram, 308, 340, "Q", { class: "tiny bit" });
    const enableD = "M37 284 H85";
    path(enableD, {}, diagram);
    value(diagram, 55, 274, "WE", { class: "tiny bit" });
    const weDigit = value(diagram, 55, 303, "0", { class: "tiny bit" });
    const clockWires = "M20 374 V71 H54 M20 374 H169";
    path(clockWires, { class: "thin dashed muted" }, diagram);
    path(
      "M54 66 L62 71 L54 76 M169 369 L177 374 L169 379",
      { class: "thin" },
      diagram,
    );
    value(diagram, 57, 393, "CLK", { class: "tiny bit" });
    path(
      "M29 410 H43 V401 H57 V410 H71 V401 H85",
      { class: "thin muted" },
      diagram,
    );
    const clockLight = path(clockWires, { class: "computer-signal" }, diagram);
    const addressLight = path(addressD, { class: "computer-signal" }, diagram);
    const writeLight = path(writeD, { class: "computer-signal" }, diagram);
    const readLight = path(readD, { class: "computer-signal" }, diagram);
    const enableLight = path(enableD, { class: "computer-signal" }, diagram);
    gsap.set([clockLight, addressLight, writeLight, readLight, enableLight], {
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
      431,
      "65,536 locations · 16 bits at each ADDR",
      { class: "tiny" },
    );
    show(addressCaption, "memory-address-space", "working-registers");
    const access = group({ "data-part": "memory-access-transfers" }, diagram);
    show(access, "memory-access", "working-registers");
    const flyingWord = value(access, 254, 389, word(9), {
      class: "interface-value bit",
      "data-access-flight": "",
    });
    const incomingAddress = value(access, 126, 19, word(1), {
      class: "interface-value bit",
    });
    const incomingData = value(access, 254, 427, word(9), {
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
          clockLight,
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
      fadeSignal(clockLight, state.clock ? 1 : 0);
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
      incomingData.setAttribute("y", 427 - 38 * load);
      const transfer = state.transfer;
      flyingWord.style.opacity = transfer
        ? Math.min(1, transfer.progress / 0.15, (1 - transfer.progress) / 0.15)
        : 0;
      if (transfer) {
        updateText(flyingWord, word(transfer.value));
        const points =
          transfer.kind === "Write"
            ? [
                [254, 389],
                [235, 345],
                [235, 325],
                [260, 218],
              ]
            : [
                [260, 218],
                [285, 325],
                [285, 345],
                [254, 389],
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
