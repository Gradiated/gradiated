import test from "node:test";
import assert from "node:assert/strict";
import { SAND_PROGRESS } from "../src/components/articles/sand/runtime/scroll-progress.js";
const { progressAt } = SAND_PROGRESS;
const bounds = [
  { start: 100, end: 200, center: 150 },
  { start: 400, end: 500, center: 450 },
  { start: 700, end: 800, center: 750 },
  { start: 1000, end: 2100, center: 1550 },
  { start: 2400, end: 2500, center: 2450 },
];

test("protected opening scenes preserve centre-to-centre progress", () => {
  assert.equal(progressAt(bounds, 150), 0);
  assert.equal(progressAt(bounds, 300), 0.5);
  assert.equal(progressAt(bounds, 450), 1);
  assert.equal(progressAt(bounds, 750), 2);
  assert.equal(progressAt(bounds, 1550), 3);
});

test("a long passage stays on its illustration through its final line", () => {
  assert.equal(progressAt(bounds, 1600), 3);
  assert.equal(progressAt(bounds, 2099), 3);
  assert.equal(progressAt(bounds, 2100), 3);
});

test("transitions occupy the gap between passages and reverse identically", () => {
  assert.equal(progressAt(bounds, 2250), 3.5);
  assert.equal(progressAt(bounds, 2399), 3 + 299 / 300);
  assert.equal(progressAt(bounds, 2400), 4);
  assert.equal(progressAt(bounds, 2250), 3.5);
});

test("the final illustration is held through the closing text", () => {
  assert.equal(progressAt(bounds, 10000), 4);
  assert.equal(progressAt([], 100), 0);
});
