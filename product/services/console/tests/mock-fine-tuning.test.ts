import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { runTimeline } from "@/store/fine-tuning-run-log";
import { STAGE_ORDER, type TrainingRunRow } from "@/store/fine-tuning-types";
import { versionsForTask } from "@/store/fine-tuning-views";
import { useMockFineTuning } from "@/store/mock-fine-tuning";

import { defined, findTask } from "./support/fine-tuning";

const MAX_TICKS_TO_FINISH = 20;

const store = () => useMockFineTuning.getState();

const taskBySlug = (slug: string) => findTask(store().tasks, slug);

const latestRun = (taskId: string) => {
  const run = store().training_runs.find(
    (candidate) => candidate.task_id === taskId,
  );
  if (!run) throw new Error(`Task ${taskId} has no run`);

  return run;
};

const tickUntil = (done: () => boolean) => {
  for (let tick = 0; tick < MAX_TICKS_TO_FINISH && !done(); tick++) {
    store().tickActiveRuns();
  }
};

beforeEach(() => {
  useMockFineTuning.setState(useMockFineTuning.getInitialState(), true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createRun", () => {
  it("advances a manual run to a published, succeeded version", () => {
    const task = taskBySlug("sql-generation");
    const modelsBefore = store().models.length;

    store().createRun(task.id);
    const runId = latestRun(task.id).id;
    tickUntil(() => latestRun(task.id).stage === "succeeded");

    const run = latestRun(task.id);
    const log = store().run_logs[runId] ?? [];
    const published = log.filter((event) => event.type === "published");
    const newModels = store()
      .models.slice(modelsBefore)
      .filter((model) => model.task_id === task.id);

    expect(run.id).toBe(runId);
    expect(run.stage).toBe("succeeded");
    expect(run.evaluation).not.toBeNull();
    expect(published).toHaveLength(1);
    expect(newModels).toEqual([
      expect.objectContaining({ task_id: task.id, training_run_id: runId }),
    ]);
    expect(published[0]).toMatchObject({ model_id: newModels[0]?.id });
    expect(store().stats[task.id]?.usable_traces_since_last_run).toBe(0);
  });

  it("writes a run log with strictly increasing sequence numbers", () => {
    const task = taskBySlug("sql-generation");

    store().createRun(task.id);
    const runId = latestRun(task.id).id;
    tickUntil(() => latestRun(task.id).stage === "succeeded");

    const sequence = (store().run_logs[runId] ?? []).map((event) => event.seq);
    expect(sequence.length).toBeGreaterThan(2);
    expect(new Set(sequence).size).toBe(sequence.length);
    expect(sequence).toEqual(sequence.toSorted((a, b) => a - b));
  });

  it("ignores a second run while one is active", () => {
    const task = taskBySlug("sql-generation");

    store().createRun(task.id);
    const runsAfterFirst = store().training_runs;
    store().createRun(task.id);

    expect(store().training_runs).toBe(runsAfterFirst);
  });

  it("keeps a separate log for runs created in the same millisecond", () => {
    const sql = taskBySlug("sql-generation");
    const email = taskBySlug("email-draft");
    vi.spyOn(Date, "now").mockReturnValue(Date.UTC(2026, 8, 1));

    store().createRun(sql.id);
    store().createRun(email.id);

    const sqlRun = latestRun(sql.id);
    const emailRun = latestRun(email.id);
    expect(sqlRun.id).not.toBe(emailRun.id);
    expect(store().run_logs[sqlRun.id]?.[0]).toMatchObject({
      type: "run_created",
      task_id: sql.id,
    });
  });

  it("sets the evaluation only when the log records its completion", () => {
    const task = taskBySlug("sql-generation");

    store().createRun(task.id);
    const runId = latestRun(task.id).id;
    tickUntil(() => latestRun(task.id).stage === "evaluating");

    expect(latestRun(task.id).evaluation).toBeNull();

    store().tickActiveRuns();

    const completed = defined(
      store().run_logs[runId]?.find(
        (event) => event.type === "evaluation_completed",
      ),
    );
    const { win, tie, loss, unresolved } = defined(
      latestRun(task.id).evaluation?.vs_comparison,
    );
    expect(completed).toMatchObject({ win, tie, loss, unresolved });
  });

  it("ignores a run for a task whose seeded run is still active", () => {
    const task = taskBySlug("support-triage");
    const runsBefore = store().training_runs;

    store().createRun(task.id);

    expect(store().training_runs).toBe(runsBefore);
  });
});

describe("seed", () => {
  it("replays the live stage machine for every seeded succeeded run", () => {
    const task = taskBySlug("sql-generation");

    store().createRun(task.id);
    const liveId = latestRun(task.id).id;
    tickUntil(() => latestRun(task.id).stage === "succeeded");

    const eventTypes = (runId: string) =>
      new Set(store().run_logs[runId]?.map((event) => event.type));
    const liveTypes = eventTypes(liveId);
    const seeded = store().training_runs.filter(
      (run) => run.stage === "succeeded" && run.id !== liveId,
    );

    expect(seeded.length).toBeGreaterThan(0);
    for (const run of seeded) {
      expect(eventTypes(run.id)).toEqual(liveTypes);
      expect(
        runTimeline(store().run_logs[run.id] ?? []).map((entry) => entry.stage),
      ).toEqual(STAGE_ORDER);
    }
  });

  it("gives seeded runs increasing stage times with the longest in training", () => {
    const seeded = store().training_runs.filter(
      (run) => run.stage === "succeeded",
    );

    for (const run of seeded) {
      const timeline = runTimeline(store().run_logs[run.id] ?? []);
      const times = timeline.map((entry) => Date.parse(entry.entered_at));
      const durations = times.slice(1).map((time, index) => {
        const previous = times[index] ?? time;

        return time - previous;
      });
      const trainingIndex = timeline.findIndex(
        (entry) => entry.stage === "training",
      );

      expect(durations.every((duration) => duration > 0)).toBe(true);
      expect(Math.max(...durations)).toBe(durations[trainingIndex]);
    }
  });

  it("points each production version at a model of its own task", () => {
    for (const task of store().tasks) {
      if (!task.production_model_id) continue;

      expect(
        versionsForTask(store(), task.id).find(
          (version) => version.is_production,
        )?.model.id,
      ).toBe(task.production_model_id);
    }
  });

  it("groups every trace that holds more than one generation", () => {
    const generationIds = new Set(store().traces.map((row) => row.id));
    const generationCounts = new Map<string, number>();
    for (const row of store().traces) {
      generationCounts.set(
        row.trace_id,
        (generationCounts.get(row.trace_id) ?? 0) + 1,
      );
    }

    for (const [traceId, count] of generationCounts) {
      if (generationIds.has(traceId)) expect(count).toBe(1);
    }
    expect([...generationCounts.values()].some((count) => count > 1)).toBe(
      true,
    );
  });

  it("links every assistant message to a captured generation", () => {
    const generationIds = new Set(store().traces.map((row) => row.id));
    const assistantMessages = Object.values(store().conversations)
      .flat()
      .filter((message) => message.role === "assistant");

    expect(assistantMessages.length).toBeGreaterThan(0);
    for (const message of assistantMessages) {
      expect(generationIds.has(message.generation_id)).toBe(true);
    }
  });
});

describe("tickActiveRuns", () => {
  const breakRun = (runId: string, changes: Partial<TrainingRunRow>) => {
    useMockFineTuning.setState((state) => ({
      training_runs: state.training_runs.map((run) =>
        run.id === runId ? { ...run, ...changes } : run,
      ),
    }));
  };

  it.each([
    ["publishing", { dataset: null }],
    ["evaluating", { dataset: null }],
  ] as const)(
    "fails a %s run that lost its inputs instead of throwing",
    (stage, changes) => {
      const task = taskBySlug("sql-generation");

      store().createRun(task.id);
      const runId = latestRun(task.id).id;
      tickUntil(() => latestRun(task.id).stage === stage);
      breakRun(runId, changes);
      store().tickActiveRuns();

      expect(latestRun(task.id).stage).toBe("failed");
      expect(store().run_logs[runId]?.at(-1)).toMatchObject({
        type: "run_finished",
        stage: "failed",
        error_code: "internal",
      });
    },
  );
});

describe("cancelRun", () => {
  it("moves through cancelling to cancelled on the next tick", () => {
    const task = taskBySlug("sql-generation");

    store().createRun(task.id);
    const runId = latestRun(task.id).id;
    store().cancelRun(runId);

    expect(latestRun(task.id).stage).toBe("cancelling");
    expect(store().run_logs[runId]?.map((event) => event.type)).toContain(
      "cancel_requested",
    );

    store().tickActiveRuns();

    expect(latestRun(task.id).stage).toBe("cancelled");
    expect(store().run_logs[runId]?.at(-1)).toMatchObject({
      type: "run_finished",
      stage: "cancelled",
    });
  });
});

describe("promote", () => {
  it("promotes a version of the same task", () => {
    const task = taskBySlug("support-triage");
    const candidate = defined(
      store().models.find(
        (model) =>
          model.task_id === task.id && model.id !== task.production_model_id,
      ),
    );

    store().promote(task.id, candidate.id);

    expect(taskBySlug("support-triage").production_model_id).toBe(candidate.id);
  });

  it("ignores a version from another task", () => {
    const task = taskBySlug("support-triage");
    const otherVersion = defined(
      store().models.find(
        (model) => model.task_id === taskBySlug("email-draft").id,
      ),
    );

    store().promote(task.id, otherVersion.id);

    expect(taskBySlug("support-triage").production_model_id).toBe(
      task.production_model_id,
    );
  });
});
