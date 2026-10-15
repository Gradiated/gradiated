import assert from "node:assert/strict";
import test from "node:test";
import {
  MEMORY_MODEL,
  REGISTER_MODEL,
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
