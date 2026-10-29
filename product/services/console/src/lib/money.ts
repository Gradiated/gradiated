import {
  MAX_TOP_UP_NANO_USD,
  MIN_TOP_UP_NANO_USD,
  NANO_USD_PER_CENT,
  NANO_USD_PER_USD,
} from "@gradiated/contracts";

// The API's limits, so the dialogs reject what the server would.
export { MAX_TOP_UP_NANO_USD, MIN_TOP_UP_NANO_USD, NANO_USD_PER_USD };

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

export const formatNanoUsdInput = (nanoUsd: string): string => {
  const amount = BigInt(nanoUsd);
  const dollars = amount / NANO_USD_PER_USD;
  const cents = (amount % NANO_USD_PER_USD) / NANO_USD_PER_CENT;

  return cents === 0n
    ? dollars.toString()
    : `${dollars}.${cents.toString().padStart(2, "0")}`;
};

// A typed USD amount within [minimum, MAX_TOP_UP_NANO_USD], or null.
export const parseUsdAmount = (
  value: string,
  minimum: bigint = MIN_TOP_UP_NANO_USD,
): bigint | null => {
  const trimmed = value.trim();
  if (!USD_AMOUNT_PATTERN.test(trimmed)) return null;

  const amount = parseUsdToNanoUsd(trimmed);

  return amount >= minimum && amount <= MAX_TOP_UP_NANO_USD ? amount : null;
};
