import type { AddressInfo } from "node:net";

import { afterEach, describe, expect, it } from "vitest";

import { closeServers, setup } from "./support/mcp.js";

afterEach(closeServers);

const scrape = async (expiry: number | undefined) => {
  const { app } = await setup({ nomadCertificateExpiry: () => expiry });
  await new Promise<void>((resolve) =>
    app.metrics.listen(0, "127.0.0.1", resolve),
  );
  const { port } = app.metrics.address() as AddressInfo;
  const body = await (await fetch(`http://127.0.0.1:${port}/metrics`)).text();
  app.metrics.close();

  return body;
};

describe("Nomad certificate expiry metric", () => {
  it("reports when the certificate the ops MCP presents to Nomad expires", async () => {
    expect(await scrape(1_800_000_000)).toMatch(
      /^nomad_certificate_expiry_timestamp_seconds\{certificate="ops-mcp"\} 1800000000$/m,
    );
  });

  it("reports nothing before a certificate has been issued", async () => {
    expect(await scrape(undefined)).not.toMatch(
      /^nomad_certificate_expiry_timestamp_seconds\{/m,
    );
  });
});
