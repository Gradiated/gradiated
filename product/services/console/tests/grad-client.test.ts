import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DeployUnavailableError,
  createGradSession,
  fetchTrainingToken,
  publishArtifactVersion,
  tokenStaleTime,
} from "@/api/grad";
import { ApiError } from "@/api/client";
import { httpStatus } from "@/lib/errors";
import { authorizedFetch } from "@/lib/grad/authorized-fetch";
import {
  signsOutOnUnauthorized,
  trainingAvailability,
} from "@/lib/grad/config";

const API = "https://api.gradiated.test";

interface Sent {
  url: string;
  authorization: string | null;
  lastEventId: string | null;
}

const fakeFetch = (respond: (url: string, attempt: number) => Response) => {
  const sent: Sent[] = [];
  const fetch: typeof globalThis.fetch = async (input, init) => {
    const url = input instanceof Request ? input.url : String(input);
    const headers = new Headers(init?.headers);
    sent.push({
      url,
      authorization: headers.get("Authorization"),
      lastEventId: headers.get("Last-Event-ID"),
    });

    return respond(url, sent.length);
  };

  return { fetch, sent };
};

const tokens = () => {
  const calls: boolean[] = [];
  const token = async (renew: boolean) => {
    calls.push(renew);

    return renew ? "renewed-token" : "first-token";
  };

  return { token, calls };
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("authorizedFetch", () => {
  it("sends the training token to grad's API only", async () => {
    const { fetch, sent } = fakeFetch(() => new Response("{}"));
    const authed = authorizedFetch({
      apiOrigin: API,
      token: tokens().token,
      fetch,
    });

    await authed(`${API}/v1/runs`);
    await authed("https://bucket.s3.amazonaws.com/upload?X-Amz-Signature=abc", {
      method: "PUT",
    });

    expect(sent.map((request) => request.authorization)).toEqual([
      "Bearer first-token",
      null,
    ]);
  });

  it("renews the token once after a 401", async () => {
    const { fetch, sent } = fakeFetch(
      (_, attempt) => new Response("{}", { status: attempt === 1 ? 401 : 200 }),
    );
    const source = tokens();
    const authed = authorizedFetch({
      apiOrigin: API,
      token: source.token,
      fetch,
    });

    const response = await authed(`${API}/v1/runs`);

    expect(response.status).toBe(200);
    expect(source.calls).toEqual([false, true]);
    expect(sent.at(-1)?.authorization).toBe("Bearer renewed-token");
  });

  it("returns a second 401 instead of retrying forever", async () => {
    const { fetch, sent } = fakeFetch(
      () => new Response("{}", { status: 401 }),
    );
    const authed = authorizedFetch({
      apiOrigin: API,
      token: tokens().token,
      fetch,
    });

    expect((await authed(`${API}/v1/runs`)).status).toBe(401);
    expect(sent).toHaveLength(2);
  });

  it("turns a refused token into a 401 the SDK does not retry", async () => {
    const { fetch, sent } = fakeFetch(() => new Response("{}"));
    const authed = authorizedFetch({
      apiOrigin: API,
      token: async () => {
        throw new Error("Not a member of this workspace.");
      },
      fetch,
    });

    const response = await authed(`${API}/v1/runs`);

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({
      code: "training_token_unavailable",
      detail: "Not a member of this workspace.",
    });
    expect(sent).toHaveLength(0);
  });
});

describe("tokenStaleTime", () => {
  it("renews a minute before the token expires", () => {
    const now = Date.parse("2026-11-27T12:00:00Z");

    expect(tokenStaleTime("2026-11-27T12:05:00Z", now)).toBe(4 * 60_000);
    expect(tokenStaleTime("2026-11-27T12:00:30Z", now)).toBe(0);
  });
});

describe("createGradSession", () => {
  it("calls grad through the SDK with the JWT and decodes snake_case", async () => {
    const { fetch, sent } = fakeFetch(() =>
      Response.json({
        data: [{ id: "run_1", dataset_name: "support", cost_usd: 1.5 }],
        next_cursor: null,
      }),
    );
    const { grad } = createGradSession({
      baseURL: `${API}/grad`,
      token: tokens().token,
      fetch,
    });

    const page = await grad.api.listRuns({ limit: 5 });

    expect(sent[0]).toMatchObject({
      url: `${API}/grad/v1/runs?limit=5`,
      authorization: "Bearer first-token",
    });
    expect(page.data[0]).toMatchObject({
      id: "run_1",
      datasetName: "support",
      costUsd: 1.5,
    });
  });

  it("resumes run events after the last seen event", async () => {
    const frame = (seq: number, data: object) =>
      `id: ${seq}\nevent: ${"type" in data ? String(data.type) : ""}\ndata: ${JSON.stringify(data)}\n\n`;
    const body = [
      frame(42, {
        type: "warning",
        run_id: "run_1",
        seq: 42,
        attempt: 1,
        timestamp: "2026-11-27T12:00:00Z",
        step: 10,
        message: "slow",
      }),
      frame(42, {
        type: "completed",
        run_id: "run_1",
        seq: 42,
        attempt: 1,
        timestamp: "2026-11-27T12:00:01Z",
        status: "completed",
        run: { id: "run_1", status: "completed" },
      }),
    ].join("");
    const { fetch, sent } = fakeFetch(
      () =>
        new Response(body, {
          headers: { "Content-Type": "text/event-stream" },
        }),
    );
    const { grad } = createGradSession({
      baseURL: API,
      token: tokens().token,
      fetch,
    });
    const seen: string[] = [];

    for await (const event of grad.runs.events("run_1", {
      follow: true,
      headers: { "Last-Event-ID": "41" },
    })) {
      seen.push(event.type);
    }

    expect(sent[0]?.lastEventId).toBe("41");
    expect(seen).toEqual(["warning", "completed"]);
  });

  it("reads the usage summary through the SDK", async () => {
    const { fetch, sent } = fakeFetch(() =>
      Response.json({
        from: "2026-11-01T00:00:00Z",
        to: "2026-11-28T00:00:00Z",
        cost_usd: 12.5,
        tokens: 1000,
        records: 3,
        by_kind: [
          { kind: "training", cost_usd: 12.5, tokens: 1000, records: 3 },
        ],
        top_runs: [
          {
            id: "run_1",
            name: "support",
            kind: "training",
            cost_usd: 12.5,
            tokens: 1000,
          },
        ],
        top_evals: [],
        group_by: "model",
        groups: [{ key: "qwen3-8b", cost_usd: 12.5, tokens: 1000, records: 3 }],
      }),
    );
    const session = createGradSession({
      baseURL: API,
      token: tokens().token,
      fetch,
    });

    const summary = await session.grad.api.getUsageSummary({
      from: "2026-11-01",
      to: "2026-11-27",
      groupBy: "model",
    });

    expect(sent[0]?.url).toBe(
      `${API}/v1/usage/summary?from=2026-11-01&to=2026-11-27&group_by=model`,
    );
    expect(summary).toMatchObject({
      costUsd: 12.5,
      byKind: [{ kind: "training", costUsd: 12.5 }],
      topRuns: [{ id: "run_1", costUsd: 12.5 }],
      groups: [{ key: "qwen3-8b", costUsd: 12.5 }],
    });
  });

  it("raises the SDK's error for a failed usage summary", async () => {
    const { fetch } = fakeFetch(() =>
      Response.json(
        { code: "forbidden", detail: "Missing scope runs:read" },
        { status: 403 },
      ),
    );
    const session = createGradSession({
      baseURL: API,
      token: tokens().token,
      fetch,
    });

    await expect(
      session.grad.api.getUsageSummary({
        from: "2026-11-01",
        to: "2026-11-27",
        groupBy: "day",
      }),
    ).rejects.toMatchObject({ status: 403, code: "forbidden" });
  });

  it("gets a presigned download URL and never sends the token to storage", async () => {
    const { fetch, sent } = fakeFetch((url) =>
      url.startsWith(API)
        ? Response.json({
            url: "https://bucket.s3.amazonaws.com/artifacts/ws/abc?X-Amz-Signature=sig",
            expires_at: "2026-11-28T12:15:00Z",
            sha256: "a".repeat(64),
            size_bytes: 10,
            filename: "support@2026-11-26-1.grad.tar.gz",
          })
        : new Response("bundle"),
    );
    const session = createGradSession({
      baseURL: API,
      token: tokens().token,
      fetch,
    });

    const download = await session.grad.api.getArtifactDownloadUrl(
      "support@2026-11-26-1",
    );
    await session.fetch(download.url);

    expect(sent[0]?.url).toBe(
      `${API}/v1/artifacts/support%402026-11-26-1/download-url`,
    );
    expect(sent[0]?.authorization).toBe("Bearer first-token");
    expect(sent[1]?.authorization).toBeNull();
  });
});

describe("product API calls", () => {
  it("fetches a training token for the workspace", async () => {
    const fetch = vi.fn(async () =>
      Response.json({ token: "jwt", expires_at: "2026-11-27T12:05:00Z" }),
    );
    vi.stubGlobal("fetch", fetch);

    await expect(fetchTrainingToken("ws-1")).resolves.toEqual({
      token: "jwt",
      expires_at: "2026-11-27T12:05:00Z",
    });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/training-tokens",
      { method: "POST", credentials: "include" },
    );
  });

  it("reports a refused token as an ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ detail: "Not a member" }, { status: 403 }),
      ),
    );

    await expect(fetchTrainingToken("ws-1")).rejects.toBeInstanceOf(ApiError);
  });

  it.each([405, 501])(
    "treats %i from publish as not available yet",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => new Response(null, { status })),
      );

      await expect(
        publishArtifactVersion({
          workspaceId: "ws-1",
          model: "support",
          artifactId: "art_1",
          version: "2026-11-26-1",
          idempotencyKey: "key",
        }),
      ).rejects.toBeInstanceOf(DeployUnavailableError);
    },
  );

  it("shows a 404 from publish as the server's answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          { code: "not_found", detail: "The artifact was not found." },
          { status: 404 },
        ),
      ),
    );

    await expect(
      publishArtifactVersion({
        workspaceId: "ws-1",
        model: "support",
        artifactId: "support@2026-11-26-1",
        version: "2026-11-26-1",
        idempotencyKey: "key",
      }),
    ).rejects.toMatchObject({
      status: 404,
      message: "The artifact was not found.",
    });
  });

  it("publishes an artifact as a model version", async () => {
    const fetch = vi.fn(async (_url: string, _init: RequestInit) =>
      Response.json(
        {
          id: "ver_1",
          name: "2026-11-26-1",
          status: "unavailable",
          qualification: { outcome: "pending" },
        },
        { status: 201 },
      ),
    );
    vi.stubGlobal("fetch", fetch);

    await expect(
      publishArtifactVersion({
        workspaceId: "ws-1",
        model: "support",
        artifactId: "support@2026-11-26-1",
        version: "2026-11-26-1",
        idempotencyKey: "key",
      }),
    ).resolves.toEqual({
      id: "ver_1",
      name: "2026-11-26-1",
      qualification: { outcome: "pending" },
    });

    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/workspaces/ws-1/tasks/support/versions");
    expect(new Headers(init?.headers).get("Idempotency-Key")).toBe("key");
    expect(JSON.parse(String(init?.body))).toEqual({
      artifact: "support@2026-11-26-1",
      name: "2026-11-26-1",
    });
  });

  it("surfaces publish refusals such as a taken model name", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          {
            code: "model_name_taken",
            detail: "Another workspace owns this name.",
          },
          { status: 409 },
        ),
      ),
    );

    await expect(
      publishArtifactVersion({
        workspaceId: "ws-1",
        model: "support",
        artifactId: "art_1",
        version: "v1",
        idempotencyKey: "key",
      }),
    ).rejects.toMatchObject({ status: 409, code: "model_name_taken" });
  });
});

describe("training availability", () => {
  it("is off without grad's URL, whatever the flag says", () => {
    expect(trainingAvailability(true, undefined)).toBe(false);
    expect(trainingAvailability("loading", undefined)).toBe(false);
    expect(trainingAvailability(true, "https://api.gradiated.com")).toBe(true);
    expect(trainingAvailability(false, "https://api.gradiated.com")).toBe(
      false,
    );
    expect(trainingAvailability("loading", "https://api.gradiated.com")).toBe(
      "loading",
    );
  });
});

describe("401s from grad", () => {
  it("never sign the member out of the console", async () => {
    const { fetch } = fakeFetch(() =>
      Response.json(
        { code: "invalid_token", detail: "The token was refused." },
        { status: 401 },
      ),
    );
    const session = createGradSession({
      baseURL: API,
      token: tokens().token,
      fetch,
    });

    const error: unknown = await session.grad.api
      .listRuns({})
      .catch((failure: unknown) => failure);

    expect(httpStatus(error)).toBe(401);
    expect(signsOutOnUnauthorized(error)).toBe(false);
    expect(signsOutOnUnauthorized(new ApiError(401, {}))).toBe(true);
  });
});
