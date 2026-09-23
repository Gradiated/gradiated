import { describe, expect, it } from "vitest";

import {
  formatStreamId,
  nextStreamId,
  parseStreamId,
} from "../src/stream-id.js";

describe("stream IDs", () => {
  it("parses the time and a sequence beyond the safe integer range", () => {
    expect(parseStreamId("1786797061000-18446744073709551615")).toEqual({
      milliseconds: 1_786_797_061_000,
      sequence: 18_446_744_073_709_551_615n,
    });
  });

  it("advances the sequence and formats the ID", () => {
    expect(formatStreamId(nextStreamId(parseStreamId("200-4")))).toBe("200-5");
    expect(formatStreamId(nextStreamId(parseStreamId("0-0")))).toBe("0-1");
  });

  it("carries the maximum sequence into the next millisecond", () => {
    expect(
      formatStreamId(nextStreamId(parseStreamId("200-18446744073709551615"))),
    ).toBe("201-0");
  });

  it.each([
    "not-an-id",
    "100",
    "01-1",
    "100-01",
    "-1-0",
    "100-1 ",
    `${Number.MAX_SAFE_INTEGER + 1}-0`,
  ])("rejects %j", (id) => {
    expect(() => parseStreamId(id)).toThrow(
      expect.objectContaining({ code: "EINVALID_STREAM_ID" }),
    );
  });
});
