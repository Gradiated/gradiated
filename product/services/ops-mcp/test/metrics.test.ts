import { mkdtempSync, writeFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { closeServers, setup } from "./support/mcp.js";
import { testCa } from "./support/nomad-ca.js";

afterEach(closeServers);

const scrape = async (nomadCertificateFile: string) => {
  const { app } = await setup({ nomadCertificateFile });
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
    const file = path.join(
      mkdtempSync(path.join(tmpdir(), "ops-mcp-")),
      "nomad-cert",
    );
    writeFileSync(file, testCa.certificate);

    expect(await scrape(file)).toMatch(
      /^ops_mcp_nomad_certificate_expiry_timestamp_seconds\{certificate="ops-mcp"\} 4943797864$/m,
    );
  });

  it("reports nothing while no certificate is mounted", async () => {
    expect(await scrape("/nonexistent/nomad-cert")).not.toMatch(
      /^ops_mcp_nomad_certificate_expiry_timestamp_seconds\{/m,
    );
  });
});
