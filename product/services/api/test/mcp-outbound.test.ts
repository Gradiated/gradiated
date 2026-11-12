import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  createOutboundFetch,
  isPublicAddress,
  OutboundError,
} from "../src/mcp/outbound.js";

describe("isPublicAddress", () => {
  it.each([
    "127.0.0.1",
    "10.1.2.3",
    "172.16.0.1",
    "192.168.1.1",
    "169.254.169.254",
    "100.64.0.1",
    "0.0.0.0",
    "::1",
    "::",
    "fd00::1",
    "fe80::1",
    "::ffff:127.0.0.1",
    "::ffff:10.0.0.1",
    "not-an-address",
  ])("rejects %s", (address) => {
    expect(isPublicAddress(address)).toBe(false);
  });

  it.each(["1.1.1.1", "34.120.1.1", "2606:4700:4700::1111", "::ffff:8.8.8.8"])(
    "accepts %s",
    (address) => {
      expect(isPublicAddress(address)).toBe(true);
    },
  );
});

describe("createOutboundFetch", () => {
  let server: Server;
  let port: number;

  beforeAll(async () => {
    server = createServer((request, response) => {
      if (request.url === "/redirect") {
        response.writeHead(302, { Location: "http://169.254.169.254/" });
        response.end();
        return;
      }
      if (request.url === "/large") {
        response.end("x".repeat(5 * 1024 * 1024));
        return;
      }
      response.end("ok");
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    port = (server.address() as AddressInfo).port;
  });

  afterAll(() => new Promise((resolve) => server.close(resolve)));

  const guarded = createOutboundFetch({ allowPrivateNetworks: false });
  const local = createOutboundFetch({ allowPrivateNetworks: true });

  it.each([
    ["http://example.com/mcp", "MCP servers must use HTTPS."],
    ["https://127.0.0.1/mcp", "127.0.0.1 is not a public address."],
    ["https://[::1]/mcp", "[::1] is not a public address."],
    [
      "https://localhost/mcp",
      "localhost does not resolve to a public address.",
    ],
  ])("refuses %s", async (url, message) => {
    await expect(guarded(url)).rejects.toThrow(message);
  });

  it("refuses redirects", async () => {
    await expect(local(`http://127.0.0.1:${port}/redirect`)).rejects.toThrow(
      OutboundError,
    );
  });

  it("bounds the response size", async () => {
    const response = await local(`http://127.0.0.1:${port}/large`);

    await expect(response.text()).rejects.toThrow();
  });

  it("reaches private addresses only when allowed", async () => {
    expect(await (await local(`http://127.0.0.1:${port}/`)).text()).toBe("ok");
  });
});
