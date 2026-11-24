import type {
  AwsGpuClient,
  Ec2Instance,
  TailnetStatus,
} from "@gradiated/gpu-hosts";

export const INSTANCE = "i-0123456789abcdef0";

// The host side of an EC2 GPU instance: its launcher runs the GPU base image
// once a fresh root volume finds its bootstrap secret, and the container joins
// the tailnet as gpu-bootstrap-<instance ID>.
export const fakeEc2 = (
  overrides: Partial<Ec2Instance> & {
    // The launcher already ran on this root volume, so a secret changes nothing.
    launched?: boolean;
    // The instance profile is attached, as when the instance was launched.
    profile?: boolean;
  } = {},
) => {
  const { launched = false, profile = true, ...fields } = overrides;
  const instance: Ec2Instance = {
    id: INSTANCE,
    accountId: "111122223333",
    state: "running",
    availabilityZone: "us-east-1b",
    instanceType: "g6.xlarge",
    imageId: "ami-0abc",
    tags: { "gradiated:managed": "gpu-fleet" },
    ...fields,
  };
  const host = {
    instance,
    launched,
    profile,
    joined: false,
    secret: undefined as
      { image: string; tailscaleAuthKey: string } | undefined,
    tasks: 0,
    // Which root volume the instance runs on; a replacement makes a new one.
    root: 0,
    // Every replace-root-volume task, oldest first, with how it will end.
    replacements: [] as {
      id: string;
      state: string;
      imageId: string;
      ends: "succeeded" | "failed";
    }[],
    // The AMI the launch template's default version pins.
    templateImage: "ami-0fedcba9876543210",
    calls: [] as string[],
    // Every value the bootstrap secret ever held.
    secrets: [] as { image: string; tailscaleAuthKey: string }[],
    // Each single-use key a launcher read, with the root volume it ran on.
    consumed: [] as { root: number; key: string }[],
  };
  // The launcher runs when a fresh volume has its secret, in a running instance.
  const launch = () => {
    if (!host.launched && host.secret && host.instance.state === "running") {
      host.launched = true;
      host.joined = true;
      host.consumed.push({
        root: host.root,
        key: host.secret.tailscaleAuthKey,
      });
    }
  };
  // Each poll moves every unfinished task one step. A task that succeeds
  // swaps the root on its first step: the old volume, its container and its
  // tailnet identity are gone.
  const advance = () => {
    for (const task of host.replacements) {
      if (task.state === "pending") {
        if (task.ends === "failed") {
          task.state = "failing";
          continue;
        }
        host.instance = { ...host.instance, imageId: task.imageId };
        host.root++;
        host.launched = false;
        host.joined = false;
        task.state = "in-progress";
      } else if (task.state === "in-progress") task.state = "succeeded";
      else if (task.state === "failing") task.state = "failed";
    }
  };
  const client: AwsGpuClient = {
    accountId: instance.accountId,
    region: "us-east-1",
    instance: async (id) => {
      host.calls.push(`instance ${id}`);
      launch();
      return { ...host.instance };
    },
    gpus: async (type) => {
      host.calls.push(`gpus ${type}`);
      return {
        count: 1,
        name: "L4",
      };
    },
    instanceStorage: async () => true,
    start: async (id) => {
      host.calls.push(`start ${id}`);
      host.instance = { ...host.instance, state: "running" };
    },
    launchTemplateImage: async () => {
      host.calls.push("launchTemplateImage");
      return host.templateImage;
    },
    replaceRootVolume: async (id, _token, imageId) => {
      host.calls.push(`replaceRootVolume ${id} ${imageId}`);
      if (host.instance.state !== "running")
        throw new Error("IncorrectState: the instance must be running");
      host.tasks++;
      const task = {
        id: `replacevol-${host.replacements.length + 1}`,
        state: "pending",
        imageId,
        ends: "succeeded" as const,
      };
      host.replacements.push(task);
      return { id: task.id, state: task.state };
    },
    // The old root keeps running until a task's first poll.
    replaceRootVolumeTask: async (id, taskId) => {
      host.calls.push(`replaceRootVolumeTask ${id} ${taskId}`);
      launch();
      const before = host.replacements.find((task) => task.id === taskId);
      advance();
      if (!before)
        throw new Error(`Replace-root-volume task ${taskId} is gone`);
      return { id: taskId, state: before.state };
    },
    replaceRootVolumeTasks: async (id) => {
      host.calls.push(`replaceRootVolumeTasks ${id}`);
      launch();
      advance();
      return host.replacements.map((task, i) => ({
        id: task.id,
        state: task.state,
        started: new Date(Date.UTC(2026, 10, 20, 12, i)),
      }));
    },
    bootstrapProfileAssociated: async (id) => {
      host.calls.push(`bootstrapProfileAssociated ${id}`);
      return host.profile;
    },
    associateBootstrapProfile: async (id) => {
      host.calls.push(`associateBootstrapProfile ${id}`);
      if (host.profile) return false;
      host.profile = true;
      return true;
    },
    disassociateBootstrapProfile: async (id) => {
      host.calls.push(`disassociateBootstrapProfile ${id}`);
      const had = host.profile ? 1 : 0;
      host.profile = false;
      const other = host.instance.instanceProfileArn;
      return { removed: had, kept: other && !had ? [other] : [] };
    },
    writeBootstrapSecret: async (id, value) => {
      host.calls.push(`writeBootstrapSecret ${id}`);
      host.secret = value;
      host.secrets.push(value);
    },
    deleteBootstrapSecret: async (id) => {
      host.calls.push(`deleteBootstrapSecret ${id}`);
      const had = host.secret !== undefined;
      host.secret = undefined;
      return had;
    },
    bootstrapSecretReadable: async () => host.secret !== undefined,
  };
  // What the ops-mcp sidecar's netmap shows while the host is a bootstrap device.
  const status = async (): Promise<TailnetStatus> => ({
    Peer: host.joined
      ? {
          node: {
            HostName: `gpu-bootstrap-${host.instance.id}`,
            TailscaleIPs: ["100.64.0.9"],
            Tags: ["tag:gpu-bootstrap"],
            Online: true,
            sshHostKeys: [
              "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHN5bnRoZXRpYw==",
            ],
          },
        }
      : {},
  });
  return { host, client, status };
};
