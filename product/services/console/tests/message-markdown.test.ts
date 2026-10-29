import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatMessage } from "@/components/playground/chat-message";
import { MessageMarkdown } from "@/components/playground/message-markdown";

const render = (content: string) =>
  renderToStaticMarkup(createElement(MessageMarkdown, { content }));

describe("playground message Markdown", () => {
  it("renders emphasis, lists, quotes, links, tables and task lists", () => {
    const html = render(
      "# Heading\n\n**Bold** and *italic* with `code`.\n\n- Item\n\n> Quote\n\n[Docs](https://example.com)\n\n| Name | Value |\n| --- | --- |\n| Speed | Fast |\n\n- [x] Ready",
    );

    for (const tag of [
      "h1",
      "strong",
      "em",
      "code",
      "ul",
      "li",
      "blockquote",
      "table",
      "th",
      "td",
    ]) {
      expect(html).toContain(`<${tag}`);
    }
    expect(html).toContain('type="checkbox"');
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("preserves fenced code and tolerates an unfinished streaming fence", () => {
    const html = render(
      '```typescript\nconst value = "<script>";\n  console.log(value);',
    );

    expect(html).toContain('<pre><code class="language-typescript">');
    expect(html).toContain("  console.log(value);");
    expect(html).toContain("&lt;script&gt;");
  });

  it("does not execute HTML, activate unsafe links, or fetch remote images", () => {
    const html = render(
      "<script>alert(1)</script>\n\n[bad](javascript:alert%281%29)\n\n![description](https://example.com/tracker.png)",
    );

    expect(html).not.toContain("<script");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("<a");
    expect(html).toContain("bad");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("tracker.png");
    expect(html).toContain("description");
  });

  it("keeps user prompts literal", () => {
    const html = renderToStaticMarkup(
      createElement(ChatMessage, {
        message: { id: "user", role: "user", content: "**bold**\n<script>" },
      }),
    );

    expect(html).toContain("**bold**\n&lt;script&gt;");
    expect(html).not.toContain("<strong>");
  });
});
