import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import type { Registrations } from "./instances/registration.js";

const text = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value) }],
});

export const registerRegistrationTools = (
  server: McpServer,
  registrations: Registrations,
  caller: string,
  audit: (tool: string, success: boolean, elapsed: number) => void,
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
        "Enrol a GPU machine into Nomad. This changes production: it records the instance, issues a Nomad client certificate, and replaces the machine's image and environment with nomad-base, which resets the machine.",
        "A running machine is refused unless reset_running_pod is true and confirm_instance_id repeats instance_id. Only do that when a person has explicitly authorized resetting that exact machine: a reset stops everything on it and can release scarce GPU capacity.",
        "A running machine whose registration was interrupted (it carries this instance's bootstrap but its node is not yet bound) is resumed without a reset: registration waits for its node and binds it. A machine that is already registered is refused; renewing its certificate or image needs reset_running_pod.",
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
        "Progress of GPU instance registrations started since the ops MCP last restarted: recording, issuing_certificate, updating_provider, waiting_for_node, then bound, or failed with the reason. Without registration_id, lists recent registrations, newest first. A registration interrupted by a restart is not listed; registering the machine again is safe.",
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
