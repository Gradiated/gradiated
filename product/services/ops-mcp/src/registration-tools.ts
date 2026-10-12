import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
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
    provider: z.enum(["runpod"]),
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
        "Enrol a GPU machine into Nomad: record the instance, issue a client certificate, and bind its ready node. Nomad deploys model jobs automatically after the node joins.",
        "Registration requires pinned direct SSH access and enrolls Tailscale before binding. Commit the returned privateService manifest under tailscale-inference/hosts and sync inference-network before serving traffic. There is no public inference fallback.",
        "A running pod on the exact configured nomad-base image with SSH credentials, a pinned host key, and existing SSH and serving ports is bootstrapped over SSH without resetting it or changing provider image, environment, ports, or capacity. The bootstrap starts only the Nomad client, never model jobs. In-place files survive process restarts, but are lost if the provider resets the container.",
        "Other running machines are refused unless reset_running_pod is true and confirm_instance_id repeats instance_id. Only do that when a person explicitly authorizes resetting that exact machine; a reset stops everything and can release scarce GPU capacity. Stopped machines use the provider bootstrap and are started.",
        "Interrupted registrations carrying this instance's bootstrap resume without reset. An already bound node is refused.",
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
        "Progress of GPU instance registrations started since the ops MCP last restarted: recording, issuing_certificate, updating_provider, waiting_for_node, enrolling_tailscale, then bound, or failed with the reason. A bound result includes privateService for Git review and Argo sync. Without registration_id, lists recent registrations, newest first. A registration interrupted by a restart is not listed; registering the machine again is safe.",
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
