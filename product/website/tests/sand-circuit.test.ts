import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { mountSandCircuit } from "../src/components/design/sand-circuit-animation";

const painter = vi.hoisted(() => ({
  render: vi.fn(() => true),
  resize: vi.fn(() => true),
}));
vi.mock("../src/components/design/sand-circuit-canvas", () => ({
  createSandCanvas: () => painter,
}));

let host: HTMLDivElement;
let trigger: EventTarget;
let page: EventTarget & { hidden: boolean };
let reduced: EventTarget & { matches: boolean };
let intersect: (entries: { isIntersecting: boolean }[]) => void;
let resizeObserver: {
  observe: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
};
let intersectionObserver: typeof resizeObserver;
let frames: Map<number, FrameRequestCallback>;
let nextFrame: number;
let stop: (() => void) | undefined;

beforeEach(() => {
  vi.clearAllMocks();
  frames = new Map();
  nextFrame = 0;
  trigger = new EventTarget();
  page = Object.assign(new EventTarget(), { hidden: false });
  reduced = Object.assign(new EventTarget(), { matches: false });
  host = Object.assign(new EventTarget(), {
    dataset: {},
    clientWidth: 600,
    clientHeight: 300,
    closest: () => trigger,
  }) as unknown as HTMLDivElement;
  resizeObserver = { observe: vi.fn(), disconnect: vi.fn() };
  intersectionObserver = { observe: vi.fn(), disconnect: vi.fn() };

  vi.stubGlobal("window", { matchMedia: () => reduced });
  vi.stubGlobal("document", page);
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    frames.set(++nextFrame, callback);
    return nextFrame;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => frames.delete(id));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor() {
        return resizeObserver;
      }
    },
  );
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(callback: typeof intersect) {
        intersect = callback;
        return intersectionObserver;
      }
    },
  );

  stop = mountSandCircuit(host, {} as HTMLCanvasElement);
});

afterEach(() => {
  stop?.();
  vi.unstubAllGlobals();
});

const tick = (time: number) => {
  const callbacks = [...frames.values()];
  frames.clear();
  callbacks.forEach((callback) => callback(time));
};

it("pauses offscreen and in hidden tabs, then resumes without resetting the morph", () => {
  expect(frames.size).toBe(0);
  intersect([{ isIntersecting: true }]);
  trigger.dispatchEvent(new Event("mouseenter"));
  tick(100);
  tick(150);
  const progress = host.dataset.morph;
  expect(Number(progress)).toBeGreaterThan(0);

  intersect([{ isIntersecting: false }]);
  expect(frames.size).toBe(0);
  intersect([{ isIntersecting: true }]);
  expect(frames.size).toBe(1);
  expect(host.dataset.morph).toBe(progress);

  page.hidden = true;
  tick(200);
  expect(frames.size).toBe(0);
  page.hidden = false;
  page.dispatchEvent(new Event("visibilitychange"));
  expect(frames.size).toBe(1);
});

it("honours reduced motion and supports keyboard focus independently of hover", () => {
  intersect([{ isIntersecting: true }]);
  trigger.dispatchEvent(new Event("focus"));
  trigger.dispatchEvent(new Event("mouseleave"));
  tick(100);
  tick(150);
  expect(Number(host.dataset.morph)).toBeGreaterThan(0);

  reduced.matches = true;
  reduced.dispatchEvent(new Event("change"));
  tick(200);
  expect(host.dataset.morph).toBe("0.000");
  expect(frames.size).toBe(0);
});

it("unmount removes listeners, observers and pending animation frames", () => {
  intersect([{ isIntersecting: true }]);
  stop?.();
  stop = undefined;
  painter.render.mockClear();

  trigger.dispatchEvent(new Event("mouseenter"));
  trigger.dispatchEvent(new Event("focus"));
  page.dispatchEvent(new Event("visibilitychange"));
  reduced.dispatchEvent(new Event("change"));

  expect(frames.size).toBe(0);
  expect(painter.render).not.toHaveBeenCalled();
  expect(resizeObserver.disconnect).toHaveBeenCalledOnce();
  expect(intersectionObserver.disconnect).toHaveBeenCalledOnce();
});

it("keeps sweeping the network after the hover morph finishes and freezes its clock offscreen", () => {
  intersect([{ isIntersecting: true }]);
  trigger.dispatchEvent(new Event("mouseenter"));
  for (let time = 100; time <= 4100; time += 50) tick(time);

  expect(host.dataset.morph).toBe("1.000");
  expect(frames.size).toBe(1);
  const before = painter.render.mock.calls.at(-1) as unknown as number[];
  tick(4150);
  const after = painter.render.mock.calls.at(-1) as unknown as number[];
  expect(after[2]).toBeGreaterThan(before[2]);

  intersect([{ isIntersecting: false }]);
  intersect([{ isIntersecting: true }]);
  tick(20000);
  const resumed = painter.render.mock.calls.at(-1) as unknown as number[];
  expect(resumed[2]).toBe(after[2]);
});
