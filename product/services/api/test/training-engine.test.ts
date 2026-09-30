import { expect, it } from "vitest";
import type { TrainingInput } from "@gradiated/control";
import { createTrainingEngine } from "../src/training/engine.js";

it.each([undefined, "", "unknown"])(
  "rejects starts when the executor is %s",
  async (executor) => {
    const training = createTrainingEngine(
      executor === undefined ? {} : { TRAINING_EXECUTOR: executor },
    );
    await expect(
      training.engine.start({} as TrainingInput),
    ).rejects.toMatchObject({ code: "training_not_configured" });
    await training.close();
  },
);
