import assert from "node:assert/strict";
import test from "node:test";
import {
  INSTRUCTION_BITS,
  PROGRAM_START,
  instructionCycleFrame,
} from "../src/components/articles/sand/runtime/instruction-cycle-model.js";

test("the fetched bits encode the same ADD R0 R0 R3 used in the processing example", () => {
  const instruction = parseInt(INSTRUCTION_BITS.replaceAll(" ", ""), 2);
  assert.equal(instruction >>> 12, 1);
  assert.equal((instruction >>> 9) & 7, 0);
  assert.equal((instruction >>> 6) & 7, 0);
  assert.equal((instruction >>> 5) & 1, 0);
  assert.equal(instruction & 7, 3);
});

test("MAR retains the fetched address when PC moves to the next instruction", () => {
  assert.equal(instructionCycleFrame(1).mar, null);
  const selected = instructionCycleFrame(1.6);
  assert.equal(selected.mar, PROGRAM_START);
  assert.equal(selected.pc, PROGRAM_START + 1);
  const next = instructionCycleFrame(2);
  assert.equal(next.mar, PROGRAM_START);
  assert.equal(next.pc, PROGRAM_START + 1);
  assert.equal(next.r0, 9);
  assert.equal(next.writeEnabled, false);
});

test("MDR receives the instruction before IR, and fetching preserves working values", () => {
  assert.equal(instructionCycleFrame(3).mdr, null);
  const read = instructionCycleFrame(3.3);
  assert.equal(read.mdr, INSTRUCTION_BITS);
  assert.equal(read.ir, null);
  const fetched = instructionCycleFrame(5.1);
  assert.equal(fetched.ir, INSTRUCTION_BITS);
  assert.equal(fetched.r0, 9);
  assert.equal(fetched.phase, "decode");
});

test("the returning result is saved only during the enabled capture", () => {
  const arriving = instructionCycleFrame(9.6);
  assert.equal(arriving.result, 11);
  assert.equal(arriving.r0, 9);
  assert.equal(arriving.writeEnabled, false);
  const capture = instructionCycleFrame(10.4);
  assert.equal(capture.writeEnabled, true);
  assert.equal(capture.r0, 11);
  const held = instructionCycleFrame(12);
  assert.equal(held.writeEnabled, false);
  assert.equal(held.r0, 11);
});

test("the second instruction continues the total without clearing the previous result", () => {
  const next = instructionCycleFrame(12, 2);
  assert.equal(next.r0, 11);
  assert.equal(next.pc, PROGRAM_START + 1);
  assert.equal(next.mar, PROGRAM_START);
  assert.equal(next.ir, INSTRUCTION_BITS);
  const fetching = instructionCycleFrame(14, 2);
  assert.equal(fetching.mar, PROGRAM_START + 1);
  assert.equal(fetching.pc, PROGRAM_START + 2);
  assert.equal(fetching.r0, 11);
  assert.equal(instructionCycleFrame(22.4, 2).r0, 13);
  const done = instructionCycleFrame(100, 2);
  assert.equal(done.r0, 13);
  assert.equal(done.pc, PROGRAM_START + 2);
  assert.equal(done.writeEnabled, false);
});
