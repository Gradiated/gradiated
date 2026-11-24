import { describe, expect, it, vi } from "vitest";

import {
  bootstrapAuthKey,
  claimInstanceName,
  instanceHasDevice,
  instanceTailnet,
  releaseInstanceName,
  tailscaleAuthKey,
} from "../src/tailscale.js";
import { fakeTailnet } from "./support/tailnet.js";

const instance = "019d5a4a-0000-7000-8000-000000000001";

describe("GPU Tailscale auth keys", () => {
  it("issues only a one-time GPU key and revokes it after use", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ access_token: "oauth-token" }))
      .mockResolvedValueOnce(
        Response.json({ key: "tskey-auth-synthetic", id: "key-id" }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 404 }));
    const enrollment = await tailscaleAuthKey(instance, request, async () => ({
      client_id: "id",
      client_secret: "secret",
    }));

    expect(enrollment.key).toBe("tskey-auth-synthetic");
    expect(JSON.parse(request.mock.calls[1]![1]!.body as string)).toEqual({
      capabilities: {
        devices: {
          create: {
            reusable: false,
            ephemeral: false,
            preauthorized: true,
            tags: ["tag:gpu-inference"],
          },
        },
      },
      expirySeconds: 3600,
      description: `GPU ${instance}`,
    });
    await expect(enrollment.revoke()).resolves.toBeUndefined();
    expect(request.mock.calls[2]![0]).toBe(
      "https://api.tailscale.com/api/v2/tailnet/-/keys/key-id",
    );
    expect(request.mock.calls[2]![1]!.method).toBe("DELETE");
  });

  it("issues a one-time tag:gpu-bootstrap key for one RunPod pod", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ access_token: "oauth-token" }))
      .mockResolvedValueOnce(
        Response.json({ key: "tskey-auth-bootstrap", id: "key-id" }),
      );
    const bootstrap = await bootstrapAuthKey(
      "w9hw3ckrz26kua",
      request,
      async () => ({
        client_id: "id",
        client_secret: "secret",
      }),
    );

    expect(bootstrap.key).toBe("tskey-auth-bootstrap");
    expect(JSON.parse(request.mock.calls[1]![1]!.body as string)).toEqual({
      capabilities: {
        devices: {
          create: {
            reusable: false,
            ephemeral: false,
            preauthorized: true,
            tags: ["tag:gpu-bootstrap"],
          },
        },
      },
      expirySeconds: 3600,
      description: "GPU bootstrap w9hw3ckrz26kua",
    });
    await expect(
      bootstrapAuthKey("../keys", request, async () => ({
        client_id: "id",
        client_secret: "secret",
      })),
    ).rejects.toThrow();
  });

  it("withholds OAuth response bodies from failures", async () => {
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValue(
        new Response("credential-bearing response", { status: 403 }),
      );

    await expect(
      tailscaleAuthKey(instance, request, async () => ({
        client_id: "id",
        client_secret: "secret",
      })),
    ).rejects.toThrow("Tailscale OAuth returned 403");
  });
});

