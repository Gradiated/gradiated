import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { afterEach, describe, expect, it, vi } from "vitest";

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
      { registrations: fake.registrations },
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
      { registrations: fake.registrations },
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
      { registrations: fake.registrations },
    );

    expect(isError).toBe(true);
    expect(body).toEqual({
      error: "A reset needs confirm_instance_id to repeat instance_id exactly",
    });
    expect(fake.start).not.toHaveBeenCalled();
  });

  it.each([
    { provider: "aws", instance_id: "i-123" },
    { provider: "runpod", instance_id: "pod/../x" },
    { provider: "runpod" },
  ])("rejects invalid arguments before starting: %o", async (args) => {
    const fake = fakeRegistrations();

    const { isError } = await callTool("register_instance", args, undefined, {
      registrations: fake.registrations,
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
      { registrations: fake.registrations },
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
