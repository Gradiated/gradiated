import {
  configureModelDeployments,
  requiredEnv,
  requiredServiceUrls,
} from "./catalog-operation.js";
import {
  createKev9bModelConfiguration,
  kev9bArtifactModelPath,
  kev9bBaseModelPath,
  kev9bModelId,
} from "./kev-9b-model.js";

// Ids are zero based to match the pod's replica index and services.conf.
const deployments = requiredServiceUrls("KEV_9B_SERVICE_URLS", [
  process.env.KEV_DEPLOYMENT_0_ID ?? "019d5a4a-0000-7000-8000-000000000101",
  process.env.KEV_DEPLOYMENT_1_ID ?? "019d5a4a-0000-7000-8000-000000000102",
]);

await configureModelDeployments({
  model: createKev9bModelConfiguration(),
  deployments,
  placement: {
    provider: "runpod",
    region: requiredEnv("KEV_9B_REGION"),
    faultDomain: process.env.KEV_9B_FAULT_DOMAIN ?? "runpod:kev-9b-rtx6000-1",
  },
  release: {
    schema_version: 1,
    runtime_revision: "kev-f0ae8fb9-systemone-v1",
    // Without it the gateway serves Kev as a chat model and every decision fails.
    protocol: "system_one",
    model_path: kev9bArtifactModelPath,
    model_revision: "2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c",
    runtime_model_name: kev9bArtifactModelPath,
    tokenizer_path: kev9bBaseModelPath,
    tokenizer_revision: "68c46c4b3498877f3ef123c856ecfde50c39f404",
  },
});

console.log(
  `Configured ${kev9bModelId} with ${deployments.length} RunPod deployments`,
);
