import { ProfilingEventBatchSchema } from "@gradiated/contracts";
import type { ProfilingWriter } from "@gradiated/control";
import { Hono } from "hono";

import {
  bearerToken,
  handleIngestError,
  ingestBodyLimit,
  readJsonBody,
  tokenMatches,
} from "./http.js";

interface ProfilingIngestDependencies {
  token: string;
  writer: ProfilingWriter;
}

export const createProfilingIngestApp = ({
  token,
  writer,
}: ProfilingIngestDependencies): Hono => {
  const app = new Hono();

  app.get("/health/live", (context) => context.text("ok\n"));
  app.post(
    "/v1/profiling-events",
    ingestBodyLimit(4 * 1024 * 1024),
    async (context) => {
      const supplied = bearerToken(context.req.header("authorization"));
      if (!supplied || !tokenMatches(supplied, token)) {
        return context.json({ error: "unauthorized" }, 401);
      }

      const body = await readJsonBody(context);
      if (!body.ok) return context.json({ error: "invalid_json" }, 400);

      const parsed = ProfilingEventBatchSchema.safeParse(body.value);
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
    },
  );

  app.onError(handleIngestError);

  return app;
};
