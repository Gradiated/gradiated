import { RunPodError, type RunPodClient } from "@gradiated/gpu-hosts";
import { describe, expect, it } from "vitest";

import { reloadingRunPod } from "../src/access.js";

// A RunPod client whose key RunPod accepts until it is revoked.
const client = (key: string, revoked: Set<string>) =>
  ({
    pod: async (podId: string) => {
      if (revoked.has(key))
        throw new RunPodError(401, "RunPod GET failed: 401");
      return { id: podId, key };
    },
    update: async () => {
      if (revoked.has(key))
        throw new RunPodError(403, "RunPod PATCH failed: 403");
    },
    start: async () => {
      throw new RunPodError(500, "RunPod POST failed: 500");
    },
  }) as unknown as RunPodClient;

describe("RunPod access", () => {
  it("keeps one client while RunPod accepts its key", async () => {
    let loads = 0;
    const access = reloadingRunPod(async () =>
      client(`key-${++loads}`, new Set()),
    );

    await (await access())!.pod("pod1");
    await (await access())!.pod("pod1");

    expect(loads).toBe(1);
  });

  it("reads the key again after RunPod rejects it", async () => {
    const revoked = new Set<string>();
    let key = "old";
    let loads = 0;
    const access = reloadingRunPod(async () => {
      loads++;
      return client(key, revoked);
    });
    await (await access())!.pod("pod1");

    revoked.add("old");
    key = "new";
    await expect((await access())!.pod("pod1")).rejects.toThrow("401");
    expect(await (await access())!.pod("pod1")).toMatchObject({ key: "new" });
    expect(loads).toBe(2);

    revoked.add("new");
    await expect((await access())!.update("pod1", {})).rejects.toThrow("403");
    await access();
    expect(loads).toBe(3);
  });

  it("keeps the client after other RunPod errors", async () => {
    let loads = 0;
    const access = reloadingRunPod(async () =>
      client(`key-${++loads}`, new Set()),
    );

    await expect((await access())!.start("pod1")).rejects.toThrow("500");
    await access();

    expect(loads).toBe(1);
  });

  it("tries again on the next request while no key is stored", async () => {
    let stored: RunPodClient | undefined;
    const access = reloadingRunPod(async () => stored);

    expect(await access()).toBeUndefined();
    stored = client("first", new Set());
    expect(await access()).toBeDefined();
  });
});
