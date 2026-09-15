import type { ComponentType, ReactElement } from "react";
import {
  Band,
  Footer,
  Module,
  Nav,
  Reading,
  Substrate,
} from "../components/design";
import type { Article } from "../articles";
import {
  DocsCodeBlock,
  DocsInlineCode,
} from "../components/docs/DocsCodeBlock";
import { methodPages } from "../method";
import type { MethodSlug } from "../method";
import { storyAt } from "../library-stories";
import "../styles/index.css";

const articleContent = import.meta.glob<{
  default: ComponentType<Record<string, unknown>>;
}>("../../content/articles/*.mdx", { eager: true });

/* `Sep 9, 2026`, as the mock sets it. */
const on = (date: string) =>
  new Date(date).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

/* PLACEHOLDER date. Method carries none, so every handbook piece shows the
   same one — the field wants adding to method.tsx. */
const METHOD_DATE = "2026-09-09";

export const MethodReadingPage = ({
  slug,
}: {
  slug: MethodSlug;
}): ReactElement => {
  const page = methodPages.find((candidate) => candidate.slug === slug)!;
  const Content = page.Content;

  return (
    <Substrate>
      <Nav />
      <Band>
        <Module className="gr-module--top" index={0}>
          <Reading
            byline={on(METHOD_DATE)}
            bylineDateTime={METHOD_DATE}
            art={storyAt(`/library/method/${slug}/`)?.art?.tall}
            cover={storyAt(`/library/method/${slug}/`)?.cover}
            lede={page.indexDescription}
            tags={["Method", page.section]}
            title={page.title}
          >
            <Content />
          </Reading>
        </Module>
      </Band>
      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};

export const ArticleReadingPage = ({
  article,
}: {
  article: Article;
}): ReactElement => {
  const Content = articleContent[`../${article.file}`]?.default;
  if (!Content) throw new Error(`Missing article component: ${article.file}`);

  return (
    <Substrate>
      <Nav />
      <Band>
        <Module className="gr-module--top" index={0}>
          <Reading
            byline={
              article.status === "draft" ? "Draft" : on(article.publishedAt)
            }
            bylineDateTime={
              article.status === "draft" ? undefined : article.publishedAt
            }
            art={storyAt(article.path)?.art?.tall}
            cover={storyAt(article.path)?.cover}
            lede={article.description}
            tags={["Notes"]}
            title={article.title}
          >
            <Content
              components={{ code: DocsInlineCode, pre: DocsCodeBlock }}
            />
          </Reading>
        </Module>
      </Band>
      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
