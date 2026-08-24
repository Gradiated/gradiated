const DEFAULT_SIGNIFICANT_DIGITS = 3;
const MAXIMUM_FRACTION_DIGITS = 20;

const fractionDigitsFor = (
  value: number,
  minimumFractionDigits: number,
  significantDigits: number,
) => {
  if (!Number.isFinite(value) || value === 0) return minimumFractionDigits;
  const magnitude = Math.floor(Math.log10(Math.abs(value)));
  return Math.min(
    MAXIMUM_FRACTION_DIGITS,
    Math.max(minimumFractionDigits, significantDigits - magnitude - 1),
  );
};

export const formatNumber = (
  value: number,
  significantDigits = DEFAULT_SIGNIFICANT_DIGITS,
) =>
  new Intl.NumberFormat(undefined, {
    minimumSignificantDigits: significantDigits,
    maximumSignificantDigits: significantDigits,
  }).format(value);

export const formatUsd = (value: number) => {
  const fractionDigits = fractionDigitsFor(
    value,
    2,
    DEFAULT_SIGNIFICANT_DIGITS,
  );
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
};

export const formatUsdShort = (value: number) =>
  new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    currencyDisplay: "narrowSymbol",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);

export const formatNanoUsd = (nanoUsd: string) =>
  formatUsd(Number(nanoUsd) / 1_000_000_000);
