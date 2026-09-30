import { Client, Connection } from "@temporalio/client";
import { createDataConverter } from "./data-converter.js";

export const TRAINING_TASK_QUEUE = "training-v1";
export const TRAINING_WORKFLOW = "trainingRunV1";
export const TRAINING_TASK_WORKFLOW = "trainingTaskV1";
export const trainingWorkflowId = (taskId: string) => `training-${taskId}`;

export const temporalOptions = async (environment: NodeJS.ProcessEnv) => {
  const production = environment.NODE_ENV === "production";
  const address =
    environment.TEMPORAL_ADDRESS ?? (production ? undefined : "localhost:7233");
  const namespace =
    environment.TEMPORAL_NAMESPACE ?? (production ? undefined : "default");
  const currentKeyId =
    environment.TEMPORAL_PAYLOAD_KEY_ID ??
    (production ? undefined : "local-dev");
  const keys =
    environment.TEMPORAL_PAYLOAD_KEYS ??
    (production
      ? undefined
      : JSON.stringify({
          "local-dev": Buffer.alloc(32, 7).toString("base64"),
        }));
  if (
    !address ||
    !namespace ||
    !currentKeyId ||
    !keys ||
    (production && !environment.TEMPORAL_API_KEY)
  )
    throw new Error(
      "Temporal connection and encryption configuration is required.",
    );

  return {
    address,
    namespace,
    ...(environment.TEMPORAL_API_KEY
      ? { apiKey: environment.TEMPORAL_API_KEY, tls: true }
      : {}),
    dataConverter: await createDataConverter({
      currentKeyId,
      keys: JSON.parse(keys) as Record<string, string>,
    }),
  };
};

export const connectTemporal = async (environment: NodeJS.ProcessEnv) => {
  const { namespace, dataConverter, ...options } =
    await temporalOptions(environment);
  const connection = await Connection.connect(options);

  return {
    connection,
    client: new Client({ connection, namespace, dataConverter }),
  };
};