describe("GPU tailnet names across a re-image", () => {
  const hostname = `gpu-${instance}`;
  const credentials = async () => ({
    client_id: "id",
    client_secret: "secret",
  });

  it("keeps gpu-<id> when a re-imaged pod rejoins", async () => {
    const tailnet = fakeTailnet();
    const old = tailnet.join(hostname, "tag:gpu-inference");
    tailnet.disconnect(old);
    tailnet.join("gpu-bootstrap-pod1", "tag:gpu-bootstrap");

    await expect(
      releaseInstanceName(instance, tailnet.fetch, credentials),
    ).resolves.toBe(1);
    const since = tailnet.now();
    const promoted = tailnet.join(hostname, "tag:gpu-inference");

    await expect(
      claimInstanceName(instance, since, tailnet.fetch, credentials),
    ).resolves.toBe(promoted.addresses[0]);
    expect(promoted.name).toBe(`${hostname}.tail186117.ts.net`);
    expect(tailnet.devices.has(old.nodeId)).toBe(false);
    expect(
      [...tailnet.devices.values()].map((device) => device.hostname),
    ).toContain("gpu-bootstrap-pod1");
  });

  it("renames a promoted device that joined while the old name was taken", async () => {
    const tailnet = fakeTailnet();
    const old = tailnet.join(hostname, "tag:gpu-inference");
    tailnet.disconnect(old);
    const since = tailnet.now();
    const promoted = tailnet.join(hostname, "tag:gpu-inference");
    expect(promoted.name).toBe(`${hostname}-1.tail186117.ts.net`);

    await expect(
      claimInstanceName(instance, since, tailnet.fetch, credentials),
    ).rejects.toThrow(
      `Another tag:gpu-inference device still uses ${hostname}`,
    );
    tailnet.devices.delete(old.nodeId);
    await expect(
      claimInstanceName(instance, since, tailnet.fetch, credentials),
    ).resolves.toBe(promoted.addresses[0]);
    expect(promoted.name).toBe(`${hostname}.tail186117.ts.net`);
  });

  it("refuses to remove a connected device that holds the name", async () => {
    const tailnet = fakeTailnet();
    const live = tailnet.join(hostname, "tag:gpu-inference");

    await expect(
      releaseInstanceName(instance, tailnet.fetch, credentials),
    ).rejects.toThrow(
      `A connected tag:gpu-inference device already uses ${hostname}`,
    );
    expect(tailnet.devices.has(live.nodeId)).toBe(true);
  });

  it("leaves other hosts and bootstrap devices alone", async () => {
    const tailnet = fakeTailnet();
    const other = tailnet.join(
      "gpu-019d5a4a-0000-7000-8000-000000000002",
      "tag:gpu-inference",
    );
    const bootstrap = tailnet.join("gpu-bootstrap-pod1", "tag:gpu-bootstrap");
    tailnet.disconnect(other);
    tailnet.disconnect(bootstrap);

    await expect(
      releaseInstanceName(instance, tailnet.fetch, credentials),
    ).resolves.toBe(0);
    expect(tailnet.devices.size).toBe(2);
  });

  it("fails while the promoted device has not appeared", async () => {
    const tailnet = fakeTailnet();
    await expect(
      claimInstanceName(instance, tailnet.now(), tailnet.fetch, credentials),
    ).rejects.toThrow("no new tag:gpu-inference device");
  });

  it("reports whether a host's device is connected and when control last saw it", async () => {
    const tailnet = fakeTailnet();
    await expect(
      instanceTailnet(instance, tailnet.fetch, credentials),
    ).resolves.toEqual({ connected: false });

    const device = tailnet.join(hostname, "tag:gpu-inference");
    await expect(
      instanceTailnet(instance, tailnet.fetch, credentials),
    ).resolves.toEqual({ connected: true, address: device.addresses[0] });

    tailnet.disconnect(device);
    const renamed = tailnet.join(hostname, "tag:gpu-inference");
    expect(renamed.name).toBe(`${hostname}-1.tail186117.ts.net`);
    await expect(
      instanceTailnet(instance, tailnet.fetch, credentials),
    ).resolves.toEqual({ connected: true, lastSeen: device.lastSeen });

    tailnet.disconnect(renamed);
    tailnet.join("gpu-bootstrap-pod1", "tag:gpu-bootstrap");
    await expect(
      instanceTailnet(instance, tailnet.fetch, credentials),
    ).resolves.toEqual({ connected: false, lastSeen: renamed.lastSeen });
  });

  it("tells whether a host was ever promoted to gpu-<id>, online or not", async () => {
    const tailnet = fakeTailnet();
    tailnet.join("gpu-bootstrap-pod1", "tag:gpu-bootstrap");
    await expect(
      instanceHasDevice(instance, tailnet.fetch, credentials),
    ).resolves.toBe(false);

    const device = tailnet.join(hostname, "tag:gpu-inference");
    tailnet.disconnect(device);
    await expect(
      instanceHasDevice(instance, tailnet.fetch, credentials),
    ).resolves.toBe(true);
  });
});
