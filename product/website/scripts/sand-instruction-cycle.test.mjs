import assert from "node:assert/strict";
import test from "node:test";
import {
  INSTRUCTION_BITS,
  PROGRAM_START,
  instructionCycleFrame,
  controllerFrame,
  CONTROLLER_GATES,
  CONTROLLER_OUTPUTS,
} from "../../../hardware/publishing/sand-to-thought/articles/sand/figures/runtime/instruction-cycle-model.js";

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

test("one step remains active throughout a complete illustrative ADD cycle", () => {
  const visits = [];
  for (let time = 0; time <= 15; time += 0.125) {
    const frame = controllerFrame(time);
    assert.equal(frame.bits.length, 2);
    assert.equal(parseInt(frame.bits, 2), frame.state);
    assert.equal(parseInt(frame.nextBits, 2), frame.nextState);
    assert.ok(["request", "wait", "copy", "execute"].includes(frame.step));
    if (visits.at(-1) !== frame.step) visits.push(frame.step);
  }
  assert.deepEqual(visits, ["request", "wait", "copy", "execute", "request"]);
  assert.equal(controllerFrame(14.99).completed, 0);
  assert.equal(controllerFrame(15).completed, 1);
  assert.equal(controllerFrame(15).request, true);
  assert.equal(controllerFrame(15).ready, false);
  assert.equal(controllerFrame(18).step, "wait");
  assert.equal(controllerFrame(30).completed, 2);
});

test("memory readiness prepares a transition but only a clock edge captures it", () => {
  for (const time of [3, 6, 7.99]) {
    const frame = controllerFrame(time);
    assert.equal(frame.step, "wait");
    assert.equal(frame.nextState, frame.state);
    assert.equal(frame.ready, false);
    assert.equal(frame.copy, false);
  }
  const ready = controllerFrame(8);
  assert.equal(ready.step, "wait");
  assert.equal(ready.nextState, 2);
  assert.equal(ready.ready, true);
  assert.equal(ready.copy, false);
  assert.equal(controllerFrame(8.99).step, "wait");
  assert.equal(controllerFrame(9).step, "copy");
});

test("a slower or absent memory response extends the waiting state", () => {
  assert.equal(controllerFrame(9, 11).step, "wait");
  assert.equal(controllerFrame(11, 11).nextState, 2);
  assert.equal(controllerFrame(11.99, 11).copy, false);
  assert.equal(controllerFrame(12, 11).copy, true);
  assert.equal(controllerFrame(14.99, 11).captured, false);
  assert.equal(controllerFrame(15, 11).captured, true);
  for (const time of [3, 6, 9, 18, 60]) {
    const frame = controllerFrame(time, Infinity);
    assert.equal(frame.step, "wait");
    assert.equal(frame.copy, false);
    assert.equal(frame.completed, 0);
  }
});

test("transfer controls are enabled before IR captures, then switch off", () => {
  assert.equal(controllerFrame(8.99).copy, false);
  for (const time of [9, 10.5, 11.99]) {
    assert.equal(controllerFrame(time).copy, true);
    assert.equal(controllerFrame(time).captured, false);
    assert.equal(controllerFrame(time).captures.ir, 0);
  }
  const captured = controllerFrame(12);
  assert.equal(captured.step, "execute");
  assert.equal(captured.copy, false);
  assert.equal(captured.captured, true);
  assert.equal(captured.captures.ir, 1);
  assert.equal(captured.processing, true);
  assert.equal(controllerFrame(15).step, "request");
  assert.equal(controllerFrame(14.99).captured, true);
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

test("state captures and clock flashes share every rising edge, even while waiting", () => {
  for (const edge of [3, 6, 9, 12, 15]) {
    assert.equal(controllerFrame(edge - 0.01).captures.state, 0);
    assert.equal(controllerFrame(edge).captures.state, 1);
    assert.equal(controllerFrame(edge).clock, 1);
    assert.equal(controllerFrame(edge + 0.5).captures.state, 0);
  }
  assert.equal(controllerFrame(0).clock, 0);
  assert.equal(controllerFrame(3).step, "wait");
  assert.equal(controllerFrame(6).step, "wait");
  assert.equal(controllerFrame(9).step, "copy");
  assert.equal(controllerFrame(12).step, "execute");
  assert.equal(controllerFrame(15).step, "request");
  assert.equal(controllerFrame(18).step, "wait");
});

test("the drawn gate circuit produces the four-state sequence and its control signals", () => {
  for (let state = 0; state < 4; state += 1) {
    for (const ready of [false, true]) {
      const values = {
        s1: Boolean(state & 2),
        s0: Boolean(state & 1),
        ready,
      };
      for (const [id, operation, inputs] of CONTROLLER_GATES) {
        const operands = inputs.map((input) => {
          assert.ok(input in values, `unconnected gate input ${input}`);
          return values[input];
        });
        values[id] =
          operation === "NOT"
            ? !operands[0]
            : operation === "AND"
              ? operands.every(Boolean)
              : operands.some(Boolean);
      }
      const outputs = Object.fromEntries(
        Object.entries(CONTROLLER_OUTPUTS).map(([name, net]) => [
          name,
          values[net],
        ]),
      );
      const next = Number(outputs.next1) * 2 + Number(outputs.next0);
      assert.equal(next, state === 1 ? (ready ? 2 : 1) : (state + 1) % 4);
      assert.equal(outputs.request, state === 0);
      assert.equal(outputs.send, state === 2);
      assert.equal(outputs.load, state === 2);
      assert.equal(outputs.processing, state === 3);
    }
  }
});
