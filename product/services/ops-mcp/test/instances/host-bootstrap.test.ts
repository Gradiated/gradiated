import { describe, expect, it } from "vitest";

import {
  carriedBootstrap,
  hostBootstrapEnvironment,
  nodeName,
  nomadNodeIdentity,
  servingEnvironment,
  type HostBootstrap,
} from "../../src/instances/host-bootstrap.js";

describe("host bootstrap environment", () => {
  const host: HostBootstrap = {
    renewalToken: "r".repeat(43),
    instanceId: "019d5a4a-0000-7000-8000-000000000001",
    nodeName: "runpod-abc123",
    nomadNodeId: "3f1e5a52-8d4b-4c1e-9a55-111111111111",
    nomadNodeSecret: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
    ca: "ca pem\n",
    certificate: "cert pem\n",
    privateKey: "key pem\n",
    artifact: {
      accessKeyId: "AKIAEXAMPLEEXAMPLE12",
      secretAccessKey: "abcdEFGHijklMNOPqrstUVWXyz0123456789+/ab",
    },
  };
  const decode = (value: string | undefined) =>
    Buffer.from(value ?? "", "base64").toString();

  it("carries identity verbatim and file contents base64 encoded", () => {
    const environment = hostBootstrapEnvironment(host);

    expect(environment).toMatchObject({
      GRADIATED_INSTANCE_ID: host.instanceId,
      GRADIATED_NODE_NAME: "runpod-abc123",
      GRADIATED_NOMAD_NODE_ID: host.nomadNodeId,
      GRADIATED_NOMAD_NODE_SECRET: host.nomadNodeSecret,
    });
    expect(decode(environment.GRADIATED_NOMAD_KEY)).toBe("key pem\n");
    expect(decode(environment.GRADIATED_ARTIFACT_ENV)).toBe(
      "AWS_ACCESS_KEY_ID=AKIAEXAMPLEEXAMPLE12\n" +
        "AWS_SECRET_ACCESS_KEY=abcdEFGHijklMNOPqrstUVWXyz0123456789+/ab\n",
    );
  });

  it("refuses credentials the host could not safely source", () => {
    expect(() =>
      hostBootstrapEnvironment({
        ...host,
        artifact: { ...host.artifact, accessKeyId: "AKIA$(reboot)" },
      }),
    ).toThrow("Artifact access key id has an unexpected format");
  });

  it("names the node after the provider and machine", () => {
    expect(nodeName("runpod", "RldmCif788b98e")).toBe("runpod-rldmcif788b98e");
    expect(() => nodeName("runpod", "pod/../x")).toThrow();
  });
});

describe("Nomad node identity", () => {
  const instanceId = "019d5a4a-0000-7000-8000-000000000001";
  const carried = {
    PUBLIC_KEY: "ssh-ed25519 debug",
    GRADIATED_INSTANCE_ID: instanceId,
    GRADIATED_NOMAD_NODE_ID: "3f1e5a52-8d4b-4c1e-9a55-111111111111",
    GRADIATED_NOMAD_NODE_SECRET: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
  };

  it("reads the bootstrap a machine carries", () => {
    expect(carriedBootstrap(carried)).toEqual({
      instanceId,
      nomadNodeId: carried.GRADIATED_NOMAD_NODE_ID,
      nomadNodeSecret: carried.GRADIATED_NOMAD_NODE_SECRET,
    });
    expect(carriedBootstrap({ PUBLIC_KEY: "ssh-ed25519 debug" })).toBeNull();
    expect(
      carriedBootstrap({ ...carried, GRADIATED_NOMAD_NODE_SECRET: "" }),
    ).toBeNull();
  });

  it("keeps the node a machine carries for this instance, bound or not", () => {
    expect(nomadNodeIdentity(instanceId, carried)).toEqual({
      nomadNodeId: carried.GRADIATED_NOMAD_NODE_ID,
      nomadNodeSecret: carried.GRADIATED_NOMAD_NODE_SECRET,
    });
  });

  it.each([
    ["the machine has never been registered", {}],
    [
      "the machine carries another instance's node",
      {
        ...carried,
        GRADIATED_INSTANCE_ID: "019d5a4a-0000-7000-8000-000000000002",
      },
    ],
  ])("starts a new node when %s", (_, environment) => {
    const identity = nomadNodeIdentity(instanceId, environment);

    expect(identity.nomadNodeId).not.toBe(carried.GRADIATED_NOMAD_NODE_ID);
    expect(identity.nomadNodeSecret).not.toBe(
      carried.GRADIATED_NOMAD_NODE_SECRET,
    );
  });
});

describe("serving environment", () => {
  const token = "a".repeat(32);

  it("passes the gateway and status tokens to the host", () => {
    expect(
      servingEnvironment({
        runtimeAccess: token,
        deploymentStatus: `${token}b`,
      }),
    ).toEqual({
      GRADIATED_RUNTIME_ACCESS_TOKEN: token,
      GRADIATED_DEPLOYMENT_STATUS_TOKEN: `${token}b`,
    });
  });

  it.each(["short", `${"a".repeat(32)}"; reboot`])(
    "refuses a token the host could not safely write into nginx: %s",
    (bad) => {
      expect(() =>
        servingEnvironment({ runtimeAccess: bad, deploymentStatus: token }),
      ).toThrow("Serving tokens must contain 32-256 base64url characters");
    },
  );
});
