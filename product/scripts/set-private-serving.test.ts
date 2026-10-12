import { describe, expect, it, vi } from "vitest";
import { probeAllocations } from "./set-private-serving.mjs";

describe("private serving qualification", () => {
  it("checks every allocation and refuses redirects through the private endpoint", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(new Response(null, { status: 200 }));
    await probeAllocations("http://private", ["one", "two"], request);
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      "http://private/alloc/one/health",
      "http://private/alloc/two/health",
    ]);
    expect(request.mock.calls[0]?.[1]).not.toHaveProperty("headers");
    expect(request.mock.calls[0]?.[1]).toMatchObject({
      redirect: "error",
    });
  });

  it("refuses qualification when any allocation is unavailable or there are none", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 503 }));
    await expect(
      probeAllocations("http://private", ["one", "two"], request),
    ).rejects.toThrow("Allocation health failed");
    await expect(
      probeAllocations("http://private", [], request),
    ).rejects.toThrow("No available allocations");
  });
});
