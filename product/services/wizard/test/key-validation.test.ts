import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { validateKey } from "../src/key.js";
import * as ui from "../src/ui.js";

const progress = vi.hoisted(() => ({ start: vi.fn(), stop: vi.fn() }));
vi.mock("../src/ui.js", () => ({
  spinner: () => progress,
  askPassword: vi.fn(),
}));

let server: Server;
let baseUrl: string;
let failureStatus: number;
let attempts: string[];

beforeEach(async () => {
  vi.resetAllMocks();
  attempts = [];
  failureStatus = 401;
  server = createServer((request, response) => {
    attempts.push(request.headers.authorization ?? "");
    if (request.headers.authorization === "Bearer grad_valid_fixture") {
      response.setHeader("content-type", "application/json");
      response.end(
        JSON.stringify({
          data: [{ id: "fixture/model", name: "Fixture model" }],
        }),
      );
    } else {
      // Reproduce the user's empty unauthorized response, not a friendly fixture error.
      response.writeHead(failureStatus).end();
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterEach(async () => {
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});

describe("API key validation and retry", () => {
  it("retries multiple invalid keys and returns only the accepted key", async () => {
    vi.mocked(ui.askPassword)
      .mockResolvedValueOnce("grad_another_invalid_fixture")
      .mockResolvedValueOnce("grad_valid_fixture");
    const result = await validateKey("grad_invalid_fixture", baseUrl, true);
    expect(result.apiKey).toBe("grad_valid_fixture");
    expect(result.models[0]?.id).toBe("fixture/model");
    expect(attempts).toEqual([
      "Bearer grad_invalid_fixture",
      "Bearer grad_another_invalid_fixture",
      "Bearer grad_valid_fixture",
    ]);
    expect(progress.stop.mock.calls).toEqual([
      ["API key invalid.", 1],
      ["API key invalid.", 1],
      ["1 model available"],
    ]);
    expect(ui.askPassword).toHaveBeenCalledTimes(2);
    expect(ui.askPassword).toHaveBeenCalledWith(
      "Paste a different API key (Ctrl+C to cancel):",
    );
    expect(JSON.stringify(progress.stop.mock.calls)).not.toContain("grad_");
  });

  it("does not prompt when the first key is valid", async () => {
    expect(
      (await validateKey("grad_valid_fixture", baseUrl, true)).apiKey,
    ).toBe("grad_valid_fixture");
    expect(ui.askPassword).not.toHaveBeenCalled();
  });

  it("exits clearly without prompting for non-interactive callers", async () => {
    await expect(
      validateKey("grad_invalid_fixture", baseUrl, false),
    ).rejects.toThrow("API key invalid.");
    expect(ui.askPassword).not.toHaveBeenCalled();
    expect(attempts).toHaveLength(1);
  });

  it.each([403, 429, 503])(
    "does not mislabel HTTP %s as an invalid key or retry it",
    async (status) => {
      failureStatus = status;
      await expect(
        validateKey("grad_invalid_fixture", baseUrl, true),
      ).rejects.toThrow(`Could not fetch the model catalog (${status})`);
      expect(ui.askPassword).not.toHaveBeenCalled();
      expect(attempts).toHaveLength(1);
    },
  );

  it("allows cancellation at the replacement prompt without another request", async () => {
    const cancelled = new Error("fixture cancellation");
    vi.mocked(ui.askPassword).mockRejectedValue(cancelled);
    await expect(
      validateKey("grad_invalid_fixture", baseUrl, true),
    ).rejects.toBe(cancelled);
    expect(attempts).toHaveLength(1);
  });
});
