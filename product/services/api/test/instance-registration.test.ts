import "reflect-metadata";

import { createPrivateKey, X509Certificate, webcrypto } from "node:crypto";

import * as x509 from "@peculiar/x509";
import { beforeAll, describe, expect, it } from "vitest";

import {
  hostBootstrapEnvironment,
  issueNomadClientCertificate,
  nodeName,
  nomadNodeIdentity,
  type HostBootstrap,
  type NomadCertificateAuthority,
} from "../src/operations/instances/host-bootstrap.js";
import {
  waitForNomadNode,
  type NomadNode,
} from "../src/operations/instances/nomad-node.js";
import { createRunPodProvider } from "../src/operations/instances/runpod.js";

const ecdsa = { name: "ECDSA", namedCurve: "P-256", hash: "SHA-256" };

const createAuthority = async (): Promise<NomadCertificateAuthority> => {
  const keys = await webcrypto.subtle.generateKey(ecdsa, true, [
    "sign",
    "verify",
  ]);
  const certificate = await x509.X509CertificateGenerator.createSelfSigned({
    serialNumber: "01",
    name: "CN=Test Nomad CA",
    keys,
    signingAlgorithm: ecdsa,
    notBefore: new Date("2026-01-01T00:00:00Z"),
    notAfter: new Date("2036-01-01T00:00:00Z"),
    extensions: [new x509.BasicConstraintsExtension(true, undefined, true)],
  });
  const privateKey = await webcrypto.subtle.exportKey("pkcs8", keys.privateKey);

  return {
    certificate: certificate.toString("pem"),
    privateKey: x509.PemConverter.encode(privateKey, "PRIVATE KEY"),
  };
};

// Made with `openssl req -utf8`, which encodes names as UTF8String like the
// production CA; the library's own encoding would hide an issuer mismatch.
const opensslAuthority: NomadCertificateAuthority = {
  certificate: `-----BEGIN CERTIFICATE-----
MIIBhzCCAS2gAwIBAgIUQGGzFMccTr4736JAO1Vu5HPEfkYwCgYIKoZIzj0EAwIw
GDEWMBQGA1UEAwwNVGVzdCBOb21hZCBDQTAgFw0yNjA5MjMyMTExMDRaGA8yMTI2
MDgzMDIxMTEwNFowGDEWMBQGA1UEAwwNVGVzdCBOb21hZCBDQTBZMBMGByqGSM49
AgEGCCqGSM49AwEHA0IABATWSu5SnmT35HWwlaREhxN7XlVMZzIQdPgItC1sBucp
PUzf/fWQazg3IYjQS4JDSLSsQG//1TVJ2J0mTTEEOyijUzBRMB0GA1UdDgQWBBTe
xS6uh0eiZU+gixSgWHUuJwQfuzAfBgNVHSMEGDAWgBTexS6uh0eiZU+gixSgWHUu
JwQfuzAPBgNVHRMBAf8EBTADAQH/MAoGCCqGSM49BAMCA0gAMEUCIEMOyUILMXm/
mAEK/TQmuJYD1YOHlKTd6Bqgpyav9hvlAiEAuRO1FVEagaa+1I2LCBZjmaUvlCAz
zMmx36G18ZK2V+w=
-----END CERTIFICATE-----`,
  privateKey: `-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg9TUfYllbQtT+Y8un
bLOTeCcrUi17FqK7A+0BMEVEPy+hRANCAAQE1kruUp5k9+R1sJWkRIcTe15VTGcy
EHT4CLQtbAbnKT1M3/31kGs4NyGI0EuCQ0i0rEBv/9U1SdidJk0xBDso
-----END PRIVATE KEY-----`,
};

