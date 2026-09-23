import { WorkerInvariantError } from "./errors.js";

export type SettlementSlot = {
  readonly id: string;
  readonly start: Date;
  readonly end: Date;
};

const slotMilliseconds = 300_000;
const slotIdPattern = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})00Z-300s-v1$/;

// The slot ID has a four-digit year, so the last slot starts in year 9999.
const lastSlotStart = Date.UTC(9999, 11, 31, 23, 55);

const slotAt = (start: number): SettlementSlot => {
  if (!Number.isSafeInteger(start) || start < 0 || start > lastSlotStart) {
    throw new WorkerInvariantError(
      "EINVALID_SETTLEMENT_SLOT",
      `Settlement slot time is out of range: ${start}`,
    );
  }

  const compact = new Date(start)
    .toISOString()
    .slice(0, 19)
    .replaceAll("-", "")
    .replaceAll(":", "");

  return {
    id: `${compact}Z-300s-v1`,
    start: new Date(start),
    end: new Date(start + slotMilliseconds),
  };
};

export const slotContaining = (milliseconds: number): SettlementSlot =>
  slotAt(Math.floor(milliseconds / slotMilliseconds) * slotMilliseconds);

export const parseSlot = (id: string): SettlementSlot => {
  const match = slotIdPattern.exec(id);
  const start = match
    ? Date.UTC(
        Number(match[1]),
        Number(match[2]) - 1,
        Number(match[3]),
        Number(match[4]),
        Number(match[5]),
      )
    : Number.NaN;
  const slot = Number.isNaN(start) ? null : slotContaining(start);

  if (slot?.id !== id) {
    throw new WorkerInvariantError(
      "EINVALID_SETTLEMENT_SLOT",
      `Invalid settlement slot ID: ${id}`,
    );
  }

  return slot;
};

export const nextSlot = (slot: SettlementSlot): SettlementSlot =>
  slotAt(slot.end.getTime());

export const lastSlotEndingBy = (
  milliseconds: number,
): SettlementSlot | null =>
  milliseconds < slotMilliseconds
    ? null
    : slotContaining(milliseconds - slotMilliseconds);
