import {
  ScheduleAlreadyRunning,
  ScheduleNotFoundError,
  ScheduleOverlapPolicy,
  TRAINING_TASK_QUEUE,
  TRAINING_TASK_WORKFLOW,
  type Client,
  type ScheduleUpdateOptions,
} from "@gradiated/temporal";

export const trainingScheduleId = (taskId: string) => `training-task-${taskId}`;

export const updateTrainingSchedule = async (
  client: Client,
  taskId: string,
  cron: string | null,
) => {
  const handle = client.schedule.getHandle(trainingScheduleId(taskId));
  if (!cron) {
    try {
      await handle.delete();
    } catch (error) {
      if (!(error instanceof ScheduleNotFoundError)) throw error;
    }
    return;
  }

  const schedule = {
    spec: { cronExpressions: [cron], timezone: "UTC" },
    action: {
      type: "startWorkflow",
      workflowType: TRAINING_TASK_WORKFLOW,
      taskQueue: TRAINING_TASK_QUEUE,
      args: [taskId],
    },
    policies: { overlap: ScheduleOverlapPolicy.SKIP, catchupWindow: "1 hour" },
    state: { paused: false },
  } satisfies ScheduleUpdateOptions;

  try {
    await handle.update(() => schedule);
    return;
  } catch (error) {
    if (!(error instanceof ScheduleNotFoundError)) throw error;
  }

  try {
    await client.schedule.create({
      scheduleId: handle.scheduleId,
      ...schedule,
    });
  } catch (error) {
    if (!(error instanceof ScheduleAlreadyRunning)) throw error;

    await handle.update(() => schedule);
  }
};
