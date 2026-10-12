import { parseArgs } from "node:util";
import { pathToFileURL } from "node:url";
import {
  createControlDatabase,
  createInstanceService,
  privateServingUrl,
} from "../packages/control/dist/index.js";

/** @param {string} base @param {string[]} allocationIds @param {string} token @param {typeof fetch} request */
export const probeAllocations = async (
  base,
  allocationIds,
  token,
  request = fetch,
) => {
  if (!allocationIds.length)
    throw new Error("No available allocations to qualify");

  for (const id of allocationIds) {
    const response = await request(`${base}/alloc/${id}/health`, {
      headers: { authorization: `Bearer ${token}` },
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
    });
    await response.body?.cancel();

    if (response.status !== 200)
      throw new Error(`Allocation health failed: ${id}`);
  }
};

/** @param {{provider: string, providerInstanceId: string}} host */
export const publicServingUrl = (host) => {
  if (
    host.provider !== "runpod" ||
    !/^[a-z0-9]+$/i.test(host.providerInstanceId)
  )
    throw new Error("Public rollback requires a RunPod host");

  return `https://${host.providerInstanceId.toLowerCase()}-8888.proxy.runpod.net`;
};

const main = async () => {
  const { values } = parseArgs({
    options: {
      "instance-id": { type: "string" },
      apply: { type: "boolean", default: false },
      public: { type: "boolean", default: false },
    },
  });
  if (
    !values["instance-id"] ||
    !process.env.DATABASE_URL ||
    !process.env.SGLANG_API_KEY
  ) {
    throw new Error(
      "instance-id, DATABASE_URL and SGLANG_API_KEY are required",
    );
  }
  const id = values["instance-id"];
  const servingUrl = privateServingUrl(id);
  const { database, pool } = createControlDatabase(process.env.DATABASE_URL);

  try {
    const inventory = createInstanceService(database);
    const { host, allocationIds } = await inventory.servingState(id);
    if (!host.nomadNodeId) throw new Error("An active bound host is required");

    const probeUrl = values.public ? publicServingUrl(host) : servingUrl;
    await probeAllocations(probeUrl, allocationIds, process.env.SGLANG_API_KEY);
    if (values.apply)
      await inventory.setServingUrl(id, values.public ? null : servingUrl, {
        nomadNodeId: host.nomadNodeId,
        servingUrl: host.servingUrl,
        allocationIds,
      });

    console.log(
      JSON.stringify({
        instance_id: id,
        nomad_node_id: host.nomadNodeId,
        serving_url: values.public ? null : servingUrl,
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
