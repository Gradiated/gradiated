export const hardwareScales = {
  capacity: { start: 1e6, end: 6e12 },
  bandwidth: { start: 1, end: 25_000 },
};

export function profileFraction(value: number, { start, end }: { start: number; end: number }) {
  return Math.log(value / start) / Math.log(end / start);
}
