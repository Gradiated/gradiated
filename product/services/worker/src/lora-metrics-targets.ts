export type AdapterMetricsTarget = {
  id: string;
  modelId: string;
  serviceUrl: string;
};

export const loraMetricsTargets = (rows: AdapterMetricsTarget[]) =>
  rows.map((row) => {
    const url = new URL(row.serviceUrl);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw new Error("Invalid inference metrics target");

    return {
      targets: [url.host],
      labels: {
        __metrics_path__: `${url.pathname.replace(/\/$/, "")}/internal/adapters/metrics`,
        model: row.modelId,
        deployment: row.id,
        service: "inference",
      },
    };
  });
