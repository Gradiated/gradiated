import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { EC2_INSTANCE_ID, RUNPOD_POD_ID } from "@gradiated/gpu-hosts";
import { z } from "zod";

import type { Registrations } from "./instances/registration.js";
import { requirePrivateToolAccess, type ToolAccess } from "./tool-access.js";

const text = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value) }],
});

export const registerRegistrationTools = (
  server: McpServer,
  registrations: Registrations,
  caller: string,
  audit: (tool: string, success: boolean, elapsed: number) => void,
  access: ToolAccess,
) => {
  const schema = {
    provider: z.enum(["runpod", "aws"]),
    instance_id: z.string().regex(/^[A-Za-z0-9-]{1,100}$/),
    reset_running_pod: z.boolean().default(false),
    confirm_instance_id: z.string().max(100).optional(),
  };

  server.registerTool(
    "register_instance",
    {
      title: "register instance",
      description: [
        "Requires the private administrative MCP connection through Tailscale and Kubernetes port-forward, in addition to MCP OAuth.",
        "Prepare a GPU host for Kubernetes: record its identity, install the pinned GPU host agent, and enroll Tailscale. Return the private Service, measured node inventory, and management-secret reference for Git and Argo.",
        "provider runpod takes a RunPod pod ID; provider aws takes an EC2 instance ID (i-...) in the GPU account, tagged gradiated:managed=gpu-fleet.",
        "Add the host as a GpuHost in gpu-inference/hosts.yaml (instance ID; the returned kubernetes.provider as spec.provider, which names the RunPod account, pod and machine or the AWS account, region, availability zone and EC2 instance; and the returned kubernetes.inventoryEntry inventory and secret reference) and render the manifests before scheduling workloads; merge it within a day or the gpu-fleet operator retires the instance row until it lands. Secrets remain in AWS and on the GPU host; results contain only secret references.",
        "A running pod with the pinned GPU bootstrap can enroll over SSH without changing provider settings or releasing capacity. A fresh running EC2 instance gets its single-use bootstrap key through its bootstrap secret, then enrolls the same way; once enrolled its secret and instance profile are removed. New enrollment requires idle GPUs; an existing enrollment keeps active model processes.",
        "Other running machines are refused unless reset_running_pod is true and confirm_instance_id repeats instance_id. Only do that when a person explicitly authorizes resetting that exact machine; a reset stops everything and can release scarce GPU capacity. A stopped machine, or one whose reset is authorized, is re-imaged with the approved GPU base image, no public ports and a single-use bootstrap key that ops-mcp mints, then started and enrolled over Tailscale SSH. On AWS a re-image replaces the instance's root volume with the AMI its launch template's default version pins and keeps the instance; nothing stops or terminates it.",
        "An enrolled host is checked without replacing its active processes or provider settings.",
        "Returns a registration id at once; registration then takes up to 30 minutes. Follow it with instance_registration_status.",
      ].join(" "),
      inputSchema: schema,
      annotations: {
        readOnlyHint: false,
        destructiveHint: true,
        idempotentHint: false,
        openWorldHint: true,
      },
    },
    async (input) => {
      const start = Date.now();

      try {
        requirePrivateToolAccess(access);
        const request = z.object(schema).parse(input);
        if (
          !(request.provider === "aws" ? EC2_INSTANCE_ID : RUNPOD_POD_ID).test(
            request.instance_id,
          )
        )
          throw new Error(
            request.provider === "aws"
              ? "instance_id must be an EC2 instance ID (i-...)"
              : "instance_id must be a RunPod pod ID",
          );
        if (
          request.reset_running_pod &&
          request.confirm_instance_id !== request.instance_id
        ) {
          throw new Error(
            "A reset needs confirm_instance_id to repeat instance_id exactly",
          );
        }

        const registration = await registrations.start({
          provider: request.provider,
          providerInstanceId: request.instance_id,
          resetRunningPod: request.reset_running_pod,
          requestedBy: caller,
        });
        audit("register_instance", true, Date.now() - start);

        return text({
          registration,
          ...(registration.resetRunningPod && {
            warning: `${registration.sku} ${registration.providerInstanceId} is being reset; everything running on it stops.`,
          }),
        });
      } catch (error) {
        audit("register_instance", false, Date.now() - start);

        return {
          isError: true,
          ...text({
            error:
              error instanceof Error ? error.message : "Registration failed",
          }),
        };
      }
    },
  );

  server.registerTool(
    "instance_registration_status",
    {
      title: "instance registration status",
      description:
        "Progress of GPU instance registrations started since the ops MCP last restarted: recording, updating_provider, then prepared, or failed with the reason. A prepared result includes kubernetes.provider (the GpuHost spec.provider: RunPod account, pod and machine, or AWS account, region, availability zone and EC2 instance) and kubernetes.inventoryEntry for the host's GpuHost in hosts.yaml, Git review and Argo sync. Without registration_id, lists recent registrations, newest first. A registration interrupted by a restart is not listed; registering the machine again is safe.",
      inputSchema: { registration_id: z.uuid().optional() },
      annotations: {
        readOnlyHint: true,
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async ({ registration_id }) => {
      const start = Date.now();
      const result = registration_id
        ? registrations.get(registration_id)
        : registrations.list();
      audit(
        "instance_registration_status",
        result !== undefined,
        Date.now() - start,
      );

      return result === undefined
        ? { isError: true, ...text({ error: "Unknown registration id" }) }
        : text(result);
    },
  );
};