describe("Nomad client certificate", () => {
  let authority: NomadCertificateAuthority;

  beforeAll(async () => {
    authority = await createAuthority();
  });

  it("is signed by the CA for Nomad's client role and local API", async () => {
    const issued = await issueNomadClientCertificate(
      authority,
      new Date("2026-09-23T00:00:00Z"),
    );
    const certificate = new X509Certificate(issued.certificate);

    expect(
      certificate.verify(new X509Certificate(authority.certificate).publicKey),
    ).toBe(true);
    expect(certificate.checkHost("client.global.nomad")).toBe(
      "client.global.nomad",
    );
    expect(certificate.checkIP("127.0.0.1")).toBe("127.0.0.1");
    expect(certificate.keyUsage).toEqual([
      "1.3.6.1.5.5.7.3.1",
      "1.3.6.1.5.5.7.3.2",
    ]);
    expect(certificate.ca).toBe(false);
    expect(
      certificate.checkPrivateKey(createPrivateKey(issued.privateKey)),
    ).toBe(true);
  });

  it("names its issuer with the CA's exact subject bytes, which Go requires", async () => {
    const issued = await issueNomadClientCertificate(opensslAuthority);

    expect(
      Buffer.from(
        new x509.X509Certificate(issued.certificate).issuerName.toArrayBuffer(),
      ),
    ).toEqual(
      Buffer.from(
        new x509.X509Certificate(
          opensslAuthority.certificate,
        ).subjectName.toArrayBuffer(),
      ),
    );
  });

  it("uses an ECDSA key, because Nomad rejects Ed25519 client keys", async () => {
    const issued = await issueNomadClientCertificate(authority);

    expect(
      new X509Certificate(issued.certificate).publicKey.asymmetricKeyType,
    ).toBe("ec");
  });

  it("never outlives the CA", async () => {
    const issued = await issueNomadClientCertificate(
      authority,
      new Date("2035-12-01T00:00:00Z"),
    );

    expect(new Date(new X509Certificate(issued.certificate).validTo)).toEqual(
      new Date("2036-01-01T00:00:00Z"),
    );
  });
});

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

type Call = { method: string; url: string; body: unknown };

const fakeRunPod = (pod: Record<string, unknown>) => {
  const calls: Call[] = [];
  let auths = [
    { id: "old", name: "gradiated-host-pod1-1" },
    { id: "other", name: "someone-else" },
  ];
  const fetch = async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url, body });
    const json = (value: unknown) => new Response(JSON.stringify(value));

    if (url.includes("/pods/")) return method === "GET" ? json(pod) : json({});
    if (method === "POST") {
      const created = { id: "new", name: body.name };
      auths = [...auths, created];
      return json(created);
    }
    if (method === "DELETE") {
      auths = auths.filter((auth) => !url.endsWith(`/${auth.id}`));
      return new Response("");
    }
    return json(auths);
  };

  return { calls, fetch: fetch as typeof globalThis.fetch, auths: () => auths };
};

const rtxPod = {
  id: "pod1",
  consumerUserId: "user_1",
  machineId: "machine1",
  gpuCount: 2,
  vcpuCount: 32,
  desiredStatus: "EXITED",
  env: { PUBLIC_KEY: "ssh-ed25519 debug" },
  machine: {
    dataCenterId: "US-NE-1",
    gpuTypeId: "NVIDIA RTX PRO 6000 Blackwell Server Edition",
  },
};

