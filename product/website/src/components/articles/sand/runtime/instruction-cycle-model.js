export const INSTRUCTION_BITS = "0001 000 000 0 00 011";
export const PROGRAM_START = 12288;
export const INSTRUCTION_CYCLE_DURATION = 12;

const capturePulse = (time, edge) =>
  time < edge ? 0 : Math.max(0, 1 - (time - edge) / 0.45);

export const instructionCycleFrame = (time, cycles = 1) => {
  const total = Math.max(
    0,
    Math.min(time, cycles * INSTRUCTION_CYCLE_DURATION),
  );
  const iteration = Math.min(
    cycles - 1,
    Math.floor(total / INSTRUCTION_CYCLE_DURATION),
  );
  const elapsed = Number(
    (total - iteration * INSTRUCTION_CYCLE_DURATION).toFixed(6),
  );
  const address = PROGRAM_START + iteration;
  const initial = 9 + iteration * 2;
  const phase =
    elapsed < 4.8
      ? "fetch"
      : elapsed < 6.4
        ? "decode"
        : elapsed < 10.8
          ? "execute"
          : "next";
  return {
    elapsed,
    iteration,
    address,
    pc: address + Number(elapsed >= 1.6),
    mar: elapsed >= 1.6 ? address : iteration ? address - 1 : null,
    mdr: iteration || elapsed >= 3.2 ? INSTRUCTION_BITS : null,
    ir: iteration || elapsed >= 4.8 ? INSTRUCTION_BITS : null,
    input: initial,
    result: initial + 2,
    r0: elapsed >= 10.4 ? initial + 2 : initial,
    writeEnabled: elapsed >= 10.1 && elapsed < 10.7,
    waitingForMemory: elapsed >= 1.6 && elapsed < 3.2,
    memoryReady: elapsed >= 3.2,
    captures: {
      pc: capturePulse(elapsed, 1.6),
      mar: capturePulse(elapsed, 1.6),
      mdr: capturePulse(elapsed, 3.2),
      ir: capturePulse(elapsed, 4.8),
      r0: capturePulse(elapsed, 10.4),
    },
    phase,
  };
};

export const CONTROLLER_CYCLE_DURATION = 15;
export const CONTROLLER_STEPS = ["request", "wait", "copy", "execute"];

export const CONTROLLER_GATES = [
  ["n1", "NOT", ["s1"]],
  ["n0", "NOT", ["s0"]],
  ["notReady", "NOT", ["ready"]],
  ["request", "AND", ["n1", "n0"]],
  ["wait", "AND", ["n1", "s0"]],
  ["copy", "AND", ["s1", "n0"]],
  ["execute", "AND", ["s1", "s0"]],
  ["hold", "AND", ["wait", "notReady"]],
  ["advance", "AND", ["wait", "ready"]],
  ["next0", "OR", ["request", "hold", "copy"]],
  ["next1", "OR", ["advance", "copy"]],
];

export const CONTROLLER_OUTPUTS = {
  request: "request",
  send: "copy",
  load: "copy",
  processing: "execute",
  next1: "next1",
  next0: "next0",
};

const nextControllerState = (state, ready) =>
  state === 1 ? (ready ? 2 : 1) : (state + 1) % CONTROLLER_STEPS.length;

export const controllerFrame = (time, memoryReadyAt = 8) => {
  // These four states illustrate ADD sequencing, not the LC-3 microstate encoding.
  let state = 0;
  let cycleStart = 0;
  let completed = 0;
  let irEdge = -Infinity;
  for (let edge = 3; edge <= time; edge += 3) {
    const ready = edge - cycleStart >= memoryReadyAt;
    if (state === 2) irEdge = edge;
    if (state === 3) {
      completed += 1;
      cycleStart = edge;
    }
    state = nextControllerState(state, ready);
  }
  const ready = state !== 0 && time - cycleStart >= memoryReadyAt;
  const nextState = nextControllerState(state, ready);
  const clockEdge = Math.floor(time / 3) * 3;
  const clock = clockEdge > 0 ? capturePulse(time, clockEdge) : 0;
  return {
    state,
    step: CONTROLLER_STEPS[state],
    bits: state.toString(2).padStart(2, "0"),
    nextState,
    nextBits: nextState.toString(2).padStart(2, "0"),
    ready,
    request: state === 0,
    copy: state === 2,
    processing: state === 3,
    captured: irEdge >= cycleStart,
    completed,
    clock,
    captures: { state: clock, ir: capturePulse(time, irEdge) },
  };
};
