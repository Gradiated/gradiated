import {
  createCatalogBillingService,
  createControlDatabase,
  type CatalogBillingService,
  type ControlDatabase,
} from "@gradiated/control";

export type CatalogModelInput = Parameters<
  CatalogBillingService["upsertModel"]
>[0];

type ModelDeploymentInput = Parameters<
  CatalogBillingService["upsertModelDeployment"]
>[0];

export interface ModelDeploymentsConfiguration {
  model: CatalogModelInput;
  deployments: readonly { id: string; serviceUrl: string }[];
  placement: Pick<ModelDeploymentInput, "provider" | "region" | "faultDomain">;
  release: ModelDeploymentInput["release"];
}

export const requiredEnv = (name: string): string => {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required`);

  return value;
};

export const requiredServiceUrls = <Id extends string>(
  name: string,
  deploymentIds: readonly Id[],
): Array<{ id: Id; serviceUrl: string }> => {
  const serviceUrls = requiredEnv(name)
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const countMismatch = () =>
    new Error(`${name} must contain ${deploymentIds.length} URLs`);
  if (serviceUrls.length > deploymentIds.length) throw countMismatch();

  return deploymentIds.map((id, index) => {
    const serviceUrl = serviceUrls[index];
    if (!serviceUrl) throw countMismatch();

    return { id, serviceUrl };
  });
};

export const withControlDatabase = async <Result>(
  operation: (context: {
    database: ControlDatabase;
    catalog: CatalogBillingService;
  }) => Promise<Result>,
  databaseUrl = requiredEnv("DATABASE_URL"),
): Promise<Result> => {
  const { database, pool } = createControlDatabase(databaseUrl);

  try {
    return await operation({
      database,
      catalog: createCatalogBillingService(database),
    });
  } finally {
    await pool.end();
  }
};

export const upsertModelDeployments = async (
  catalog: Pick<CatalogBillingService, "upsertModel" | "upsertModelDeployment">,
  { model, deployments, placement, release }: ModelDeploymentsConfiguration,
): Promise<void> => {
  await catalog.upsertModel(model);

  for (const { id, serviceUrl } of deployments) {
    await catalog.upsertModelDeployment({
      id,
      modelId: model.id,
      status: "available",
      ...placement,
      serviceUrl,
      release,
    });
  }
};

export const configureModelDeployments = (
  configuration: ModelDeploymentsConfiguration,
): Promise<void> =>
  withControlDatabase(({ catalog }) =>
    upsertModelDeployments(catalog, configuration),
  );
