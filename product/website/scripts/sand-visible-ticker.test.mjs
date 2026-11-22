import test from "node:test";
import assert from "node:assert/strict";
import { mountVisibleTicker } from "../../../hardware/publishing/sand-to-thought/articles/sand/figures/runtime/visible-ticker.js";

const setup = (visibilityState = "visible") => {
  let notify;
  let observed;
  let disconnected = false;
  let added = 0;
  let paused = 0;
  let rendered = 0;
  const callbacks = new Set();
  const page = new EventTarget();
  page.visibilityState = visibilityState;
  page.defaultView = {
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
  const cleanup = mountVisibleTicker(
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
  );

  return {
    element,
    cleanup,
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
