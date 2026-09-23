import { describe, expect, it } from "vitest";

import {
  lastSlotEndingBy,
  nextSlot,
  parseSlot,
  slotContaining,
} from "../src/settlement-slot.js";

const slotMilliseconds = 300_000;
const lastSlotStart = Date.UTC(9999, 11, 31, 23, 55);

const invalidSlot = expect.objectContaining({
  code: "EINVALID_SETTLEMENT_SLOT",
});

const seededRandom = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;

  return ((value ^ (value >>> 14)) >>> 0) / 4_294_967_296;
};

const boundaryTimes = [
  0,
  1,
  slotMilliseconds - 1,
  slotMilliseconds,
  slotMilliseconds + 1,
  Date.UTC(2024, 1, 29, 23, 57, 30),
  Date.UTC(2026, 7, 15, 12, 30) - 1,
  Date.UTC(2026, 7, 15, 12, 30),
  lastSlotStart,
  lastSlotStart + slotMilliseconds - 1,
];

const random = seededRandom(20_260_815);
const sampleTimes = [
  ...boundaryTimes,
  ...Array.from({ length: 500 }, () =>
    Math.floor(random() * (lastSlotStart + slotMilliseconds)),
  ),
];

describe("settlement slots", () => {
  it("pins the slot ID format", () => {
    expect(slotContaining(Date.UTC(2026, 7, 15, 12, 32, 10)).id).toBe(
      "20260815T123000Z-300s-v1",
    );
    expect(slotContaining(0).id).toBe("19700101T000000Z-300s-v1");
    expect(parseSlot("20260815T123000Z-300s-v1")).toEqual({
      id: "20260815T123000Z-300s-v1",
      start: new Date("2026-08-15T12:30:00.000Z"),
      end: new Date("2026-08-15T12:35:00.000Z"),
    });
  });

  it("contains each time in its slot and round-trips the slot ID", () => {
    for (const time of sampleTimes) {
      const slot = slotContaining(time);

      expect(slot.start.getTime()).toBeLessThanOrEqual(time);
      expect(time).toBeLessThan(slot.end.getTime());
      expect(slotContaining(parseSlot(slot.id).start.getTime()).id).toBe(
        slot.id,
      );
    }
  });

  it("starts the next slot where the slot ends", () => {
    for (const time of sampleTimes.filter((value) => value < lastSlotStart)) {
      const slot = slotContaining(time);

      expect(nextSlot(slot).start).toEqual(slot.end);
    }
  });

  it("orders slot IDs as it orders time", () => {
    const slots = sampleTimes.map(slotContaining);

    for (const [index, slot] of slots.entries()) {
      const other = slots[(index + 1) % slots.length];
      if (!other) continue;

      expect(Math.sign(slot.id.localeCompare(other.id))).toBe(
        Math.sign(slot.start.getTime() - other.start.getTime()),
      );
    }
  });

  it("finds the last slot that ends by a time", () => {
    expect(lastSlotEndingBy(slotMilliseconds - 1)).toBeNull();
    expect(lastSlotEndingBy(slotMilliseconds)?.start).toEqual(new Date(0));
    expect(lastSlotEndingBy(2 * slotMilliseconds - 1)?.start).toEqual(
      new Date(0),
    );
  });

  it.each([
    [
      "a slot that is not on a five-minute boundary",
      "20260815T123100Z-300s-v1",
    ],
    ["a slot with seconds", "20260815T123010Z-300s-v1"],
    ["February 30", "20260230T123000Z-300s-v1"],
    ["hour 24", "20260815T240000Z-300s-v1"],
    ["a two-digit year that Date.UTC remaps", "00500101T000000Z-300s-v1"],
    ["a time before the Unix epoch", "19691231T235500Z-300s-v1"],
    ["trailing text", "20260815T123000Z-300s-v1x"],
    ["another slot width", "20260815T123000Z-600s-v1"],
  ])("rejects %s", (_case, id) => {
    expect(() => parseSlot(id)).toThrow(invalidSlot);
  });

  it("rejects a time past the four-digit year range", () => {
    expect(() => slotContaining(lastSlotStart + slotMilliseconds)).toThrow(
      invalidSlot,
    );
    expect(() => nextSlot(slotContaining(lastSlotStart))).toThrow(invalidSlot);
  });

  it("rejects a time that is not finite", () => {
    expect(() => slotContaining(Number.NaN)).toThrow(invalidSlot);
    expect(() => slotContaining(Number.POSITIVE_INFINITY)).toThrow(invalidSlot);
  });
});
