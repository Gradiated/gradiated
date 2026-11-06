import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadEnv, type ViteDevServer } from "vite";
import { slackPreview } from "../scripts/slack-preview";

vi.mock("vite", async (original) => ({
  ...(await original<typeof import("vite")>()),
  loadEnv: vi.fn(),
}));

const settings = {
  SLACK_CONNECT_PREVIEW: "true",
  SLACK_BOT_TOKEN: "fake-bot-token",
  SLACK_ENGINEER_USER_IDS: "U123,U456",
};
const organizationId = "00000000-0000-4000-8000-000000000001";
const input = { organizationId, company: "Example", email: "test@example.com" };
type Handler = (request: unknown, response: unknown) => Promise<void>;

const setup = () => {
  let handler: Handler | undefined;
  const invite = vi.fn().mockResolvedValue({
    channel_id: "C123",
    channel_name: "ext-example-gradiated",
    email: input.email,
    status: "invited",
  });
  const postNotes = vi.fn().mockResolvedValue({ status: "sent" });
  const ssrLoadModule = vi
    .fn()
    .mockResolvedValue({ createSlackConnect: () => ({ invite, postNotes }) });
  const use = vi.fn((_path: string, middleware: Handler) => {
    handler = middleware;
  });
  const configure = slackPreview().configureServer as (
    server: ViteDevServer,
  ) => void;
  configure({
    middlewares: { use },
    ssrLoadModule,
  } as unknown as ViteDevServer);

  const request = async (
    method: string,
    url: string,
    body: unknown = input,
    origin = "http://localhost:5173",
  ) => {
    const result = { status: 200, body: "" };
    const response = {
      setHeader: vi.fn(),
      writeHead(status: number) {
        result.status = status;
        return this;
      },
      end(value: string) {
        result.body = value;
      },
    };
    await handler!(
      {
        method,
        url,
        headers: { host: "localhost:5173", origin },
        async *[Symbol.asyncIterator]() {
          yield Buffer.from(JSON.stringify(body));
        },
      },
      response,
    );
    return result;
  };

  return { request, invite, postNotes, use, ssrLoadModule };
};

describe("local live Slack preview", () => {
  it("posts notes only after an explicit same-origin request with the preview organization marker", async () => {
    const { request, postNotes, invite } = setup();
    const notes = {
      organizationId,
      email: input.email,
      channelName: "ext-example-gradiated",
      notes: "Context",
      requestId: organizationId,
    };
    expect(
      (await request("POST", "/messages", notes, "http://untrusted.example"))
        .status,
    ).toBe(403);
    expect(postNotes).not.toHaveBeenCalled();
    expect((await request("POST", "/messages", notes)).status).toBe(200);
    expect(postNotes).toHaveBeenCalledWith({
      ...notes,
      organizationId: `local-preview:${organizationId}`,
    });
    expect(invite).not.toHaveBeenCalled();
  });
  beforeEach(() => {
    vi.mocked(loadEnv).mockReturnValue({ ...settings });
  });

  it("is absent unless explicitly enabled", () => {
    vi.mocked(loadEnv).mockReturnValue({
      ...settings,
      SLACK_CONNECT_PREVIEW: "false",
    });
    expect(setup().use).not.toHaveBeenCalled();
  });

  it("reports availability without creating an invitation or exposing credentials", async () => {
    const { request, invite, ssrLoadModule } = setup();
    const result = await request("GET", "/");
    expect(JSON.parse(result.body)).toEqual({ enabled: true });
    expect(result.body).not.toContain(settings.SLACK_BOT_TOKEN);
    expect(invite).not.toHaveBeenCalled();
    expect(ssrLoadModule).not.toHaveBeenCalled();
  });

  it("rejects cross-origin invitation requests before calling Slack", async () => {
    const { request, invite } = setup();
    expect(
      (await request("POST", "/invitations", input, "http://untrusted.example"))
        .status,
    ).toBe(403);
    expect(invite).not.toHaveBeenCalled();
  });

  it("sends only on an explicit same-origin POST and uses the chosen email", async () => {
    const { request, invite } = setup();
    expect((await request("POST", "/invitations")).status).toBe(200);
    expect(invite).toHaveBeenCalledOnce();
    expect(invite).toHaveBeenCalledWith({
      ...input,
      organizationId: `local-preview:${organizationId}`,
    });
  });

  it("rejects invalid addresses without calling Slack", async () => {
    const { request, invite } = setup();
    expect(
      (await request("POST", "/invitations", { ...input, email: "invalid" }))
        .status,
    ).toBe(503);
    expect(invite).not.toHaveBeenCalled();
  });

  it("forwards a valid replacement channel name without weakening organization binding", async () => {
    const { request, invite } = setup();
    expect(
      (
        await request("POST", "/invitations", {
          ...input,
          channelName: "ext-example-team-gradiated",
        })
      ).status,
    ).toBe(200);
    expect(invite).toHaveBeenCalledWith({
      ...input,
      channelName: "ext-example-team-gradiated",
      organizationId: `local-preview:${organizationId}`,
    });
  });
});
