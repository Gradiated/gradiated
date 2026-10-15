import test from "node:test";
import assert from "node:assert/strict";
import { mountVisibleTicker } from "../src/components/articles/sand/runtime/visible-ticker.js";

const setup = (visibilityState = "visible", reduced = false) => {
  let notify;
  let observed;
  let disconnected = false;
  let added = 0;
  let paused = 0;
  let rendered = 0;
  const callbacks = new Set();
  const frames = new Map();
  let nextFrame = 0;
  const motion = new EventTarget();
  motion.matches = reduced;
  const page = new EventTarget();
  page.visibilityState = visibilityState;
  page.defaultView = {
    requestAnimationFrame: (callback) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    },
    cancelAnimationFrame: (id) => frames.delete(id),
    IntersectionObserver: class {
      constructor(callback) {
        notify = callback;
      }
      observe(element) {
        observed = element;
      }
      disconnect() {
        disconnected = true;
      }
    },
  };
  const element = { ownerDocument: page };
  const rendering = mountVisibleTicker(
    element,
    {
      add: (callback) => {
        added += 1;
        callbacks.add(callback);
      },
      remove: (callback) => callbacks.delete(callback),
    },
    () => {
      rendered += 1;
    },
    () => {
      paused += 1;
    },
    motion,
  );

  return {
    element,
    cleanup: rendering.destroy,
    invalidate: rendering.invalidate,
    flush: () => {
      const pending = [...frames.values()];
      frames.clear();
      pending.forEach((callback) => callback());
    },
    motion: (matches) => {
      motion.matches = matches;
      motion.dispatchEvent(new Event("change"));
    },
    intersect: (isIntersecting, intersectionRatio = isIntersecting ? 1 : 0) =>
      notify([{ target: element, isIntersecting, intersectionRatio }]),
    visibility: (value) => {
      page.visibilityState = value;
      page.dispatchEvent(new Event("visibilitychange"));
    },
    tick: () => callbacks.forEach((callback) => callback()),
    get state() {
      return {
        added,
        paused,
        rendered,
        running: callbacks.size,
        pending: frames.size,
        observed,
        disconnected,
      };
    },
  };
};

test("offscreen stages do not render, including viewport edge contact", () => {
  const demo = setup();
  assert.equal(demo.state.observed, demo.element);
  demo.tick();
  demo.intersect(false);
  demo.intersect(true, 0);
  demo.tick();
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.rendered, 0);
  demo.cleanup();
});

test("entering resumes rendering once, leaving pauses, and re-entry resumes", () => {
  const demo = setup();
  demo.intersect(true);
  demo.intersect(true, 0.5);
  demo.tick();
  assert.equal(demo.state.added, 1);
  assert.equal(demo.state.rendered, 1);
  demo.intersect(false);
  demo.tick();
  assert.equal(demo.state.rendered, 1);
  assert.equal(demo.state.paused, 1);
  demo.intersect(true);
  demo.tick();
  assert.equal(demo.state.rendered, 2);
  assert.equal(demo.state.running, 1);
  demo.cleanup();
});

test("a hidden tab pauses and only resumes when both tab and stage are visible", () => {
  const demo = setup("hidden");
  demo.intersect(true);
  assert.equal(demo.state.running, 0);
  demo.visibility("visible");
  assert.equal(demo.state.running, 1);
  demo.visibility("hidden");
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.paused, 1);
  demo.intersect(false);
  demo.visibility("visible");
  assert.equal(demo.state.running, 0);
  demo.cleanup();
});

test("unmount disconnects observation and late callbacks cannot restart rendering", () => {
  const demo = setup();
  demo.intersect(true);
  demo.cleanup();
  assert.equal(demo.state.disconnected, true);
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.paused, 1);
  demo.intersect(true);
  demo.visibility("visible");
  demo.tick();
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.rendered, 0);
});

test("reduced motion renders once on entry and remains idle between changes", () => {
  const demo = setup("visible", true);
  demo.intersect(true);
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.pending, 1);
  demo.flush();
  assert.equal(demo.state.rendered, 1);
  demo.tick();
  demo.tick();
  assert.equal(demo.state.rendered, 1);
  assert.equal(demo.state.pending, 0);
  demo.cleanup();
});

test("reduced-motion invalidations coalesce and do not render hidden stages", () => {
  const demo = setup("visible", true);
  demo.intersect(true);
  demo.invalidate();
  demo.invalidate();
  assert.equal(demo.state.pending, 1);
  demo.flush();
  assert.equal(demo.state.rendered, 1);
  demo.invalidate();
  demo.visibility("hidden");
  demo.flush();
  demo.invalidate();
  assert.equal(demo.state.pending, 0);
  assert.equal(demo.state.rendered, 1);
  demo.visibility("visible");
  demo.flush();
  assert.equal(demo.state.rendered, 2);
  demo.cleanup();
});

test("changing the motion preference switches between static and continuous rendering", () => {
  const demo = setup();
  demo.intersect(true);
  demo.tick();
  demo.motion(true);
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.paused, 1);
  demo.flush();
  assert.equal(demo.state.rendered, 2);
  demo.motion(false);
  assert.equal(demo.state.running, 1);
  assert.equal(demo.state.pending, 0);
  demo.tick();
  assert.equal(demo.state.rendered, 3);
  demo.cleanup();
});

test("unmount cancels a pending static frame and ignores subsequent motion changes", () => {
  const demo = setup("visible", true);
  demo.intersect(true);
  demo.cleanup();
  demo.flush();
  demo.motion(false);
  demo.invalidate();
  assert.equal(demo.state.running, 0);
  assert.equal(demo.state.pending, 0);
  assert.equal(demo.state.rendered, 0);
});
