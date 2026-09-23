import {
  configureModelDeployments,
  requiredEnv,
  requiredServiceUrls,
} from "./catalog-operation.js";
import {
  createGlm53FlashModelConfiguration,
  glm53FlashArtifactModelPath,
  glm53FlashModelId,
} from "./glm-5-3-flash-model.js";

const modelRevision = "84c6a6aa9497188e15a635ba793b0f95a79b1033";

await configureModelDeployments({
  model: createGlm53FlashModelConfiguration(),
  deployments: requiredServiceUrls("GLM_5_3_FLASH_SERVICE_URLS", [
    process.env.GLM_5_3_FLASH_DEPLOYMENT_1_ID ??
      "019d5a4a-0000-7000-8000-000000000001",
    process.env.GLM_5_3_FLASH_DEPLOYMENT_2_ID ??
      "019d5a4a-0000-7000-8000-000000000002",
  ]),
  placement: {
    provider: "runpod",
    region: requiredEnv("GLM_5_3_FLASH_REGION"),
    faultDomain:
      process.env.GLM_5_3_FLASH_FAULT_DOMAIN ?? "runpod:glm-5-3-flash-b300-1",
  },
  release: {
    schema_version: 1,
    runtime_revision:
      "vllm-933876c388fb129ad82590660e6506614559cb86-priority-v1",
    model_path: glm53FlashArtifactModelPath,
    model_revision: modelRevision,
    runtime_model_name: "zai-org/GLM-5.3-Flash",
    tokenizer_path: glm53FlashArtifactModelPath,
    tokenizer_revision: modelRevision,
  },
});

console.log(`Configured ${glm53FlashModelId} with two RunPod deployments`);
