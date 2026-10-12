import { describe, expect, it, vi } from "vitest";
import { probeAllocations, publicServingUrl } from "./set-private-serving.mjs";

describe("private serving qualification", () => {
  it("accepts mixed-case provider IDs for public rollback without accepting arbitrary hosts", () => {
    expect(
      publicServingUrl({
        provider: "runpod",
        providerInstanceId: "RldmCif788b98e",
      }),
    ).toBe("https://rldmcif788b98e-8888.proxy.runpod.net");
    expect(() =>
      publicServingUrl({ provider: "runpod", providerInstanceId: "pod.evil" }),
    ).toThrow();
    expect(() =>
      publicServingUrl({ provider: "other", providerInstanceId: "pod" }),
    ).toThrow();
  });
  it("checks every allocation and refuses redirects with authenticated health requests", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 200 }));
    await probeAllocations(
      "http://private",
      ["one", "two"],
      "synthetic-token",
      request,
    );
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      "http://private/alloc/one/health",
      "http://private/alloc/two/health",
    ]);
    expect(request.mock.calls[0]?.[1]).toMatchObject({
      headers: { authorization: "Bearer synthetic-token" },
      redirect: "error",
    });
  });

  it("refuses qualification when any allocation is unavailable or there are none", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 503 }));
    await expect(
      probeAllocations(
        "http://private",
        ["one", "two"],
        "synthetic-token",
        request,
      ),
    ).rejects.toThrow("Allocation health failed");
    await expect(
      probeAllocations("http://private", [], "synthetic-token", request),
    ).rejects.toThrow("No available allocations");
  });
});
