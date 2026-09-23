import {
  createBillingService,
  type BillingService,
} from "../billing/service.js";
import {
  createCatalogService,
  type CatalogService,
} from "../catalog/service.js";
import type { ControlDatabase } from "../db/client.js";

export type CatalogBillingService = CatalogService & BillingService;

export const createCatalogBillingService = (
  database: ControlDatabase,
): CatalogBillingService => ({
  ...createCatalogService(database),
  ...createBillingService(database),
});
