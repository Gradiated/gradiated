export type AdapterMetricsTarget = {
  id: string;
  modelId: string;
  serviceUrl: string;
};

export const loraMetricsTargets = (rows: AdapterMetricsTarget[]) =>
  rows.map((row) => {
    const url = new URL(row.serviceUrl);
    const privateTarget =
      /^http:\/\/gpu-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.tailscale-inference\.svc\.cluster\.local:8888\/alloc\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/?$/.test(
        row.serviceUrl,
      );
    if (
      (url.protocol !== "https:" && !privateTarget) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    )
      throw new Error("Invalid inference metrics target");

    return {
      targets: [url.host],
      labels: {
        __scheme__: url.protocol.slice(0, -1),
        __metrics_path__: `${url.pathname.replace(/\/$/, "")}/internal/adapters/metrics`,
        model: row.modelId,
        deployment: row.id,
        service: "inference",
      },
    };
  });
