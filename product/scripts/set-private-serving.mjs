import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import {
  createControlDatabase,
  createInstanceService,
  privateServingUrl,
} from "../packages/control/dist/index.js";

/** @param {string} base @param {string[]} allocationIds @param {typeof fetch} request */
export const probeAllocations = async (
  base,
  allocationIds,
  request = fetch,
) => {
  const proxy = await request(`${base}/private-healthz`, {
    redirect: "error",
    signal: AbortSignal.timeout(10_000),
  });
  await proxy.body?.cancel();
  if (proxy.status !== 200) throw new Error("Private host proxy health failed");

  for (const id of allocationIds) {
    const response = await request(`${base}/alloc/${id}/health`, {
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    await response.body?.cancel();

    if (response.status !== 200)
      throw new Error(`Allocation health failed: ${id}`);
  }
};

const main = async () => {
  const { values } = parseArgs({
    options: {
      "instance-id": { type: "string" },
      apply: { type: "boolean", default: false },
    },
  });
  if (!values["instance-id"] || !process.env.DATABASE_URL) {
    throw new Error("instance-id and DATABASE_URL are required");
  }
  const id = values["instance-id"];
  const servingUrl = privateServingUrl(id);
  const { database, pool } = createControlDatabase(process.env.DATABASE_URL);

  try {
    const inventory = createInstanceService(database);
    const { host, allocationIds } = await inventory.servingState(id);
    if (!host.nomadNodeId) throw new Error("An active bound host is required");

    await probeAllocations(servingUrl, allocationIds);
    if (values.apply)
      await inventory.setServingUrl(id, servingUrl, {
        nomadNodeId: host.nomadNodeId,
        servingUrl: host.servingUrl,
        allocationIds,
      });

    console.log(
      JSON.stringify({
        instance_id: id,
        nomad_node_id: host.nomadNodeId,
        serving_url: servingUrl,
        allocations_checked: allocationIds.length,
        applied: values.apply,
      }),
    );
  } finally {
    await pool.end();
  }
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().catch(() => {
    console.error(
      "Private serving qualification or activation failed; no provider reset was attempted",
    );
    process.exitCode = 1;
  });
}
