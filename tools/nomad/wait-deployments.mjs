import { readFileSync } from "node:fs";
import { request } from "node:https";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";

export const waitForDeployment = async (
  id,
  { get, signal, pause = (ms) => delay(ms, undefined, { signal }) },
) => {
  while (!signal.aborted) {
    const deployment = await get(
      `/v1/deployment/${encodeURIComponent(id)}`,
      signal,
    );
    if (deployment.Status === "successful") return;
    if (["failed", "cancelled", "blocked"].includes(deployment.Status)) {
      throw new Error(`Deployment ${id} is ${deployment.Status}`);
    }
    await pause(10_000);
  }
  throw new Error(
    `Deployment ${id} did not become healthy before its deadline`,
  );
};

export const waitForEvaluation = async (id, previous, options) => {
  const {
    get,
    signal,
    pause = (ms) => delay(ms, undefined, { signal }),
  } = options;
  while (!signal.aborted) {
    const evaluation = await get(
      `/v1/evaluation/${encodeURIComponent(id)}`,
      signal,
    );
    if (["failed", "cancelled"].includes(evaluation.Status))
      throw new Error(`Evaluation ${id} is ${evaluation.Status}`);
    if (evaluation.Status === "complete") {
      if (evaluation.DeploymentID && evaluation.DeploymentID !== previous) {
        await waitForDeployment(evaluation.DeploymentID, options);
      }
      return;
    }
    await pause(1_000);
  }
  throw new Error(`Evaluation ${id} did not complete before its deadline`);
};

export const renewingToken = (initial, renew, now = Date.now) => {
  let token = initial;
  let refreshedAt = now();
  let inFlight;
  return async () => {
    if (now() - refreshedAt >= 45 * 60_000) {
      inFlight ??= renew()
        .then((next) => {
          token = next;
          refreshedAt = now();
        })
        .finally(() => {
          inFlight = undefined;
        });
      await inFlight;
    }
    return token;
  };
};

const main = async () => {
  const deployments = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const controller = new AbortController();
  const signal = AbortSignal.any([
    controller.signal,
    AbortSignal.timeout(110 * 60_000),
  ]);
  const call = (path, signal, token, body) =>
    new Promise((resolve, reject) => {
      const req = request(
        new URL(path, process.env.NOMAD_ADDR),
        {
          ca: readFileSync(process.env.NOMAD_CACERT),
          cert: readFileSync(process.env.NOMAD_CLIENT_CERT),
          key: readFileSync(process.env.NOMAD_CLIENT_KEY),
          servername: process.env.NOMAD_TLS_SERVER_NAME,
          method: body ? "POST" : "GET",
          headers: {
            "x-nomad-token": token ?? "",
            "content-type": "application/json",
          },
          signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
        },
        (response) => {
          let body = "";
          response.setEncoding("utf8");
          response.on("data", (chunk) => {
            body += chunk;
          });
          response.on("error", reject);
          response.on("end", () => {
            if (response.statusCode !== 200)
              return reject(new Error(`Nomad returned ${response.statusCode}`));
            try {
              resolve(JSON.parse(body));
            } catch (error) {
              reject(error);
            }
          });
        },
      );
      req.on("error", reject);
      req.end(body ? JSON.stringify(body) : undefined);
    });
  const getToken = renewingToken(process.env.NOMAD_TOKEN, async () => {
    const url = new URL(process.env.ACTIONS_ID_TOKEN_REQUEST_URL);
    url.searchParams.set("audience", "nomad.gradiated.com");
    const response = await fetch(url, {
      headers: {
        authorization: `bearer ${process.env.ACTIONS_ID_TOKEN_REQUEST_TOKEN}`,
      },
      signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
    });
    if (!response.ok)
      throw new Error(`Workflow identity renewal returned ${response.status}`);
    const { value } = await response.json();
    if (typeof value !== "string" || !value)
      throw new Error("Workflow identity renewal omitted its token");
    const result = await call("/v1/acl/login", signal, undefined, {
      AuthMethodName: "github-actions",
      LoginToken: value,
    });
    if (typeof result.SecretID !== "string" || !result.SecretID)
      throw new Error("Nomad login omitted its token");
    return result.SecretID;
  });
  const get = async (path, signal) => call(path, signal, await getToken());
  try {
    await Promise.all(
      deployments.map(async ({ job, evaluation, previous }) => {
        console.log(
          `Waiting for ${job} evaluation ${evaluation} and any new deployment`,
        );
        await waitForEvaluation(evaluation, previous, { get, signal });
        console.log(
          `${job}: evaluation complete; any new deployment is healthy`,
        );
      }),
    );
  } finally {
    controller.abort();
  }
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
