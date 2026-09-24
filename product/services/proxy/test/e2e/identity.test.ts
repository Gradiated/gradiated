import { describe, expect, it } from "vitest";

import { useCases, type Case } from "../../../gateway/test/integration/case.js";
import { eventually } from "../../../gateway/test/integration/eventually.js";
import {
  CHAT,
  expectProxyError,
  MESSAGES,
  providerModel,
  relayHeaders,
  useProxy,
  type ProxyErrorCode,
  type RelayRoute,
} from "./support/fixtures.js";
import { IDENTITY_FRESH_SECONDS } from "./support/proxy-process.js";

const { makeCase } = useCases();
const fixture = useProxy(makeCase);

const relay = (instance: Case, route: RelayRoute = MESSAGES) =>
  fixture.proxy.client.post(route.path, {
    headers: relayHeaders(instance, route.provider),
    json: route.body(providerModel(route.provider)),
  });

const DENIALS: {
  name: string;
  deny: (instance: Case) => Promise<void>;
  code: ProxyErrorCode;
}[] = [
  {
    name: "a revoked key",
    deny: (instance) => instance.writeCredentialRow({ revokedAt: new Date() }),
    code: "invalid_api_key",
  },
  {
    name: "an expired key",
    deny: (instance) =>
      instance.writeCredentialRow({ expiresAt: new Date(Date.now() - 1000) }),
    code: "invalid_api_key",
  },
  {
    name: "an archived workspace",
    deny: (instance) => instance.setTenant({ workspaceArchived: true }),
    code: "workspace_archived",
  },
  {
    name: "a suspended organization",
    deny: (instance) => instance.setTenant({ organizationStatus: "suspended" }),
    code: "organization_suspended",
  },
  {
    name: "a deleted key",
    deny: (instance) =>
      instance.database
        .query("delete from api_keys where id = $1", [instance.credential])
        .then(() => undefined),
    code: "invalid_api_key",
  },
];

describe("relay authorization", () => {
  it.each(DENIALS)(
    "refuses $name before the provider sees the request",
    async ({ deny, code }) => {
      const instance = await makeCase("vllm");
      await deny(instance);

      for (const route of [MESSAGES, CHAT]) {
        expectProxyError(await relay(instance, route), code, route.provider);
      }
      expect(fixture.provider.requests).toEqual([]);
    },
  );

  it.each(DENIALS)(
    "stops relaying within the fresh lifetime after $name",
    async ({ deny, code }) => {
      const instance = await makeCase("vllm");
      expect((await relay(instance)).status).toBe(200);
      const denied = Date.now();

      await deny(instance);

      const refused = await eventually(
        async () => {
          const response = await relay(instance);
          return response.status === 200 ? undefined : response;
        },
        IDENTITY_FRESH_SECONDS * 1000 + 3000,
        "the denial never took effect",
      );
      expectProxyError(refused, code, "anthropic");
      expect(Date.now() - denied).toBeLessThan(
        IDENTITY_FRESH_SECONDS * 1000 + 3000,
      );
    },
  );

  it("authorizes a key created a moment ago", async () => {
    const instance = await makeCase("vllm");

    expect((await relay(instance)).status).toBe(200);
  });

  it("shares one database lookup across a burst for one key", async () => {
    const instance = await makeCase("vllm");
    const queriesBefore = await fixture.proxy.count(
      "proxy_identity_queries_total",
    );

    const responses = await Promise.all(
      Array.from({ length: 20 }, () => relay(instance)),
    );

    expect(responses.map((response) => response.status)).toEqual(
      Array(20).fill(200),
    );
    expect(await fixture.proxy.count("proxy_identity_queries_total")).toBe(
      queriesBefore + 1,
    );
  });
});
