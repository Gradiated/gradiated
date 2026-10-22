import { defineConfig } from "vitest/config";

// The end-to-end rejoin test (test/e2e). It needs Docker and the assets that
// product/inference/images/gpu-base/tests/e2e_image.py builds; set
// GPU_FLEET_E2E to that output directory.
export default defineConfig({
  test: {
    include: ["test/e2e/**/*.e2e.ts"],
    fileParallelism: false,
  },
});
