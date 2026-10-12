import { z } from "zod";

import { readSecret } from "./aws.js";

const API = "https://api.tailscale.com/api/v2";
const SECRET = "gradiated/prod/platform/tailscale-gpu-enrollment";

export const gpuService = (instanceId: string, tailscaleIp: string) => ({
  apiVersion: "v1",
  kind: "Service",
  metadata: {
    name: `gpu-${z.uuid().parse(instanceId)}`,
    namespace: "tailscale-inference",
    annotations: {
      "tailscale.com/tailnet-ip": tailscaleIp,
      "tailscale.com/proxy-group": "inference-egress",
    },
  },
  spec: {
    type: "ExternalName",
    externalName: "unused",
    ports: [{ name: "inference", port: 8888, protocol: "TCP" }],
  },
});

export const tailscaleAuthKey = async (
  instanceId: string,
  request: typeof fetch = fetch,
  credentials = () =>
    readSecret(
      SECRET,
      z.object({
        client_id: z.string().min(1),
        client_secret: z.string().min(1),
      }),
    ),
) => {
  const response = await request(`${API}/oauth/token`, {
    method: "POST",
    body: new URLSearchParams({
      ...(await credentials()),
      grant_type: "client_credentials",
    }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok)
    throw new Error(`GPU enrollment OAuth returned ${response.status}`);

  const token = z
    .object({ access_token: z.string().min(1) })
    .parse(await response.json()).access_token;
  const headers = {
    authorization: `Bearer ${token}`,
    "content-type": "application/json",
  };
  const created = await request(`${API}/tailnet/-/keys`, {
    method: "POST",
    headers,
    body: JSON.stringify({
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
      description: `GPU ${z.uuid().parse(instanceId)}`,
    }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!created.ok)
    throw new Error(`GPU enrollment key creation returned ${created.status}`);

  const { key, id } = z
    .object({
      key: z.string().startsWith("tskey-auth-"),
      id: z.string().min(1),
    })
    .parse(await created.json());

  return {
    key,
    revoke: async () => {
      const revoked = await request(
        `${API}/tailnet/-/keys/${encodeURIComponent(id)}`,
        {
          method: "DELETE",
          headers,
          signal: AbortSignal.timeout(30_000),
        },
      );
      if (!revoked.ok && revoked.status !== 404)
        throw new Error(
          `GPU enrollment key revocation returned ${revoked.status}`,
        );
    },
  };
};
