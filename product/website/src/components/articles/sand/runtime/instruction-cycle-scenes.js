import { gsap } from "gsap";
import {
  INSTRUCTION_BITS,
  PROGRAM_START,
  instructionCycleFrame,
} from "./instruction-cycle-model.js";

export const INSTRUCTION_CYCLE_SCENES = {
  build({
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
  }) {
    const clamp = (n) => Math.max(0, Math.min(1, n));
    const during = (time, start, end) =>
      Math.min(clamp((time - start) / 0.18), clamp((end - time) / 0.18));
    const diagram = group({ "data-diagram": "instruction-cycle" }, root, "0 0");
    key(diagram, "addressed-memory", {}, null, 0.55);
    const label = (parent, x, y, content, attrs = {}) =>
      text(x, y, content, { class: "caption", ...attrs }, parent);
    const bit = (parent, x, y, content, attrs = {}) =>
      text(x, y, content, { class: "bit", ...attrs }, parent);
    const setText = (node, content) => {
      if (node.textContent !== String(content))
        node.textContent = String(content);
    };
    const rect = (parent, x, y, width, height, className = "memory-box") =>
      mk("rect", { x, y, width, height, rx: 4, class: className }, parent);
    const bus = (parent, d) => path(d, { class: "interface-bus" }, parent);
    const wires = group({ "data-part": "fetch-wires" }, diagram);
    const ports = group({}, diagram);
    const signals = group({ "data-wire-highlights": "" }, diagram);
    const transfers = group({}, diagram);
    const route = (name, d, startScene) => {
      const base = bus(wires, d);
      const lit = path(
        d,
        { class: "computer-signal", "data-fetch-route": name },
        signals,
      );
      if (startScene) show(base, startScene, undefined);
      return { base, lit };
    };
    const cpu = group({ "data-part": "fetch-cpu-outline" }, diagram);
    rect(cpu, 2, 4, 434, 214, "fetch-cpu-frame");
    rect(cpu, 196, 0, 46, 16, "timing-paper");
    label(cpu, 219, 14, "CPU");
    show(cpu, "computer", undefined);
    diagram.insertBefore(cpu, wires);

    const boundaries = group({ "data-part": "system-boundaries" }, diagram);
    diagram.insertBefore(boundaries, wires);
    const controlBoundary = group(
      { "data-part": "control-unit-boundary" },
      boundaries,
    );
    const controlFrame = path(
      "M22 16 H430 V98 H266 V98 H22 Z",
      { class: "fetch-control-frame" },
      controlBoundary,
    );
    label(controlBoundary, 231, 35, "control unit");
    key(controlBoundary, "program");
    key(controlFrame, "program", {
      attr: { d: "M22 16 H430 V98 H266 V98 H22 Z" },
    });
    key(controlFrame, "execute", {
      attr: { d: "M22 16 H430 V212 H266 V98 H22 Z" },
    });
    const memoryBoundary = group(
      { "data-part": "memory-system-boundary" },
      boundaries,
    );
    const memoryBoundaryShape = "M10 220 H428 V438 H100 V294 H10 Z";
    path(memoryBoundaryShape, { class: "memory-block-tint" }, memoryBoundary);
    path(memoryBoundaryShape, { class: "memory-block-frame" }, memoryBoundary);
    label(memoryBoundary, 150, 235, "memory");
    show(memoryBoundary, "program", undefined);

    const memory = group({ "data-part": "program-memory" }, ports, "0 0");
    const tableTint = rect(memory, 106, 296, 314, 138, "memory-block-tint");
    show(tableTint, "addressed-memory", "program");
    rect(memory, 106, 296, 314, 138, "memory-block-frame");
    bit(memory, 141, 316, "ADDR", { class: "tiny bit" });
    const memoryHeading = label(memory, 298, 316, "memory");
    path(
      "M106 324 H420 M177 296 V434 M106 360 H420 M106 396 H420",
      { class: "thin muted" },
      memory,
    );
    const memoryRows = [];
    for (const [i, address, contents] of [
      [0, PROGRAM_START, INSTRUCTION_BITS],
      [1, PROGRAM_START + 1, INSTRUCTION_BITS],
      [2, 16384, "0000 0000 0000 0110"],
    ]) {
      const y = 348 + i * 36;
      const tint = rect(memory, 108, y - 21, 310, 32, "computer-glow");
      bit(memory, 141, y, address, { class: "fetch-address bit" });
      bit(memory, 298, y, contents, { class: "fetch-bits bit" });
      memoryRows.push(tint);
    }
    const programNames = group({}, diagram);
    bit(programNames, 263, 180, "ADD R0 R0 R3");
    label(programNames, 263, 205, "the same instruction, stored as bits", {
      class: "tiny muted",
    });
    show(programNames, "addressed-memory", "program", {}, 0.4);
    key(memory, "addressed-memory", { x: 0, y: -40, scale: 1 });
    key(memory, "program", { x: 0, y: 0, scale: 1 });

    const pc = group({ "data-part": "program-counter" }, ports);
    rect(pc, 38, 46, 76, 40);
    label(pc, 46, 35, "PC");
    const pcValue = bit(pc, 76, 72, PROGRAM_START, {
      "data-fetch-value": "pc",
    });
    show(pc, "program", undefined);
    const mar = group({}, ports);
    rect(mar, 16, 246, 76, 40);
    label(mar, 54, 235, "MAR");
    const marValue = bit(mar, 54, 272, "—", { "data-fetch-value": "mar" });
    show(mar, "program", undefined);
    const addressRoute = route("pc-mar", "M38 66 H12 V266 H16", "program");
    const selectionRoute = route(
      "mar-memory",
      "M92 266 H102 V342 H106",
      "program",
    );
    const increment = group({}, ports);
    rect(increment, 142, 49, 29, 32);
    bit(increment, 156.5, 70, "+1", { class: "tiny bit" });
    bus(increment, "M114 66 H142 M171 66 H182 V22 H76 V46");
    show(increment, "instruction-fetch", undefined);
    const mdr = group({}, ports);
    rect(mdr, 212, 236, 208, 40);
    label(mdr, 316, 235, "MDR");
    const mdrValue = bit(mdr, 316, 261, "—", {
      class: "fetch-bits bit",
      "data-fetch-value": "mdr",
    });
    show(mdr, "instruction-fetch", undefined);
    const ir = group({}, ports);
    rect(ir, 245, 46, 175, 40);
    label(ir, 332.5, 35, "IR");
    const irValue = bit(ir, 332.5, 71, "—", {
      class: "fetch-bits bit",
      "data-fetch-value": "ir",
    });
    show(ir, "instruction-fetch", undefined);
    const readRoute = route("memory-mdr", "M316 296 V276", "instruction-fetch");
    const irRoute = route(
      "mdr-ir",
      "M420 256 H432 V66 H420",
      "instruction-fetch",
    );

    const pu = group({ "data-part": "fetched-processing-unit" }, ports);
    rect(pu, 20, 112, 215, 104, "processing-block-tint");
    rect(pu, 20, 112, 215, 104, "processing-block-frame");
    label(pu, 127.5, 126, "processing unit");
    for (const [y, name] of [
      [133, "R0"],
      [165, "R3"],
    ]) {
      rect(pu, 32, y, 69, 26);
      bit(pu, 46, y + 18, name, { class: "tiny bit" });
    }
    const r0Value = bit(pu, 83, 151, "9", { "data-fetch-value": "r0" });
    bit(pu, 83, 183, "2");
    path("M156 130 H174 L183 141 L192 130 H218 L208 185 H166 Z", {}, pu);
    label(pu, 187, 160, "ALU");
    const addMode = bit(pu, 187, 176, "ADD", { class: "tiny bit" });
    const inputRoutes = [
      route("r0-alu", "M101 146 H126 V145 H159", "execute"),
      route("r3-alu", "M101 178 H137 V171 H163", "execute"),
    ];
    const resultRoute = route(
      "alu-r0",
      "M187 185 V202 H25 V146 H32",
      "execute",
    );
    show(pu, "execute", undefined);

    const cu = group({ "data-part": "fetch-control-unit" }, ports);
    rect(cu, 280, 112, 140, 80);
    label(cu, 350, 131, "controller");
    const decoded = bit(cu, 350, 163, "ADD R0 R0 R3", {
      class: "fetch-bits bit",
    });
    show(cu, "execute", undefined);
    const decodeRoute = route("ir-cu", "M332 86 V112", "execute");
    const controlWires = group({}, wires);
    show(controlWires, "execute", undefined);
    const controlRoute = path(
      "M280 148 H251 V94 H127.5 V112",
      { class: "control-wire" },
      controlWires,
    );
    const saveRoute = path(
      "M280 177 H254 V224 H12 V122 H66.5 V133",
      { class: "control-wire" },
      controlWires,
    );
    const modeRoute = path(
      "M280 164 H241 V170 H211",
      { class: "control-wire" },
      controlWires,
    );
    const states = group({ "data-part": "sequencer" }, cu);
    const stateTints = ["fetch", "decode", "execute"].map((name, i) => {
      const tint = rect(states, 287 + i * 43, 149, 40, 25, "computer-glow");
      label(states, 307 + i * 43, 165, name, { class: "tiny" });
      return tint;
    });
    show(states, "control", undefined);
    show(decoded, "execute", "control");
    const clock = group({ "data-part": "sequencing-clock" }, ports);
    mk("circle", { cx: 287, cy: 200, r: 4, class: "computer-glow" }, clock);
    const clockPulse = mk(
      "circle",
      { cx: 287, cy: 200, r: 4, class: "fetch-clock-pulse" },
      clock,
    );
    label(clock, 323, 204, "clock", { class: "tiny" });
    path("M287 196 V192", { class: "thin muted" }, clock);
    show(clock, "control", undefined);

    const io = group({}, ports);
    for (const [y, name] of [
      [378, "input"],
      [413, "output"],
    ]) {
      rect(io, 16, y, 69, 22);
      label(io, 50.5, y + 15, name, { class: "tiny" });
    }
    path("M16 389 H6 V218 M16 424 H2 V218", { class: "thin muted" }, io);
    show(io, "computer", undefined);
    const status = label(diagram, 233, 8, "", {
      class: "fetch-phase caption",
      "data-fetch-phase": "",
    });
    const flying = [
      "address",
      "instruction",
      "result",
      "input-a",
      "input-b",
    ].map((name) =>
      bit(transfers, 0, 0, "", {
        class: "fetch-transfer bit",
        "data-fetch-transfer": name,
      }),
    );
    const move = (node, route, progress, content) => {
      const q = clamp(progress);
      const point = route.base.getPointAtLength(
        route.base.getTotalLength() * q,
      );
      node.setAttribute("x", point.x);
      node.setAttribute("y", point.y - 9);
      node.style.opacity =
        progress > 0 && progress < 1
          ? String(Math.min(1, progress * 8, (1 - progress) * 8))
          : "0";
      setText(node, content);
    };
    const lit = (route, amount) => {
      route.lit.style.opacity = String(clamp(amount));
    };
    const time = { value: 0 };
    const demo = gsap.timeline({ paused: true });
    let activeScene = null;
    const durations = {
      program: 2,
      "instruction-fetch": 4.2,
      execute: 6.5,
      control: 24.5,
    };
    afterRender.push(() => {
      const p = tl.time();
      if (p < index("addressed-memory") - hold) {
        demo.pause();
        activeScene = null;
        return;
      }
      const scene =
        Object.keys(durations).find(
          (name) => Math.abs(p - index(name)) <= hold,
        ) || null;
      if (scene !== activeScene) {
        demo.pause().clear();
        if (scene) {
          time.value = 0;
          demo.to(time, {
            value: durations[scene],
            duration: durations[scene],
            ease: "none",
          });
        }
        activeScene = scene;
      }
      if (scene && matchMedia("(prefers-reduced-motion: reduce)").matches)
        demo.progress(1).pause();
      else if (scene) demo.play();
      else demo.pause();
      const stage =
        p < index("program") - hold
          ? "stored"
          : p < index("instruction-fetch") - hold
            ? "program"
            : p < index("execute") - hold
              ? "instruction-fetch"
              : p < index("control") - hold
                ? "execute"
                : p < index("computer") - hold
                  ? "control"
                  : "computer";
      const t = scene ? time.value : durations[stage] || 0;
      const modelTime =
        stage === "stored"
          ? 0
          : stage === "program"
            ? Math.min(t, 1.8)
            : stage === "instruction-fetch"
              ? Math.min(1.6 + t, 5.8)
              : stage === "execute"
                ? 5 + t
                : stage === "computer"
                  ? 24
                  : t;
      const state = instructionCycleFrame(
        modelTime,
        stage === "control" || stage === "computer" ? 2 : 1,
      );
      const elapsed = state.elapsed;
      const full = stage === "control" || stage === "computer";
      const fetching = stage === "instruction-fetch" || full;
      const executing = stage === "execute" || full;
      setText(memoryHeading, stage === "stored" ? "memory" : "contents");
      setText(pcValue, stage === "program" ? PROGRAM_START : state.pc);
      setText(marValue, state.mar ?? "—");
      setText(mdrValue, state.mdr ?? "—");
      setText(irValue, state.ir ?? "—");
      setText(r0Value, state.r0);
      diagram.setAttribute(
        "data-fetch-pc",
        stage === "program" ? PROGRAM_START : state.pc,
      );
      diagram.setAttribute("data-fetch-r0", state.r0);
      diagram.setAttribute(
        "data-fetch-write-enabled",
        String(state.writeEnabled),
      );
      const addressProgress = (elapsed - 0.3) / 1.3;
      const readProgress = (elapsed - 1.8) / 1.4;
      const instructionProgress = (elapsed - 3.4) / 1.4;
      const resultProgress = (elapsed - 8.6) / 1.8;
      lit(addressRoute, stage !== "stored" ? during(elapsed, 0.3, 1.8) : 0);
      lit(selectionRoute, state.mar !== null ? during(elapsed, 1.6, 5.2) : 0);
      lit(readRoute, fetching ? during(elapsed, 1.8, 3.4) : 0);
      lit(irRoute, fetching ? during(elapsed, 3.4, 5.2) : 0);
      lit(decodeRoute, executing ? during(elapsed, 4.8, 6.4) : 0);
      for (const input of inputRoutes)
        lit(input, executing ? during(elapsed, 6.4, 8.6) : 0);
      lit(resultRoute, executing ? during(elapsed, 8.6, 10.7) : 0);
      controlRoute.style.opacity = String(
        0.2 + (executing ? 0.5 * during(elapsed, 6.4, 10.7) : 0),
      );
      modeRoute.style.opacity = String(
        0.2 + (executing ? 0.6 * during(elapsed, 7.6, 8.6) : 0),
      );
      saveRoute.style.opacity = String(
        0.2 + (executing ? 0.65 * during(elapsed, 10.1, 10.7) : 0),
      );
      addMode.style.opacity = executing && elapsed >= 7.6 ? "1" : "0.4";
      memoryRows.forEach((node, i) => {
        node.style.opacity =
          stage === "stored"
            ? i < 2
              ? "0.5"
              : "0"
            : state.mar === PROGRAM_START + i && i < 2
              ? String(during(elapsed, 1.6, 5.2))
              : "0";
      });
      stateTints.forEach((node, i) => {
        const [start, end] = [
          [0, 4.8],
          [4.8, 6.4],
          [6.4, 10.8],
        ][i];
        node.style.opacity = String(during(elapsed, start, end));
      });
      const tickDistance = Math.min(elapsed % 0.8, 0.8 - (elapsed % 0.8));
      clockPulse.style.opacity = String(
        scene && time.value < durations[scene]
          ? clamp(1 - tickDistance / 0.12)
          : 0,
      );
      const phase =
        stage === "stored" || stage === "computer"
          ? ""
          : stage === "program"
            ? "PC → MAR"
            : stage === "instruction-fetch" && elapsed >= 4.8
              ? "instruction ready in IR"
              : elapsed < 1.6
                ? "PC → MAR"
                : elapsed < 3.4
                  ? "memory → MDR"
                  : elapsed < 4.8
                    ? "MDR → IR"
                    : elapsed < 6.4
                      ? "decode"
                      : elapsed < 7.6
                        ? "read R0 and R3"
                        : elapsed < 8.6
                          ? `${state.input} + 2 = ${state.result}`
                          : elapsed < 10.4
                            ? "return the result"
                            : elapsed < 10.8
                              ? "save in R0"
                              : "ready for the next instruction";
      setText(status, phase);
      move(flying[0], addressRoute, addressProgress, state.address);
      move(
        flying[1],
        elapsed < 3.4 ? readRoute : irRoute,
        elapsed < 3.4 ? readProgress : instructionProgress,
        INSTRUCTION_BITS,
      );
      move(flying[2], resultRoute, resultProgress, state.result);
      move(flying[3], inputRoutes[0], (elapsed - 6.4) / 1.2, state.input);
      move(flying[4], inputRoutes[1], (elapsed - 6.4) / 1.2, 2);
      for (const node of flying.slice(3))
        node.style.opacity = executing ? node.style.opacity : "0";
      flying[0].style.opacity =
        stage === "stored" ? "0" : flying[0].style.opacity;
      flying[1].style.opacity = fetching ? flying[1].style.opacity : "0";
      flying[2].style.opacity = executing ? flying[2].style.opacity : "0";
    });
    return { demos: [demo] };
  },
};
