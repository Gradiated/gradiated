import { createSandCanvas } from "./sand-circuit-canvas";

export const mountSandCircuit = (
  host: HTMLDivElement,
  canvas: HTMLCanvasElement,
): (() => void) => {
  const painter = createSandCanvas(canvas);
  if (!painter) return () => {};

  const trigger = host.closest<HTMLElement>(".sand-cover") ?? host;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let frame = 0;
  let progress = 0;
  let target = 0;
  let clock = 0;
  let networkClock = 0;
  let previous = 0;
  let visible = false;
  let hovered = false;
  let focused = false;

  const render = () => {
    if (!painter.render(progress, clock, networkClock)) return;

    host.dataset.morph = progress.toFixed(3);
    host.dataset.ready = "true";
  };

  const tick = (now: number) => {
    frame = 0;
    if (!visible || document.hidden) return;

    const elapsed = previous ? Math.min((now - previous) / 1000, 0.05) : 0;
    previous = now;
    clock += elapsed;
    if (target === 1 && progress > 0.92) networkClock += elapsed;
    progress += (target - progress) * (1 - Math.exp(-elapsed * 6.5));
    if (Math.abs(target - progress) < 0.001) progress = target;

    render();
    if (!reduced.matches) frame = requestAnimationFrame(tick);
  };
  const schedule = () => {
    if (frame || !visible || document.hidden) return;

    previous = 0;
    frame = requestAnimationFrame(tick);
  };
  const update = () => {
    target = reduced.matches ? 0 : Number(hovered || focused);
    if (progress === 0) networkClock = 0;
    if (reduced.matches) progress = 0;
    render();
    schedule();
  };
  const enter = () => {
    hovered = true;
    update();
  };
  const leave = () => {
    hovered = false;
    update();
  };
  const focus = () => {
    focused = true;
    update();
  };
  const blur = () => {
    focused = false;
    update();
  };
  const resize = () => {
    if (
      !painter.resize(
        Math.round(host.clientWidth),
        Math.round(host.clientHeight),
      )
    )
      return;

    render();
    schedule();
  };
  const observer = new ResizeObserver(resize);
  const intersection = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    if (visible) schedule();
    else {
      cancelAnimationFrame(frame);
      frame = 0;
    }
  });
  resize();
  observer.observe(host);
  intersection.observe(host);
  trigger.addEventListener("mouseenter", enter);
  trigger.addEventListener("mouseleave", leave);
  trigger.addEventListener("focus", focus);
  trigger.addEventListener("blur", blur);
  reduced.addEventListener("change", update);
  document.addEventListener("visibilitychange", schedule);

  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    intersection.disconnect();
    trigger.removeEventListener("mouseenter", enter);
    trigger.removeEventListener("mouseleave", leave);
    trigger.removeEventListener("focus", focus);
    trigger.removeEventListener("blur", blur);
    reduced.removeEventListener("change", update);
    document.removeEventListener("visibilitychange", schedule);
  };
};
