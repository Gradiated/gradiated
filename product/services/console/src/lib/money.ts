export const NANO_USD_PER_USD = 1_000_000_000n;

const NANO_USD_PER_CENT = NANO_USD_PER_USD / 100n;

export const MIN_TOP_UP_NANO_USD = 5n * NANO_USD_PER_USD;
export const MAX_TOP_UP_NANO_USD = 10_000n * NANO_USD_PER_USD;

export const USD_AMOUNT_PATTERN = /^(\d+)(?:\.(\d{1,2}))?$/;

export const parseUsdToNanoUsd = (value: string): bigint => {
  const match = USD_AMOUNT_PATTERN.exec(value);
  if (!match) throw new RangeError(`Not a USD amount: ${value}`);

  const [, dollars = "0", cents = ""] = match;

  return (
    BigInt(dollars) * NANO_USD_PER_USD +
    BigInt(cents.padEnd(2, "0")) * NANO_USD_PER_CENT
  );
};
