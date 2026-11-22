import assert from "node:assert/strict";
import test from "node:test";
import {
  createMemoryAccessModel,
  MEMORY_ACCESS_DURATION,
} from "../../../hardware/publishing/sand-to-thought/articles/sand/figures/runtime/memory-access-model.js";

test("the interface holds its values until the register capture", () => {
  const model = createMemoryAccessModel();
  model.choose("Write");
  const before = model.frame(0.8);
  assert.equal(before.mar, 0);
  assert.equal(before.mdr, 0);
  assert.equal(before.we, 0);
  const captured = model.frame(1);
  assert.equal(captured.mar, 1);
  assert.equal(captured.mdr, 9);
  assert.equal(captured.words[1], 6);
});

test("writing updates only the addressed location after the transfer", () => {
  const model = createMemoryAccessModel();
  model.choose("Write");
  assert.equal(model.frame(2).we, 1);
  assert.deepEqual(model.frame(2).words, [3, 6, null, 0]);
  const done = model.frame(MEMORY_ACCESS_DURATION);
  assert.deepEqual(done.words, [3, 9, null, 0]);
  assert.equal(done.we, 0);
  assert.equal(done.busy, false);
});

test("reading waits for data before capturing MDR and leaves memory unchanged", () => {
  const model = createMemoryAccessModel();
  model.choose("Read");
  assert.equal(model.frame(1).mar, 1);
  assert.equal(model.frame(2).transfer.kind, "Read");
  assert.equal(model.frame(2.9).mdr, 0);
  const done = model.frame(MEMORY_ACCESS_DURATION);
  assert.equal(done.mdr, 6);
  assert.equal(done.we, 0);
  assert.deepEqual(done.words, [3, 6, null, 0]);
});

test("a read after a write returns the new stored value", () => {
  const model = createMemoryAccessModel();
  model.choose("Write");
  model.frame(MEMORY_ACCESS_DURATION);
  model.choose("Read");
  const transfer = model.frame(2).transfer;
  assert.equal(transfer.value, 9);
  assert.equal(model.frame(MEMORY_ACCESS_DURATION).mdr, 9);
});

test("the clock capture and write enable are independent controls", () => {
  const model = createMemoryAccessModel();
  model.choose("Read");
  assert.equal(model.frame(0.95).clock, true);
  assert.equal(model.frame(0.95).we, 0);
  assert.equal(model.frame(3.15).clock, true);
  model.frame(MEMORY_ACCESS_DURATION);
  model.choose("Write");
  assert.equal(model.frame(1.8).we, 1);
  assert.equal(model.frame(1.8).clock, false);
});