describe("RunPod provider", () => {
  it.each(["RUNNING", "CREATED", undefined])(
    "refuses reset at status %s before any provider mutation",
    async (desiredStatus) => {
      const runpod = fakeRunPod({ ...rtxPod, desiredStatus });
      const provider = createRunPodProvider({
        apiKey: "key",
        fetch: runpod.fetch,
      });
      const instance = await provider.describe("pod1");

      await expect(
        provider.bootstrap(
          instance,
          {
            reference: "registry.example/nomad-base@sha256:abc",
            registry: { username: "AWS", password: "token" },
          },
          {},
        ),
      ).rejects.toThrow("Refusing to reset");
      expect(runpod.calls.every((call) => call.method === "GET")).toBe(true);
    },
  );

  it("describes a pod as the instance row records it", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await expect(provider.describe("pod1")).resolves.toEqual({
      provider: "runpod",
      providerAccountId: "user_1",
      providerInstanceId: "pod1",
      region: "US-NE-1",
      faultDomain: "runpod:machine1",
      sku: "2x NVIDIA RTX PRO 6000 Blackwell Server Edition",
    });
  });

  it("reads the pod's current environment", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await expect(provider.environment("pod1")).resolves.toEqual({
      PUBLIC_KEY: "ssh-ed25519 debug",
    });
  });

  it("points the pod at the host image with its bootstrap and keeps other variables", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
      now: () => new Date(2),
    });
    const instance = await provider.describe("pod1");

    await provider.bootstrap(
      instance,
      {
        reference: "registry.example/nomad-base@sha256:abc",
        registry: { username: "AWS", password: "token" },
      },
      { GRADIATED_NODE_NAME: "runpod-pod1" },
    );

    expect(runpod.calls.find((call) => call.method === "POST")?.body).toEqual({
      name: "gradiated-host-pod1-2",
      username: "AWS",
      password: "token",
    });
    expect(runpod.calls.find((call) => call.method === "PATCH")?.body).toEqual({
      imageName: "registry.example/nomad-base@sha256:abc",
      env: {
        PUBLIC_KEY: "ssh-ed25519 debug",
        GRADIATED_NODE_NAME: "runpod-pod1",
      },
      containerRegistryAuthId: "new",
    });
    expect(runpod.auths().map((auth) => auth.id)).toEqual(["other", "new"]);
  });

  it("keeps the old pull credentials when the pod update fails", async () => {
    const runpod = fakeRunPod(rtxPod);
    const failing = (async (input, init) =>
      init?.method === "PATCH"
        ? new Response("no", { status: 500 })
        : runpod.fetch(input, init)) as typeof fetch;
    const provider = createRunPodProvider({ apiKey: "key", fetch: failing });

    await expect(
      provider.bootstrap(
        await provider.describe("pod1"),
        {
          reference: "r/i@sha256:abc",
          registry: { username: "u", password: "p" },
        },
        {},
      ),
    ).rejects.toThrow("RunPod PATCH /pods/pod1 failed: 500");
    expect(runpod.auths().map((auth) => auth.id)).toContain("old");
  });
});

describe("waiting for the Nomad node", () => {
  const node = (Status: string, instance = "instance-1"): NomadNode => ({
    ID: "node-1",
    Name: "runpod-pod1",
    Status,
    Meta: { gradiated_instance_id: instance },
  });
  const clock = () => {
    let time = 0;
    return {
      now: () => time,
      sleep: async (ms: number) => {
        time += ms;
      },
    };
  };

  it("returns once the node has joined and is ready", async () => {
    const states = [null, node("initializing"), node("ready")];

    await expect(
      waitForNomadNode(async () => states.shift() ?? null, {
        nomadNodeId: "node-1",
        instanceId: "instance-1",
        timeoutMs: 60_000,
        ...clock(),
      }),
    ).resolves.toMatchObject({ Status: "ready" });
  });

  it("rejects a node that carries another instance's metadata", async () => {
    await expect(
      waitForNomadNode(async () => node("ready", "instance-2"), {
        nomadNodeId: "node-1",
        instanceId: "instance-1",
        timeoutMs: 60_000,
        ...clock(),
      }),
    ).rejects.toThrow("belongs to instance instance-2, not instance-1");
  });

  it("gives up with the last status it saw", async () => {
    await expect(
      waitForNomadNode(async () => node("down"), {
        nomadNodeId: "node-1",
        instanceId: "instance-1",
        timeoutMs: 10_000,
        ...clock(),
      }),
    ).rejects.toThrow("was not ready after 10s (last status: down)");
  });
});
