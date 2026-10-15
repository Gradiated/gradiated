import assert from "node:assert/strict";
import test from "node:test";
import { MEMORY_MODEL } from "../src/components/articles/sand/runtime/memory-model.js";

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
