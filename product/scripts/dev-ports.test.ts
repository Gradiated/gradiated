import { execFileSync } from "node:child_process";

import { describe, expect, it } from "vitest";

import { forwardedListenPorts, isNoListenersExit } from "./dev-ports.mjs";

const thrownBy = (run: () => unknown): unknown => {
  try {
    run();
  } catch (error) {
    return error;
  }

  throw new Error("Expected the command to fail");
};

describe("forwardedListenPorts", () => {
  it("reads a bare listen port", () => {
    expect(
      forwardedListenPorts("localforward 3000 [127.0.0.1]:3000\n"),
    ).toEqual([3000]);
  });

  it("reads a listen port with a bracketed listen host", () => {
    expect(
      forwardedListenPorts("localforward [127.0.0.1]:14000 [127.0.0.1]:4000"),
    ).toEqual([14000]);
  });

  it("returns the listen side when it differs from the connect side", () => {
    expect(forwardedListenPorts("localforward 13000 [127.0.0.1]:3000")).toEqual(
      [13000],
    );
  });

  it("keeps forwards whose connect host is not loopback", () => {
    expect(
      forwardedListenPorts("localforward [127.0.0.1]:14000 [example.com]:4000"),
    ).toEqual([14000]);
  });

  it("ignores unix-socket forwards", () => {
    expect(
      forwardedListenPorts("localforward /tmp/dev.sock [127.0.0.1]:5000"),
    ).toEqual([]);
  });

  it("deduplicates listen ports", () => {
    const config = [
      "localforward 3000 [127.0.0.1]:3000",
      "localforward [127.0.0.1]:3000 [127.0.0.1]:3000",
      "localforward 5173 [127.0.0.1]:5173",
    ].join("\n");

    expect(forwardedListenPorts(config)).toEqual([3000, 5173]);
  });

  it("returns no ports without forwards", () => {
    expect(forwardedListenPorts("hostname dev.example.com\nport 22\n")).toEqual(
      [],
    );
  });
});

describe("isNoListenersExit", () => {
  it("treats exit status 1 as no matching listeners", () => {
    const error = thrownBy(() => execFileSync("sh", ["-c", "exit 1"]));

    expect(isNoListenersExit(error)).toBe(true);
  });

  it("rejects a missing command", () => {
    const error = thrownBy(() =>
      execFileSync("gradiated-missing-command", [], { stdio: "ignore" }),
    );

    expect(error).toMatchObject({ code: "ENOENT" });
    expect(isNoListenersExit(error)).toBe(false);
  });

  it("rejects any other exit status", () => {
    const error = thrownBy(() =>
      execFileSync("sh", ["-c", "exit 2"], { stdio: "ignore" }),
    );

    expect(isNoListenersExit(error)).toBe(false);
  });
});
