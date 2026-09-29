import { readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
import { pathToFileURL } from "node:url";

export const templateRequests = (config, enrollmentImage) => {
  if (
    !/:nomad-base-inputs-[a-f0-9]{64}$/.test(config.image) ||
    config.image !== enrollmentImage
  )
    throw new Error("Templates must use the immutable tagged enrollment image");

  return config.models.map(({ name, volumeGb }) => ({
    name,
    image: config.image,
    args: "",
    disk: 100,
    mounts: { persistent: { path: "/workspace", size: volumeGb } },
    ports: ["8888/http", "22/tcp"],
    env: {},
    registry: null,
    public: false,
    serverless: false,
    startSsh: true,
    startJupyter: false,
    allowedCudaVersions: config.allowedCudaVersions,
  }));
};

export const reconcileTemplates = async (requests, call, apply) => {
  const existing = [];
  let cursor;
  do {
    const page = await call(
      "GET",
      `/templates${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    existing.push(...page.templates);
    cursor = page.pagination.hasNextPage ? page.pagination.nextCursor : null;
    if (page.pagination.hasNextPage && !cursor)
      throw new Error("RunPod template pagination omitted its next cursor");
  } while (cursor);

  const matches = requests.map((request) => {
    const found = existing.filter((item) => item.name === request.name);
    if (found.length > 1)
      throw new Error(`Duplicate template: ${request.name}`);
    const current = found[0];
    if (
      current &&
      Object.entries(request).some(
        ([key, value]) => !isDeepStrictEqual(current[key], value),
      )
    )
      throw new Error(
        `Template differs: ${request.name}; create a new version`,
      );

    return current;
  });

  const results = [];
  for (const [index, request] of requests.entries()) {
    const current = matches[index];
    const result =
      current ?? (apply ? await call("POST", "/templates", request) : null);
    results.push({
      name: request.name,
      id: result?.id,
      status: current ? "unchanged" : apply ? "created" : "missing",
      ...(result && {
        url: `https://console.runpod.io/deploy?template=${result.id}`,
      }),
    });
  }
  return results;
};

const main = async () => {
  const mode = process.argv[2] ?? "--plan";
  if (!["--plan", "--check", "--apply"].includes(mode))
    throw new Error("Usage: runpod-templates.mjs [--plan|--check|--apply]");

  const config = JSON.parse(
    readFileSync(
      new URL(
        "../../infra/environments/prod/runpod/templates.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  const workload = readFileSync(
    new URL(
      "../../infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml",
      import.meta.url,
    ),
    "utf8",
  );
  const image = workload.match(/name: NOMAD_BASE_IMAGE\s+value: (\S+)/)?.[1];
  const requests = templateRequests(config, image);
  if (mode === "--plan") {
    console.log(JSON.stringify(requests, null, 2));
    return;
  }
  if (!process.env.RUNPOD_API_KEY)
    throw new Error("RUNPOD_API_KEY is required");

  const call = async (method, path, body) => {
    const response = await fetch(`https://api.runpod.io/v2${path}`, {
      method,
      headers: {
        authorization: `Bearer ${process.env.RUNPOD_API_KEY}`,
        "content-type": "application/json",
      },
      ...(body && { body: JSON.stringify(body) }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok)
      throw new Error(`RunPod ${method} ${path}: HTTP ${response.status}`);
    return response.json();
  };
  const { keys } = await call("GET", "/account/ssh-keys");
  if (!keys.length) throw new Error("Register an account SSH public key first");
  const { delegations } = await call("GET", "/registries/delegations");
  if (!delegations.some((item) => item.dockerRegistryUri === config.image))
    throw new Error("The enrollment image needs its RunPod ECR delegation");

  const results = await reconcileTemplates(requests, call, mode === "--apply");
  console.log(JSON.stringify(results, null, 2));
  if (mode === "--check" && results.some((item) => item.status === "missing"))
    process.exitCode = 1;
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
