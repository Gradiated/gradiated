import { timingSafeEqual } from "node:crypto";

import { ProfilingEventBatchSchema } from "@gradiated/contracts";
import type { ProfilingWriter } from "@gradiated/control";
import { Hono } from "hono";
import { bodyLimit } from "hono/body-limit";

interface ProfilingIngestDependencies {
  token: string;
  writer: ProfilingWriter;
}

const matchesToken = (authorization: string | undefined, token: string): boolean => {
  if (!authorization?.startsWith("Bearer ")) return false;
  const supplied = Buffer.from(authorization.slice("Bearer ".length));
  const expected = Buffer.from(token);
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
};

export const createProfilingIngestApp = ({
  token,
  writer,
}: ProfilingIngestDependencies): Hono => {
  if (token.length < 32) {
    throw new Error("PROFILING_INGEST_TOKEN must contain at least 32 characters");
  }
  const app = new Hono();
  app.use(
    "*",
    bodyLimit({
      maxSize: 4 * 1024 * 1024,
      onError: (context) => context.json({ error: "payload_too_large" }, 413),
    }),
  );
  app.get("/health/live", (context) => context.text("ok\n"));
  app.post("/v1/profiling-events", async (context) => {
    if (!matchesToken(context.req.header("authorization"), token)) {
      return context.json({ error: "unauthorized" }, 401);
    }
    let payload: unknown;
    try {
      payload = await context.req.json();
    } catch {
      return context.json({ error: "invalid_json" }, 400);
    }
    const parsed = ProfilingEventBatchSchema.safeParse(payload);
    if (!parsed.success) {
      return context.json(
        {
          error: "invalid_batch",
          issues: parsed.error.issues.map((issue) => ({
            path: issue.path.join("."),
            message: issue.message,
          })),
        },
        422,
      );
    }
    await writer.insertBatch(parsed.data);
    return context.body(null, 204);
  });
  return app;
};
