import { describe, expect, it, vi } from "vitest";
import { readBaseModelConfiguration } from "../src/training/base-model-configuration.js";

const repo = "test/base";
const revision = "a".repeat(40);
const response = (body: unknown) => new Response(JSON.stringify(body));

describe("immutable base configuration", () => {
  it("reads the requested repository and exact revision with a deadline", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(response({ num_hidden_layers: 28 }));
    expect(await readBaseModelConfiguration(repo, revision, fetcher)).toEqual({
      layerCount: 28,
      expertCount: 0,
    });
    expect(String(fetcher.mock.calls[0]![0])).toBe(
      `https://huggingface.co/${repo}/resolve/${revision}/config.json`,
    );
    expect(fetcher.mock.calls[0]![1]).toMatchObject({
      redirect: "manual",
      signal: expect.any(AbortSignal),
    });
  });
  it("uses the text configuration for multimodal bases", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      response({
        num_hidden_layers: 99,
        text_config: { num_hidden_layers: 40 },
      }),
    );
    expect(await readBaseModelConfiguration(repo, revision, fetcher)).toEqual({
      layerCount: 40,
      expertCount: 0,
    });
  });
  it("derives expert counts using the serving configuration precedence", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response({
          num_hidden_layers: 32,
          n_routed_experts: 4,
          num_local_experts: 8,
        }),
      )
      .mockResolvedValueOnce(
        response({ num_hidden_layers: 32, num_local_experts: 8 }),
      );
    expect(await readBaseModelConfiguration(repo, revision, fetcher)).toEqual({
      layerCount: 32,
      expertCount: 4,
    });
    expect(await readBaseModelConfiguration(repo, revision, fetcher)).toEqual({
      layerCount: 32,
      expertCount: 8,
    });
  });
  it("follows bounded same-origin Hugging Face cache redirects", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(null, {
          status: 307,
          headers: {
            location: `/api/resolve-cache/models/${repo}/${revision}/config.json`,
          },
        }),
      )
      .mockResolvedValueOnce(response({ num_hidden_layers: 32 }));
    expect(await readBaseModelConfiguration(repo, revision, fetcher)).toEqual({
      layerCount: 32,
      expertCount: 0,
    });
    expect(String(fetcher.mock.calls[1]![0])).toBe(
      `https://huggingface.co/api/resolve-cache/models/${repo}/${revision}/config.json`,
    );
  });
  it("rejects redirects to other origins without requesting them", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: { location: "http://169.254.169.254/latest/meta-data" },
      }),
    );
    await expect(
      readBaseModelConfiguration(repo, revision, fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it("rejects redirect loops, mutable revisions and invalid repositories", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockImplementation(
        async () =>
          new Response(null, { status: 307, headers: { location: "/loop" } }),
      );
    await expect(
      readBaseModelConfiguration(repo, revision, fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
    expect(fetcher).toHaveBeenCalledTimes(4);
    fetcher.mockClear();
    await expect(
      readBaseModelConfiguration(repo, "main", fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
    await expect(
      readBaseModelConfiguration("../private", revision, fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
    expect(fetcher).not.toHaveBeenCalled();
  });
  it.each([{}, { num_hidden_layers: 0 }, { num_hidden_layers: 4097 }])(
    "rejects unsupported model configurations: %j",
    async (body) => {
      const fetcher = vi.fn<typeof fetch>().mockResolvedValue(response(body));
      await expect(
        readBaseModelConfiguration(repo, revision, fetcher),
      ).rejects.toMatchObject({ code: "unavailable" });
    },
  );
  it("bounds streamed configuration bytes even without a declared length", async () => {
    const cancelled = vi.fn();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array(1024 * 1024));
        controller.enqueue(new Uint8Array(1));
      },
      cancel: cancelled,
    });
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(stream));
    await expect(
      readBaseModelConfiguration(repo, revision, fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
    expect(cancelled).toHaveBeenCalledOnce();
  });
  it("fails closed on missing revisions and transport errors", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockRejectedValueOnce(new Error("Network unavailable"));
    await expect(
      readBaseModelConfiguration(repo, revision, fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
    await expect(
      readBaseModelConfiguration(repo, revision, fetcher),
    ).rejects.toMatchObject({ code: "unavailable" });
  });
});
