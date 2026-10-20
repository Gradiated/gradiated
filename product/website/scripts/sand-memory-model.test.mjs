import assert from "node:assert/strict";
import test from "node:test";
import {
  createMemoryDemo,
  createAdderMemoryDemo,
  ADDER_MEMORY_DURATION,
  MEMORY_TRANSFER_DURATION,
  REGISTER_MODEL,
  createLatchModel,
  dataChangePulse,
} from "../src/components/articles/sand/runtime/memory-model.js";

test("memory stays still until a reader chooses an action", () => {
  const model = createMemoryDemo();
  const initial = model.frame();
  assert.deepEqual(model.frame(120), initial);
  assert.equal(initial.busy, false);
  assert.equal(initial.transfer, null);
});

test("reading every address copies its word without changing memory", () => {
  for (const words of [
    [3, 6],
    [3, 6, 0, 15],
  ]) {
    const model = createMemoryDemo(words);
    for (let address = 0; address < words.length; address++) {
      model.choose("Read", address);
      const moving = model.frame(MEMORY_TRANSFER_DURATION / 2);
      assert.equal(moving.we, 0);
      assert.equal(moving.transfer.kind, "Read");
      assert.equal(moving.transfer.value, words[address]);
      assert.deepEqual(moving.words, words);
      const settled = model.frame(MEMORY_TRANSFER_DURATION);
      assert.equal(settled.output, words[address]);
      assert.deepEqual(settled.words, words);
      assert.equal(settled.busy, false);
    }
  }
});

test("writing every address updates only that row after the digits arrive", () => {
  for (const words of [
    [3, 6],
    [3, 6, 0, 15],
  ]) {
    for (let address = 0; address < words.length; address++) {
      const model = createMemoryDemo(words);
      model.choose("Write", address);
      const moving = model.frame(MEMORY_TRANSFER_DURATION / 2);
      assert.equal(moving.we, 1);
      assert.equal(moving.transfer.kind, "Write");
      assert.equal(moving.transfer.value, 9);
      assert.deepEqual(moving.words, words);
      const expected = words.map((word, row) => (row === address ? 9 : word));
      const settled = model.frame(MEMORY_TRANSFER_DURATION);
      assert.deepEqual(settled.words, expected);
      assert.equal(settled.output, 9);
      assert.equal(settled.we, 1);
      assert.equal(settled.transfer, null);
      assert.deepEqual(model.frame(120), settled);
      assert.deepEqual(words, words.length === 2 ? [3, 6] : [3, 6, 0, 15]);
    }
  }
});

test("reading elsewhere and replaying actions preserve earlier writes", () => {
  const model = createMemoryDemo();
  model.choose("Write", 1);
  model.frame(MEMORY_TRANSFER_DURATION);
  model.choose("Read", 0);
  assert.equal(model.frame(MEMORY_TRANSFER_DURATION).output, 3);
  model.choose("Read", 1);
  assert.equal(model.frame(MEMORY_TRANSFER_DURATION).output, 9);
  model.choose("Write", 1);
  assert.equal(model.frame(0.6).transfer.value, 9);
  assert.deepEqual(model.frame(MEMORY_TRANSFER_DURATION).words, [3, 9, 0, 0]);
});

test("expanding memory retains existing rows and adds empty locations", () => {
  const small = createMemoryDemo([3, 6]);
  small.choose("Write", 0);
  const words = small.frame(MEMORY_TRANSFER_DURATION).words;
  const large = createMemoryDemo([...words, 0, 0]);
  assert.deepEqual(large.frame().words, [9, 6, 0, 0]);
});

test("the adder writes address 01 then reads the same stored answer", () => {
  const model = createAdderMemoryDemo([3, 6, 0, 15]);
  assert.equal(model.frame(0.4).we, 0);
  assert.equal(model.frame(0.4).transfer, null);
  const writing = model.frame(1.4);
  assert.equal(writing.we, 1);
  assert.equal(writing.address, 1);
  assert.equal(writing.transfer.kind, "Write");
  assert.deepEqual(writing.words, [3, 6, 0, 15]);
  const reading = model.frame(3.2);
  assert.equal(reading.we, 0);
  assert.equal(reading.address, 1);
  assert.equal(reading.transfer.kind, "Read");
  assert.equal(reading.transfer.value, 9);
  assert.deepEqual(reading.words, [3, 9, 0, 15]);
  const held = model.frame(ADDER_MEMORY_DURATION);
  assert.equal(held.action, "Read");
  assert.equal(held.output, 9);
  assert.equal(held.busy, false);
  assert.equal(held.transfer, null);
  assert.deepEqual(model.frame(120), held);
});

test("the adder sequence restarts from its seed independently of skipped frames", () => {
  const words = [12, 6, 0, 15];
  const model = createAdderMemoryDemo(words);
  const initial = model.frame(0);
  const settled = model.frame(ADDER_MEMORY_DURATION);
  assert.deepEqual(model.frame(0), initial);
  assert.deepEqual(createAdderMemoryDemo(words).frame(0), initial);
  assert.deepEqual(
    createAdderMemoryDemo(words).frame(ADDER_MEMORY_DURATION),
    settled,
  );
  assert.deepEqual(words, [12, 6, 0, 15]);
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
