import {
  COMPARISON_MODELS,
  isExternalModelId,
} from "@gradiated/contracts/model-catalog";
import type { CatalogBillingService } from "@gradiated/control";
import { ControlServiceError } from "@gradiated/control";
import type { createExternalModelCatalog } from "./external-models.js";

export const createEvaluationModelValidator =
  (
    externalModels: ReturnType<typeof createExternalModelCatalog>,
    hostedModels: Pick<CatalogBillingService, "listModels">,
  ) =>
  async (id: string) => {
    const available = isExternalModelId(id)
      ? (await externalModels()).data.some(
          (model) => model.id === id && model.status === "available",
        )
      : COMPARISON_MODELS.some((model) => model.id === id) &&
        (await hostedModels.listModels()).some(
          (model) => model.id === id && model.status === "available",
        );

    if (!available)
      throw new ControlServiceError(
        "not_found",
        "The evaluation model is unavailable.",
      );
  };
