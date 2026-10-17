export const INSTRUCTION_BITS = "0001 000 000 0 00 011";
export const PROGRAM_START = 12288;
export const INSTRUCTION_CYCLE_DURATION = 12;

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
    phase,
  };
};
