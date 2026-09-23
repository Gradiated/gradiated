import type { RequestListener } from "node:http";
import { describe, expect } from "vitest";
import { HttpStatusError, NetworkError, request } from "../src/http.js";
import { test as it, unreachableUrl } from "./support/http-server.js";
import { rejectionOf } from "./support/rejection.js";

const respondWith =
  (status: number, contentType: string, body: string): RequestListener =>
  (_request, response) => {
    response.writeHead(status, { "content-type": contentType });
    response.end(body);
  };

describe("request", () => {
  it("returns the parsed JSON body", async ({ serve }) => {
    const { baseUrl } = await serve(
      respondWith(200, "application/json", '{"ok":true}'),
    );

    expect((await request(baseUrl)).body).toEqual({ ok: true });
  });

  it("reads the problem code from a problem+json response", async ({
    serve,
  }) => {
    const { baseUrl } = await serve(
      respondWith(
        403,
        "application/problem+json",
        '{"code":"insufficient_balance","detail":"Top up first."}',
      ),
    );

    const error = await rejectionOf(request(baseUrl), HttpStatusError);

    expect(error).toMatchObject({
      status: 403,
      problemCode: "insufficient_balance",
      detail: "Top up first.",
    });
  });

  it("ignores a code field outside problem+json", async ({ serve }) => {
    const { baseUrl } = await serve(
      respondWith(500, "application/json", '{"code":"x"}'),
    );

    expect(await rejectionOf(request(baseUrl), HttpStatusError)).toMatchObject({
      status: 500,
      problemCode: undefined,
    });
  });

  it("cuts a non-JSON error body to 500 characters", async ({ serve }) => {
    const { baseUrl } = await serve(
      respondWith(502, "text/html", "x".repeat(2_000)),
    );

    const error = await rejectionOf(request(baseUrl), HttpStatusError);

    expect(error.detail).toBe("x".repeat(500));
  });

  it("reports a stalled server as a timeout", async ({ serve }) => {
    const { baseUrl } = await serve(() => undefined);

    const error = await rejectionOf(
      request(baseUrl, { timeoutMs: 50 }),
      NetworkError,
    );

    expect(error.reason).toBe("timeout");
  });

  it("reports a body that stalls after the headers as a timeout", async ({
    serve,
  }) => {
    const { baseUrl } = await serve((_request, response) => {
      response.writeHead(200, { "content-type": "application/json" });
      response.write("{");
    });

    const error = await rejectionOf(
      request(baseUrl, { timeoutMs: 100 }),
      NetworkError,
    );

    expect(error.reason).toBe("timeout");
  });

  it("reports a connection reset during the body as a network failure", async ({
    serve,
  }) => {
    const { baseUrl } = await serve((_request, response) => {
      response.writeHead(200, { "content-type": "application/json" });
      response.write("{", () => response.socket?.destroy());
    });

    const error = await rejectionOf(request(baseUrl), NetworkError);

    expect(error.reason).toBe("failure");
  });

  it("reports a refused connection as a network failure", async () => {
    const error = await rejectionOf(
      request(await unreachableUrl()),
      NetworkError,
    );

    expect(error.reason).toBe("failure");
  });
});
