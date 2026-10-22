// A Tailscale control plane with the device rules enrollment depends on:
// device names are unique, so a device joining under a taken name becomes
// <name>-1, -2, ...; deleting a device frees its name.
type Device = {
  nodeId: string;
  name: string;
  hostname: string;
  addresses: string[];
  tags: string[];
  created: string;
  connectedToControl: boolean;
};

const DOMAIN = "tail186117.ts.net";

export const fakeTailnet = () => {
  const devices = new Map<string, Device>();
  let clock = Date.parse("2026-10-22T12:00:00Z");
  let next = 1;

  const label = (device: Device) => device.name.split(".")[0]!;
  const free = (name: string) =>
    ![...devices.values()].some((device) => label(device) === name);

  const join = (hostname: string, tag: string) => {
    let name = hostname;
    for (let suffix = 1; !free(name); suffix++) name = `${hostname}-${suffix}`;
    const device: Device = {
      nodeId: `n${next}CNTRL`,
      name: `${name}.${DOMAIN}`,
      hostname,
      addresses: [`100.64.0.${next}`, `fd7a:115c:a1e0::${next}`],
      tags: [tag],
      created: new Date((clock += 1_000)).toISOString(),
      connectedToControl: true,
    };
    next++;
    devices.set(device.nodeId, device);
    return device;
  };

  const fetch = async (input: string | URL | Request, init?: RequestInit) => {
    const { pathname } = new URL(String(input));
    const method = init?.method ?? "GET";
    const path = pathname.replace("/api/v2", "");
    if (path === "/oauth/token")
      return Response.json({ access_token: "oauth-token" });
    if (method === "GET" && path === "/tailnet/-/devices")
      return Response.json({ devices: [...devices.values()] });

    const [, , id, action] = path.split("/");
    const device = devices.get(decodeURIComponent(id ?? ""));
    if (!device) return new Response(null, { status: 404 });
    if (method === "DELETE" && !action) {
      devices.delete(device.nodeId);
      return new Response(null, { status: 200 });
    }
    if (method === "POST" && action === "name") {
      const { name } = JSON.parse(String(init?.body)) as { name: string };
      if (label(device) !== name && !free(name))
        return new Response(null, { status: 409 });
      device.name = `${name}.${DOMAIN}`;
      return new Response(null, { status: 200 });
    }
    return new Response(null, { status: 400 });
  };

  return {
    devices,
    join,
    disconnect: (device: Device) => {
      device.connectedToControl = false;
    },
    now: () => new Date(clock),
    fetch: fetch as typeof globalThis.fetch,
  };
};
