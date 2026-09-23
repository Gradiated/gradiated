import { configureModelDeployments, requiredEnv } from "./catalog-operation.js";
import {
  createDeepseekV4FlashModelConfiguration,
  deepseekV4FlashArtifactModelPath,
  deepseekV4FlashModelId,
} from "./deepseek-v4-flash-model.js";

const serviceUrl = requiredEnv("DEEPSEEK_V4_FLASH_SERVICE_URL");
const modelRevision = "7872f01b1d1fe23eabc4c98b48bffcef5a386062";
const deploymentId =
  process.env.DEEPSEEK_V4_FLASH_DEPLOYMENT_ID ??
  "019cc9fa-1d00-7000-8000-000000000001";

await configureModelDeployments({
  model: createDeepseekV4FlashModelConfiguration(),
  deployments: [{ id: deploymentId, serviceUrl }],
  placement: {
    provider: process.env.DEEPSEEK_V4_FLASH_PROVIDER ?? "runpod",
    region: process.env.DEEPSEEK_V4_FLASH_REGION ?? "us",
    faultDomain:
      process.env.DEEPSEEK_V4_FLASH_FAULT_DOMAIN ?? `runpod:${deploymentId}`,
  },
  release: {
    schema_version: 1,
    runtime_revision:
      process.env.DEEPSEEK_V4_FLASH_RUNTIME_REVISION ??
      "vllm-0.27.1-deepseek-v4-flash-b300-v2",
    model_path: deepseekV4FlashArtifactModelPath,
    model_revision: modelRevision,
    runtime_model_name: "deepseek-v4-flash",
    tokenizer_path: deepseekV4FlashArtifactModelPath,
    tokenizer_revision: modelRevision,
    tokenizer_mode: "deepseek_v4",
  },
});

console.log(
  `Configured ${deepseekV4FlashModelId} deployment ${deploymentId} at ${serviceUrl}`,
);
