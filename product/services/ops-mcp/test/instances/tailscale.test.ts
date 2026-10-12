import { describe, expect, it, vi } from "vitest";

import { tailscaleAuthKey } from "../../src/instances/tailscale.js";

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
    ).rejects.toThrow("GPU enrollment OAuth returned 403");
  });
});
