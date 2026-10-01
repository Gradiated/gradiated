import { expect, it, vi } from "vitest";
import { ProxyProcess } from "./support/proxy-process.js";

it("waits for a new catalog snapshot despite a delayed metrics response", async () => {
  vi.useFakeTimers();
  vi.setSystemTime(5020);
  const metrics = vi
    .fn()
    .mockImplementationOnce(async () => {
      vi.setSystemTime(5100);
      return new Map([["gradiated_proxy_catalog_age_seconds", 0.025]]);
    })
    .mockResolvedValue(
      new Map([["gradiated_proxy_catalog_age_seconds", 0.005]]),
    );
  let refreshed = false;
  const proxy = Object.assign(Object.create(ProxyProcess.prototype), {
    metrics,
  }) as ProxyProcess;
  const waiting = proxy.catalogRefreshedAfter(5010).then(() => {
    refreshed = true;
  });

  try {
    await vi.advanceTimersByTimeAsync(0);
    expect(refreshed).toBe(false);
    expect(metrics).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(20);
    await waiting;
    expect(metrics).toHaveBeenCalledTimes(2);
  } finally {
    vi.useRealTimers();
  }
});
