export type Call = { method: string; url: string; body: unknown };

export const fakeRunPod = (pod: Record<string, unknown>) => {
  const calls: Call[] = [];
  let auths = [
    { id: "old", name: "gradiated-host-pod1-1" },
    { id: "other", name: "someone-else" },
  ];
  const fetch = async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });
    const json = (value: unknown) => new Response(JSON.stringify(value));

    if (url.includes("/pods/")) return method === "GET" ? json(pod) : json({});
    if (method === "POST") {
      const created = { id: "new", name: body.name };
      auths = [...auths, created];
      return json(created);
    }
    if (method === "DELETE") {
      auths = auths.filter((auth) => !url.endsWith(`/${auth.id}`));
      return new Response("");
    }
    return json(auths);
  };

  return { calls, fetch: fetch as typeof globalThis.fetch, auths: () => auths };
};

export const rtxPod = {
  id: "pod1",
  consumerUserId: "user_1",
  machineId: "machine1",
  gpuCount: 2,
  vcpuCount: 32,
  desiredStatus: "EXITED",
  ports: ["22/tcp"],
  env: { PUBLIC_KEY: "ssh-ed25519 debug" },
  machine: {
    dataCenterId: "US-NE-1",
    gpuTypeId: "NVIDIA RTX PRO 6000 Blackwell Server Edition",
  },
};
