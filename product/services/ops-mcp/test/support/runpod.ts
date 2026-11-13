import { runPodSchema } from "@gradiated/gpu-hosts";

export type Call = { method: string; url: string; body: unknown };

export const v2Pod = (input: Record<string, unknown>) => {
  const pod = runPodSchema.parse(input);
  return {
    id: pod.id,
    status: pod.desiredStatus,
    image: pod.imageName ?? "registry.example/gpu-base:pinned",
    startedAt: pod.lastStartedAt ?? null,
    env: pod.env ?? {},
    dataCenterId: pod.machine.dataCenterId,
    ...(pod.gpuCount
      ? {
          gpu: {
            id: pod.machine.gpuTypeId,
            count: pod.gpuCount,
            vcpuCount: pod.vcpuCount,
          },
        }
      : { cpu: { vcpuCount: pod.vcpuCount } }),
    mounts: pod.volumeInGb ? { persistent: { size: pod.volumeInGb } } : {},
  };
};

export const fakeRunPod = (pod: Record<string, unknown>) => {
  const calls: Call[] = [];
  const fetch = async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });

    return Response.json(
      url.endsWith("/graphql")
        ? {
            data: {
              pod: {
                consumerUserId: pod.consumerUserId,
                machineId: pod.machineId,
              },
            },
          }
        : method === "GET"
          ? v2Pod(pod)
          : {},
    );
  };

  return { calls, fetch: fetch as typeof globalThis.fetch };
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
