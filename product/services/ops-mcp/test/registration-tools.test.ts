import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AddressInfo } from "node:net";

import type {
  Registration,
  Registrations,
} from "../src/instances/registration.js";
import { callTool, closeServers, setup } from "./support/mcp.js";

afterEach(closeServers);

const registration: Registration = {
  id: "0199a1b2-0000-4000-8000-000000000001",
  provider: "runpod",
  providerInstanceId: "rldmcif788b98e",
  sku: "1x NVIDIA RTX PRO 6000",
  requestedBy: "tester@gradiated.com",
  resetRunningPod: false,
  resuming: false,
  startedAt: "2026-09-28T10:00:00.000Z",
  updatedAt: "2026-09-28T10:00:00.000Z",
  phase: "recording",
};

const fakeRegistrations = (started: Registration = registration) => {
  const start = vi.fn(async () => started);

  return {
    start,
    registrations: {
      start,
      get: vi.fn((id: string) =>
        id === registration.id ? registration : undefined,
      ),
      list: vi.fn(() => [registration]),
    } as unknown as Registrations,
  };
};

const listTools = async (registrations?: Registrations) => {
  const { url, headers } = await setup(registrations ? { registrations } : {});
  const client = new Client({ name: "test", version: "1" });
  await client.connect(
    new StreamableHTTPClientTransport(url, { requestInit: { headers } }),
  );
  const { tools } = await client.listTools();
  await client.close();

  return tools;
};

