import { afterEach, describe, expect, it } from "vitest";

import { callTool, closeServers } from "./support/mcp.js";

afterEach(closeServers);

describe("alertmanager tools", () => {
  it.each([
    [
      "alertmanager_alerts",
      { filter: ['alertname="WorkerLoopFailing"'], silenced: false },
      "/api/v2/alerts",
      { filter: ['alertname="WorkerLoopFailing"'], silenced: "false" },
    ],
    ["alertmanager_alerts", {}, "/api/v2/alerts", {}],
    [
      "alertmanager_silences",
      { filter: ['severity=~"critical|warning"'] },
      "/api/v2/silences",
      { filter: ['severity=~"critical|warning"'] },
    ],
  ])("%s with %o reads %s", async (name, args, path, parameters) => {
    const { backend, isError } = await callTool(name, args, []);

    expect(isError).toBe(false);
    expect(backend).toHaveBeenCalledWith("alertmanager", path, parameters);
  });
});
