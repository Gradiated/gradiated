import { fileURLToPath } from "node:url";
import { loadEnv, type Plugin } from "vite";
import type { NdaDetails, NdaDocument } from "../src/api/nda";

type Owner = { organizationId: string; userId: string; email: string };
type Provider = {
  create(owner: Owner, details: NdaDetails): Promise<NdaDocument>;
  read(owner: Owner, id: string): Promise<NdaDocument>;
  session(owner: Owner, id: string): Promise<{ session_id: string }>;
};

export const ndaSandbox = (): Plugin => ({
  name: "nda-sandbox",
  apply: "serve",
  configureServer(server) {
    const root = fileURLToPath(new URL("../../../", import.meta.url));
    const env = loadEnv("development", root, "PANDADOC_");
    const email = env.PANDADOC_SANDBOX_SIGNER_EMAIL;
    if (
      env.PANDADOC_SANDBOX_PREVIEW !== "true" ||
      !env.PANDADOC_API_KEY ||
      !email
    )
      return;

    const owner = {
      organizationId: "local-sandbox",
      userId: "local-preview",
      email,
    };
    const documents = new Set<string>();
    let provider: Provider | undefined;
    server.middlewares.use("/__nda-sandbox", async (req, res) => {
      res.setHeader("Cache-Control", "no-store");
      res.setHeader("Content-Type", "application/json");
      const host = req.headers.host ?? "";
      const local = /^(localhost|127\.0\.0\.1):\d+$/.test(host);
      if (
        !local ||
        (req.headers.origin && req.headers.origin !== `http://${host}`)
      ) {
        res.writeHead(403).end(
          JSON.stringify({
            error: "Sandbox preview requires same-origin localhost access.",
          }),
        );
        return;
      }
      if (req.method === "GET" && req.url === "/") {
        res.end(JSON.stringify({ enabled: true, signer_email: email }));
        return;
      }
      if (
        req.method !== "POST" ||
        !["/session", "/status"].includes(req.url ?? "")
      ) {
        res.writeHead(404).end("{}");
        return;
      }
      try {
        let body = "";
        for await (const chunk of req) {
          body += chunk.toString();
          if (body.length > 10_000) throw new Error("Request too large");
        }
        const input = JSON.parse(body);
        if (!provider) {
          const module = await server.ssrLoadModule(
            fileURLToPath(
              new URL(
                "../../services/api/src/legal/pandadoc.ts",
                import.meta.url,
              ),
            ),
          );
          provider = module.createPandaDocNda({
            apiKey: env.PANDADOC_API_KEY,
            templateId: env.PANDADOC_NDA_TEMPLATE_ID,
            templateVersion: env.PANDADOC_NDA_TEMPLATE_VERSION,
            dateField: env.PANDADOC_NDA_DATE_FIELD,
            silent: true,
          });
        }
        let id =
          typeof input.document_id === "string" &&
          documents.has(input.document_id)
            ? input.document_id
            : undefined;
        if (req.url === "/status") {
          if (!id) {
            res.writeHead(404).end("{}");
            return;
          }
          res.end(
            JSON.stringify({ document: await provider!.read(owner, id) }),
          );
          return;
        }
        if (!id) {
          const created = await provider!.create(owner, {
            ...input.details,
            email,
          });
          id = created.id;
          documents.add(id);
        }
        let current: NdaDocument | undefined;
        for (let attempt = 0; attempt < 15; attempt++) {
          try {
            current = await provider!.read(owner, id);
            if (current.status !== "preparing") break;
          } catch (error) {
            if (
              (error as { problem?: { status?: number } }).problem?.status !==
              404
            )
              throw error;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        if (!current || current.status === "preparing")
          throw new Error("Sandbox NDA is still being prepared. Try again.");

        const response = await fetch(
          `https://api.pandadoc.com/public/v1/documents/${id}/details`,
          {
            headers: { Authorization: `API-Key ${env.PANDADOC_API_KEY}` },
            signal: AbortSignal.timeout(15_000),
          },
        );
        if (!response.ok || !(await response.json()).name.startsWith("[DEV]"))
          throw new Error(
            "A PandaDoc sandbox key is required for this preview.",
          );

        res.end(
          JSON.stringify({
            document: current,
            ...(current.status === "completed"
              ? {}
              : await provider!.session(owner, id)),
          }),
        );
      } catch (error) {
        res.writeHead(503).end(
          JSON.stringify({
            error:
              error instanceof Error
                ? error.message
                : "Could not open the sandbox NDA.",
          }),
        );
      }
    });
  },
});
