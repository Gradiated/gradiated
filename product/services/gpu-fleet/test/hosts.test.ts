import { describe, expect, it } from "vitest";

import { parseHosts } from "../src/hosts.js";
import { FIRST, gpuHost } from "./support/fleet.js";

const awsHost = (region: string, availabilityZone: string) => {
  const host = gpuHost(FIRST, "unused");
  return {
    ...host,
    metadata: { ...host.metadata, uid: "uid-1" },
    spec: {
      ...host.spec,
      provider: {
        name: "aws",
        accountId: "111122223333",
        region,
        availabilityZone,
        ec2InstanceId: "i-0123456789abcdef0",
      },
    },
  };
};

describe("GpuHost parsing", () => {
  it("takes an AWS host whose zone is its region plus one letter", () => {
    expect(parseHosts([awsHost("us-east-1", "us-east-1b")]).hosts).toHaveLength(
      1,
    );
  });

  it.each([
    ["us-east-1", "us-east-10a"],
    ["us-east-1", "us-west-2a"],
    ["us-east-1", "us-east-1"],
    ["us-east-1", "us-east-1ab"],
    ["us-east-1", "us-east-12"],
  ])("refuses region %s with zone %s", (region, zone) => {
    const { hosts, invalid } = parseHosts([awsHost(region, zone)]);
    expect(hosts).toEqual([]);
    expect(invalid).toEqual([{ name: `gpu-${FIRST}`, reported: false }]);
  });
});
