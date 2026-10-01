import { createServer, type IncomingMessage } from "node:http";
import { randomUUID } from "node:crypto";
import express, {
  type RequestHandler,
  type ErrorRequestHandler,
} from "express";
import type { Identity } from "./auth.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import {
  Counter,
  Gauge,
  Histogram,
  Registry,
  collectDefaultMetrics,
} from "prom-client";
import { createTools } from "./tools.js";
import type { Backend } from "./backend.js";
import type { Registrations } from "./instances/registration.js";

export const createHttp = (options: {
  host: string;
  authenticate: (token: string) => Promise<Identity | undefined>;
  authRouter?: RequestHandler;
  backend: Backend;
  registrations?: Registrations;
  nomadCertificateExpiry?: () => number | undefined;
  audit: (event: Record<string, unknown>) => void;
}) => {
  const registry = new Registry();
  collectDefaultMetrics({ register: registry });
  const calls = new Counter({
    name: "ops_mcp_tool_calls_total",
    help: "Diagnostic tool outcomes",
    labelNames: ["tool", "outcome"],
    registers: [registry],
  });
  const duration = new Histogram({
    name: "ops_mcp_tool_duration_seconds",
    help: "Diagnostic tool duration",
    labelNames: ["tool"],
    buckets: [0.1, 0.5, 1, 3, 5, 10, 15],
    registers: [registry],
  });
  const certificateExpiry = options.nomadCertificateExpiry;
  if (certificateExpiry) {
    new Gauge({
      name: "nomad_certificate_expiry_timestamp_seconds",
      help: "Expiry of a Nomad certificate that renews itself",
      labelNames: ["certificate"],
      registers: [registry],
      collect() {
        const expiry = certificateExpiry();
        if (expiry === undefined) this.reset();
        else this.set({ certificate: "ops-mcp" }, expiry);
      },
    });
  }
  let active = 0;
  const budgets = new Map<string, { window: number; count: number }>();

  const app = express();
  const privateRequests = new WeakSet<IncomingMessage>();
  app.disable("x-powered-by");
  // The only ingress hop is the ALB, which appends the actual caller to XFF.
  // Trust only that last hop, never the caller-supplied leftmost address.
  app.set("trust proxy", 1);
  app.use((request, response, next) => {
    response.setHeader("X-Content-Type-Options", "nosniff");
    response.setHeader("Strict-Transport-Security", "max-age=31536000");
    if (request.url.length > 8192) {
      response.status(414).end();
      return;
    }
    if (request.url === "/healthz") {
      next();
      return;
    }
    const localHost =
      privateRequests.has(request) &&
      /^(127\.0\.0\.1|localhost):[0-9]{1,5}$/.test(request.headers.host ?? "");
    const allowedOrigin =
      request.headers.origin === `https://${options.host}` ||
      (localHost &&
        request.headers.origin === `http://${request.headers.host}`);
    if (
      (request.headers.host !== options.host && !localHost) ||
      (request.headers.origin && !allowedOrigin)
    ) {
      response.status(403).end();
      return;
    }
    next();
  });
  if (options.authRouter) app.use(options.authRouter);
  app.use(async (request, response) => {
    const reject = (status: number) => {
      response.writeHead(status).end();
    };
    if (request.method === "GET" && request.url === "/healthz") {
      response.writeHead(200).end("ok");
      return;
    }
    if (request.url !== "/mcp") {
      reject(404);
      return;
    }

    const provided = request.headers.authorization;
    const identity = await options.authenticate(
      provided?.startsWith("Bearer ") ? provided.slice(7) : "",
    );
    const principal = identity?.subject;
    if (!principal) {
      response.setHeader(
        "WWW-Authenticate",
        `Bearer resource_metadata="https://${options.host}/.well-known/oauth-protected-resource/mcp", scope="production:read"`,
      );
      reject(401);
      return;
    }
    if (request.method !== "POST") {
      response.setHeader("Allow", "POST");
      reject(405);
      return;
    }
    const window = Math.floor(Date.now() / 60_000);
    for (const [key, value] of budgets)
      if (value.window !== window) budgets.delete(key);
    const budget = budgets.get(principal);
    const current = budget?.window === window ? budget : { window, count: 0 };
    budgets.set(principal, current);
    if (++current.count > 60 || active >= 8) {
      response.setHeader("Retry-After", "5");
      reject(429);
      return;
    }
    if (!request.headers["content-type"]?.startsWith("application/json")) {
      reject(415);
      return;
    }

    active++;
    const requestId = randomUUID();
    const timeout = setTimeout(() => request.destroy(), 15_000);
    let mcp: ReturnType<typeof createTools> | undefined;
    try {
      const chunks: Buffer[] = [];
      let size = 0;
      for await (const chunk of request) {
        size += chunk.length;
        if (size > 65_536) {
          reject(413);
          return;
        }
        chunks.push(chunk);
      }
      let body: unknown;
      try {
        body = JSON.parse(Buffer.concat(chunks).toString());
      } catch {
        reject(400);
        return;
      }
      if (Array.isArray(body)) {
        reject(400);
        return;
      }

      const operations =
        options.registrations && identity
          ? {
              registrations: options.registrations,
              caller: identity.email,
              access: {
                ingress: privateRequests.has(request)
                  ? ("private" as const)
                  : ("public" as const),
              },
            }
          : undefined;
      mcp = createTools(
        options.backend,
        (tool, success, elapsed) => {
          calls.inc({ tool, outcome: success ? "success" : "error" });
          duration.observe({ tool }, elapsed / 1000);
          options.audit({
            service: "ops-mcp",
            event: "tool_completed",
            principal,
            email: identity?.email,
            request_id: requestId,
            tool,
            ingress: privateRequests.has(request) ? "private" : "public",
            outcome: success ? "success" : "error",
            duration_ms: elapsed,
          });
        },
        operations,
      );
      const transport = new StreamableHTTPServerTransport({
        enableJsonResponse: true,
      });
      await mcp.connect(transport);
      await transport.handleRequest(request, response, body);
    } catch {
      if (!response.headersSent && !response.destroyed) reject(500);
    } finally {
      clearTimeout(timeout);
      await mcp?.close();
      active--;
    }
  });
  // Do not let Express print raw parser errors or return stack traces.
  const handleError: ErrorRequestHandler = (
    _error,
    _request,
    response,
    _next,
  ) => {
    if (!response.headersSent)
      response.status(400).json({ error: "invalid_request" });
  };
  app.use(handleError);
  const server = createServer(app);
  // Listener provenance is server-owned; forwarded headers cannot grant access.
  const privateServer = createServer((request, response) => {
    privateRequests.add(request);
    app(request, response);
  });
  server.requestTimeout = 15_000;
  server.headersTimeout = 10_000;
  privateServer.requestTimeout = 15_000;
  privateServer.headersTimeout = 10_000;
  const metrics = createServer(async (request, response) => {
    if (request.url !== "/metrics" || request.method !== "GET") {
      response.writeHead(404).end();
      return;
    }
    try {
      response.setHeader("Content-Type", registry.contentType);
      response.end(await registry.metrics());
    } catch {
      response.writeHead(503).end();
    }
  });

  return { server, privateServer, metrics };
};
