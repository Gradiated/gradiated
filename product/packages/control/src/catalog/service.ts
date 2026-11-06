import type {
  ModelDeploymentRelease,
  ModelPropertiesInput,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import type { ModelRecord, ModelDeploymentRecord } from "./records.js";
import { createCatalogStore } from "./store.js";

export type { ModelRecord, ModelDeploymentRecord } from "./records.js";
export type CatalogModelInput = Parameters<CatalogService["upsertModel"]>[0];

export interface CatalogService {
  listModels(): Promise<ModelRecord[]>;
  upsertModel(input: {
    id: string;
    name: string;
    status: ModelRecord["status"];
    properties: ModelPropertiesInput;
    /** Omitted means OpenRouter cannot serve the model. */
    openrouterModelId?: string | null;
  }): Promise<ModelRecord>;
  upsertModelDeployment(input: {
    id: string;
    modelId: string;
    status: ModelDeploymentRecord["status"];
    provider: string;
    region: string;
    faultDomain: string;
    serviceUrl: string;
    release: ModelDeploymentRelease;
  }): Promise<ModelDeploymentRecord>;
}

export const createCatalogService = (
  database: ControlDatabase,
): CatalogService => createCatalogStore(database);
