import { gsap } from "gsap";
import {
  CONTROLLER_CYCLE_DURATION,
  CONTROLLER_GATES,
  CONTROLLER_OUTPUTS,
  controllerFrame,
} from "./instruction-cycle-model.js";

export const buildControllerScene = ({
  root,
  tl,
  hold,
  index,
  group,
  mk,
  path,
  text,
  afterRender,
  diagram,
  controls,
}) => {
  const scene = group({ "data-diagram": "controller-internals" }, root);
  const contents = group({}, scene, "0 0");
  const clamp = (value) => Math.max(0, Math.min(1, value));
  const ease = (value) => value * value * (3 - 2 * value);
  const mix = (a, b, amount) => a + (b - a) * amount;
  const label = (x, y, value, className = "fetch-phase") =>
    text(x, y, value, { class: className }, contents);
  const wire = (d) => path(d, {}, contents);
  const signal = (d, bus = false) => {
    path(d, bus ? { class: "interface-bus" } : {}, contents);
    return path(d, { class: "computer-signal" }, contents);
  };
  const arrow = (
    d,
    x,
    y,
    rotation = 0,
    { highlighted = false, bus = false } = {},
  ) => {
    const shaft = highlighted ? signal(d, bus) : wire(d);
    path(
      "M-5 -3 L0 0 L-5 3",
      { transform: `translate(${x} ${y}) rotate(${rotation})` },
      contents,
    );
    return shaft;
  };
  const box = (x, y, width, height) =>
    mk("rect", { x, y, width, height, rx: 3, class: "memory-box" }, contents);
  const setText = (node, value) => {
    if (node.textContent !== String(value)) node.textContent = String(value);
  };

  const zoomFrame = mk(
    "rect",
    {
      x: 12,
      y: 42,
      width: 416,
      height: 370,
      rx: 6,
      class: "fetch-control-frame",
    },
    scene,
  );
  scene.insertBefore(zoomFrame, contents);
  label(220, 27, "Inside the controller", "caption");
  const stateTints = [
    [116, 72, "Request instruction"],
    [324, 72, "Wait for memory"],
    [324, 148, "Copy MDR to IR"],
    [116, 148, "Execute ADD"],
  ].map(([x, y, name], state) => {
    const card = group({ "data-controller-step": state }, contents);
    const tint = mk(
      "rect",
      {
        x: x - 56,
        y,
        width: 112,
        height: 44,
        rx: 3,
        class: "computer-glow",
      },
      card,
    );
    text(
      x,
      y + 13,
      state.toString(2).padStart(2, "0"),
      { class: "bit tiny" },
      card,
    );
    text(x, y + 31, name, { class: "fetch-phase" }, card);
    return { card, tint };
  });
  arrow("M178 94 H262", 262, 94);
  arrow("M324 120 V142", 324, 142, 90);
  arrow("M262 170 H178", 178, 170, 180);
  arrow("M116 142 V120", 116, 120, -90);
  const waitingLoop = arrow(
    "M306 67 V63 C306 44 342 44 342 63 V67",
    342,
    67,
    90,
    { highlighted: true },
  );

  box(39, 270, 92, 80);
  label(85, 293, "State register");
  const stateCapture = mk(
    "rect",
    {
      x: 40,
      y: 271,
      width: 90,
      height: 78,
      rx: 3,
      class: "computer-glow",
      "data-register-capture": "state",
      opacity: 0,
    },
    contents,
  );
  const stateBits = label(85, 322, "00", "bit");
  box(184, 242, 102, 122);
  const circuitTransform = { x: 185, y: 243, scale: 0.196 };
  const readyPort = { x: 235, y: 242 };
  const circuit = group(
    {
      opacity: 0.13,
      class: "thin",
      transform: `translate(${circuitTransform.x} ${circuitTransform.y}) scale(${circuitTransform.scale})`,
      "data-controller-circuit": "",
      "aria-hidden": "true",
    },
    contents,
  );
  const circuitWires = group({}, circuit);
  const circuitGates = group({}, circuit);
  const positions = {
    n1: [40, 90],
    n0: [40, 290],
    notReady: [40, 500],
    request: [170, 75],
    wait: [170, 215],
    copy: [170, 355],
    execute: [170, 495],
    hold: [290, 185],
    advance: [290, 375],
    next0: [410, 155],
    next1: [410, 415],
  };
  const terminals = {
    s1: [16, 90],
    s0: [16, 290],
    ready: [24, 500],
  };
  const rails = {
    s1: [100, 58],
    n1: [120, 90],
    s0: [140, 258],
    n0: [160, 290],
    ready: [270, 440],
    notReady: [280, 548],
    request: [350, 75],
    wait: [250, 215],
    copy: [390, 290],
    execute: [244, 537],
    hold: [370, 185],
    advance: [370, 375],
    next0: [478, 155],
    next1: [470, 415],
  };
  const route = (d) => path(d, {}, circuitWires);
  for (const [id, operation, inputs] of CONTROLLER_GATES) {
    const [x, y] = positions[id];
    const gate = group(
      { transform: `translate(${x} ${y})`, "data-gate": id },
      circuitGates,
    );
    if (operation === "NOT") {
      path("M0 -16 L26 0 L0 16 Z", {}, gate);
      mk("circle", { cx: 30, cy: 0, r: 4 }, gate);
    } else if (operation === "AND") {
      path("M0 -24 H24 A24 24 0 0 1 24 24 H0 Z", {}, gate);
    } else {
      path("M0 -24 Q16 0 0 24 Q32 24 48 0 Q32 -24 0 -24 Z", {}, gate);
    }
    inputs.forEach((input, i) => {
      const dy = inputs.length === 1 ? 0 : (i * 24) / (inputs.length - 1) - 12;
      const inset = operation === "OR" ? (dy === 0 ? 8 : 6) : 0;
      const [sx, sy] = operation === "NOT" ? terminals[input] : rails[input];
      route(`M${sx} ${sy} V${y + dy} H${x + inset}`);
    });
    terminals[id] = [x + (operation === "NOT" ? 34 : 48), y];
  }
  for (const name of ["s1", "s0", "ready"]) {
    const [sx, sy] = terminals[name];
    const [rx, ry] = rails[name];
    route(`M${sx} ${sy} H28 V${ry} H${rx}`);
  }
  for (const name of [
    "n1",
    "n0",
    "request",
    "wait",
    "hold",
    "advance",
    "next0",
    "next1",
  ]) {
    const [sx, sy] = terminals[name];
    const [rx, ry] = rails[name];
    route(`M${sx} ${sy} H${rx} V${ry}`);
  }
  route("M74 500 H140 V548 H280");
  route("M218 355 H232 V290 H390");
  route("M218 495 H244 V537");
  for (const [name, y, lane] of [
    ["s1", 338, 4],
    ["s0", 346, 10],
  ]) {
    const [x, sy] = terminals[name];
    route(`M0 ${y} H${lane} V${sy} H${x}`);
  }
  const readyInputX =
    (readyPort.x - circuitTransform.x) / circuitTransform.scale;
  const readyInputY =
    (readyPort.y - circuitTransform.y) / circuitTransform.scale;
  route(`M${readyInputX} ${readyInputY} V40 H24 V500`);
  for (const [output, y, lane] of [
    ["request", 127, 488],
    ["send", 270, 496],
    ["load", 413, 496],
    ["processing", 556, 502],
  ]) {
    const [sx, sy] = rails[CONTROLLER_OUTPUTS[output]];
    route(`M${sx} ${sy} H${lane} V${y} H515`);
  }
  for (const [output, x, y] of [
    ["next1", 251, 584],
    ["next0", 259, 596],
  ]) {
    const [sx, sy] = rails[CONTROLLER_OUTPUTS[output]];
    route(`M${sx} ${sy} V${y} H${x} V617`);
  }
  const gateLabels = group({ "data-part": "controller-gate-labels" }, contents);
  text(
    235,
    303,
    "Logic gates",
    {
      class: "fetch-phase",
      "dominant-baseline": "central",
    },
    gateLabels,
  );

  const statePath = arrow("M131 310 H184", 184, 310, 0, {
    highlighted: true,
    bus: true,
  });
  const feedbackPath = arrow(
    "M235 364 V376 Q235 386 225 386 H35 Q25 386 25 376 V344 Q25 334 35 334 H39",
    39,
    334,
    0,
    { highlighted: true, bus: true },
  );
  path("M155 314 L161 306 M205 390 L211 382", {}, contents);
  label(158, 300, "2", "fetch-phase bit");
  label(208, 402, "2", "fetch-phase bit");
  const nextBits = label(133, 377, "next step 01", "fetch-phase bit");

  wire("M85 245 V270 M81 270 L85 276 L89 270");
  label(85, 235, "clock");
  const clock = mk(
    "circle",
    { cx: 85, cy: 245, r: 4, class: "fetch-clock-pulse" },
    contents,
  );
  const readyPath = signal(`M-20 218 H${readyPort.x} V${readyPort.y}`);
  const readyValue = label(196, 208, "READY 0", "fetch-phase bit");
  const memoryPath = signal("M286 268 H460");
  const sendPath = signal("M286 296 H460");
  const savePath = signal("M286 324 H460");
  const processingPath = signal("M286 352 H460");
  label(357, 258, "request memory");
  label(357, 286, "send MDR");
  label(357, 314, "load IR");
  label(357, 342, "control the PU");

  const time = { value: 0 };
  const demo = gsap.timeline({ paused: true, repeat: -1 }).to(time, {
    value: CONTROLLER_CYCLE_DURATION,
    duration: CONTROLLER_CYCLE_DURATION,
    ease: "none",
  });
  let started = false;
  afterRender.push(() => {
    const position = tl.time();
    const span = 1 - 2 * hold;
    const entering = clamp((position - index("controller") + 1 - hold) / span);
    const leaving = clamp((position - index("computer") + 1 - hold) / span);
    const openness = ease(entering) * (1 - ease(leaving));
    const inView = entering > 0 && leaving < 1;
    scene.style.opacity = inView ? "1" : "0";
    if (inView) {
      const scaleX = Number(gsap.getProperty(diagram, "scaleX"));
      const scaleY = Number(gsap.getProperty(diagram, "scaleY"));
      const x = Number(gsap.getProperty(diagram, "x"));
      const y = Number(gsap.getProperty(diagram, "y"));
      const small = {
        x: 248 * scaleX + x,
        y: 118 * scaleY + y,
        width: 154 * scaleX,
        height: 40 * scaleY,
      };
      const expanded = { x: 12, y: 42, width: 416, height: 370 };
      for (const attribute of ["x", "y", "width", "height"])
        zoomFrame.setAttribute(
          attribute,
          mix(small[attribute], expanded[attribute], openness),
        );
      const scale = mix(
        Math.min(small.width / 416, small.height / 370),
        1,
        openness,
      );
      gsap.set(contents, {
        scale,
        x: mix(small.x + small.width / 2, 220, openness) - 220 * scale,
        y: mix(small.y + small.height / 2, 227, openness) - 227 * scale,
        opacity: clamp((openness - 0.12) / 0.45),
      });
      const backgroundOpacity = String(
        leaving > 0
          ? ease(clamp((leaving - 0.65) / 0.35))
          : 1 - ease(clamp(entering / 0.35)),
      );
      diagram.style.opacity = backgroundOpacity;
    }
    const visible = Math.abs(position - index("controller")) <= hold;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (visible && !reduced) {
      if (!started) {
        demo.restart();
        started = true;
      } else demo.play();
    } else demo.pause();
    const elapsed =
      time.value +
      (demo.totalTime() >= CONTROLLER_CYCLE_DURATION
        ? CONTROLLER_CYCLE_DURATION
        : 0);
    const frame = controllerFrame(reduced ? 13 : elapsed);
    stateCapture.style.opacity =
      visible && !reduced ? String(frame.captures.state) : "0";
    setText(stateBits, frame.bits);
    setText(nextBits, `next step ${frame.nextBits}`);
    setText(readyValue, `READY ${Number(frame.ready)}`);
    if (inView) controls.update("controller", {}, 0);
    stateTints.forEach(({ card, tint }, state) => {
      const active = state === frame.state;
      card.setAttribute("data-active", String(active));
      tint.style.opacity = active ? "0.65" : "0";
    });
    for (const [node, active] of [
      [waitingLoop, frame.step === "wait" && !frame.ready],
      [statePath, true],
      [feedbackPath, true],
      [readyPath, frame.ready],
      [memoryPath, frame.request],
      [sendPath, frame.copy],
      [savePath, frame.copy],
      [processingPath, frame.processing],
    ])
      node.style.opacity = active ? "0.8" : "0";
    clock.style.opacity = visible && !reduced ? String(frame.clock) : "0";
    scene.setAttribute("data-controller-state", frame.bits);
    scene.setAttribute("data-controller-step", frame.step);
    scene.setAttribute("data-controller-ready", String(frame.ready));
    scene.setAttribute("data-controller-copy", String(frame.copy));
    scene.setAttribute("data-controller-captured", String(frame.captured));
  });
  return demo;
};
