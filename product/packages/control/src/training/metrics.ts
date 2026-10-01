import { z } from "zod";
import { RUN_STAGES } from "@gradiated/contracts";
import { sql } from "drizzle-orm";
import type { ControlDatabase } from "../db/client.js";

const TrainingMetricSchema = z.object({
  kind: z.enum(["active", "oldest", "completed", "duration"]),
  stage: z.enum(RUN_STAGES),
  value: z.number().nonnegative(),
});
export type TrainingMetric = z.infer<typeof TrainingMetricSchema>;

export const readTrainingMetrics = async (
  database: ControlDatabase,
): Promise<TrainingMetric[]> => {
  const result = await database.transaction(async (tx) => {
    await tx.execute(sql`set local statement_timeout = '2s'`);

    return tx.execute(sql`
    with recent_runs as (
      select id, stage, created_at, finished_at from training_runs
      where finished_at is null or finished_at >= now() - interval '24 hours'
    ), stages as (
      select e.run_id, e.payload->>'stage' as stage, e.at,
        lead(e.at) over (partition by e.run_id order by e.id) as next_at
      from training_run_events e join recent_runs r on r.id = e.run_id
      where e.payload->>'type' = 'stage_entered'
    ), active as (
      select r.stage, coalesce(max(s.at), r.created_at) as entered_at
      from recent_runs r left join stages s on s.run_id = r.id and s.stage = r.stage
      where r.finished_at is null
      group by r.id, r.stage, r.created_at
    )
    select 'active' as kind, stage, count(*)::float8 as value from active group by stage
    union all
    select 'oldest', stage, greatest(0, extract(epoch from now() - min(entered_at)))::float8
      from active group by stage
    union all
    select 'completed', stage, count(*)::float8 from recent_runs
      where finished_at is not null group by stage
    union all
    select 'duration', stage,
      percentile_cont(0.95) within group (order by greatest(0, extract(epoch from next_at - at)))::float8
      from stages where next_at >= now() - interval '24 hours' group by stage
  `);
  });

  return TrainingMetricSchema.array().parse(result.rows);
};
