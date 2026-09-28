import { describe, expect, it } from "vitest";

import {
  hostBootstrapEnvironment,
  nodeName,
  nomadNodeIdentity,
  servingEnvironment,
  type HostBootstrap,
} from "../../src/instances/host-bootstrap.js";

describe("host bootstrap environment", () => {
  const host: HostBootstrap = {
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
  const bound = "3f1e5a52-8d4b-4c1e-9a55-111111111111";
  const environment = {
    PUBLIC_KEY: "ssh-ed25519 debug",
    GRADIATED_NOMAD_NODE_ID: bound,
    GRADIATED_NOMAD_NODE_SECRET: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
  };

  it("keeps the bound node's identity so Nomad sees the same node return", () => {
    expect(nomadNodeIdentity(bound, environment)).toEqual({
      nomadNodeId: bound,
      nomadNodeSecret: "3f1e5a52-8d4b-4c1e-9a55-222222222222",
    });
  });

  it.each([
    ["the machine has never been registered", null, {}],
    ["the machine carries a node that was never bound", null, environment],
    [
      "the machine carries another node",
      "3f1e5a52-8d4b-4c1e-9a55-333333333333",
      environment,
    ],
  ])("starts a new node when %s", (_, boundNodeId, current) => {
    const identity = nomadNodeIdentity(boundNodeId, current);

    expect(identity.nomadNodeId).not.toBe(bound);
    expect(identity.nomadNodeSecret).not.toBe(
      environment.GRADIATED_NOMAD_NODE_SECRET,
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
