import type { ClickHouseClient } from "@clickhouse/client";
import { GenerationLogSchema } from "@gradiated/contracts";
import { z } from "zod";

import { requireWorkspaceMembership } from "../access.js";
import { clickHouseUInt64Schema } from "../clickhouse/client.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import {
  decodeCursor,
  encodeCursor,
  generationFilter,
  rangeFilter,
  usageMeasures,
  type GenerationStatus,
  type UsageRange,
  type UsageSort,
} from "./query.js";

export type { UsageRange } from "./query.js";

const unsignedStringSchema = clickHouseUInt64Schema.transform(String);

const usagePointRowSchema = z.strictObject({
  date: z.string(),
  charge: unsignedStringSchema,
  input_tokens: unsignedStringSchema,
  output_tokens: unsignedStringSchema,
  generation_count: unsignedStringSchema,
});

const modelUsageRowSchema = usagePointRowSchema.omit({ date: true }).extend({
  model_id: z.string(),
});

const usageTotalRowSchema = usagePointRowSchema
  .omit({ date: true })
  .extend({ succeeded_count: unsignedStringSchema });

const generationRowSchema = z.strictObject({
  id: z.uuid(),
  external_id: z.string().nullable(),
  model_id: z.string(),
  status: GenerationLogSchema.shape.status,
  streamed: z.coerce.number().int().min(0).max(1).transform(Boolean),
  charge: unsignedStringSchema,
  input_tokens: z.coerce.number().int().nonnegative(),
  cached_input_tokens: z.coerce.number().int().nonnegative(),
  cache_write_tokens: z.coerce.number().int().nonnegative(),
  output_tokens: z.coerce.number().int().nonnegative(),
  reasoning_tokens: z.coerce.number().int().nonnegative(),
  finish_reason: z.string().nullable(),
  error_code: z.string().nullable(),
  usable_output_delivered: z.coerce
    .number()
    .int()
    .min(0)
    .max(1)
    .transform(Boolean),
  cancellation_owner: GenerationLogSchema.shape.cancellation_owner,
  received_at: z.iso.datetime({ offset: true }),
  started_at: z.iso.datetime({ offset: true }).nullable(),
  first_token_at: z.iso.datetime({ offset: true }).nullable(),
  completed_at: z.iso.datetime({ offset: true }),
});

type UsagePointRecord = z.infer<typeof usagePointRowSchema>;
type ModelUsageRecord = z.infer<typeof modelUsageRowSchema>;
export type GenerationLogRecord = z.infer<typeof generationRowSchema>;

export type UsageSummaryRecord = {
  charge: string;
  inputTokens: string;
  outputTokens: string;
  generationCount: string;
  succeededCount: string;
  daily: UsagePointRecord[];
  models: ModelUsageRecord[];
};

export interface UsageService {
  getSummary(input: {
    userId: string;
    organizationId: string;
    workspaceId: string;
    range: UsageRange;
  }): Promise<UsageSummaryRecord>;
  listGenerations(input: {
    userId: string;
    organizationId: string;
    workspaceId: string;
    range: UsageRange;
    cursor?: string;
    limit: number;
    apiKeyId?: string;
    model?: string;
    search?: string;
    sort: UsageSort;
    status?: GenerationStatus;
  }): Promise<{ data: GenerationLogRecord[]; nextCursor: string | null }>;
}

const usageUnavailable = (error: unknown) =>
  new ControlServiceError(
    "unavailable",
    "Usage data is temporarily unavailable.",
    error,
  );

