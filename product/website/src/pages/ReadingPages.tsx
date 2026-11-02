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

export const ArticleReadingPage = ({
  article,
}: {
  article: Article;
}): ReactElement => {
  const Content = articleContent[`../${article.file}`]?.default;
  if (!Content) throw new Error(`Missing article component: ${article.file}`);

  if (article.layout === "journey") {
    return (
      <Substrate>
        <Nav />
        <Content article={article} />
        <Band>
          <Footer index={1} />
        </Band>
      </Substrate>
    );
  }

  return (
    <Substrate>
      <Nav />
      <Band>
        <Module className="gr-module--top" index={0}>
          <Reading
            byline={
              article.status === "draft" ? undefined : on(article.publishedAt)
            }
            bylineDateTime={
              article.status === "draft" ? undefined : article.publishedAt
            }
            art={storyAt(article.path)?.art?.tall}
            cover={storyAt(article.path)?.cover}
            lede={article.description}
            tags={[article.category === "hardware" ? "Hardware" : "Notes"]}
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
