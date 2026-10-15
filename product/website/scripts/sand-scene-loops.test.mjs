import assert from "node:assert/strict";
import test from "node:test";
import { syncSceneLoops } from "../src/components/articles/sand/runtime/scene-loops.js";

const loopAt = (scene, initiallyPaused = true) => {
  const state = {
    paused: initiallyPaused,
    time: 0.4,
    starts: 0,
    resumes: 0,
    resets: 0,
  };
  const loop = {
    scene,
    tween: {
      paused: () => state.paused,
      pause: () => {
        state.paused = true;
      },
      restart: () => {
        state.starts += 1;
        state.time = 0;
        state.paused = false;
      },
      resume: () => {
        state.resumes += 1;
        state.paused = false;
      },
    },
    reset: () => {
      state.resets += 1;
      state.time = 0;
    },
  };
  return { loop, state };
};

test("reduced motion never starts a scene loop and stops loops already moving", () => {
  const initial = loopAt(7);
  const running = loopAt(8, false);
  const suspended = new Set();
  syncSceneLoops([initial.loop, running.loop], 7, false, true, suspended);
  assert.equal(initial.state.starts, 0);
  assert.equal(running.state.paused, true);
  assert.equal(running.state.resets, 1);
  assert.equal(running.state.time, 0);
});

test("normal motion starts only the settled matching scene and resets it on leaving", () => {
  const first = loopAt(7);
  const second = loopAt(8);
  const suspended = new Set();
  syncSceneLoops([first.loop, second.loop], 7, false, false, suspended);
  assert.equal(first.state.starts, 1);
  assert.equal(second.state.starts, 0);
  syncSceneLoops([first.loop, second.loop], 7.5, true, false, suspended);
  assert.equal(first.state.paused, true);
  assert.equal(first.state.resets, 1);
  assert.equal(second.state.starts, 0);
});

test("offscreen suspension resumes the existing playhead unless motion is reduced", () => {
  const demo = loopAt(7);
  const suspended = new Set([demo.loop.tween]);
  syncSceneLoops([demo.loop], 7, false, false, suspended);
  assert.equal(demo.state.time, 0.4);
  assert.equal(demo.state.resumes, 1);
  assert.equal(demo.state.starts, 0);
  assert.equal(suspended.size, 0);

  demo.state.paused = true;
  suspended.add(demo.loop.tween);
  syncSceneLoops([demo.loop], 7, false, true, suspended);
  assert.equal(demo.state.resets, 1);
  assert.equal(demo.state.resumes, 1);
  assert.equal(suspended.size, 0);
});
