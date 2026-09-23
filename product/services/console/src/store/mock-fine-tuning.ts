import { useEffect, useMemo } from "react";
import { create } from "zustand";

import {
  isTerminalStage,
  type EvaluationJudge,
  type FineTunedModel,
  type TaskRow,
  type TaskStats,
  type TrainingRunRow,
  type VersionView,
} from "@/store/fine-tuning-types";
import { versionsForTask } from "@/store/fine-tuning-views";
import { seedFineTuning, type FineTuningSeed } from "@/store/mock-seed";
import { advanceRun, newRun, requestCancel } from "@/store/mock-training-runs";
import { isoAt, seededRandom } from "@/store/mock-values";

const LIVE_TICK_MS = 3_200;

const NO_STATS: TaskStats = {
  requests_7d: 0,
  tokens_7d: 0,
  usable_traces_since_last_run: 0,
};

interface FineTuningStore extends FineTuningSeed {
  setTraceCapture: (enabled: boolean) => void;
  setEvaluationJudge: (judge: EvaluationJudge) => void;
  setTaskBaseModel: (taskId: string, baseModelId: string) => void;
  setTaskComparisonModel: (taskId: string, modelId: string) => void;
  promote: (taskId: string, modelId: string) => void;
  createRun: (taskId: string) => void;
  cancelRun: (runId: string) => void;
  tickActiveRuns: () => void;
}

const updateTask = (
  tasks: readonly TaskRow[],
  taskId: string,
  changes: Partial<TaskRow>,
): TaskRow[] =>
  tasks.map((candidate) =>
    candidate.id === taskId ? { ...candidate, ...changes } : candidate,
  );

export const useMockFineTuning = create<FineTuningStore>()((set, get) => ({
  ...seedFineTuning(Date.now()),

  setTraceCapture: (enabled) =>
    set((state) => ({
      workspace: { ...state.workspace, trace_capture_enabled: enabled },
    })),

  setEvaluationJudge: (judge) =>
    set((state) => ({
      workspace: { ...state.workspace, evaluation_judge: judge },
    })),

  setTaskBaseModel: (taskId, baseModelId) =>
    set((state) => ({
      tasks: updateTask(state.tasks, taskId, { base_model_id: baseModelId }),
    })),

  setTaskComparisonModel: (taskId, modelId) =>
    set((state) => ({
      tasks: updateTask(state.tasks, taskId, { comparison_model_id: modelId }),
    })),

  promote: (taskId, modelId) =>
    set((state) => {
      const belongsToTask = state.models.some(
        (model) => model.id === modelId && model.task_id === taskId,
      );
      if (!belongsToTask) return {};

      return {
        tasks: updateTask(state.tasks, taskId, {
          production_model_id: modelId,
        }),
      };
    }),

  createRun: (taskId) => {
    const { tasks, training_runs, run_logs } = get();
    const target = tasks.find((candidate) => candidate.id === taskId);
    const hasActiveRun = training_runs.some(
      (run) => run.task_id === taskId && !isTerminalStage(run.stage),
    );
    if (!target || hasActiveRun) return;

    const id = crypto.randomUUID();
    const { run, log } = newRun(target, "manual", id, isoAt(Date.now()));

    set({
      training_runs: [run, ...training_runs],
      run_logs: { ...run_logs, [id]: log },
    });
  },

  cancelRun: (runId) =>
    set((state) => {
      const run = state.training_runs.find(
        (candidate) => candidate.id === runId,
      );
      if (!run || isTerminalStage(run.stage) || run.stage === "cancelling") {
        return {};
      }

      const cancelled = requestCancel(
        run,
        state.run_logs[runId] ?? [],
        isoAt(Date.now()),
      );

      return {
        training_runs: state.training_runs.map((candidate) =>
          candidate.id === runId ? cancelled.run : candidate,
        ),
        run_logs: { ...state.run_logs, [runId]: cancelled.log },
      };
    }),

  tickActiveRuns: () => {
    const state = get();
    const now = isoAt(Date.now());
    const run_logs = { ...state.run_logs };
    const published: FineTunedModel[] = [];
    const succeededTasks = new Set<string>();
    let changed = false;

    const training_runs = state.training_runs.map((run) => {
      const target = state.tasks.find(
        (candidate) => candidate.id === run.task_id,
      );
      if (isTerminalStage(run.stage) || !target) return run;

      const next = advanceRun(run, run_logs[run.id] ?? [], {
        now,
        random: seededRandom(`${run.id}:${run.stage}`),
        task: target,
        judge: state.workspace.evaluation_judge,
        existingIds: [...state.models, ...published].map((model) => model.id),
      });

      changed = true;
      run_logs[run.id] = next.log;
      if (next.published) published.push(next.published);
      if (next.run.stage === "succeeded") succeededTasks.add(target.id);

      return next.run;
    });

    if (!changed) return;

    set({
      training_runs,
      run_logs,
      models: [...state.models, ...published],
      stats: Object.fromEntries(
        Object.entries(state.stats).map(([taskId, stats]) => [
          taskId,
          succeededTasks.has(taskId)
            ? { ...stats, usable_traces_since_last_run: 0 }
            : stats,
        ]),
      ),
    });
  },
}));

export const useLiveRunTicker = () => {
  useEffect(() => {
    const interval = window.setInterval(
      () => useMockFineTuning.getState().tickActiveRuns(),
      LIVE_TICK_MS,
    );

    return () => window.clearInterval(interval);
  }, []);
};

export const useTaskVersions = (taskId: string): VersionView[] => {
  const models = useMockFineTuning((state) => state.models);
  const trainingRuns = useMockFineTuning((state) => state.training_runs);
  const tasks = useMockFineTuning((state) => state.tasks);

  return useMemo(
    () =>
      versionsForTask({ models, training_runs: trainingRuns, tasks }, taskId),
    [models, trainingRuns, tasks, taskId],
  );
};

export const useTaskRuns = (taskId: string): TrainingRunRow[] => {
  const trainingRuns = useMockFineTuning((state) => state.training_runs);

  return useMemo(
    () =>
      trainingRuns
        .filter((run) => run.task_id === taskId)
        .toSorted((a, b) => b.created_at.localeCompare(a.created_at)),
    [trainingRuns, taskId],
  );
};

export const useTaskStats = (taskId: string): TaskStats =>
  useMockFineTuning((state) => state.stats[taskId] ?? NO_STATS);
