import assert from "node:assert/strict";
import test from "node:test";
import {
  INSTRUCTION_BITS,
  PROGRAM_START,
  instructionCycleFrame,
  controllerFrame,
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

test("the controller close-up enables one transfer then holds the next state", () => {
  const ready = controllerFrame(1.99);
  assert.equal(ready.state, 0);
  assert.equal(ready.copy, false);
  assert.equal((ready.next1 << 1) | ready.next0, 1);
  const copying = controllerFrame(2);
  assert.equal(copying.state, 1);
  assert.equal(copying.copy, true);
  assert.equal(copying.captured, false);
  assert.equal((copying.next1 << 1) | copying.next0, 2);
  assert.equal(controllerFrame(5.99).copy, true);
  const captured = controllerFrame(6);
  assert.equal(captured.state, 2);
  assert.equal(captured.copy, false);
  assert.equal(captured.captured, true);
  assert.equal((captured.next1 << 1) | captured.next0, 2);
  assert.equal(controllerFrame(10).state, 2);
});

test("the whole-computer fetch waits for memory before transferring the instruction into IR", () => {
  for (const time of [1.6, 2.4, 3.19]) {
    const waiting = instructionCycleFrame(time);
    assert.equal(waiting.waitingForMemory, true);
    assert.equal(waiting.memoryReady, false);
    assert.equal(waiting.mdr, null);
    assert.equal(waiting.ir, null);
  }
  const ready = instructionCycleFrame(3.2);
  assert.equal(ready.waitingForMemory, false);
  assert.equal(ready.memoryReady, true);
  assert.equal(ready.mdr, INSTRUCTION_BITS);
  assert.equal(ready.ir, null);
  assert.equal(instructionCycleFrame(4.79).ir, null);
  assert.equal(instructionCycleFrame(4.8).ir, INSTRUCTION_BITS);
  const secondRead = instructionCycleFrame(14.4, 2);
  assert.equal(secondRead.waitingForMemory, true);
  assert.equal(secondRead.memoryReady, false);
  assert.equal(secondRead.captures.ir, 0);
});

test("register capture flashes coincide with clock edges and value arrival", () => {
  for (const [name, edge] of [
    ["pc", 1.6],
    ["mar", 1.6],
    ["mdr", 3.2],
    ["ir", 4.8],
    ["r0", 10.4],
  ]) {
    const before = instructionCycleFrame(edge - 0.01);
    const captured = instructionCycleFrame(edge);
    assert.equal(before.captures[name], 0);
    assert.equal(captured.captures[name], 1);
    assert.ok(Math.abs(edge / 0.8 - Math.round(edge / 0.8)) < 1e-9);
    assert.notEqual(captured[name], before[name]);
    assert.equal(instructionCycleFrame(edge + 0.5).captures[name], 0);
  }
  assert.ok(
    Object.values(instructionCycleFrame(0.8).captures).every(
      (value) => value === 0,
    ),
  );
  const repeated = instructionCycleFrame(16.8, 2);
  assert.equal(repeated.ir, INSTRUCTION_BITS);
  assert.equal(repeated.captures.ir, 1);
});

test("the state register flashes on state changes but holds on subsequent clock pulses", () => {
  for (const edge of [2, 6]) {
    assert.equal(controllerFrame(edge - 0.01).captures.state, 0);
    assert.equal(controllerFrame(edge).captures.state, 1);
    assert.notEqual(
      controllerFrame(edge).state,
      controllerFrame(edge - 0.01).state,
    );
    assert.equal(controllerFrame(edge + 0.5).captures.state, 0);
  }
  assert.equal(controllerFrame(10).captures.state, 0);
  assert.equal(controllerFrame(10).state, 2);
});
