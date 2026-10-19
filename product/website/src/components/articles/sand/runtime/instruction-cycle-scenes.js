import { gsap } from "gsap";
import { buildControllerScene } from "./controller-scenes.js";
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
    key(diagram, "controller", { opacity: 0 });
    key(diagram, "computer", { scale: 0.88, x: 26.4, y: 52 });
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
    key(signals, "addressed-memory");
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
    rect(cpu, 6, 6, 428, 328, "fetch-cpu-frame");
    rect(cpu, 56, 0, 46, 16, "timing-paper");
    label(cpu, 79, 14, "CPU");
    show(cpu, "computer", undefined);
    diagram.insertBefore(cpu, wires);

    const boundaries = group({ "data-part": "system-boundaries" }, diagram);
    diagram.insertBefore(boundaries, wires);
    const controlBoundary = group(
      { "data-part": "control-unit-boundary" },
      boundaries,
    );
    const controlFrame = rect(
      controlBoundary,
      132,
      20,
      288,
      86,
      "fetch-control-frame",
    );
    label(controlBoundary, 276, 36, "control unit");
    key(controlBoundary, "program");
    key(controlFrame, "program", { attr: { height: 86 } });
    key(controlFrame, "execute", { attr: { height: 150 } });
    const memoryBoundary = group(
      { "data-part": "memory-system-boundary" },
      boundaries,
    );
    rect(memoryBoundary, 20, 350, 400, 84, "memory-block-tint");
    rect(memoryBoundary, 20, 350, 400, 84, "memory-block-frame");
    label(memoryBoundary, 220, 368, "memory");
    show(memoryBoundary, "program", undefined);

    const memory = group({ "data-part": "program-memory" }, ports, "0 0");
    rect(memory, 106, 296, 314, 138, "memory-block-tint");
    rect(memory, 106, 296, 314, 138, "memory-block-frame");
    bit(memory, 141, 316, "ADDR", { class: "tiny bit" });
    const memoryHeading = label(memory, 298, 316, "memory");
    path(
      "M106 324 H420 M177 296 V434 M106 354 H420 M106 384 H420 M106 404 H420",
      { class: "thin muted" },
      memory,
    );
    const memoryRows = [];
    for (const [y, address, contents] of [
      [344, PROGRAM_START, INSTRUCTION_BITS],
      [374, PROGRAM_START + 1, INSTRUCTION_BITS],
      [424, 2 ** 16 - 1, "1010 0110 1101 0011"],
    ]) {
      const tint = rect(memory, 108, y - 17, 310, 26, "computer-glow");
      bit(memory, 141, y, address, { class: "fetch-address bit" });
      bit(memory, 298, y, contents, { class: "fetch-bits bit" });
      memoryRows.push(tint);
    }
    bit(memory, 141, 398, "…", { class: "tiny bit muted" });
    bit(memory, 298, 398, "…", { class: "tiny bit muted" });
    const programNames = group({}, diagram);
    bit(programNames, 263, 180, "ADD R0 R0 R3");
    label(programNames, 263, 205, "the same instruction, stored as bits", {
      class: "tiny muted",
    });
    show(programNames, "addressed-memory", "program", {}, 0.4);
    key(memory, "addressed-memory", { x: 0, y: -40, scaleX: 1, scaleY: 1 });
    key(memory, "program", {
      x: 0,
      y: 260,
      scaleX: 1,
      scaleY: 0.25,
      opacity: 0,
    });

    const captures = {};
    const capture = (parent, name, x, y, width, height) => {
      const tint = rect(parent, x, y, width, height, "computer-glow");
      tint.setAttribute("data-register-capture", name);
      tint.style.opacity = "0";
      captures[name] = tint;
    };
    const pc = group({ "data-part": "program-counter" }, ports);
    rect(pc, 150, 54, 80, 42);
    capture(pc, "pc", 151, 55, 78, 40);
    bit(pc, 190, 49, "PC");
    const pcValue = bit(pc, 190, 81, PROGRAM_START, {
      "data-fetch-value": "pc",
    });
    show(pc, "program", undefined);
    const mar = group({}, ports);
    rect(mar, 40, 379, 100, 40);
    capture(mar, "mar", 41, 380, 98, 38);
    bit(mar, 90, 393, "MAR", { class: "tiny bit" });
    const marValue = bit(mar, 90, 411, "—", { "data-fetch-value": "mar" });
    show(mar, "program", undefined);
    const addressRoute = route(
      "pc-mar",
      "M150 75 H118 V115 H10 V399 H40",
      "program",
    );
    const selectionRoute = route("mar-memory", "M90 419 V429", "program");
    const mdr = group({}, ports);
    rect(mdr, 180, 379, 220, 40);
    capture(mdr, "mdr", 181, 380, 218, 38);
    bit(mdr, 290, 393, "MDR", { class: "tiny bit" });
    const mdrValue = bit(mdr, 290, 411, "—", {
      class: "fetch-bits bit",
      "data-fetch-value": "mdr",
    });
    show(mdr, "instruction-fetch", undefined);
    const ir = group({}, ports);
    rect(ir, 248, 54, 154, 42);
    capture(ir, "ir", 249, 55, 152, 40);
    bit(ir, 325, 49, "IR");
    const irValue = bit(ir, 325, 81, "—", {
      class: "fetch-bits bit",
      "data-fetch-value": "ir",
    });
    show(ir, "instruction-fetch", undefined);
    const readRoute = route("memory-mdr", "M290 429 V419", "instruction-fetch");
    const irRoute = route(
      "mdr-ir",
      "M400 399 H438 V75 H402",
      "instruction-fetch",
    );

    const pu = group({ "data-part": "fetched-processing-unit" }, ports, "0 0");
    const puTint = rect(pu, 20, 190, 400, 135, "processing-block-tint");
    const puFrame = rect(pu, 20, 190, 400, 135, "processing-block-frame");
    for (const frame of [puTint, puFrame]) {
      key(frame, "addressed-memory", {
        attr: { x: 3, y: 91, width: 405, height: 316, rx: 8 },
      });
      key(frame, "execute", {
        attr: { x: 20, y: 190, width: 400, height: 135, rx: 4 },
      });
    }
    key(pu, "addressed-memory", { scale: 0.18, x: 14.61, y: -6 });
    key(pu, "execute", { scale: 1, x: 0, y: 0 });
    const puIcon = path(
      "M70 160 H180 V290 H70 Z M70 192 H180 M70 224 H180 M70 256 H180 M180 190 H238 V208 H270 M180 258 H250 V248 H276 M270 180 H298 L310 195 L322 180 H365 L350 285 H285 Z M315 285 V322 H45 V176 H70",
      { class: "processing-block-icon" },
      pu,
    );
    show(puIcon, "addressed-memory", "execute", {}, 0.55);
    const puName = label(ports, 51.6, 61, "PU", {
      class: "processing-block-name",
    });
    show(puName, "addressed-memory", "execute", {}, 0.35);
    const puDetail = group({ "data-part": "fetched-processing-detail" }, pu);
    key(puDetail, "execute", {}, null, 0.4);
    label(puDetail, 220, 208, "processing unit");
    for (const [y, name] of [
      [222, "R0"],
      [266, "R3"],
    ]) {
      rect(puDetail, 40, y, 120, 32);
      if (name === "R0") capture(puDetail, "r0", 41, y + 1, 118, 30);
      bit(puDetail, 65, y + 22, name);
    }
    const r0Value = bit(puDetail, 135, 244, "9", { "data-fetch-value": "r0" });
    bit(puDetail, 135, 288, "2");
    path("M306 218 H329 L337 230 L345 218 H368 L357 303 H317 Z", {}, puDetail);
    label(puDetail, 337, 257, "ALU");
    const addMode = bit(puDetail, 337, 275, "ADD", { class: "tiny bit" });
    const inputRoutes = [
      route("r0-alu", "M160 238 H230 V242 H309.106", "execute"),
      route("r3-alu", "M160 282 H240 V266 H312.212", "execute"),
    ];
    const resultRoute = route(
      "alu-r0",
      "M337 303 V312 H30 V238 H40",
      "execute",
    );
    for (const item of [...inputRoutes, resultRoute])
      puDetail.appendChild(item.base);
    for (const item of [...inputRoutes, resultRoute])
      puDetail.appendChild(item.lit);

    const easePu = gsap.parseEase("power2.inOut");
    afterRender.push(() => {
      const p = tl.time();
      if (
        p <= index("instruction-fetch") + hold ||
        p >= index("execute") - hold
      )
        return;
      const progress = (p - index("instruction-fetch") - hold) / (1 - 2 * hold);
      const slide = easePu(clamp(progress / 0.45));
      const grow = easePu(clamp((progress - 0.45) / 0.55));
      const scale = 0.18 + 0.82 * grow;
      gsap.set(pu, {
        scale,
        x: 15.15 + (20 - 15.15) * slide - (3 + 17 * grow) * scale,
        y: 10.38 + (190 - 10.38) * slide - (91 + 99 * grow) * scale,
      });
      for (const frame of [puTint, puFrame]) {
        frame.setAttribute("x", 3 + 17 * grow);
        frame.setAttribute("y", 91 + 99 * grow);
        frame.setAttribute("width", 405 - 5 * grow);
        frame.setAttribute("height", 316 - 181 * grow);
        frame.setAttribute("rx", 8 - 4 * grow);
      }
    });

    const cu = group({ "data-part": "fetch-control-unit" }, ports);
    rect(cu, 248, 118, 154, 40);
    label(cu, 325, 132, "controller", { class: "tiny" });
    const decoded = bit(cu, 325, 150, "ADD R0 R0 R3", {
      class: "fetch-bits bit",
    });
    show(cu, "execute", undefined);
    const decodeRoute = route("ir-cu", "M325 96 V118", "execute");
    const controlWires = group({}, wires);
    key(controlWires, "execute", {}, null, 0.85);
    const controlRoute = path(
      "M290 158 V184 H200 V190",
      { class: "control-wire" },
      controlWires,
    );
    const saveRoute = path(
      "M270 158 V174 H100 V222",
      { class: "control-wire" },
      controlWires,
    );
    const modeRoute = path(
      "M402 138 H430 V274 H360.753",
      { class: "control-wire" },
      controlWires,
    );
    const states = group({ "data-part": "sequencer" }, cu);
    const stateTints = ["fetch", "decode", "execute"].map((name, i) => {
      const tint = rect(states, 254 + i * 47, 136, 44, 18, "computer-glow");
      label(states, 276 + i * 47, 149, name, { class: "tiny" });
      return tint;
    });
    show(states, "control", undefined);
    show(decoded, "execute", "control");
    const clock = group({ "data-part": "sequencing-clock" }, ports);
    mk("circle", { cx: 168, cy: 142, r: 4, class: "computer-glow" }, clock);
    const clockPulse = mk(
      "circle",
      { cx: 168, cy: 142, r: 4, class: "fetch-clock-pulse" },
      clock,
    );
    label(clock, 204, 160, "clock", { class: "tiny" });
    path("M172 142 H248", { class: "thin muted" }, clock);
    show(clock, "control", undefined);
    const status = label(diagram, 233, 8, "", {
      class: "fetch-phase caption",
      "data-fetch-phase": "",
    });
    show(status, "addressed-memory", "computer");
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
      const rightAligned = String(content).length > 8 && point.x > 350;
      node.setAttribute("text-anchor", rightAligned ? "end" : "middle");
      const x = node === flying[0] ? Math.max(26, point.x) : point.x;
      node.setAttribute("x", x - (rightAligned ? 10 : 0));
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
      setText(mdrValue, state.mdr?.replaceAll(" ", "") ?? "—");
      setText(irValue, state.ir?.replaceAll(" ", "") ?? "—");
      setText(r0Value, state.r0);
      for (const [name, tint] of Object.entries(captures))
        tint.style.opacity = scene ? String(state.captures[name]) : "0";
      diagram.setAttribute(
        "data-fetch-pc",
        stage === "program" ? PROGRAM_START : state.pc,
      );
      diagram.setAttribute("data-fetch-r0", state.r0);
      diagram.setAttribute(
        "data-fetch-memory-ready",
        String(state.memoryReady),
      );
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
        0.35 + (executing ? 0.5 * during(elapsed, 6.4, 10.7) : 0),
      );
      modeRoute.style.opacity = String(
        0.35 + (executing ? 0.6 * during(elapsed, 7.6, 8.6) : 0),
      );
      saveRoute.style.opacity = String(
        0.35 + (executing ? 0.65 * during(elapsed, 10.1, 10.7) : 0),
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
                : state.waitingForMemory
                  ? "waiting for memory"
                  : elapsed < 3.4
                    ? "instruction ready in MDR"
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
        INSTRUCTION_BITS.replaceAll(" ", ""),
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
    const controllerDemo = buildControllerScene({
      diagram,
      root,
      tl,
      hold,
      index,
      group,
      mk,
      path,
      text,
      show,
      afterRender,
    });
    return {
      demos: [demo, controllerDemo],
      handoff: { diagram, memory, programNames, pu, puName, signals },
    };
  },
};
