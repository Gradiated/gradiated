import type { ModelDeploymentRelease } from "@gradiated/contracts";

import type { MODEL_TYPES } from "../db/schema/index.js";

/**
 * Whether a release serves a model of this type. Every model declares one, and
 * only releases that serve it may be its deployments, so the gateway never
 * routes a request to a release of the other interface.
 */
export const releaseServesType = (
  release: Pick<ModelDeploymentRelease, "protocol">,
  type: (typeof MODEL_TYPES)[number],
) => (release.protocol === "system_one") === (type === "decision");
