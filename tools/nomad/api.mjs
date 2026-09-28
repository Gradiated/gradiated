import { readFileSync } from "node:fs";
import { request } from "node:https";

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

export const createNomadClient = (signal) => {
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
  const get = async (path) => call(path, signal, await getToken());
  const post = async (path, body) => call(path, signal, await getToken(), body);
  return { get, post };
};
