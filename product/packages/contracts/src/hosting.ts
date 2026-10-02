import { TaskVersionAdapterSchema, TaskVersionSchema } from "./training.js";

export const adapterRuntimeName = (
  versionId: string,
  sha256: string,
): string => {
  const id = TaskVersionSchema.shape.id.parse(versionId);
  const hash = TaskVersionAdapterSchema.shape.sha256.parse(sha256);

  return `ft-${id}-${hash}`;
};
