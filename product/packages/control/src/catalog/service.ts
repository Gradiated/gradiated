import type {
  ModelDeploymentRelease,
  ModelPropertiesInput,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import type { ModelRecord, ModelDeploymentRecord } from "./records.js";
import { createCatalogStore } from "./store.js";

export type { ModelRecord, ModelDeploymentRecord } from "./records.js";
export type CatalogModelUpsert = Parameters<CatalogService["upsertModel"]>[0];

/**
 * A Git catalog definition. IDs differ per environment but slugs don't, so an
 * organization-owned model names its owner by slug; applying the catalog
 * resolves it, and the model ID must start with `<slug>/`.
 */
export type CatalogModelInput = Omit<CatalogModelUpsert, "organizationId"> & {
  owner?: { organizationSlug: string };
};

export interface CatalogService {
  /**
   * Public catalog models. Organization-owned models are left out unless
   * `includeOrganizationModels` is set, which only internal callers that never
   * publish the result (catalog apply, probes, fleet) may do.
   */
  listModels(options?: {
    includeRetired?: boolean;
    includeOrganizationModels?: boolean;
  }): Promise<ModelRecord[]>;
  upsertModel(input: {
    id: string;
    aliases?: string[];
    name: string;
    status: ModelRecord["status"];
    properties: ModelPropertiesInput;
    /** Omitted means OpenRouter cannot serve the model. */
    openrouterModelId?: string | null;
    /** A Hugging Face tokenizer at a commit, for counting without a deployment. */
    tokenizer?: { path: string; revision: string } | null;
    /** Omitted means a public catalog model. */
    organizationId?: string | null;
    /**
     * The interface the model serves: `decision` for SystemOne releases, `chat`
     * for the rest. Every deployment's release must serve it.
     */
    type: ModelRecord["type"];
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
