import { describe, expect, it, vi } from "vitest";

import {
  bootstrapAuthKey,
  promotedAddress,
  tailscaleAuthKey,
} from "../../src/instances/tailscale.js";

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

  it("finds the new inference device that re-authentication created", async () => {
    const hostname = `gpu-${instance}`;
    const request = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ access_token: "oauth-token" }))
      .mockResolvedValue(
        Response.json({
          devices: [
            {
              hostname,
              addresses: ["100.75.50.69", "fd7a:115c:a1e0::1"],
              tags: ["tag:gpu-inference"],
              created: "2026-10-19T20:46:30Z",
            },
            {
              hostname: "gpu-bootstrap-pod1",
              addresses: ["100.126.83.106"],
              tags: ["tag:gpu-bootstrap"],
              created: "2026-10-21T11:00:00Z",
            },
            {
              hostname,
              addresses: ["fd7a:115c:a1e0::2", "100.85.29.110"],
              tags: ["tag:gpu-inference"],
              created: "2026-10-21T11:49:20Z",
            },
          ],
        }),
      );
    const credentials = async () => ({
      client_id: "id",
      client_secret: "secret",
    });

    await expect(
      promotedAddress(
        instance,
        new Date("2026-10-21T11:48:52Z"),
        request,
        credentials,
      ),
    ).resolves.toBe("100.85.29.110");
    expect(request.mock.calls[1]![0]).toBe(
      "https://api.tailscale.com/api/v2/tailnet/-/devices",
    );
    await expect(
      promotedAddress(
        instance,
        new Date("2026-10-21T12:00:00Z"),
        vi
          .fn<typeof fetch>()
          .mockResolvedValueOnce(Response.json({ access_token: "oauth-token" }))
          .mockResolvedValueOnce(Response.json({ devices: [] })),
        credentials,
      ),
    ).rejects.toThrow("no new tag:gpu-inference device");
  });
});
