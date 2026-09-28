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

  it("accepts automatic issuance without a stored client key", () => {
    expect(
      parseNomadEnvironment({
        NOMAD_ADDR: "https://nomad-api.nomad.svc.cluster.local:4646",
        NOMAD_TOKEN: "test-token",
        NOMAD_CA_PEM: "test-ca",
        NOMAD_CA_KMS_KEY: "alias/test-ca",
      })?.NOMAD_CA_KMS_KEY,
    ).toBe("alias/test-ca");
  });

  it("rejects a client certificate without its key or an issuer", () => {
    expect(() =>
      parseNomadEnvironment({
        NOMAD_ADDR: "https://nomad-api.nomad.svc.cluster.local:4646",
        NOMAD_TOKEN: "test-token",
        NOMAD_CA_PEM: "test-ca",
        NOMAD_CLIENT_CERT_PEM: "test-certificate",
      }),
    ).toThrow();
  });
});