describe("registration tools", () => {
  it("keeps private authorization scoped to the listener for each request", async () => {
    const fake = fakeRegistrations();
    const { app, url, headers, audit } = await setup({
      registrations: fake.registrations,
    });
    await new Promise<void>((resolve) =>
      app.privateServer.listen(0, "127.0.0.1", resolve),
    );
    const privateUrl = new URL(
      `http://127.0.0.1:${(app.privateServer.address() as AddressInfo).port}/mcp`,
    );

    for (const endpoint of [privateUrl, url]) {
      const client = new Client({ name: "test", version: "1" });
      await client.connect(
        new StreamableHTTPClientTransport(endpoint, {
          requestInit: { headers },
        }),
      );
      const result = await client.callTool({
        name: "register_instance",
        arguments: { provider: "runpod", instance_id: "rldmcif788b98e" },
      });

      expect(Boolean(result.isError)).toBe(endpoint === url);
      await client.close();
    }

    expect(fake.start).toHaveBeenCalledTimes(1);
    expect(audit).toHaveBeenCalledWith(
      expect.objectContaining({
        tool: "register_instance",
        outcome: "success",
        ingress: "private",
      }),
    );
  });

  it("rejects public enrollment even with forged private-network headers", async () => {
    const fake = fakeRegistrations();
    const { url, headers, audit } = await setup({
      registrations: fake.registrations,
    });
    const client = new Client({ name: "test", version: "1" });
    await client.connect(
      new StreamableHTTPClientTransport(url, {
        requestInit: {
          headers: {
            ...headers,
            "x-forwarded-for": "100.64.0.1, 127.0.0.1",
            "tailscale-user-login": "tester@gradiated.com",
            "x-mcp-ingress": "private",
          },
        },
      }),
    );

    const result = await client.callTool({
      name: "register_instance",
      arguments: { provider: "runpod", instance_id: "rldmcif788b98e" },
    });

    expect(result.isError).toBe(true);
    expect(JSON.stringify(result.content)).toContain(
      "private administrative MCP connection",
    );
    expect(fake.start).not.toHaveBeenCalled();
    expect(audit).toHaveBeenCalledWith(
      expect.objectContaining({
        tool: "register_instance",
        outcome: "error",
        ingress: "public",
      }),
    );

    const status = await client.callTool({
      name: "instance_registration_status",
      arguments: {},
    });
    expect(status.isError).not.toBe(true);
    await client.close();
  });

  it("requires OAuth on the private listener too", async () => {
    const fake = fakeRegistrations();
    const { url, headers } = await setup({
      registrations: fake.registrations,
      privateConnection: true,
    });
    const response = await fetch(url, {
      method: "POST",
      headers: { ...headers, authorization: "Bearer invalid" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: {
          name: "register_instance",
          arguments: { provider: "runpod", instance_id: "rldmcif788b98e" },
        },
      }),
    });

    expect(response.status).toBe(401);
    expect(fake.start).not.toHaveBeenCalled();
  });

  it("marks registration as the one destructive tool and its status as read-only", async () => {
    const tools = await listTools(fakeRegistrations().registrations);
    const annotations = (name: string) =>
      tools.find((tool) => tool.name === name)?.annotations;

    expect(annotations("register_instance")).toMatchObject({
      readOnlyHint: false,
      destructiveHint: true,
    });
    expect(annotations("instance_registration_status")).toMatchObject({
      readOnlyHint: true,
    });
    expect(
      tools.filter((tool) => tool.annotations?.readOnlyHint === false),
    ).toHaveLength(1);
  });

  it("offers no registration tools when registration is not configured", async () => {
    const names = (await listTools()).map((tool) => tool.name);

    expect(names).not.toContain("register_instance");
    expect(names).not.toContain("instance_registration_status");
  });

  it("starts a registration on behalf of the signed-in person", async () => {
    const fake = fakeRegistrations();

    const { body, isError } = await callTool(
      "register_instance",
      { provider: "runpod", instance_id: "rldmcif788b98e" },
      undefined,
      { registrations: fake.registrations, privateConnection: true },
    );

    expect(isError).toBe(false);
    expect(fake.start).toHaveBeenCalledWith({
      provider: "runpod",
      providerInstanceId: "rldmcif788b98e",
      resetRunningPod: false,
      requestedBy: "tester@gradiated.com",
    });
    expect(body).toEqual({ registration });
  });

  it("starts a registration of an EC2 instance", async () => {
    const fake = fakeRegistrations({
      ...registration,
      provider: "aws",
      providerInstanceId: "i-0123456789abcdef0",
      sku: "1x L4",
    });

    const { isError } = await callTool(
      "register_instance",
      { provider: "aws", instance_id: "i-0123456789abcdef0" },
      undefined,
      { registrations: fake.registrations, privateConnection: true },
    );

    expect(isError).toBe(false);
    expect(fake.start).toHaveBeenCalledWith({
      provider: "aws",
      providerInstanceId: "i-0123456789abcdef0",
      resetRunningPod: false,
      requestedBy: "tester@gradiated.com",
    });
  });

  it("warns that an authorized reset stops the machine", async () => {
    const fake = fakeRegistrations({ ...registration, resetRunningPod: true });

    const { body } = await callTool(
      "register_instance",
      {
        provider: "runpod",
        instance_id: "rldmcif788b98e",
        reset_running_pod: true,
        confirm_instance_id: "rldmcif788b98e",
      },
      undefined,
      { registrations: fake.registrations, privateConnection: true },
    );

    expect(fake.start).toHaveBeenCalledWith(
      expect.objectContaining({ resetRunningPod: true }),
    );
    expect(body).toMatchObject({
      warning: expect.stringContaining("is being reset"),
    });
  });

  it.each([
    [{ reset_running_pod: true }],
    [{ reset_running_pod: true, confirm_instance_id: "another-pod" }],
  ])("refuses a reset without the machine id confirmed: %o", async (reset) => {
    const fake = fakeRegistrations();

    const { body, isError } = await callTool(
      "register_instance",
      { provider: "runpod", instance_id: "rldmcif788b98e", ...reset },
      undefined,
      { registrations: fake.registrations, privateConnection: true },
    );

    expect(isError).toBe(true);
    expect(body).toEqual({
      error: "A reset needs confirm_instance_id to repeat instance_id exactly",
    });
    expect(fake.start).not.toHaveBeenCalled();
  });

  it.each([
    { provider: "gcp", instance_id: "abc123" },
    { provider: "aws", instance_id: "i-123" },
    { provider: "aws", instance_id: "rldmcif788b98e" },
    { provider: "runpod", instance_id: "i-0123456789abcdef0" },
    { provider: "runpod", instance_id: "pod/../x" },
    { provider: "runpod" },
  ])("rejects invalid arguments before starting: %o", async (args) => {
    const fake = fakeRegistrations();

    const { isError } = await callTool("register_instance", args, undefined, {
      registrations: fake.registrations,
      privateConnection: true,
    });

    expect(isError).toBe(true);
    expect(fake.start).not.toHaveBeenCalled();
  });

  it("returns the workflow's refusal to the caller", async () => {
    const fake = fakeRegistrations();
    fake.start.mockRejectedValue(
      new Error("pod1 is running; reset_running_pod"),
    );

    const { body, isError, audit } = await callTool(
      "register_instance",
      { provider: "runpod", instance_id: "pod1" },
      undefined,
      { registrations: fake.registrations, privateConnection: true },
    );

    expect(isError).toBe(true);
    expect(body).toEqual({ error: "pod1 is running; reset_running_pod" });
    expect(audit).toHaveBeenCalledWith(
      expect.objectContaining({
        tool: "register_instance",
        outcome: "error",
        email: "tester@gradiated.com",
      }),
    );
  });

  it.each([
    [{ registration_id: registration.id }, registration],
    [{}, [registration]],
  ])("reports status for %o", async (args, expected) => {
    const { body } = await callTool(
      "instance_registration_status",
      args,
      undefined,
      { registrations: fakeRegistrations().registrations },
    );

    expect(body).toEqual(expected);
  });

  it("reports an unknown registration id", async () => {
    const { body, isError } = await callTool(
      "instance_registration_status",
      { registration_id: "0199a1b2-0000-4000-8000-000000000009" },
      undefined,
      { registrations: fakeRegistrations().registrations },
    );

    expect(isError).toBe(true);
    expect(body).toEqual({ error: "Unknown registration id" });
  });
});
