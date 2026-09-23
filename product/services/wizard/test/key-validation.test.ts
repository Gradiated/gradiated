import { beforeEach, describe, expect, vi } from "vitest";
import { validateKey } from "../src/key.js";
import * as ui from "../src/ui.js";
import {
  API_KEY,
  DEFAULT_MODEL,
  REJECTED_KEY,
  ROTATED_KEY,
} from "./support/catalog.js";
import { test } from "./support/gradiated-api.js";
import { unreachableUrl } from "./support/http-server.js";
import { progress } from "./support/ui-stub.js";

vi.mock("../src/ui.js", () => import("./support/ui-stub.js"));

const it = test.extend("api", async ({ serveGradiatedApi }) =>
  serveGradiatedApi({ acceptedKeys: [API_KEY] }),
);

const interactive = (apiBaseUrl: string) => ({ apiBaseUrl, interactive: true });

beforeEach(() => {
  vi.resetAllMocks();
});

describe("API key validation and retry", () => {
  it("retries multiple invalid keys and returns only the accepted key", async ({
    api,
  }) => {
    vi.mocked(ui.askPassword)
      .mockResolvedValueOnce(ROTATED_KEY)
      .mockResolvedValueOnce(API_KEY);

    const result = await validateKey(REJECTED_KEY, interactive(api.baseUrl));

    expect(result.apiKey).toBe(API_KEY);
    expect(result.models[0].id).toBe(DEFAULT_MODEL);
    expect(api.authorizations).toEqual([
      `Bearer ${REJECTED_KEY}`,
      `Bearer ${ROTATED_KEY}`,
      `Bearer ${API_KEY}`,
    ]);
    expect(progress.stop.mock.calls).toEqual([
      ["API key invalid.", 1],
      ["API key invalid.", 1],
      ["2 models available"],
    ]);
    expect(ui.askPassword).toHaveBeenCalledTimes(2);
    expect(ui.askPassword).toHaveBeenCalledWith(
      "Paste a different API key (Ctrl+C to cancel):",
    );
    expect(JSON.stringify(progress.stop.mock.calls)).not.toContain("grad_");
  });

  it("does not prompt when the first key is valid", async ({ api }) => {
    expect((await validateKey(API_KEY, interactive(api.baseUrl))).apiKey).toBe(
      API_KEY,
    );
    expect(ui.askPassword).not.toHaveBeenCalled();
  });

  it("exits clearly without prompting for non-interactive callers", async ({
    api,
  }) => {
    await expect(
      validateKey(REJECTED_KEY, {
        apiBaseUrl: api.baseUrl,
        interactive: false,
      }),
    ).rejects.toThrow("API key invalid.");
    expect(ui.askPassword).not.toHaveBeenCalled();
    expect(api.authorizations).toHaveLength(1);
  });

  it.for([403, 429, 503])(
    "does not mislabel HTTP %s as an invalid key or retry it",
    async (status, { serveGradiatedApi }) => {
      const api = await serveGradiatedApi({
        acceptedKeys: [API_KEY],
        catalogStatus: status,
      });

      await expect(
        validateKey(API_KEY, interactive(api.baseUrl)),
      ).rejects.toThrow(`Could not fetch the model catalog (${status})`);
      expect(ui.askPassword).not.toHaveBeenCalled();
      expect(api.authorizations).toHaveLength(1);
    },
  );

  it("allows cancellation at the replacement prompt without another request", async ({
    api,
  }) => {
    const cancelled = new Error("fixture cancellation");
    vi.mocked(ui.askPassword).mockRejectedValue(cancelled);

    await expect(
      validateKey(REJECTED_KEY, interactive(api.baseUrl)),
    ).rejects.toBe(cancelled);
    expect(api.authorizations).toHaveLength(1);
  });

  it("reports an unreachable API as a service failure, not an invalid key", async () => {
    const attempt = validateKey(API_KEY, interactive(await unreachableUrl()));

    await expect(attempt).rejects.toThrow(
      "Could not fetch the model catalog: The request could not reach the server.",
    );
    expect(progress.stop).toHaveBeenCalledWith(
      "Could not fetch the model catalog",
      1,
    );
    expect(ui.askPassword).not.toHaveBeenCalled();
  });
});
