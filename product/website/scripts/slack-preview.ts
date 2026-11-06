import { fileURLToPath } from "node:url";
import { loadEnv, type Plugin } from "vite";
import { z } from "zod";
import type { components } from "../src/api/schema";

type Invitation = components["schemas"]["SlackInvitation"];
type Provider = {
  invite(input: {
    organizationId: string;
    company: string;
    email: string;
    channelName?: string;
  }): Promise<Invitation>;
};
const inputSchema = z.strictObject({
  organizationId: z.uuid(),
  company: z.string().trim().min(1).max(200),
  email: z.string().trim().toLowerCase().email().max(200),
  channelName: z
    .string()
    .trim()
    .max(80)
    .regex(/^ext-[a-z0-9]+(?:-[a-z0-9]+)*-gradiated$/)
    .optional(),
});

export const slackPreview = (): Plugin => ({
  name: "slack-preview",
  apply: "serve",
  configureServer(server) {
    const env = loadEnv(
      "development",
      fileURLToPath(new URL("../../../", import.meta.url)),
      "SLACK_",
    );
    const engineerUserIds = (env.SLACK_ENGINEER_USER_IDS ?? "")
      .split(",")
      .map((id) => id.trim())
      .filter(Boolean);
    if (
      env.SLACK_CONNECT_PREVIEW !== "true" ||
      !env.SLACK_BOT_TOKEN ||
      !engineerUserIds.length
    )
      return;

    let provider: Provider | undefined;
    const attempts: number[] = [];
    server.middlewares.use("/__slack-preview", async (req, res) => {
      res.setHeader("Content-Type", "application/json");
      res.setHeader("Cache-Control", "no-store");
      const host = req.headers.host ?? "";
      if (
        !/^(localhost|127\.0\.0\.1):\d+$/.test(host) ||
        (req.headers.origin && req.headers.origin !== `http://${host}`)
      ) {
        res.writeHead(403).end("{}");
        return;
      }
      if (req.method === "GET" && req.url === "/") {
        res.end(JSON.stringify({ enabled: true }));
        return;
      }
      if (
        req.method !== "POST" ||
        req.url !== "/invitations" ||
        req.headers.origin !== `http://${host}`
      ) {
        res.writeHead(403).end("{}");
        return;
      }
      const now = Date.now();
      while (attempts.length && attempts[0]! < now - 60_000) attempts.shift();
      if (attempts.length >= 5) {
        res.writeHead(429).end(
          JSON.stringify({
            error: "Wait a minute before trying another Slack invitation.",
          }),
        );
        return;
      }
      attempts.push(now);
      try {
        let body = "";
        for await (const chunk of req) {
          body += chunk.toString();
          if (body.length > 3000) throw new Error("Request too large");
        }
        const input = inputSchema.parse(JSON.parse(body));
        if (!provider) {
          const integration = await server.ssrLoadModule(
            fileURLToPath(
              new URL(
                "../../services/api/src/slack/connect.ts",
                import.meta.url,
              ),
            ),
          );
          provider = integration.createSlackConnect({
            token: env.SLACK_BOT_TOKEN,
            engineerUserIds,
          });
        }
        const invitation = await provider!.invite({
          ...input,
          organizationId: `local-preview:${input.organizationId}`,
        });
        res.end(JSON.stringify(invitation));
      } catch (error) {
        const problem = (error as { problem?: { detail?: string } }).problem;
        res.writeHead(503).end(
          JSON.stringify({
            error:
              problem?.detail ??
              "Could not send the Slack invitation. Check the address and try again.",
          }),
        );
      }
    });
  },
});
