import { randomUUID } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ControlDatabase } from "../src/db/client.js";
import { prepareTraining } from "../src/training/admission.js";
import { createTrainingStore } from "../src/training/store.js";
import { countTrainingTraces } from "../src/training/traces.js";
import { createMemoryContentStore } from "./support/content-store.js";

vi.mock("../src/training/store.js", () => ({ createTrainingStore: vi.fn() }));
vi.mock("../src/training/traces.js", () => ({ countTrainingTraces: vi.fn() }));

type Context = NonNullable<
  Awaited<
    ReturnType<ReturnType<typeof createTrainingStore>["admissionContext"]>
  >
>;

const context = (): Context => ({
  task: {
    id: randomUUID(),
    workspaceId: randomUUID(),
    name: "triage",
    baseModelId: "test/base",
    comparisonModelId: "openai/gpt-5",
    judgeModelId: "openai/gpt-5",
    productionVersionId: null,
    trainingSchedule: "0 3 * * 1",
    createdAt: new Date(),
    updatedAt: new Date(),
  },
  workspace: {
    id: randomUUID(),
    archivedAt: null,
    traceCaptureEnabled: true,
  },
  organization: { status: "active" },
});

describe("training admission", () => {
  const database = {} as ControlDatabase;
  const content = createMemoryContentStore(new Map());
  const records = {
    admissionContext: vi.fn(),
    activeRun: vi.fn(),
    lastSuccessfulCutoff: vi.fn(),
  };
  let row: Context;

  beforeEach(() => {
    vi.resetAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-30T12:00:00Z"));
    row = context();
    row.task.workspaceId = row.workspace.id;
    vi.mocked(createTrainingStore).mockReturnValue(
      records as unknown as ReturnType<typeof createTrainingStore>,
    );
    records.admissionContext.mockResolvedValue(row);
    records.activeRun.mockResolvedValue(undefined);
    records.lastSuccessfulCutoff.mockResolvedValue(null);
    vi.mocked(countTrainingTraces).mockResolvedValue(500);
  });

  afterEach(() => vi.useRealTimers());

  it.each(["missing", "archived"] as const)(
    "rejects a %s task before looking for runs or traces",
    async (reason) => {
      if (reason === "missing")
        records.admissionContext.mockResolvedValue(undefined);
      else row.workspace.archivedAt = new Date();

      await expect(
        prepareTraining(database, content, row.task.id, "manual", null),
      ).rejects.toMatchObject({ code: "not_found" });
      expect(records.activeRun).not.toHaveBeenCalled();
      expect(countTrainingTraces).not.toHaveBeenCalled();
    },
  );

  it.each(["manual", "automation"] as const)(
    "rejects %s training on the retired stock GLM base before reading traces",
    async (trigger) => {
      row.task.baseModelId = "z-ai/glm-5.3-flash";

      await expect(
        prepareTraining(database, content, row.task.id, trigger, null),
      ).rejects.toMatchObject({ code: "training_not_configured" });
      expect(countTrainingTraces).not.toHaveBeenCalled();
    },
  );

  it("rejects an active run before reading trace storage", async () => {
    records.activeRun.mockResolvedValue({ id: randomUUID() });

    await expect(
      prepareTraining(database, content, row.task.id, "manual", null),
    ).rejects.toMatchObject({ code: "already_training" });
    expect(records.activeRun).toHaveBeenCalledWith(row.task.id);
    expect(records.lastSuccessfulCutoff).not.toHaveBeenCalled();
    expect(countTrainingTraces).not.toHaveBeenCalled();
  });

  it.each(["baseModelId", "comparisonModelId"] as const)(
    "requires %s for both triggers",
    async (field) => {
      row.task[field] = null;

      for (const trigger of ["manual", "automation"] as const)
        await expect(
          prepareTraining(database, content, row.task.id, trigger, null),
        ).rejects.toMatchObject({ code: "training_not_configured" });
      expect(countTrainingTraces).not.toHaveBeenCalled();
    },
  );

  it.each([
    "capture disabled",
    "schedule disabled",
    "organization suspended",
  ] as const)(
    "blocks automatic admission when %s while allowing manual admission",
    async (reason) => {
      if (reason === "capture disabled")
        row.workspace.traceCaptureEnabled = false;
      if (reason === "schedule disabled") row.task.trainingSchedule = null;
      if (reason === "organization suspended")
        row.organization.status = "suspended";

      await expect(
        prepareTraining(database, content, row.task.id, "automation", null),
      ).rejects.toMatchObject({ code: "training_not_configured" });
      expect(countTrainingTraces).not.toHaveBeenCalled();
      await expect(
        prepareTraining(database, content, row.task.id, "manual", null),
      ).resolves.toMatchObject({ taskId: row.task.id });
    },
  );

  it.each([
    ["manual", 99, false],
    ["manual", 100, true],
    ["automation", 499, false],
    ["automation", 500, true],
  ] as const)(
    "enforces the %s threshold at %i traces",
    async (trigger, count, admitted) => {
      vi.mocked(countTrainingTraces).mockResolvedValue(count);
      const result = prepareTraining(
        database,
        content,
        row.task.id,
        trigger,
        null,
      );

      if (admitted) await expect(result).resolves.toMatchObject({ trigger });
      else
        await expect(result).rejects.toMatchObject({
          code: "insufficient_traces",
        });
      expect(countTrainingTraces).toHaveBeenCalledWith(
        content,
        expect.objectContaining({
          threshold: trigger === "manual" ? 100 : 500,
        }),
      );
    },
  );

  it.each([null, new Date("2026-09-20T12:00:00Z")])(
    "counts since the successful cutoff %s and returns the exact admission snapshot",
    async (since) => {
      records.lastSuccessfulCutoff.mockResolvedValue(since);
      const requestedBy = randomUUID();
      const target = { workspaceId: row.workspace.id, name: row.task.name };

      const result = await prepareTraining(
        database,
        content,
        target,
        "manual",
        requestedBy,
      );

      expect(records.admissionContext).toHaveBeenCalledWith(target);
      expect(records.lastSuccessfulCutoff).toHaveBeenCalledWith(row.task.id);
      expect(countTrainingTraces).toHaveBeenCalledWith(content, {
        workspaceId: row.workspace.id,
        task: row.task.name,
        since,
        cutoff: new Date("2026-09-30T12:00:00Z"),
        threshold: 100,
      });
      expect(result).toEqual({
        taskId: row.task.id,
        workspaceId: row.workspace.id,
        name: row.task.name,
        baseModelId: row.task.baseModelId,
        comparisonModelId: row.task.comparisonModelId,
        judgeModelId: row.task.judgeModelId,
        inputCutoff: "2026-09-30T12:00:00.000Z",
        trigger: "manual",
        requestedBy,
      });
    },
  );

  it.each(["database", "trace storage"] as const)(
    "propagates %s failures instead of admitting a run",
    async (source) => {
      const error = new Error("unavailable");
      if (source === "database")
        records.admissionContext.mockRejectedValue(error);
      else vi.mocked(countTrainingTraces).mockRejectedValue(error);

      await expect(
        prepareTraining(database, content, row.task.id, "manual", null),
      ).rejects.toBe(error);
      if (source === "database")
        expect(countTrainingTraces).not.toHaveBeenCalled();
    },
  );
});
