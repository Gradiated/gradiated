import { describe, expect, it } from "vitest";

import { credentialedSync } from "../src/database.js";

describe("the PostgreSQL credential", () => {
  it("connects once the credential appears and reconnects when it rotates", async () => {
    let url: string | undefined;
    const opened: string[] = [];
    const closed: string[] = [];
    const credential = credentialedSync(
      () => url,
      (value) => {
        opened.push(value);
        return { database: value, close: async () => void closed.push(value) };
      },
      (database) => async () => ({
        inserted: [database],
        restored: [],
        retired: [],
        updated: [],
        conflicts: [],
      }),
    );

    expect(credential.resolve()).toBeUndefined();
    expect(credential.database()).toBeUndefined();
    url = "postgres://first";
    expect(credential.database()).toBe("postgres://first");
    expect((await credential.resolve()!([], () => {})).inserted).toEqual([
      "postgres://first",
    ]);
    credential.resolve();
    expect(opened).toEqual(["postgres://first"]);

    url = "postgres://rotated";
    expect(credential.database()).toBe("postgres://rotated");
    expect((await credential.resolve()!([], () => {})).inserted).toEqual([
      "postgres://rotated",
    ]);
    expect(opened).toEqual(["postgres://first", "postgres://rotated"]);
    expect(closed).toEqual(["postgres://first"]);

    await credential.close();
    expect(closed).toEqual(["postgres://first", "postgres://rotated"]);
  });
});
