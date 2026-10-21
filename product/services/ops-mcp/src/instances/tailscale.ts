import { z } from "zod";

import { readSecret } from "./aws.js";

const API = "https://api.tailscale.com/api/v2";
const SECRET = "gradiated/prod/platform/tailscale-gpu-enrollment";

const enrollmentCredentials = () =>
  readSecret(
    SECRET,
    z.object({
      client_id: z.string().min(1),
      client_secret: z.string().min(1),
    }),
  );

const accessToken = async (
  request: typeof fetch,
  credentials: typeof enrollmentCredentials,
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

  return z
    .object({ access_token: z.string().min(1) })
    .parse(await response.json()).access_token;
};

export const tailscaleAuthKey = async (
  instanceId: string,
  request: typeof fetch = fetch,
  credentials = enrollmentCredentials,
) => {
  const token = await accessToken(request, credentials);
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

const devicesSchema = z.object({
  devices: z.array(
    z.object({
      hostname: z.string(),
      addresses: z.array(z.string()),
      tags: z.array(z.string()).nullish(),
      created: z.string(),
    }),
  ),
});

// Re-authentication registers the promoted pod as a new device with a new
// address, which ops-mcp's own netmap cannot see.
export const promotedAddress = async (
  instanceId: string,
  since: Date,
  request: typeof fetch = fetch,
  credentials = enrollmentCredentials,
) => {
  const token = await accessToken(request, credentials);
  const response = await request(`${API}/tailnet/-/devices`, {
    headers: { authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok)
    throw new Error(`Tailscale device listing returned ${response.status}`);

  const hostname = `gpu-${z.uuid().parse(instanceId)}`;
  const device = devicesSchema
    .parse(await response.json())
    .devices.filter(
      (device) =>
        device.hostname === hostname &&
        (device.tags ?? []).includes("tag:gpu-inference") &&
        Date.parse(device.created) >= since.getTime(),
    )
    .sort((a, b) => Date.parse(b.created) - Date.parse(a.created))[0];
  const address = device?.addresses.find((address) =>
    /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+$/.test(address),
  );
  if (!address)
    throw new Error(`${hostname} has no new tag:gpu-inference device`);
  return address;
};
