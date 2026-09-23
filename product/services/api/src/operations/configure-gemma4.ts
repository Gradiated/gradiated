import { configureModelDeployments, requiredEnv } from "./catalog-operation.js";
import {
  createGemma4ModelConfiguration,
  gemma4ArtifactModelPath,
  gemma4ModelId,
} from "./gemma4-model.js";

const serviceUrl = requiredEnv("GEMMA4_SERVICE_URL");
const modelRevision = "b9ea41a2887d8607f594846523f94c6cc75ac8a4";
const deploymentId =
  process.env.GEMMA4_DEPLOYMENT_ID ?? "019c8ad2-f857-7000-8000-000000000001";

await configureModelDeployments({
  model: createGemma4ModelConfiguration(),
  deployments: [{ id: deploymentId, serviceUrl }],
  placement: {
    provider: process.env.GEMMA4_PROVIDER ?? "local",
    region: process.env.GEMMA4_REGION ?? "local",
    faultDomain: process.env.GEMMA4_FAULT_DOMAIN ?? `local:${deploymentId}`,
  },
  release: {
    schema_version: 1,
    runtime_revision:
      process.env.GEMMA4_RUNTIME_REVISION ?? "native-gemma4-h200-v2",
    model_path: gemma4ArtifactModelPath,
    model_revision: modelRevision,
    tokenizer_path: gemma4ArtifactModelPath,
    tokenizer_revision: modelRevision,
  },
});

console.log(
  `Configured ${gemma4ModelId} deployment ${deploymentId} at ${serviceUrl}`,
);