export const createUsageService = (
  database: ControlDatabase,
  clickhouse: ClickHouseClient,
): UsageService => {
  const requireWorkspaceAccess = async (input: {
    userId: string;
    organizationId: string;
    workspaceId: string;
  }) => {
    const { workspace } = await requireWorkspaceMembership(database, input);
    if (workspace.archivedAt) {
      throw new ControlServiceError(
        "not_found",
        "The workspace does not exist or is not accessible.",
      );
    }
  };

  return {
    async getSummary(input) {
      await requireWorkspaceAccess(input);

      const range = rangeFilter(input);
      const where = range.where.join("\n          AND ");
      const selectRows = async (sql: string) =>
        (
          await clickhouse.query({
            query: sql,
            query_params: range.params,
            format: "JSONEachRow",
          })
        ).json();

      try {
        const [totalRows, dailyRows, modelRows] = await Promise.all([
          selectRows(`
            SELECT ${usageMeasures},
              countIf(g.status = 'succeeded') AS succeeded_count
            FROM generations AS g
            WHERE ${where}
          `),
          selectRows(`
            SELECT toString(toDate(g.completed_at, 'UTC')) AS date, ${usageMeasures}
            FROM generations AS g
            WHERE ${where}
            GROUP BY date
            ORDER BY date
          `),
          selectRows(`
            SELECT g.model_id AS model_id, ${usageMeasures}
            FROM generations AS g
            WHERE ${where}
            GROUP BY model_id
            ORDER BY charge DESC, model_id
          `),
        ]);
        const [total] = z.tuple([usageTotalRowSchema]).parse(totalRows);

        return {
          charge: total.charge,
          inputTokens: total.input_tokens,
          outputTokens: total.output_tokens,
          generationCount: total.generation_count,
          succeededCount: total.succeeded_count,
          daily: usagePointRowSchema.array().parse(dailyRows),
          models: modelUsageRowSchema.array().parse(modelRows),
        };
      } catch (error) {
        throw usageUnavailable(error);
      }
    },

    async listGenerations(input) {
      await requireWorkspaceAccess(input);

      const cursor = input.cursor
        ? decodeCursor(input.cursor, input.sort)
        : undefined;

      const filter = generationFilter(input, cursor);
      const orderBy =
        input.sort === "highest_cost"
          ? "g.charge DESC, g.completed_at DESC, g.id DESC"
          : "g.completed_at DESC, g.id DESC";

      try {
        const result = await clickhouse.query({
          query: `
          SELECT
            toString(id) AS id,
            nullIf(toString(getSubcolumn(properties, 'external_id')), '') AS external_id,
            model_id,
            status,
            toUInt8(getSubcolumn(properties, 'streamed')) AS streamed,
            charge,
            toUInt64(getSubcolumn(properties, 'usage.input_tokens')) AS input_tokens,
            toUInt64(getSubcolumn(properties, 'usage.cached_input_tokens')) AS cached_input_tokens,
            toUInt64(getSubcolumn(properties, 'usage.cache_write_tokens')) AS cache_write_tokens,
            toUInt64(getSubcolumn(properties, 'usage.output_tokens')) AS output_tokens,
            toUInt64(getSubcolumn(properties, 'usage.reasoning_tokens')) AS reasoning_tokens,
            nullIf(toString(getSubcolumn(properties, 'outcome.finish_reason')), '') AS finish_reason,
            nullIf(toString(getSubcolumn(properties, 'outcome.error_code')), '') AS error_code,
            toUInt8(getSubcolumn(properties, 'outcome.usable_output_delivered')) AS usable_output_delivered,
            nullIf(toString(getSubcolumn(properties, 'outcome.cancellation_owner')), '') AS cancellation_owner,
            formatDateTime(getSubcolumn(properties, 'timing.received_at'), '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC') AS received_at,
            if(isNull(getSubcolumn(properties, 'timing.started_at')), NULL, formatDateTime(getSubcolumn(properties, 'timing.started_at'), '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC')) AS started_at,
            if(isNull(getSubcolumn(properties, 'timing.first_token_at')), NULL, formatDateTime(getSubcolumn(properties, 'timing.first_token_at'), '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC')) AS first_token_at,
            formatDateTime(g.completed_at, '%Y-%m-%dT%H:%i:%S.%fZ', 'UTC') AS completed_at
          FROM generations AS g
          WHERE ${filter.where.join("\n            AND ")}
          ORDER BY ${orderBy}
          LIMIT {limit:UInt16}
        `,
          query_params: { ...filter.params, limit: input.limit + 1 },
          format: "JSONEachRow",
        });
        const rows = generationRowSchema.array().parse(await result.json());
        const data = rows.slice(0, input.limit);
        const last = data.at(-1);

        return {
          data,
          nextCursor:
            rows.length > input.limit && last
              ? encodeCursor(last, input.sort)
              : null,
        };
      } catch (error) {
        throw usageUnavailable(error);
      }
    },
  };
};
