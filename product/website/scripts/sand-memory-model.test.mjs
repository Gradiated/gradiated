import assert from "node:assert/strict";
import test from "node:test";
import {
  MEMORY_MODEL,
  REGISTER_MODEL,
  createLatchModel,
  dataChangePulse,
} from "../src/components/articles/sand/runtime/memory-model.js";

test("read selection returns the addressed word without writing", () => {
  const first = MEMORY_MODEL.frame(1);
  const second = MEMORY_MODEL.frame(3);
  assert.equal(first.we, 0);
  assert.equal(first.output, 3);
  assert.equal(second.output, 6);
  assert.deepEqual(first.words, second.words);
});
test("a write changes only the selected four-bit word", () => {
  for (const rows of [2, 4]) {
    const before = MEMORY_MODEL.frame(4.5, rows);
    const during = MEMORY_MODEL.frame(6, rows);
    assert.equal(during.we, 1);
    assert.equal(during.words[during.address], during.input);
    assert.equal(during.output, 9);
    during.words.forEach((word, address) => {
      if (address !== during.address) assert.equal(word, before.words[address]);
    });
  }
});
test("disabling writing and reading elsewhere retain the stored answer", () => {
  const held = MEMORY_MODEL.frame(8);
  const elsewhere = MEMORY_MODEL.frame(11);
  assert.equal(held.we, 0);
  assert.equal(held.output, 9);
  assert.equal(elsewhere.address, 3);
  assert.equal(elsewhere.output, 0);
  assert.deepEqual(elsewhere.words, held.words);
});
test("a repeated animation never silently erases a stored word", () => {
  assert.deepEqual(
    MEMORY_MODEL.frame(11.999).words,
    MEMORY_MODEL.frame(12).words,
  );
  assert.deepEqual(MEMORY_MODEL.frame(36).words, [3, 6, 9, 0]);
});
test("expanding the array preserves the existing rows before writing the new row", () => {
  const small = MEMORY_MODEL.frame(8, 2);
  const bigger = MEMORY_MODEL.frame(0, 4, small.words);
  assert.deepEqual(bigger.words, small.words);
  const written = MEMORY_MODEL.frame(8, 4, bigger.words);
  assert.deepEqual(written.words, [3, 9, 9, 0]);
});

test("the register holds its outputs when disabled even as the input changes", () => {
  for (const [time, input, output] of [
    [0, 3, 3],
    [2, 12, 3],
    [10.5, 6, 9],
  ]) {
    const state = REGISTER_MODEL.frame(time);
    assert.equal(state.we, 0);
    assert.equal(state.input, input);
    assert.equal(state.output, output);
    assert.equal(state.transfer, null);
  }
});

test("the register transfers on enable and on data changes while still enabled", () => {
  for (const [start, from, to] of [
    [3, 3, 12],
    [6, 12, 9],
    [12, 9, 6],
    [14.5, 6, 3],
  ]) {
    const travelling = REGISTER_MODEL.frame(start + 0.45);
    assert.equal(travelling.we, 1);
    assert.equal(travelling.output, from);
    assert.equal(travelling.input, to);
    assert.deepEqual(travelling.transfer, {
      start,
      from,
      to,
      progress: (travelling.time - start) / REGISTER_MODEL.TRANSFER_DURATION,
    });
    const arrived = REGISTER_MODEL.frame(
      start + REGISTER_MODEL.TRANSFER_DURATION,
    );
    assert.equal(arrived.output, to);
    assert.equal(arrived.transfer, null);
  }
});

test("every register output update occurs while writing is enabled", () => {
  let previous = REGISTER_MODEL.frame(0).output;
  for (let tick = 1; tick <= 5400; tick++) {
    const state = REGISTER_MODEL.frame(tick / 100);
    if (state.output !== previous) assert.equal(state.we, 1);
    previous = state.output;
  }
});

test("the register repeats without silently resetting its stored bits", () => {
  assert.equal(
    REGISTER_MODEL.frame(17.999).output,
    REGISTER_MODEL.frame(18).output,
  );
  assert.deepEqual(REGISTER_MODEL.frame(2), REGISTER_MODEL.frame(38));
});

const latchModel = createLatchModel(
  [
    { time: 1, d: 1 },
    { time: 3, we: 0 },
    { time: 4, d: 0 },
    { time: 6, we: 1 },
    { time: 7.5, d: 1 },
    { time: 8, we: 0 },
  ],
  10,
);

test("the single latch flies a changed bit while enabled and settles before holding", () => {
  const moving = latchModel.frame(1.3);
  assert.equal(moving.we, 1);
  assert.equal(moving.d, 1);
  assert.equal(moving.q, 0);
  assert.equal(moving.transfer.to, 1);
  assert.equal(latchModel.frame(2).q, 1);
  const held = latchModel.frame(4.5);
  assert.equal(held.d, 0);
  assert.equal(held.q, 1);
  assert.equal(held.transfer, null);
});

test("enabling the latch copies a waiting input and another change copies while still enabled", () => {
  assert.equal(latchModel.frame(6.2).transfer.to, 0);
  assert.equal(latchModel.frame(6.8).q, 0);
  assert.equal(latchModel.frame(7.7).transfer.to, 1);
  assert.equal(latchModel.frame(8).q, 1);
  assert.equal(latchModel.frame(8).we, 0);
  assert.equal(latchModel.frame(8).transfer, null);
});

test("the single latch copies on repeat instead of silently resetting its held output", () => {
  assert.equal(latchModel.frame(9.999).q, latchModel.frame(10).q);
  assert.equal(latchModel.frame(10.3).transfer.to, 0);
  assert.equal(latchModel.frame(10.8).q, 0);
  for (let tick = 0; tick <= 3000; tick++) {
    const state = latchModel.frame(tick / 100);
    if (!state.we) assert.equal(state.transfer, null);
  }
});

test("data-change flashes fade away and do not restart for an unchanged input", () => {
  assert.equal(dataChangePulse(null), 0);
  assert.equal(dataChangePulse(0), 0);
  assert.equal(dataChangePulse(0.325), 1);
  assert.equal(dataChangePulse(0.65), 0);
  const model = createLatchModel([
    { time: 1, d: 1 },
    { time: 2, d: 1 },
    { time: 3, d: 0 },
  ]);
  assert.ok(dataChangePulse(model.frame(1.3).dataAge) > 0.9);
  assert.equal(dataChangePulse(model.frame(2.3).dataAge), 0);
  assert.ok(dataChangePulse(model.frame(3.3).dataAge) > 0.9);
});

test("register input flashes identify only the bits changed by the new input", () => {
  const change = REGISTER_MODEL.frame(6.325).inputChange;
  assert.equal(change.from ^ change.to, 0b0101);
  assert.ok(dataChangePulse(change.age) > 0.99);
  assert.equal(dataChangePulse(REGISTER_MODEL.frame(7).inputChange.age), 0);
  assert.equal(REGISTER_MODEL.frame(0).inputChange, null);
});
