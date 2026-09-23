import { describe, expect, it } from "vitest";
import { parseArguments, UsageError } from "../src/arguments.js";

const parse = (argv: string[], stdinIsTTY = true) =>
  parseArguments(argv, { stdinIsTTY, environmentKey: "grad_environment" });

const installOptions = (argv: string[], stdinIsTTY = true) => {
  const command = parse(argv, stdinIsTTY);
  if (command.kind !== "install") throw new Error(`Parsed ${command.kind}`);
  return command.options;
};

describe("parseArguments", () => {
  it("defaults to an interactive install against the production API", () => {
    expect(parse([])).toEqual({
      kind: "install",
      options: {
        credential: { kind: "discover", environmentKey: "grad_environment" },
        agent: undefined,
        model: undefined,
        apiBaseUrl: "https://api.gradiated.com",
        dryRun: false,
        interactive: true,
      },
    });
  });

  it.each([
    [["help"], "help"],
    [["--help"], "help"],
    [["uninstall", "--help"], "help"],
    [["--version"], "version"],
    [["install"], "install"],
    [["uninstall"], "uninstall"],
  ])("parses %j as %s", (argv, kind) => {
    expect(parse(argv).kind).toBe(kind);
  });

  it("does not treat a flag value as the command", () => {
    expect(parse(["--agent", "codex", "uninstall", "--yes"])).toEqual({
      kind: "uninstall",
      options: { agent: "codex", dryRun: false, interactive: false },
    });
  });

  it("is interactive only without --yes and with a terminal on stdin", () => {
    expect(installOptions([]).interactive).toBe(true);
    expect(installOptions(["--yes"]).interactive).toBe(false);
    expect(installOptions([], false).interactive).toBe(false);
  });

  it.each([
    [["--key", "grad_k"], { kind: "key", key: "grad_k" }],
    [["--signup"], { kind: "account", mode: "signup" }],
    [["--login"], { kind: "account", mode: "login" }],
  ])("parses the credential of %j", (argv, credential) => {
    expect(installOptions(argv).credential).toEqual(credential);
  });

  it("strips trailing slashes from the API base URL", () => {
    expect(
      installOptions(["--api-base-url", "https://staging.example.com//"])
        .apiBaseUrl,
    ).toBe("https://staging.example.com");
  });

  it.each([
    [["--model", "--yes"], "--model"],
    [["--agnet", "codex"], "--agnet"],
    [["--agent", "cursor"], 'Unsupported agent "cursor"'],
    [["install", "uninstall"], 'Unexpected argument "uninstall"'],
    [["setup"], 'Unknown command "setup"'],
    [["--api-base-url", "not a url"], "not a valid --api-base-url"],
    [
      ["--key", "grad_k", "--login"],
      "--key and --login cannot be used together",
    ],
    [["--signup", "--login"], "--signup and --login cannot be used together"],
    [
      ["--key", "grad_k", "--signup", "--login"],
      "--key and --signup and --login cannot be used together",
    ],
    [["--dry-run", "--signup"], "--dry-run cannot be used with --signup"],
    [["uninstall", "--key", "grad_k"], "uninstall does not accept --key"],
    [["uninstall", "--model", "m"], "uninstall does not accept --model"],
    [["uninstall", "--login"], "uninstall does not accept --login"],
    [
      ["uninstall", "--api-base-url", "https://example.com"],
      "uninstall does not accept --api-base-url",
    ],
  ])("rejects %j", (argv, message) => {
    const attempt = () => parse(argv);

    expect(attempt).toThrow(UsageError);
    expect(attempt).toThrow(message);
    expect(attempt).toThrow("Run gradiated --help");
  });
});
