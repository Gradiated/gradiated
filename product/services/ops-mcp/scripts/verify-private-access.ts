import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const token = process.env.T3_MCP_BEARER_TOKEN;
assert(token, "T3_MCP_BEARER_TOKEN is required");

const args = {
  provider: "runpod",
  instance_id: `security-probe-${randomUUID()}`,
  reset_running_pod: true,
  confirm_instance_id: "deliberately-mismatched-no-registration",
};

const probe = async (
  url: URL,
  expectedError: string,
  extraHeaders: Record<string, string> = {},
) => {
  const client = new Client({ name: "ops-private-access-probe", version: "1" });
  try {
    await client.connect(
      new StreamableHTTPClientTransport(url, {
        requestInit: {
          headers: { authorization: `Bearer ${token}`, ...extraHeaders },
        },
      }),
    );
    const tools = await client.listTools();
    assert(tools.tools.some((tool) => tool.name === "register_instance"));
    const result = await client.callTool({
      name: "register_instance",
      arguments: args,
    });
    assert.equal(result.isError, true);
    const content = result.content as { type: string; text?: string }[];
    assert(
      content.some((item) => item.text?.includes(expectedError)),
      "Unexpected tool rejection",
    );
    const status = await client.callTool({
      name: "instance_registration_status",
      arguments: {},
    });
    assert.notEqual(status.isError, true);
    assert(
      !JSON.stringify(status.content).includes(args.instance_id),
      "Probe started a registration",
    );
  } finally {
    await client.close();
  }
};

const publicUrl = new URL("https://ops.gradiated.com/mcp");
await probe(publicUrl, "private administrative MCP connection");
console.log(
  "PASS: authenticated public enrollment denied; status remains readable",
);
await probe(publicUrl, "private administrative MCP connection", {
  "x-forwarded-for": "100.64.0.1, 127.0.0.1",
  "tailscale-user-login": "security-probe@gradiated.com",
  "x-mcp-ingress": "private",
});
console.log("PASS: forged private-network headers cannot authorize enrollment");

if (process.env.MCP_PRIVATE_PROBE_URL) {
  const privateUrl = new URL(process.env.MCP_PRIVATE_PROBE_URL);
  assert(
    privateUrl.protocol === "http:" &&
      privateUrl.hostname === "127.0.0.1" &&
      privateUrl.pathname === "/mcp" &&
      !privateUrl.username &&
      !privateUrl.password &&
      !privateUrl.search &&
      !privateUrl.hash,
    "Private probe must target the local port-forward",
  );
  await probe(
    privateUrl,
    "A reset needs confirm_instance_id to repeat instance_id exactly",
  );
  console.log(
    "PASS: private connection reaches tool validation without starting enrollment",
  );
  const unauthenticated = await fetch(privateUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  assert.equal(unauthenticated.status, 401);
  console.log("PASS: private listener still requires OAuth");
}
