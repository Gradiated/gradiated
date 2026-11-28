import { and, asc, eq, lte, sql } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import {
  GRAD_WORKSPACE_STATES,
  gradWorkspaceStateOutbox as outbox,
} from "../db/schema/index.js";
import type { ServiceLogFields } from "../service-logging.js";

// A claim outlives one request's timeout; a sweep that dies mid-send is retried after it.
const CLAIM_SECONDS = 120;
const MAX_BACKOFF_SECONDS = 900;

const PendingStateSchema = z.object({
  // Any uuid the column holds, so one odd ID cannot block the queue.
  workspaceId: z.guid(),
  state: z.enum(GRAD_WORKSPACE_STATES),
  generation: z.number().int(),
  attempts: z.number().int().nonnegative(),
});
type PendingState = z.infer<typeof PendingStateSchema>;

const ProblemSchema = z.object({ code: z.string().optional() }).passthrough();

const createGradWorkspaceStateStore = (database: ControlDatabase) => ({
  // Claims the next due row; SKIP LOCKED and the pushed-back next_attempt_at
  // keep other replicas' sweeps off it while it is sent.
  claim: () =>
    database.transaction(async (tx) => {
      const [row] = await tx
        .select({
          workspaceId: outbox.workspaceId,
          state: outbox.state,
          generation: outbox.generation,
          attempts: outbox.attempts,
        })
        .from(outbox)
        .where(lte(outbox.nextAttemptAt, sql`now()`))
        .orderBy(asc(outbox.nextAttemptAt))
        .limit(1)
        .for("update", { skipLocked: true });
      if (!row) return undefined;

      await tx
        .update(outbox)
        .set({
          nextAttemptAt: sql`now() + make_interval(secs => ${CLAIM_SECONDS})`,
        })
        .where(eq(outbox.workspaceId, row.workspaceId));

      return PendingStateSchema.parse(row);
    }),

  async complete({ workspaceId, generation }: PendingState) {
    const done = await database
      .delete(outbox)
      .where(
        and(
          eq(outbox.workspaceId, workspaceId),
          eq(outbox.generation, generation),
        ),
      )
      .returning({ workspaceId: outbox.workspaceId });
    if (done.length > 0) return;

    // A newer state arrived while this one was in flight: send it next.
    await database
      .update(outbox)
      .set({ nextAttemptAt: sql`now()` })
      .where(eq(outbox.workspaceId, workspaceId));
  },

  async fail({ workspaceId, attempts }: PendingState, error: string) {
    const backoff = Math.min(60 * 2 ** attempts, MAX_BACKOFF_SECONDS);

    await database
      .update(outbox)
      .set({
        attempts: sql`${outbox.attempts} + 1`,
        lastError: error.slice(0, 200),
        nextAttemptAt: sql`now() + make_interval(secs => ${backoff})`,
      })
      .where(eq(outbox.workspaceId, workspaceId));
  },
});

type Log = (
  level: "info" | "warn" | "error",
  event: string,
  fields?: ServiceLogFields,
) => void;

/**
 * Sends the outbox's workspace states to grad-server's internal listener:
 * `PUT /internal/v1/workspaces/{ws}/state` with a service JWT that
 * `authorization` signs for the workspace and scope.
 */
export const createGradWorkspaceStateSync = ({
  database,
  baseUrl,
  authorization,
  log,
  fetch: request = fetch,
  timeoutMs = 10_000,
}: {
  database: ControlDatabase;
  baseUrl: string;
  authorization: (call: {
    workspaceId: string;
    scopes: readonly "workspaces:admin"[];
  }) => Promise<string>;
  log: Log;
  fetch?: typeof fetch;
  timeoutMs?: number;
}) => {
  const store = createGradWorkspaceStateStore(database);

  // "sent", "deleted" (grad already deleted it) or the error to retry on.
  const send = async ({ workspaceId, state }: PendingState) => {
    let response: Response;
    try {
      const token = await authorization({
        workspaceId,
        scopes: ["workspaces:admin"],
      });
      response = await request(
        new URL(`/internal/v1/workspaces/${workspaceId}/state`, baseUrl),
        {
          method: "PUT",
          headers: {
            authorization: `Bearer ${token}`,
            accept: "application/json",
            "content-type": "application/json",
          },
          body: JSON.stringify({ state }),
          redirect: "error",
          signal: AbortSignal.timeout(timeoutMs),
        },
      );
    } catch (error) {
      return `request failed: ${error instanceof Error ? error.name : "unknown"}`;
    }

    const text = await response.text().catch(() => "");
    if (response.ok) return "sent";

    let code: string | undefined;
    try {
      code = ProblemSchema.safeParse(JSON.parse(text)).data?.code;
    } catch {
      code = undefined;
    }
    if (response.status === 409 && code === "workspace_deleted")
      return "deleted";

    return `http ${response.status}${code ? ` ${code.slice(0, 64)}` : ""}`;
  };

  return {
    async sweep(limit = 20) {
      let sent = 0;
      let failed = 0;

      for (let index = 0; index < limit; index++) {
        const pending = await store.claim();
        if (!pending) break;

        const result = await send(pending);
        if (result === "sent" || result === "deleted") {
          await store.complete(pending);
          sent++;
          log(
            result === "sent" ? "info" : "warn",
            result === "sent"
              ? "grad_workspace_state_sent"
              : "grad_workspace_already_deleted",
            { workspace_id: pending.workspaceId, reason: pending.state },
          );
          continue;
        }

        await store.fail(pending, result);
        failed++;
        log("warn", "grad_workspace_state_failed", {
          workspace_id: pending.workspaceId,
          reason: result,
          attempt: pending.attempts + 1,
        });
      }

      return { sent, failed };
    },
  };
};

// Without a grad URL nothing is sent; the triggers keep at most one row per workspace.
export const startGradWorkspaceStateSweep = ({
  baseUrl,
  intervalMs = 60_000,
  ...options
}: Omit<Parameters<typeof createGradWorkspaceStateSync>[0], "baseUrl"> & {
  baseUrl: string | undefined;
  intervalMs?: number;
}): (() => void) => {
  if (!baseUrl) return () => {};

  const sync = createGradWorkspaceStateSync({ ...options, baseUrl });
  // One sweep at a time: while grad is down, each call waits out its timeout.
  let sweeping = false;
  const timer = setInterval(() => {
    if (sweeping) return;
    sweeping = true;
    sync
      .sweep()
      .catch((error: unknown) => {
        options.log("warn", "grad_workspace_state_sweep_failed", { error });
      })
      .finally(() => {
        sweeping = false;
      });
  }, intervalMs).unref();

  return () => clearInterval(timer);
};
