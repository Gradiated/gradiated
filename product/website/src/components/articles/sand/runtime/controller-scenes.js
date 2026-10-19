import { gsap } from "gsap";
import { controllerFrame } from "./instruction-cycle-model.js";

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
}) => {
  const scene = group({ "data-diagram": "controller-internals" }, root);
  const contents = group({}, scene, "0 0");
  const clamp = (value) => Math.max(0, Math.min(1, value));
  const ease = (value) => value * value * (3 - 2 * value);
  const mix = (a, b, amount) => a + (b - a) * amount;
  const label = (x, y, value, className = "tiny") =>
    text(x, y, value, { class: className }, contents);
  const wire = (d) => path(d, {}, contents);
  const signal = (d) => {
    wire(d);
    return path(d, { class: "computer-signal" }, contents);
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
      height: 308,
      rx: 6,
      class: "fetch-control-frame",
    },
    scene,
  );
  scene.insertBefore(zoomFrame, contents);
  label(220, 27, "Inside the controller", "caption");
  const stateNames = ["ready to copy", "copy to IR", "next step"];
  const stateTints = stateNames.map((name, i) => {
    const x = 112 + i * 100;
    const tint = mk(
      "rect",
      {
        x: x - 42,
        y: 57,
        width: 84,
        height: 37,
        rx: 3,
        class: "computer-glow",
      },
      contents,
    );
    label(x, 71, ["00", "01", "10"][i], "bit tiny");
    label(x, 86, name);
    return tint;
  });
  wire(
    "M155 76 H168 M162 72 L168 76 L162 80 M255 76 H268 M262 72 L268 76 L262 80",
  );

  label(121, 137, "next state");
  label(228, 137, "current state");
  label(351, 137, "control signals");

  const stateOnePath = signal(
    "M266 206 H278 V112 H32 V198 H72.414 M278 206 H290",
  );
  const stateZeroPath = signal("M266 254 H278 V314 H32 V214 H72.414");
  wire("M68 188 Q79 206 68 224 Q100 224 110 206 Q100 188 68 188 Z");
  wire("M72 243 L92 254 L72 265 Z");
  mk("circle", { cx: 96, cy: 254, r: 3, class: "memory-box" }, contents);
  const nextOnePath = signal("M110 206 H190 M122 206 V232 H54 V254 H72");
  const nextZeroPath = signal("M99 254 H190");
  const nextOne = label(172, 194, "0", "bit");
  const nextZero = label(172, 242, "1", "bit");

  box(190, 178, 76, 108);
  const stateCapture = mk(
    "rect",
    {
      x: 191,
      y: 179,
      width: 74,
      height: 106,
      rx: 3,
      class: "computer-glow",
      "data-register-capture": "state",
      opacity: 0,
    },
    contents,
  );
  label(208, 206, "S1", "bit");
  label(208, 254, "S0", "bit");
  const s1 = label(246, 206, "0", "bit");
  const s0 = label(246, 254, "0", "bit");
  wire("M228 163 V178 M224 178 L228 184 L232 178");
  const clock = mk(
    "circle",
    { cx: 228, cy: 165, r: 4, class: "fetch-clock-pulse" },
    contents,
  );
  label(228, 155, "clock");
  wire("M290 195 L308 206 L290 217 Z");
  mk("circle", { cx: 312, cy: 206, r: 3, class: "memory-box" }, contents);
  const invertedPath = signal("M315 206 H326");
  const directPath = signal("M278 254 H326");
  wire("M326 194 H338 A36 36 0 0 1 338 266 H326 Z");
  label(351, 168, "detects 01");
  const enable = label(391, 248, "0", "bit");
  const sendPath = signal("M374 230 H460");
  const savePath = signal("M380 230 V314 H460");
  label(400, 218, "send MDR");
  label(407, 302, "load IR");
  for (const [cx, cy] of [
    [278, 206],
    [278, 254],
    [122, 206],
    [380, 230],
  ])
    mk("circle", { cx, cy, r: 1.5, class: "dot" }, contents);

  const status = label(220, 377, "Instruction ready in MDR");
  const time = { value: 0 };
  const demo = gsap
    .timeline({ paused: true, repeat: -1 })
    .to(time, { value: 12, duration: 12, ease: "none" });
  let active = false;
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
      const expanded = { x: 12, y: 42, width: 416, height: 308 };
      for (const attribute of ["x", "y", "width", "height"])
        zoomFrame.setAttribute(
          attribute,
          mix(small[attribute], expanded[attribute], openness),
        );
      const scale = mix(
        Math.min(small.width / 416, small.height / 308),
        1,
        openness,
      );
      gsap.set(contents, {
        scale,
        x: mix(small.x + small.width / 2, 220, openness) - 220 * scale,
        y: mix(small.y + small.height / 2, 196, openness) - 196 * scale,
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
    if (visible && !active) demo.restart();
    if (!visible) demo.pause();
    active = visible;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (visible && !reduced) demo.play();
    else demo.pause();
    const frame = controllerFrame(reduced ? 4 : time.value);
    stateCapture.style.opacity =
      visible && !reduced ? String(frame.captures.state) : "0";
    setText(s1, frame.s1);
    setText(s0, frame.s0);
    setText(nextOne, frame.next1);
    setText(nextZero, frame.next0);
    setText(enable, Number(frame.copy));
    setText(
      status,
      frame.captured
        ? "Instruction captured in IR"
        : frame.copy
          ? "MDR → IR enabled"
          : "Instruction ready in MDR",
    );
    stateTints.forEach((node, i) => {
      node.style.opacity = i === frame.state ? "0.65" : "0";
    });
    for (const [node, value] of [
      [stateOnePath, frame.s1],
      [stateZeroPath, frame.s0],
      [nextOnePath, frame.next1],
      [nextZeroPath, frame.next0],
      [invertedPath, 1 - frame.s1],
      [directPath, frame.s0],
      [sendPath, frame.copy],
      [savePath, frame.copy],
    ])
      node.style.opacity = value ? "0.8" : "0";
    const tick = Math.abs((time.value % 4) - 2);
    clock.style.opacity =
      visible && !reduced ? String(Math.max(0, 1 - tick / 0.2)) : "0";
    scene.setAttribute(
      "data-controller-state",
      frame.state.toString(2).padStart(2, "0"),
    );
    scene.setAttribute("data-controller-copy", String(frame.copy));
    scene.setAttribute("data-controller-captured", String(frame.captured));
  });
  return demo;
};
