import { describe, expect, it } from "vitest";
import { adapterRuntimeName, RuntimeAdapterSchema } from "../src/hosting.js";

describe("immutable runtime adapter identity", () => {
  it("keeps different weights and versions in separate runtime namespaces", () => {
    const id = "01980000-0000-7000-8000-000000000001";
    const hash = "a".repeat(64);
    expect(adapterRuntimeName(id, hash)).not.toEqual(
      adapterRuntimeName(id, "b".repeat(64)),
    );
    expect(() => adapterRuntimeName(id, "../../adapter")).toThrow();
    expect(
      RuntimeAdapterSchema.safeParse({
        version_id: id,
        sha256: hash,
        name: "public-path",
        profile_id: "tp2",
      }).success,
    ).toBe(false);
  });
});
