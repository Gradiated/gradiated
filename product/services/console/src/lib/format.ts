import { NANO_USD_PER_USD } from "@/lib/money";

const SIGNIFICANT_DIGITS = 3;
const MINIMUM_FRACTION_DIGITS = 2;
const MAXIMUM_FRACTION_DIGITS = 20;

const fractionDigitsFor = (value: number) => {
  if (!Number.isFinite(value) || value === 0) return MINIMUM_FRACTION_DIGITS;

  const magnitude = Math.floor(Math.log10(Math.abs(value)));

  return Math.min(
    MAXIMUM_FRACTION_DIGITS,
    Math.max(MINIMUM_FRACTION_DIGITS, SIGNIFICANT_DIGITS - magnitude - 1),
  );
};

export const formatUsd = (value: number) => {
  const fractionDigits = fractionDigitsFor(value);

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

export const formatNanoUsd = (nanoUsd: bigint | string | number) =>
  formatUsd(Number(nanoUsd) / Number(NANO_USD_PER_USD));

export const formatLatency = (ms: number) =>
  ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;

export const formatElapsed = (ms: number) => {
  const seconds = Math.max(1, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s`;

  const minutes = Math.round(seconds / 60);

  return minutes < 60 ? `${minutes} min` : `${(minutes / 60).toFixed(1)} h`;
};

export const formatPercent = (fraction: number) =>
  `${Math.round(fraction * 100)}%`;

export interface Ratio {
  tone: "good" | "bad" | "neutral";
  label: string;
}

// Under 2× the difference reads as a percentage, from 2× as a multiple. A
// saving ("cheaper") is the share of the comparison's cost removed; every
// other direction is the increase over the slower or cheaper side.
export const formatRatio = (
  advantage: number,
  good: string,
  bad: string,
  { goodIsReduction = good === "cheaper" } = {},
): Ratio => {
  if (!Number.isFinite(advantage) || advantage <= 0) {
    return { tone: "neutral", label: "n/a" };
  }

  const isGood = advantage >= 1;
  const factor = isGood ? advantage : 1 / advantage;
  const percent = isGood && goodIsReduction ? 1 - 1 / factor : factor - 1;

  return {
    tone: isGood ? "good" : "bad",
    label: `${factor < 2 ? `${(percent * 100).toFixed(1)}%` : `${factor.toFixed(1)}×`} ${isGood ? good : bad}`,
  };
};

export const formatFileSize = (bytes: number) =>
  bytes < 1024 ** 2
    ? `${Math.max(1, Math.ceil(bytes / 1024))} KB`
    : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
