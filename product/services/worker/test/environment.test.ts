import { describe, expect, it } from "vitest";

import { parseNomadEnvironment } from "../src/environment.js";

describe("Nomad environment", () => {
  it("leaves deployment reconciliation off without a Nomad address", () => {
    expect(parseNomadEnvironment({})).toBeNull();
  });

  it("requires every credential once the address is set", () => {
    expect(() =>
      parseNomadEnvironment({
        NOMAD_ADDR: "https://nomad-api.nomad.svc.cluster.local:4646",
      }),
    ).toThrow();
  });
});
