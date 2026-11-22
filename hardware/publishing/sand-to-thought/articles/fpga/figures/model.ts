export type Bit = 0 | 1;
export type Rule = "AND" | "OR" | "XOR";
export type LutAnswers = readonly [Bit, Bit, Bit, Bit];

export const answers: Record<Rule, LutAnswers> = {
  AND: [0, 0, 0, 1],
  OR: [0, 1, 1, 1],
  XOR: [0, 1, 1, 0],
};

export const address = (a: Bit, b: Bit) => 2 * a + b;
export const lookup = (rule: Rule, a: Bit, b: Bit): Bit =>
  answers[rule][address(a, b)];
export const changedAnswers = (stored: LutAnswers, target: LutAnswers) =>
  stored.flatMap((bit, row) => (bit === target[row] ? [] : [row]));

export const writeAnswer = (
  stored: LutAnswers,
  row: number,
  value: Bit,
): LutAnswers => {
  if (!Number.isInteger(row) || row < 0 || row > 3) {
    throw new RangeError("A two-input LUT has rows 0 to 3");
  }

  const updated: [Bit, Bit, Bit, Bit] = [...stored];
  updated[row] = value;

  return updated;
};

export const combined = (a: Bit, b: Bit, c: Bit): Bit =>
  lookup("XOR", lookup("AND", a, b), c);
export const binary = (value: number, width = 4) =>
  value.toString(2).padStart(width, "0");

export type Pair = { a: number; b: number };
export const capturePair = ({ a }: Pair): Pair => ({ a: (a + 1) % 16, b: a });

export type PulseState = {
  count: number;
  width: number;
  pending: number;
  output: Bit;
  edges: number;
};

export const initialPulse = (width = 4): PulseState => ({
  count: 0,
  width,
  pending: width,
  output: width > 0 ? 1 : 0,
  edges: 0,
});

export const requestWidth = (state: PulseState, width: number): PulseState => {
  if (!Number.isInteger(width) || width < 0 || width > 16) {
    throw new RangeError("Width must be a whole number from 0 to 16");
  }

  return { ...state, pending: width };
};

export const pulseEdge = (state: PulseState): PulseState => {
  const count = (state.count + 1) % 16;
  const width = count === 0 ? state.pending : state.width;

  return {
    ...state,
    count,
    width,
    output: count < width ? 1 : 0,
    edges: state.edges + 1,
  };
};

export const pulsePeriod = (width: number): Bit[] =>
  Array.from({ length: 16 }, (_, count) => (count < width ? 1 : 0));

export const timingBudget = (period: number) => ({
  delay: 8,
  period,
  slack: period - 8,
  passes: period >= 8,
});
