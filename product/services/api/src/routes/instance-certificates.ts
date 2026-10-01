import { createPublicKey, X509Certificate } from "node:crypto";
import { createRoute, OpenAPIHono, z } from "@hono/zod-openapi";
import { bodyLimit } from "hono/body-limit";
import {
  CertificateAuthorizationError,
  CertificateRateLimitError,
  type InstanceCertificateService,
} from "@gradiated/control";
import {
  issueCertificateForPublicKey,
  renewableHostProfile,
  type CertificateSigner,
} from "@gradiated/nomad-pki";
import { apiRateLimit } from "../http/request-limits.js";
import type { ApiEnvironment } from "../types.js";

const path = "/api/internal/v1/instances/{instance_id}/nomad-certificates";
const requestSchema = z.strictObject({
  nomad_node_id: z.uuid().describe("The enrolled Nomad node identity"),
  public_key: z
    .string()
    .max(1024)
    .optional()
    .describe("Host-generated P-256 SPKI public key; omit for a heartbeat"),
  certificate: z
    .string()
    .max(2048)
    .describe("Installed certificate, reported after reload verification"),
});
const route = createRoute({
  hide: true,
  method: "post",
  path,
  operationId: "renewInstanceNomadCertificate",
  tags: ["Infrastructure"],
  request: {
    params: z.object({
      instance_id: z.uuid().describe("Inventory instance identity"),
    }),
    body: {
      required: true,
      content: { "application/json": { schema: requestSchema } },
    },
  },
  responses: {
    200: {
      description: "Installed-certificate heartbeat accepted",
      content: { "application/json": { schema: z.strictObject({}) } },
    },
    201: {
      description: "Renewed certificate for the host public key",
      content: {
        "application/json": { schema: z.object({ certificate: z.string() }) },
      },
    },
    401: { description: "Missing or invalid host credential" },
    403: { description: "Host not authorized" },
    413: { description: "Request too large" },
    422: { description: "Invalid request or certificate" },
    429: { description: "Retry after one minute" },
    503: { description: "Issuer unavailable; retry after one minute" },
  },
});
export interface HostCertificateDependencies {
  credentials: () => Promise<InstanceCertificateService>;
  caCertificate: () => Promise<string>;
  signer: CertificateSigner;
  audit: (event: Record<string, unknown>) => void;
}

export const createHostCertificateRouter = (
  dependencies: HostCertificateDependencies,
) => {
  const router = new OpenAPIHono<ApiEnvironment>();
  let active = 0;
  router.use(route.getRoutingPath(), apiRateLimit(60));
  router.use(route.getRoutingPath(), async (context, next) => {
    context.header("Cache-Control", "no-store");
    if (
      !/^Bearer [A-Za-z0-9_-]{43}$/.test(
        context.req.header("authorization") ?? "",
      )
    )
      return context.body(null, 401);

    await next();
  });
  router.use(
    route.getRoutingPath(),
    bodyLimit({ maxSize: 8192, onError: (context) => context.body(null, 413) }),
  );
  router.openapi(
    route,
    async (context) => {
      const instanceId = context.req.valid("param").instance_id;
      const body = context.req.valid("json");
      let installed: X509Certificate;
      try {
        installed = new X509Certificate(body.certificate);
        if (body.public_key) {
          const key = createPublicKey(body.public_key);
          if (
            key.asymmetricKeyType !== "ec" ||
            key.asymmetricKeyDetails?.namedCurve !== "prime256v1"
          )
            throw new Error();
        }
      } catch {
        return context.body(null, 422);
      }

      if (active >= 4) {
        context.header("Retry-After", "60");
        return context.body(null, 429);
      }

      active++;
      let phase = "credentials";
      try {
        const service = await dependencies.credentials();
        phase = "ca";
        const ca = await dependencies.caCertificate();
        if (
          !installed.verify(new X509Certificate(ca).publicKey) ||
          installed.ca ||
          !installed.checkHost("client.global.nomad")
        )
          return context.body(null, 422);

        const startsAt = Date.parse(installed.validFrom);
        const expiresAt = Date.parse(installed.validTo);
        const lifetime = expiresAt - startsAt;
        const renewalDueAt =
          lifetime > 31 * 86400_000 ? startsAt : startsAt + (lifetime * 2) / 3;
        const token = context.req.header("authorization")!.slice(7);
        phase = "heartbeat";
        await service.observe(
          instanceId,
          body.nomad_node_id,
          token,
          new Date(expiresAt),
          new Date(renewalDueAt),
        );
        if (!body.public_key) return context.json({}, 200);

        phase = "issuance";
        const certificate = await service.issue(
          instanceId,
          body.nomad_node_id,
          token,
          () =>
            issueCertificateForPublicKey(
              ca,
              dependencies.signer,
              renewableHostProfile,
              body.public_key!,
            ),
        );
        dependencies.audit({
          event: "host_certificate_issued",
          instance_id: instanceId,
          nomad_node_id: body.nomad_node_id,
        });
        return context.json({ certificate }, 201);
      } catch (error) {
        const status =
          error instanceof CertificateAuthorizationError
            ? 403
            : error instanceof CertificateRateLimitError
              ? 429
              : 503;
        if (status === 429 || status === 503)
          context.header("Retry-After", "60");
        dependencies.audit({
          event: "host_certificate_rejected",
          level: status === 503 ? "error" : "warn",
          instance_id: instanceId,
          phase,
          status,
        });
        return context.body(null, status);
      } finally {
        active--;
      }
    },
    (result, context) => {
      if (!result.success) return context.body(null, 422);
    },
  );
  return router;
};
