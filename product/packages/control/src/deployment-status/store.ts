import { eq } from "drizzle-orm";
import type { ControlDatabase } from "../db/client.js";
import { modelDeployments } from "../db/schema/index.js";
import { ModelDeploymentRecordSchema } from "../catalog/records.js";

const StatusDeploymentSchema = ModelDeploymentRecordSchema.pick({
  id: true,
  provider: true,
  release: true,
});

export const createDeploymentStatusStore = (database: ControlDatabase) => ({
  async getDeployment(deploymentId: string) {
    const [row] = await database
      .select({
        id: modelDeployments.id,
        provider: modelDeployments.provider,
        release: modelDeployments.release,
      })
      .from(modelDeployments)
      .where(
        eq(
          modelDeployments.id,
          StatusDeploymentSchema.shape.id.parse(deploymentId),
        ),
      )
      .limit(1);

    return row && StatusDeploymentSchema.parse(row);
  },
});
